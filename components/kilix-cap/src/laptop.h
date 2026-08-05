/* laptop.h — kilix laptop profiles: discovery, strict parsing, and kitty
 * session emission.
 *
 * kilix-cap. FROZEN CONTRACT. Owning .c: src/laptop.c (LOC ~600).
 * Spec: docs/LAPTOP.md.
 *
 * One convention shared by every kilix desktop that ships a laptop object:
 * profiles are plain KEY=value files named <id>.profile in
 * ~/.local/gpu_terminal/laptop/ (override: KILIX_LAPTOP_PROFILES, an
 * absolute directory). A profile either names another desktop provider to
 * open, or describes one kilix terminal session — its pane layout, each
 * pane's working directory or ssh destination, and each pane's command.
 * Data can never smuggle shell text into a launch: values are validated
 * here, panes become lines of a kitty --session file, and the launch argv
 * is always a fixed vector.
 */
#ifndef KILIX_CAP_LAPTOP_H
#define KILIX_CAP_LAPTOP_H

#include "types.h"

enum {
    LAPTOP_PROFILES_MAX = 16,
    LAPTOP_ID_MAX = 40,     /* file stem, [A-Za-z0-9._-], no leading dot */
    LAPTOP_NAME_MAX = 48,   /* display name shown by the chooser */
    LAPTOP_PANES_MAX = 8,
    LAPTOP_VALUE_MAX = 200, /* any single cwd/ssh/cmd value */
    LAPTOP_DESKTOP_MAX = 12,
    LAPTOP_ERROR_MAX = 96
};

typedef struct LaptopPane {
    char title[LAPTOP_NAME_MAX]; /* optional; empty = default */
    char cwd[LAPTOP_VALUE_MAX];  /* local dir, or remote dir with ssh= */
    char ssh[LAPTOP_VALUE_MAX];  /* [user@]host destination, or empty */
    char cmd[LAPTOP_VALUE_MAX];  /* command line, or empty = a shell */
} LaptopPane;

typedef struct LaptopProfile {
    char id[LAPTOP_ID_MAX];
    char name[LAPTOP_NAME_MAX];
    char desktop[LAPTOP_DESKTOP_MAX]; /* provider word, or empty */
    bool tabs;                        /* layout=tabs; default splits */
    int pane_count;
    LaptopPane panes[LAPTOP_PANES_MAX];
} LaptopProfile;

typedef struct LaptopList {
    int count;
    char ids[LAPTOP_PROFILES_MAX][LAPTOP_ID_MAX];
} LaptopList;

/* The shared profile directory. False when no home is resolvable or the
 * KILIX_LAPTOP_PROFILES override is not an absolute path. */
bool laptop_directory(char *path, size_t size);

/* Sorted profile ids. A missing directory is created once and seeded with
 * the bundled examples from seed_directory (NULL skips seeding); an
 * existing directory — even an emptied one — is never reseeded, because
 * deleting every profile is a valid configuration. Returns the count, or
 * -1 when the directory cannot be resolved or read. */
int laptop_scan(const char *seed_directory, LaptopList *list);

/* Strict parse of <directory>/<id>.profile. On failure the profile is
 * zeroed and error holds one short user-facing sentence. */
bool laptop_load(const char *id, LaptopProfile *profile,
                 char *error, size_t error_size);

/* Writes the kitty --session file describing a pane profile, 0600, via a
 * same-directory temp file and rename so a concurrent reader never sees a
 * half-written session. Refuses desktop profiles (nothing to emit). */
bool laptop_write_session(const LaptopProfile *profile, const char *path,
                          char *error, size_t error_size);

/* Fills argv words after "kilix" for a desktop profile ("cap" -> {"cap"};
 * "95" -> {"desktop", "95"}). Returns the word count, 0 for pane
 * profiles. */
size_t laptop_desktop_arguments(const LaptopProfile *profile,
                                const char *arguments[2]);

/* Headless self-checks over a private temp directory. */
bool laptop_selftest(void);

#endif /* KILIX_CAP_LAPTOP_H */
