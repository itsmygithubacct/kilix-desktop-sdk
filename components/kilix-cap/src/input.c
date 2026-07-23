/* input.c — SGR mouse scanner, merged key+mouse event queue, geometry map.
 *
 * kilix-cap. Contract: src/input.h. Spec: docs/ENGINE.md §3.
 * term.c owns the fd and feeds input_mouse_feed() raw bytes alongside the
 * vendored keyboard parser; translated key events arrive via
 * input_push_key(). Everything here is plain state — no reads, no vendor
 * calls beyond the KEY/MOD mirror asserts below.
 */
#include "input.h"

#include "kitty_keyboard.h"

#include <string.h>

/* ---- KEY/MOD mirror (input.h promises these track the vendor header);
 * casts silence -Wenum-compare across the two anonymous enums. ---- */
#define MIRROR(a, b) _Static_assert((uint32_t)(a) == (uint32_t)(b), #a " drifted")
MIRROR(KEY_ESCAPE, KITTYKB_KEY_ESCAPE);
MIRROR(KEY_ENTER, KITTYKB_KEY_ENTER);
MIRROR(KEY_TAB, KITTYKB_KEY_TAB);
MIRROR(KEY_BACKSPACE, KITTYKB_KEY_BACKSPACE);
MIRROR(KEY_LEFT, KITTYKB_KEY_LEFT);
MIRROR(KEY_RIGHT, KITTYKB_KEY_RIGHT);
MIRROR(KEY_UP, KITTYKB_KEY_UP);
MIRROR(KEY_DOWN, KITTYKB_KEY_DOWN);
MIRROR(KEY_PAGE_UP, KITTYKB_KEY_PAGE_UP);
MIRROR(KEY_PAGE_DOWN, KITTYKB_KEY_PAGE_DOWN);
MIRROR(KEY_HOME, KITTYKB_KEY_HOME);
MIRROR(KEY_END, KITTYKB_KEY_END);
MIRROR(MOD_SHIFT, KITTYKB_MOD_SHIFT);
MIRROR(MOD_ALT, KITTYKB_MOD_ALT);
MIRROR(MOD_CTRL, KITTYKB_MOD_CTRL);
#undef MIRROR

/* ---- Queues: key FIFO + mouse ring, merged by sequence stamp ---- */
enum { KEY_RING = 64 };

typedef struct Queued {
    input_event ev;
    uint32_t seq;
} Queued;

/* ---- SGR scanner states (docs/ENGINE.md §3.3) ---- */
enum { SC_GROUND, SC_ESC, SC_CSI, SC_SKIP, SC_PARAMS };

static struct {
    Queued key[KEY_RING];
    int key_head, key_count;
    Queued mouse[INPUT_MOUSE_RING];
    int mouse_head, mouse_count;
    uint32_t seq;

    int sc_state;
    uint32_t param[3];
    int param_idx;
    bool param_digit[3];

    /* geometry mirror (input_set_geometry) */
    int cols, rows;
    int cell_w, cell_h;
    int origin_col, origin_row;
    int scale, off_x, off_y;
    bool pixel_latched;          /* CELL until proven PIXEL, then forever */

    int16_t last_mx, last_my;
    bool last_in_view;
} in;

static void key_push(const input_event *ev)
{
    Queued *slot;
    if (in.key_count == KEY_RING) {              /* overwrite-oldest */
        in.key_head = (in.key_head + 1) % KEY_RING;
        in.key_count--;
    }
    slot = &in.key[(in.key_head + in.key_count) % KEY_RING];
    slot->ev = *ev;
    slot->seq = in.seq++;
    in.key_count++;
}

static void mouse_push(const input_event *ev)
{
    Queued *slot;
    if (ev->kind == IN_MOUSE_MOVE && in.mouse_count > 0) {
        Queued *newest = &in.mouse[(in.mouse_head + in.mouse_count - 1) %
                                   INPUT_MOUSE_RING];
        /* Coalesce only when this really is the globally adjacent event.
         * A key queued between two moves must keep its place in the merged
         * stream, even though it lives in the other ring. */
        if (newest->ev.kind == IN_MOUSE_MOVE && newest->seq + 1u == in.seq) {
            newest->ev = *ev;
            return;
        }
    }
    if (in.mouse_count == INPUT_MOUSE_RING) {    /* overwrite-oldest */
        in.mouse_head = (in.mouse_head + 1) % INPUT_MOUSE_RING;
        in.mouse_count--;
    }
    slot = &in.mouse[(in.mouse_head + in.mouse_count) % INPUT_MOUSE_RING];
    slot->ev = *ev;
    slot->seq = in.seq++;
    in.mouse_count++;
}

/* Terminal coords -> 480x320 (docs/ENGINE.md §3.4). in_view is decided in
 * framebuffer pixels before clamping so edge events survive as clamped
 * positions (edge-of-screen scrolling wants them). */
static void map_coords(uint32_t x, uint32_t y, int *gx, int *gy, bool *view)
{
    int fx, fy, sc = in.scale > 0 ? in.scale : 1;
    if (in.pixel_latched) {
        /* SGR pixel reports are one-based just like cell reports.  Convert
         * to a zero-based terminal pixel before removing the image origin;
         * otherwise every scale > 1 shifts the logical pixel boundaries and
         * rejects the framebuffer's last physical row and column. */
        fx = (int)x - 1 - (in.origin_col - 1) * in.cell_w;
        fy = (int)y - 1 - (in.origin_row - 1) * in.cell_h;
    } else {
        fx = ((int)x - in.origin_col) * in.cell_w + in.cell_w / 2;
        fy = ((int)y - in.origin_row) * in.cell_h + in.cell_h / 2;
    }
    *view = fx >= in.off_x && fx < in.off_x + CANVAS_W * sc &&
            fy >= in.off_y && fy < in.off_y + CANVAS_H * sc;
    *gx = iclampi((fx - in.off_x) / sc, 0, CANVAS_W - 1);
    *gy = iclampi((fy - in.off_y) / sc, 0, CANVAS_H - 1);
}

/* Complete SGR report: params = {cb, x, y}, final 'M' (press/motion) or
 * 'm' (release). cb bits: 4 shift, 8 alt, 16 ctrl, 32 motion, 64+dir wheel,
 * 256 leave (pixel protocol only). */
static void mouse_emit(bool final_press)
{
    uint32_t cb = in.param[0], x = in.param[1], y = in.param[2];
    input_event ev = {0};
    int gx, gy;
    bool view;

    if (!in.pixel_latched && in.cols > 0 &&
        (x > (uint32_t)in.cols || y > (uint32_t)in.rows))
        in.pixel_latched = true;

    ev.mods = ((cb & 4u) ? MOD_SHIFT : 0u) |
              ((cb & 8u) ? MOD_ALT : 0u) |
              ((cb & 16u) ? MOD_CTRL : 0u);

    if (cb & 256u) {
        ev.kind = IN_MOUSE_LEAVE;
        ev.mx = in.last_mx;
        ev.my = in.last_my;
        ev.in_view = false;
        in.last_in_view = false;
        mouse_push(&ev);
        return;
    }

    /* The event model deliberately exposes only the three conventional
     * buttons. XTerm's extra-button bank uses bit 7; aliasing those reports
     * through cb&3 would turn a side button into a primary click. */
    if (cb & 128u) return;
    if (x == 0 || y == 0) return;       /* SGR coordinates are 1-based */

    map_coords(x, y, &gx, &gy, &view);
    in.last_mx = (int16_t)gx;
    in.last_my = (int16_t)gy;
    in.last_in_view = view;
    ev.mx = (int16_t)gx;
    ev.my = (int16_t)gy;
    ev.in_view = view;

    if (cb & 64u) {
        if ((cb & 3u) > 1u) return;     /* horizontal wheels are unsupported */
        ev.kind = IN_MOUSE_WHEEL;
        ev.wheel = (cb & 3u) == 0 ? 1 : -1;
    } else if (cb & 32u) {
        ev.kind = IN_MOUSE_MOVE;                 /* button 3 = hover */
        ev.button = (uint8_t)(cb & 3u);
    } else {
        if (final_press && (cb & 3u) == 3u) return;
        ev.kind = final_press ? IN_MOUSE_DOWN : IN_MOUSE_UP;
        ev.button = (uint8_t)(cb & 3u);
    }
    mouse_push(&ev);
}

void input_mouse_feed(const uint8_t *buf, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        uint8_t b = buf[i];
        switch (in.sc_state) {
        case SC_GROUND:
            if (b == 0x1b) in.sc_state = SC_ESC;
            break;
        case SC_ESC:
            if (b == '[') in.sc_state = SC_CSI;
            else if (b != 0x1b) in.sc_state = SC_GROUND;
            break;
        case SC_CSI:
            if (b == '<') {
                in.param[0] = in.param[1] = in.param[2] = 0;
                in.param_digit[0] = in.param_digit[1] =
                    in.param_digit[2] = false;
                in.param_idx = 0;
                in.sc_state = SC_PARAMS;
            } else if (b == 0x1b) {
                in.sc_state = SC_ESC;
            } else if (b >= 0x20 && b <= 0x3f) {
                in.sc_state = SC_SKIP;
            } else {
                in.sc_state = SC_GROUND;
            }
            break;
        case SC_SKIP:
            if (b >= 0x40 && b <= 0x7e) in.sc_state = SC_GROUND;
            else if (b == 0x1b) in.sc_state = SC_ESC;
            break;
        case SC_PARAMS:
            if (b >= '0' && b <= '9') {
                uint32_t v = in.param[in.param_idx] * 10u + (uint32_t)(b - '0');
                in.param[in.param_idx] = v > 65535u ? 65535u : v;
                in.param_digit[in.param_idx] = true;
            } else if (b == ';') {
                if (!in.param_digit[in.param_idx] || in.param_idx >= 2) {
                    in.sc_state = SC_SKIP;
                } else in.param_idx++;
            } else if (b == 'M') {
                if (in.param_idx == 2 && in.param_digit[0] &&
                    in.param_digit[1] && in.param_digit[2])
                    mouse_emit(true);
                in.sc_state = SC_GROUND;
            } else if (b == 'm') {
                if (in.param_idx == 2 && in.param_digit[0] &&
                    in.param_digit[1] && in.param_digit[2])
                    mouse_emit(false);
                in.sc_state = SC_GROUND;
            } else if (b == 0x1b) {
                in.sc_state = SC_ESC;            /* malformed, drop */
            } else {
                in.sc_state = SC_GROUND;         /* drop */
            }
            break;
        }
    }
}

void input_reset(void)
{
    memset(&in, 0, sizeof in);
    in.cell_w = 1;
    in.cell_h = 1;
    in.scale = 1;
}

void input_push_key(uint32_t key, uint32_t mods, int action)
{
    input_event ev = {0};
    ev.kind = action == 3 ? IN_KEY_UP :
              action == 2 ? IN_KEY_REPEAT : IN_KEY_DOWN;
    ev.key = key;
    ev.mods = mods;
    ev.mx = in.last_mx;
    ev.my = in.last_my;
    ev.in_view = in.last_in_view;
    key_push(&ev);
}

void input_set_geometry(int term_cols, int term_rows,
                        int cell_w, int cell_h,
                        int origin_col, int origin_row,
                        int scale, int off_x, int off_y)
{
    in.cols = term_cols;
    in.rows = term_rows;
    in.cell_w = cell_w > 0 ? cell_w : 1;
    in.cell_h = cell_h > 0 ? cell_h : 1;
    in.origin_col = origin_col;
    in.origin_row = origin_row;
    in.scale = scale;
    in.off_x = off_x;
    in.off_y = off_y;
    /* pixel_latched survives resizes: the protocol choice is per session */
}

bool input_next(input_event *ev)
{
    bool take_key;
    if (in.key_count == 0 && in.mouse_count == 0) return false;
    if (in.key_count > 0 && in.mouse_count > 0) {
        uint32_t diff = in.mouse[in.mouse_head].seq - in.key[in.key_head].seq;
        take_key = diff != 0 && diff < 0x80000000u;  /* key stamped first */
    } else {
        take_key = in.key_count > 0;
    }
    if (take_key) {
        *ev = in.key[in.key_head].ev;
        in.key_head = (in.key_head + 1) % KEY_RING;
        in.key_count--;
    } else {
        *ev = in.mouse[in.mouse_head].ev;
        in.mouse_head = (in.mouse_head + 1) % INPUT_MOUSE_RING;
        in.mouse_count--;
    }
    return true;
}

void input_mouse_pos(int *gx, int *gy, bool *in_view)
{
    if (gx) *gx = in.last_mx;
    if (gy) *gy = in.last_my;
    if (in_view) *in_view = in.last_in_view;
}
