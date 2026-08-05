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

/* Four generated small-prop variants: the Storeroom's storage box (0),
 * wooden crate (1), and tin canister (2), plus the Study laptop (3). The
 * pair mansion-items.ppm / mansion-items-mask.ppm is an OPTIONAL add-on to
 * the mandatory bundle: a tree without it still loads every plate and the
 * props keep their procedural drawings, so review-pending art degrades
 * gracefully. Hash-pinned render fixtures exclude it (see
 * art_set_extra_items_enabled), keeping their digests identical whether or
 * not the optional pair is present. */
enum { ART_MANSION_ITEM_VARIANTS = 4 };
enum {
    ART_MANSION_ITEM_BOX = 0,
    ART_MANSION_ITEM_CRATE = 1,
    ART_MANSION_ITEM_TIN = 2,
    ART_MANSION_ITEM_LAPTOP = 3
};
bool art_mansion_items_ready(void);
void art_set_extra_items_enabled(bool enabled);
bool art_draw_mansion_item(Canvas *canvas, int variant, int x, int y,
                           int w, int h, bool pressed);
bool art_mansion_item_hit(int variant, int x, int y, int w, int h,
                          int px, int py);

/* Two generated lid frames animate the Study laptop: fully closed (0) and
 * half-open (1); the fully open frame stays ART_MANSION_ITEM_LAPTOP. The
 * pair laptop-lid.ppm / laptop-lid-mask.ppm is a SECOND optional add-on
 * following the mansion-items rules exactly — both-or-neither, validated
 * on load, excluded from hash-pinned render fixtures via
 * art_set_extra_items_enabled — and it only engages when the small-prop
 * atlas whose open laptop it animates is itself present, so the lid never
 * mixes generated frames with the procedural drawing. The procedural
 * closed/ajar icons remain the complete fallback. The four mansion-items
 * cells are untouched by this extension. */
enum { ART_LAPTOP_LID_FRAMES = 2 };
enum { ART_LAPTOP_LID_CLOSED = 0, ART_LAPTOP_LID_AJAR = 1 };
bool art_laptop_lid_ready(void);
bool art_draw_laptop_lid(Canvas *canvas, int frame, int x, int y,
                         int w, int h, bool pressed);
bool art_laptop_lid_hit(int frame, int x, int y, int w, int h,
                        int px, int py);

#endif /* KILIX_CAP_ART_H */
