/* icon.h — procedural object drawings.
 *
 * kilix-cap. FROZEN CONTRACT. Owning .c: src/icon.c (LOC ~300).
 * Spec: docs/ENGINE.md §4; asset contract §1 (procedural, not generated)
 * and §4 (drawing rules).
 *
 * Every icon is drawn in code from hard-edged primitives. Nothing here is
 * traced, sampled, or derived from any Magic Cap artwork — asset contract
 * §7.2 forbids using the original as a generation or authoring input, and
 * the original UI graphics are identifiable authored work by a living
 * designer.
 *
 * The house style follows the vendor's own art direction: objects should
 * "reflect and represent real-world objects, rather than depicting them
 * precisely", drawn toward medieval mosaic rather than post-Tintoretto
 * perspective. Each object carries its own suggestion of depth; there is
 * deliberately NO shared vanishing point between them.
 */
#ifndef KILIX_CAP_ICON_H
#define KILIX_CAP_ICON_H

#include "canvas.h"

typedef enum IconId {
    ICON_NONE = 0,
    ICON_CLOCK,
    ICON_INBOX,
    ICON_OUTBOX,
    ICON_POSTCARD,
    ICON_NAMECARD,
    ICON_NOTEBOOK,
    ICON_DATEBOOK,
    ICON_CARDFILE,
    ICON_CABINET,
    ICON_PHONE,
    ICON_STATIONERY,
    ICON_TOOLBOX,
    ICON_GLOBE,
    ICON_BOX,
    ICON_CRATE,
    ICON_TIN,
    ICON_KEYBOARD,
    ICON_COUNT
} IconId;

/* Draws the physical object directly over the current environment. Safe for
 * any rect; icons scale by choosing proportions rather than resampling. */
void icon_draw(Canvas *c, IconId id, int x, int y, int w, int h);

/* Pixel-exact semantic picking for procedural objects. A point responds only
 * when icon_draw() paints that local pixel; transparent bbox corners do not. */
bool icon_hit(IconId id, int x, int y, int w, int h, int px, int py);

#endif /* KILIX_CAP_ICON_H */
