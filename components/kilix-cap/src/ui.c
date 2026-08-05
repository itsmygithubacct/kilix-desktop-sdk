/* ui.c — object geometry, hit testing, object drawing. Contract: src/ui.h. */
#include "ui.h"

#include "art.h"
#include "draw.h"
#include "game_catalog.h"

UiRect ui_rect(int x, int y, int w, int h)
{
    UiRect r;
    r.x = x;
    r.y = y;
    r.w = w;
    r.h = h;
    return r;
}

bool ui_hit(UiRect r, int x, int y)
{
    return r.w > 0 && r.h > 0 && (int64_t)x >= r.x && (int64_t)y >= r.y &&
           (int64_t)x < (int64_t)r.x + r.w &&
           (int64_t)y < (int64_t)r.y + r.h;
}

bool ui_contains(UiRect outer, UiRect inner)
{
    return outer.w >= 0 && outer.h >= 0 && inner.w >= 0 && inner.h >= 0 &&
           (int64_t)inner.x >= outer.x && (int64_t)inner.y >= outer.y &&
           (int64_t)inner.x + inner.w <= (int64_t)outer.x + outer.w &&
           (int64_t)inner.y + inner.h <= (int64_t)outer.y + outer.h;
}

UiRect ui_target(UiRect v)
{
    UiRect r = v;
    if (r.w < MIN_TARGET_W) {
        r.x -= (MIN_TARGET_W - r.w) / 2;
        r.w = MIN_TARGET_W;
    }
    if (r.h < MIN_TARGET_H) {
        r.y -= (MIN_TARGET_H - r.h) / 2;
        r.h = MIN_TARGET_H;
    }
    return r;
}

bool ui_touchable(const Object *o)
{
    return o != NULL && o->visible && o->kind != OBJ_PLAIN;
}

bool ui_target_valid(const Object *o)
{
    if (o == NULL) return false;
    if (!ui_touchable(o)) return true;  /* scenery has no target contract */
    if (o->kind == OBJ_PROGRAM || o->kind == OBJ_ITEM ||
        o->kind == OBJ_GAME_MEDIA ||
        o->kind == OBJ_DOOR || o->kind == OBJ_PORTAL ||
        o->kind == OBJ_APPLIANCE || o->kind == OBJ_LAPTOP)
        return o->visual.w > 0 && o->visual.h > 0 &&
               o->hit.x == o->visual.x && o->hit.y == o->visual.y &&
               o->hit.w == o->visual.w && o->hit.h == o->visual.h;
    if (o->hit.w < MIN_TARGET_W || o->hit.h < MIN_TARGET_H) return false;
    return ui_contains(o->hit, o->visual);
}

bool ui_object_hit(const Object *o, int px, int py)
{
    int x;
    int y;
    if (!ui_touchable(o)) return false;
    x = o->held ? o->draw_x : o->visual.x;
    y = o->held ? o->draw_y : o->visual.y;
    if (o->kind == OBJ_PROGRAM) {
        if (art_ready())
            return art_workdesk_item_hit(o->icon, x, y, o->visual.w,
                                         o->visual.h, px, py);
        return icon_hit(o->icon, x, y, o->visual.w, o->visual.h, px, py);
    }
    if (o->kind == OBJ_ITEM) {
        if (art_mansion_items_ready() && o->icon >= ICON_BOX &&
            o->icon <= ICON_TIN)
            return art_mansion_item_hit(o->icon - ICON_BOX, x, y,
                                        o->visual.w, o->visual.h, px, py);
        return icon_hit(o->icon, x, y, o->visual.w, o->visual.h, px, py);
    }
    if (o->kind == OBJ_LAPTOP) {
        if (art_mansion_items_ready())
            return art_mansion_item_hit(ART_MANSION_ITEM_LAPTOP, x, y,
                                        o->visual.w, o->visual.h, px, py);
        return icon_hit(ICON_LAPTOP, x, y, o->visual.w, o->visual.h,
                        px, py);
    }
    if (o->kind == OBJ_GAME_MEDIA) {
        if (art_ready())
            return art_game_media_hit(o->container, x, y, o->visual.w,
                                      o->visual.h, px, py);
        return ui_hit(ui_rect(x, y, o->visual.w, o->visual.h), px, py);
    }
    if (o->kind == OBJ_DOOR) {
        return ui_hit(ui_rect(x, y, o->visual.w, o->visual.h), px, py);
    }
    if (o->kind == OBJ_PORTAL || o->kind == OBJ_APPLIANCE)
        return ui_hit(ui_rect(x, y, o->visual.w, o->visual.h), px, py);
    return ui_hit(o->hit, px, py);
}

static uint32_t object_accent(const Object *o)
{
    static const uint32_t accents[] = {
        UI_TEAL, UI_GOLD, UI_CORAL, UI_BLUE, UI_GREEN, UI_ORANGE, UI_PURPLE
    };
    unsigned key = (unsigned)(o->target < 0 ? -o->target : o->target);
    key += (unsigned)o->icon;
    return accents[key % (sizeof accents / sizeof accents[0])];
}

/* A warm wooden door leaf with a recessed panel and brass knob. */
static void draw_door(Canvas *c, int x, int y, int w, int h, bool touchable,
                      bool pressed)
{
    (void)touchable;
    draw_shadow(c, x, y, w, h);
    draw_gradient_v(c, x, y, w, h,
                    pressed ? UI_WOOD_DARK : UI_WOOD,
                    pressed ? UI_WOOD : UI_WOOD_DARK);
    draw_frame(c, x, y, w, h, 2, UI_WOOD_DARK);
    /* Recessed panel */
    if (w > 24 && h > 40) {
        int px = x + 10, py = y + 12;
        int pw = w - 20, ph = h - 34;
        draw_frame(c, px, py, pw, ph, 1, MC_BLACK);
        draw_blend_rect(c, px + 1, py + 1, pw - 2, ph - 2,
                        MC_BLACK, pressed ? 42u : 18u);
    }
    /* Knob, on the right; shadow falls down-right per the light rule. On a
     * short leaf the knob would land on the label, so it is omitted rather
     * than moved — a doorway too small to show a knob still reads as one. */
    if (w > 20 && h >= 60) {
        int kx = x + w - 12, ky = y + h / 2 - 2;
        draw_disc(c, kx + 3, ky + 3, 4, UI_WOOD_DARK);
        draw_disc(c, kx + 2, ky + 2, 3, UI_GOLD);
    }
}

static void draw_game_media_fallback(Canvas *c, const Object *o,
                                     int x, int y, int w, int h)
{
    static const uint32_t colors[] = {
        0xd9b56du, 0x35383du, 0x4f6658u,
        0x30343au, 0x48665du, 0xa95136u,
        0x263b56u, 0x596330u, 0x9f5136u
    };
    int variant = o->container;
    uint32_t color = colors[(unsigned)variant %
                            (sizeof colors / sizeof colors[0])];
    if (o->pressed) color = (color >> 1) & 0x7f7f7fu;
    draw_shadow(c, x, y, w, h);
    draw_round_rect(c, x, y, w, h, variant >= 3 && variant < 6 ? 3 : 2,
                    color);
    draw_frame(c, x, y, w, h, 1, UI_NAVY);
    if (variant >= 3 && variant < 6) {
        draw_rect(c, x + w / 5, y + h / 7, w * 3 / 5, h / 3,
                  0xe7d6af);
        draw_rect(c, x + w / 3, y + h * 2 / 3, w / 3, h / 5,
                  UI_SLATE);
    } else {
        draw_frame(c, x + 4, y + 4, w - 8, h - 8, 1, UI_GOLD);
    }
}

static uint32_t game_icon_color(uint8_t index, bool pressed)
{
    static const uint32_t palette[15] = {
        0x000000u, 0x000000u, 0xffffffu, 0x808080u, 0xc0c0c0u,
        0xff0000u, 0x800000u, 0xffff00u, 0x808000u, 0x0000ffu,
        0x000080u, 0x00ffffu, 0x008080u, 0x00ff00u, 0x008000u
    };
    uint32_t color = palette[index <= 14u ? index : 1u];
    if (pressed) {
        unsigned red = ((color >> 16) & 0xffu) * 3u / 4u;
        unsigned green = ((color >> 8) & 0xffu) * 3u / 4u;
        unsigned blue = (color & 0xffu) * 3u / 4u;
        color = (red << 16) | (green << 8) | blue;
    }
    return 0xff000000u | color;
}

static void draw_game_icon(Canvas *c, const Object *o,
                           int x, int y, int w, int h)
{
    int size;
    int left;
    int top;
    if (c == NULL || o == NULL || o->game_icon == NULL || w < 7 || h < 7)
        return;
    size = imini(GAME_ICON_SIDE, imini(w - 4, h - 4));
    if (size < 4) return;
    left = x + (w - size) / 2;
    top = y + (h - size) / 2;
    for (int dy = 0; dy < size; dy++) {
        int destination_y = top + dy;
        int source_y = dy * GAME_ICON_SIDE / size;
        if (destination_y < 0 || destination_y >= c->h) continue;
        for (int dx = 0; dx < size; dx++) {
            int destination_x = left + dx;
            int source_x = dx * GAME_ICON_SIDE / size;
            uint8_t color = o->game_icon[source_y * GAME_ICON_SIDE + source_x];
            if (color == 0u || destination_x < 0 || destination_x >= c->w)
                continue;
            /* Printed artwork belongs only to the physical case/disk/book;
             * irregular transparent corners stay visually and semantically
             * empty. */
            if (art_ready() &&
                !art_game_media_hit(o->container, x, y, w, h,
                                    destination_x, destination_y))
                continue;
            c->px[(size_t)destination_y * (size_t)c->w +
                  (size_t)destination_x] =
                game_icon_color(color, o->pressed);
        }
    }
}

void ui_draw_object(Canvas *c, const Object *o)
{
    int x, y, w, h;
    const char *label;

    if (c == NULL || o == NULL || !o->visible) return;
    x = o->held ? o->draw_x : o->visual.x;
    y = o->held ? o->draw_y : o->visual.y;
    w = o->visual.w;
    h = o->visual.h;
    label = o->label != NULL ? o->label : "";

    if (o->kind == OBJ_PROGRAM) {
        if (!art_ready()) icon_draw(c, o->icon, x, y, w, h);
        return;
    }
    if (o->kind == OBJ_ITEM) {
        /* Generated small props arrive as an optional atlas; the drawn
         * icons remain the complete fallback. */
        if (o->icon >= ICON_BOX && o->icon <= ICON_TIN &&
            art_draw_mansion_item(c, o->icon - ICON_BOX, x, y, w, h,
                                  o->pressed))
            return;
        icon_draw(c, o->icon, x, y, w, h);
        return;
    }
    if (o->kind == OBJ_LAPTOP) {
        if (art_draw_mansion_item(c, ART_MANSION_ITEM_LAPTOP, x, y, w, h,
                                  o->pressed))
            return;
        icon_draw(c, ICON_LAPTOP, x, y, w, h);
        return;
    }
    if (o->kind == OBJ_GAME_MEDIA) {
        if (!art_draw_game_media(c, o->container, x, y, w, h, o->pressed))
            draw_game_media_fallback(c, o, x, y, w, h);
        draw_game_icon(c, o, x, y, w, h);
        return;
    }
    if (o->kind == OBJ_PORTAL || o->kind == OBJ_APPLIANCE) {
        return;
    }
    if (o->kind == OBJ_DOOR) {
        /* Generated doors are part of the room plates so their perspective,
         * trim, light, and shadows remain native to each scene. */
        if (!art_ready())
            draw_door(c, x, y, w, h, ui_touchable(o), o->pressed);
        return;
    }
    if (o->tall) {
        draw_door(c, x, y, w, h, ui_touchable(o), o->pressed);
        return;
    }

    if (!ui_touchable(o)) {
        draw_shadow(c, x, y, w, h);
        draw_gradient_v(c, x, y, w, h, MC_DARK, UI_SLATE);
        draw_frame(c, x, y, w, h, DRAW_BORDER, MC_BLACK);
    } else if (o->pressed) {
        uint32_t accent = object_accent(o);
        draw_round_rect(c, x + 1, y + 2, w - 2, h - 2, 6, accent);
        draw_frame(c, x + 1, y + 2, w - 2, h - 2, 2, MC_WHITE);
    } else {
        uint32_t accent = object_accent(o);
        draw_shadow(c, x, y, w, h);
        draw_round_rect(c, x, y, w, h, 6, MC_WHITE);
        draw_rect(c, x + 3, y + 3, 5, h - 6, accent);
        draw_frame(c, x, y, w, h, 1, UI_NAVY);
        if (o->active && w > 10 && h > 10) {
            draw_blend_rect(c, x + 8, y + 3, w - 11, h - 6,
                            accent, 58u);
            draw_frame(c, x + 3, y + 3, w - 6, h - 6, 2, accent);
        }
    }

    if (o->icon != ICON_NONE) {
        int label_h = (label[0] != '\0') ? draw_text_height() + 6 : 0;
        icon_draw(c, o->icon, x + 4, y + 5, w - 8, h - 9 - label_h);
    }

    if (label[0] != '\0') {
        int ty = y + h - draw_text_height() - 4;
        uint32_t ink = (o->pressed || (!ui_touchable(o) && !o->tall))
                           ? MC_WHITE : UI_NAVY;
        draw_text_center(c, x + w / 2, ty, label, ink);
    }
}
