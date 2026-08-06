/* types.h — canvas geometry, zone contract, integer helpers.
 *
 * kilix-cap. FROZEN CONTRACT. Owning .c: none (header-only).
 * Spec: docs/ENGINE.md §2; asset contract §2 (canvas and zone geometry).
 *
 * The canvas is the native Magic Cap panel geometry at 1:1 — 480x320, which
 * every shipping device (Sony Magic Link PIC-1000/PIC-2000, Motorola Envoy
 * 100) used. No design resampling is required or permitted.
 */
#ifndef KILIX_CAP_TYPES_H
#define KILIX_CAP_TYPES_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* The canvas is authored at 3x its original 480x320: every layout number
 * below and every asset is three times what it was, so the room plates are
 * sampled near their generated resolution instead of being replicated by
 * the presenter. CANVAS_SCALE exists to document that relationship and to
 * let the render fixtures state it; nothing derives coordinates from it at
 * runtime, because a layout that computed itself would be harder to read
 * than one that says where things are. */
enum { CANVAS_SCALE = 3 };

enum {
    CANVAS_W = 1440,
    CANVAS_H = 960,

    /* Three stacked zones; the split is a release contract. */
    NAMEBAR_Y    = 0,
    NAMEBAR_H    = 72,
    CONTENT_Y    = 72,
    CONTENT_H    = 768,
    CONTROLBAR_Y = 840,
    CONTROLBAR_H = 120
};

_Static_assert(CANVAS_W == 480 * CANVAS_SCALE &&
                   CANVAS_H == 320 * CANVAS_SCALE,
               "the canvas must stay an exact multiple of its original size");

_Static_assert(NAMEBAR_H + CONTENT_H + CONTROLBAR_H == CANVAS_H,
               "zone heights must sum to the canvas height");
_Static_assert(CONTENT_Y == NAMEBAR_Y + NAMEBAR_H,
               "content follows the name bar");
_Static_assert(CONTROLBAR_Y == CONTENT_Y + CONTENT_H,
               "control bar follows the content area");

/* Minimum conventional-control target (docs/ENGINE.md §3.1). Physical room
 * objects instead use exact visible-pixel targets with no expansion. */
enum { MIN_TARGET_W = 32 * CANVAS_SCALE,
       MIN_TARGET_H = 32 * CANVAS_SCALE };

static inline int imini(int a, int b) { return a < b ? a : b; }
static inline int imaxi(int a, int b) { return a > b ? a : b; }
static inline int iclampi(int v, int lo, int hi)
{
    return v < lo ? lo : (v > hi ? hi : v);
}

#endif /* KILIX_CAP_TYPES_H */
