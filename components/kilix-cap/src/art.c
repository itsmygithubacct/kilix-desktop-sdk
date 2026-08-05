/* art.c — strict RGB environment plates and masked Desk item composition. */
#include "art.h"

#include "soft_raster.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

typedef enum BackgroundId {
    BACKGROUND_DESK = 0,
    BACKGROUND_HALLWAY,
    BACKGROUND_STOREROOM,
    BACKGROUND_SERVER_ROOM,
    BACKGROUND_GAME_ROOM,
    BACKGROUND_LIBRARY,
    BACKGROUND_CLEANING_ROOM,
    BACKGROUND_BALCONY,
    BACKGROUND_COUNT
} BackgroundId;

typedef struct DeskSprite {
    IconId icon;
    int x, y, w, h;  /* full-canvas coordinates */
} DeskSprite;

static const char *const background_names[BACKGROUND_COUNT] = {
    "workdesk-room.ppm", "hallway-room.ppm", "storeroom-room.ppm",
    "server-room.ppm", "game-room.ppm", "library-room.ppm",
    "cleaning-room.ppm", "balcony-room.ppm"
};

static const DeskSprite desk_sprites[] = {
    {ICON_CLOCK,      140, 140, 45, 41},
    {ICON_INBOX,       71, 150, 70, 25},
    {ICON_OUTBOX,      71, 169, 70, 30},
    {ICON_POSTCARD,    55, 195, 58, 28},
    {ICON_NAMECARD,   250, 194, 25, 17},
    {ICON_NOTEBOOK,   139, 192, 53, 34},
    {ICON_DATEBOOK,   280,  96, 35, 43},
    {ICON_CARDFILE,   277, 149, 42, 35},
    {ICON_CABINET,    319, 143, 45, 44},
    {ICON_PHONE,      340, 146, 92, 53},
    {ICON_STATIONERY, 296, 184, 54, 31},
    {ICON_TOOLBOX,    343, 200, 52, 37},
    {ICON_GLOBE,      187, 105, 89, 73}
};

enum {
    DESK_SPRITE_COUNT = (int)(sizeof desk_sprites / sizeof desk_sprites[0]),
    GAME_MEDIA_COLS = 3,
    GAME_MEDIA_ROWS = 3,
    GAME_MEDIA_CELL_W = 48,
    GAME_MEDIA_CELL_H = 56,
    GAME_MEDIA_W = GAME_MEDIA_COLS * GAME_MEDIA_CELL_W,
    GAME_MEDIA_H = GAME_MEDIA_ROWS * GAME_MEDIA_CELL_H,
    MANSION_ITEM_COLS = 2,
    MANSION_ITEM_ROWS = 2,
    MANSION_ITEM_CELL_W = 48,
    MANSION_ITEM_CELL_H = 56,
    MANSION_ITEM_W = MANSION_ITEM_COLS * MANSION_ITEM_CELL_W,
    MANSION_ITEM_H = MANSION_ITEM_ROWS * MANSION_ITEM_CELL_H,
    LAPTOP_LID_COLS = 2,
    LAPTOP_LID_ROWS = 1,
    LAPTOP_LID_CELL_W = MANSION_ITEM_CELL_W,
    LAPTOP_LID_CELL_H = MANSION_ITEM_CELL_H,
    LAPTOP_LID_W = LAPTOP_LID_COLS * LAPTOP_LID_CELL_W,
    LAPTOP_LID_H = LAPTOP_LID_ROWS * LAPTOP_LID_CELL_H
};

_Static_assert(LAPTOP_LID_COLS * LAPTOP_LID_ROWS == ART_LAPTOP_LID_FRAMES,
               "the lid grid must hold exactly the frame count");

_Static_assert(MANSION_ITEM_COLS * MANSION_ITEM_ROWS ==
                   ART_MANSION_ITEM_VARIANTS,
               "the small-prop grid must hold exactly the variant count");

_Static_assert((int)ICON_CLOCK == 1 &&
                   (int)ICON_GLOBE == (int)DESK_SPRITE_COUNT,
               "generated Desk sprite IDs must be contiguous");

static sr_canvas backgrounds[BACKGROUND_COUNT];
static sr_canvas item_atlas;
static sr_canvas item_alpha;
static sr_canvas item_hit;
static sr_canvas game_media;
static sr_canvas game_media_alpha;
static sr_canvas mansion_items;
static sr_canvas mansion_items_alpha;
static sr_canvas laptop_lid;
static sr_canvas laptop_lid_alpha;
static bool loaded;
static bool mansion_items_loaded;
static bool laptop_lid_loaded;
static bool extra_items_enabled = true;

static const DeskSprite *find_sprite(IconId icon)
{
    for (size_t i = 0; i < sizeof desk_sprites / sizeof desk_sprites[0]; i++)
        if (desk_sprites[i].icon == icon) return &desk_sprites[i];
    return NULL;
}

static bool copy_text(char *dst, size_t size, const char *src)
{
    int n;
    if (dst == NULL || size == 0 || src == NULL) return false;
    n = snprintf(dst, size, "%s", src);
    return n >= 0 && (size_t)n < size;
}

static bool join_path(char *dst, size_t size, const char *left,
                      const char *right)
{
    size_t length;
    int n;
    if (dst == NULL || left == NULL || right == NULL) return false;
    length = strlen(left);
    n = snprintf(dst, size, "%s%s%s", left,
                 length > 0 && left[length - 1] == '/' ? "" : "/", right);
    return n >= 0 && (size_t)n < size;
}

static bool executable_path(const char *argv0, char *dst, size_t size)
{
    char resolved[PATH_MAX];
#if defined(__linux__)
    {
        ssize_t length = readlink("/proc/self/exe", resolved,
                                  sizeof resolved - 1u);
        if (length > 0 && (size_t)length < sizeof resolved) {
            resolved[length] = '\0';
            return copy_text(dst, size, resolved);
        }
    }
#endif
    if (argv0 != NULL && argv0[0] != '\0' && strchr(argv0, '/') != NULL &&
        realpath(argv0, resolved) != NULL)
        return copy_text(dst, size, resolved);
    return false;
}

static bool executable_asset_directory(const char *argv0, char *dst,
                                       size_t size)
{
    char executable[PATH_MAX];
    char directory[PATH_MAX];
    const char *slash;
    if (!executable_path(argv0, executable, sizeof executable)) return false;
    slash = strrchr(executable, '/');
    if (slash == NULL) return false;
    {
        size_t length = (size_t)(slash - executable);
        if (length + 1u >= sizeof directory) return false;
        memcpy(directory, executable, length);
        directory[length] = '\0';
    }
    return join_path(dst, size, directory, "../assets/art");
}

static bool load_rgb_size(const char *directory, const char *name,
                          int width, int height, sr_canvas *result)
{
    char path[PATH_MAX];
    sr_canvas candidate = {0};
    if (!join_path(path, sizeof path, directory, name) ||
        !sr_load_ppm(&candidate, path) || candidate.w != width ||
        candidate.h != height) {
        sr_canvas_free(&candidate);
        return false;
    }
    *result = candidate;
    return true;
}

static bool load_rgb(const char *directory, const char *name,
                     sr_canvas *result)
{
    return load_rgb_size(directory, name, CANVAS_W, CONTENT_H, result);
}

static void free_bundle(void)
{
    for (int i = 0; i < BACKGROUND_COUNT; i++)
        sr_canvas_free(&backgrounds[i]);
    sr_canvas_free(&item_atlas);
    sr_canvas_free(&item_alpha);
    sr_canvas_free(&item_hit);
    sr_canvas_free(&game_media);
    sr_canvas_free(&game_media_alpha);
    sr_canvas_free(&mansion_items);
    sr_canvas_free(&mansion_items_alpha);
    sr_canvas_free(&laptop_lid);
    sr_canvas_free(&laptop_lid_alpha);
}

/* The two mask plates are deliberately RGB PPMs so the runtime asset format
 * stays uniform. Treating only their blue channel as data without checking
 * the other two channels would let a malformed colored mask silently change
 * picking or alpha behavior. Semantic pixels must also be backed by a
 * substantially visible alpha pixel and remain inside their declared prop. */
static bool item_layers_valid(const sr_canvas *atlas, const sr_canvas *alpha,
                              const sr_canvas *hit)
{
    size_t semantic_pixels[ICON_COUNT] = {0};
    size_t pixels = (size_t)CANVAS_W * CONTENT_H;

    for (size_t i = 0; i < pixels; i++) {
        uint32_t alpha_rgb = alpha->px[i] & 0xffffffu;
        uint32_t hit_rgb = hit->px[i] & 0xffffffu;
        unsigned alpha_value = alpha_rgb & 0xffu;
        unsigned hit_value = hit_rgb & 0xffu;
        int x = (int)(i % CANVAS_W);
        int y = (int)(i / CANVAS_W);
        const DeskSprite *sprite;

        if (((alpha_rgb >> 16) & 0xffu) != alpha_value ||
            ((alpha_rgb >> 8) & 0xffu) != alpha_value ||
            ((hit_rgb >> 16) & 0xffu) != hit_value ||
            ((hit_rgb >> 8) & 0xffu) != hit_value)
            return false;
        if (alpha_value == 0u && (atlas->px[i] & 0xffffffu) != 0u)
            return false;
        if (hit_value == 0u) continue;
        if (hit_value >= (unsigned)ICON_COUNT || alpha_value < 128u)
            return false;
        sprite = find_sprite((IconId)hit_value);
        if (sprite == NULL || x < sprite->x || x >= sprite->x + sprite->w ||
            y < sprite->y - CONTENT_Y ||
            y >= sprite->y - CONTENT_Y + sprite->h)
            return false;
        semantic_pixels[hit_value]++;
    }

    for (size_t i = 0; i < sizeof desk_sprites / sizeof desk_sprites[0]; i++)
        if (semantic_pixels[desk_sprites[i].icon] == 0u) return false;
    return true;
}

static bool game_media_layers_valid(const sr_canvas *atlas,
                                    const sr_canvas *alpha)
{
    size_t visible[ART_GAME_MEDIA_VARIANTS] = {0};
    size_t partial = 0;
    size_t pixels = (size_t)GAME_MEDIA_W * GAME_MEDIA_H;
    for (size_t i = 0; i < pixels; i++) {
        uint32_t mask_rgb = alpha->px[i] & 0xffffffu;
        unsigned value = mask_rgb & 0xffu;
        int x = (int)(i % GAME_MEDIA_W);
        int y = (int)(i / GAME_MEDIA_W);
        int variant = (y / GAME_MEDIA_CELL_H) * GAME_MEDIA_COLS +
                      x / GAME_MEDIA_CELL_W;
        if (((mask_rgb >> 16) & 0xffu) != value ||
            ((mask_rgb >> 8) & 0xffu) != value)
            return false;
        if (value == 0u) {
            if ((atlas->px[i] & 0xffffffu) != 0u) return false;
        } else {
            visible[variant]++;
            if (value < 255u) partial++;
        }
    }
    for (int i = 0; i < ART_GAME_MEDIA_VARIANTS; i++)
        if (visible[i] < 100u) return false;
    return partial > 0u;
}

static bool mansion_item_layers_valid(const sr_canvas *atlas,
                                      const sr_canvas *alpha)
{
    size_t visible[ART_MANSION_ITEM_VARIANTS] = {0};
    size_t partial = 0;
    size_t pixels = (size_t)MANSION_ITEM_W * MANSION_ITEM_H;
    for (size_t i = 0; i < pixels; i++) {
        uint32_t mask_rgb = alpha->px[i] & 0xffffffu;
        unsigned value = mask_rgb & 0xffu;
        int x = (int)(i % MANSION_ITEM_W);
        int y = (int)(i / MANSION_ITEM_W);
        int variant = (y / MANSION_ITEM_CELL_H) * MANSION_ITEM_COLS +
                      x / MANSION_ITEM_CELL_W;
        if (((mask_rgb >> 16) & 0xffu) != value ||
            ((mask_rgb >> 8) & 0xffu) != value)
            return false;
        if (value == 0u) {
            if ((atlas->px[i] & 0xffffffu) != 0u) return false;
        } else {
            visible[variant]++;
            if (value < 255u) partial++;
        }
    }
    for (int i = 0; i < ART_MANSION_ITEM_VARIANTS; i++)
        if (visible[i] < 100u) return false;
    return partial > 0u;
}

/* The optional pair loads both-or-neither after the mandatory bundle, so a
 * checkout awaiting art review runs with every plate and procedural
 * props rather than losing the whole bundle. */
static void load_mansion_items(const char *directory)
{
    sr_canvas atlas = {0};
    sr_canvas alpha = {0};
    if (!load_rgb_size(directory, "mansion-items.ppm", MANSION_ITEM_W,
                       MANSION_ITEM_H, &atlas) ||
        !load_rgb_size(directory, "mansion-items-mask.ppm", MANSION_ITEM_W,
                       MANSION_ITEM_H, &alpha) ||
        !mansion_item_layers_valid(&atlas, &alpha)) {
        sr_canvas_free(&atlas);
        sr_canvas_free(&alpha);
        return;
    }
    mansion_items = atlas;
    mansion_items_alpha = alpha;
    mansion_items_loaded = true;
}

static bool laptop_lid_layers_valid(const sr_canvas *atlas,
                                    const sr_canvas *alpha)
{
    size_t visible[ART_LAPTOP_LID_FRAMES] = {0};
    size_t partial = 0;
    size_t pixels = (size_t)LAPTOP_LID_W * LAPTOP_LID_H;
    for (size_t i = 0; i < pixels; i++) {
        uint32_t mask_rgb = alpha->px[i] & 0xffffffu;
        unsigned value = mask_rgb & 0xffu;
        int x = (int)(i % LAPTOP_LID_W);
        int frame = x / LAPTOP_LID_CELL_W;
        if (((mask_rgb >> 16) & 0xffu) != value ||
            ((mask_rgb >> 8) & 0xffu) != value)
            return false;
        if (value == 0u) {
            if ((atlas->px[i] & 0xffffffu) != 0u) return false;
        } else {
            visible[frame]++;
            if (value < 255u) partial++;
        }
    }
    for (int i = 0; i < ART_LAPTOP_LID_FRAMES; i++)
        if (visible[i] < 100u) return false;
    return partial > 0u;
}

/* The lid pair is a second optional add-on with the same both-or-neither
 * rule; it animates the mansion-items open laptop, so it is only loaded
 * once that atlas is in. */
static void load_laptop_lid(const char *directory)
{
    sr_canvas atlas = {0};
    sr_canvas alpha = {0};
    if (!mansion_items_loaded) return;
    if (!load_rgb_size(directory, "laptop-lid.ppm", LAPTOP_LID_W,
                       LAPTOP_LID_H, &atlas) ||
        !load_rgb_size(directory, "laptop-lid-mask.ppm", LAPTOP_LID_W,
                       LAPTOP_LID_H, &alpha) ||
        !laptop_lid_layers_valid(&atlas, &alpha)) {
        sr_canvas_free(&atlas);
        sr_canvas_free(&alpha);
        return;
    }
    laptop_lid = atlas;
    laptop_lid_alpha = alpha;
    laptop_lid_loaded = true;
}

static bool load_bundle(const char *directory)
{
    sr_canvas plates[BACKGROUND_COUNT] = {{0}};
    sr_canvas atlas = {0};
    sr_canvas alpha = {0};
    sr_canvas hit = {0};
    sr_canvas media = {0};
    sr_canvas media_mask = {0};
    bool ok = true;

    for (int i = 0; i < BACKGROUND_COUNT && ok; i++)
        ok = load_rgb(directory, background_names[i], &plates[i]);
    if (ok) ok = load_rgb(directory, "workdesk-items.ppm", &atlas);
    if (ok) ok = load_rgb(directory, "workdesk-items-mask.ppm", &alpha);
    if (ok) ok = load_rgb(directory, "workdesk-items-hit.ppm", &hit);
    if (ok) ok = item_layers_valid(&atlas, &alpha, &hit);
    if (ok)
        ok = load_rgb_size(directory, "game-media.ppm", GAME_MEDIA_W,
                           GAME_MEDIA_H, &media);
    if (ok)
        ok = load_rgb_size(directory, "game-media-mask.ppm", GAME_MEDIA_W,
                           GAME_MEDIA_H, &media_mask);
    if (ok) ok = game_media_layers_valid(&media, &media_mask);
    if (!ok) {
        for (int i = 0; i < BACKGROUND_COUNT; i++)
            sr_canvas_free(&plates[i]);
        sr_canvas_free(&atlas);
        sr_canvas_free(&alpha);
        sr_canvas_free(&hit);
        sr_canvas_free(&media);
        sr_canvas_free(&media_mask);
        return false;
    }
    for (int i = 0; i < BACKGROUND_COUNT; i++) backgrounds[i] = plates[i];
    item_atlas = atlas;
    item_alpha = alpha;
    item_hit = hit;
    game_media = media;
    game_media_alpha = media_mask;
    load_mansion_items(directory);
    load_laptop_lid(directory);
    return true;
}

bool art_init(const char *argv0, bool verbose)
{
    const char *override = getenv("KILIX_CAP_VISUAL_DIR");
    char directories[2][PATH_MAX] = {{0}};
    int directory_count = 0;

    art_shutdown();
    if (override != NULL && override[0] != '\0') {
        if (!copy_text(directories[0], sizeof directories[0], override)) {
            if (verbose) fprintf(stderr, "visual: override path is too long\n");
            return false;
        }
        directory_count = 1;
    } else {
        if (executable_asset_directory(argv0, directories[directory_count],
                                       sizeof directories[directory_count]))
            directory_count++;
        if (copy_text(directories[directory_count],
                      sizeof directories[directory_count], "assets/art"))
            directory_count++;
    }

    for (int i = 0; i < directory_count; i++) {
        if (!load_bundle(directories[i])) continue;
        loaded = true;
        if (verbose)
            printf("visual: loaded room-native RGB scenes and sprites from %s\n",
                   directories[i]);
        return true;
    }
    if (verbose) {
        fprintf(stderr, "visual: cannot load layered RGB room bundle");
        for (int i = 0; i < directory_count; i++)
            fprintf(stderr, "%s%s", i == 0 ? " from " : ", ", directories[i]);
        fputc('\n', stderr);
    }
    return false;
}

void art_shutdown(void)
{
    free_bundle();
    loaded = false;
    mansion_items_loaded = false;
    laptop_lid_loaded = false;
}

bool art_ready(void) { return loaded; }

bool art_mansion_items_ready(void)
{
    return loaded && mansion_items_loaded && extra_items_enabled;
}

void art_set_extra_items_enabled(bool enabled)
{
    extra_items_enabled = enabled;
}

bool art_laptop_lid_ready(void)
{
    return art_mansion_items_ready() && laptop_lid_loaded;
}

static bool draw_background(Canvas *canvas, BackgroundId id)
{
    if (!loaded || canvas == NULL || canvas->px == NULL ||
        canvas->w != CANVAS_W || canvas->h != CANVAS_H ||
        id < 0 || id >= BACKGROUND_COUNT)
        return false;
    for (int y = 0; y < CONTENT_H; y++)
        memcpy(canvas->px + (size_t)(CONTENT_Y + y) * CANVAS_W,
               backgrounds[id].px + (size_t)y * CANVAS_W,
               (size_t)CANVAS_W * sizeof *canvas->px);
    return true;
}

bool art_draw_workdesk(Canvas *canvas)
{
    return draw_background(canvas, BACKGROUND_DESK);
}

bool art_draw_hallway(Canvas *canvas)
{
    return draw_background(canvas, BACKGROUND_HALLWAY);
}

bool art_draw_storeroom(Canvas *canvas)
{
    return draw_background(canvas, BACKGROUND_STOREROOM);
}

bool art_draw_server_room(Canvas *canvas)
{
    return draw_background(canvas, BACKGROUND_SERVER_ROOM);
}

bool art_draw_game_room(Canvas *canvas)
{
    return draw_background(canvas, BACKGROUND_GAME_ROOM);
}

bool art_draw_library(Canvas *canvas)
{
    return draw_background(canvas, BACKGROUND_LIBRARY);
}

bool art_draw_cleaning_room(Canvas *canvas)
{
    return draw_background(canvas, BACKGROUND_CLEANING_ROOM);
}

bool art_draw_balcony(Canvas *canvas)
{
    return draw_background(canvas, BACKGROUND_BALCONY);
}

static uint32_t alpha_blend(uint32_t below, uint32_t above, unsigned alpha)
{
    unsigned inverse = 255u - alpha;
    unsigned r = (((above >> 16) & 0xffu) * alpha +
                  ((below >> 16) & 0xffu) * inverse + 127u) / 255u;
    unsigned g = (((above >> 8) & 0xffu) * alpha +
                  ((below >> 8) & 0xffu) * inverse + 127u) / 255u;
    unsigned b = ((above & 0xffu) * alpha + (below & 0xffu) * inverse +
                  127u) / 255u;
    return 0xff000000u | (r << 16) | (g << 8) | b;
}

bool art_draw_workdesk_items(Canvas *canvas)
{
    if (!loaded || canvas == NULL || canvas->px == NULL ||
        canvas->w != CANVAS_W || canvas->h != CANVAS_H)
        return false;
    for (int y = 0; y < CONTENT_H; y++)
        for (int x = 0; x < CANVAS_W; x++) {
            size_t source = (size_t)y * CANVAS_W + (size_t)x;
            unsigned alpha = item_alpha.px[source] & 0xffu;
            if (alpha != 0u) {
                size_t destination = (size_t)(y + CONTENT_Y) * CANVAS_W +
                                     (size_t)x;
                canvas->px[destination] = alpha_blend(
                    canvas->px[destination], item_atlas.px[source], alpha);
            }
        }
    return true;
}

static uint32_t shade_rgb(uint32_t rgb, unsigned numerator,
                          unsigned denominator)
{
    unsigned r = ((rgb >> 16) & 0xffu) * numerator / denominator;
    unsigned g = ((rgb >> 8) & 0xffu) * numerator / denominator;
    unsigned b = (rgb & 0xffu) * numerator / denominator;
    return 0xff000000u | (r << 16) | (g << 8) | b;
}

bool art_draw_game_media(Canvas *canvas, int variant, int x, int y,
                         int w, int h, bool pressed)
{
    int cell_x;
    int cell_y;
    if (!loaded || canvas == NULL || canvas->px == NULL || w <= 0 || h <= 0 ||
        variant < 0 || variant >= ART_GAME_MEDIA_VARIANTS)
        return false;
    cell_x = (variant % GAME_MEDIA_COLS) * GAME_MEDIA_CELL_W;
    cell_y = (variant / GAME_MEDIA_COLS) * GAME_MEDIA_CELL_H;
    for (int dy = 0; dy < h; dy++) {
        int destination_y = y + dy;
        int source_y = cell_y +
                       (int)((int64_t)dy * GAME_MEDIA_CELL_H / h);
        if (destination_y < 0 || destination_y >= canvas->h) continue;
        for (int dx = 0; dx < w; dx++) {
            int destination_x = x + dx;
            int source_x = cell_x +
                           (int)((int64_t)dx * GAME_MEDIA_CELL_W / w);
            size_t source;
            size_t destination;
            unsigned alpha;
            uint32_t above;
            if (destination_x < 0 || destination_x >= canvas->w) continue;
            source = (size_t)source_y * GAME_MEDIA_W + (size_t)source_x;
            alpha = game_media_alpha.px[source] & 0xffu;
            if (alpha == 0u) continue;
            above = game_media.px[source];
            if (pressed) above = shade_rgb(above, 3u, 4u);
            destination = (size_t)destination_y * (size_t)canvas->w +
                          (size_t)destination_x;
            canvas->px[destination] = alpha_blend(
                canvas->px[destination], above, alpha);
        }
    }
    return true;
}

bool art_game_media_hit(int variant, int x, int y, int w, int h,
                        int px, int py)
{
    int cell_x;
    int cell_y;
    int source_x;
    int source_y;
    if (!loaded || variant < 0 || variant >= ART_GAME_MEDIA_VARIANTS ||
        w <= 0 || h <= 0 || (int64_t)px < x || (int64_t)py < y ||
        (int64_t)px >= (int64_t)x + w ||
        (int64_t)py >= (int64_t)y + h)
        return false;
    cell_x = (variant % GAME_MEDIA_COLS) * GAME_MEDIA_CELL_W;
    cell_y = (variant / GAME_MEDIA_COLS) * GAME_MEDIA_CELL_H;
    source_x = cell_x + (int)(((int64_t)px - x) * GAME_MEDIA_CELL_W / w);
    source_y = cell_y + (int)(((int64_t)py - y) * GAME_MEDIA_CELL_H / h);
    return (game_media_alpha.px[(size_t)source_y * GAME_MEDIA_W +
                                (size_t)source_x] & 0xffu) >= 128u;
}

bool art_draw_mansion_item(Canvas *canvas, int variant, int x, int y,
                           int w, int h, bool pressed)
{
    int cell_x;
    int cell_y;
    if (!art_mansion_items_ready() || canvas == NULL ||
        canvas->px == NULL || w <= 0 || h <= 0 || variant < 0 ||
        variant >= ART_MANSION_ITEM_VARIANTS)
        return false;
    cell_x = (variant % MANSION_ITEM_COLS) * MANSION_ITEM_CELL_W;
    cell_y = (variant / MANSION_ITEM_COLS) * MANSION_ITEM_CELL_H;
    for (int dy = 0; dy < h; dy++) {
        int destination_y = y + dy;
        int source_y = cell_y +
                       (int)((int64_t)dy * MANSION_ITEM_CELL_H / h);
        if (destination_y < 0 || destination_y >= canvas->h) continue;
        for (int dx = 0; dx < w; dx++) {
            int destination_x = x + dx;
            int source_x = cell_x +
                           (int)((int64_t)dx * MANSION_ITEM_CELL_W / w);
            size_t source;
            size_t destination;
            unsigned alpha;
            uint32_t above;
            if (destination_x < 0 || destination_x >= canvas->w) continue;
            source = (size_t)source_y * MANSION_ITEM_W + (size_t)source_x;
            alpha = mansion_items_alpha.px[source] & 0xffu;
            if (alpha == 0u) continue;
            above = mansion_items.px[source];
            if (pressed) above = shade_rgb(above, 3u, 4u);
            destination = (size_t)destination_y * (size_t)canvas->w +
                          (size_t)destination_x;
            canvas->px[destination] = alpha_blend(
                canvas->px[destination], above, alpha);
        }
    }
    return true;
}

bool art_mansion_item_hit(int variant, int x, int y, int w, int h,
                          int px, int py)
{
    int cell_x;
    int cell_y;
    int source_x;
    int source_y;
    if (!art_mansion_items_ready() || variant < 0 ||
        variant >= ART_MANSION_ITEM_VARIANTS || w <= 0 || h <= 0 ||
        (int64_t)px < x || (int64_t)py < y ||
        (int64_t)px >= (int64_t)x + w ||
        (int64_t)py >= (int64_t)y + h)
        return false;
    cell_x = (variant % MANSION_ITEM_COLS) * MANSION_ITEM_CELL_W;
    cell_y = (variant / MANSION_ITEM_COLS) * MANSION_ITEM_CELL_H;
    source_x = cell_x + (int)(((int64_t)px - x) * MANSION_ITEM_CELL_W / w);
    source_y = cell_y + (int)(((int64_t)py - y) * MANSION_ITEM_CELL_H / h);
    return (mansion_items_alpha.px[(size_t)source_y * MANSION_ITEM_W +
                                   (size_t)source_x] & 0xffu) >= 128u;
}

bool art_draw_laptop_lid(Canvas *canvas, int frame, int x, int y,
                         int w, int h, bool pressed)
{
    int cell_x;
    if (!art_laptop_lid_ready() || canvas == NULL || canvas->px == NULL ||
        w <= 0 || h <= 0 || frame < 0 || frame >= ART_LAPTOP_LID_FRAMES)
        return false;
    cell_x = frame * LAPTOP_LID_CELL_W;
    for (int dy = 0; dy < h; dy++) {
        int destination_y = y + dy;
        int source_y = (int)((int64_t)dy * LAPTOP_LID_CELL_H / h);
        if (destination_y < 0 || destination_y >= canvas->h) continue;
        for (int dx = 0; dx < w; dx++) {
            int destination_x = x + dx;
            int source_x = cell_x +
                           (int)((int64_t)dx * LAPTOP_LID_CELL_W / w);
            size_t source;
            size_t destination;
            unsigned alpha;
            uint32_t above;
            if (destination_x < 0 || destination_x >= canvas->w) continue;
            source = (size_t)source_y * LAPTOP_LID_W + (size_t)source_x;
            alpha = laptop_lid_alpha.px[source] & 0xffu;
            if (alpha == 0u) continue;
            above = laptop_lid.px[source];
            if (pressed) above = shade_rgb(above, 3u, 4u);
            destination = (size_t)destination_y * (size_t)canvas->w +
                          (size_t)destination_x;
            canvas->px[destination] = alpha_blend(
                canvas->px[destination], above, alpha);
        }
    }
    return true;
}

bool art_laptop_lid_hit(int frame, int x, int y, int w, int h,
                        int px, int py)
{
    int cell_x;
    int source_x;
    int source_y;
    if (!art_laptop_lid_ready() || frame < 0 ||
        frame >= ART_LAPTOP_LID_FRAMES || w <= 0 || h <= 0 ||
        (int64_t)px < x || (int64_t)py < y ||
        (int64_t)px >= (int64_t)x + w || (int64_t)py >= (int64_t)y + h)
        return false;
    cell_x = frame * LAPTOP_LID_CELL_W;
    source_x = cell_x + (int)(((int64_t)px - x) * LAPTOP_LID_CELL_W / w);
    source_y = (int)(((int64_t)py - y) * LAPTOP_LID_CELL_H / h);
    return (laptop_lid_alpha.px[(size_t)source_y * LAPTOP_LID_W +
                                (size_t)source_x] & 0xffu) >= 128u;
}

bool art_workdesk_item_bounds(IconId icon, int *x, int *y, int *w, int *h)
{
    const DeskSprite *sprite = find_sprite(icon);
    if (sprite == NULL || x == NULL || y == NULL || w == NULL || h == NULL)
        return false;
    *x = sprite->x;
    *y = sprite->y;
    *w = sprite->w;
    *h = sprite->h;
    return true;
}

bool art_workdesk_item_hit(IconId icon, int x, int y, int w, int h,
                           int px, int py)
{
    const DeskSprite *sprite = find_sprite(icon);
    int64_t local_x;
    int64_t local_y;
    int source_x;
    int source_y;
    if (!loaded || sprite == NULL || w <= 0 || h <= 0 ||
        (int64_t)px < x || (int64_t)py < y ||
        (int64_t)px >= (int64_t)x + w ||
        (int64_t)py >= (int64_t)y + h)
        return false;
    local_x = (int64_t)px - x;
    local_y = (int64_t)py - y;
    source_x = sprite->x + (int)(local_x * sprite->w / w);
    source_y = sprite->y - CONTENT_Y +
               (int)(local_y * sprite->h / h);
    if (source_x < 0 || source_x >= CANVAS_W || source_y < 0 ||
        source_y >= CONTENT_H)
        return false;
    return (item_hit.px[(size_t)source_y * CANVAS_W + (size_t)source_x] &
            0xffu) == (unsigned)icon;
}
