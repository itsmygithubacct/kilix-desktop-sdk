/* game_icons.h — Kilix 95 game-icon payload helpers. */
#ifndef KILIX_CAP_GAME_ICONS_H
#define KILIX_CAP_GAME_ICONS_H

#include "game_catalog.h"

/* Keeps a valid live-catalog icon unchanged. Missing test/offline-fixture
 * pixels receive the matching bundled Kilix 95 icon, or a deterministic
 * generic game icon for an unknown future ID. */
void game_icon_ensure(const char *game_id,
                      uint8_t pixels[GAME_ICON_PIXELS]);

bool game_icon_valid(const uint8_t pixels[GAME_ICON_PIXELS]);

#endif /* KILIX_CAP_GAME_ICONS_H */
