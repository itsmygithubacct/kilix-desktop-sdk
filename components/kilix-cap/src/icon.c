/* icon.c — procedural object drawings. Contract: src/icon.h.
 *
 * Each icon reads its proportions from the box it is given rather than
 * being resampled, so the same code serves a 104x32 desk object and a
 * 44x22 shelf item.
 */
#include "icon.h"

#include "draw.h"

static int iabs(int v) { return v < 0 ? -v : v; }

/* A vertical arrow whose tip is at (cx, tip). */
static void arrow_v(Canvas *c, int cx, int tail, int tip, uint32_t rgb)
{
    int dir = tip > tail ? 1 : -1;
    int barb = 4;
    draw_rect(c, cx - 1, imini(tail, tip), 2, iabs(tip - tail) + 1, rgb);
    draw_line_hard(c, cx, tip, cx - barb, tip - barb * dir, rgb);
    draw_line_hard(c, cx, tip, cx + barb, tip - barb * dir, rgb);
}

/* An open tray, drawn as three thick sides. */
static void tray(Canvas *c, int x, int y, int w, int h, uint32_t rgb)
{
    draw_rect(c, x, y + h - 3, w, 3, rgb);
    draw_rect(c, x, y, 3, h, rgb);
    draw_rect(c, x + w - 3, y, 3, h, rgb);
}

static void icon_clock(Canvas *c, int x, int y, int w, int h)
{
    int r = imini(w, h) / 2 - 1;
    int cx = x + w / 2, cy = y + h / 2;
    if (r < 4) return;
    draw_ring_hard(c, cx, cy, r, r - 2, MC_BLACK);
    draw_line_hard(c, cx, cy, cx, cy - r + 4, MC_BLACK);
    draw_line_hard(c, cx, cy, cx + r - 5, cy + 2, MC_BLACK);
    draw_disc(c, cx, cy, 1, MC_BLACK);
}

static void icon_tray(Canvas *c, int x, int y, int w, int h, bool incoming)
{
    int tw = w * 3 / 4, th = h / 2;
    int tx = x + (w - tw) / 2, ty = y + h - th;
    int cx = x + w / 2;
    if (tw < 8 || th < 5) return;
    tray(c, tx, ty, tw, th, MC_BLACK);
    if (incoming) arrow_v(c, cx, y + 1, ty - 3, MC_BLACK);
    else          arrow_v(c, cx, ty - 3, y + 1, MC_BLACK);
}

static void icon_postcard(Canvas *c, int x, int y, int w, int h)
{
    int pw = w * 4 / 5, ph = h * 4 / 5;
    int px = x + (w - pw) / 2, py = y + (h - ph) / 2;
    if (pw < 12 || ph < 10) return;
    draw_rect(c, px, py, pw, ph, MC_WHITE);
    draw_frame(c, px, py, pw, ph, 2, MC_BLACK);
    draw_rect(c, px + pw - 12, py + 3, 8, 6, MC_BLACK);   /* the stamp */
    for (int i = 0; i < 3; i++)
        draw_rect(c, px + 4, py + 4 + i * 4, pw / 2, 1, MC_BLACK);
}

static void icon_namecard(Canvas *c, int x, int y, int w, int h)
{
    int pw = w * 4 / 5, ph = h * 4 / 5;
    int px = x + (w - pw) / 2, py = y + (h - ph) / 2;
    if (pw < 14 || ph < 10) return;
    draw_rect(c, px, py, pw, ph, MC_WHITE);
    draw_frame(c, px, py, pw, ph, 2, MC_BLACK);
    draw_disc(c, px + 9, py + ph / 2 - 2, 3, MC_BLACK);          /* head */
    draw_rect(c, px + 5, py + ph / 2 + 2, 9, 4, MC_BLACK);       /* body */
    for (int i = 0; i < 2; i++)
        draw_rect(c, px + 18, py + 5 + i * 5, pw - 24, 2, MC_DARK);
}

static void icon_notebook(Canvas *c, int x, int y, int w, int h)
{
    int pw = w * 3 / 4, ph = h * 4 / 5;
    int px = x + (w - pw) / 2, py = y + (h - ph) / 2;
    if (pw < 12 || ph < 12) return;
    draw_rect(c, px, py, pw, ph, MC_WHITE);
    draw_frame(c, px, py, pw, ph, 2, MC_BLACK);
    for (int i = 0; i < 4; i++)                                  /* spiral */
        draw_disc(c, px + 5 + i * (pw - 10) / 3, py, 2, MC_BLACK);
    for (int i = 0; i < 3; i++)
        draw_rect(c, px + 5, py + 8 + i * 5, pw - 10, 1, MC_DARK);
}

static void icon_datebook(Canvas *c, int x, int y, int w, int h)
{
    int pw = w * 3 / 4, ph = h * 4 / 5;
    int px = x + (w - pw) / 2, py = y + (h - ph) / 2;
    if (pw < 14 || ph < 12) return;
    draw_rect(c, px, py, pw, ph, MC_WHITE);
    draw_rect(c, px, py, pw, 6, MC_BLACK);                       /* band  */
    draw_frame(c, px, py, pw, ph, 2, MC_BLACK);
    for (int r = 0; r < 2; r++)
        for (int col = 0; col < 4; col++)
            draw_rect(c, px + 5 + col * (pw - 10) / 4,
                      py + 10 + r * 6, 3, 3, MC_DARK);
}

static void icon_cardfile(Canvas *c, int x, int y, int w, int h)
{
    int bw = w * 4 / 5, bh = h / 2;
    int bx = x + (w - bw) / 2, by = y + h - bh;
    if (bw < 14 || bh < 6) return;
    for (int i = 0; i < 4; i++) {                                /* cards */
        int ch = bh / 2 + (i % 2) * 4;
        draw_rect(c, bx + 4 + i * (bw - 8) / 4, by - ch, (bw - 8) / 4 - 2,
                  ch, MC_WHITE);
        draw_frame(c, bx + 4 + i * (bw - 8) / 4, by - ch, (bw - 8) / 4 - 2,
                   ch, 1, MC_BLACK);
    }
    draw_rect(c, bx, by, bw, bh, MC_LIGHT);
    draw_frame(c, bx, by, bw, bh, 2, MC_BLACK);
}

static void icon_cabinet(Canvas *c, int x, int y, int w, int h)
{
    int pw = w * 2 / 3, ph = h * 4 / 5;
    int px = x + (w - pw) / 2, py = y + (h - ph) / 2;
    if (pw < 12 || ph < 12) return;
    draw_rect(c, px, py, pw, ph, MC_WHITE);
    draw_frame(c, px, py, pw, ph, 2, MC_BLACK);
    for (int i = 1; i < 3; i++)
        draw_rect(c, px, py + i * ph / 3, pw, 2, MC_BLACK);
    for (int i = 0; i < 3; i++)                                  /* handles */
        draw_rect(c, px + pw / 2 - 4, py + i * ph / 3 + ph / 6, 8, 2, MC_DARK);
}

static void icon_phone(Canvas *c, int x, int y, int w, int h)
{
    int bw = w * 3 / 4, bh = h / 2;
    int bx = x + (w - bw) / 2, by = y + h - bh;
    if (bw < 14 || bh < 6) return;
    draw_rect(c, bx, by, bw, bh, MC_WHITE);
    draw_frame(c, bx, by, bw, bh, 2, MC_BLACK);
    for (int r = 0; r < 2; r++)                                  /* keypad */
        for (int col = 0; col < 3; col++)
            draw_rect(c, bx + 4 + col * (bw - 8) / 3, by + 4 + r * 5, 3, 3,
                      MC_DARK);
    draw_rect(c, bx + 2, by - 8, bw - 4, 4, MC_BLACK);           /* handset */
    draw_rect(c, bx, by - 10, 6, 6, MC_BLACK);
    draw_rect(c, bx + bw - 6, by - 10, 6, 6, MC_BLACK);
}

static void icon_stationery(Canvas *c, int x, int y, int w, int h)
{
    int pw = w * 3 / 5, ph = h * 3 / 5;
    int px = x + (w - pw) / 2 - 4, py = y + (h - ph) / 2 - 4;
    if (pw < 10 || ph < 8) return;
    for (int i = 0; i < 3; i++) {
        draw_rect(c, px + i * 4, py + i * 4, pw, ph, MC_WHITE);
        draw_frame(c, px + i * 4, py + i * 4, pw, ph, 2, MC_BLACK);
    }
}

static void icon_toolbox(Canvas *c, int x, int y, int w, int h)
{
    int bw = w * 3 / 4, bh = h / 2;
    int bx = x + (w - bw) / 2, by = y + h - bh;
    int hr;
    if (bw < 14 || bh < 6) return;
    /* The handle radius is capped by the box height so its lower arc is
     * fully covered when the box is drawn over it — otherwise a sliver of
     * ring shows below the box and the whole thing reads as a road sign. */
    hr = imini(bw / 4, bh - 2);
    draw_ring_hard(c, bx + bw / 2, by, hr, hr - 2, MC_BLACK);
    draw_rect(c, bx, by, bw, bh, MC_WHITE);
    draw_frame(c, bx, by, bw, bh, 2, MC_BLACK);
    draw_rect(c, bx + bw / 2 - 4, by + bh / 2 - 2, 8, 4, MC_DARK);
}

static void icon_globe(Canvas *c, int x, int y, int w, int h)
{
    int r = imini(w, h) / 2 - 1;
    int cx = x + w / 2, cy = y + h / 2;
    if (r < 5) return;
    draw_ring_hard(c, cx, cy, r, r - 2, MC_BLACK);
    draw_rect(c, cx - r + 2, cy - 1, (r - 2) * 2, 2, MC_BLACK);  /* equator */
    draw_ring_hard(c, cx, cy, r - 2, r - 4, MC_DARK);
    draw_rect(c, cx - 1, cy - r + 2, 2, (r - 2) * 2, MC_BLACK);  /* meridian */
}

static void icon_box(Canvas *c, int x, int y, int w, int h)
{
    int bw = w * 3 / 4, bh = h * 3 / 4;
    int bx = x + (w - bw) / 2, by = y + (h - bh) / 2;
    if (bw < 10 || bh < 8) return;
    draw_gradient_v(c, bx, by, bw, bh, 0xc98b52, 0x9c5d32);
    draw_frame(c, bx, by, bw, bh, 2, UI_WOOD_DARK);
    draw_rect(c, bx, by + bh / 3, bw, 2, UI_WOOD_DARK);          /* lid    */
    draw_rect(c, bx + bw / 2 - 2, by, 4, bh, UI_GOLD);           /* tape   */
}

static void icon_crate(Canvas *c, int x, int y, int w, int h)
{
    int bw = w * 3 / 4, bh = h * 3 / 4;
    int bx = x + (w - bw) / 2, by = y + (h - bh) / 2;
    if (bw < 10 || bh < 8) return;
    draw_gradient_v(c, bx, by, bw, bh, 0xa96a38, UI_WOOD);
    draw_frame(c, bx, by, bw, bh, 2, UI_WOOD_DARK);
    draw_line_hard(c, bx + 2, by + 2, bx + bw - 3, by + bh - 3, UI_GOLD);
    draw_line_hard(c, bx + bw - 3, by + 2, bx + 2, by + bh - 3, UI_GOLD);
}

static void icon_tin(Canvas *c, int x, int y, int w, int h)
{
    int bw = w * 3 / 5, bh = h * 3 / 4;
    int bx = x + (w - bw) / 2, by = y + (h - bh) / 2;
    if (bw < 8 || bh < 8) return;
    draw_gradient_v(c, bx, by, bw, bh, 0xa9c7c8, 0x557b83);
    draw_frame(c, bx, by, bw, bh, 2, UI_NAVY);
    draw_rect(c, bx, by + 4, bw, 2, UI_GOLD);                    /* lid rim */
    draw_dither(c, bx + 2, by + 8, bw - 4, bh - 12,
                0x6f9f9a, 0x86b4ae);
}

static void icon_laptop(Canvas *c, int x, int y, int w, int h)
{
    /* An open portable computer: raised screen leaf over a keyboard base
     * wedge, hinge line between them, teal screen glow. */
    int bw = w * 9 / 10;
    int bx = x + (w - bw) / 2;
    int sh = h * 3 / 5;             /* screen leaf height   */
    int kh = h - sh - 2;            /* keyboard base height */
    int sw = bw * 4 / 5;
    int sx = bx + (bw - sw) / 2;
    int sy = y + 1;
    if (bw < 14 || sh < 8 || kh < 5) return;
    draw_rect(c, sx, sy, sw, sh, UI_NAVY);
    draw_frame(c, sx, sy, sw, sh, 2, MC_BLACK);
    draw_rect(c, sx + 3, sy + 3, sw - 6, sh - 6, UI_TEAL);
    draw_rect(c, sx + 4, sy + 4, sw - 8, 2, MC_WHITE);   /* glare line */
    draw_rect(c, sx - 2, sy + sh, sw + 4, 2, MC_BLACK);  /* hinge      */
    draw_gradient_v(c, bx, sy + sh + 2, bw, kh, UI_SLATE, UI_NAVY);
    draw_frame(c, bx, sy + sh + 2, bw, kh, 1, MC_BLACK);
    for (int row = 0; row < 2; row++)
        for (int col = 0; col < 6; col++)
            draw_rect(c, bx + 3 + col * (bw - 6) / 6,
                      sy + sh + 4 + row * (kh - 3) / 2, 2, 2, MC_LIGHT);
}

static void icon_laptop_closed(Canvas *c, int x, int y, int w, int h)
{
    /* The same portable computer with its lid shut: a slim two-layer
     * slab resting on the desk, hinge ridge at the back, thin front
     * seam. Proportions echo icon_laptop's base wedge so the closed and
     * open frames read as one object. */
    int bw = w * 9 / 10;
    int bx = x + (w - bw) / 2;
    int bh = h * 2 / 5;
    int by = y + h - bh - 1;
    if (bw < 14 || bh < 6) return;
    draw_gradient_v(c, bx, by, bw, bh, 0x6f8890, UI_NAVY); /* lid top   */
    draw_frame(c, bx, by, bw, bh, 1, MC_BLACK);
    draw_rect(c, bx, by, bw, 2, 0x8fa6ac);                 /* back ridge */
    draw_rect(c, bx + 2, by + bh - 3, bw - 4, 1, MC_BLACK); /* seam     */
    draw_rect(c, bx + bw / 2 - 3, by + bh - 2, 6, 1, UI_GOLD); /* latch */
}

static void icon_breaker(Canvas *c, int x, int y, int w, int h)
{
    /* A wall breaker panel: steel door on a recessed box, hinge down the
     * left, a handle, and three toggles behind the glass — one per action
     * the panel offers, so the object states its own arity. */
    int door_x = x + 2;
    int door_w = w - 4;
    int inner_y = y + 6;
    int inner_h = h - 12;
    if (w < 16 || h < 20) return;
    draw_rect(c, x, y, w, h, UI_SLATE);
    draw_frame(c, x, y, w, h, 2, MC_BLACK);
    draw_gradient_v(c, door_x, y + 2, door_w, h - 4, MC_LIGHT, UI_SLATE);
    draw_frame(c, door_x, y + 2, door_w, h - 4, 1, MC_BLACK);
    draw_rect(c, door_x + 1, y + 3, 2, h - 6, MC_BLACK);      /* hinge  */
    draw_rect(c, x + w - 6, y + h / 2 - 3, 3, 7, UI_NAVY);    /* handle */
    draw_rect(c, door_x + 5, inner_y, door_w - 10, inner_h, MC_BLACK);
    for (int i = 0; i < 3; i++) {
        int slot_h = inner_h / 3;
        int slot_y = inner_y + i * slot_h + 1;
        if (slot_h < 4) break;
        draw_rect(c, door_x + 7, slot_y, door_w - 14, slot_h - 2, UI_TEAL);
        /* Each toggle sits thrown to one side; the top one is the odd
         * one out so the panel never reads as a plain grille. */
        draw_rect(c, i == 0 ? door_x + 8 : door_x + door_w - 12,
                  slot_y + 1, 3, slot_h - 4, MC_WHITE);
    }
}

static void icon_laptop_ajar(Canvas *c, int x, int y, int w, int h)
{
    /* The lid mid-swing: a short raised leaf over the keyboard base,
     * screen still dark, one glare line where the light catches it. */
    int bw = w * 9 / 10;
    int bx = x + (w - bw) / 2;
    int sh = h * 2 / 5;             /* the part-raised screen leaf */
    int kh = h / 4;                 /* keyboard base wedge         */
    int sw = bw * 4 / 5;
    int sx = bx + (bw - sw) / 2;
    int sy = y + h - kh - sh - 4;
    if (bw < 14 || sh < 5 || kh < 4) return;
    draw_rect(c, sx, sy, sw, sh, UI_NAVY);
    draw_frame(c, sx, sy, sw, sh, 1, MC_BLACK);
    draw_rect(c, sx + 3, sy + 2, sw - 6, 1, MC_WHITE);   /* glare line */
    draw_rect(c, sx - 2, sy + sh, sw + 4, 2, MC_BLACK);  /* hinge      */
    draw_gradient_v(c, bx, sy + sh + 2, bw, kh, UI_SLATE, UI_NAVY);
    draw_frame(c, bx, sy + sh + 2, bw, kh, 1, MC_BLACK);
    for (int col = 0; col < 6; col++)
        draw_rect(c, bx + 3 + col * (bw - 6) / 6, sy + sh + 4, 2, 2,
                  MC_LIGHT);
}

static void icon_keyboard(Canvas *c, int x, int y, int w, int h)
{
    int bw = w * 9 / 10;
    int bh = h * 3 / 5;
    int bx = x + (w - bw) / 2;
    int by = y + (h - bh) / 2;
    if (bw < 12 || bh < 8) return;
    draw_round_rect(c, bx, by, bw, bh, 2, MC_WHITE);
    draw_frame(c, bx, by, bw, bh, 1, MC_BLACK);
    for (int row = 0; row < 2; row++)
        for (int col = 0; col < 5; col++)
            draw_rect(c, bx + 2 + col * (bw - 3) / 5,
                      by + 2 + row * (bh - 3) / 2, 2, 2, MC_DARK);
    draw_rect(c, bx + 4, by + bh - 3, bw - 8, 1, MC_DARK);
}

void icon_draw(Canvas *c, IconId id, int x, int y, int w, int h)
{
    if (c == NULL || w <= 0 || h <= 0) return;
    switch (id) {
    case ICON_CLOCK:      icon_clock(c, x, y, w, h); break;
    case ICON_INBOX:      icon_tray(c, x, y, w, h, true); break;
    case ICON_OUTBOX:     icon_tray(c, x, y, w, h, false); break;
    case ICON_POSTCARD:   icon_postcard(c, x, y, w, h); break;
    case ICON_NAMECARD:   icon_namecard(c, x, y, w, h); break;
    case ICON_NOTEBOOK:   icon_notebook(c, x, y, w, h); break;
    case ICON_DATEBOOK:   icon_datebook(c, x, y, w, h); break;
    case ICON_CARDFILE:   icon_cardfile(c, x, y, w, h); break;
    case ICON_CABINET:    icon_cabinet(c, x, y, w, h); break;
    case ICON_PHONE:      icon_phone(c, x, y, w, h); break;
    case ICON_STATIONERY: icon_stationery(c, x, y, w, h); break;
    case ICON_TOOLBOX:    icon_toolbox(c, x, y, w, h); break;
    case ICON_GLOBE:      icon_globe(c, x, y, w, h); break;
    case ICON_BOX:        icon_box(c, x, y, w, h); break;
    case ICON_CRATE:      icon_crate(c, x, y, w, h); break;
    case ICON_TIN:        icon_tin(c, x, y, w, h); break;
    case ICON_KEYBOARD:   icon_keyboard(c, x, y, w, h); break;
    case ICON_LAPTOP:     icon_laptop(c, x, y, w, h); break;
    case ICON_LAPTOP_CLOSED: icon_laptop_closed(c, x, y, w, h); break;
    case ICON_LAPTOP_AJAR:   icon_laptop_ajar(c, x, y, w, h); break;
    case ICON_BREAKER:       icon_breaker(c, x, y, w, h); break;
    case ICON_NONE:
    case ICON_COUNT:
    default: break;
    }
}

bool icon_hit(IconId id, int x, int y, int w, int h, int px, int py)
{
    enum { MASK_MAX = 128 };
    static uint32_t pixels[MASK_MAX * MASK_MAX];
    const uint32_t untouched = 0x00123456u;
    Canvas mask;
    int local_x = px - x;
    int local_y = py - y;
    if (id <= ICON_NONE || id >= ICON_COUNT || w <= 0 || h <= 0 ||
        w > MASK_MAX || h > MASK_MAX || local_x < 0 || local_y < 0 ||
        local_x >= w || local_y >= h)
        return false;
    for (int i = 0; i < w * h; i++) pixels[i] = untouched;
    mask.px = pixels;
    mask.w = w;
    mask.h = h;
    icon_draw(&mask, id, 0, 0, w, h);
    return pixels[local_y * w + local_x] != untouched;
}
