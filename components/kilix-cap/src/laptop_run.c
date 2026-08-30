/* laptop_run.c — run registry, host-verb handoff, fallback spawn.
 * Contract: src/laptop_run.h; spec: docs/LAPTOP.md.
 *
 * Everything that runs a program here is a fixed argv vector through
 * posix_spawnp with stdio on /dev/null — profile text can never reach a
 * shell. The registry rules are deliberately identical, byte for byte of
 * behavior, to kilix-land-desktop's laptop.c and the host's
 * config/laptop.py: four surfaces share these files, and the only thing
 * that keeps them agreeing is all of them enforcing the same checks. */
#include "laptop_run.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

extern char **environ;

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

enum { RUN_CHILD_MAX = 8 };

/* Short-lived helper children (`kilix laptop open|close`) and fallback
 * session windows this process spawned; reaped opportunistically so an
 * exited child never lingers as a zombie that would fool kill(pid, 0)
 * elsewhere. */
static pid_t run_children[RUN_CHILD_MAX];

static void reap_run_children(void)
{
    for (int i = 0; i < RUN_CHILD_MAX; i++) {
        if (run_children[i] <= 0) continue;
        if (waitpid(run_children[i], NULL, WNOHANG) != 0)
            run_children[i] = 0;
    }
}

static void track_run_child(pid_t pid)
{
    reap_run_children();
    for (int i = 0; i < RUN_CHILD_MAX; i++) {
        if (run_children[i] <= 0) {
            run_children[i] = pid;
            return;
        }
    }
    /* Full table: block briefly on the oldest slot rather than leak it. */
    (void)waitpid(run_children[0], NULL, 0);
    run_children[0] = pid;
}

static void set_error(char *error, size_t error_size, const char *message)
{
    if (error != NULL && error_size > 0)
        (void)snprintf(error, error_size, "%s", message);
}

static bool format_two(char *dst, size_t size, const char *format,
                       const char *a, const char *b)
{
    int n = snprintf(dst, size, format, a, b);
    return n >= 0 && (size_t)n < size;
}

static bool valid_run_id(const char *id)
{
    size_t i;
    if (id == NULL || id[0] == '\0' || id[0] == '.') return false;
    if (strlen(id) >= LAPTOP_ID_MAX) return false;
    for (i = 0; id[i] != '\0'; i++) {
        char c = id[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')
            continue;
        return false;
    }
    return true;
}

static bool ensure_run_directory(const char *path)
{
    struct stat info;
    if (stat(path, &info) == 0) return S_ISDIR(info.st_mode);
    if (errno != ENOENT) return false;
    {
        char parent[PATH_MAX];
        const char *slash = strrchr(path, '/');
        if (slash == NULL || slash == path) return false;
        if ((size_t)(slash - path) >= sizeof parent) return false;
        memcpy(parent, path, (size_t)(slash - path));
        parent[slash - path] = '\0';
        if (!ensure_run_directory(parent)) return false;
    }
    return mkdir(path, 0700) == 0 || errno == EEXIST;
}

static bool read_run_file(const char *path, char *buffer, size_t size,
                          size_t *length)
{
    struct stat info;
    ssize_t got;
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return false;
    if (fstat(fd, &info) != 0 || !S_ISREG(info.st_mode) ||
        info.st_size < 0 || (size_t)info.st_size >= size) {
        close(fd);
        return false;
    }
    got = read(fd, buffer, (size_t)info.st_size);
    close(fd);
    if (got < 0 || (size_t)got != (size_t)info.st_size) return false;
    buffer[got] = '\0';
    *length = (size_t)got;
    return true;
}

static bool write_run_file(const char *path, const char *data,
                           size_t length)
{
    char temp[PATH_MAX];
    int fd;
    ssize_t put;
    if (!format_two(temp, sizeof temp, "%s.tmp", path, NULL)) return false;
    fd = open(temp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC | O_NOFOLLOW,
              0600);
    if (fd < 0) return false;
    put = write(fd, data, length);
    if (put < 0 || (size_t)put != length || close(fd) != 0) {
        if (put >= 0 && (size_t)put != length) close(fd);
        unlink(temp);
        return false;
    }
    if (rename(temp, path) != 0) {
        unlink(temp);
        return false;
    }
    return true;
}

bool laptop_run_directory(char *path, size_t size)
{
    char profiles[PATH_MAX];
    if (!laptop_directory(profiles, sizeof profiles)) return false;
    return format_two(path, size, "%s/run", profiles, NULL);
}

static bool run_pid_path(const char *id, char *path, size_t size)
{
    char directory[PATH_MAX];
    if (!valid_run_id(id) ||
        !laptop_run_directory(directory, sizeof directory))
        return false;
    return format_two(path, size, "%s/%s.pid", directory, id);
}

/* The contract's liveness check: kill(pid, 0), EPERM counts as alive, a
 * /proc zombie does not — its window is already gone, and only an
 * unreaped parent keeps the pid answering. */
static bool run_pid_alive(long pid)
{
    char stat_path[64];
    char stat_text[512];
    size_t stat_length = 0;
    if (pid <= 1) return false;
    if (kill((pid_t)pid, 0) != 0 && errno != EPERM) return false;
    if (snprintf(stat_path, sizeof stat_path, "/proc/%ld/stat", pid) > 0 &&
        read_run_file(stat_path, stat_text, sizeof stat_text,
                      &stat_length)) {
        const char *closing = strrchr(stat_text, ')');
        if (closing != NULL && closing[1] == ' ' && closing[2] == 'Z')
            return false;
    }
    return true;
}

bool laptop_run_record(const char *id, long pid)
{
    char path[PATH_MAX];
    char directory[PATH_MAX];
    char text[32];
    int written;
    if (pid <= 1 || !run_pid_path(id, path, sizeof path)) return false;
    if (!laptop_run_directory(directory, sizeof directory) ||
        !ensure_run_directory(directory))
        return false;
    written = snprintf(text, sizeof text, "%ld\n", pid);
    if (written <= 0 || (size_t)written >= sizeof text) return false;
    return write_run_file(path, text, (size_t)written);
}

int laptop_run_status(const char *id, long *pid)
{
    char path[PATH_MAX];
    char text[64];
    size_t length = 0;
    char *end = NULL;
    long value;
    if (pid != NULL) *pid = 0;
    reap_run_children();
    if (!run_pid_path(id, path, sizeof path)) return -1;
    if (!read_run_file(path, text, sizeof text, &length)) return 0;
    value = strtol(text, &end, 10);
    if (end != NULL && end != text && (*end == '\n' || *end == '\0') &&
        run_pid_alive(value)) {
        if (pid != NULL) *pid = value;
        return 1;
    }
    /* Stale: whichever reader notices cleans up. */
    (void)unlink(path);
    return 0;
}

bool laptop_run_any(void)
{
    char directory[PATH_MAX];
    DIR *entries;
    struct dirent *entry;
    bool any = false;
    if (!laptop_run_directory(directory, sizeof directory)) return false;
    entries = opendir(directory);
    if (entries == NULL) return false; /* never used = never created */
    while (!any && (entry = readdir(entries)) != NULL) {
        char id[LAPTOP_ID_MAX];
        const char *dot = strrchr(entry->d_name, '.');
        if (dot == NULL || strcmp(dot, ".pid") != 0) continue;
        if ((size_t)(dot - entry->d_name) >= sizeof id) continue;
        memcpy(id, entry->d_name, (size_t)(dot - entry->d_name));
        id[dot - entry->d_name] = '\0';
        if (!valid_run_id(id)) continue;
        any = laptop_run_status(id, NULL) == 1;
    }
    closedir(entries);
    return any;
}

/* ---- spawning ---- */

/* The same gate every app launch obeys (launcher.c's in_kilix_session):
 * a laptop session opens Kilix windows, so Kilix must be around us. */
static bool run_in_kilix_session(void)
{
    const char *home = getenv("KILIX_HOME");
    const char *socket = getenv("KITTY_LISTEN_ON");
    const char *password = getenv("KILIX_RC_PASSWORD_FILE");
    return home != NULL && home[0] != '\0' && socket != NULL &&
           socket[0] != '\0' && password != NULL && password[0] != '\0';
}

/* The kilix launcher: $KILIX_HOME/kilix when it is executable, else the
 * bare word for posix_spawnp's PATH search. */
static const char *resolve_kilix_word(char *path, size_t size)
{
    const char *home = getenv("KILIX_HOME");
    if (home != NULL && home[0] != '\0' &&
        format_two(path, size, "%s/kilix", home, NULL) &&
        access(path, X_OK) == 0)
        return path;
    return "kilix";
}

/* Fixed argv, stdio on /dev/null. Returns the child pid, or -1. */
static pid_t spawn_run_argv(const char *const argv_words[], size_t count)
{
    char *argv[8];
    posix_spawn_file_actions_t actions;
    pid_t pid = -1;
    int rc;
    size_t i;
    if (count == 0 || count > 7) return -1;
    for (i = 0; i < count; i++) argv[i] = (char *)argv_words[i];
    argv[count] = NULL;
    if (posix_spawn_file_actions_init(&actions) != 0) return -1;
    if (posix_spawn_file_actions_addopen(&actions, STDIN_FILENO,
                                         "/dev/null", O_RDONLY, 0) != 0 ||
        posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO,
                                         "/dev/null", O_WRONLY, 0) != 0 ||
        posix_spawn_file_actions_addopen(&actions, STDERR_FILENO,
                                         "/dev/null", O_WRONLY, 0) != 0) {
        (void)posix_spawn_file_actions_destroy(&actions);
        return -1;
    }
    rc = posix_spawnp(&pid, argv[0], &actions, NULL, argv, environ);
    (void)posix_spawn_file_actions_destroy(&actions);
    return rc == 0 ? pid : -1;
}

/* Whether this host's kilix knows the `laptop` verb, probed once per
 * process the way the games handoff probes `kilix games play`: run
 * `kilix laptop help`, bounded to two seconds, and require the usage
 * token — never the exit code alone, because an old launcher forwards
 * unknown words to the terminal engine. */
static bool laptop_host_verb_available(const char *kilix)
{
    static int cached = -1;
    int pipe_fds[2];
    posix_spawn_file_actions_t actions;
    char *argv[4];
    pid_t pid = -1;
    char output[256];
    size_t output_length = 0;
    int status = 0;
    bool exited = false;

    if (cached >= 0) return cached == 1;
    cached = 0;
    if (kilix == NULL || pipe(pipe_fds) != 0) return false;
    argv[0] = (char *)kilix;
    argv[1] = (char *)"laptop";
    argv[2] = (char *)"help";
    argv[3] = NULL;
    if (posix_spawn_file_actions_init(&actions) != 0) {
        close(pipe_fds[0]);
        close(pipe_fds[1]);
        return false;
    }
    if (posix_spawn_file_actions_addopen(&actions, STDIN_FILENO,
                                         "/dev/null", O_RDONLY, 0) != 0 ||
        posix_spawn_file_actions_adddup2(&actions, pipe_fds[1],
                                         STDOUT_FILENO) != 0 ||
        posix_spawn_file_actions_addopen(&actions, STDERR_FILENO,
                                         "/dev/null", O_WRONLY, 0) != 0 ||
        posix_spawn_file_actions_addclose(&actions, pipe_fds[0]) != 0 ||
        posix_spawnp(&pid, kilix, &actions, NULL, argv, environ) != 0) {
        (void)posix_spawn_file_actions_destroy(&actions);
        close(pipe_fds[0]);
        close(pipe_fds[1]);
        return false;
    }
    (void)posix_spawn_file_actions_destroy(&actions);
    close(pipe_fds[1]);
    (void)fcntl(pipe_fds[0], F_SETFL, O_NONBLOCK);
    for (int waited = 0; waited < 200; waited++) {
        ssize_t got = read(pipe_fds[0], output + output_length,
                           sizeof output - 1u - output_length);
        if (got > 0 && output_length < sizeof output - 1u)
            output_length += (size_t)got;
        if (!exited) {
            pid_t reaped = waitpid(pid, &status, WNOHANG);
            if (reaped == pid) exited = true;
            else if (reaped < 0) break;
        }
        if (exited && (got == 0 || output_length >= sizeof output - 1u))
            break;
        if (!exited || got < 0) {
            struct timespec delay = { 0, 10L * 1000L * 1000L };
            (void)nanosleep(&delay, NULL);
        }
    }
    close(pipe_fds[0]);
    if (!exited) {
        (void)kill(pid, SIGKILL);
        (void)waitpid(pid, &status, 0);
        return false;
    }
    output[output_length] = '\0';
    if (WIFEXITED(status) && WEXITSTATUS(status) == 0 &&
        strstr(output, "open PROFILE") != NULL)
        cached = 1;
    return cached == 1;
}

/* Waits ~250ms on a short-lived helper; a survivor is tracked for later
 * WNOHANG reaping so the frame loop never blocks on it. True when the
 * helper exited 0 or is still doing its job. */
static bool settle_helper(pid_t pid)
{
    for (int waited = 0; waited < 25; waited++) {
        int status = 0;
        pid_t reaped = waitpid(pid, &status, WNOHANG);
        if (reaped == pid)
            return WIFEXITED(status) && WEXITSTATUS(status) == 0;
        if (reaped < 0) return true;
        {
            struct timespec delay = { 0, 10L * 1000L * 1000L };
            (void)nanosleep(&delay, NULL);
        }
    }
    track_run_child(pid);
    return true;
}

/* The fallback session home mirrors launcher.c's private config
 * directory: ~/.local/gpu_terminal/kilix-cap (KILIX_CAP_CONFIG_HOME
 * overrides), each missing level created 0700. */
static bool fallback_session_path(const char *id, char *path, size_t size)
{
    const char *override = getenv("KILIX_CAP_CONFIG_HOME");
    const char *home = getenv("HOME");
    char directory[PATH_MAX];
    int written;
    if (override != NULL && override[0] == '/')
        written = snprintf(directory, sizeof directory, "%s", override);
    else if (home != NULL && home[0] == '/')
        written = snprintf(directory, sizeof directory,
                           "%s/.local/gpu_terminal/kilix-cap", home);
    else
        return false;
    if (written < 0 || (size_t)written >= sizeof directory ||
        strcmp(directory, "/") == 0 || !ensure_run_directory(directory))
        return false;
    written = snprintf(path, size, "%s/laptop-%s.session", directory, id);
    return written > 0 && (size_t)written < size;
}

bool laptop_run_open(const char *profile_id, char *error,
                     size_t error_size)
{
    char kilix_path[PATH_MAX];
    const char *kilix;
    LaptopProfile profile;
    char load_error[LAPTOP_ERROR_MAX];

    set_error(error, error_size, "");
    if (!run_in_kilix_session()) {
        set_error(error, error_size,
                  "Run Kilix Cap inside Kilix to open the laptop.");
        return false;
    }
    if (!laptop_load(profile_id, &profile, load_error,
                     sizeof load_error)) {
        set_error(error, error_size, load_error);
        return false;
    }
    if (profile.desktop[0] == '\0' &&
        laptop_run_status(profile.id, NULL) == 1) {
        set_error(error, error_size,
                  "That session is already running.");
        return false;
    }
    kilix = resolve_kilix_word(kilix_path, sizeof kilix_path);
    if (laptop_host_verb_available(kilix)) {
        const char *argv_words[4];
        pid_t helper;
        argv_words[0] = kilix;
        argv_words[1] = "laptop";
        argv_words[2] = "open";
        argv_words[3] = profile.id;
        helper = spawn_run_argv(argv_words, 4);
        if (helper < 0 || !settle_helper(helper)) {
            set_error(error, error_size,
                      "The laptop profile could not open.");
            return false;
        }
        return true;
    }
    if (profile.desktop[0] != '\0') {
        const char *desktop_arguments[2] = {NULL, NULL};
        const char *argv_words[3];
        size_t count =
            laptop_desktop_arguments(&profile, desktop_arguments);
        pid_t helper;
        argv_words[0] = kilix;
        argv_words[1] = desktop_arguments[0];
        argv_words[2] = count > 1 ? desktop_arguments[1] : NULL;
        helper = spawn_run_argv(argv_words, 1 + count);
        if (helper < 0 || !settle_helper(helper)) {
            set_error(error, error_size,
                      "The laptop profile could not open.");
            return false;
        }
        return true;
    }
    {
        char session_path[PATH_MAX];
        char write_error[LAPTOP_ERROR_MAX];
        const char *argv_words[3];
        pid_t session;
        if (!fallback_session_path(profile.id, session_path,
                                   sizeof session_path)) {
            set_error(error, error_size,
                      "The laptop session file has no home.");
            return false;
        }
        if (!laptop_write_session(&profile, session_path, write_error,
                                  sizeof write_error)) {
            set_error(error, error_size, write_error);
            return false;
        }
        /* Un-detached on purpose: the child pid is the session window
         * itself, so the registry records the truth. */
        argv_words[0] = kilix;
        argv_words[1] = "--session";
        argv_words[2] = session_path;
        session = spawn_run_argv(argv_words, 3);
        if (session < 0) {
            set_error(error, error_size,
                      "The laptop profile could not open.");
            return false;
        }
        /* A quick exit — even a clean one — means the window never came
         * up. */
        for (int waited = 0; waited < 20; waited++) {
            int status = 0;
            pid_t reaped = waitpid(session, &status, WNOHANG);
            if (reaped == session) {
                set_error(error, error_size,
                          "The laptop session ended immediately.");
                return false;
            }
            if (reaped < 0) break;
            {
                struct timespec delay = { 0, 10L * 1000L * 1000L };
                (void)nanosleep(&delay, NULL);
            }
        }
        track_run_child(session);
        (void)laptop_run_record(profile.id, (long)session);
        return true;
    }
}

bool laptop_run_close(const char *profile_id, char *error,
                      size_t error_size)
{
    char kilix_path[PATH_MAX];
    const char *kilix;
    long pid = 0;
    int status;

    set_error(error, error_size, "");
    if (!valid_run_id(profile_id)) {
        set_error(error, error_size, "That profile name is not valid.");
        return false;
    }
    kilix = resolve_kilix_word(kilix_path, sizeof kilix_path);
    if (run_in_kilix_session() && laptop_host_verb_available(kilix)) {
        const char *argv_words[4];
        pid_t helper;
        argv_words[0] = kilix;
        argv_words[1] = "laptop";
        argv_words[2] = "close";
        argv_words[3] = profile_id;
        helper = spawn_run_argv(argv_words, 4);
        if (helper >= 0 && settle_helper(helper)) return true;
        /* fall through to the direct signal */
    }
    status = laptop_run_status(profile_id, &pid);
    if (status < 0) {
        set_error(error, error_size, "No laptop profile directory.");
        return false;
    }
    if (status == 0) return true; /* already gone counts as closed */
    if (kill((pid_t)pid, SIGTERM) != 0 && errno != ESRCH) {
        set_error(error, error_size, "That session cannot be signaled.");
        return false;
    }
    return true;
}

/* ---- selftest ---- */

static bool run_expect(bool condition, const char *label)
{
    if (!condition)
        fprintf(stderr, "laptop-run selftest: FAIL %s\n", label);
    return condition;
}

/* Save-and-clear one environment variable, so the selftest never
 * depends on (or reaches) the Kilix session it happens to run inside. */
typedef struct SavedVariable {
    const char *name;
    char value[PATH_MAX];
    bool present;
} SavedVariable;

static void save_and_clear(SavedVariable *saved, const char *name)
{
    const char *current = getenv(name);
    saved->name = name;
    saved->present = current != NULL;
    saved->value[0] = '\0';
    if (current != NULL)
        (void)snprintf(saved->value, sizeof saved->value, "%s", current);
    unsetenv(name);
}

static void restore_variable(const SavedVariable *saved)
{
    if (saved->present)
        (void)setenv(saved->name, saved->value, 1);
    else
        unsetenv(saved->name);
}

bool laptop_run_selftest(void)
{
    char root[] = "/tmp/kilix-cap-laptop-run.XXXXXX";
    char run_dir[PATH_MAX];
    char stale[PATH_MAX];
    long pid = 0;
    bool ok = true;
    SavedVariable session_variables[3];

    if (mkdtemp(root) == NULL) return false;
    if (setenv("KILIX_LAPTOP_PROFILES", root, 1) != 0) return false;
    /* Outside any Kilix session on purpose: the close path must take
     * the direct-signal branch, not shell out to a host that may or may
     * not exist on the test machine. */
    save_and_clear(&session_variables[0], "KILIX_HOME");
    save_and_clear(&session_variables[1], "KITTY_LISTEN_ON");
    save_and_clear(&session_variables[2], "KILIX_RC_PASSWORD_FILE");

    ok &= run_expect(!laptop_run_any(),
                     "an unused registry reports nothing running");
    ok &= run_expect(laptop_run_status("bench", NULL) == 0,
                     "an unrecorded profile is not running");
    ok &= run_expect(laptop_run_record("bench", (long)getpid()) &&
                         laptop_run_status("bench", &pid) == 1 &&
                         pid == (long)getpid(),
                     "a recorded live session reads back");
    ok &= run_expect(laptop_run_any(),
                     "a live session turns the laptop on");
    ok &= run_expect(laptop_run_directory(run_dir, sizeof run_dir) &&
                         snprintf(stale, sizeof stale, "%s/junk.pid",
                                  run_dir) > 0 &&
                         write_run_file(stale, "not-a-pid\n", 10) &&
                         laptop_run_status("junk", NULL) == 0 &&
                         access(stale, F_OK) != 0,
                     "a garbled pid file is cleaned up on read");
    ok &= run_expect(write_run_file(stale, "1\n", 2) &&
                         laptop_run_status("junk", NULL) == 0 &&
                         access(stale, F_OK) != 0,
                     "pid 1 and below never count as a session");
    ok &= run_expect(laptop_run_status("../escape", NULL) == -1,
                     "registry ids follow the profile id rules");

    /* close: the SIGTERM reaches the recorded pid — held to SIG_IGN
     * here so the selftest survives its own medicine — and the entry
     * stays until the process is really gone; a stopped profile closes
     * calmly. */
    {
        struct sigaction ignore_term;
        struct sigaction previous_term;
        char bench[PATH_MAX];
        memset(&ignore_term, 0, sizeof ignore_term);
        ignore_term.sa_handler = SIG_IGN;
        ok &= run_expect(sigaction(SIGTERM, &ignore_term,
                                   &previous_term) == 0,
                         "SIGTERM can be held for the close check");
        ok &= run_expect(laptop_run_close("bench", NULL, 0),
                         "close signals the recorded session");
        (void)sigaction(SIGTERM, &previous_term, NULL);
        ok &= run_expect(laptop_run_status("bench", NULL) == 1,
                         "a surviving session stays registered");
        if (format_two(bench, sizeof bench, "%s/bench.pid", run_dir,
                       NULL))
            (void)unlink(bench);
        ok &= run_expect(laptop_run_close("bench", NULL, 0),
                         "closing a stopped session counts as closed");
    }

    restore_variable(&session_variables[0]);
    restore_variable(&session_variables[1]);
    restore_variable(&session_variables[2]);
    (void)rmdir(run_dir);
    unsetenv("KILIX_LAPTOP_PROFILES");
    (void)rmdir(root);
    return ok;
}
