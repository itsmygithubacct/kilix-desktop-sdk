/* Harmless lifecycle tests: every process operation is a mock. */
#include <assert.h>
#include <stdarg.h>
#include <fcntl.h>
#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/syscall.h>
static int mock_open(const char *, int, ...);
static pid_t mock_waitpid(pid_t, int *, int);
static int mock_kill(pid_t, int);
static int mock_spawn(pid_t *, const char *, const posix_spawn_file_actions_t *,
                      const posix_spawnattr_t *, char *const [], char *const []);
static int mock_sleep(const struct timespec *, struct timespec *);
static long mock_syscall(long, ...);
static int mock_rename(const char *, const char *);
#define rename mock_rename
#define open mock_open
#define waitpid mock_waitpid
#define kill mock_kill
#define posix_spawnp mock_spawn
#define nanosleep mock_sleep
#define syscall mock_syscall
#include "../src/laptop_run.c"
#undef rename
#undef open
#undef waitpid
#undef kill
#undef posix_spawnp
#undef nanosleep
#undef syscall
static char root[PATH_MAX];
static int wait_error, spawned, terms, kills, stable_signals, sleeps;
static bool exited, pidfd_available = true, swap_identity, fail_registration;
static int mock_rename(const char *a, const char *b)
{
    if (fail_registration && strstr(b, ".pid") && !strstr(b, ".identity")) {
        errno = EACCES; return -1;
    }
    return rename(a, b);
}
static int mock_open(const char *path, int flags, ...)
{
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args; va_start(args, flags); mode = va_arg(args, int); va_end(args);
    }
    char fixture[PATH_MAX];
    if (strcmp(path, "/proc/4242/stat") == 0) {
        assert(snprintf(fixture, sizeof fixture, "%s/stat", root) > 0);
        path = fixture;
    } else if (strcmp(path, "/proc/sys/kernel/random/boot_id") == 0) {
        assert(snprintf(fixture, sizeof fixture, "%s/boot", root) > 0);
        path = fixture;
    } else if (strncmp(path, "/proc/", 6) == 0) {
        errno = ENOENT; return -1;
    }
    return open(path, flags, mode);
}
static pid_t mock_waitpid(pid_t pid, int *status, int options)
{
    assert(pid == 4242 && options == WNOHANG);
    if (wait_error) { errno = wait_error; return -1; }
    if (exited) { if (status) *status = 0; return pid; }
    return 0;
}
static int mock_kill(pid_t pid, int sig)
{
    assert(pid == 4242);
    if (sig == SIGTERM) terms++;
    else if (sig == SIGKILL) kills++;
    else assert(sig == 0);
    return 0;
}
static int mock_spawn(pid_t *pid, const char *file,
                      const posix_spawn_file_actions_t *actions,
                      const posix_spawnattr_t *attr,
                      char *const argv[], char *const env[])
{
    (void)file; (void)actions; (void)attr; (void)env;
    if (strcmp(argv[1], "laptop") == 0) return ENOENT;
    spawned++; *pid = 4242; return 0;
}
static int mock_sleep(const struct timespec *a, struct timespec *b)
{ (void)a; (void)b; sleeps++; return 0; }
static long mock_syscall(long number, ...)
{
    va_list args; va_start(args, number);
    long result;
    if (number == SYS_pidfd_open) {
        assert(va_arg(args, int) == 4242);
        if (!pidfd_available) { errno = ENOSYS; result = -1; }
        else {
            result = open("/dev/null", O_RDONLY);
            if (swap_identity) {
                /* Replace the synthetic birth identity after handle acquisition. */
                char stat[PATH_MAX];
                assert(format_two(stat, sizeof stat, "%s/stat", root, NULL));
                FILE *f = fopen(stat, "w"); assert(f);
                fputs("4242 (fixture) S 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 999 0\n", f);
                assert(fclose(f) == 0);
            }
        }
    } else {
        assert(number == SYS_pidfd_send_signal);
        assert(va_arg(args, int) >= 0);
        assert(va_arg(args, int) == SIGTERM);
        stable_signals++; result = 0;
    }
    va_end(args); return result;
}
bool launcher_enabled(void) { return true; }
bool laptop_directory(char *path, size_t size)
{ return format_two(path, size, "%s/profiles", root, NULL); }
bool laptop_load(const char *id, LaptopProfile *p, char *e, size_t n)
{
    (void)e; (void)n; memset(p, 0, sizeof *p);
    snprintf(p->id, sizeof p->id, "%s", id); return true;
}
bool laptop_write_session(const LaptopProfile *p, const char *path, char *e, size_t n)
{ (void)p; (void)path; (void)e; (void)n; return true; }
size_t laptop_desktop_arguments(const LaptopProfile *p, const char *a[2])
{ (void)p; a[0] = "cap"; return 1; }
static void fixture(const char *name, const char *text)
{
    char path[PATH_MAX]; assert(format_two(path, sizeof path, "%s/%s", root, name));
    FILE *f = fopen(path, "w"); assert(f); fputs(text, f); assert(fclose(f) == 0);
}
int main(int argc, char **argv)
{
    assert(argc == 2); snprintf(root, sizeof root, "%s", argv[1]);
    fixture("stat", "4242 (fixture with ) parentheses) S 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 123 0\n");
    fixture("boot", "01234567-89ab-cdef-0123-456789abcdef\n");
    char error[128], path[PATH_MAX], metadata[PATH_MAX]; long pid;
    assert(laptop_run_record("bench", 4242));
    assert(laptop_run_status("bench", &pid) == 1 && pid == 4242);
    assert(laptop_run_close("bench", error, sizeof error) && stable_signals == 1);
    fixture("boot", "fedcba98-7654-3210-fedc-ba9876543210\n");
    assert(laptop_run_status("bench", NULL) == -1);
    assert(!laptop_run_close("bench", error, sizeof error) && stable_signals == 1);
    fixture("boot", "01234567-89ab-cdef-0123-456789abcdef\n");
    pidfd_available = false;
    assert(!laptop_run_close("bench", error, sizeof error));
    pidfd_available = true;
    swap_identity = true;
    assert(!laptop_run_close("bench", error, sizeof error) && stable_signals == 1);
    swap_identity = false;
    assert(laptop_run_status("bench", NULL) == -1);
    assert(run_pid_path("bench", path, sizeof path));
    assert(format_two(metadata, sizeof metadata, "%s.identity", path, NULL));
    assert(unlink(metadata) == 0);
    assert(!laptop_run_close("bench", error, sizeof error));
    assert(access(path, F_OK) == 0); /* legacy record preserved */
    setenv("KILIX_HOME", root, 1); setenv("KITTY_LISTEN_ON", "mock", 1);
    setenv("KILIX_RC_PASSWORD_FILE", "mock-not-a-file", 1);
    assert(!laptop_run_open("bench", error, sizeof error) && spawned == 0);
    assert(write_run_file(path, "invalid\n", 8));
    assert(laptop_run_status("bench", NULL) == -1);
    assert(!laptop_run_close("bench", error, sizeof error));
    assert(unlink(path) == 0);
    assert(laptop_run_close("bench", error, sizeof error));
    assert(terms == 0 && kills == 0);

    for (int i = 0; i < RUN_CHILD_MAX; i++) run_children[i] = 4242;
    assert(available_child_slot() == -1);
    wait_error = EINTR; assert(available_child_slot() == -1);
    wait_error = ECHILD; assert(available_child_slot() == 0);
    wait_error = 0;
    setenv("KILIX_HOME", root, 1); setenv("KITTY_LISTEN_ON", "mock", 1);
    setenv("KILIX_RC_PASSWORD_FILE", "mock-not-a-file", 1);
    assert(format_two(path, sizeof path, "%s/config", root, NULL));
    setenv("KILIX_CAP_CONFIG_HOME", path, 1);
    for (int i = 0; i < RUN_CHILD_MAX; i++) run_children[i] = 4242;
    assert(!laptop_run_open("bench", error, sizeof error));
    assert(strstr(error, "capacity") && spawned == 0 && sleeps == 0);
    memset(run_children, 0, sizeof run_children);
    /* Inject publication failure without starting any real process. */
    fail_registration = true;
    assert(!laptop_run_open("bench", error, sizeof error));
    assert(strstr(error, "registered") && spawned == 1 && terms == 1 && kills == 1);
    assert(sleeps <= 45 && run_children[0] == 4242);
    exited = true; reap_run_children(); assert(run_children[0] == 0); exited = false;
    fail_registration = false;
    assert(laptop_run_open("bench", error, sizeof error));
    assert(laptop_run_status("bench", NULL) == 1 && spawned == 2);
    assert(terms == 1 && kills == 1);
    fixture("stat", "4242 (fixture) Z 0\n");
    assert(laptop_run_status("bench", NULL) == 0);
    assert(!laptop_run_record("bench", 4242));
    assert(!laptop_run_close("bench", error, sizeof error));
    puts("laptop lifecycle mocks: passed");
}
