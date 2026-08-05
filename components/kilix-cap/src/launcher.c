/* launcher.c — fixed desktop-app plans with no shell interpretation. */
#define _GNU_SOURCE
#include "launcher.h"

#include "laptop.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

extern char **environ;

enum {
    CHILD_MAX = 16,
    ARG_MAX_LOCAL = 28,
    PLAN_ARGUMENT_MAX = 26,
    MAIL_TARGET_MAX = 255,
    WEB_HOME_MAX = 2047,
    CONFIG_FILE_MAX = 4096,
    WEB_LOG_MAX = 16384,
    HANDLER_PROBE_ATTEMPTS = 100,
    HANDLER_PROBE_PAUSE_NS = 10000000
};

typedef struct LaunchPlan {
    char executable[PATH_MAX];
    char cwd[PATH_MAX];
    char argument[PLAN_ARGUMENT_MAX][PATH_MAX];
    char *argv[ARG_MAX_LOCAL];
    const char *program;
} LaunchPlan;

typedef enum WebReadyReason {
    WEB_READY_REASON_NONE = 0,
    WEB_READY_REASON_CHANGED,
    WEB_READY_REASON_INITIAL_GRACE,
    WEB_READY_REASON_LEGACY_CHANGED
} WebReadyReason;

static pid_t children[CHILD_MAX];
static int child_count;
static bool enabled;
static char working_directory[PATH_MAX];
static char config_directory[PATH_MAX];
static char mail_target[MAIL_TARGET_MAX + 1];
static char web_home[WEB_HOME_MAX + 1];
static char web_window_id[32];
static char web_ready_path[PATH_MAX];
static double web_started_at;
static double web_ready_at;
static bool web_ready_seen;
static char last_program[64];
static char last_error[128];

static const char default_web_home[] = "https://news.ycombinator.com/";
static const double web_ready_settle_seconds = 0.75;
static const double web_launch_timeout_seconds = 30.0;

static const char *const app_titles[LAUNCH_APP_COUNT] = {
    "Clock", "Inbox", "Outbox", "Mail", "Profile", "Notepad", "Dates",
    "Contacts", "Files", "Phone", "Writer", "Calculator", "Web"
};

static const char *const tool_titles[LAUNCH_TOOL_COUNT] = {
    "Logs / Alerts / System Mail",
    "Processes / Network",
    "System Settings",
    "Storage Administration",
    "Software Administration",
    "Network Settings",
    "Temporary-file Cleaning",
    "Trash Cleaning",
    "Cache Cleaning",
    "Package-cache Cleaning",
    "Housekeeping",
    "First Steps",
    "Rooms",
    "Interactions",
    "Applications",
    "Engine",
    "Weather",
    "Stargazing"
};

static bool false_value(const char *value)
{
    return value != NULL &&
           (strcmp(value, "0") == 0 || strcasecmp(value, "off") == 0 ||
            strcasecmp(value, "false") == 0 || strcasecmp(value, "no") == 0);
}

static void set_error(const char *message)
{
    (void)snprintf(last_error, sizeof last_error, "%s",
                   message != NULL ? message : "launch failed");
}

static bool executable_file(const char *path)
{
    struct stat st;
    return path != NULL && stat(path, &st) == 0 && S_ISREG(st.st_mode) &&
           access(path, X_OK) == 0;
}

static bool accessible_directory(const char *path)
{
    struct stat st;
    return path != NULL && path[0] == '/' && stat(path, &st) == 0 &&
           S_ISDIR(st.st_mode) && access(path, X_OK) == 0;
}

static bool resolve_program(const char *name, char *path, size_t size)
{
    const char *search;
    const char *cursor;
    if (name == NULL || name[0] == '\0' || path == NULL || size == 0)
        return false;
    if (strchr(name, '/') != NULL) {
        if (!executable_file(name)) return false;
        return snprintf(path, size, "%s", name) >= 0 && strlen(name) < size;
    }
    search = getenv("PATH");
    if (search == NULL || search[0] == '\0') search = "/usr/local/bin:/usr/bin:/bin";
    cursor = search;
    while (*cursor != '\0') {
        const char *end = strchr(cursor, ':');
        size_t length = end != NULL ? (size_t)(end - cursor) : strlen(cursor);
        int written;
        if (length > 0 && length < PATH_MAX - 2u) {
            written = snprintf(path, size, "%.*s/%s", (int)length, cursor,
                               name);
            if (written >= 0 && (size_t)written < size &&
                executable_file(path))
                return true;
        }
        if (end == NULL) break;
        cursor = end + 1;
    }
    path[0] = '\0';
    return false;
}

static bool join_path(char *dst, size_t size, const char *left,
                      const char *right)
{
    size_t length;
    int written;
    if (dst == NULL || left == NULL || right == NULL) return false;
    length = strlen(left);
    written = snprintf(dst, size, "%s%s%s", left,
                       length > 0 && left[length - 1] == '/' ? "" : "/",
                       right);
    return written >= 0 && (size_t)written < size;
}

static bool regular_readable_file(const char *path);

static double monotonic_seconds(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return 0.0;
    return (double)now.tv_sec + (double)now.tv_nsec / 1000000000.0;
}

static bool project_paths(char *root, size_t root_size,
                          char *helper, size_t helper_size)
{
    char executable[PATH_MAX];
    char *slash;
    ssize_t length;

    if (root == NULL || root_size == 0 || helper == NULL || helper_size == 0)
        return false;
    root[0] = '\0';
    helper[0] = '\0';
#if defined(__linux__)
    length = readlink("/proc/self/exe", executable, sizeof executable - 1u);
    if (length <= 0 || (size_t)length >= sizeof executable) return false;
    executable[length] = '\0';
#else
    (void)length;
    return false;
#endif
    slash = strrchr(executable, '/');
    if (slash == NULL) return false;
    *slash = '\0'; /* executable directory, normally bin/ */
    slash = strrchr(executable, '/');
    if (slash == NULL || slash == executable) return false;
    *slash = '\0';
    if (!accessible_directory(executable) ||
        snprintf(root, root_size, "%s", executable) < 0 ||
        strlen(executable) >= root_size ||
        !join_path(helper, helper_size, executable, "tools/mansion_tui.py") ||
        !regular_readable_file(helper)) {
        root[0] = '\0';
        helper[0] = '\0';
        return false;
    }
    return true;
}

static bool set_documents_cwd(LaunchPlan *plan, const char *home)
{
    return plan != NULL && home != NULL && home[0] == '/' &&
           join_path(plan->cwd, sizeof plan->cwd, home, "Documents");
}

static bool regular_readable_file(const char *path)
{
    struct stat st;
    return path != NULL && path[0] == '/' && stat(path, &st) == 0 &&
           S_ISREG(st.st_mode) && access(path, R_OK) == 0;
}

static bool valid_game_id(const char *game_id)
{
    size_t length;
    if (game_id == NULL || game_id[0] == '\0' || game_id[0] == '-')
        return false;
    length = strlen(game_id);
    if (length > GAME_ID_MAX) return false;
    for (size_t i = 0; i < length; i++) {
        unsigned char ch = (unsigned char)game_id[i];
        if (!((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') ||
              ch == '-'))
            return false;
    }
    return true;
}

static bool mail_target_is_url(const char *target)
{
    return target != NULL &&
           (strncmp(target, "https://", 8) == 0 ||
            strncmp(target, "http://", 7) == 0);
}

static bool valid_http_url(const char *target, size_t maximum)
{
    const char *host;
    size_t length;
    if (!mail_target_is_url(target)) return false;
    length = strlen(target);
    if (length == 0 || length > maximum) return false;
    for (size_t i = 0; i < length; i++) {
        unsigned char ch = (unsigned char)target[i];
        if (ch < 33u || ch > 126u) return false;
    }
    host = strstr(target, "://") + 3;
    return host[0] != '\0' && host[0] != '/';
}

static bool valid_mail_target(const char *target)
{
    size_t length;
    if (target == NULL || target[0] == '\0') return false;
    length = strlen(target);
    if (length > MAIL_TARGET_MAX) return false;
    if (mail_target_is_url(target))
        return valid_http_url(target, MAIL_TARGET_MAX);
    if (target[0] == '-' ||
        (strchr(target, '/') != NULL && target[0] != '/'))
        return false;
    for (size_t i = 0; i < length; i++) {
        unsigned char ch = (unsigned char)target[i];
        if (!isalnum(ch) && ch != '_' && ch != '+' && ch != '-' &&
            ch != '.' && ch != '/')
            return false;
    }
    return true;
}

static void init_config_directory(void)
{
    const char *override = getenv("KILIX_CAP_CONFIG_HOME");
    const char *home = getenv("HOME");
    int written;

    config_directory[0] = '\0';
    if (override != NULL && override[0] != '\0') {
        if (override[0] != '/') return;
        written = snprintf(config_directory, sizeof config_directory, "%s",
                           override);
    } else {
        if (home == NULL || home[0] != '/') return;
        written = snprintf(config_directory, sizeof config_directory,
                           "%s/.local/gpu_terminal/kilix-cap", home);
    }
    if (written < 0 || (size_t)written >= sizeof config_directory ||
        strcmp(config_directory, "/") == 0)
        config_directory[0] = '\0';
}

static bool ensure_config_directory(void)
{
    char path[PATH_MAX];
    struct stat st;
    size_t length;

    if (config_directory[0] != '/' ||
        snprintf(path, sizeof path, "%s", config_directory) < 0)
        return false;
    length = strlen(path);
    if (length == 0 || length >= sizeof path) return false;
    while (length > 1 && path[length - 1] == '/') path[--length] = '\0';
    for (char *cursor = path + 1;; cursor++) {
        if (*cursor != '/' && *cursor != '\0') continue;
        char saved = *cursor;
        *cursor = '\0';
        if (mkdir(path, 0700) != 0 && errno != EEXIST) {
            *cursor = saved;
            return false;
        }
        *cursor = saved;
        if (saved == '\0') break;
    }
    if (lstat(path, &st) != 0 || !S_ISDIR(st.st_mode) ||
        st.st_uid != getuid())
        return false;
    return true;
}

static int open_config_directory(bool create)
{
    struct stat st;
    int fd;
    if (config_directory[0] == '\0' ||
        (create && !ensure_config_directory()))
        return -1;
    fd = open(config_directory,
              O_RDONLY | O_CLOEXEC | O_DIRECTORY | O_NOFOLLOW);
    if (fd < 0) return -1;
    if (fstat(fd, &st) != 0 || !S_ISDIR(st.st_mode) ||
        st.st_uid != getuid() || (create && fchmod(fd, 0700) != 0)) {
        close(fd);
        return -1;
    }
    return fd;
}

static void clear_web_tracking(bool remove_log)
{
    if (remove_log && web_ready_path[0] == '/')
        (void)unlink(web_ready_path);
    web_window_id[0] = '\0';
    web_ready_path[0] = '\0';
    web_started_at = 0.0;
    web_ready_at = 0.0;
    web_ready_seen = false;
}

static bool prepare_web_ready_log(void)
{
    static unsigned int nonce;
    char name[80];
    int dirfd;
    int fd = -1;

    clear_web_tracking(false);
    name[0] = '\0';
    dirfd = open_config_directory(true);
    if (dirfd < 0) return false;
    for (int attempt = 0; attempt < 32; attempt++) {
        int written = snprintf(name, sizeof name, ".web-ready.%ld.%u.log",
                               (long)getpid(), nonce++);
        if (written < 0 || (size_t)written >= sizeof name) break;
        fd = openat(dirfd, name,
                    O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                    0600);
        if (fd >= 0 || errno != EEXIST) break;
    }
    if (fd < 0) {
        close(dirfd);
        return false;
    }
    if (close(fd) != 0 ||
        !join_path(web_ready_path, sizeof web_ready_path,
                   config_directory, name)) {
        if (name[0] != '\0') (void)unlinkat(dirfd, name, 0);
        web_ready_path[0] = '\0';
        close(dirfd);
        return false;
    }
    close(dirfd);
    return true;
}

static void load_config(void)
{
    char contents[CONFIG_FILE_MAX];
    struct stat st;
    size_t used = 0;
    int dirfd;
    int fd;

    mail_target[0] = '\0';
    (void)snprintf(web_home, sizeof web_home, "%s", default_web_home);
    dirfd = open_config_directory(false);
    if (dirfd < 0) return;
    fd = openat(dirfd, "config", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    close(dirfd);
    if (fd < 0) return;
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) ||
        st.st_uid != getuid() || (st.st_mode & 0022) != 0) {
        close(fd);
        return;
    }
    while (used + 1u < sizeof contents) {
        ssize_t count = read(fd, contents + used,
                             sizeof contents - used - 1u);
        if (count > 0) {
            used += (size_t)count;
            continue;
        }
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) used = 0;
        break;
    }
    close(fd);
    if (used == 0 || used + 1u >= sizeof contents ||
        memchr(contents, '\0', used) != NULL)
        return;
    contents[used] = '\0';
    for (char *line = contents; line != NULL;) {
        char *next = strchr(line, '\n');
        if (next != NULL) *next++ = '\0';
        if (line[0] != '\0' && line[strlen(line) - 1u] == '\r')
            line[strlen(line) - 1u] = '\0';
        if (strncmp(line, "mail_target=", 12) == 0 &&
            valid_mail_target(line + 12))
            (void)snprintf(mail_target, sizeof mail_target, "%s", line + 12);
        else if (strncmp(line, "web_home=", 9) == 0 &&
                 valid_http_url(line + 9, WEB_HOME_MAX))
            (void)snprintf(web_home, sizeof web_home, "%s", line + 9);
        line = next;
    }
}

static bool write_all(int fd, const char *data, size_t length)
{
    size_t written = 0;
    while (written < length) {
        ssize_t count = write(fd, data + written, length - written);
        if (count > 0) {
            written += (size_t)count;
            continue;
        }
        if (count < 0 && errno == EINTR) continue;
        return false;
    }
    return true;
}

static bool persist_mail_target(const char *target)
{
    static unsigned int nonce;
    char contents[MAIL_TARGET_MAX + WEB_HOME_MAX + 96];
    char temporary[80];
    int dirfd;
    int fd = -1;
    int length;
    bool ok = false;

    dirfd = open_config_directory(true);
    if (dirfd < 0) return false;
    length = snprintf(contents, sizeof contents,
                      "# kilix-cap local configuration\n"
                      "mail_target=%s\nweb_home=%s\n",
                      target, valid_http_url(web_home, WEB_HOME_MAX)
                                  ? web_home
                                  : default_web_home);
    if (length < 0 || (size_t)length >= sizeof contents) goto done;
    for (int attempt = 0; attempt < 16; attempt++) {
        int name_length = snprintf(temporary, sizeof temporary,
                                   ".config.tmp.%ld.%u", (long)getpid(),
                                   nonce++);
        if (name_length < 0 || (size_t)name_length >= sizeof temporary)
            goto done;
        fd = openat(dirfd, temporary,
                    O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
                    0600);
        if (fd >= 0 || errno != EEXIST) break;
    }
    if (fd < 0) goto done;
    if (!write_all(fd, contents, (size_t)length) || fchmod(fd, 0600) != 0 ||
        fsync(fd) != 0)
        goto cleanup_file;
    if (close(fd) != 0) {
        fd = -1;
        goto cleanup_file;
    }
    fd = -1;
    if (renameat(dirfd, temporary, dirfd, "config") != 0) goto cleanup_file;
    ok = fsync(dirfd) == 0;
    goto done;

cleanup_file:
    if (fd >= 0) close(fd);
    (void)unlinkat(dirfd, temporary, 0);
done:
    close(dirfd);
    return ok;
}

typedef bool (*ProgramResolver)(const char *, char *, size_t);
typedef bool (*SchemeHandlerProbe)(const char *);
typedef bool (*DesktopHandlerProbe)(char *, size_t);
static bool query_scheme_handler(const char *scheme);
static bool query_text_editor_handler(char *desktop_id, size_t size);
static ProgramResolver program_resolver = resolve_program;
static SchemeHandlerProbe scheme_handler_probe = query_scheme_handler;
static DesktopHandlerProbe text_editor_probe = query_text_editor_handler;
static const char *fixture_only_program;
static bool fixture_tel_handler;
static bool fixture_text_editor_handler;

static bool wait_for_probe(pid_t child, int *status)
{
    struct timespec pause = {0, HANDLER_PROBE_PAUSE_NS};
    for (int i = 0; i < HANDLER_PROBE_ATTEMPTS; i++) {
        pid_t result = waitpid(child, status, WNOHANG);
        if (result == child) return true;
        if (result < 0 && errno != EINTR) return false;
        (void)nanosleep(&pause, NULL);
    }
    (void)kill(child, SIGKILL);
    while (waitpid(child, status, 0) < 0)
        if (errno != EINTR) break;
    return false;
}

/* Querying a URI association must not invoke a shell or let a broken desktop
 * helper stall startup.  Capture one short stdout response and terminate the
 * helper after roughly one second. */
static bool command_capture(const char *executable, char *const argv[],
                            char *output, size_t output_size,
                            bool require_output)
{
    posix_spawn_file_actions_t actions;
    posix_spawnattr_t attributes;
    sigset_t empty;
    sigset_t defaults;
    size_t used = 0;
    int pipefd[2];
    int status = 0;
    int rc;
    pid_t child;
    bool completed;

    if (output == NULL || output_size < 2u) return false;
    output[0] = '\0';
    if (pipe(pipefd) != 0) return false;
    if (fcntl(pipefd[0], F_SETFD, FD_CLOEXEC) != 0 ||
        fcntl(pipefd[1], F_SETFD, FD_CLOEXEC) != 0) {
        close(pipefd[0]);
        close(pipefd[1]);
        return false;
    }
    rc = posix_spawn_file_actions_init(&actions);
    if (rc != 0) {
        close(pipefd[0]);
        close(pipefd[1]);
        return false;
    }
    rc = posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null",
                                          O_RDONLY, 0);
    if (rc == 0)
        rc = posix_spawn_file_actions_adddup2(&actions, pipefd[1],
                                              STDOUT_FILENO);
    if (rc == 0)
        rc = posix_spawn_file_actions_addopen(&actions, STDERR_FILENO,
                                              "/dev/null", O_WRONLY, 0);
    if (rc == 0) rc = posix_spawn_file_actions_addclose(&actions, pipefd[0]);
    if (rc == 0) rc = posix_spawn_file_actions_addclose(&actions, pipefd[1]);
    if (rc != 0) {
        posix_spawn_file_actions_destroy(&actions);
        close(pipefd[0]);
        close(pipefd[1]);
        return false;
    }
    rc = posix_spawnattr_init(&attributes);
    if (rc != 0) {
        posix_spawn_file_actions_destroy(&actions);
        close(pipefd[0]);
        close(pipefd[1]);
        return false;
    }
    sigemptyset(&empty);
    sigemptyset(&defaults);
    sigaddset(&defaults, SIGINT);
    sigaddset(&defaults, SIGTERM);
    sigaddset(&defaults, SIGHUP);
    sigaddset(&defaults, SIGQUIT);
    sigaddset(&defaults, SIGPIPE);
    rc = posix_spawnattr_setsigmask(&attributes, &empty);
    if (rc == 0) rc = posix_spawnattr_setsigdefault(&attributes, &defaults);
    if (rc == 0)
        rc = posix_spawnattr_setflags(&attributes,
                                      POSIX_SPAWN_SETSIGMASK |
                                      POSIX_SPAWN_SETSIGDEF);
    if (rc == 0)
        rc = posix_spawn(&child, executable, &actions, &attributes, argv,
                         environ);
    posix_spawnattr_destroy(&attributes);
    posix_spawn_file_actions_destroy(&actions);
    close(pipefd[1]);
    if (rc != 0) {
        close(pipefd[0]);
        return false;
    }

    completed = wait_for_probe(child, &status);
    {
        int flags = fcntl(pipefd[0], F_GETFL);
        if (flags >= 0) (void)fcntl(pipefd[0], F_SETFL, flags | O_NONBLOCK);
    }
    while (used + 1u < output_size) {
        ssize_t count = read(pipefd[0], output + used,
                             output_size - used - 1u);
        if (count > 0) {
            used += (size_t)count;
            continue;
        }
        if (count < 0 && errno == EINTR) continue;
        break;
    }
    close(pipefd[0]);
    output[used] = '\0';
    if (!completed || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
        return false;
    {
        size_t first = 0;
        size_t end = used;
        while (first < end && isspace((unsigned char)output[first])) first++;
        while (end > first && isspace((unsigned char)output[end - 1u])) end--;
        if (first == end) {
            output[0] = '\0';
            return !require_output;
        }
        memmove(output, output + first, end - first);
        output[end - first] = '\0';
    }
    return true;
}

static bool command_output(const char *executable, char *const argv[],
                           char *output, size_t output_size)
{
    return command_capture(executable, argv, output, output_size, true);
}

static bool command_without_output(const char *executable, char *const argv[])
{
    char output[2];
    return command_capture(executable, argv, output, sizeof output, false);
}

static bool query_scheme_handler(const char *scheme)
{
    char executable[PATH_MAX];
    char mime_type[64];
    char output[256];
    char *argv[5];
    int written;

    if (scheme == NULL || scheme[0] == '\0' ||
        !resolve_program("xdg-mime", executable, sizeof executable))
        return false;
    written = snprintf(mime_type, sizeof mime_type, "x-scheme-handler/%s",
                       scheme);
    if (written < 0 || (size_t)written >= sizeof mime_type) return false;
    argv[0] = executable;
    argv[1] = "query";
    argv[2] = "default";
    argv[3] = mime_type;
    argv[4] = NULL;
    return command_output(executable, argv, output, sizeof output);
}

static bool valid_desktop_id(const char *desktop_id)
{
    size_t length;
    if (desktop_id == NULL || desktop_id[0] == '\0' ||
        desktop_id[0] == '-' || desktop_id[0] == '.')
        return false;
    length = strlen(desktop_id);
    if (length < 9u || length > 200u ||
        strcmp(desktop_id + length - 8u, ".desktop") != 0)
        return false;
    for (size_t i = 0; i < length; i++) {
        unsigned char ch = (unsigned char)desktop_id[i];
        if (!isalnum(ch) && ch != '.' && ch != '_' && ch != '+' && ch != '-')
            return false;
    }
    return true;
}

static bool query_text_editor_handler(char *desktop_id, size_t size)
{
    char executable[PATH_MAX];
    char output[256];
    char *argv[5];
    int written;
    if (desktop_id == NULL || size == 0 ||
        !resolve_program("xdg-mime", executable, sizeof executable))
        return false;
    argv[0] = executable;
    argv[1] = "query";
    argv[2] = "default";
    argv[3] = "text/plain";
    argv[4] = NULL;
    if (!command_output(executable, argv, output, sizeof output) ||
        !valid_desktop_id(output))
        return false;
    written = snprintf(desktop_id, size, "%s", output);
    return written >= 0 && (size_t)written < size;
}

static bool fixture_scheme_handler(const char *scheme)
{
    return fixture_tel_handler && scheme != NULL &&
           strcmp(scheme, "tel") == 0;
}

static bool fixture_text_editor(char *desktop_id, size_t size)
{
    int written;
    if (!fixture_text_editor_handler || desktop_id == NULL || size == 0)
        return false;
    written = snprintf(desktop_id, size, "fixture-editor.desktop");
    return written >= 0 && (size_t)written < size;
}

static bool fixture_resolver(const char *name, char *path, size_t size)
{
    int written;
    if (fixture_only_program != NULL && strcmp(name, fixture_only_program) != 0)
        return false;
    written = snprintf(path, size, "/fixture/%s", name);
    return written >= 0 && (size_t)written < size;
}

static bool choose_program(LaunchPlan *plan, const char *const *names,
                           size_t count)
{
    for (size_t i = 0; i < count; i++) {
        if (program_resolver(names[i], plan->executable,
                             sizeof plan->executable)) {
            plan->program = names[i];
            return true;
        }
    }
    return false;
}

static void finish_plan_three(LaunchPlan *plan, const char *first,
                              const char *second, const char *third)
{
    const char *const values[] = {first, second, third};
    int argc = 0;
    plan->argv[argc++] = plan->executable;
    for (size_t i = 0; i < sizeof values / sizeof values[0]; i++) {
        if (values[i] == NULL) continue;
        (void)snprintf(plan->argument[argc - 1],
                       sizeof plan->argument[argc - 1], "%s", values[i]);
        plan->argv[argc] = plan->argument[argc - 1];
        argc++;
    }
    plan->argv[argc] = NULL;
}

static bool finish_plan_many(LaunchPlan *plan, const char *const *values,
                             size_t count)
{
    int argc = 0;
    if (plan == NULL || values == NULL || count > PLAN_ARGUMENT_MAX)
        return false;
    plan->argv[argc++] = plan->executable;
    for (size_t i = 0; i < count; i++) {
        int written;
        if (values[i] == NULL || values[i][0] == '\0') return false;
        written = snprintf(plan->argument[argc - 1],
                           sizeof plan->argument[argc - 1], "%s", values[i]);
        if (written < 0 || (size_t)written >= sizeof plan->argument[0])
            return false;
        plan->argv[argc] = plan->argument[argc - 1];
        argc++;
    }
    plan->argv[argc] = NULL;
    return true;
}

static void finish_plan(LaunchPlan *plan, const char *first,
                        const char *second)
{
    finish_plan_three(plan, first, second, NULL);
}

#define COUNT_OF(a) (sizeof(a) / sizeof((a)[0]))

static bool build_plan(LaunchAppId id, LaunchPlan *plan)
{
    static const char *const clocks[] = {"gnome-clocks", "kclock"};
    static const char *const mailers[] = {"thunderbird", "evolution", "kmail"};
    static const char *const contacts[] = {"gnome-contacts", "kaddressbook"};
    static const char *const preferred_editors[] = {"mousepad"};
    static const char *const desktop_launchers[] = {"gtk-launch"};
    static const char *const fallback_editors[] = {
        "xed", "gedit", "pluma", "leafpad", "featherpad", "kate",
        "kwrite", "notepad.exe"
    };
    static const char *const calendars[] = {"gnome-calendar", "korganizer"};
    static const char *const files[] = {"thunar", "nautilus", "dolphin"};
    static const char *const phones[] = {"gnome-calls"};
    static const char *const writers[] = {"libreoffice", "abiword"};
    static const char *const calculators[] = {
        "gnome-calculator", "kcalc", "qalculate-gtk", "xcalc"
    };
    static const char *const kilix[] = {"kilix"};
    static const char *const opener[] = {"xdg-open"};
    static const char *const email[] = {"xdg-email"};
    const char *home = getenv("HOME");
    char available_path[PATH_MAX];
    char desktop_id[256];

    if (plan == NULL || id < 0 || id >= LAUNCH_APP_COUNT) return false;
    memset(plan, 0, sizeof *plan);
    switch (id) {
    case LAUNCH_CLOCK:
        if (choose_program(plan, clocks, COUNT_OF(clocks))) finish_plan(plan, NULL, NULL);
        else if (choose_program(plan, opener, COUNT_OF(opener)))
            finish_plan(plan, "https://time.is", NULL);
        break;
    case LAUNCH_INBOX:
    case LAUNCH_OUTBOX:
        if (choose_program(plan, mailers, COUNT_OF(mailers))) finish_plan(plan, NULL, NULL);
        else if (choose_program(plan, email, COUNT_OF(email))) finish_plan(plan, NULL, NULL);
        break;
    case LAUNCH_MAIL:
        if (mail_target[0] != '\0' &&
            choose_program(plan, kilix, COUNT_OF(kilix))) {
            if (mail_target_is_url(mail_target) &&
                program_resolver("firefox-esr", available_path,
                                 sizeof available_path)) {
                plan->program = "firefox-esr";
                finish_plan_three(plan, "run", "firefox-esr", mail_target);
            } else if (!mail_target_is_url(mail_target) &&
                       program_resolver(mail_target, available_path,
                                        sizeof available_path)) {
                plan->program = mail_target;
                finish_plan(plan, "run", mail_target);
            }
        } else if (mail_target[0] == '\0' &&
                   choose_program(plan, mailers, COUNT_OF(mailers)))
            finish_plan(plan, NULL, NULL);
        else if (mail_target[0] == '\0' &&
                choose_program(plan, email, COUNT_OF(email)))
            finish_plan(plan, NULL, NULL);
        break;
    case LAUNCH_PROFILE:
        if (choose_program(plan, contacts, COUNT_OF(contacts))) finish_plan(plan, NULL, NULL);
        else if (choose_program(plan, files, COUNT_OF(files)))
            finish_plan(plan, home != NULL ? home : working_directory, NULL);
        break;
    case LAUNCH_NOTES:
        if (!set_documents_cwd(plan, home)) break;
        if (choose_program(plan, preferred_editors,
                           COUNT_OF(preferred_editors)))
            finish_plan(plan, "--disable-server", NULL);
        else if (choose_program(plan, desktop_launchers,
                                COUNT_OF(desktop_launchers)) &&
                 text_editor_probe(desktop_id, sizeof desktop_id)) {
            plan->program = "default text editor";
            finish_plan(plan, desktop_id, NULL);
        } else if (choose_program(plan, fallback_editors,
                                  COUNT_OF(fallback_editors)))
            finish_plan(plan, NULL, NULL);
        else if (choose_program(plan, writers, COUNT_OF(writers)))
            finish_plan(plan, strcmp(plan->program, "libreoffice") == 0 ? "--writer" : NULL,
                        NULL);
        break;
    case LAUNCH_DATES:
        if (choose_program(plan, calendars, COUNT_OF(calendars))) finish_plan(plan, NULL, NULL);
        else if (choose_program(plan, opener, COUNT_OF(opener)))
            finish_plan(plan, "https://calendar.google.com", NULL);
        break;
    case LAUNCH_CARDS:
        if (choose_program(plan, contacts, COUNT_OF(contacts))) finish_plan(plan, NULL, NULL);
        else if (choose_program(plan, email, COUNT_OF(email))) finish_plan(plan, NULL, NULL);
        break;
    case LAUNCH_FILES:
        if (choose_program(plan, files, COUNT_OF(files)))
            finish_plan(plan, working_directory, NULL);
        else if (choose_program(plan, opener, COUNT_OF(opener)))
            finish_plan(plan, working_directory, NULL);
        break;
    case LAUNCH_PHONE:
        if (choose_program(plan, phones, COUNT_OF(phones))) finish_plan(plan, NULL, NULL);
        else if (choose_program(plan, opener, COUNT_OF(opener)) &&
                 scheme_handler_probe("tel"))
            finish_plan(plan, "tel:", NULL);
        break;
    case LAUNCH_PAPER:
        if (choose_program(plan, writers, COUNT_OF(writers)))
            finish_plan(plan, strcmp(plan->program, "libreoffice") == 0 ? "--writer" : NULL,
                        NULL);
        break;
    case LAUNCH_CALCULATOR:
        if (choose_program(plan, calculators, COUNT_OF(calculators)))
            finish_plan(plan, NULL, NULL);
        break;
    case LAUNCH_WEB:
        if (choose_program(plan, kilix, COUNT_OF(kilix)) &&
            program_resolver("firefox-esr", available_path,
                             sizeof available_path)) {
            plan->program = "firefox-esr";
            finish_plan_three(plan, "run", "firefox-esr", web_home);
        }
        break;
    default:
        break;
    }
    return plan->argv[0] != NULL;
}

static bool build_background_web_plan(const char *url, const char *kitten,
                                      const char *password,
                                      const char *kilix,
                                      const char *python,
                                      const char *helper,
                                      const char *firefox,
                                      const char *ready_path,
                                      LaunchPlan *plan)
{
    char ready_environment[PATH_MAX + 32];
    const char *values[] = {
        "@", "--password-file", password, "launch", "--type=tab",
        "--cwd=current", "--self", "--keep-focus", "--tab-title", "Web",
        "--env", "KILIX_IN_OVERLAY=1", "--env", ready_environment,
        "--", kilix, "run", python, helper, firefox, url
    };
    int written;
    if (plan == NULL || !valid_http_url(url, WEB_HOME_MAX) ||
        kitten == NULL || kitten[0] != '/' ||
        password == NULL || password[0] != '/' ||
        kilix == NULL || kilix[0] != '/' ||
        python == NULL || python[0] != '/' ||
        helper == NULL || helper[0] != '/' ||
        firefox == NULL || firefox[0] != '/' ||
        ready_path == NULL || ready_path[0] != '/')
        return false;
    written = snprintf(ready_environment, sizeof ready_environment,
                       "KILIX_RUN_LOG=%s", ready_path);
    if (written < 0 || (size_t)written >= sizeof ready_environment)
        return false;
    memset(plan, 0, sizeof *plan);
    if (snprintf(plan->executable, sizeof plan->executable, "%s", kitten) < 0 ||
        strlen(kitten) >= sizeof plan->executable)
        return false;
    plan->program = "firefox-esr";
    return finish_plan_many(plan, values, COUNT_OF(values));
}

static bool valid_window_id(const char *id)
{
    size_t length;
    if (id == NULL || id[0] == '\0') return false;
    length = strlen(id);
    if (length > 20u) return false;
    for (size_t i = 0; i < length; i++)
        if (!isdigit((unsigned char)id[i])) return false;
    return id[0] != '0';
}

static bool build_focus_web_plan(const char *id, const char *kitten,
                                 const char *password, LaunchPlan *plan)
{
    char match[64];
    const char *values[] = {
        "@", "--password-file", password, "focus-window", "--match", match
    };
    int written;
    if (plan == NULL || !valid_window_id(id) ||
        kitten == NULL || kitten[0] != '/' ||
        password == NULL || password[0] != '/')
        return false;
    written = snprintf(match, sizeof match, "id:%s", id);
    if (written < 0 || (size_t)written >= sizeof match) return false;
    memset(plan, 0, sizeof *plan);
    if (snprintf(plan->executable, sizeof plan->executable, "%s", kitten) < 0 ||
        strlen(kitten) >= sizeof plan->executable)
        return false;
    plan->program = "firefox-esr";
    return finish_plan_many(plan, values, COUNT_OF(values));
}

static bool build_game_plan(const char *game_id, GameLaunchKind kind,
                            const char *root, const char *helper,
                            const char *kitten, const char *password,
                            LaunchPlan *plan)
{
    char python[PATH_MAX];
    char games_py[PATH_MAX];
    if (plan == NULL || !valid_game_id(game_id) || root == NULL ||
        root[0] != '/' || helper == NULL || helper[0] != '/' ||
        kitten == NULL || kitten[0] != '/' || password == NULL ||
        password[0] != '/' ||
        (kind != GAME_LAUNCH_KILIX95 &&
         kind != GAME_LAUNCH_KILIX95_BUILTIN))
        return false;
    memset(plan, 0, sizeof *plan);
    if (snprintf(plan->executable, sizeof plan->executable, "%s", kitten) < 0 ||
        strlen(kitten) >= sizeof plan->executable ||
        !program_resolver("python3", python, sizeof python) ||
        !join_path(games_py, sizeof games_py, root, "games.py") ||
        !regular_readable_file(games_py))
        return false;
    plan->program = game_id;
    if (kind == GAME_LAUNCH_KILIX95) {
        const char *values[16];
        if (!regular_readable_file(helper)) return false;
        values[0] = "@";
        values[1] = "--password-file";
        values[2] = password;
        values[3] = "launch";
        values[4] = "--type=tab";
        values[5] = "--cwd";
        values[6] = root;
        values[7] = "--self";
        values[8] = "--tab-title";
        values[9] = game_id;
        values[10] = "--";
        values[11] = python;
        values[12] = helper;
        values[13] = "launch";
        values[14] = root;
        values[15] = game_id;
        return finish_plan_many(plan, values, COUNT_OF(values));
    }
    if (!regular_readable_file(helper)) return false;
    {
        const char *values[16] = {
            "@", "--password-file", password, "launch", "--type=tab",
            "--cwd", root, "--self", "--tab-title", game_id, "--",
            python, helper, "builtin", root, game_id
        };
        return finish_plan_many(plan, values, COUNT_OF(values));
    }
}

static bool resolve_kilix_control(char *kitten, size_t kitten_size,
                                  char *password, size_t password_size)
{
    const char *override = getenv("KILIX_KITTEN");
    const char *build = getenv("KILIX_BUILD_DIRECTORY");
    const char *prebuilt = getenv("KILIX_PREBUILT_HOME");
    const char *password_env = getenv("KILIX_RC_PASSWORD_FILE");
    bool found = false;
    if (password_env == NULL || password_env[0] != '/' ||
        !regular_readable_file(password_env))
        return false;
    if (override != NULL && override[0] == '/' && executable_file(override))
        found = snprintf(kitten, kitten_size, "%s", override) >= 0 &&
                strlen(override) < kitten_size;
    if (!found && build != NULL && build[0] == '/' &&
        join_path(kitten, kitten_size, build,
                  "current/src/kitty/launcher/kitten") &&
        executable_file(kitten))
        found = true;
    if (!found && prebuilt != NULL && prebuilt[0] == '/' &&
        join_path(kitten, kitten_size, prebuilt, "bin/kitten") &&
        executable_file(kitten))
        found = true;
    if (!found) return false;
    return snprintf(password, password_size, "%s", password_env) >= 0 &&
           strlen(password_env) < password_size;
}

static bool tool_is_terminal(LaunchToolId id)
{
    return id == LAUNCH_TOOL_LOGS || id == LAUNCH_TOOL_ACTIVITY ||
           (id >= LAUNCH_TOOL_CLEAN_TEMP && id <= LAUNCH_TOOL_CLEAN_ALL);
}

static bool tool_is_document(LaunchToolId id)
{
    return id >= LAUNCH_TOOL_DOC_START && id <= LAUNCH_TOOL_DOC_ENGINE;
}

static bool build_terminal_tool_plan(LaunchToolId id, const char *root,
                                     const char *helper,
                                     const char *kitten,
                                     const char *password,
                                     LaunchPlan *plan)
{
    const char *mode = NULL;
    const char *focus = NULL;
    const char *values[15];
    char python[PATH_MAX];
    size_t count = 0;

    if (plan == NULL || root == NULL || helper == NULL || kitten == NULL ||
        password == NULL || !tool_is_terminal(id) ||
        !regular_readable_file(helper) ||
        !program_resolver("python3", python, sizeof python))
        return false;
    if (id == LAUNCH_TOOL_LOGS)
        mode = "logs";
    else if (id == LAUNCH_TOOL_ACTIVITY)
        mode = "activity";
    else {
        mode = "cleanup";
        focus = id == LAUNCH_TOOL_CLEAN_TEMP       ? "temp" :
                id == LAUNCH_TOOL_CLEAN_TRASH      ? "trash" :
                id == LAUNCH_TOOL_CLEAN_CACHE      ? "cache" :
                id == LAUNCH_TOOL_CLEAN_PACKAGES   ? "packages" : "all";
    }

    memset(plan, 0, sizeof *plan);
    if (snprintf(plan->executable, sizeof plan->executable, "%s", kitten) < 0 ||
        strlen(kitten) >= sizeof plan->executable ||
        snprintf(plan->cwd, sizeof plan->cwd, "%s", root) < 0 ||
        strlen(root) >= sizeof plan->cwd)
        return false;
    plan->program = tool_titles[id];
    values[count++] = "@";
    values[count++] = "--password-file";
    values[count++] = password;
    values[count++] = "launch";
    values[count++] = "--type=tab";
    values[count++] = "--cwd";
    values[count++] = root;
    values[count++] = "--self";
    values[count++] = "--tab-title";
    values[count++] = tool_titles[id];
    values[count++] = "--";
    values[count++] = python;
    values[count++] = helper;
    values[count++] = mode;
    if (focus != NULL) values[count++] = focus;
    return finish_plan_many(plan, values, count);
}

/* A Kilix tab running an arbitrary argv.
 *
 * The mansion's established answer to a heavyweight interface is a tab — the
 * two Server Room monitors and every Game Room title already open that way —
 * so reaching a stack tool is new furniture rather than a new mechanism, and
 * cap never grows a second copy of a list some other component owns.
 */
static bool build_kilix_tab_plan(const char *title,
                                 const char *const *arguments,
                                 size_t argument_count, const char *root,
                                 const char *kitten, const char *password,
                                 LaunchPlan *plan)
{
    const char *values[24];
    size_t count = 0;
    size_t index;

    if (plan == NULL || title == NULL || arguments == NULL || root == NULL ||
        kitten == NULL || password == NULL || argument_count == 0 ||
        argument_count > 8)
        return false;
    memset(plan, 0, sizeof *plan);
    if (snprintf(plan->executable, sizeof plan->executable, "%s", kitten) < 0 ||
        strlen(kitten) >= sizeof plan->executable ||
        snprintf(plan->cwd, sizeof plan->cwd, "%s", root) < 0 ||
        strlen(root) >= sizeof plan->cwd)
        return false;
    plan->program = title;
    values[count++] = "@";
    values[count++] = "--password-file";
    values[count++] = password;
    values[count++] = "launch";
    values[count++] = "--type=tab";
    values[count++] = "--cwd";
    values[count++] = root;
    values[count++] = "--self";
    values[count++] = "--tab-title";
    values[count++] = title;
    values[count++] = "--";
    for (index = 0; index < argument_count; index++)
        values[count++] = arguments[index];
    return finish_plan_many(plan, values, count);
}

static bool in_kilix_session(void);

/* Stack tools the Server Room reaches before it falls back to the host's own
 * desktop-environment programs. Inside Kilix these are the right answer: the
 * settings console that edits the file every Kilix component reads, and the
 * updater that moves the whole pinned closure rather than one checkout. On a
 * bare X session with no Kilix around them, neither exists, and the original
 * candidate ladders still apply.
 */
static bool build_stack_tool_plan(LaunchToolId id, LaunchPlan *plan)
{
    static const char *const settings_argv[] = {"kilix", "settings"};
    static const char *const update_argv[] = {"kilix", "update", "--stack"};
    char root[PATH_MAX];
    char helper[PATH_MAX];
    char kitten[PATH_MAX];
    char password[PATH_MAX];
    char kilix[PATH_MAX];

    if (!in_kilix_session() ||
        !program_resolver("kilix", kilix, sizeof kilix) ||
        !project_paths(root, sizeof root, helper, sizeof helper) ||
        !resolve_kilix_control(kitten, sizeof kitten,
                               password, sizeof password))
        return false;
    if (id == LAUNCH_TOOL_SETTINGS)
        return build_kilix_tab_plan("Kilix Settings", settings_argv,
                                    COUNT_OF(settings_argv), root, kitten,
                                    password, plan);
    if (id == LAUNCH_TOOL_SOFTWARE)
        return build_kilix_tab_plan("Update", update_argv,
                                    COUNT_OF(update_argv), root, kitten,
                                    password, plan);
    return false;
}

static bool build_tool_plan(LaunchToolId id, LaunchPlan *plan)
{
    static const char *const settings[] = {
        "xfce4-settings-manager", "gnome-control-center", "systemsettings"
    };
    static const char *const storage[] = {
        "gnome-disks", "partitionmanager", "gparted"
    };
    static const char *const software[] = {
        "synaptic", "gnome-software", "plasma-discover"
    };
    static const char *const network[] = {
        "nm-connection-editor", "systemsettings", "gnome-control-center"
    };
    static const char *const weather[] = {
        "gnome-weather", "kweather", "meteo-qt"
    };
    static const char *const stars[] = {"stellarium", "kstars"};
    static const char *const opener[] = {"xdg-open"};
    static const char *const document_paths[] = {
        "README.md", "docs/INTERACTIONS.md", "docs/INTERACTIONS.md",
        "docs/APPS.md", "docs/ENGINE.md"
    };
    char root[PATH_MAX];
    char helper[PATH_MAX];
    char document[PATH_MAX];
    char kitten[PATH_MAX];
    char password[PATH_MAX];
    const char *const *candidates = NULL;
    size_t candidate_count = 0;

    if (plan == NULL || id < 0 || id >= LAUNCH_TOOL_COUNT ||
        !project_paths(root, sizeof root, helper, sizeof helper))
        return false;
    if (tool_is_terminal(id)) {
        if (!resolve_kilix_control(kitten, sizeof kitten,
                                   password, sizeof password))
            return false;
        return build_terminal_tool_plan(id, root, helper, kitten, password,
                                        plan);
    }
    /* Stack tools win over the host DE's equivalents when there is a Kilix to
     * run them in; otherwise the ladders below are unchanged. */
    if ((id == LAUNCH_TOOL_SETTINGS || id == LAUNCH_TOOL_SOFTWARE) &&
        build_stack_tool_plan(id, plan))
        return true;
    memset(plan, 0, sizeof *plan);
    if (tool_is_document(id)) {
        int document_index = id - LAUNCH_TOOL_DOC_START;
        if (!join_path(document, sizeof document, root,
                       document_paths[document_index]) ||
            !regular_readable_file(document) ||
            !choose_program(plan, opener, COUNT_OF(opener)))
            return false;
        finish_plan(plan, document, NULL);
        return true;
    }
    switch (id) {
    case LAUNCH_TOOL_SETTINGS:
        candidates = settings;
        candidate_count = COUNT_OF(settings);
        break;
    case LAUNCH_TOOL_STORAGE:
        candidates = storage;
        candidate_count = COUNT_OF(storage);
        break;
    case LAUNCH_TOOL_SOFTWARE:
        candidates = software;
        candidate_count = COUNT_OF(software);
        break;
    case LAUNCH_TOOL_NETWORK:
        candidates = network;
        candidate_count = COUNT_OF(network);
        break;
    case LAUNCH_TOOL_WEATHER:
        candidates = weather;
        candidate_count = COUNT_OF(weather);
        break;
    case LAUNCH_TOOL_STARGAZING:
        candidates = stars;
        candidate_count = COUNT_OF(stars);
        break;
    default:
        return false;
    }
    if (!choose_program(plan, candidates, candidate_count)) return false;
    if (id == LAUNCH_TOOL_NETWORK &&
        strcmp(plan->program, "gnome-control-center") == 0)
        finish_plan(plan, "network", NULL);
    else
        finish_plan(plan, NULL, NULL);
    return true;
}

static bool spawn_plan(LaunchPlan *plan)
{
    posix_spawn_file_actions_t actions;
    posix_spawnattr_t attributes;
    sigset_t empty;
    sigset_t defaults;
    pid_t child;
    int rc;

    launcher_poll();
    if (plan->cwd[0] != '\0' && !accessible_directory(plan->cwd)) {
        set_error("the requested launch folder is unavailable");
        return false;
    }
    if (child_count >= CHILD_MAX) {
        set_error("too many launched programs are still starting");
        return false;
    }
    rc = posix_spawn_file_actions_init(&actions);
    if (rc != 0) {
        set_error("cannot prepare desktop launch");
        return false;
    }
    rc = posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null",
                                          O_RDONLY, 0);
    if (rc == 0)
        rc = posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO,
                                              "/dev/null", O_WRONLY, 0);
    if (rc == 0)
        rc = posix_spawn_file_actions_addopen(&actions, STDERR_FILENO,
                                              "/dev/null", O_WRONLY, 0);
    if (rc == 0 && plan->cwd[0] != '\0')
        rc = posix_spawn_file_actions_addchdir_np(&actions, plan->cwd);
    if (rc != 0) {
        posix_spawn_file_actions_destroy(&actions);
        set_error(plan->cwd[0] != '\0'
                      ? "cannot use the requested launch folder"
                      : "cannot isolate desktop program input and output");
        return false;
    }
    rc = posix_spawnattr_init(&attributes);
    if (rc != 0) {
        posix_spawn_file_actions_destroy(&actions);
        set_error("cannot prepare desktop launch");
        return false;
    }
    sigemptyset(&empty);
    sigemptyset(&defaults);
    sigaddset(&defaults, SIGINT);
    sigaddset(&defaults, SIGTERM);
    sigaddset(&defaults, SIGHUP);
    sigaddset(&defaults, SIGQUIT);
    sigaddset(&defaults, SIGPIPE);
    rc = posix_spawnattr_setsigmask(&attributes, &empty);
    if (rc == 0) rc = posix_spawnattr_setsigdefault(&attributes, &defaults);
    if (rc == 0)
        rc = posix_spawnattr_setflags(&attributes,
                                      POSIX_SPAWN_SETSIGMASK |
                                      POSIX_SPAWN_SETSIGDEF);
    if (rc == 0)
        rc = posix_spawn(&child, plan->executable, &actions, &attributes,
                         plan->argv, environ);
    posix_spawnattr_destroy(&attributes);
    posix_spawn_file_actions_destroy(&actions);
    if (rc != 0) {
        set_error("the desktop program could not be started safely");
        return false;
    }
    children[child_count++] = child;
    (void)snprintf(last_program, sizeof last_program, "%s", plan->program);
    last_error[0] = '\0';
    return true;
}

void launcher_init(void)
{
    const char *setting = getenv("KILIX_CAP_EXTERNAL_APPS");
    memset(children, 0, sizeof children);
    child_count = 0;
    last_program[0] = '\0';
    last_error[0] = '\0';
    clear_web_tracking(false);
    init_config_directory();
    load_config();
    if (getcwd(working_directory, sizeof working_directory) == NULL)
        (void)snprintf(working_directory, sizeof working_directory, ".");
    scheme_handler_probe = query_scheme_handler;
    text_editor_probe = query_text_editor_handler;
    enabled = !false_value(setting) && getuid() == geteuid() &&
              getgid() == getegid();
    if (!enabled) set_error("desktop app launching is disabled");
}

void launcher_poll(void)
{
    int write = 0;
    for (int i = 0; i < child_count; i++) {
        pid_t result = waitpid(children[i], NULL, WNOHANG);
        if (result == 0 || (result < 0 && errno == EINTR))
            children[write++] = children[i];
    }
    child_count = write;
}

void launcher_shutdown(void)
{
    launcher_poll();
    child_count = 0; /* launched GUI processes intentionally outlive Kilix Cap */
    clear_web_tracking(false);
}

bool launcher_enabled(void) { return enabled; }

const char *launcher_app_title(LaunchAppId id)
{
    return id >= 0 && id < LAUNCH_APP_COUNT ? app_titles[id] : "Program";
}

const char *launcher_tool_title(LaunchToolId id)
{
    return id >= 0 && id < LAUNCH_TOOL_COUNT ? tool_titles[id] : "Tool";
}

bool launcher_phone_available(void)
{
    LaunchPlan plan;
    return build_plan(LAUNCH_PHONE, &plan);
}

bool launcher_mail_configured(void) { return mail_target[0] != '\0'; }
const char *launcher_mail_target(void) { return mail_target; }
const char *launcher_web_home(void) { return web_home; }
const char *launcher_config_directory(void) { return config_directory; }

bool launcher_save_mail_target(const char *target)
{
    if (!valid_mail_target(target)) {
        set_error("Enter a program name or an http(s) mail URL.");
        return false;
    }
    if (config_directory[0] == '\0') {
        set_error("The Kilix Cap config directory is unavailable.");
        return false;
    }
    if (!persist_mail_target(target)) {
        set_error("Could not save the local mail configuration.");
        return false;
    }
    (void)snprintf(mail_target, sizeof mail_target, "%s", target);
    last_error[0] = '\0';
    return true;
}

static bool resolver_has_program(const char *name)
{
    char path[PATH_MAX];
    return program_resolver(name, path, sizeof path);
}

static bool in_kilix_session(void)
{
    const char *home = getenv("KILIX_HOME");
    const char *socket = getenv("KITTY_LISTEN_ON");
    const char *password = getenv("KILIX_RC_PASSWORD_FILE");
    return home != NULL && home[0] != '\0' && socket != NULL &&
           socket[0] != '\0' && password != NULL && password[0] != '\0';
}

bool launcher_open(LaunchAppId id)
{
    LaunchPlan plan;
    if (!enabled) {
        set_error("desktop app launching is disabled");
        return false;
    }
    if ((id == LAUNCH_WEB ||
         (id == LAUNCH_MAIL && mail_target[0] != '\0')) &&
        !in_kilix_session()) {
        set_error("Run Kilix Cap inside Kilix to open an app tab.");
        return false;
    }
    if (!build_plan(id, &plan)) {
        if (id == LAUNCH_PHONE)
            set_error("No VoIP or phone service is configured.");
        else if (id == LAUNCH_WEB ||
                 (id == LAUNCH_MAIL && mail_target[0] != '\0')) {
            if (!resolver_has_program("kilix"))
                set_error("Kilix is required to open a new app tab.");
            else if (id == LAUNCH_WEB || mail_target_is_url(mail_target))
                set_error("firefox-esr is not installed.");
            else
                set_error("The configured mail program is not installed.");
        } else
            set_error("no matching desktop program is installed");
        return false;
    }
    return spawn_plan(&plan);
}

bool launcher_open_laptop(const char *profile_id)
{
    LaunchPlan plan;
    LaptopProfile profile;
    char error[LAPTOP_ERROR_MAX];
    const char *desktop_arguments[2] = {NULL, NULL};
    size_t desktop_argument_count;

    if (!enabled) {
        set_error("desktop app launching is disabled");
        return false;
    }
    if (!in_kilix_session()) {
        set_error("Run Kilix Cap inside Kilix to open the laptop.");
        return false;
    }
    if (!laptop_load(profile_id, &profile, error, sizeof error)) {
        set_error(error);
        return false;
    }
    memset(&plan, 0, sizeof plan);
    if (!choose_program(&plan, (const char *const[]){"kilix"}, 1)) {
        set_error("Kilix is required to open the laptop.");
        return false;
    }
    plan.program = "the laptop";
    desktop_argument_count =
        laptop_desktop_arguments(&profile, desktop_arguments);
    if (desktop_argument_count > 0) {
        finish_plan_three(&plan, desktop_arguments[0],
                          desktop_argument_count > 1 ? desktop_arguments[1]
                                                     : NULL,
                          NULL);
        return spawn_plan(&plan);
    }
    {
        char session_path[PATH_MAX];
        if (config_directory[0] == '\0' ||
            snprintf(session_path, sizeof session_path,
                     "%s/laptop-%s.session", config_directory,
                     profile.id) >= (int)sizeof session_path ||
            !ensure_config_directory()) {
            set_error("The laptop session file has no home.");
            return false;
        }
        if (!laptop_write_session(&profile, session_path, error,
                                  sizeof error)) {
            set_error(error);
            return false;
        }
        finish_plan_three(&plan, "--detach", "--session", session_path);
    }
    return spawn_plan(&plan);
}

bool launcher_begin_web(void)
{
    LaunchPlan plan;
    char root[PATH_MAX];
    char project_helper[PATH_MAX];
    char browser_helper[PATH_MAX];
    char kitten[PATH_MAX];
    char password[PATH_MAX];
    char kilix[PATH_MAX];
    char python[PATH_MAX];
    char firefox[PATH_MAX];
    char output[64];

    if (!enabled) {
        set_error("desktop app launching is disabled");
        return false;
    }
    if (!in_kilix_session()) {
        set_error("Run Kilix Cap inside Kilix to open an app tab.");
        return false;
    }
    if (!resolve_kilix_control(kitten, sizeof kitten,
                               password, sizeof password) ||
        !program_resolver("kilix", kilix, sizeof kilix)) {
        set_error("Kilix remote control is unavailable.");
        return false;
    }
    if (!program_resolver("python3", python, sizeof python) ||
        !program_resolver("firefox-esr", firefox, sizeof firefox)) {
        set_error("firefox-esr is not installed.");
        return false;
    }
    if (!project_paths(root, sizeof root,
                       project_helper, sizeof project_helper) ||
        !join_path(browser_helper, sizeof browser_helper, root,
                   "tools/kilix_browser.py") ||
        !regular_readable_file(browser_helper)) {
        set_error("The isolated browser launcher is unavailable.");
        return false;
    }
    if (!prepare_web_ready_log()) {
        set_error("The browser readiness channel is unavailable.");
        return false;
    }
    if (!build_background_web_plan(web_home, kitten, password, kilix,
                                   python, browser_helper, firefox,
                                   web_ready_path, &plan) ||
        !command_output(plan.executable, plan.argv, output, sizeof output) ||
        !valid_window_id(output)) {
        clear_web_tracking(true);
        set_error("The background browser tab could not be started.");
        return false;
    }
    memcpy(web_window_id, output, strlen(output) + 1u);
    web_started_at = monotonic_seconds();
    (void)snprintf(last_program, sizeof last_program, "%s", plan.program);
    last_error[0] = '\0';
    return true;
}

static bool web_log_line_is(const char *line, size_t length,
                            const char *expected)
{
    size_t expected_length = strlen(expected);
    return length == expected_length &&
           memcmp(line, expected, expected_length) == 0;
}

static bool web_log_is_timestamped_legacy(const char *line, size_t length)
{
    static const char suffix[] = "] content-frames=1";
    const size_t suffix_length = sizeof suffix - 1u;
    const size_t suffix_at = length >= suffix_length
                                 ? length - suffix_length
                                 : 0u;
    size_t decimal_at = 0u;

    if (suffix_at <= 1u || line[0] != '[' ||
        memcmp(line + suffix_at, suffix, suffix_length) != 0)
        return false;
    for (size_t i = 1u; i < suffix_at; i++) {
        if (line[i] >= '0' && line[i] <= '9') continue;
        if (line[i] == '.' && decimal_at == 0u) {
            decimal_at = i;
            continue;
        }
        return false;
    }
    return decimal_at > 1u && suffix_at - decimal_at == 4u;
}

static WebReadyReason web_ready_reason(const char *contents)
{
    const char *line = contents;
    if (contents == NULL) return WEB_READY_REASON_NONE;
    while (*line != '\0') {
        const char *end = line;
        size_t length;
        while (*end != '\0' && *end != '\n' && *end != '\r') end++;
        length = (size_t)(end - line);
        if (web_log_line_is(line, length, "content-ready=changed"))
            return WEB_READY_REASON_CHANGED;
        if (web_log_line_is(line, length, "content-ready=initial-grace"))
            return WEB_READY_REASON_INITIAL_GRACE;
        if (web_log_line_is(line, length, "content-frames=1") ||
            web_log_is_timestamped_legacy(line, length))
            return WEB_READY_REASON_LEGACY_CHANGED;
        if (*end == '\0') break;
        line = end + 1;
        if (*end == '\r' && *line == '\n') line++;
    }
    return WEB_READY_REASON_NONE;
}

static LauncherWebStatus web_wait_status(double now, double started_at,
                                         bool ready_seen, double ready_at)
{
    if (ready_seen) {
        if (now <= 0.0 || ready_at <= 0.0 ||
            now - ready_at >= web_ready_settle_seconds)
            return LAUNCHER_WEB_READY;
        return LAUNCHER_WEB_WAITING;
    }
    if (now > 0.0 && started_at > 0.0 &&
        now - started_at >= web_launch_timeout_seconds)
        return LAUNCHER_WEB_FAILED;
    return LAUNCHER_WEB_WAITING;
}

LauncherWebStatus launcher_web_status(void)
{
    char contents[WEB_LOG_MAX];
    struct stat st;
    double now;
    LauncherWebStatus status;
    size_t used = 0;
    int fd;

    if (!valid_window_id(web_window_id) || web_ready_path[0] != '/') {
        set_error("The background browser tab is unavailable.");
        return LAUNCHER_WEB_FAILED;
    }
    now = monotonic_seconds();
    if (web_ready_seen)
        return web_wait_status(now, web_started_at,
                               web_ready_seen, web_ready_at);
    fd = open(web_ready_path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        if (errno == ENOENT)
            set_error("Firefox exited before capture readiness was reported.");
        else
            set_error("The browser readiness channel could not be read.");
        return LAUNCHER_WEB_FAILED;
    }
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) ||
        st.st_uid != getuid() || (st.st_mode & 0022) != 0) {
        close(fd);
        set_error("The browser readiness channel is unsafe.");
        return LAUNCHER_WEB_FAILED;
    }
    while (used + 1u < sizeof contents) {
        ssize_t count = read(fd, contents + used,
                             sizeof contents - used - 1u);
        if (count > 0) {
            used += (size_t)count;
            continue;
        }
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) {
            close(fd);
            set_error("The browser readiness channel could not be read.");
            return LAUNCHER_WEB_FAILED;
        }
        break;
    }
    close(fd);
    contents[used] = '\0';
    if (web_ready_reason(contents) != WEB_READY_REASON_NONE) {
        web_ready_seen = true;
        web_ready_at = now;
        return web_wait_status(now, web_started_at,
                               web_ready_seen, web_ready_at);
    }
    status = web_wait_status(now, web_started_at,
                             web_ready_seen, web_ready_at);
    if (status == LAUNCHER_WEB_FAILED)
        set_error("Firefox did not report capture readiness within 30 seconds.");
    return status;
}

bool launcher_focus_web(void)
{
    LaunchPlan plan;
    char kitten[PATH_MAX];
    char password[PATH_MAX];

    if (!valid_window_id(web_window_id)) {
        set_error("The background browser tab is unavailable.");
        return false;
    }
    if (!resolve_kilix_control(kitten, sizeof kitten,
                               password, sizeof password) ||
        !build_focus_web_plan(web_window_id, kitten, password, &plan)) {
        set_error("Kilix remote control is unavailable.");
        return false;
    }
    if (!command_without_output(plan.executable, plan.argv)) {
        set_error("The background browser tab could not be focused.");
        return false;
    }
    clear_web_tracking(false);
    (void)snprintf(last_program, sizeof last_program, "%s", plan.program);
    last_error[0] = '\0';
    return true;
}

void launcher_discard_web(void)
{
    clear_web_tracking(true);
}

bool launcher_open_tool(LaunchToolId id)
{
    LaunchPlan plan;
    if (!enabled) {
        set_error("desktop app launching is disabled");
        return false;
    }
    if (id < 0 || id >= LAUNCH_TOOL_COUNT) {
        set_error("the selected mansion tool is invalid");
        return false;
    }
    if (tool_is_terminal(id) && !in_kilix_session()) {
        set_error("Run Kilix Cap inside Kilix to open a monitor tab.");
        return false;
    }
    if (!build_tool_plan(id, &plan)) {
        if (tool_is_terminal(id))
            set_error("The Kilix system-console launcher is unavailable.");
        else if (tool_is_document(id))
            set_error("The project document viewer is unavailable.");
        else
            set_error("no matching desktop program is installed");
        return false;
    }
    return spawn_plan(&plan);
}

bool launcher_open_text_browser(void)
{
    LaunchPlan plan;
    char root[PATH_MAX];
    char helper[PATH_MAX];
    char kitten[PATH_MAX];
    char password[PATH_MAX];
    char kilix[PATH_MAX];
    const char *values[14];
    size_t count = 0;

    if (!enabled) {
        set_error("desktop app launching is disabled");
        return false;
    }
    if (!in_kilix_session()) {
        set_error("Run Kilix Cap inside Kilix to open a browser tab.");
        return false;
    }
    if (!resolve_kilix_control(kitten, sizeof kitten,
                               password, sizeof password)) {
        set_error("Kilix remote control is unavailable.");
        return false;
    }
    /* `kilix chawan` rather than the browser binary: the launcher owns the
     * pinned checkout and the first-run build, and on a machine that has
     * never opened it that first launch is what installs it. */
    if (!program_resolver("kilix", kilix, sizeof kilix)) {
        set_error("The Kilix launcher is unavailable.");
        return false;
    }
    if (!project_paths(root, sizeof root, helper, sizeof helper)) {
        set_error("The Kilix Cap project directory is unavailable.");
        return false;
    }

    memset(&plan, 0, sizeof plan);
    if (snprintf(plan.executable, sizeof plan.executable, "%s", kitten) < 0 ||
        strlen(kitten) >= sizeof plan.executable ||
        snprintf(plan.cwd, sizeof plan.cwd, "%s", root) < 0 ||
        strlen(root) >= sizeof plan.cwd) {
        set_error("The browser tab could not be described.");
        return false;
    }
    plan.program = "Text Browser";
    values[count++] = "@";
    values[count++] = "--password-file";
    values[count++] = password;
    values[count++] = "launch";
    values[count++] = "--type=tab";
    values[count++] = "--cwd";
    values[count++] = root;
    values[count++] = "--self";
    values[count++] = "--tab-title";
    values[count++] = "Text Browser";
    values[count++] = "--";
    values[count++] = kilix;
    values[count++] = "chawan";
    if (!finish_plan_many(&plan, values, count)) {
        set_error("The browser tab could not be described.");
        return false;
    }
    return spawn_plan(&plan);
}

bool launcher_open_game(const char *game_id, GameLaunchKind kind,
                        const char *kilix95_project_root,
                        const char *catalog_helper)
{
    LaunchPlan plan;
    char games_py[PATH_MAX];
    char kitten[PATH_MAX];
    char password[PATH_MAX];
    if (!enabled) {
        set_error("desktop app launching is disabled");
        return false;
    }
    if (!valid_game_id(game_id)) {
        set_error("Kilix 95 returned an invalid game identifier.");
        return false;
    }
    if (!in_kilix_session()) {
        set_error("Run Kilix Cap inside Kilix to open a game tab.");
        return false;
    }
    if (!resolve_kilix_control(kitten, sizeof kitten,
                               password, sizeof password)) {
        set_error("Kilix remote control is unavailable.");
        return false;
    }
    if (!build_game_plan(game_id, kind, kilix95_project_root,
                         catalog_helper, kitten, password, &plan)) {
        if (!resolver_has_program("python3"))
            set_error("Python 3 is required to launch Kilix 95 games.");
        else if (kilix95_project_root == NULL ||
                 !join_path(games_py, sizeof games_py,
                            kilix95_project_root, "games.py") ||
                 !regular_readable_file(games_py))
            set_error("The Kilix 95 game launcher is unavailable.");
        else if (!regular_readable_file(catalog_helper))
            set_error("The Kilix 95 game helper is unavailable.");
        else
            set_error("The Kilix 95 game could not be launched safely.");
        return false;
    }
    return spawn_plan(&plan);
}

const char *launcher_last_program(void) { return last_program; }
const char *launcher_last_error(void) { return last_error; }

static bool self_executable(char *path, size_t size)
{
    char resolved[PATH_MAX];
#if defined(__linux__)
    {
        ssize_t length = readlink("/proc/self/exe", resolved,
                                  sizeof resolved - 1u);
        if (length > 0 && (size_t)length < sizeof resolved) {
            int written;
            resolved[length] = '\0';
            written = snprintf(path, size, "%s", resolved);
            return written >= 0 && (size_t)written < size;
        }
    }
#endif
    /* argv[0] is caller-controlled (including via exec -a), so it is never
     * accepted as the identity of the test child. Unsupported platforms fail
     * the lifecycle test instead of spawning an untrusted path. */
    return false;
}

static bool plan_matches(LaunchAppId id, const char *program,
                         const char *first, const char *second,
                         const char *third)
{
    const char *const expected[] = {first, second, third};
    LaunchPlan plan;
    if (!build_plan(id, &plan) || strcmp(plan.program, program) != 0 ||
        strcmp(plan.argv[0], plan.executable) != 0)
        return false;
    for (size_t i = 0; i < sizeof expected / sizeof expected[0]; i++) {
        if (expected[i] == NULL) return plan.argv[i + 1u] == NULL;
        if (plan.argv[i + 1u] == NULL ||
            strcmp(plan.argv[i + 1u], expected[i]) != 0)
            return false;
    }
    return plan.argv[4] == NULL;
}

static bool config_selftest(void)
{
    static const char *const rejected[] = {
        "", "thunderbird --safe", "../mail", "-option",
        "javascript:alert(1)", "https://", "http:///bad", "mail;touch"
    };
    char saved_directory[PATH_MAX];
    char saved_target[MAIL_TARGET_MAX + 1];
    char saved_web_home[WEB_HOME_MAX + 1];
    char saved_error[sizeof last_error];
    char temporary[] = "/tmp/kilix-cap-config.XXXXXX";
    char config_path[PATH_MAX];
    struct stat directory_stat;
    struct stat config_stat;
    bool ok = false;

    (void)snprintf(saved_directory, sizeof saved_directory, "%s",
                   config_directory);
    (void)snprintf(saved_target, sizeof saved_target, "%s", mail_target);
    (void)snprintf(saved_web_home, sizeof saved_web_home, "%s", web_home);
    (void)snprintf(saved_error, sizeof saved_error, "%s", last_error);
    if (mkdtemp(temporary) == NULL) goto done;
    (void)snprintf(config_directory, sizeof config_directory, "%s",
                   temporary);
    mail_target[0] = '\0';
    (void)snprintf(web_home, sizeof web_home, "%s",
                   "https://example.test/start");
    for (size_t i = 0; i < COUNT_OF(rejected); i++)
        if (launcher_save_mail_target(rejected[i])) goto cleanup;
    if (!launcher_save_mail_target("https://mail.example.test/inbox"))
        goto cleanup;
    mail_target[0] = '\0';
    (void)snprintf(web_home, sizeof web_home, "%s", default_web_home);
    load_config();
    if (strcmp(mail_target, "https://mail.example.test/inbox") != 0 ||
        strcmp(web_home, "https://example.test/start") != 0)
        goto cleanup;
    if (!launcher_save_mail_target("thunderbird")) goto cleanup;
    mail_target[0] = '\0';
    (void)snprintf(web_home, sizeof web_home, "%s", default_web_home);
    load_config();
    if (strcmp(mail_target, "thunderbird") != 0 ||
        strcmp(web_home, "https://example.test/start") != 0)
        goto cleanup;
    if (valid_http_url("https://", WEB_HOME_MAX) ||
        valid_http_url("file:///tmp/page", WEB_HOME_MAX) ||
        valid_http_url("javascript:alert(1)", WEB_HOME_MAX) ||
        valid_http_url("https://bad host/", WEB_HOME_MAX))
        goto cleanup;
    if (snprintf(config_path, sizeof config_path, "%s/config", temporary) < 0 ||
        lstat(temporary, &directory_stat) != 0 ||
        lstat(config_path, &config_stat) != 0 ||
        !S_ISDIR(directory_stat.st_mode) ||
        (directory_stat.st_mode & 0777) != 0700 ||
        !S_ISREG(config_stat.st_mode) || (config_stat.st_mode & 0777) != 0600)
        goto cleanup;
    ok = true;

cleanup:
    (void)snprintf(config_path, sizeof config_path, "%s/config", temporary);
    (void)unlink(config_path);
    (void)rmdir(temporary);
done:
    (void)snprintf(config_directory, sizeof config_directory, "%s",
                   saved_directory);
    (void)snprintf(mail_target, sizeof mail_target, "%s", saved_target);
    (void)snprintf(web_home, sizeof web_home, "%s", saved_web_home);
    (void)snprintf(last_error, sizeof last_error, "%s", saved_error);
    return ok;
}

static bool game_plan_selftest(void)
{
    static const char fixture[] = "# launcher plan fixture\n";
    char temporary[] = "/tmp/kilix-cap-game-plan.XXXXXX";
    char games_py[PATH_MAX] = {0};
    char helper[PATH_MAX] = {0};
    LaunchPlan plan;
    int fd = -1;
    bool ok = false;
    if (mkdtemp(temporary) == NULL ||
        !join_path(games_py, sizeof games_py, temporary, "games.py") ||
        !join_path(helper, sizeof helper, temporary, "helper.py"))
        goto cleanup;
    fd = open(games_py, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0 || write(fd, fixture, sizeof fixture - 1u) !=
                      (ssize_t)(sizeof fixture - 1u))
        goto cleanup;
    close(fd);
    fd = open(helper, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0 || write(fd, fixture, sizeof fixture - 1u) !=
                      (ssize_t)(sizeof fixture - 1u))
        goto cleanup;
    close(fd);
    fd = -1;

    if (!build_game_plan("kilix-pong", GAME_LAUNCH_KILIX95, temporary,
                         helper, "/fixture/kitten", "/fixture/password",
                         &plan) ||
        strcmp(plan.program, "kilix-pong") != 0 ||
        strcmp(plan.argv[0], "/fixture/kitten") != 0 ||
        strcmp(plan.argv[1], "@") != 0 ||
        strcmp(plan.argv[2], "--password-file") != 0 ||
        strcmp(plan.argv[3], "/fixture/password") != 0 ||
        strcmp(plan.argv[4], "launch") != 0 ||
        strcmp(plan.argv[5], "--type=tab") != 0 ||
        strcmp(plan.argv[6], "--cwd") != 0 ||
        strcmp(plan.argv[7], temporary) != 0 ||
        strcmp(plan.argv[8], "--self") != 0 ||
        strcmp(plan.argv[9], "--tab-title") != 0 ||
        strcmp(plan.argv[10], "kilix-pong") != 0 ||
        strcmp(plan.argv[11], "--") != 0 ||
        strcmp(plan.argv[12], "/fixture/python3") != 0 ||
        strcmp(plan.argv[13], helper) != 0 ||
        strcmp(plan.argv[14], "launch") != 0 ||
        strcmp(plan.argv[15], temporary) != 0 ||
        strcmp(plan.argv[16], "kilix-pong") != 0 || plan.argv[17] != NULL)
        goto cleanup;
    if (!build_game_plan("mines", GAME_LAUNCH_KILIX95_BUILTIN, temporary,
                         helper, "/fixture/kitten", "/fixture/password",
                         &plan) ||
        strcmp(plan.argv[11], "--") != 0 ||
        strcmp(plan.argv[12], "/fixture/python3") != 0 ||
        strcmp(plan.argv[13], helper) != 0 ||
        strcmp(plan.argv[14], "builtin") != 0 ||
        strcmp(plan.argv[15], temporary) != 0 ||
        strcmp(plan.argv[16], "mines") != 0 || plan.argv[17] != NULL)
        goto cleanup;
    if (build_game_plan("doom;touch", GAME_LAUNCH_KILIX95, temporary,
                        helper, "/fixture/kitten", "/fixture/password",
                        &plan) ||
        build_game_plan("../doom", GAME_LAUNCH_KILIX95, temporary,
                        helper, "/fixture/kitten", "/fixture/password",
                        &plan))
        goto cleanup;
    ok = true;

cleanup:
    if (fd >= 0) close(fd);
    if (games_py[0] != '\0') (void)unlink(games_py);
    if (helper[0] != '\0') (void)unlink(helper);
    if (temporary[0] == '/') (void)rmdir(temporary);
    return ok;
}

/* `make test` has to answer the same question inside a Kilix pane and outside
 * one. These variables are what in_kilix_session() reads, so without this the
 * developer's terminal would decide which ladder the assertions below see.
 */
typedef struct {
    char home[PATH_MAX];
    char socket[PATH_MAX];
    char password[PATH_MAX];
    bool had_home;
    bool had_socket;
    bool had_password;
} SavedKilixSession;

static bool save_environment_value(const char *name, char *value, size_t size,
                                   bool *present)
{
    const char *current = getenv(name);
    *present = current != NULL;
    if (current == NULL) {
        value[0] = '\0';
        return true;
    }
    return snprintf(value, size, "%s", current) >= 0 && strlen(current) < size;
}

static bool without_kilix_session(SavedKilixSession *saved)
{
    if (saved == NULL ||
        !save_environment_value("KILIX_HOME", saved->home, sizeof saved->home,
                                &saved->had_home) ||
        !save_environment_value("KITTY_LISTEN_ON", saved->socket,
                                sizeof saved->socket, &saved->had_socket) ||
        !save_environment_value("KILIX_RC_PASSWORD_FILE", saved->password,
                                sizeof saved->password, &saved->had_password))
        return false;
    unsetenv("KILIX_HOME");
    unsetenv("KITTY_LISTEN_ON");
    unsetenv("KILIX_RC_PASSWORD_FILE");
    return !in_kilix_session();
}

static void restore_kilix_session(const SavedKilixSession *saved)
{
    if (saved == NULL) return;
    if (saved->had_home) setenv("KILIX_HOME", saved->home, 1);
    if (saved->had_socket) setenv("KITTY_LISTEN_ON", saved->socket, 1);
    if (saved->had_password)
        setenv("KILIX_RC_PASSWORD_FILE", saved->password, 1);
}

static bool tool_plan_selftest(void)
{
    char root[PATH_MAX];
    char helper[PATH_MAX];
    char readme[PATH_MAX];
    SavedKilixSession session;
    LaunchPlan plan;

    if (!project_paths(root, sizeof root, helper, sizeof helper) ||
        !build_terminal_tool_plan(
            LAUNCH_TOOL_LOGS, root, helper, "/fixture/kitten",
            "/fixture/password", &plan) ||
        strcmp(plan.program, tool_titles[LAUNCH_TOOL_LOGS]) != 0 ||
        strcmp(plan.argv[0], "/fixture/kitten") != 0 ||
        strcmp(plan.argv[1], "@") != 0 ||
        strcmp(plan.argv[2], "--password-file") != 0 ||
        strcmp(plan.argv[3], "/fixture/password") != 0 ||
        strcmp(plan.argv[4], "launch") != 0 ||
        strcmp(plan.argv[5], "--type=tab") != 0 ||
        strcmp(plan.argv[6], "--cwd") != 0 ||
        strcmp(plan.argv[7], root) != 0 ||
        strcmp(plan.argv[8], "--self") != 0 ||
        strcmp(plan.argv[9], "--tab-title") != 0 ||
        strcmp(plan.argv[10], tool_titles[LAUNCH_TOOL_LOGS]) != 0 ||
        strcmp(plan.argv[11], "--") != 0 ||
        strcmp(plan.argv[12], "/fixture/python3") != 0 ||
        strcmp(plan.argv[13], helper) != 0 ||
        strcmp(plan.argv[14], "logs") != 0 || plan.argv[15] != NULL)
        return false;
    if (!build_terminal_tool_plan(
            LAUNCH_TOOL_CLEAN_PACKAGES, root, helper, "/fixture/kitten",
            "/fixture/password", &plan) ||
        strcmp(plan.argv[14], "cleanup") != 0 ||
        strcmp(plan.argv[15], "packages") != 0 || plan.argv[16] != NULL)
        return false;
    /* The stack tab a Server Room console opens when there is a Kilix around
     * it. Built with fixture control values for the same reason the terminal
     * plans above are: the assertion is the exact argv, not the machine. */
    if (!build_kilix_tab_plan("Kilix Settings",
                              (const char *const[]){"kilix", "settings"}, 2,
                              root, "/fixture/kitten", "/fixture/password",
                              &plan) ||
        strcmp(plan.program, "Kilix Settings") != 0 ||
        strcmp(plan.argv[0], "/fixture/kitten") != 0 ||
        strcmp(plan.argv[9], "--tab-title") != 0 ||
        strcmp(plan.argv[10], "Kilix Settings") != 0 ||
        strcmp(plan.argv[11], "--") != 0 ||
        strcmp(plan.argv[12], "kilix") != 0 ||
        strcmp(plan.argv[13], "settings") != 0 || plan.argv[14] != NULL)
        return false;
    if (!build_kilix_tab_plan("Update",
                              (const char *const[]){"kilix", "update",
                                                    "--stack"}, 3,
                              root, "/fixture/kitten", "/fixture/password",
                              &plan) ||
        strcmp(plan.argv[12], "kilix") != 0 ||
        strcmp(plan.argv[13], "update") != 0 ||
        strcmp(plan.argv[14], "--stack") != 0 || plan.argv[15] != NULL)
        return false;
    /* An empty argv would launch a tab that runs whatever the shell defaults
     * to; a caller that miscounts must get nothing instead. */
    if (build_kilix_tab_plan("Empty", (const char *const[]){"kilix"}, 0, root,
                             "/fixture/kitten", "/fixture/password", &plan))
        return false;
    /* Outside a Kilix session the host's own settings program is still the
     * answer. Cleared explicitly so running `make test` from inside a Kilix
     * pane cannot change what this asserts. */
    if (!without_kilix_session(&session) ||
        !build_tool_plan(LAUNCH_TOOL_SETTINGS, &plan) ||
        strcmp(plan.program, "xfce4-settings-manager") != 0 ||
        plan.argv[1] != NULL) {
        restore_kilix_session(&session);
        return false;
    }
    if (!build_tool_plan(LAUNCH_TOOL_SOFTWARE, &plan) ||
        strcmp(plan.program, "synaptic") != 0 || plan.argv[1] != NULL) {
        restore_kilix_session(&session);
        return false;
    }
    restore_kilix_session(&session);
    if (!join_path(readme, sizeof readme, root, "README.md") ||
        !build_tool_plan(LAUNCH_TOOL_DOC_START, &plan) ||
        strcmp(plan.program, "xdg-open") != 0 ||
        plan.argv[1] == NULL || strcmp(plan.argv[1], readme) != 0 ||
        plan.argv[2] != NULL)
        return false;
    return !build_tool_plan((LaunchToolId)-1, &plan) &&
           !build_tool_plan(LAUNCH_TOOL_COUNT, &plan);
}

static bool web_plan_selftest(void)
{
    LaunchPlan plan;
    if (!build_background_web_plan(
            "https://news.ycombinator.com/", "/fixture/kitten",
            "/fixture/password", "/fixture/kilix", "/fixture/python3",
            "/fixture/kilix_browser.py", "/fixture/firefox-esr",
            "/fixture/.web-ready.1.0.log", &plan) ||
        strcmp(plan.program, "firefox-esr") != 0 ||
        strcmp(plan.argv[0], "/fixture/kitten") != 0 ||
        strcmp(plan.argv[1], "@") != 0 ||
        strcmp(plan.argv[2], "--password-file") != 0 ||
        strcmp(plan.argv[3], "/fixture/password") != 0 ||
        strcmp(plan.argv[4], "launch") != 0 ||
        strcmp(plan.argv[5], "--type=tab") != 0 ||
        strcmp(plan.argv[6], "--cwd=current") != 0 ||
        strcmp(plan.argv[7], "--self") != 0 ||
        strcmp(plan.argv[8], "--keep-focus") != 0 ||
        strcmp(plan.argv[9], "--tab-title") != 0 ||
        strcmp(plan.argv[10], "Web") != 0 ||
        strcmp(plan.argv[11], "--env") != 0 ||
        strcmp(plan.argv[12], "KILIX_IN_OVERLAY=1") != 0 ||
        strcmp(plan.argv[13], "--env") != 0 ||
        strcmp(plan.argv[14],
               "KILIX_RUN_LOG=/fixture/.web-ready.1.0.log") != 0 ||
        strcmp(plan.argv[15], "--") != 0 ||
        strcmp(plan.argv[16], "/fixture/kilix") != 0 ||
        strcmp(plan.argv[17], "run") != 0 ||
        strcmp(plan.argv[18], "/fixture/python3") != 0 ||
        strcmp(plan.argv[19], "/fixture/kilix_browser.py") != 0 ||
        strcmp(plan.argv[20], "/fixture/firefox-esr") != 0 ||
        strcmp(plan.argv[21], "https://news.ycombinator.com/") != 0 ||
        plan.argv[22] != NULL)
        return false;
    if (!build_focus_web_plan("187", "/fixture/kitten",
                              "/fixture/password", &plan) ||
        strcmp(plan.argv[4], "focus-window") != 0 ||
        strcmp(plan.argv[5], "--match") != 0 ||
        strcmp(plan.argv[6], "id:187") != 0 || plan.argv[7] != NULL)
        return false;
    return !build_background_web_plan(
               "file:///tmp/page", "/fixture/kitten", "/fixture/password",
               "/fixture/kilix", "/fixture/python3",
               "/fixture/kilix_browser.py", "/fixture/firefox-esr",
               "/fixture/.web-ready.1.0.log", &plan) &&
           !build_focus_web_plan("187;touch", "/fixture/kitten",
                                 "/fixture/password", &plan) &&
           !build_focus_web_plan("../187", "/fixture/kitten",
                                 "/fixture/password", &plan);
}

static bool web_readiness_selftest(void)
{
    return web_ready_reason("content-ready=changed\n") ==
               WEB_READY_REASON_CHANGED &&
           web_ready_reason("noise\r\ncontent-ready=initial-grace\r\n") ==
               WEB_READY_REASON_INITIAL_GRACE &&
           web_ready_reason("content-frames=1") ==
               WEB_READY_REASON_LEGACY_CHANGED &&
           web_ready_reason("[123.456] content-frames=1\n") ==
               WEB_READY_REASON_LEGACY_CHANGED &&
           web_ready_reason("") == WEB_READY_REASON_NONE &&
           web_ready_reason("xcontent-ready=changed\n") ==
               WEB_READY_REASON_NONE &&
           web_ready_reason("content-ready=changed-extra\n") ==
               WEB_READY_REASON_NONE &&
           web_ready_reason("content-ready=unknown\n") ==
               WEB_READY_REASON_NONE &&
           web_ready_reason("prefix content-frames=1\n") ==
               WEB_READY_REASON_NONE &&
           web_ready_reason("[time] content-frames=1\n") ==
               WEB_READY_REASON_NONE &&
           web_ready_reason("[123.45] content-frames=1\n") ==
               WEB_READY_REASON_NONE &&
           web_wait_status(10.74, 1.0, true, 10.0) ==
               LAUNCHER_WEB_WAITING &&
           web_wait_status(10.75, 1.0, true, 10.0) ==
               LAUNCHER_WEB_READY &&
           web_wait_status(30.99, 1.0, false, 0.0) ==
               LAUNCHER_WEB_WAITING &&
           web_wait_status(31.0, 1.0, false, 0.0) ==
               LAUNCHER_WEB_FAILED;
}

bool launcher_selftest(void)
{
    static const struct {
        LaunchAppId id;
        const char *program;
        const char *first;
        const char *second;
        const char *third;
    } expected[LAUNCH_APP_COUNT] = {
        {LAUNCH_CLOCK, "gnome-clocks", NULL, NULL, NULL},
        {LAUNCH_INBOX, "thunderbird", NULL, NULL, NULL},
        {LAUNCH_OUTBOX, "thunderbird", NULL, NULL, NULL},
        {LAUNCH_MAIL, "thunderbird", "run", "thunderbird", NULL},
        {LAUNCH_PROFILE, "gnome-contacts", NULL, NULL, NULL},
        {LAUNCH_NOTES, "mousepad", "--disable-server", NULL, NULL},
        {LAUNCH_DATES, "gnome-calendar", NULL, NULL, NULL},
        {LAUNCH_CARDS, "gnome-contacts", NULL, NULL, NULL},
        {LAUNCH_FILES, "thunar", NULL, NULL, NULL},
        {LAUNCH_PHONE, "gnome-calls", NULL, NULL, NULL},
        {LAUNCH_PAPER, "libreoffice", "--writer", NULL, NULL},
        {LAUNCH_CALCULATOR, "gnome-calculator", NULL, NULL, NULL},
        {LAUNCH_WEB, "firefox-esr", "run", "firefox-esr", NULL}
    };
    char saved_mail_target[MAIL_TARGET_MAX + 1];
    char saved_web_home[WEB_HOME_MAX + 1];
    char expected_documents[PATH_MAX];
    char launch_cwd[] = "/tmp/kilix-cap-launch-cwd.XXXXXX";
    LaunchPlan plan;
    pid_t child;
    int status = 0;
    bool ok = false;

    launcher_init();
    (void)snprintf(saved_mail_target, sizeof saved_mail_target, "%s",
                   mail_target);
    (void)snprintf(saved_web_home, sizeof saved_web_home, "%s", web_home);
    if (!config_selftest()) goto done;
    if (!valid_desktop_id("fixture-editor.desktop") ||
        valid_desktop_id("../editor.desktop") ||
        valid_desktop_id("-option.desktop") ||
        valid_desktop_id("editor;touch.desktop") ||
        valid_desktop_id("editor"))
        goto done;
    (void)snprintf(mail_target, sizeof mail_target, "%s", "thunderbird");
    program_resolver = fixture_resolver;
    scheme_handler_probe = fixture_scheme_handler;
    fixture_only_program = NULL;
    fixture_tel_handler = false;
    fixture_text_editor_handler = false;
    if (!game_plan_selftest() || !tool_plan_selftest() ||
        !web_plan_selftest() || !web_readiness_selftest())
        goto done;
    for (int i = 0; i < LAUNCH_APP_COUNT; i++) {
        const char *first = expected[i].first;
        if (expected[i].id == LAUNCH_FILES) first = working_directory;
        const char *third = expected[i].id == LAUNCH_WEB
                                ? web_home
                                : expected[i].third;
        if (!plan_matches(expected[i].id, expected[i].program, first,
                          expected[i].second, third))
            goto done;
    }
    if (!join_path(expected_documents, sizeof expected_documents,
                   getenv("HOME"), "Documents") ||
        !build_plan(LAUNCH_NOTES, &plan) ||
        strcmp(plan.cwd, expected_documents) != 0)
        goto done;
    fixture_only_program = "xdg-open";
    if (!plan_matches(LAUNCH_CLOCK, "xdg-open", "https://time.is", NULL,
                      NULL))
        goto done;
    fixture_only_program = "abiword";
    if (!plan_matches(LAUNCH_NOTES, "abiword", NULL, NULL, NULL)) goto done;
    fixture_only_program = "gtk-launch";
    fixture_text_editor_handler = true;
    text_editor_probe = fixture_text_editor;
    if (!plan_matches(LAUNCH_NOTES, "default text editor",
                      "fixture-editor.desktop", NULL, NULL))
        goto done;
    fixture_text_editor_handler = false;
    text_editor_probe = query_text_editor_handler;
    fixture_only_program = "xdg-open";
    fixture_tel_handler = true;
    if (!plan_matches(LAUNCH_PHONE, "xdg-open", "tel:", NULL, NULL))
        goto done;
    fixture_tel_handler = false;
    if (launcher_phone_available() || build_plan(LAUNCH_PHONE, &plan))
        goto done;
    if (enabled &&
        (launcher_open(LAUNCH_PHONE) ||
         strcmp(launcher_last_error(),
                "No VoIP or phone service is configured.") != 0))
        goto done;
    fixture_only_program = NULL;
    (void)snprintf(mail_target, sizeof mail_target, "%s",
                   "https://mail.example.test/");
    if (!plan_matches(LAUNCH_MAIL, "firefox-esr", "run", "firefox-esr",
                      "https://mail.example.test/"))
        goto done;
    mail_target[0] = '\0';
    if (!plan_matches(LAUNCH_MAIL, "thunderbird", NULL, NULL, NULL))
        goto done;
    if (build_plan((LaunchAppId)-1, &plan) ||
        build_plan(LAUNCH_APP_COUNT, &plan))
        goto done;

    /* The global opt-out is absolute, even for the lifecycle portion of the
     * selftest. Pure plan checks above still run without starting a child. */
    if (!enabled) {
        ok = true;
        goto done;
    }

    program_resolver = resolve_program;
    fixture_only_program = NULL;
    memset(&plan, 0, sizeof plan);
    if (mkdtemp(launch_cwd) == NULL ||
        !self_executable(plan.executable, sizeof plan.executable) ||
        snprintf(plan.cwd, sizeof plan.cwd, "%s", launch_cwd) < 0 ||
        strlen(launch_cwd) >= sizeof plan.cwd)
        goto done;
    plan.program = "kilix-cap-test-child";
    finish_plan_three(&plan, "--launcher-child", "literal;*$()", launch_cwd);
    if (!spawn_plan(&plan) || child_count != 1) goto done;
    child = children[0];
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) goto done;
    }
    child_count = 0;
    ok = WIFEXITED(status) &&
         WEXITSTATUS(status) == LAUNCHER_TEST_CHILD_EXIT;

done:
    (void)snprintf(mail_target, sizeof mail_target, "%s", saved_mail_target);
    (void)snprintf(web_home, sizeof web_home, "%s", saved_web_home);
    program_resolver = resolve_program;
    scheme_handler_probe = query_scheme_handler;
    text_editor_probe = query_text_editor_handler;
    fixture_only_program = NULL;
    fixture_tel_handler = false;
    fixture_text_editor_handler = false;
    (void)rmdir(launch_cwd);
    launcher_shutdown();
    return ok;
}
