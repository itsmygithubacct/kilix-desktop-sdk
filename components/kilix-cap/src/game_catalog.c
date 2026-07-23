/* game_catalog.c — bounded, shell-free Kilix 95 catalog discovery. */
#include "game_catalog.h"

#include <ctype.h>
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

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

extern char **environ;

enum {
    WATCH_MAX = 4,
    OUTPUT_MAX = 32768,
    POLL_INTERVAL_MS = 1000
};

typedef struct WatchSource {
    char path[PATH_MAX];
    dev_t device;
    ino_t inode;
    off_t size;
    struct timespec modified;
    bool exists;
} WatchSource;

typedef struct CatalogSnapshot {
    GameCatalogEntry entries[GAME_CATALOG_MAX];
    int count;
    WatchSource watches[WATCH_MAX];
    int watch_count;
} CatalogSnapshot;

static CatalogSnapshot current;
static char kilix95_root[PATH_MAX];
static char helper_path[PATH_MAX];
static char last_error[160];
static int64_t next_poll_ms;
static bool available;

static void set_error(const char *message)
{
    (void)snprintf(last_error, sizeof last_error, "%s",
                   message != NULL ? message : "game catalog unavailable");
}

static bool copy_text(char *dst, size_t size, const char *src)
{
    int written;
    if (dst == NULL || size == 0 || src == NULL) return false;
    written = snprintf(dst, size, "%s", src);
    return written >= 0 && (size_t)written < size;
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

static bool parent_directory(const char *path, char *dst, size_t size)
{
    const char *slash;
    size_t length;
    if (path == NULL || dst == NULL || size == 0) return false;
    slash = strrchr(path, '/');
    if (slash == NULL) return false;
    length = slash == path ? 1u : (size_t)(slash - path);
    if (length + 1u > size) return false;
    memcpy(dst, path, length);
    dst[length] = '\0';
    return true;
}

static bool executable_path(const char *argv0, char *dst, size_t size)
{
    char resolved[PATH_MAX];
#if defined(__linux__)
    {
        ssize_t length = readlink("/proc/self/exe", resolved,
                                  sizeof resolved - 1u);
        if (length > 0 && (size_t)length < sizeof resolved) {
            resolved[length] = '\0';
            return copy_text(dst, size, resolved);
        }
    }
#endif
    if (argv0 != NULL && strchr(argv0, '/') != NULL &&
        realpath(argv0, resolved) != NULL)
        return copy_text(dst, size, resolved);
    return false;
}

static bool regular_readable(const char *path)
{
    struct stat st;
    return path != NULL && stat(path, &st) == 0 && S_ISREG(st.st_mode) &&
           access(path, R_OK) == 0;
}

static bool valid_root(const char *candidate, char *resolved, size_t size)
{
    char real[PATH_MAX];
    char games[PATH_MAX];
    struct stat st;
    if (candidate == NULL || candidate[0] != '/' ||
        realpath(candidate, real) == NULL || stat(real, &st) != 0 ||
        !S_ISDIR(st.st_mode) || !join_path(games, sizeof games, real,
                                           "games.py") ||
        !regular_readable(games))
        return false;
    return copy_text(resolved, size, real);
}

static bool locate_paths(const char *argv0)
{
    const char *root_override = getenv("KILIX95_PROJECT_HOME");
    const char *helper_override = getenv("KILIX_CAP_KILIX95_HELPER");
    char executable[PATH_MAX];
    char bin_directory[PATH_MAX];
    char project_directory[PATH_MAX];
    char source_parent[PATH_MAX];
    char candidate[PATH_MAX];
    char real_helper[PATH_MAX];

    kilix95_root[0] = '\0';
    helper_path[0] = '\0';
    if (!executable_path(argv0, executable, sizeof executable) ||
        !parent_directory(executable, bin_directory, sizeof bin_directory) ||
        !parent_directory(bin_directory, project_directory,
                          sizeof project_directory)) {
        set_error("Could not locate Kilix Cap's game-catalog helper.");
        return false;
    }
    if (helper_override != NULL && helper_override[0] != '\0') {
        if (helper_override[0] != '/' ||
            realpath(helper_override, real_helper) == NULL ||
            !regular_readable(real_helper) ||
            !copy_text(helper_path, sizeof helper_path, real_helper)) {
            set_error("The Kilix 95 catalog helper override is invalid.");
            return false;
        }
    } else {
        if (!join_path(candidate, sizeof candidate, project_directory,
                       "tools/kilix95_games.py") ||
            realpath(candidate, real_helper) == NULL ||
            !regular_readable(real_helper) ||
            !copy_text(helper_path, sizeof helper_path, real_helper)) {
            set_error("Could not locate Kilix Cap's game-catalog helper.");
            return false;
        }
    }

    if (root_override != NULL && root_override[0] != '\0') {
        if (!valid_root(root_override, kilix95_root, sizeof kilix95_root)) {
            set_error("KILIX95_PROJECT_HOME does not contain games.py.");
            return false;
        }
    } else {
        if (!parent_directory(project_directory, source_parent,
                              sizeof source_parent) ||
            !join_path(candidate, sizeof candidate, source_parent,
                       "kilix-95") ||
            !valid_root(candidate, kilix95_root, sizeof kilix95_root)) {
            set_error("A sibling Kilix 95 checkout was not found.");
            return false;
        }
    }
    return true;
}

static bool locate_helper_only(const char *argv0)
{
    const char *override = getenv("KILIX_CAP_KILIX95_HELPER");
    char executable[PATH_MAX];
    char bin_directory[PATH_MAX];
    char project_directory[PATH_MAX];
    char candidate[PATH_MAX];
    char resolved[PATH_MAX];
    if (override != NULL && override[0] != '\0') {
        if (override[0] != '/' || realpath(override, resolved) == NULL ||
            !regular_readable(resolved))
            return false;
        return copy_text(helper_path, sizeof helper_path, resolved);
    }
    if (!executable_path(argv0, executable, sizeof executable) ||
        !parent_directory(executable, bin_directory, sizeof bin_directory) ||
        !parent_directory(bin_directory, project_directory,
                          sizeof project_directory) ||
        !join_path(candidate, sizeof candidate, project_directory,
                   "tools/kilix95_games.py") ||
        realpath(candidate, resolved) == NULL || !regular_readable(resolved))
        return false;
    return copy_text(helper_path, sizeof helper_path, resolved);
}

static int64_t monotonic_ms(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return 0;
    return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static bool run_helper(const char *mode, const char *root,
                       char *output, size_t size)
{
    posix_spawn_file_actions_t actions;
    posix_spawnattr_t attributes;
    sigset_t empty;
    sigset_t defaults;
    char *argv[6];
    int pipefd[2] = {-1, -1};
    pid_t child = -1;
    size_t used = 0;
    int status = 0;
    int rc;
    bool overflow = false;

    if (mode == NULL || output == NULL || size < 2 || helper_path[0] == '\0')
        return false;
    if (pipe(pipefd) != 0) return false;
    (void)fcntl(pipefd[0], F_SETFD, FD_CLOEXEC);
    (void)fcntl(pipefd[1], F_SETFD, FD_CLOEXEC);
    rc = posix_spawn_file_actions_init(&actions);
    if (rc != 0) goto cleanup;
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
        goto cleanup;
    }
    rc = posix_spawnattr_init(&attributes);
    if (rc != 0) {
        posix_spawn_file_actions_destroy(&actions);
        goto cleanup;
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
    argv[0] = (char *)"python3";
    argv[1] = helper_path;
    argv[2] = (char *)mode;
    argv[3] = root != NULL ? (char *)root : NULL;
    argv[4] = NULL;
    argv[5] = NULL;
    if (rc == 0)
        rc = posix_spawnp(&child, "python3", &actions, &attributes, argv,
                          environ);
    posix_spawnattr_destroy(&attributes);
    posix_spawn_file_actions_destroy(&actions);
    if (rc != 0) goto cleanup;
    close(pipefd[1]);
    pipefd[1] = -1;

    for (;;) {
        ssize_t count;
        if (used + 1u >= size) {
            char discard[1024];
            overflow = true;
            count = read(pipefd[0], discard, sizeof discard);
        } else {
            count = read(pipefd[0], output + used, size - used - 1u);
            if (count > 0) used += (size_t)count;
        }
        if (count == 0) break;
        if (count < 0 && errno == EINTR) continue;
        if (count < 0) overflow = true;
        if (count < 0) break;
    }
    close(pipefd[0]);
    pipefd[0] = -1;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) goto cleanup;
    }
    child = -1;
    output[used] = '\0';
    return !overflow && WIFEXITED(status) && WEXITSTATUS(status) == 0;

cleanup:
    if (pipefd[0] >= 0) close(pipefd[0]);
    if (pipefd[1] >= 0) close(pipefd[1]);
    if (child > 0) {
        while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
    }
    if (size > 0) output[0] = '\0';
    return false;
}

static bool valid_id(const char *text)
{
    size_t length;
    if (text == NULL || text[0] == '\0') return false;
    length = strlen(text);
    if (length > GAME_ID_MAX || text[0] == '-') return false;
    for (size_t i = 0; i < length; i++) {
        unsigned char ch = (unsigned char)text[i];
        if (!((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') ||
              ch == '-'))
            return false;
    }
    return true;
}

static bool valid_label(const char *text)
{
    size_t length;
    if (text == NULL || text[0] == '\0') return false;
    length = strlen(text);
    if (length > GAME_LABEL_MAX) return false;
    for (size_t i = 0; i < length; i++) {
        unsigned char ch = (unsigned char)text[i];
        if (ch < 32u || ch > 126u) return false;
    }
    return true;
}

static bool decode_icon(const char *text, uint8_t pixels[GAME_ICON_PIXELS])
{
    bool visible = false;
    if (text == NULL || strlen(text) != GAME_ICON_PIXELS || pixels == NULL)
        return false;
    for (int i = 0; i < GAME_ICON_PIXELS; i++) {
        unsigned char ch = (unsigned char)text[i];
        uint8_t value;
        if (ch >= '0' && ch <= '9') value = (uint8_t)(ch - '0');
        else if (ch >= 'a' && ch <= 'e') value = (uint8_t)(ch - 'a' + 10);
        else return false;
        pixels[i] = value;
        if (value != 0) visible = true;
    }
    return visible;
}

static void snapshot_watch(WatchSource *watch)
{
    struct stat st;
    if (watch == NULL) return;
    watch->exists = stat(watch->path, &st) == 0;
    if (!watch->exists) {
        watch->device = 0;
        watch->inode = 0;
        watch->size = 0;
        watch->modified.tv_sec = 0;
        watch->modified.tv_nsec = 0;
        return;
    }
    watch->device = st.st_dev;
    watch->inode = st.st_ino;
    watch->size = st.st_size;
    watch->modified = st.st_mtim;
}

static bool parse_output(char *output, CatalogSnapshot *snapshot)
{
    char *save = NULL;
    char *line;
    if (output == NULL || snapshot == NULL) return false;
    memset(snapshot, 0, sizeof *snapshot);
    for (line = strtok_r(output, "\n", &save); line != NULL;
         line = strtok_r(NULL, "\n", &save)) {
        char *first;
        char *second;
        char *third;
        size_t length = strlen(line);
        if (length > 0 && line[length - 1] == '\r') line[length - 1] = '\0';
        first = strchr(line, '\t');
        if (first == NULL) return false;
        *first++ = '\0';
        if (strcmp(line, "watch") == 0) {
            WatchSource *watch;
            if (strchr(first, '\t') != NULL || first[0] != '/' ||
                strlen(first) >= PATH_MAX ||
                snapshot->watch_count >= WATCH_MAX)
                return false;
            watch = &snapshot->watches[snapshot->watch_count++];
            if (!copy_text(watch->path, sizeof watch->path, first))
                return false;
            snapshot_watch(watch);
            continue;
        }
        second = strchr(first, '\t');
        if (second == NULL || snapshot->count >= GAME_CATALOG_MAX)
            return false;
        *second++ = '\0';
        third = strchr(second, '\t');
        if (third == NULL) return false;
        *third++ = '\0';
        if (strchr(third, '\t') != NULL || !valid_id(first) ||
            !valid_label(second))
            return false;
        for (int i = 0; i < snapshot->count; i++)
            if (strcmp(snapshot->entries[i].id, first) == 0) return false;
        {
            GameCatalogEntry *entry = &snapshot->entries[snapshot->count++];
            if (strcmp(line, "game") == 0)
                entry->launch_kind = GAME_LAUNCH_KILIX95;
            else if (strcmp(line, "builtin") == 0)
                entry->launch_kind = GAME_LAUNCH_KILIX95_BUILTIN;
            else
                return false;
            if (!copy_text(entry->id, sizeof entry->id, first) ||
                !copy_text(entry->label, sizeof entry->label, second) ||
                !decode_icon(third, entry->icon_pixels))
                return false;
        }
    }
    return snapshot->count > 0 && snapshot->watch_count > 0;
}

static bool same_catalog(const CatalogSnapshot *left,
                         const CatalogSnapshot *right)
{
    if (left->count != right->count) return false;
    for (int i = 0; i < left->count; i++) {
        const GameCatalogEntry *a = &left->entries[i];
        const GameCatalogEntry *b = &right->entries[i];
        if (a->launch_kind != b->launch_kind || strcmp(a->id, b->id) != 0 ||
            strcmp(a->label, b->label) != 0 ||
            memcmp(a->icon_pixels, b->icon_pixels,
                   sizeof a->icon_pixels) != 0)
            return false;
    }
    return true;
}

static bool load_current(bool *changed)
{
    char output[OUTPUT_MAX];
    CatalogSnapshot next;
    if (!run_helper("list", kilix95_root, output, sizeof output)) {
        set_error("Kilix 95's game registry could not be read.");
        return false;
    }
    if (!parse_output(output, &next)) {
        set_error("Kilix 95 returned an invalid game registry.");
        return false;
    }
    if (changed != NULL) *changed = !available || !same_catalog(&current, &next);
    current = next;
    available = true;
    last_error[0] = '\0';
    return true;
}

static bool watch_changed(const WatchSource *watch)
{
    WatchSource next = *watch;
    snapshot_watch(&next);
    return next.exists != watch->exists || next.device != watch->device ||
           next.inode != watch->inode || next.size != watch->size ||
           next.modified.tv_sec != watch->modified.tv_sec ||
           next.modified.tv_nsec != watch->modified.tv_nsec;
}

bool game_catalog_init(const char *argv0)
{
    bool changed = false;
    memset(&current, 0, sizeof current);
    available = false;
    last_error[0] = '\0';
    next_poll_ms = monotonic_ms() + POLL_INTERVAL_MS;
    if (!locate_paths(argv0)) return false;
    return load_current(&changed);
}

void game_catalog_shutdown(void)
{
    memset(&current, 0, sizeof current);
    kilix95_root[0] = '\0';
    helper_path[0] = '\0';
    last_error[0] = '\0';
    available = false;
    next_poll_ms = 0;
}

bool game_catalog_poll(void)
{
    int64_t now = monotonic_ms();
    bool changed = false;
    bool dirty = !available;
    if (now < next_poll_ms) return false;
    next_poll_ms = now + POLL_INTERVAL_MS;
    if (!dirty)
        for (int i = 0; i < current.watch_count; i++)
            if (watch_changed(&current.watches[i])) {
                dirty = true;
                break;
            }
    if (!dirty) return false;
    if ((kilix95_root[0] == '\0' || helper_path[0] == '\0') &&
        !locate_paths(NULL))
        return false;
    return load_current(&changed) && changed;
}

bool game_catalog_available(void) { return available; }
int game_catalog_count(void) { return current.count; }

const GameCatalogEntry *game_catalog_entry(int index)
{
    return index >= 0 && index < current.count ? &current.entries[index] : NULL;
}

const char *game_catalog_kilix95_root(void) { return kilix95_root; }
const char *game_catalog_helper(void) { return helper_path; }
const char *game_catalog_error(void) { return last_error; }

bool game_catalog_selftest(const char *argv0)
{
    char output[OUTPUT_MAX];
    CatalogSnapshot fixture;
    char saved_root[PATH_MAX];
    char saved_helper[PATH_MAX];
    bool saved_available = available;
    bool ok;

    (void)copy_text(saved_root, sizeof saved_root, kilix95_root);
    (void)copy_text(saved_helper, sizeof saved_helper, helper_path);
    if (!locate_helper_only(argv0)) return false;
    ok = run_helper("fixture", NULL, output, sizeof output) &&
         parse_output(output, &fixture) && fixture.count == 4 &&
         fixture.entries[0].launch_kind == GAME_LAUNCH_KILIX95_BUILTIN &&
         strcmp(fixture.entries[0].id, "mines") == 0 &&
         fixture.entries[0].icon_pixels[0] == 1 &&
         fixture.entries[0].icon_pixels[1] == 0 &&
         fixture.entries[2].launch_kind == GAME_LAUNCH_KILIX95 &&
         strcmp(fixture.entries[3].label, "Kilix Pong") == 0;
    (void)copy_text(kilix95_root, sizeof kilix95_root, saved_root);
    (void)copy_text(helper_path, sizeof helper_path, saved_helper);
    available = saved_available;
    return ok;
}
