/* game_catalog.h — live, read-only view of the Kilix 95 Games menu. */
#ifndef KILIX_CAP_GAME_CATALOG_H
#define KILIX_CAP_GAME_CATALOG_H

#include <stdbool.h>
#include <stdint.h>

enum {
    GAME_CATALOG_MAX = 30,
    GAME_ID_MAX = 63,
    GAME_LABEL_MAX = 95,
    GAME_ICON_SIDE = 16,
    GAME_ICON_PIXELS = GAME_ICON_SIDE * GAME_ICON_SIDE
};

typedef enum GameLaunchKind {
    GAME_LAUNCH_KILIX95 = 0,
    GAME_LAUNCH_KILIX95_BUILTIN
} GameLaunchKind;

typedef struct GameCatalogEntry {
    char id[GAME_ID_MAX + 1];
    char label[GAME_LABEL_MAX + 1];
    GameLaunchKind launch_kind;
    /* Exact palette indices exported from Kilix 95's original icon set.
     * Zero is transparent; values 1..14 select its fixed RGB palette. */
    uint8_t icon_pixels[GAME_ICON_PIXELS];
} GameCatalogEntry;

/* Discovery is read-only: the helper gives Kilix 95 a temporary storage root
 * while importing its registry, so merely opening the Game Room cannot create
 * or alter Kilix 95's user configuration. */
bool game_catalog_init(const char *argv0);
void game_catalog_shutdown(void);

/* Cheap one-second source polling. Returns true only when a newly validated
 * catalog differs from the currently exposed list. */
bool game_catalog_poll(void);

bool                    game_catalog_available(void);
int                     game_catalog_count(void);
const GameCatalogEntry *game_catalog_entry(int index);
const char             *game_catalog_kilix95_root(void);
const char             *game_catalog_helper(void);
const char             *game_catalog_error(void);

/* Uses the bundled helper's deterministic fixture, never the live catalog. */
bool game_catalog_selftest(const char *argv0);

#endif /* KILIX_CAP_GAME_CATALOG_H */
