/* main.c — frame loop, signal safety, and the headless test subcommands.
 *
 * kilix-cap. Spec: docs/ENGINE.md §§1,5,6.
 *
 * Tests are subcommands of the shipped binary rather than a separate test
 * program (house convention). Headless modes never call term_init(), which
 * is why every function in term.c is a safe no-op on an unstarted session.
 */
#include "canvas.h"
#include "art.h"
#include "draw.h"
#include "game_catalog.h"
#include "game_icons.h"
#include "input.h"
#include "laptop_run.h"
#include "launcher.h"
#include "panel.h"
#include "provider_protocol.h"
#include "scene.h"
#include "sound.h"
#include "term.h"
#include "ui.h"

#include "soft_raster.h"

#include <errno.h>
#include <limits.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#define KILIX_CAP_VERSION "3.0.0"

enum { PRESENT_HZ = 30 };

static Canvas canvas;

static void send_mouse(input_kind kind, int x, int y, uint8_t button,
                       bool in_view);

/* ---- Signal-safe teardown ---- */

static const int fatal_signals[] = {
    SIGINT, SIGTERM, SIGHUP, SIGSEGV, SIGBUS, SIGFPE, SIGABRT
};

/* These externally delivered signals can arrive while term_init() has put
 * the PTY in raw mode but is still waiting for its graphics probe.  Hold them
 * until the terminal session is fully visible to the emergency restore path. */
static const int startup_signals[] = { SIGINT, SIGTERM, SIGHUP };

static void on_fatal_signal(int sig)
{
    term_emergency_restore();
    _exit(128 + sig);
}

static int install_signal_handlers(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_fatal_signal;
    if (sigfillset(&sa.sa_mask) != 0) return -1;
    sa.sa_flags = (int)SA_RESETHAND;
    for (size_t i = 0;
         i < sizeof fatal_signals / sizeof fatal_signals[0]; i++)
        if (sigaction(fatal_signals[i], &sa, NULL) != 0) return -1;
    return 0;
}

static int block_startup_signals(sigset_t *previous)
{
    sigset_t blocked;
    if (previous == NULL) {
        errno = EINVAL;
        return -1;
    }
    if (sigemptyset(&blocked) != 0) return -1;
    for (size_t i = 0;
         i < sizeof startup_signals / sizeof startup_signals[0]; i++)
        if (sigaddset(&blocked, startup_signals[i]) != 0) return -1;
    return sigprocmask(SIG_BLOCK, &blocked, previous);
}

static int64_t now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static void sleep_ms(int64_t ms)
{
    struct timespec ts;
    if (ms <= 0) return;
    ts.tv_sec = (time_t)(ms / 1000);
    ts.tv_nsec = (long)((ms % 1000) * 1000000);
    nanosleep(&ts, NULL);
}

/* ---- Headless helpers ---- */

static uint32_t rng_state;

static uint32_t rng_next(void)
{
    rng_state = rng_state * 1664525u + 1013904223u;
    return rng_state;
}

static bool check_object(const Object *o, const char *where, int *failures)
{
    if (!ui_target_valid(o)) {
        printf("FAIL %s: '%s' violates its exact-object or conventional "
               "minimum-target contract (hit %dx%d)\n",
               where, o->name, o->hit.w, o->hit.h);
        (*failures)++;
        return false;
    }
    return true;
}

static bool rects_overlap(UiRect a, UiRect b)
{
    return a.x < b.x + b.w && b.x < a.x + a.w &&
           a.y < b.y + b.h && b.y < a.y + a.h;
}

static void test_expect(bool condition, const char *what, int *failures)
{
    if (!condition) {
        printf("FAIL %s\n", what);
        (*failures)++;
    }
}

static bool object_hit_point(const Object *o, int *hit_x, int *hit_y)
{
    UiRect scan;
    int center_x;
    int center_y;

    if (o == NULL || hit_x == NULL || hit_y == NULL || !ui_touchable(o))
        return false;
    center_x = o->visual.x + o->visual.w / 2;
    center_y = o->visual.y + o->visual.h / 2;
    if (ui_object_hit(o, center_x, center_y)) {
        *hit_x = center_x;
        *hit_y = center_y;
        return true;
    }
    scan = o->hit;
    for (int y = scan.y; y < scan.y + scan.h; y++)
        for (int x = scan.x; x < scan.x + scan.w; x++)
            if (ui_object_hit(o, x, y)) {
                *hit_x = x;
                *hit_y = y;
                return true;
            }
    return false;
}

static bool object_transparent_point(const Object *o, int *clear_x,
                                     int *clear_y)
{
    if (o == NULL || clear_x == NULL || clear_y == NULL) return false;
    for (int y = o->visual.y; y < o->visual.y + o->visual.h; y++)
        for (int x = o->visual.x; x < o->visual.x + o->visual.w; x++)
            if (!ui_object_hit(o, x, y)) {
                *clear_x = x;
                *clear_y = y;
                return true;
            }
    return false;
}

static bool click_object(const Object *o)
{
    int x, y;
    if (!object_hit_point(o, &x, &y)) return false;
    send_mouse(IN_MOUSE_DOWN, x, y, 0, true);
    send_mouse(IN_MOUSE_UP, x, y, 0, true);
    return true;
}

static bool object_hits_overlap(const Object *a, const Object *b)
{
    UiRect overlap;
    int right;
    int bottom;

    /* A foreground physical Desk prop may visually occlude the distant exit
     * leaf. scene.c uses that same z order for picking, so this is resolved
     * layering rather than an ambiguous pair of peer targets. */
    if ((a->kind == OBJ_PROGRAM && b->kind == OBJ_DOOR) ||
        (a->kind == OBJ_DOOR && b->kind == OBJ_PROGRAM))
        return false;
    overlap.x = a->hit.x > b->hit.x ? a->hit.x : b->hit.x;
    overlap.y = a->hit.y > b->hit.y ? a->hit.y : b->hit.y;
    right = a->hit.x + a->hit.w;
    if (b->hit.x + b->hit.w < right) right = b->hit.x + b->hit.w;
    bottom = a->hit.y + a->hit.h;
    if (b->hit.y + b->hit.h < bottom) bottom = b->hit.y + b->hit.h;
    overlap.w = right - overlap.x;
    overlap.h = bottom - overlap.y;
    if (overlap.w <= 0 || overlap.h <= 0) return false;
    for (int y = overlap.y; y < overlap.y + overlap.h; y++)
        for (int x = overlap.x; x < overlap.x + overlap.w; x++)
            if (ui_object_hit(a, x, y) && ui_object_hit(b, x, y)) return true;
    return false;
}

/* Conventional controls retain a generous minimum target. Separate physical
 * sprites use their exact visible silhouettes, including transparent pixels
 * inside their bounding rectangles. Room-native doors use architectural
 * rectangles fitted to the depicted leaves. Peer semantic hit areas may not
 * overlap; a foreground Desk prop may occlude the distant exit door. */
static int cmd_targets_test(const char *argv0)
{
    int failures = 0;

    test_expect(art_init(argv0, true),
                "layered visual bundle loads for semantic hit tests",
                &failures);
    scene_init();
    for (int s = 0; s < SCENE_COUNT; s++) {
        int n = scene_object_count((SceneId)s);
        for (int i = 0; i < n; i++) {
            const Object *o = scene_object((SceneId)s, i);
            int hit_x = 0;
            int hit_y = 0;
            check_object(o, scene_name((SceneId)s), &failures);
            if (!ui_touchable(o)) continue;
            test_expect(object_hit_point(o, &hit_x, &hit_y),
                        "every touchable object has a semantic hit pixel",
                        &failures);
            if (o->kind == OBJ_PROGRAM || o->kind == OBJ_ITEM ||
                o->kind == OBJ_GAME_MEDIA) {
                int clear_x = 0;
                int clear_y = 0;
                test_expect(object_transparent_point(o, &clear_x, &clear_y),
                            "physical object bbox contains transparent space",
                            &failures);
            }
            if (o->kind == OBJ_PROGRAM || o->kind == OBJ_ITEM ||
                o->kind == OBJ_DOOR || o->kind == OBJ_GAME_MEDIA) {
                test_expect(!ui_object_hit(o, o->visual.x - 1, hit_y) &&
                                !ui_object_hit(o, o->visual.x + o->visual.w,
                                               hit_y) &&
                                !ui_object_hit(o, hit_x, o->visual.y - 1) &&
                                !ui_object_hit(o, hit_x,
                                               o->visual.y + o->visual.h),
                            "physical object never responds outside its bounds",
                            &failures);
            }
        }
        for (int i = 0; i < n; i++) {
            const Object *a = scene_object((SceneId)s, i);
            if (!ui_touchable(a)) continue;
            for (int j = i + 1; j < n; j++) {
                const Object *b = scene_object((SceneId)s, j);
                if (!ui_touchable(b)) continue;
                if (object_hits_overlap(a, b)) {
                    printf("FAIL %s: semantic targets overlap: '%s' and '%s'\n",
                           scene_name((SceneId)s), a->name, b->name);
                    failures++;
                }
            }
        }
    }
    for (int i = 0; i < scene_bar_count(); i++)
        check_object(scene_bar_object(i), "Control bar", &failures);
    for (int i = 0; i < scene_bar_count(); i++) {
        const Object *a = scene_bar_object(i);
        if (!ui_touchable(a)) continue;
        for (int j = i + 1; j < scene_bar_count(); j++) {
            const Object *b = scene_bar_object(j);
            if (!ui_touchable(b)) continue;
            if (rects_overlap(a->hit, b->hit)) {
                printf("FAIL Control bar: hit rects overlap: '%s' and '%s'\n",
                       a->name, b->name);
                failures++;
            }
        }
    }

    /* Physical launchers must dispatch without manufacturing modal targets. */
    for (int i = 0; i < 13; i++) {
        LaunchAppId app = LAUNCH_CLOCK;
        scene_goto(SCENE_DESK);
        click_object(scene_object(SCENE_DESK, i));
        test_expect(!scene_panel_open() &&
                        scene_take_launch_request(&app) &&
                        app == (LaunchAppId)i,
                    "Desk object dispatches directly", &failures);
    }
    scene_goto(SCENE_LIBRARY);
    click_object(scene_object(SCENE_LIBRARY, 1));
    {
        LaunchToolId tool = LAUNCH_TOOL_COUNT;
        test_expect(!scene_panel_open() &&
                        scene_take_tool_request(&tool) &&
                        tool == LAUNCH_TOOL_DOC_START,
                    "Library book dispatches directly", &failures);
    }

    art_shutdown();
    if (failures == 0) printf("targets-test: ok\n");
    return failures == 0 ? 0 : 1;
}

static int cmd_input_test(void)
{
    static const uint8_t move_a[] = "\x1b[<35;10;10M";
    static const uint8_t move_b[] = "\x1b[<35;11;10M";
    static const uint8_t press[] = "\x1b[<0;2;2M";
    static const uint8_t malformed[] =
        "\x1b[<M\x1b[<0;1M\x1b[<0;;1M\x1b[<128;1;1M"
        "\x1b[<3;1;1M\x1b[<0;0;1M";
    static const uint8_t wheels[] =
        "\x1b[<64;2;2M\x1b[<65;2;2M";
    static const uint8_t pixel_second[] = "\x1b[<35;22;62M";
    static const uint8_t pixel_last[] = "\x1b[<35;2900;1980M";
    static const uint8_t pixel_outside[] = "\x1b[<35;2901;1981M";
    input_event ev;
    int failures = 0;

    input_reset();
    input_set_geometry(80, 24, 9, 18, 1, 1, 1, 0, 0);

    /* A key between two moves prevents coalescing and keeps global order. */
    input_mouse_feed(move_a, sizeof move_a - 1u);
    input_push_key('x', 0, 1);
    input_mouse_feed(move_b, sizeof move_b - 1u);
    test_expect(input_next(&ev) && ev.kind == IN_MOUSE_MOVE,
                "input order: first move", &failures);
    test_expect(input_next(&ev) && ev.kind == IN_KEY_DOWN && ev.key == 'x',
                "input order: interleaved key", &failures);
    test_expect(input_next(&ev) && ev.kind == IN_MOUSE_MOVE,
                "input order: second move", &failures);
    test_expect(!input_next(&ev), "input order: queue drained", &failures);

    /* The scanner is resumable at every byte boundary. */
    input_reset();
    input_set_geometry(80, 24, 9, 18, 1, 1, 1, 0, 0);
    for (size_t i = 0; i < sizeof press - 1u; i++)
        input_mouse_feed(&press[i], 1u);
    test_expect(input_next(&ev) && ev.kind == IN_MOUSE_DOWN && ev.button == 0,
                "fragmented SGR press", &failures);
    test_expect(!input_next(&ev), "fragmented SGR emitted once", &failures);

    input_mouse_feed(malformed, sizeof malformed - 1u);
    test_expect(!input_next(&ev),
                "malformed and extra-button SGR reports are ignored",
                &failures);

    input_mouse_feed(wheels, sizeof wheels - 1u);
    test_expect(input_next(&ev) && ev.kind == IN_MOUSE_WHEEL && ev.wheel == 1,
                "wheel up", &failures);
    test_expect(input_next(&ev) && ev.kind == IN_MOUSE_WHEEL && ev.wheel == -1,
                "wheel down", &failures);
    test_expect(!input_next(&ev), "wheel queue drained", &failures);

    input_push_key('z', 0, 1);
    input_reset();
    test_expect(!input_next(&ev), "input reset clears queued events", &failures);

    /* SGR-pixel coordinates are one-based.  With a 2x framebuffer beginning
     * at terminal pixel 21,61, both 21,61 and 22,62 belong to canvas pixel
     * 0,0; 2900,1980 is the final displayed physical pixel. */
    input_set_geometry(80, 24, 10, 20, 3, 4, 2, 0, 0);
    input_mouse_feed(pixel_second, sizeof pixel_second - 1u);
    test_expect(input_next(&ev) && ev.kind == IN_MOUSE_MOVE &&
                    ev.mx == 0 && ev.my == 0 && ev.in_view,
                "one-based SGR pixels map within the first scaled pixel",
                &failures);
    input_mouse_feed(pixel_last, sizeof pixel_last - 1u);
    test_expect(input_next(&ev) && ev.kind == IN_MOUSE_MOVE &&
                    ev.mx == CANVAS_W - 1 && ev.my == CANVAS_H - 1 &&
                    ev.in_view,
                "last framebuffer pixel remains in view", &failures);
    input_mouse_feed(pixel_outside, sizeof pixel_outside - 1u);
    test_expect(input_next(&ev) && ev.kind == IN_MOUSE_MOVE &&
                    ev.mx == CANVAS_W - 1 && ev.my == CANVAS_H - 1 &&
                    !ev.in_view,
                "first pixel beyond framebuffer clamps out of view",
                &failures);

    test_expect(term_translation_test(),
                "Kitty shifted letters and punctuation preserve produced text",
                &failures);

    if (failures == 0) printf("input-test: ok\n");
    return failures == 0 ? 0 : 1;
}

static void send_mouse(input_kind kind, int x, int y, uint8_t button,
                       bool in_view)
{
    input_event ev;
    memset(&ev, 0, sizeof ev);
    ev.kind = kind;
    ev.mx = (int16_t)x;
    ev.my = (int16_t)y;
    ev.button = button;
    ev.in_view = in_view;
    scene_handle(&ev);
}

static bool fallback_desk_z_order_matches_picking(void)
{
    const uint32_t untouched = 0xff010203u;
    const Object *phone = NULL;
    const Object *door = NULL;
    Canvas rendered = {0};
    Canvas phone_layer = {0};
    bool found_overlap = false;
    bool matched = true;

    /* scene-test intentionally does not initialize the generated art bundle,
     * so ui_draw_object() and scene_draw() exercise procedural fallbacks. */
    for (int i = 0; i < scene_object_count(SCENE_DESK); i++) {
        const Object *o = scene_object(SCENE_DESK, i);
        if (o->kind == OBJ_PROGRAM && o->icon == ICON_PHONE) phone = o;
        if (o->kind == OBJ_DOOR) door = o;
    }
    if (phone == NULL || door == NULL ||
        !canvas_init(&rendered, CANVAS_W, CANVAS_H) ||
        !canvas_init(&phone_layer, CANVAS_W, CANVAS_H)) {
        canvas_free(&rendered);
        canvas_free(&phone_layer);
        return false;
    }

    scene_goto(SCENE_DESK);
    scene_draw(&rendered);
    draw_clear(&phone_layer, untouched);
    ui_draw_object(&phone_layer, phone);

    int left = phone->visual.x > door->visual.x ?
                   phone->visual.x : door->visual.x;
    int top = phone->visual.y > door->visual.y ?
                  phone->visual.y : door->visual.y;
    int right = phone->visual.x + phone->visual.w;
    int bottom = phone->visual.y + phone->visual.h;
    if (door->visual.x + door->visual.w < right)
        right = door->visual.x + door->visual.w;
    if (door->visual.y + door->visual.h < bottom)
        bottom = door->visual.y + door->visual.h;

    for (int y = top; y < bottom && matched; y++) {
        for (int x = left; x < right; x++) {
            size_t offset = (size_t)y * CANVAS_W + (size_t)x;
            if (ui_object_hit(phone, x, y) && ui_object_hit(door, x, y) &&
                phone_layer.px[offset] != untouched) {
                found_overlap = true;
                if (rendered.px[offset] != phone_layer.px[offset]) {
                    matched = false;
                    break;
                }
            }
        }
    }

    canvas_free(&rendered);
    canvas_free(&phone_layer);
    return found_overlap && matched;
}

static int cmd_scene_test(void)
{
    const Object *item;
    const Object *door;
    const Object *hovered;
    int failures = 0;
    int ix = 0, iy = 0, dx = 0, dy = 0;
    int clear_x = 0, clear_y = 0;

    scene_init();
    test_expect(fallback_desk_z_order_matches_picking(),
                "fallback Desk props render in front of the exit door",
                &failures);
    hovered = scene_object(SCENE_DESK, 0);
    test_expect(object_hit_point(hovered, &ix, &iy),
                "Desk prop has an opaque hover point", &failures);
    send_mouse(IN_MOUSE_MOVE, ix, iy, 0, true);
    test_expect(strstr(scene_hover_text(), hovered->name) != NULL,
                "hover text identifies the physical Desk prop", &failures);
    test_expect(object_transparent_point(hovered, &clear_x, &clear_y),
                "Desk prop has transparent space inside its bounds", &failures);
    send_mouse(IN_MOUSE_MOVE, clear_x, clear_y, 0, true);
    test_expect(scene_hover_text()[0] == '\0',
                "transparent prop pixels show no hover text", &failures);
    send_mouse(IN_MOUSE_LEAVE, clear_x, clear_y, 0, false);
    test_expect(scene_hover_text()[0] == '\0',
                "mouse leave clears hover text", &failures);
    hovered = scene_object(SCENE_DESK, LAUNCH_NOTES);
    test_expect(strcmp(hovered->name, "Notepad") == 0 &&
                    object_hit_point(hovered, &ix, &iy),
                "Desk carries a physical Notepad prop", &failures);
    send_mouse(IN_MOUSE_MOVE, ix, iy, 0, true);
    test_expect(strcmp(scene_hover_text(), "Notepad - open") == 0,
                "Notepad hover identifies its direct action", &failures);

    scene_goto(SCENE_STOREROOM);
    item = scene_object(SCENE_STOREROOM, 1);
    test_expect(object_hit_point(item, &ix, &iy),
                "movable item has an opaque pickup point", &failures);

    send_mouse(IN_MOUSE_DOWN, ix, iy, 0, true);
    send_mouse(IN_MOUSE_MOVE, 1050, 390, 0, true);
    send_mouse(IN_MOUSE_UP, 1050, 390, 1, true);
    test_expect(item->container == 0 && !item->held,
                "wrong-button release cancels drag", &failures);

    send_mouse(IN_MOUSE_DOWN, ix, iy, 0, true);
    send_mouse(IN_MOUSE_MOVE, 1050, 390, 0, true);
    send_mouse(IN_MOUSE_UP, 1050, 390, 0, true);
    test_expect(item->container == 1 && !item->held,
                "left-button drag moves item between shelves", &failures);

    test_expect(object_hit_point(item, &ix, &iy),
                "moved item keeps an opaque pickup point", &failures);
    send_mouse(IN_MOUSE_DOWN, ix, iy, 0, true);
    send_mouse(IN_MOUSE_UP, 1050, 390, 0, false);
    test_expect(item->container == 1 && !item->held,
                "off-view release snaps item home", &failures);

    send_mouse(IN_MOUSE_DOWN, ix, iy, 0, true);
    scene_goto(SCENE_HALLWAY);
    test_expect(!item->held && !item->pressed,
                "scene reset cancels active drag", &failures);

    /* An unsupported second button still cancels the old left drag. */
    scene_goto(SCENE_STOREROOM);
    item = scene_object(SCENE_STOREROOM, 1);
    test_expect(object_hit_point(item, &ix, &iy),
                "restored item keeps an opaque pickup point", &failures);
    send_mouse(IN_MOUSE_DOWN, ix, iy, 0, true);
    send_mouse(IN_MOUSE_DOWN, ix + 4, iy + 4, 1, true);
    send_mouse(IN_MOUSE_UP, 450, 300, 0, true);
    test_expect(!item->held && item->container == ITEM_RIGHT_SHELF,
                "any second down cancels old gesture ownership", &failures);

    scene_goto(SCENE_HALLWAY);
    door = scene_object(SCENE_HALLWAY, 0);       /* Study door */
    test_expect(object_hit_point(door, &dx, &dy),
                "Hall door has a physical hit point", &failures);
    send_mouse(IN_MOUSE_DOWN, dx, dy, 0, true);
    send_mouse(IN_MOUSE_UP, dx, dy, 1, true);
    test_expect(!scene_busy() && scene_current() == SCENE_HALLWAY,
                "wrong-button release does not open door", &failures);

    send_mouse(IN_MOUSE_DOWN, dx, dy, 0, true);
    send_mouse(IN_MOUSE_UP, dx, dy, 0, true);
    test_expect(scene_busy(), "matching release begins door transition",
                &failures);
    test_expect(scene_hover_text()[0] == '\0',
                "transition suppresses hover text", &failures);
    scene_update(NAN);
    test_expect(scene_busy() && scene_current() == SCENE_HALLWAY,
                "non-finite delta cannot wedge or advance transition",
                &failures);
    for (int i = 0; i < 20; i++) scene_update(1.0 / 30.0);
    test_expect(!scene_busy() && scene_current() == SCENE_DESK,
                "door transition completes", &failures);

    /* A second down recovers ownership instead of leaving the first item
     * permanently held. */
    scene_goto(SCENE_STOREROOM);
    item = scene_object(SCENE_STOREROOM, 1);
    test_expect(object_hit_point(item, &ix, &iy),
                "item can be picked after scene reset", &failures);
    door = scene_object(SCENE_STOREROOM, 0);
    test_expect(object_hit_point(door, &dx, &dy),
                "Storeroom door has a physical hit point", &failures);
    send_mouse(IN_MOUSE_DOWN, ix, iy, 0, true);
    send_mouse(IN_MOUSE_DOWN, dx, dy, 0, true);
    send_mouse(IN_MOUSE_UP, dx, dy, 0, true);
    test_expect(!item->held && scene_busy(),
                "second down cancels old gesture and owns the new one",
                &failures);

    if (failures == 0) printf("scene-test: ok\n");
    return failures == 0 ? 0 : 1;
}

static void finish_transition(void)
{
    for (int i = 0; i < 24 && scene_busy(); i++)
        scene_update(1.0 / (double)PRESENT_HZ);
}

static const Object *find_panel_label(const char *label)
{
    for (int i = 0; i < scene_panel_object_count(); i++) {
        const Object *o = scene_panel_object(i);
        if (o != NULL && o->label != NULL && strcmp(o->label, label) == 0)
            return o;
    }
    return NULL;
}

static void drag_object_to(const Object *o, int x, int y)
{
    int ox, oy;
    if (!object_hit_point(o, &ox, &oy)) return;
    send_mouse(IN_MOUSE_DOWN, ox, oy, 0, true);
    send_mouse(IN_MOUSE_MOVE, x, y, 0, true);
    send_mouse(IN_MOUSE_UP, x, y, 0, true);
}

static int cmd_interaction_test(void)
{
    static const SceneId hall_targets[7] = {
        SCENE_DESK, SCENE_LIBRARY, SCENE_SERVER_ROOM, SCENE_BALCONY,
        SCENE_CLEANING_ROOM, SCENE_GAME_ROOM, SCENE_STOREROOM
    };
    static const LaunchToolId server_tools[7] = {
        LAUNCH_TOOL_LOGS, LAUNCH_TOOL_ACTIVITY, LAUNCH_TOOL_SETTINGS,
        LAUNCH_TOOL_STORAGE, LAUNCH_TOOL_NETWORK, LAUNCH_TOOL_SOFTWARE,
        LAUNCH_TOOL_PDF
    };
    static const int server_objects[7] = {1, 2, 3, 4, 5, 6, 8};
    static const LaunchToolId cleaning_tools[4] = {
        LAUNCH_TOOL_CLEAN_TEMP, LAUNCH_TOOL_CLEAN_TRASH,
        LAUNCH_TOOL_CLEAN_CACHE, LAUNCH_TOOL_CLEAN_ALL
    };
    static const LaunchToolId library_tools[5] = {
        LAUNCH_TOOL_DOC_START, LAUNCH_TOOL_DOC_ROOMS,
        LAUNCH_TOOL_DOC_INTERACTIONS, LAUNCH_TOOL_DOC_APPS,
        LAUNCH_TOOL_DOC_ENGINE
    };
    static const LaunchToolId balcony_tools[2] = {
        LAUNCH_TOOL_WEATHER, LAUNCH_TOOL_STARGAZING
    };
    static const struct {
        int bar_index;
        SceneId scene;
    } map_targets[] = {
        {0, SCENE_DESK},
        {1, SCENE_HALLWAY},
        {3, SCENE_STOREROOM},
        {4, SCENE_SERVER_ROOM},
        {5, SCENE_GAME_ROOM},
        {6, SCENE_CLEANING_ROOM}
    };
    int failures = 0;

    scene_init();
    for (int i = 0; i < 7; i++) {
        scene_goto(SCENE_HALLWAY);
        click_object(scene_object(SCENE_HALLWAY, i));
        finish_transition();
        test_expect(scene_current() == hall_targets[i],
                    "every Grand Gallery door reaches its room", &failures);
    }

    scene_goto(SCENE_DESK);
    for (int i = 0; i < 13; i++) {
        LaunchAppId app = LAUNCH_CLOCK;
        click_object(scene_object(SCENE_DESK, i));
        test_expect(!scene_panel_open(),
                    "Desk props never open an internal text panel", &failures);
        test_expect(scene_take_launch_request(&app) &&
                        app == (LaunchAppId)i,
                    "every Desk prop launches its mapped app directly",
                    &failures);
        test_expect(!scene_take_launch_request(&app),
                    "Desk launch request is consumed exactly once", &failures);
    }
    test_expect(scene_begin_web_boot() && scene_web_boot_active() &&
                    scene_busy(),
                "Computer boot sequence owns the scene after hidden launch",
                &failures);
    scene_update(3.7);
    test_expect(!scene_take_web_focus_request() &&
                    scene_web_boot_active(),
                "browser stays hidden until Kilix presents a browser frame",
                &failures);
    scene_mark_web_ready();
    scene_update(0.7);
    test_expect(!scene_take_web_focus_request() &&
                    scene_web_boot_active(),
                "render readiness starts but does not skip the monitor zoom",
                &failures);
    scene_update(0.2);
    test_expect(scene_take_web_focus_request() &&
                    !scene_take_web_focus_request(),
                "ready-frame zoom emits one exact browser focus request",
                &failures);
    scene_finish_web_boot();
    test_expect(!scene_web_boot_active() && !scene_busy(),
                "browser handoff releases scene input", &failures);

    scene_goto(SCENE_SERVER_ROOM);
    for (int i = 0; i < 7; i++) {
        LaunchToolId tool = LAUNCH_TOOL_COUNT;
        click_object(scene_object(SCENE_SERVER_ROOM, server_objects[i]));
        test_expect(!scene_panel_open() &&
                        scene_take_tool_request(&tool) &&
                        tool == server_tools[i],
                    "every Server Room console opens its real tool directly",
                    &failures);
    }

    scene_goto(SCENE_CLEANING_ROOM);
    for (int i = 0; i < 4; i++) {
        LaunchToolId tool = LAUNCH_TOOL_COUNT;
        click_object(scene_object(SCENE_CLEANING_ROOM, i + 1));
        test_expect(!scene_panel_open() &&
                        scene_take_tool_request(&tool) &&
                        tool == cleaning_tools[i],
                    "every Cleaning Room station opens Housekeeping directly",
                    &failures);
    }

    scene_goto(SCENE_LIBRARY);
    for (int i = 0; i < 5; i++) {
        LaunchToolId tool = LAUNCH_TOOL_COUNT;
        click_object(scene_object(SCENE_LIBRARY, i + 1));
        test_expect(!scene_panel_open() &&
                        scene_take_tool_request(&tool) &&
                        tool == library_tools[i],
                    "every physical Library volume opens a document viewer",
                    &failures);
    }

    scene_goto(SCENE_BALCONY);
    for (int i = 0; i < 2; i++) {
        LaunchToolId tool = LAUNCH_TOOL_COUNT;
        click_object(scene_object(SCENE_BALCONY, i + 1));
        test_expect(scene_take_tool_request(&tool) &&
                        tool == balcony_tools[i],
                    "Balcony instruments launch direct desktop apps",
                    &failures);
    }

    {
        static const GameCatalogEntry expanding[] = {
            {"doom", "Doom", GAME_LAUNCH_KILIX95, {0}},
            {"kilix-pong", "Kilix Pong", GAME_LAUNCH_KILIX95, {0}},
            {"mines", "Minesweeper", GAME_LAUNCH_KILIX95_BUILTIN, {0}}
        };
        const char *game_id = NULL;
        GameLaunchKind game_kind = GAME_LAUNCH_KILIX95;
        scene_set_game_catalog(expanding, 3, true);
        scene_goto(SCENE_GAME_ROOM);
        test_expect(scene_game_count() == 3 &&
                        scene_object_count(SCENE_GAME_ROOM) == 4,
                    "Game Room expands to the supplied catalog", &failures);
        click_object(scene_object(SCENE_GAME_ROOM, 2));
        test_expect(strcmp(scene_hover_text(), "Kilix Pong - open") == 0,
                    "Game media identifies its direct launch", &failures);
        test_expect(scene_take_game_request(&game_id, &game_kind) &&
                        strcmp(game_id, "kilix-pong") == 0 &&
                        game_kind == GAME_LAUNCH_KILIX95,
                    "Game media queues its matching Kilix 95 title",
                    &failures);
        scene_set_game_catalog(expanding, 1, true);
        test_expect(scene_game_count() == 1 &&
                        scene_object_count(SCENE_GAME_ROOM) == 2,
                    "Game Room retracts and reflows with the catalog",
                    &failures);
    }

    scene_goto(SCENE_DESK);
    click_object(scene_bar_object(2));
    test_expect(scene_lamp_enabled(), "Lamp toggles on", &failures);
    click_object(scene_bar_object(2));
    test_expect(!scene_lamp_enabled(), "Lamp toggles off", &failures);

    for (size_t i = 0; i < sizeof map_targets / sizeof map_targets[0]; i++) {
        scene_goto(SCENE_BALCONY);
        click_object(scene_bar_object(map_targets[i].bar_index));
        finish_transition();
        test_expect(scene_current() == map_targets[i].scene &&
                        !scene_panel_open(),
                    "house map shortcuts navigate without modal lists",
                    &failures);
    }

    scene_goto(SCENE_STOREROOM);
    drag_object_to(scene_object(SCENE_STOREROOM, 1), 1050, 390);
    test_expect(scene_item_place(0) == ITEM_RIGHT_SHELF,
                "Storeroom item moves to the right shelf", &failures);
    drag_object_to(scene_object(SCENE_STOREROOM, 1), 480, 390);
    test_expect(scene_item_place(0) == ITEM_LEFT_SHELF,
                "Storeroom item moves back to the left shelf", &failures);

    /* The Study laptop: click raises exactly one chooser request; the
     * injected chooser resolves rows by geometry and hands over exactly
     * one profile id. */
    {
        LaptopList profiles;
        const Object *laptop = scene_object(SCENE_DESK, 13);
        const char *profile_id = NULL;
        int laptop_x = 0;
        int laptop_y = 0;
        memset(&profiles, 0, sizeof profiles);
        profiles.count = 2;
        (void)snprintf(profiles.ids[0], sizeof profiles.ids[0], "alpha");
        (void)snprintf(profiles.ids[1], sizeof profiles.ids[1], "beta");
        scene_goto(SCENE_DESK);
        test_expect(laptop != NULL && laptop->kind == OBJ_LAPTOP &&
                        strcmp(laptop->name, "Laptop") == 0,
                    "the Study keeps a laptop beside the postcard",
                    &failures);
        test_expect(object_hit_point(laptop, &laptop_x, &laptop_y),
                    "laptop responds on its visible pixels", &failures);
        test_expect(!scene_take_laptop_menu_request(),
                    "no chooser request before the laptop is touched",
                    &failures);
        click_object(laptop);
        test_expect(scene_take_laptop_menu_request() &&
                        !scene_take_laptop_menu_request(),
                    "laptop click raises one chooser request", &failures);
        scene_set_laptop_profiles(&profiles);
        scene_open_laptop_menu();
        test_expect(scene_laptop_menu_open(),
                    "chooser opens with injected profiles", &failures);
        /* Two profiles: card is 792x330 at (324, 291); the first profile
         * row spans y 381..452. */
        send_mouse(IN_MOUSE_DOWN, 720, 417, 0, true);
        send_mouse(IN_MOUSE_UP, 720, 417, 0, true);
        test_expect(!scene_laptop_menu_open() &&
                        scene_take_laptop_request(&profile_id) &&
                        profile_id != NULL &&
                        strcmp(profile_id, "alpha") == 0,
                    "choosing the first row launches profile alpha",
                    &failures);
        test_expect(!scene_take_laptop_request(&profile_id),
                    "laptop launch request is consumed exactly once",
                    &failures);
        scene_open_laptop_menu();
        send_mouse(IN_MOUSE_DOWN, 20, 40, 0, true);
        test_expect(!scene_laptop_menu_open() &&
                        !scene_take_laptop_request(&profile_id),
                    "clicking outside the card dismisses without launching",
                    &failures);
        scene_open_laptop_menu();
        send_mouse(IN_MOUSE_DOWN, 720, 417, 0, true);
        send_mouse(IN_MOUSE_UP, 720, 417 + 72, 0, true);
        test_expect(scene_laptop_menu_open() &&
                        !scene_take_laptop_request(&profile_id),
                    "releasing on a different row arms nothing", &failures);
        send_mouse(IN_MOUSE_DOWN, 720, 417 + 2 * 72, 0, true);
        send_mouse(IN_MOUSE_UP, 720, 417 + 2 * 72, 0, true);
        test_expect(!scene_laptop_menu_open() &&
                        !scene_take_laptop_request(&profile_id),
                    "the Close row dismisses without launching", &failures);

        /* The master breaker. Its rows ARM before they act, so no single
         * touch anywhere in the mansion can end the session or the
         * machine. Card is 696x402 at (372, 255): row 0 spans y 345..416,
         * row 1 417..488, the Close row 561..632. */
        {
            const Object *breaker = NULL;
            LaunchPowerId power = LAUNCH_POWER_COUNT;
            int bx = 0, by = 0;
            scene_goto(SCENE_SERVER_ROOM);
            breaker = scene_object(SCENE_SERVER_ROOM,
                                   SCENE_SERVER_BREAKER_INDEX);
            test_expect(breaker != NULL && breaker->kind == OBJ_BREAKER &&
                            strcmp(breaker->name,
                                   "Master breaker panel") == 0,
                        "the Server Room wall carries a master breaker",
                        &failures);
            test_expect(object_hit_point(breaker, &bx, &by),
                        "breaker responds on its visible pixels", &failures);
            test_expect(!scene_power_menu_open(),
                        "no power menu before the breaker is touched",
                        &failures);
            click_object(breaker);
            test_expect(scene_power_menu_open(),
                        "touching the breaker opens the power menu",
                        &failures);
            send_mouse(IN_MOUSE_DOWN, 720, 381, 0, true);
            send_mouse(IN_MOUSE_UP, 720, 381, 0, true);
            test_expect(scene_power_menu_open() &&
                            !scene_take_power_request(&power),
                        "the first touch of a power row only arms it",
                        &failures);
            send_mouse(IN_MOUSE_DOWN, 720, 381, 0, true);
            send_mouse(IN_MOUSE_UP, 720, 381, 0, true);
            test_expect(!scene_power_menu_open() &&
                            scene_take_power_request(&power) &&
                            power == LAUNCH_POWER_LOGOUT,
                        "the second touch of the same row acts", &failures);
            test_expect(!scene_take_power_request(&power),
                        "the power request is consumed exactly once",
                        &failures);
            /* Arming one row then touching another must leave nothing
               armed and act on nothing. */
            scene_open_power_menu();
            send_mouse(IN_MOUSE_DOWN, 720, 381, 0, true);
            send_mouse(IN_MOUSE_UP, 720, 381, 0, true);
            send_mouse(IN_MOUSE_DOWN, 720, 453, 0, true);
            send_mouse(IN_MOUSE_UP, 720, 453, 0, true);
            test_expect(scene_power_menu_open() &&
                            !scene_take_power_request(&power),
                        "arming a second row acts on neither", &failures);
            send_mouse(IN_MOUSE_DOWN, 720, 597, 0, true);
            send_mouse(IN_MOUSE_UP, 720, 597, 0, true);
            test_expect(!scene_power_menu_open() &&
                            !scene_take_power_request(&power),
                        "the breaker's Close row leaves the power alone",
                        &failures);
            scene_open_power_menu();
            send_mouse(IN_MOUSE_DOWN, 20, 40, 0, true);
            test_expect(!scene_power_menu_open() &&
                            !scene_take_power_request(&power),
                        "pressing outside the breaker card dismisses it",
                        &failures);
            scene_goto(SCENE_DESK);
        }

        /* Running state, injected exactly like the profile list: the lid
         * tweens closed -> half-open -> open, and a running profile's
         * row asks to CLOSE the session instead of opening a second. */
        test_expect(laptop->container == 0,
                    "the laptop starts with its lid closed", &failures);
        {
            bool running[LAPTOP_PROFILES_MAX] = {true, false};
            scene_set_laptop_state(true, running, profiles.count);
        }
        scene_update(0.05);
        test_expect(scene_object(SCENE_DESK, 13)->container == 1,
                    "the opening lid passes the half-open frame",
                    &failures);
        scene_update(0.25);
        test_expect(scene_object(SCENE_DESK, 13)->container == 2,
                    "a live session settles the lid fully open",
                    &failures);
        scene_open_laptop_menu();
        send_mouse(IN_MOUSE_DOWN, 720, 417, 0, true);
        send_mouse(IN_MOUSE_UP, 720, 417, 0, true);
        test_expect(!scene_laptop_menu_open() &&
                        !scene_take_laptop_request(&profile_id) &&
                        scene_take_laptop_close_request(&profile_id) &&
                        profile_id != NULL &&
                        strcmp(profile_id, "alpha") == 0,
                    "choosing a running row raises one close request",
                    &failures);
        test_expect(!scene_take_laptop_close_request(&profile_id),
                    "the close request is consumed exactly once",
                    &failures);
        scene_set_laptop_state(false, NULL, 0);
        scene_update(0.10);
        test_expect(scene_object(SCENE_DESK, 13)->container == 1,
                    "the closing lid reverses through half-open",
                    &failures);
        scene_update(0.25);
        test_expect(scene_object(SCENE_DESK, 13)->container == 0,
                    "an ended session closes the lid again", &failures);
    }

    if (failures == 0) printf("interaction-test: ok\n");
    return failures == 0 ? 0 : 1;
}

static int cmd_audio_trigger_test(void)
{
    int failures = 0;
    const Object *object;

    scene_init();

    object = scene_object(SCENE_DESK, 0);
    {
        int x = 0;
        int y = 0;
        sound_reset_trace();
        test_expect(object_hit_point(object, &x, &y),
                    "Desk object has an opaque audio-test point", &failures);
        send_mouse(IN_MOUSE_DOWN, x, y, 0, true);
        send_mouse(IN_MOUSE_MOVE, object->visual.x - 12, y, 0, true);
        send_mouse(IN_MOUSE_UP, object->visual.x - 12, y, 0, true);
        test_expect(sound_trace_count(SOUND_TOUCH) == 1,
                    "touch fires once on accepted down", &failures);
        test_expect(sound_trace_count(SOUND_ERROR) == 1,
                    "error fires once on an attempted slide", &failures);
    }

    sound_reset_trace();
    click_object(scene_bar_object(2));
    test_expect(sound_trace_count(SOUND_SWITCH) == 1 &&
                    scene_lamp_enabled(),
                "switch fires after Lamp state commits", &failures);
    click_object(scene_bar_object(2));

    scene_goto(SCENE_HALLWAY);
    sound_reset_trace();
    click_object(scene_object(SCENE_HALLWAY, 0));
    finish_transition();
    test_expect(sound_trace_count(SOUND_DOOR) == 1,
                "door fires on an accepted room transition", &failures);

    scene_goto(SCENE_STOREROOM);
    sound_reset_trace();
    drag_object_to(scene_object(SCENE_STOREROOM, 1), 1050, 390);
    test_expect(sound_trace_count(SOUND_CONTAIN) == 1,
                "contain fires on a changed shelf", &failures);

    scene_goto(SCENE_SERVER_ROOM);
    sound_reset_trace();
    click_object(scene_object(SCENE_SERVER_ROOM, 1));
    test_expect(sound_trace_count(SOUND_TOUCH) == 1,
                "a baked console has ordinary physical touch feedback",
                &failures);

    if (failures == 0)
        printf("audio-trigger-test: ok (direct room interactions)\n");
    return failures == 0 ? 0 : 1;
}

static int cmd_audio_test(const char *argv0)
{
    int failures = 0;
    int16_t block[4096];

    if (!sound_validate_assets(argv0, true)) return 1;
    for (int cue = 0; cue < SOUND_COUNT; cue++) {
        int64_t energy = 0;
        sound_set_enabled(true);
        test_expect(sound_init(argv0, true),
                    "offline mixer starts with complete bank", &failures);
        sound_reset_trace();
        sound_play((SoundCue)cue);
        for (int chunk = 0; chunk < 12; chunk++) {
            memset(block, 0, sizeof block);
            test_expect(sound_mix_offline(block,
                                          sizeof block / sizeof block[0]),
                        "offline mix call succeeds", &failures);
            for (size_t i = 0; i < sizeof block / sizeof block[0]; i++)
                energy += block[i] < 0 ? -(int64_t)block[i] : block[i];
        }
        test_expect(energy > 0, "offline cue renders nonzero PCM", &failures);
        test_expect(sound_trace_count((SoundCue)cue) == 1,
                    "offline cue trace increments once", &failures);
        sound_shutdown();
    }

    sound_set_enabled(true);
    test_expect(sound_init(argv0, true), "muted offline mixer starts",
                &failures);
    sound_set_enabled(false);
    sound_reset_trace();
    sound_play(SOUND_TOUCH);
    memset(block, 0x7f, sizeof block);
    test_expect(sound_mix_offline(block, sizeof block / sizeof block[0]),
                "muted offline mix call succeeds", &failures);
    for (size_t i = 0; i < sizeof block / sizeof block[0]; i++)
        test_expect(block[i] == 0, "muted offline mix is silent", &failures);
    test_expect(sound_trace_count(SOUND_TOUCH) == 1,
                "muted requests remain traceable", &failures);
    sound_shutdown();

    if (failures == 0) printf("audio-test: ok (12 strict WAVs, offline mix)\n");
    return failures == 0 ? 0 : 1;
}

/* The visual gate proves generated color reaches the final canvas without a
 * grayscale conversion and that every scene remains fully opaque. */
static int cmd_visual_test(const char *argv0)
{
    int failures = 0;

    if (!canvas_init(&canvas, CANVAS_W, CANVAS_H)) return 2;
    test_expect(art_init(argv0, true), "generated art bundle loads", &failures);
    scene_init();
    for (int s = 0; s < SCENE_COUNT; s++) {
        int bad_x = 0, bad_y = 0;
        scene_goto((SceneId)s);
        scene_draw(&canvas);
        draw_cursor(&canvas, 100, 100);
        if (!draw_canvas_opaque(&canvas, &bad_x, &bad_y)) {
            printf("FAIL %s: transparent pixel at %d,%d\n",
                   scene_name((SceneId)s), bad_x, bad_y);
            failures++;
        }
        test_expect(draw_chromatic_pixels(&canvas) > 10000u,
                    "scene contains substantial full color", &failures);
    }
    scene_goto(SCENE_DESK);
    scene_draw(&canvas);
    test_expect(draw_chromatic_pixels(&canvas) > 90000u,
                "generated Desk remains chromatic", &failures);
    for (int i = 0; i < 13; i++) {
        const Object *o = scene_object(SCENE_DESK, i);
        int hit_x = 0;
        int hit_y = 0;
        int clear_x = 0;
        int clear_y = 0;
        test_expect(object_hit_point(o, &hit_x, &hit_y),
                    "generated Desk prop has a semantic hit pixel", &failures);
        test_expect(object_transparent_point(o, &clear_x, &clear_y),
                    "generated Desk prop has a transparent bbox pixel",
                    &failures);
        if (object_transparent_point(o, &clear_x, &clear_y))
            test_expect(!ui_object_hit(o, clear_x, clear_y),
                        "transparent Desk prop pixel is not clickable",
                        &failures);
    }
    scene_goto(SCENE_GAME_ROOM);
    for (int i = 1; i < scene_object_count(SCENE_GAME_ROOM); i++) {
        const Object *o = scene_object(SCENE_GAME_ROOM, i);
        int hit_x = 0;
        int hit_y = 0;
        int clear_x = 0;
        int clear_y = 0;
        test_expect(o->kind == OBJ_GAME_MEDIA,
                    "Game Room catalog object uses generated media",
                    &failures);
        test_expect((o->label == NULL || o->label[0] == '\0') &&
                        game_icon_valid(o->game_icon),
                    "Game media draws an icon instead of a text plaque",
                    &failures);
        test_expect(object_hit_point(o, &hit_x, &hit_y),
                    "generated game media has an alpha hit pixel", &failures);
        test_expect(object_transparent_point(o, &clear_x, &clear_y),
                    "generated game media has a transparent bbox pixel",
                    &failures);
        if (object_transparent_point(o, &clear_x, &clear_y))
            test_expect(!ui_object_hit(o, clear_x, clear_y),
                        "transparent game-media pixel is not clickable",
                        &failures);
    }
    /* The optional small-prop atlas is validated only when present; its
     * absence is the review-pending state and every prop then keeps its
     * procedural drawing (already proven by the scenes above). */
    if (art_mansion_items_ready()) {
        const Object *item = scene_object(SCENE_STOREROOM, 1);
        const Object *laptop = scene_object(SCENE_DESK, 13);
        int hit_x = 0;
        int hit_y = 0;
        int clear_x = 0;
        int clear_y = 0;
        test_expect(item != NULL && object_hit_point(item, &hit_x, &hit_y),
                    "generated Storeroom prop has an alpha hit pixel",
                    &failures);
        test_expect(item != NULL &&
                        object_transparent_point(item, &clear_x, &clear_y) &&
                        !ui_object_hit(item, clear_x, clear_y),
                    "transparent Storeroom prop pixel is not clickable",
                    &failures);
        test_expect(laptop != NULL &&
                        object_hit_point(laptop, &hit_x, &hit_y),
                    "generated laptop has an alpha hit pixel", &failures);
        printf("visual-test: optional mansion-items atlas loaded\n");
    } else {
        printf("visual-test: optional mansion-items atlas absent "
               "(procedural props)\n");
    }
    /* The breaker face stands alone: it composes with no other atlas, so
     * it is proven on its own terms rather than inside the block above. */
    if (art_breaker_ready()) {
        const Object *breaker =
            scene_object(SCENE_SERVER_ROOM, SCENE_SERVER_BREAKER_INDEX);
        int hit_x = 0;
        int hit_y = 0;
        int clear_x = 0;
        int clear_y = 0;
        test_expect(breaker != NULL &&
                        object_hit_point(breaker, &hit_x, &hit_y),
                    "generated breaker has an alpha hit pixel", &failures);
        test_expect(breaker != NULL &&
                        object_transparent_point(breaker, &clear_x,
                                                 &clear_y) &&
                        !ui_object_hit(breaker, clear_x, clear_y),
                    "transparent breaker pixel is not clickable", &failures);
        printf("visual-test: optional breaker face loaded\n");
    } else {
        printf("visual-test: optional breaker face absent "
               "(procedural panel)\n");
    }
    art_shutdown();
    canvas_free(&canvas);
    if (failures == 0)
        printf("visual-test: ok (%d opaque full-color scenes)\n", SCENE_COUNT);
    return failures == 0 ? 0 : 1;
}

static int cmd_font_test(void)
{
    int failures = 0;
    int ink = 0;

    /* Cap's authored 7x14 face, drawn by soft-raster and selected by name so
     * a change of default in the shared module cannot silently restyle this
     * desktop. The advance is what the layout is built on, so it is pinned;
     * coverage is checked by drawing rather than by asking, because a glyph
     * the module renders blank would pass a lookup and still leave a hole. */
    test_expect(draw_text_height() == 14 * CANVAS_SCALE,
                "text cell is the scaled 7x14 authored face", &failures);
    test_expect(draw_text_width("Desk") == 4 * 8 * CANVAS_SCALE,
                "text advance is 8px per character, scaled", &failures);
    test_expect(draw_text_width("") == 0, "empty string has no width",
                &failures);

    if (!canvas_init(&canvas, CANVAS_W, CANVAS_H)) return 2;
    draw_clear(&canvas, MC_WHITE);
    draw_text(&canvas, 4, 4, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", MC_BLACK);
    draw_text(&canvas, 4, 24, "abcdefghijklmnopqrstuvwxyz", MC_BLACK);
    draw_text(&canvas, 4, 44, "0123456789 !?.,:;+-=/()[]{}", MC_BLACK);
    for (int i = 0; i < canvas.w * canvas.h; i++)
        if ((canvas.px[i] & 0xffffffu) == MC_BLACK) ink++;
    test_expect(ink > 500, "font render contains substantial ink", &failures);
    test_expect(draw_canvas_opaque(&canvas, NULL, NULL),
                "font render is opaque", &failures);
    canvas_free(&canvas);

    if (failures == 0) printf("font-test: ok\n");
    return failures == 0 ? 0 : 1;
}

static int cmd_launcher_test(void)
{
    LaunchAppId app = LAUNCH_WEB;
    LaunchToolId tool = LAUNCH_TOOL_COUNT;
    int failures = 0;

    test_expect(launcher_selftest(),
                "shell-free launcher verifies plans and reaps its own helper",
                &failures);
    scene_init();
    for (int i = 0; i < LAUNCH_APP_COUNT; i++) {
        scene_goto(SCENE_DESK);
        click_object(scene_object(SCENE_DESK, i));
        test_expect(!scene_panel_open() &&
                        scene_take_launch_request(&app) &&
                        app == (LaunchAppId)i,
                    "Desk prop queues its exact direct mapping", &failures);
        test_expect(!scene_take_launch_request(&app),
                    "app launch request is take-and-clear", &failures);
    }

    scene_goto(SCENE_SERVER_ROOM);
    click_object(scene_object(SCENE_SERVER_ROOM, 1));
    test_expect(scene_take_tool_request(&tool) &&
                    tool == LAUNCH_TOOL_LOGS,
                "Server monitor queues its live console", &failures);
    click_object(scene_object(SCENE_SERVER_ROOM, 8));
    test_expect(scene_take_tool_request(&tool) &&
                    tool == LAUNCH_TOOL_PDF,
                "Server PDF terminal queues the shared catalog app",
                &failures);
    scene_goto(SCENE_CLEANING_ROOM);
    click_object(scene_object(SCENE_CLEANING_ROOM, 4));
    test_expect(scene_take_tool_request(&tool) &&
                    tool == LAUNCH_TOOL_CLEAN_ALL,
                "Cleaning terminal queues bounded Housekeeping", &failures);
    scene_goto(SCENE_LIBRARY);
    click_object(scene_object(SCENE_LIBRARY, 1));
    test_expect(scene_take_tool_request(&tool) &&
                    tool == LAUNCH_TOOL_DOC_START,
                "Library volume queues the real document viewer", &failures);

    if (failures == 0)
        printf("launcher-test: ok (13 direct Desk apps, fixed mansion tools, authenticated terminal plans)\n");
    return failures == 0 ? 0 : 1;
}

static int cmd_game_catalog_test(const char *argv0)
{
    int failures = 0;
    test_expect(game_catalog_selftest(argv0),
                "bounded Kilix 95 catalog helper protocol", &failures);
    if (failures == 0)
        printf("game-catalog-test: ok (fixture discovery, live reflow)\n");
    return failures == 0 ? 0 : 1;
}

static bool write_render_fixture(const char *dir, const char *slug)
{
    char path[1024];
    sr_canvas sc;
    int bad_x = 0, bad_y = 0;

    scene_draw(&canvas);
    if (!draw_canvas_opaque(&canvas, &bad_x, &bad_y)) {
        printf("FAIL render %s: transparent pixel at %d,%d\n",
               slug, bad_x, bad_y);
        return false;
    }
    int path_length = snprintf(path, sizeof path, "%s/%s.ppm", dir, slug);
    if (path_length < 0 || (size_t)path_length >= sizeof path) {
        printf("FAIL render: output path is too long for %s\n", slug);
        return false;
    }
    sr_canvas_wrap(&sc, canvas.px, canvas.w, canvas.h);
    if (!sr_write_ppm(&sc, path)) {
        printf("FAIL render: cannot write %s\n", path);
        return false;
    }
    return true;
}

static int cmd_render_test(const char *argv0, const char *dir)
{
    static const char *const base_slugs[SCENE_COUNT] = {
        "base-desk", "base-hallway", "base-storeroom", "base-server-room",
        "base-game-room", "base-library", "base-cleaning-room",
        "base-balcony"
    };
    int written = 0;

    if (dir == NULL) return 2;
    if (!canvas_init(&canvas, CANVAS_W, CANVAS_H)) return 2;
    if (!art_init(argv0, true)) {
        canvas_free(&canvas);
        return 1;
    }
    /* Hash-pinned frames must not depend on the OPTIONAL small-prop
     * atlas, which is absent while generated art awaits review; these
     * fixtures always render the procedural props. --render-review keeps
     * the atlas so reviewers see the shipped composition. */
    art_set_extra_items_enabled(false);
    scene_init();

    for (int s = 0; s < SCENE_COUNT; s++) {
        scene_goto((SceneId)s);
        if (!write_render_fixture(dir, base_slugs[s])) {
            art_shutdown();
            canvas_free(&canvas);
            return 1;
        }
        written++;
    }

    scene_goto(SCENE_DESK);
    {
        int hover_x = 0;
        int hover_y = 0;
        if (!object_hit_point(scene_object(SCENE_DESK, 0),
                              &hover_x, &hover_y))
            goto render_fail;
        send_mouse(IN_MOUSE_MOVE, hover_x, hover_y, 0, true);
    }
    if (!write_render_fixture(dir, "state-desk-hover")) goto render_fail;
    written++;

    scene_goto(SCENE_DESK);
    if (!scene_begin_web_boot()) goto render_fail;
    scene_update(1.55);
    if (!write_render_fixture(dir, "state-desk-web-boot"))
        goto render_fail;
    written++;
    scene_mark_web_ready();
    scene_update(1.65);
    if (!write_render_fixture(dir, "state-desk-web-zoom"))
        goto render_fail;
    written++;
    scene_finish_web_boot();

    scene_goto(SCENE_SERVER_ROOM);
    {
        int hover_x = 0;
        int hover_y = 0;
        if (!object_hit_point(scene_object(SCENE_SERVER_ROOM, 1),
                              &hover_x, &hover_y))
            goto render_fail;
        send_mouse(IN_MOUSE_MOVE, hover_x, hover_y, 0, true);
    }
    if (!write_render_fixture(dir, "state-server-hover")) goto render_fail;
    written++;

    scene_goto(SCENE_CLEANING_ROOM);
    {
        int hover_x = 0;
        int hover_y = 0;
        if (!object_hit_point(scene_object(SCENE_CLEANING_ROOM, 4),
                              &hover_x, &hover_y))
            goto render_fail;
        send_mouse(IN_MOUSE_MOVE, hover_x, hover_y, 0, true);
    }
    if (!write_render_fixture(dir, "state-cleaning-hover")) goto render_fail;
    written++;

    scene_goto(SCENE_GAME_ROOM);
    {
        int hover_x = 0;
        int hover_y = 0;
        if (!object_hit_point(scene_object(SCENE_GAME_ROOM, 1),
                              &hover_x, &hover_y))
            goto render_fail;
        send_mouse(IN_MOUSE_MOVE, hover_x, hover_y, 0, true);
    }
    if (!write_render_fixture(dir, "state-game-hover")) goto render_fail;
    written++;

    scene_goto(SCENE_STOREROOM);
    drag_object_to(scene_object(SCENE_STOREROOM, 1), 1050, 390);
    if (!write_render_fixture(dir, "state-store-moved")) goto render_fail;
    written++;

    art_shutdown();
    canvas_free(&canvas);
    printf("render-test: wrote %d frames to %s\n", written, dir);
    return 0;

render_fail:
    art_shutdown();
    canvas_free(&canvas);
    return 1;
}

/* Broad visual coverage for development and release review.  The stable
 * render-test fixtures above stay intentionally small and hash-pinned; this
 * pass renders every modal surface so a panel can no longer drift, clip, or
 * lose full-color output without the release gate seeing it. */
static int cmd_render_review(const char *argv0, const char *dir)
{
    static const char *const panel_slugs[PANEL_COUNT] = {
        NULL,
        "review-panel-clock", "review-panel-inbox", "review-panel-outbox",
        "review-panel-mail", "review-panel-profile", "review-panel-notes",
        "review-panel-dates", "review-panel-cards", "review-panel-files",
        "review-panel-phone", "review-panel-paper",
        "review-panel-calculator", "review-panel-web",
        "review-panel-stamper", "review-panel-tote",
        "review-panel-tool-holder", "review-panel-keyboard",
        "review-panel-trash", "review-panel-library-book"
    };
    int written = 0;

    if (dir == NULL) return 2;
    if (!canvas_init(&canvas, CANVAS_W, CANVAS_H)) return 2;
    if (!art_init(argv0, true)) {
        canvas_free(&canvas);
        return 1;
    }

    for (int id = PANEL_CLOCK; id < PANEL_COUNT; id++) {
        scene_init();
        scene_goto(SCENE_DESK);
        panel_open((PanelId)id);
        if (!write_render_fixture(dir, panel_slugs[id])) goto review_fail;
        written++;
    }

    scene_init();
    panel_set_mail_target("thunderbird");
    scene_goto(SCENE_DESK);
    panel_open(PANEL_MAIL);
    if (!write_render_fixture(dir, "review-panel-mail-configured"))
        goto review_fail;
    written++;
    click_object(find_panel_label("Setup"));
    scene_set_pointer(0, 0, false);
    if (!write_render_fixture(dir, "review-panel-mail-registration"))
        goto review_fail;
    written++;
    panel_set_mail_target(NULL);

    scene_init();
    scene_goto(SCENE_DESK);
    panel_open(PANEL_CLOCK);
    panel_set_launch_status("No matching desktop app is installed.", false);
    if (!write_render_fixture(dir, "review-panel-clock-launch-status"))
        goto review_fail;
    written++;

    panel_set_launch_status("Started Clock with gnome-clocks.", true);
    if (!write_render_fixture(dir, "review-panel-clock-launch-success"))
        goto review_fail;
    written++;

    scene_init();
    scene_goto(SCENE_DESK);
    panel_open(PANEL_PHONE);
    click_object(find_panel_label("Ring"));
    if (!write_render_fixture(dir, "review-panel-phone-ringing"))
        goto review_fail;
    written++;

    scene_init();
    panel_set_phone_unavailable(
        "No VoIP or phone service is configured.");
    scene_goto(SCENE_DESK);
    panel_open(PANEL_PHONE);
    if (!write_render_fixture(dir, "review-panel-phone-unavailable"))
        goto review_fail;
    written++;
    panel_set_phone_unavailable(NULL);

    {
        static const GameCatalogEntry compact[] = {
            {"doom", "Doom", GAME_LAUNCH_KILIX95, {0}},
            {"kilix-pong", "Kilix Pong", GAME_LAUNCH_KILIX95, {0}},
            {"mines", "Minesweeper", GAME_LAUNCH_KILIX95_BUILTIN, {0}}
        };
        scene_init();
        scene_set_game_catalog(compact, 3, true);
        scene_goto(SCENE_GAME_ROOM);
        if (!write_render_fixture(dir, "review-game-catalog-compact"))
            goto review_fail;
        written++;
        scene_set_game_catalog(NULL, 0, true);
        if (!write_render_fixture(dir, "review-game-catalog-empty"))
            goto review_fail;
        written++;
    }

    scene_init();
    scene_goto(SCENE_DESK);
    panel_open(PANEL_OUTBOX);
    click_object(find_panel_label("Send"));
    if (!write_render_fixture(dir, "review-panel-outbox-sent"))
        goto review_fail;
    written++;

    scene_init();
    panel_set_storage_counts(1, 0);
    scene_goto(SCENE_STOREROOM);
    panel_open(PANEL_TOTE);
    if (!write_render_fixture(dir, "review-panel-tote-nonempty"))
        goto review_fail;
    written++;

    scene_init();
    panel_set_storage_counts(0, 1);
    scene_goto(SCENE_STOREROOM);
    panel_open(PANEL_TRASH);
    if (!write_render_fixture(dir, "review-panel-trash-nonempty"))
        goto review_fail;
    written++;

    art_shutdown();
    canvas_free(&canvas);
    printf("render-review: wrote %d review frames to %s\n", written, dir);
    return 0;

review_fail:
    art_shutdown();
    canvas_free(&canvas);
    return 1;
}

/* Deterministic synthetic-input soak: same seed and step count must always
 * produce the same digest, on any compiler and any terminal. */
static int cmd_selftest(uint32_t seed, int steps)
{
    input_event ev;
    uint32_t acc = 2166136261u;

    rng_state = seed;
    scene_init();
    for (int i = 0; i < steps; i++) {
        int x = (int)(rng_next() % (uint32_t)CANVAS_W);
        int y = (int)(rng_next() % (uint32_t)CANVAS_H);
        int drift_x = (int)(rng_next() % 64u) - 32;
        int drift_y = (int)(rng_next() % 64u) - 32;

        memset(&ev, 0, sizeof ev);
        ev.kind = IN_MOUSE_DOWN;
        ev.mx = (int16_t)x;
        ev.my = (int16_t)y;
        ev.in_view = true;
        scene_handle(&ev);

        ev.kind = IN_MOUSE_MOVE;
        ev.mx = (int16_t)iclampi(x + drift_x, 0, CANVAS_W - 1);
        ev.my = (int16_t)iclampi(y + drift_y, 0, CANVAS_H - 1);
        scene_handle(&ev);

        ev.kind = IN_MOUSE_UP;
        scene_handle(&ev);

        /* Let any door transition run to completion. */
        for (int f = 0; f < 16; f++) scene_update(1.0 / (double)PRESENT_HZ);

        /* Accumulate the state after every step, not just at the end. A
         * final-state digest is nearly worthless here: three items over two
         * shelves gives only eight terminal configurations, so unrelated
         * seeds collide constantly and a behavioural regression hides. */
        acc ^= scene_digest();
        acc *= 16777619u;
    }
    printf("selftest: seed=%u steps=%d digest=%08x scene=%s\n",
           seed, steps, acc, scene_name(scene_current()));
    return 0;
}

/* ---- Interactive ---- */

static void launch_and_report(LaunchAppId app)
{
    char status[64];
    if (app == LAUNCH_WEB) {
        if (launcher_begin_web()) {
            if (scene_begin_web_boot()) {
                (void)snprintf(status, sizeof status,
                               "Loading Web in the background.");
                panel_set_launch_status(status, true);
                sound_play(SOUND_MAGIC);
                return;
            }
            (void)launcher_focus_web();
            (void)snprintf(status, sizeof status, "%s",
                           "The computer could not begin its boot sequence.");
        } else {
            /* No graphical browser, so the computer starts the text one
             * instead of refusing. It is a terminal program, so it opens in
             * a tab directly and skips the capture handshake entirely. */
            if (launcher_open_text_browser()) {
                (void)snprintf(status, sizeof status, "%s",
                               "Opened the text browser in a tab.");
                panel_set_launch_status(status, true);
                sound_play(SOUND_MAGIC);
                return;
            }
            (void)snprintf(status, sizeof status, "%s",
                           launcher_last_error()[0] != '\0'
                               ? launcher_last_error()
                               : "The computer could not start the browser.");
        }
        panel_set_launch_status(status, false);
        scene_set_status(status, false);
        sound_play(SOUND_ERROR);
        return;
    }
    if (launcher_open(app)) {
        if (app == LAUNCH_WEB ||
            (app == LAUNCH_MAIL && launcher_mail_configured()))
            (void)snprintf(status, sizeof status,
                           "Opened %s in a Kilix tab.",
                           launcher_app_title(app));
        else
            (void)snprintf(status, sizeof status, "Started %s with %s.",
                           launcher_app_title(app), launcher_last_program());
        panel_set_launch_status(status, true);
        scene_set_status(status, true);
        sound_play(SOUND_MAGIC);
    } else {
        if (launcher_enabled() && launcher_last_error()[0] != '\0')
            (void)snprintf(status, sizeof status, "%s",
                           launcher_last_error());
        else
            (void)snprintf(status, sizeof status, "%s",
                           launcher_enabled()
                               ? "No matching desktop app is installed."
                               : "Desktop app launching is disabled.");
        panel_set_launch_status(status, false);
        scene_set_status(status, false);
        sound_play(SOUND_ERROR);
    }
}

static void service_web_focus(void)
{
    if (!scene_take_web_focus_request()) return;
    if (!launcher_focus_web()) {
        const char *error = launcher_last_error()[0] != '\0'
                                ? launcher_last_error()
                                : "The browser tab could not be focused.";
        panel_set_launch_status(error, false);
        scene_set_status(error, false);
        sound_play(SOUND_ERROR);
    }
    scene_finish_web_boot();
}

static void service_web_readiness(void)
{
    LauncherWebStatus status;
    const char *error;

    if (!scene_web_boot_active()) return;
    status = launcher_web_status();
    if (status == LAUNCHER_WEB_READY) {
        scene_mark_web_ready();
        return;
    }
    if (status != LAUNCHER_WEB_FAILED) return;

    error = launcher_last_error()[0] != '\0'
                ? launcher_last_error()
                : "The browser did not render a usable frame.";
    panel_set_launch_status(error, false);
    scene_set_status(error, false);
    launcher_discard_web();
    scene_finish_web_boot();
    sound_play(SOUND_ERROR);
}

/* The breaker's chosen action. Success is deliberately quiet about what
 * happens next: the session or the machine is already on its way out, and
 * a cheerful "Opened" would be the last thing a user reads. */
static void run_power_and_report(LaunchPowerId action)
{
    char status[96];
    if (launcher_power(action)) {
        (void)snprintf(status, sizeof status, "%s...",
                       launcher_power_title(action));
        panel_set_launch_status(status, true);
        scene_set_status(status, true);
        sound_play(SOUND_SWITCH);
    } else {
        (void)snprintf(status, sizeof status, "%s",
                       launcher_last_error()[0] != '\0'
                           ? launcher_last_error()
                           : "That power action is unavailable.");
        panel_set_launch_status(status, false);
        scene_set_status(status, false);
        sound_play(SOUND_ERROR);
    }
}

static void launch_tool_and_report(LaunchToolId tool)
{
    char status[96];
    if (launcher_open_tool(tool)) {
        (void)snprintf(status, sizeof status, "Opened %s.",
                       launcher_tool_title(tool));
        panel_set_launch_status(status, true);
        scene_set_status(status, true);
        sound_play(SOUND_MAGIC);
    } else {
        (void)snprintf(status, sizeof status, "%s",
                       launcher_last_error()[0] != '\0'
                           ? launcher_last_error()
                           : "The selected tool could not be opened.");
        panel_set_launch_status(status, false);
        scene_set_status(status, false);
        sound_play(SOUND_ERROR);
    }
}

static const char *game_label(const char *id)
{
    for (int i = 0; i < game_catalog_count(); i++) {
        const GameCatalogEntry *entry = game_catalog_entry(i);
        if (entry != NULL && strcmp(entry->id, id) == 0) return entry->label;
    }
    return id != NULL ? id : "Game";
}

static void launch_game_and_report(const char *id, GameLaunchKind kind)
{
    char status[160];
    const char *label = game_label(id);
    if (launcher_open_game(id, kind, game_catalog_kilix95_root(),
                           game_catalog_helper())) {
        (void)snprintf(status, sizeof status, "Opened %s in a Kilix tab.",
                       label);
        panel_set_launch_status(status, true);
        scene_set_status(status, true);
        sound_play(SOUND_MAGIC);
    } else {
        (void)snprintf(status, sizeof status, "%s",
                       launcher_last_error()[0] != '\0'
                           ? launcher_last_error()
                           : "The game could not be launched.");
        panel_set_launch_status(status, false);
        scene_set_status(status, false);
        sound_play(SOUND_ERROR);
    }
}

/* Bundled example profiles ship beside the art: <exe>/../assets/laptop.
 * They seed the shared profile directory once on first use. */
static bool laptop_seed_directory(char *path, size_t size)
{
    char executable[PATH_MAX];
    ssize_t length = readlink("/proc/self/exe", executable,
                              sizeof executable - 1u);
    const char *slash;
    if (length <= 0 || (size_t)length >= sizeof executable) {
        return snprintf(path, size, "assets/laptop") < (int)size;
    }
    executable[length] = '\0';
    slash = strrchr(executable, '/');
    if (slash == NULL) return false;
    return snprintf(path, size, "%.*s/../assets/laptop",
                    (int)(slash - executable), executable) < (int)size;
}

/* The profile list the chooser was last given, kept so the periodic
 * registry poll can keep its running flags fresh while it is open. */
static LaptopList chooser_profiles;

/* Push the run registry's word into the scene: the lid state, and — for
 * the chooser — which injected profiles have a live session. The scene
 * itself never touches the filesystem. */
static void inject_laptop_state(void)
{
    bool running[LAPTOP_PROFILES_MAX] = {false};
    for (int i = 0; i < chooser_profiles.count; i++)
        running[i] =
            laptop_run_status(chooser_profiles.ids[i], NULL) == 1;
    scene_set_laptop_state(laptop_run_any(), running,
                           chooser_profiles.count);
}

static void service_laptop_menu(void)
{
    char seed[PATH_MAX];
    if (!scene_take_laptop_menu_request()) return;
    if (laptop_scan(laptop_seed_directory(seed, sizeof seed) ? seed : NULL,
                    &chooser_profiles) < 0)
        memset(&chooser_profiles, 0, sizeof chooser_profiles);
    scene_set_laptop_profiles(&chooser_profiles);
    inject_laptop_state();
    scene_open_laptop_menu();
}

static void launch_laptop_and_report(const char *profile_id)
{
    char status[96];
    char error[LAPTOP_ERROR_MAX];
    if (laptop_run_open(profile_id, error, sizeof error)) {
        (void)snprintf(status, sizeof status,
                       "Opened laptop profile %s.", profile_id);
        scene_set_status(status, true);
        sound_play(SOUND_MAGIC);
    } else {
        (void)snprintf(status, sizeof status, "%s",
                       error[0] != '\0'
                           ? error
                           : "The laptop profile could not open.");
        scene_set_status(status, false);
        sound_play(SOUND_ERROR);
    }
}

static void close_laptop_and_report(const char *profile_id)
{
    char status[96];
    char error[LAPTOP_ERROR_MAX];
    if (laptop_run_close(profile_id, error, sizeof error)) {
        (void)snprintf(status, sizeof status,
                       "Closing laptop session %s.", profile_id);
        scene_set_status(status, true);
        sound_play(SOUND_DISMISS);
    } else {
        (void)snprintf(status, sizeof status, "%s",
                       error[0] != '\0'
                           ? error
                           : "The laptop session could not close.");
        scene_set_status(status, false);
        sound_play(SOUND_ERROR);
    }
}

static void service_requests(void)
{
    const char *target;
    const char *laptop_profile;
    GameLaunchKind game_kind;
    LaunchAppId app;
    LaunchToolId tool;
    LaunchPowerId power;
    service_laptop_menu();
    while (scene_take_laptop_request(&laptop_profile))
        launch_laptop_and_report(laptop_profile);
    while (scene_take_laptop_close_request(&laptop_profile))
        close_laptop_and_report(laptop_profile);
    while (scene_take_mail_registration(&target)) {
        if (launcher_save_mail_target(target)) {
            panel_set_mail_target(launcher_mail_target());
            launch_and_report(LAUNCH_MAIL);
        } else {
            panel_set_launch_status(launcher_last_error(), false);
            sound_play(SOUND_ERROR);
        }
    }
    while (scene_take_game_request(&target, &game_kind))
        launch_game_and_report(target, game_kind);
    while (scene_take_power_request(&power)) run_power_and_report(power);
    while (scene_take_tool_request(&tool)) launch_tool_and_report(tool);
    while (scene_take_launch_request(&app)) launch_and_report(app);
}

static int run_interactive(const char *argv0)
{
    const double dt = 1.0 / (double)PRESENT_HZ;
    const int64_t frame_ms = 1000 / PRESENT_HZ;
    int64_t next;
    bool running = true;
    sigset_t previous_signal_mask;

    if (!canvas_init(&canvas, CANVAS_W, CANVAS_H)) {
        fprintf(stderr, "kilix-cap: out of memory\n");
        return 1;
    }
    if (!art_init(argv0, true))
        fprintf(stderr,
                "kilix-cap: generated workroom unavailable; using fallback\n");
    launcher_init();
    (void)game_catalog_init(argv0);
    if (block_startup_signals(&previous_signal_mask) != 0) {
        int error = errno;
        game_catalog_shutdown();
        launcher_shutdown();
        art_shutdown();
        canvas_free(&canvas);
        fprintf(stderr, "kilix-cap: cannot protect terminal startup: %s\n",
                strerror(error));
        return 1;
    }
    if (term_init() != 0) {
        int error = errno;
        (void)sigprocmask(SIG_SETMASK, &previous_signal_mask, NULL);
        game_catalog_shutdown();
        launcher_shutdown();
        art_shutdown();
        canvas_free(&canvas);
        if (error == ENOTSUP) {
            fprintf(stderr,
                    "kilix-cap needs a terminal that speaks the kitty "
                    "graphics protocol (kitty, kilix, ghostty, WezTerm).\n");
            return 1;
        }
        fprintf(stderr, "kilix-cap: cannot start terminal session: %s\n",
                strerror(error));
        return 1;
    }
    if (atexit(term_shutdown) != 0) {
        term_shutdown();
        (void)sigprocmask(SIG_SETMASK, &previous_signal_mask, NULL);
        game_catalog_shutdown();
        launcher_shutdown();
        art_shutdown();
        canvas_free(&canvas);
        fprintf(stderr, "kilix-cap: cannot register terminal cleanup\n");
        return 1;
    }
    if (install_signal_handlers() != 0) {
        int error = errno;
        term_shutdown();
        (void)sigprocmask(SIG_SETMASK, &previous_signal_mask, NULL);
        game_catalog_shutdown();
        launcher_shutdown();
        art_shutdown();
        canvas_free(&canvas);
        fprintf(stderr, "kilix-cap: cannot install signal handlers: %s\n",
                strerror(error));
        return 1;
    }
    if (sigprocmask(SIG_SETMASK, &previous_signal_mask, NULL) != 0) {
        int error = errno;
        term_shutdown();
        game_catalog_shutdown();
        launcher_shutdown();
        art_shutdown();
        canvas_free(&canvas);
        fprintf(stderr, "kilix-cap: cannot restore signal mask: %s\n",
                strerror(error));
        return 1;
    }

    (void)sound_init(argv0, false);
    scene_init();
    scene_set_game_catalog(game_catalog_entry(0), game_catalog_count(),
                           game_catalog_available());
    panel_set_mail_target(launcher_mail_target());
    if (launcher_enabled() && !launcher_phone_available())
        panel_set_phone_unavailable(
            "No VoIP or phone service is configured.");
    else
        panel_set_phone_unavailable(NULL);
    next = now_ms();

    while (running) {
        input_event ev;
        int mx = 0, my = 0;
        bool in_view = false;

        if (term_read_input() < 0) break;
        while (input_next(&ev)) {
            if (ev.kind == IN_KEY_DOWN || ev.kind == IN_KEY_REPEAT) {
                if (scene_handle(&ev)) {
                    service_requests();
                    continue;
                }
                if (ev.kind == IN_KEY_DOWN &&
                    (ev.key == KEY_ESCAPE || ev.key == 'q')) {
                    running = false;
                    break;
                }
            } else {
                (void)scene_handle(&ev);
                service_requests();
            }
        }
        if (!running) break;

        launcher_poll();
        {
            /* The registry is the laptop's truth; consult it about once
             * a second and let the scene tween the lid to match. */
            static int laptop_poll_countdown;
            if (--laptop_poll_countdown <= 0) {
                laptop_poll_countdown = PRESENT_HZ;
                inject_laptop_state();
            }
        }
        service_web_readiness();
        scene_update(dt);
        if (game_catalog_poll())
            scene_set_game_catalog(game_catalog_entry(0),
                                   game_catalog_count(),
                                   game_catalog_available());
        term_check_resize();

        scene_draw(&canvas);
        input_mouse_pos(&mx, &my, &in_view);
        if (in_view && !scene_web_boot_active())
            draw_cursor(&canvas, mx, my);
        if (!term_present_canvas(&canvas)) break;
        service_web_focus();

        next += frame_ms;
        sleep_ms(next - now_ms());
    }

    sound_shutdown();
    game_catalog_shutdown();
    launcher_shutdown();
    term_shutdown();
    art_shutdown();
    canvas_free(&canvas);
    return 0;
}

/* ---- Entry ---- */

static void usage(void)
{
    printf("kilix-cap " KILIX_CAP_VERSION "\n"
           "usage: kilix-cap [subcommand]\n\n"
           "  (no arguments)         run the interface\n"
           "  --version              print the version\n"
           "  --targets-test         verify semantic and minimum targets\n"
           "  --input-test           exercise raw SGR parsing and ordering\n"
           "  --scene-test           exercise gesture and transition rules\n"
           "  --interaction-test     exercise every room and visible tool\n"
           "  --audio-trigger-test   prove all twelve cue bindings headlessly\n"
           "  --audio-test           strict-load and offline-mix the sound bank\n"
           "  --font-test            verify the original bitmap face\n"
           "  --launcher-test        verify safe desktop-app handoff\n"
           "  --laptop-test          verify laptop profile parsing/sessions\n"
           "  --game-catalog-test    verify Kilix 95 catalog discovery\n"
           "  --visual-test          verify RGB art and opaque scene output\n"
           "  --render-test DIR      write hash-pinned release frames\n"
           "  --render-review DIR    write all panels and key variants\n"
           "  --selftest SEED STEPS  deterministic synthetic-input soak\n");
}

static bool parse_u32_arg(const char *text, uint32_t *value)
{
    char *end = NULL;
    unsigned long parsed;
    if (text == NULL || text[0] == '\0' || value == NULL) return false;
    errno = 0;
    parsed = strtoul(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || parsed > UINT32_MAX)
        return false;
    *value = (uint32_t)parsed;
    return true;
}

static bool parse_steps_arg(const char *text, int *value)
{
    char *end = NULL;
    long parsed;
    if (text == NULL || text[0] == '\0' || value == NULL) return false;
    errno = 0;
    parsed = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' ||
        parsed < 0 || parsed > 1000000L)
        return false;
    *value = (int)parsed;
    return true;
}

static bool provider_assets_ready(const char *argv0)
{
    char executable[PATH_MAX];
    char directory[PATH_MAX];
    char visual[PATH_MAX];
    char audio[PATH_MAX];
    char *separator;
    ssize_t length = readlink("/proc/self/exe", executable,
                              sizeof executable - 1u);
    if (length < 0 || (size_t)length >= sizeof executable - 1u) {
        if (argv0 == NULL || realpath(argv0, executable) == NULL)
            return access("assets/art/runtime/workdesk-room.png", R_OK) == 0 &&
                   access("assets/sfx/touch.wav", R_OK) == 0;
    } else {
        executable[length] = '\0';
    }
    if (snprintf(directory, sizeof directory, "%s", executable) < 0)
        return false;
    separator = strrchr(directory, '/');
    if (separator == NULL) return false;
    *separator = '\0';
    if (snprintf(visual, sizeof visual,
                 "%s/../assets/art/runtime/workdesk-room.png", directory) < 0 ||
        snprintf(audio, sizeof audio, "%s/../assets/sfx/touch.wav", directory) < 0)
        return false;
    return access(visual, R_OK) == 0 && access(audio, R_OK) == 0;
}

int main(int argc, char **argv)
{
    struct kilix_provider_v1 provider = {
        .provider_id = "kilix-cap",
        .provider_version = KILIX_CAP_VERSION,
        .display_modes_json = "[\"kitty-graphics\"]",
        .capabilities_json =
            "{\"audio\":true,\"headless_screenshot\":{"
            "\"available\":false,\"detail\":\"Kilix Cap does not expose a "
            "general headless screenshot endpoint.\",\"reason\":\"not-implemented\"},"
            "\"keyboard\":true,\"launcher\":true,\"mouse\":true,"
            "\"reduced_motion\":{\"available\":false,\"detail\":\"Kilix Cap "
            "does not expose a reduced-motion renderer.\",\"reason\":\"not-implemented\"},"
            "\"settings\":{\"available\":false,\"detail\":\"Protocol configuration "
            "writes are not available in this adapter.\",\"reason\":\"not-implemented\"}}",
        .required_capabilities_json = "[\"keyboard\"]",
        .check_id = "provider-assets",
        .ready_summary = "Kilix Cap is ready.",
        .unavailable_summary = "Kilix Cap assets are unavailable.",
        .check_pass_summary = "Required visual and audio assets are readable.",
        .check_unavailable_summary = "Required visual or audio assets are missing.",
        .check_ready = provider_assets_ready(argv[0]),
        .screenshot_available = false
    };
    int provider_result = kilix_provider_v1_dispatch(argc, argv, &provider);
    if (provider_result == KILIX_PROVIDER_LAUNCH)
        return run_interactive(argv[0]);
    if (provider_result != KILIX_PROVIDER_NOT_HANDLED)
        return provider_result;

    if (argc < 2) return run_interactive(argv[0]);

    if (strcmp(argv[1], "--launcher-child") == 0) {
        char cwd[4096];
        return argc == 4 && strcmp(argv[2], "literal;*$()") == 0 &&
                       getcwd(cwd, sizeof cwd) != NULL &&
                       strcmp(cwd, argv[3]) == 0
                   ? LAUNCHER_TEST_CHILD_EXIT
                   : 74;
    }

    if (strcmp(argv[1], "--version") == 0) {
        printf("kilix-cap " KILIX_CAP_VERSION "\n");
        return 0;
    }
    if (strcmp(argv[1], "--help") == 0) {
        usage();
        return 0;
    }
    if (strcmp(argv[1], "--targets-test") == 0)
        return cmd_targets_test(argv[0]);
    if (strcmp(argv[1], "--input-test") == 0) return cmd_input_test();
    if (strcmp(argv[1], "--scene-test") == 0) return cmd_scene_test();
    if (strcmp(argv[1], "--interaction-test") == 0)
        return cmd_interaction_test();
    if (strcmp(argv[1], "--audio-trigger-test") == 0)
        return cmd_audio_trigger_test();
    if (strcmp(argv[1], "--audio-test") == 0)
        return cmd_audio_test(argv[0]);
    if (strcmp(argv[1], "--font-test") == 0) return cmd_font_test();
    if (strcmp(argv[1], "--launcher-test") == 0)
        return cmd_launcher_test();
    if (strcmp(argv[1], "--laptop-test") == 0) {
        if (!laptop_selftest()) return 1;
        if (!laptop_run_selftest()) return 1;
        printf("laptop-test: ok (profiles, sessions, rejections, "
               "run registry)\n");
        return 0;
    }
    if (strcmp(argv[1], "--game-catalog-test") == 0)
        return cmd_game_catalog_test(argv[0]);
    if (strcmp(argv[1], "--visual-test") == 0)
        return cmd_visual_test(argv[0]);
    if (strcmp(argv[1], "--render-test") == 0) {
        if (argc != 3 || argv[2][0] == '\0') {
            fprintf(stderr,
                    "kilix-cap: --render-test requires exactly one DIR\n");
            return 2;
        }
        return cmd_render_test(argv[0], argv[2]);
    }
    if (strcmp(argv[1], "--render-review") == 0) {
        if (argc != 3 || argv[2][0] == '\0') {
            fprintf(stderr,
                    "kilix-cap: --render-review requires exactly one DIR\n");
            return 2;
        }
        return cmd_render_review(argv[0], argv[2]);
    }
    if (strcmp(argv[1], "--selftest") == 0) {
        uint32_t seed = 1337u;
        int steps = 500;
        if ((argc > 2 && !parse_u32_arg(argv[2], &seed)) ||
            (argc > 3 && !parse_steps_arg(argv[3], &steps))) {
            fprintf(stderr, "kilix-cap: invalid --selftest arguments\n");
            return 2;
        }
        return cmd_selftest(seed, steps);
    }

    fprintf(stderr, "kilix-cap: unknown option '%s'\n", argv[1]);
    usage();
    return 2;
}
