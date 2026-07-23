/* input.h — merged key + mouse event queue in 480x320 canvas coordinates.
 *
 * kilix-cap. FROZEN CONTRACT. Owning .c: src/input.c (LOC ~300).
 * Spec: docs/ENGINE.md §3 (dual-feed SGR mouse design).
 *
 * Adapted from c-com-ufo-defense with the canvas retargeted; the scanner,
 * latch, and queue logic are unchanged because they were already correct.
 *
 * Plumbing: term.c owns the fd read loop and feeds BOTH parsers — the
 * vendored kitty keyboard parser (which provably ignores SGR mouse CSIs)
 * and this module's SGR mouse scanner (which ignores everything else).
 * term.c then translates keyboard events into input_push_key(). UI code
 * consumes only input_next()/term_key_down(). This header includes no
 * vendor headers; only src/input.c and src/term.c touch kitty_* APIs.
 *
 * Coarse-input note (docs/ENGINE.md §3.1): terminals that ignore SGR-pixel
 * mode (1016) report cell-granular positions, so pointing precision is
 * +/- half a cell. Conventional controls retain 32x32 canvas-pixel targets.
 * Physical room objects deliberately use only their painted silhouettes, so
 * they are kept visually large enough to point at without target dilation.
 */
#ifndef KILIX_CAP_INPUT_H
#define KILIX_CAP_INPUT_H

#include "types.h"

/* ---- Event model (docs/ENGINE.md §6.6, verbatim) ---- */
typedef enum input_kind {
    IN_NONE = 0,
    IN_KEY_DOWN, IN_KEY_REPEAT, IN_KEY_UP,   /* key = KEY_x or unicode, mods */
    IN_MOUSE_MOVE,                           /* mx,my updated; button=held|3 */
    IN_MOUSE_DOWN, IN_MOUSE_UP,              /* button 0=L 1=M 2=R           */
    IN_MOUSE_WHEEL,                          /* wheel = +1 up / -1 down      */
    IN_MOUSE_LEAVE                           /* pointer left the window      */
} input_kind;

typedef struct input_event {
    input_kind kind;
    uint32_t   key;      /* kitty key value (unicode scalar or KEY_* below) */
    uint32_t   mods;     /* MOD_* bitset (keys); shift/alt/ctrl (mouse)     */
    uint8_t    button;
    int8_t     wheel;
    int16_t    mx, my;   /* 480x320 canvas coords, clamped; valid on mouse evs */
    bool       in_view;  /* false when clamped from outside the viewport    */
} input_event;

/* ---- Key/mod constants ----
 * Values mirror the vendored kitty_keyboard.h canonical numbers (PUA plane);
 * src/input.c _Static_asserts them against the vendor header. Ordinary keys
 * are lowercase Unicode scalars ('a', '1', '+'). Bindings should match via
 * ev->key so the base-layout fallback handled in term.c keeps non-QWERTY
 * working.
 */
enum {
    KEY_ESCAPE    = 0xe000,
    KEY_ENTER     = 0xe001,
    KEY_TAB       = 0xe002,
    KEY_BACKSPACE = 0xe003,
    KEY_LEFT      = 0xe006,
    KEY_RIGHT     = 0xe007,
    KEY_UP        = 0xe008,
    KEY_DOWN      = 0xe009,
    KEY_PAGE_UP   = 0xe00a,
    KEY_PAGE_DOWN = 0xe00b,
    KEY_HOME      = 0xe00c,
    KEY_END       = 0xe00d
};
enum {
    MOD_SHIFT = 1u << 0,
    MOD_ALT   = 1u << 1,
    MOD_CTRL  = 1u << 2
};

/* ---- Consumer API (game code / main loop) ---- */
bool input_next(input_event *ev);            /* pop merged FIFO; false=empty */
void input_mouse_pos(int *gx, int *gy, bool *in_view);  /* latest, polled    */

/* ---- Producer API (called by term.c only) ---- */

/* Reset queues, scanner, pointer position, and the per-session pixel latch.
 * term.c calls this before every terminal-session start; headless parser tests
 * use it to make fixtures independent. Geometry is reset to safe 1px cells. */
void input_reset(void);

/* Feed raw terminal bytes to the SGR mouse scanner (resumable state machine,
 * docs/ENGINE.md §6.4: CSI '<' params 'M'/'m'; cb bits: 4 shift, 8 alt,
 * 16 ctrl, 32 motion, 64+dir wheel, 256 leave; pixel-vs-cell latch: start in
 * CELL, latch PIXEL permanently when x > cols || y > rows). */
void input_mouse_feed(const uint8_t *buf, size_t n);

/* Push one translated keyboard event (action: 1=press 2=repeat 3=release). */
void input_push_key(uint32_t key, uint32_t mods, int action);

/* Geometry mirror for mouse coordinate mapping (docs/ENGINE.md §6.5).
 * term.c calls this after start and after every resize. origin_col/row are
 * 1-based cell coords of the image top-left; scale/off_x/off_y are the
 * integer-upscale placement of the 480x320 canvas inside the fb. */
void input_set_geometry(int term_cols, int term_rows,
                        int cell_w, int cell_h,
                        int origin_col, int origin_row,
                        int scale, int off_x, int off_y);

/* Mouse event ring is 32 entries, overwrite-oldest; consecutive
 * IN_MOUSE_MOVE events are coalesced (one event per swipe per pump). */
enum { INPUT_MOUSE_RING = 32 };

#endif /* KILIX_CAP_INPUT_H */
