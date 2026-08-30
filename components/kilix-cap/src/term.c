/* term.c — kitty terminal session adapter: lifecycle, integer upscale +
 * present, resize, dual-feed input read with the 25 ms lone-ESC timeout.
 *
 * kilix-cap. Contract: src/term.h. Spec: docs/ENGINE.md §§1,2,3,5.
 * Headless subcommands never call term_init; every
 * function here is a safe no-op on an unstarted session, so atexit
 * (term_shutdown) and the signal handlers main.c installs can always fire.
 */
#include "term.h"
#include "input.h"

#include "kitty_terminal_session.h"
#include "kitty_framebuffer_internal.h"

#include <errno.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

/* Mouse tracking (docs/ENGINE.md §3.1): 1003 any-event, 1006 SGR, 1016
 * SGR-pixels. Baked into the framebuffer enter/leave sequences so the
 * prebuilt emergency restore turns reporting off even on SIGSEGV. */
#define MOUSE_ON  "\x1b[?1003h\x1b[?1006h\x1b[?1016h"
#define MOUSE_OFF "\x1b[?1016l\x1b[?1006l\x1b[?1003l"

enum { ESC_TIMEOUT_MS = 25 };

static kittyts_session session;
static kittyts_options options;
static bool active;

static uint8_t *present_buf;         /* fb_w * fb_h * 4 RGBA, borders black */
static int fb_w, fb_h;
static int scale = 1, off_x, off_y;

static struct winsize last_ws;
static int64_t esc_since_ms = -1;

enum { MIN_PRESENT_SCALE = 1, CELL_SNAP_HEADROOM = 64 };

static int64_t now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static short poll_events(int fd)
{
    struct pollfd pfd;
    int r;
    pfd.fd = fd;
    pfd.events = POLLIN;
    pfd.revents = 0;
    do {
        r = poll(&pfd, 1u, 0);
    } while (r < 0 && errno == EINTR);
    return r > 0 ? pfd.revents : 0;
}

static bool poll_readable(int fd)
{
    return (poll_events(fd) & (POLLIN | POLLHUP)) != 0;
}

static bool alloc_present_buffer(int w, int h)
{
    free(present_buf);
    present_buf = calloc((size_t)w * (size_t)h, 4);  /* zero = black border */
    fb_w = w;
    fb_h = h;
    return present_buf != NULL;
}

/* scale = min(fbw/1440, fbh/960); the canvas is already authored at 3x,
 * so 1 is the floor and min bounds 1440x960 guarantee it; max
 * 2400x1600 caps it at 5 (docs/ENGINE.md §2). */
static void compute_placement(void)
{
    scale = imini(fb_w / CANVAS_W, fb_h / CANVAS_H);
    if (scale < 1) scale = 1;
    off_x = (fb_w - CANVAS_W * scale) / 2;
    off_y = (fb_h - CANVAS_H * scale) / 2;
}

/* Mirror the image placement into input.c (docs/ENGINE.md §3.4): rerun
 * the library's own geometry derivation on the live winsize; if it ever
 * disagrees with the session (never observed), re-center from the session's
 * cell metrics instead. */
static void mirror_geometry(void)
{
    struct winsize ws;
    kittyfb_geometry g;
    int cell_w, cell_h, origin_col, origin_row;

    memset(&ws, 0, sizeof ws);
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) != 0 || ws.ws_col == 0 ||
        ws.ws_row == 0) {
        ws.ws_col = 80;
        ws.ws_row = 24;
        ws.ws_xpixel = 0;
        ws.ws_ypixel = 0;
    }
    last_ws = ws;
    if (kittyfb_derive_geometry(ws.ws_col, ws.ws_row, ws.ws_xpixel,
                                ws.ws_ypixel, &options.framebuffer, &g) &&
        g.width == fb_w && g.height == fb_h) {
        cell_w = g.cell_width;
        cell_h = g.cell_height;
        origin_col = g.origin_column;
        origin_row = g.origin_row;
    } else {
        cell_w = kittyts_cell_width(&session);
        cell_h = kittyts_cell_height(&session);
        if (cell_w < 1) cell_w = 9;
        if (cell_h < 1) cell_h = 18;
        origin_col = imaxi(1, 1 + (ws.ws_col - fb_w / cell_w) / 2);
        origin_row = imaxi(1, 1 + (ws.ws_row - 1 - fb_h / cell_h) / 2);
    }
    input_set_geometry(ws.ws_col, ws.ws_row, cell_w, cell_h,
                       origin_col, origin_row, scale, off_x, off_y);
}

int term_init(void)
{
    input_reset();
    kittyts_session_init(&session);
    kittyts_options_init(&options);
    /* kitty-framebuffer snaps its clamp down to whole terminal cells. Leave
     * enough headroom that ordinary (and unusually large) cells cannot turn
     * the requested 2x minimum into a 1x canvas. */
    options.framebuffer.min_width =
        CANVAS_W * MIN_PRESENT_SCALE + CELL_SNAP_HEADROOM - 1;
    options.framebuffer.min_height =
        CANVAS_H * MIN_PRESENT_SCALE + CELL_SNAP_HEADROOM - 1;
    options.framebuffer.max_width = 2400;
    options.framebuffer.max_height = 1600;
    options.framebuffer.enter_sequence = MOUSE_ON;
    options.framebuffer.leave_sequence = MOUSE_OFF;
    if (getenv("KILIX_CAP_SKIP_PROBE"))
        options.framebuffer.probe_graphics = false;
    if (kittyts_start(&session, STDIN_FILENO, STDOUT_FILENO, &options) != 0)
        return -1;
    if (!alloc_present_buffer(kittyts_width(&session),
                              kittyts_height(&session))) {
        kittyts_stop(&session);
        errno = ENOMEM;
        return -1;
    }
    active = true;
    esc_since_ms = -1;
    compute_placement();
    mirror_geometry();
    return 0;
}

void term_shutdown(void)
{
    kittyts_stop(&session);      /* internally idempotent / no-op if unused */
    active = false;
    free(present_buf);
    present_buf = NULL;
}

void term_emergency_restore(void)
{
    /* Async-signal-safe: mouse off (leave sequence), kbd mode pop,
     * framebuffer restore. No locks, no frees. */
    kittyts_emergency_restore(&session);
}

/* One pass: 0xAARRGGBB -> RGBA bytes, replicated scale x scale
 * (docs/ENGINE.md §2; canvas alpha ignored, game canvas is opaque). */
static void upscale(const uint32_t *src)
{
    for (int y = 0; y < CANVAS_H; y++) {
        uint8_t *row0 = present_buf +
            ((size_t)(off_y + y * scale) * (size_t)fb_w + (size_t)off_x) * 4;
        uint8_t *p = row0;
        for (int x = 0; x < CANVAS_W; x++) {
            uint32_t c = src[y * CANVAS_W + x];
            uint8_t r = (uint8_t)(c >> 16);
            uint8_t g = (uint8_t)(c >> 8);
            uint8_t b = (uint8_t)c;
            for (int k = 0; k < scale; k++) {
                p[0] = r;
                p[1] = g;
                p[2] = b;
                p[3] = 255;
                p += 4;
            }
        }
        for (int k = 1; k < scale; k++)
            memcpy(row0 + (size_t)k * (size_t)fb_w * 4, row0,
                   (size_t)CANVAS_W * (size_t)scale * 4);
    }
}

bool term_present_canvas(const Canvas *c)
{
    if (!active || present_buf == NULL || c == NULL || c->px == NULL ||
        c->w != CANVAS_W || c->h != CANVAS_H)
        return false;
    upscale(c->px);
    return kittyts_present(&session, present_buf, fb_w, fb_h) &&
           !kittyfb_failed(&session.framebuffer);
}

bool term_check_resize(void)
{
    int nw, nh;
    struct winsize ws;

    if (!active) return false;
    if (kittyts_check_resize(&session, &nw, &nh)) {
        /* On alloc failure present_buf stays NULL and term_present_canvas
         * returns false, which exits the main loop. */
        (void)alloc_present_buffer(nw, nh);
        compute_placement();
        mirror_geometry();
        return true;
    }
    /* Centering-only change (cols/rows moved but the clamped fb size did
     * not): re-mirror so the mouse map stays exact. */
    memset(&ws, 0, sizeof ws);
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 &&
        (ws.ws_col != last_ws.ws_col || ws.ws_row != last_ws.ws_row ||
         ws.ws_xpixel != last_ws.ws_xpixel ||
         ws.ws_ypixel != last_ws.ws_ypixel))
        mirror_geometry();
    return false;
}

/* Non-QWERTY fallback (input.h): keep functional (PUA) and ASCII keys as-is;
 * for other layouts report the PC-101 base-layout key so bindings on
 * 'a'..'z' keep working. */
static uint32_t translate_key(const kittykb_event *ev)
{
    /* Kitty's produced-text and shifted-key fields carry layout-resolved
     * punctuation (Shift+1 -> '!').  Bindings still fall back to the base
     * key below, but text editors must receive what the user actually typed. */
    if (ev->action != KITTYKB_ACTION_RELEASE) {
        if (ev->text_length == 1 && ev->text[0] >= 32 && ev->text[0] <= 126)
            return ev->text[0];
        if ((ev->modifiers & KITTYKB_MOD_SHIFT) != 0 &&
            ev->shifted_key >= 32 && ev->shifted_key <= 126)
            return ev->shifted_key;
    }
    if (ev->key < 0x80 || (ev->key >= 0xe000 && ev->key <= 0xe0ff))
        return ev->key;
    return ev->base_layout_key != 0 ? ev->base_layout_key : ev->key;
}

bool term_translation_test(void)
{
    static const char shifted_one[] = "\x1b[49:33;2u";
    static const char shifted_a[] = "\x1b[97:65;2u";
    const struct {
        const char *bytes;
        size_t length;
        uint32_t expected;
    } cases[] = {
        {shifted_one, sizeof shifted_one - 1u, '!'},
        {shifted_a, sizeof shifted_a - 1u, 'A'}
    };

    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        kittykb_input input;
        kittykb_event event;
        kittykb_input_init(&input);
        kittykb_input_feed(&input, cases[i].bytes, cases[i].length);
        if (!kittykb_input_next(&input, &event) ||
            translate_key(&event) != cases[i].expected)
            return false;
    }
    return true;
}

static void drain_keys(void)
{
    kittykb_event kev;
    while (kittykb_input_next(&session.keyboard.input, &kev))
        input_push_key(translate_key(&kev), kev.modifiers, (int)kev.action);
}

int term_read_input(void)
{
    unsigned char buf[4096];
    bool read_any = false;

    if (!active) return 0;
    for (;;) {
        ssize_t n = read(STDIN_FILENO, buf, sizeof buf);
        if (n > 0) {
            read_any = true;
            /* Feed and drain one byte at a time so the two parsers stamp
             * completed events in raw-stream order. Feeding a whole buffer
             * to mouse before draining keyboard reverses key,mouse pairs. */
            for (ssize_t i = 0; i < n; i++) {
                kittykb_input_feed(&session.keyboard.input, &buf[i], 1u);
                input_mouse_feed(&buf[i], 1u);
                drain_keys();
            }
            if (!poll_readable(STDIN_FILENO)) break;     /* drained */
            continue;
        }
        if (n == 0) {
            /* Raw mode uses VMIN=0, so an empty read may be ordinary
             * no-input even with O_NONBLOCK. Only poll's terminal/error
             * flags distinguish a dead descriptor from that idle state. */
            if (poll_events(STDIN_FILENO) & (POLLHUP | POLLERR | POLLNVAL))
                return -1;
            break;
        }
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) return -1;
        break;
    }

    /* Lone-ESC disambiguation, kittykb_terminal_read semantics verbatim
     * (docs/ENGINE.md §3.2), 25 ms. */
    if (kittykb_input_has_pending_escape(&session.keyboard.input)) {
        int64_t now = now_ms();
        if (read_any || esc_since_ms < 0) {
            esc_since_ms = now;
        } else if (now - esc_since_ms >= ESC_TIMEOUT_MS) {
            kittykb_input_flush_escape(&session.keyboard.input);
            drain_keys();
            esc_since_ms = -1;
        }
    } else {
        esc_since_ms = -1;
    }
    return 0;
}

bool term_key_down(uint32_t key)
{
    return active && kittyts_key_down(&session, key);
}

bool term_has_release_events(void)
{
    return active && kittyts_has_release_events(&session);
}

int term_scale(void)
{
    return scale;
}

void term_offsets(int *out_x, int *out_y)
{
    if (out_x) *out_x = off_x;
    if (out_y) *out_y = off_y;
}
