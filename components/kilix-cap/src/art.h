/* art.h — generated environment-art loading and composition. */
#ifndef KILIX_CAP_ART_H
#define KILIX_CAP_ART_H

#include "canvas.h"
#include "icon.h"

/* Loads the committed, executable-relative workroom asset once. Missing art
 * is non-fatal so developer builds can still display a procedural fallback. */
bool art_init(const char *argv0, bool verbose);
void art_shutdown(void);
bool art_ready(void);

/* Copies one of the 480x256 environment plates into the content zone.
 * Architectural doors belong to their own generated room editions; the Desk
 * item atlas is then composited as a separate masked layer. */
bool art_draw_workdesk(Canvas *canvas);
bool art_draw_hallway(Canvas *canvas);
bool art_draw_storeroom(Canvas *canvas);
bool art_draw_server_room(Canvas *canvas);
bool art_draw_game_room(Canvas *canvas);
bool art_draw_library(Canvas *canvas);
bool art_draw_cleaning_room(Canvas *canvas);
bool art_draw_balcony(Canvas *canvas);
bool art_draw_workdesk_items(Canvas *canvas);

/* Nine generated game-media variants: CD cases (0..2), 3.5-inch floppies
 * (3..5), and manuals/books (6..8). The same alpha is used for composition
 * and exact-object picking after arbitrary room-layout scaling. */
enum { ART_GAME_MEDIA_VARIANTS = 9 };
bool art_draw_game_media(Canvas *canvas, int variant, int x, int y,
                         int w, int h, bool pressed);
bool art_game_media_hit(int variant, int x, int y, int w, int h,
                        int px, int py);

/* Generated Desk props use a semantic mask separate from their environment.
 * Bounds are returned in full 480x320 canvas coordinates. */
bool art_workdesk_item_bounds(IconId icon, int *x, int *y, int *w, int *h);
bool art_workdesk_item_hit(IconId icon, int x, int y, int w, int h,
                           int px, int py);

#endif /* KILIX_CAP_ART_H */
