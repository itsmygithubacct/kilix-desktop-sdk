/* scene.c — eight connected rooms, persistent tools, and room interactions. */
#include "scene.h"

#include "art.h"
#include "draw.h"
#include "game_icons.h"
#include "panel.h"
#include "sound.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct Container {
    const char *name;
    UiRect rect;
} Container;

enum {
    DESK_ITEMS = 13,
    DESK_LAPTOP_INDEX = DESK_ITEMS,
    DESK_OBJS = DESK_ITEMS + 2, /* props + laptop + hallway door */
    HALL_OBJS = 7,
    STORE_ITEMS = 3,
    STORE_OBJS = STORE_ITEMS + 1,
    SERVER_OBJS = 7,
    GAME_OBJS_MAX = GAME_CATALOG_MAX + 1,
    LIBRARY_BOOKS = 5,
    LIBRARY_OBJS = LIBRARY_BOOKS + 1,
    CLEANING_OBJS = 5,
    BALCONY_OBJS = 3,
    BAR_OBJS = 7,
    STORE_CONTAINERS = 2
};

typedef struct Scene {
    const char *name;
    Object *objs;
    int nobjs;
    Container *containers;
    int ncontainers;
} Scene;

static Object desk_objs[DESK_OBJS];
static Object hall_objs[HALL_OBJS];
static Object store_objs[STORE_OBJS];
static Object server_objs[SERVER_OBJS];
static Object game_objs[GAME_OBJS_MAX];
static Object library_objs[LIBRARY_OBJS];
static Object cleaning_objs[CLEANING_OBJS];
static Object balcony_objs[BALCONY_OBJS];
static Object bar_objs[BAR_OBJS];
static Container store_containers[STORE_CONTAINERS];
static Scene scenes[SCENE_COUNT];

static SceneId current = SCENE_DESK;
static Object *active_obj;
static uint8_t active_button = 3;
static int gesture_start_x;
static int gesture_start_y;
static bool gesture_error_played;
static int pointer_x;
static int pointer_y;
static bool pointer_in_view;

static bool lamp_on;
static bool motion_on;
static bool notices_on;
static GameCatalogEntry game_entries[GAME_CATALOG_MAX];
static int game_entry_count;
static bool game_catalog_known;
static bool game_catalog_seeded;
static bool launch_pending;
static LaunchAppId pending_launch;
static bool tool_launch_pending;
static LaunchToolId pending_tool_launch;
static bool mail_registration_pending;
static bool game_launch_pending;
static char pending_game_id[GAME_ID_MAX + 1];
static GameLaunchKind pending_game_kind;
static char transient_status[96];
static double transient_status_remaining;
static bool transient_status_success;

/* The laptop's profile chooser. The scene never reads the profile
 * directory itself: opening is a take-and-clear request main answers by
 * scanning profiles and calling scene_set_laptop_profiles +
 * scene_open_laptop_menu, so every filesystem read stays in one layer and
 * the deterministic soak sees only injected state. */
static struct {
    bool open;
    int pressed_row; /* -1 = none */
    LaptopList profiles;
} laptop_menu = {false, -1, {0, {{0}}}};
static bool laptop_menu_request_pending;
static bool laptop_launch_pending;
static char pending_laptop_profile[LAPTOP_ID_MAX];
/* The laptop's running state, injected by main from the run registry the
 * same way the profile ids are injected, so the deterministic soak and
 * the headless tests see only what they put in. laptop_on drives the
 * lid: a short tween between closed (0) and open (2) with the half-open
 * frame between, in the scene's dt idiom like door transitions. */
static bool laptop_menu_running[LAPTOP_PROFILES_MAX];
static bool laptop_on;
static double laptop_lid_t; /* 0 closed .. 2 open */
static bool laptop_close_pending;
static char pending_laptop_close[LAPTOP_ID_MAX];
#define LAPTOP_LID_STEP_SECONDS 0.10
#define LAPTOP_LID_OPEN_FRAME 2

enum {
    LAPTOP_MENU_W = 264,
    LAPTOP_MENU_HEADER_H = 30,
    LAPTOP_MENU_ROW_H = 24,
    LAPTOP_MENU_FOOTER_H = 8
};

#define TRANS_PHASE 0.18
#define WEB_BOOT_SECONDS 2.80
#define WEB_ZOOM_SECONDS 0.80
static struct {
    bool active;
    double t;
    SceneId to;
    UiRect door;
} trans;
static struct {
    bool active;
    bool ready;
    bool focus_pending;
    bool focus_issued;
    double elapsed;
    double zoom_elapsed;
} web_boot;
static uint32_t web_zoom_source[CANVAS_W * CANVAS_H];

enum {
    WALL_Y = CONTENT_Y,
    WALL_H = 42,
    DESK_ROW0_Y = 72,
    DESK_ROW1_Y = 136,
    DESK_ROW2_Y = 200,
    DESK_ROW_H = 56,
    DESK_EDGE_Y = 262,
    WEB_SCREEN_X = 194,
    WEB_SCREEN_Y = 111,
    WEB_SCREEN_W = 77,
    WEB_SCREEN_H = 43
};

static void layout_container_items(void);

static void set_object(Object *o, const char *name, const char *label,
                       ObjKind kind, IconId icon, UiRect visual, int target,
                       bool tall)
{
    memset(o, 0, sizeof *o);
    o->name = name;
    o->label = label;
    o->kind = kind;
    o->icon = icon;
    o->visual = visual;
    if (kind == OBJ_PROGRAM || kind == OBJ_DOOR || kind == OBJ_ITEM ||
        kind == OBJ_PORTAL || kind == OBJ_GAME_MEDIA ||
        kind == OBJ_APPLIANCE || kind == OBJ_LAPTOP)
        o->hit = visual;
    else
        o->hit = ui_target(visual);
    o->target = target;
    o->container = -1;
    o->tall = tall;
    o->visible = true;
}

static void refresh_storage_counts(void)
{
    int tote = 0;
    int trash = 0;
    for (int i = 1; i < STORE_OBJS; i++) {
        if (store_objs[i].container == ITEM_TOTE) tote++;
        if (store_objs[i].container == ITEM_TRASH) trash++;
    }
    panel_set_storage_counts(tote, trash);
}

static void layout_container_items(void)
{
    for (int i = 1; i < STORE_OBJS; i++)
        store_objs[i].visible = store_objs[i].container == ITEM_LEFT_SHELF ||
                                store_objs[i].container == ITEM_RIGHT_SHELF;

    for (int ci = 0; ci < STORE_CONTAINERS; ci++) {
        int slot = 0;
        for (int i = 1; i < STORE_OBJS; i++) {
            Object *o = &store_objs[i];
            if (!o->visible || o->container != ci) continue;
            o->visual.x = store_containers[ci].rect.x + 8 + slot * 52;
            o->visual.y = store_containers[ci].rect.y +
                          store_containers[ci].rect.h - 56;
            o->hit = o->visual;
            slot++;
        }
    }
    refresh_storage_counts();
}

static void cancel_gesture(void)
{
    if (active_obj != NULL) {
        bool was_held = active_obj->held;
        active_obj->pressed = false;
        active_obj->held = false;
        active_obj = NULL;
        active_button = 3;
        gesture_error_played = false;
        if (was_held) layout_container_items();
    }
}

static void clear_pressed(void)
{
    for (int i = 0; i < BAR_OBJS; i++) {
        bar_objs[i].pressed = false;
        bar_objs[i].held = false;
    }
    for (int s = 0; s < SCENE_COUNT; s++)
        for (int i = 0; i < scenes[s].nobjs; i++) {
            scenes[s].objs[i].pressed = false;
            scenes[s].objs[i].held = false;
        }
}

static void build_desk(void)
{
    static const struct {
        const char *name;
        const char *label;
        IconId icon;
        LaunchAppId app;
    } items[DESK_ITEMS] = {
        {"Clock", "Clock", ICON_CLOCK, LAUNCH_CLOCK},
        {"In box", "In", ICON_INBOX, LAUNCH_INBOX},
        {"Out box", "Out", ICON_OUTBOX, LAUNCH_OUTBOX},
        {"New-message postcard", "Mail", ICON_POSTCARD, LAUNCH_MAIL},
        {"Own name card", "Me", ICON_NAMECARD, LAUNCH_PROFILE},
        {"Notepad", "Notepad", ICON_NOTEBOOK, LAUNCH_NOTES},
        {"Datebook", "Dates", ICON_DATEBOOK, LAUNCH_DATES},
        {"Name card file", "Cards", ICON_CARDFILE, LAUNCH_CARDS},
        {"File cabinet", "Files", ICON_CABINET, LAUNCH_FILES},
        {"Telephone", "Phone", ICON_PHONE, LAUNCH_PHONE},
        {"Stationery drawer", "Paper", ICON_STATIONERY, LAUNCH_PAPER},
        {"Desk accessories drawer", "Calc", ICON_TOOLBOX, LAUNCH_CALCULATOR},
        {"Computer", "Web", ICON_GLOBE, LAUNCH_WEB}
    };

    /* art.c is the sole source of truth for Desk prop geometry. Its
     * desk_sprites table is compile-time data rather than part of the
     * loadable bundle, so these bounds resolve with or without the atlas and
     * a second copy here would only be a table to forget to update. */
    for (int i = 0; i < DESK_ITEMS; i++) {
        int x = 0, y = 0, w = 0, h = 0;
        if (!art_workdesk_item_bounds(items[i].icon, &x, &y, &w, &h)) continue;
        set_object(&desk_objs[i], items[i].name, items[i].label, OBJ_PROGRAM,
                   items[i].icon, ui_rect(x, y, w, h), items[i].app, false);
    }
    /* The laptop sits on the clear front-left corner of the desk, beside
     * the postcard. It is a scene object rather than a Desk prop: its
     * sprite comes from the optional small-prop atlas (procedural drawing
     * as fallback), not from the pre-composed workdesk item layer. */
    set_object(&desk_objs[DESK_LAPTOP_INDEX], "Laptop", "Laptop",
               OBJ_LAPTOP, ICON_LAPTOP, ui_rect(12, 204, 42, 49), -1,
               false);
    /* The lid frame rides in container (game media's variant pattern):
     * closed until the run registry says a session is live. */
    desk_objs[DESK_LAPTOP_INDEX].container =
        (int)(laptop_lid_t + 0.5);
    set_object(&desk_objs[DESK_ITEMS + 1], "Hallway door", "Hall", OBJ_DOOR,
               ICON_NONE, ui_rect(386, 44, 50, 150), SCENE_HALLWAY, true);
}

static void build_hallway(void)
{
    static const struct {
        const char *name;
        const char *label;
        SceneId target;
    } doors[HALL_OBJS] = {
        {"Study", "Study", SCENE_DESK},
        {"Library", "Library", SCENE_LIBRARY},
        {"Server Room", "Server", SCENE_SERVER_ROOM},
        {"Balcony entrance", "Balcony", SCENE_BALCONY},
        {"Cleaning Room", "Clean", SCENE_CLEANING_ROOM},
        {"Game Room", "Games", SCENE_GAME_ROOM},
        {"Storeroom", "Store", SCENE_STOREROOM}
    };
    static const UiRect openings[HALL_OBJS] = {
        { 72, 49, 54, 171},
        {146, 66, 34, 143},
        {180, 78, 25, 125},
        {211, 80, 58, 132},
        {279, 78, 25, 125},
        {314, 66, 34, 143},
        {358, 49, 54, 171}
    };
    for (int i = 0; i < HALL_OBJS; i++) {
        ObjKind kind = i == 3 ? OBJ_PORTAL : OBJ_DOOR;
        set_object(&hall_objs[i], doors[i].name, doors[i].label,
                   kind, ICON_NONE, openings[i], doors[i].target, true);
    }
}

static void build_storeroom(void)
{
    static const struct {
        const char *name;
        const char *label;
        IconId icon;
    } items[STORE_ITEMS] = {
        {"Storage box", "Box", ICON_BOX},
        {"Wooden crate", "Crate", ICON_CRATE},
        {"Tin canister", "Tin", ICON_TIN}
    };

    store_containers[0].name = "Left shelf";
    store_containers[0].rect = ui_rect(103, 68, 164, 160);
    store_containers[1].name = "Right shelf";
    store_containers[1].rect = ui_rect(282, 68, 164, 160);
    set_object(&store_objs[0], "Hallway door", "Out", OBJ_DOOR, ICON_NONE,
               ui_rect(15, 37, 49, 190), SCENE_HALLWAY, true);
    for (int i = 0; i < STORE_ITEMS; i++) {
        set_object(&store_objs[i + 1], items[i].name, items[i].label,
                   OBJ_ITEM, items[i].icon, ui_rect(0, 0, 44, 44), -1, false);
        store_objs[i + 1].container = ITEM_LEFT_SHELF;
    }
    layout_container_items();
}

static void build_server_room(void)
{
    set_object(&server_objs[0], "Grand Gallery door", "Out", OBJ_DOOR,
               ICON_NONE, ui_rect(20, 45, 70, 180), SCENE_HALLWAY, true);
    set_object(&server_objs[1], "Logs, alerts, and system mail monitor",
               "Logs", OBJ_APPLIANCE, ICON_NONE, ui_rect(123, 96, 68, 84),
               LAUNCH_TOOL_LOGS, false);
    set_object(&server_objs[2], "Processes and network monitor",
               "Activity", OBJ_APPLIANCE, ICON_NONE, ui_rect(193, 96, 68, 84),
               LAUNCH_TOOL_ACTIVITY, false);
    set_object(&server_objs[3], "System settings console",
               "Settings", OBJ_APPLIANCE, ICON_NONE, ui_rect(263, 69, 46, 104),
               LAUNCH_TOOL_SETTINGS, false);
    set_object(&server_objs[4], "Storage administration rack",
               "Disks", OBJ_APPLIANCE, ICON_NONE, ui_rect(318, 61, 38, 137),
               LAUNCH_TOOL_STORAGE, false);
    set_object(&server_objs[5], "Network patch panel",
               "Network", OBJ_APPLIANCE, ICON_NONE, ui_rect(361, 61, 53, 137),
               LAUNCH_TOOL_NETWORK, false);
    set_object(&server_objs[6], "Software administration cabinet",
               "Software", OBJ_APPLIANCE, ICON_NONE, ui_rect(419, 36, 55, 188),
               LAUNCH_TOOL_SOFTWARE, false);
}

typedef struct GamePlacement {
    int variant;
    UiRect rect;
} GamePlacement;

static const UiRect game_cd_slots[10] = {
    {95, 51, 28, 40}, {130, 51, 28, 40}, {165, 51, 28, 40},
    {200, 51, 28, 40}, {235, 51, 28, 40},
    {95, 84, 28, 40}, {130, 84, 28, 40}, {165, 84, 28, 40},
    {200, 84, 28, 40}, {235, 84, 28, 40}
};

static const UiRect game_floppy_slots[10] = {
    {185, 212, 42, 30}, {235, 226, 42, 30}, {285, 210, 42, 30},
    {335, 232, 42, 30}, {430, 214, 40, 29},
    {170, 245, 42, 29}, {220, 245, 42, 29}, {270, 245, 42, 29},
    {320, 245, 42, 29}, {420, 245, 42, 29}
};

static const UiRect game_book_slots[10] = {
    {314, 55, 17, 32}, {334, 55, 17, 32},
    {314, 91, 17, 32}, {334, 91, 17, 32},
    {314, 127, 17, 32}, {334, 127, 17, 32},
    {314, 163, 17, 32}, {334, 163, 17, 32},
    {270, 127, 36, 29}, {270, 162, 36, 29}
};

static const GameCatalogEntry default_game_entries[] = {
    {"mines", "Minesweeper", GAME_LAUNCH_KILIX95_BUILTIN, {0}},
    {"sol", "Solitaire", GAME_LAUNCH_KILIX95_BUILTIN, {0}},
    {"doom", "Doom", GAME_LAUNCH_KILIX95, {0}},
    {"dosbox", "DOSBox", GAME_LAUNCH_KILIX95, {0}},
    {"bashed-earth", "Bashed Earth", GAME_LAUNCH_KILIX95, {0}},
    {"kilix-jpak", "Kilix JPAK", GAME_LAUNCH_KILIX95, {0}},
    {"kilix-rancher", "Kilix Rancher", GAME_LAUNCH_KILIX95, {0}},
    {"kilix-pong", "Kilix Pong", GAME_LAUNCH_KILIX95, {0}},
    {"joustix", "Joustix", GAME_LAUNCH_KILIX95, {0}},
    {"chess-bash", "Chess Bash", GAME_LAUNCH_KILIX95, {0}},
    {"kilix-fishtank", "Kilix Fishtank", GAME_LAUNCH_KILIX95, {0}},
    {"terminal-lander", "Kilix Lander", GAME_LAUNCH_KILIX95, {0}},
    {"kitty-brokeout", "Kilix Brokeout", GAME_LAUNCH_KILIX95, {0}}
};

static GamePlacement game_placement(int index)
{
    int medium = index % 3;
    int slot = index / 3;
    GamePlacement placement;
    memset(&placement, 0, sizeof placement);
    if (medium == 0) {
        placement.variant = slot % 3;
        placement.rect = game_cd_slots[slot];
    } else if (medium == 1) {
        placement.variant = 3 + slot % 3;
        placement.rect = game_floppy_slots[slot];
    } else {
        placement.variant = slot >= 8 ? 8 : 6 + slot % 2;
        placement.rect = game_book_slots[slot];
    }
    return placement;
}

static void build_game_room(void)
{
    set_object(&game_objs[0], "Hallway door", "Out", OBJ_DOOR, ICON_NONE,
               ui_rect(15, 37, 49, 190), SCENE_HALLWAY, true);
    for (int i = 0; i < game_entry_count; i++) {
        GamePlacement placement = game_placement(i);
        game_icon_ensure(game_entries[i].id, game_entries[i].icon_pixels);
        set_object(&game_objs[i + 1], game_entries[i].label, NULL,
                   OBJ_GAME_MEDIA, ICON_NONE, placement.rect, i, false);
        game_objs[i + 1].container = placement.variant;
        game_objs[i + 1].game_icon = game_entries[i].icon_pixels;
    }
}

static void build_library(void)
{
    static const char *const names[LIBRARY_BOOKS] = {
        "First Steps", "Rooms", "Objects", "Sound", "Colophon"
    };
    static const LaunchToolId tools[LIBRARY_BOOKS] = {
        LAUNCH_TOOL_DOC_START, LAUNCH_TOOL_DOC_ROOMS,
        LAUNCH_TOOL_DOC_INTERACTIONS, LAUNCH_TOOL_DOC_APPS,
        LAUNCH_TOOL_DOC_ENGINE
    };
    static const UiRect volumes[LIBRARY_BOOKS] = {
        { 89, 142, 54, 67},
        {153, 142, 48, 67},
        {213, 142, 46, 67},
        {271, 142, 45, 67},
        {329, 142, 45, 67}
    };
    set_object(&library_objs[0], "Grand Gallery door", "Out", OBJ_DOOR,
               ICON_NONE, ui_rect(14, 48, 51, 178), SCENE_HALLWAY, true);
    for (int i = 0; i < LIBRARY_BOOKS; i++)
        set_object(&library_objs[i + 1], names[i], names[i], OBJ_APPLIANCE,
                   ICON_NONE, volumes[i], tools[i], false);
}

static void build_cleaning_room(void)
{
    set_object(&cleaning_objs[0], "Grand Gallery door", "Out", OBJ_DOOR,
               ICON_NONE, ui_rect(19, 45, 69, 181), SCENE_HALLWAY, true);
    set_object(&cleaning_objs[1], "Temporary-file wash basin",
               "Temp", OBJ_APPLIANCE, ICON_NONE, ui_rect(108, 111, 103, 111),
               LAUNCH_TOOL_CLEAN_TEMP, false);
    set_object(&cleaning_objs[2], "Trash copper bin",
               "Trash", OBJ_APPLIANCE, ICON_NONE, ui_rect(222, 119, 56, 105),
               LAUNCH_TOOL_CLEAN_TRASH, false);
    set_object(&cleaning_objs[3], "User cache drawers",
               "Cache", OBJ_APPLIANCE, ICON_NONE, ui_rect(280, 98, 64, 127),
               LAUNCH_TOOL_CLEAN_CACHE, false);
    set_object(&cleaning_objs[4], "Package cache and housekeeping terminal",
               "Packages", OBJ_APPLIANCE, ICON_NONE, ui_rect(349, 93, 78, 129),
               LAUNCH_TOOL_CLEAN_ALL, false);
}

static void build_balcony(void)
{
    set_object(&balcony_objs[0], "Grand Gallery entrance", "Inside",
               OBJ_PORTAL, ICON_NONE, ui_rect(13, 42, 78, 174),
               SCENE_HALLWAY, true);
    set_object(&balcony_objs[1], "Weather instrument",
               "Weather", OBJ_APPLIANCE, ICON_NONE, ui_rect(289, 137, 48, 71),
               LAUNCH_TOOL_WEATHER, false);
    set_object(&balcony_objs[2], "Brass telescope",
               "Stars", OBJ_APPLIANCE, ICON_NONE, ui_rect(363, 83, 86, 151),
               LAUNCH_TOOL_STARGAZING, false);
}

static void build_bar(void)
{
    static const char *const names[BAR_OBJS] = {
        "Study", "Grand Gallery", "Magic lamp", "Storeroom", "Server Room",
        "Game Room", "Cleaning Room"
    };
    static const char *const labels[BAR_OBJS] = {
        "Study", "Gallery", "Lamp", "Store", "Server", "Games", "Clean"
    };
    for (int i = 0; i < BAR_OBJS; i++)
        set_object(&bar_objs[i], names[i], labels[i], OBJ_BUTTON, ICON_NONE,
                   ui_rect(4 + i * 68, CONTROLBAR_Y + 6, 64, 28), i, false);
}

static void register_scenes(void)
{
    scenes[SCENE_DESK] = (Scene){"Study", desk_objs, DESK_OBJS, NULL, 0};
    scenes[SCENE_HALLWAY] = (Scene){"Grand Gallery", hall_objs, HALL_OBJS,
                                    NULL, 0};
    scenes[SCENE_STOREROOM] = (Scene){"Storeroom", store_objs, STORE_OBJS,
                                      store_containers, STORE_CONTAINERS};
    scenes[SCENE_SERVER_ROOM] = (Scene){"Server Room", server_objs,
                                        SERVER_OBJS, NULL, 0};
    scenes[SCENE_GAME_ROOM] = (Scene){"Game Room", game_objs,
                                      game_entry_count + 1, NULL, 0};
    scenes[SCENE_LIBRARY] = (Scene){"Library", library_objs, LIBRARY_OBJS,
                                    NULL, 0};
    scenes[SCENE_CLEANING_ROOM] = (Scene){"Cleaning Room", cleaning_objs,
                                          CLEANING_OBJS, NULL, 0};
    scenes[SCENE_BALCONY] = (Scene){"Balcony", balcony_objs, BALCONY_OBJS,
                                    NULL, 0};
}

static void reset_world(SceneId destination)
{
    build_desk();
    build_hallway();
    build_bar();
    build_storeroom();
    build_server_room();
    build_game_room();
    build_library();
    build_cleaning_room();
    build_balcony();
    register_scenes();
    panel_init();
    lamp_on = false;
    motion_on = true;
    notices_on = true;
    current = destination;
    memset(&trans, 0, sizeof trans);
    memset(&web_boot, 0, sizeof web_boot);
    active_obj = NULL;
    active_button = 3;
    gesture_error_played = false;
    launch_pending = false;
    pending_launch = LAUNCH_CLOCK;
    tool_launch_pending = false;
    pending_tool_launch = LAUNCH_TOOL_LOGS;
    mail_registration_pending = false;
    game_launch_pending = false;
    pending_game_id[0] = '\0';
    pending_game_kind = GAME_LAUNCH_KILIX95;
    transient_status[0] = '\0';
    transient_status_remaining = 0.0;
    transient_status_success = false;
    /* The injected profile list survives a workspace reset the way the
     * game catalog does; only the transient chooser state clears. */
    laptop_menu.open = false;
    laptop_menu.pressed_row = -1;
    laptop_menu_request_pending = false;
    laptop_launch_pending = false;
    pending_laptop_profile[0] = '\0';
    laptop_close_pending = false;
    pending_laptop_close[0] = '\0';
    bar_objs[2].active = lamp_on;
}

void scene_init(void)
{
    if (!game_catalog_seeded) {
        game_entry_count = (int)(sizeof default_game_entries /
                                 sizeof default_game_entries[0]);
        memcpy(game_entries, default_game_entries,
               sizeof default_game_entries);
        game_catalog_known = true;
        game_catalog_seeded = true;
    }
    pointer_x = 0;
    pointer_y = 0;
    pointer_in_view = false;
    reset_world(SCENE_DESK);
}

void scene_set_game_catalog(const GameCatalogEntry *entries, int count,
                            bool catalog_available)
{
    if (count < 0 || count > GAME_CATALOG_MAX ||
        (count > 0 && entries == NULL))
        return;
    cancel_gesture();
    memset(game_entries, 0, sizeof game_entries);
    if (count > 0)
        memcpy(game_entries, entries, (size_t)count * sizeof entries[0]);
    game_entry_count = count;
    game_catalog_known = catalog_available;
    game_catalog_seeded = true;
    build_game_room();
    scenes[SCENE_GAME_ROOM].objs = game_objs;
    scenes[SCENE_GAME_ROOM].nobjs = game_entry_count + 1;
}

void scene_goto(SceneId id)
{
    if (id < 0 || id >= SCENE_COUNT) return;
    cancel_gesture();
    clear_pressed();
    panel_close(false);
    laptop_menu.open = false;
    laptop_menu.pressed_row = -1;
    current = id;
    memset(&trans, 0, sizeof trans);
    memset(&web_boot, 0, sizeof web_boot);
}

SceneId scene_current(void) { return current; }
bool scene_busy(void) { return trans.active || web_boot.active; }

const char *scene_name(SceneId id)
{
    if (id < 0 || id >= SCENE_COUNT) return "";
    return scenes[id].name;
}

int scene_object_count(SceneId id)
{
    if (id < 0 || id >= SCENE_COUNT) return 0;
    return scenes[id].nobjs;
}

const Object *scene_object(SceneId id, int index)
{
    if (id < 0 || id >= SCENE_COUNT || index < 0 ||
        index >= scenes[id].nobjs) return NULL;
    return &scenes[id].objs[index];
}

int scene_bar_count(void) { return BAR_OBJS; }

const Object *scene_bar_object(int index)
{
    if (index < 0 || index >= BAR_OBJS) return NULL;
    return &bar_objs[index];
}

bool scene_panel_open(void) { return panel_active(); }
const char *scene_panel_title(void) { return panel_title(); }
int scene_panel_object_count(void) { return panel_object_count(); }
const Object *scene_panel_object(int index) { return panel_object(index); }

ItemPlace scene_item_place(int item_index)
{
    if (item_index < 0 || item_index >= STORE_ITEMS) return ITEM_DISCARDED;
    return (ItemPlace)store_objs[item_index + 1].container;
}

int scene_game_count(void) { return game_entry_count; }
bool scene_lamp_enabled(void) { return lamp_on; }

bool scene_take_launch_request(LaunchAppId *app)
{
    if (!launch_pending || app == NULL) return false;
    *app = pending_launch;
    launch_pending = false;
    return true;
}

bool scene_take_tool_request(LaunchToolId *tool)
{
    if (!tool_launch_pending || tool == NULL) return false;
    *tool = pending_tool_launch;
    tool_launch_pending = false;
    return true;
}

bool scene_begin_web_boot(void)
{
    if (current != SCENE_DESK || trans.active || web_boot.active)
        return false;
    cancel_gesture();
    panel_close(false);
    memset(&web_boot, 0, sizeof web_boot);
    web_boot.active = true;
    (void)snprintf(transient_status, sizeof transient_status, "%s",
                   "Computer booting Web...");
    transient_status_remaining = WEB_BOOT_SECONDS + WEB_ZOOM_SECONDS;
    transient_status_success = true;
    return true;
}

bool scene_web_boot_active(void) { return web_boot.active; }

void scene_mark_web_ready(void)
{
    if (web_boot.active) web_boot.ready = true;
}

bool scene_take_web_focus_request(void)
{
    if (!web_boot.focus_pending) return false;
    web_boot.focus_pending = false;
    return true;
}

void scene_finish_web_boot(void)
{
    memset(&web_boot, 0, sizeof web_boot);
    if (strcmp(transient_status, "Computer booting Web...") == 0) {
        transient_status[0] = '\0';
        transient_status_remaining = 0.0;
    }
}

bool scene_take_mail_registration(const char **target)
{
    if (!mail_registration_pending || target == NULL) return false;
    *target = panel_mail_target_edit();
    mail_registration_pending = false;
    return true;
}

bool scene_take_game_request(const char **id, GameLaunchKind *kind)
{
    if (!game_launch_pending || id == NULL || kind == NULL) return false;
    *id = pending_game_id;
    *kind = pending_game_kind;
    game_launch_pending = false;
    return true;
}

bool scene_take_laptop_menu_request(void)
{
    if (!laptop_menu_request_pending) return false;
    laptop_menu_request_pending = false;
    return true;
}

void scene_set_laptop_profiles(const LaptopList *profiles)
{
    if (profiles == NULL || profiles->count < 0 ||
        profiles->count > LAPTOP_PROFILES_MAX) {
        memset(&laptop_menu.profiles, 0, sizeof laptop_menu.profiles);
        return;
    }
    laptop_menu.profiles = *profiles;
}

void scene_open_laptop_menu(void)
{
    if (trans.active || web_boot.active) return;
    cancel_gesture();
    panel_close(false);
    laptop_menu.open = true;
    laptop_menu.pressed_row = -1;
}

bool scene_laptop_menu_open(void) { return laptop_menu.open; }

bool scene_take_laptop_request(const char **profile_id)
{
    if (!laptop_launch_pending || profile_id == NULL) return false;
    *profile_id = pending_laptop_profile;
    laptop_launch_pending = false;
    return true;
}

void scene_set_laptop_state(bool on, const bool *running, int count)
{
    laptop_on = on;
    memset(laptop_menu_running, 0, sizeof laptop_menu_running);
    if (running == NULL || count <= 0) return;
    if (count > LAPTOP_PROFILES_MAX) count = LAPTOP_PROFILES_MAX;
    memcpy(laptop_menu_running, running,
           (size_t)count * sizeof running[0]);
}

bool scene_take_laptop_close_request(const char **profile_id)
{
    if (!laptop_close_pending || profile_id == NULL) return false;
    *profile_id = pending_laptop_close;
    laptop_close_pending = false;
    return true;
}

/* Chooser card layout. Row 0..count-1 are profiles; row count is Close.
 * An empty scan keeps only the Close row under a hint line. */
static int laptop_menu_rows(void)
{
    return laptop_menu.profiles.count + 1;
}

/* An empty scan grows the header by one hint line above the Close row. */
static int laptop_menu_header_height(void)
{
    return LAPTOP_MENU_HEADER_H +
           (laptop_menu.profiles.count == 0 ? 14 : 0);
}

static UiRect laptop_menu_card(void)
{
    int rows = laptop_menu_rows();
    int height = laptop_menu_header_height() + rows * LAPTOP_MENU_ROW_H +
                 LAPTOP_MENU_FOOTER_H;
    UiRect card;
    card.x = (CANVAS_W - LAPTOP_MENU_W) / 2;
    card.y = CONTENT_Y + (CONTENT_H - height) / 2;
    card.w = LAPTOP_MENU_W;
    card.h = height;
    return card;
}

static int laptop_menu_row_at(int x, int y)
{
    UiRect card = laptop_menu_card();
    int header = laptop_menu_header_height();
    int row;
    if (!ui_hit(card, x, y)) return -1;
    row = (y - card.y - header) / LAPTOP_MENU_ROW_H;
    if (y < card.y + header || row < 0 || row >= laptop_menu_rows())
        return -1;
    return row;
}

static void laptop_menu_choose(int row)
{
    if (row < 0 || row >= laptop_menu_rows()) return;
    if (row == laptop_menu.profiles.count) {
        laptop_menu.open = false;
        sound_play(SOUND_DISMISS);
        return;
    }
    if (laptop_menu_running[row]) {
        /* A live session: choosing its row asks for it to be CLOSED
         * rather than opened twice; the row said so before the touch. */
        (void)snprintf(pending_laptop_close, sizeof pending_laptop_close,
                       "%s", laptop_menu.profiles.ids[row]);
        laptop_close_pending = true;
        laptop_menu.open = false;
        sound_play(SOUND_MAGIC);
        return;
    }
    (void)snprintf(pending_laptop_profile, sizeof pending_laptop_profile,
                   "%s", laptop_menu.profiles.ids[row]);
    laptop_launch_pending = true;
    laptop_menu.open = false;
    sound_play(SOUND_MAGIC);
}

/* Modal pointer routing while the chooser is open: a press inside a row
 * arms it, releasing on the same row acts, releasing anywhere else (or
 * pressing outside the card) dismisses without side effects. */
static bool laptop_menu_handle(const input_event *ev)
{
    if (ev->kind == IN_MOUSE_DOWN) {
        if (!ev->in_view || ev->button != 0) return true;
        laptop_menu.pressed_row = laptop_menu_row_at(ev->mx, ev->my);
        if (laptop_menu.pressed_row < 0 &&
            !ui_hit(laptop_menu_card(), ev->mx, ev->my)) {
            laptop_menu.open = false;
            sound_play(SOUND_DISMISS);
        } else {
            sound_play(SOUND_TOUCH);
        }
        return true;
    }
    if (ev->kind == IN_MOUSE_UP) {
        int row = laptop_menu_row_at(ev->mx, ev->my);
        if (laptop_menu.pressed_row >= 0 &&
            row == laptop_menu.pressed_row)
            laptop_menu_choose(row);
        laptop_menu.pressed_row = -1;
        return true;
    }
    if (ev->kind == IN_MOUSE_LEAVE) {
        laptop_menu.pressed_row = -1;
        return true;
    }
    return ev->kind == IN_MOUSE_MOVE || ev->kind == IN_MOUSE_WHEEL;
}

static void draw_laptop_menu(Canvas *c)
{
    UiRect card;
    int rows;
    if (!laptop_menu.open) return;
    card = laptop_menu_card();
    rows = laptop_menu_rows();
    draw_shadow(c, card.x, card.y, card.w, card.h);
    draw_round_rect(c, card.x, card.y, card.w, card.h, 6, MC_WHITE);
    draw_frame(c, card.x, card.y, card.w, card.h, 2, UI_NAVY);
    draw_rect(c, card.x + 2, card.y + 2, card.w - 4, 3, UI_TEAL);
    draw_text_center(c, card.x + card.w / 2, card.y + 9,
                     "LAPTOP - OPEN A SESSION", UI_NAVY);
    for (int row = 0; row < rows; row++) {
        int row_y = card.y + laptop_menu_header_height() +
                    row * LAPTOP_MENU_ROW_H;
        bool close_row = row == laptop_menu.profiles.count;
        char row_text[LAPTOP_ID_MAX + 24];
        const char *text;
        if (close_row) {
            text = "Close";
        } else if (laptop_menu_running[row]) {
            /* The row is honest about what a touch does. */
            (void)snprintf(row_text, sizeof row_text,
                           "%s - running, close",
                           laptop_menu.profiles.ids[row]);
            text = row_text;
        } else {
            text = laptop_menu.profiles.ids[row];
        }
        if (row == laptop_menu.pressed_row) {
            draw_round_rect(c, card.x + 8, row_y + 1, card.w - 16,
                            LAPTOP_MENU_ROW_H - 2, 4, UI_TEAL);
        } else if (!close_row) {
            draw_round_rect(c, card.x + 8, row_y + 1, card.w - 16,
                            LAPTOP_MENU_ROW_H - 2, 4, MC_LIGHT);
            draw_frame(c, card.x + 8, row_y + 1, card.w - 16,
                       LAPTOP_MENU_ROW_H - 2, 1, UI_SLATE);
        }
        draw_text_center(c, card.x + card.w / 2,
                         row_y + (LAPTOP_MENU_ROW_H -
                                  draw_text_height()) / 2,
                         text,
                         row == laptop_menu.pressed_row ? MC_WHITE
                                                        : UI_NAVY);
    }
    if (laptop_menu.profiles.count == 0)
        draw_text_center(c, card.x + card.w / 2,
                         card.y + LAPTOP_MENU_HEADER_H - 4,
                         "No profiles yet - see docs/LAPTOP.md",
                         UI_SLATE);
}

void scene_set_status(const char *message, bool success)
{
    (void)snprintf(transient_status, sizeof transient_status, "%s",
                   message != NULL ? message : "");
    transient_status_remaining = transient_status[0] != '\0' ? 4.0 : 0.0;
    transient_status_success = success;
}

static void begin_transition(SceneId to, UiRect door)
{
    if (to < 0 || to >= SCENE_COUNT || to == current) return;
    cancel_gesture();
    panel_close(false);
    sound_play(SOUND_DOOR);
    if (!motion_on) {
        current = to;
        clear_pressed();
        return;
    }
    trans.active = true;
    trans.t = 0.0;
    trans.to = to;
    trans.door = door;
}

static Object *object_at(int x, int y)
{
    for (int i = BAR_OBJS - 1; i >= 0; i--)
        if (ui_object_hit(&bar_objs[i], x, y))
            return &bar_objs[i];
    if (panel_active()) return panel_object_at(x, y);
    /* Desk props sit on the foreground work surface.  They are composited
     * after the distant exit leaf and therefore own any physically
     * overlapping pixels (notably the telephone in front of the doorway). */
    if (current == SCENE_DESK) {
        for (int i = DESK_ITEMS - 1; i >= 0; i--)
            if (ui_object_hit(&desk_objs[i], x, y)) return &desk_objs[i];
    }
    for (int i = scenes[current].nobjs - 1; i >= 0; i--) {
        Object *o = &scenes[current].objs[i];
        if (current == SCENE_DESK && o->kind == OBJ_PROGRAM) continue;
        if (ui_object_hit(o, x, y)) return o;
    }
    return NULL;
}

void scene_set_pointer(int x, int y, bool in_view)
{
    pointer_x = iclampi(x, 0, CANVAS_W - 1);
    pointer_y = iclampi(y, 0, CANVAS_H - 1);
    pointer_in_view = in_view;
}

const char *scene_hover_text(void)
{
    static char text[64];
    Object *o;

    text[0] = '\0';
    if (!notices_on || !pointer_in_view || trans.active || web_boot.active ||
        laptop_menu.open || (active_obj != NULL && active_obj->held))
        return text;
    o = object_at(pointer_x, pointer_y);
    if (o == NULL || o->name == NULL || o->name[0] == '\0') return text;

    if (o->kind == OBJ_PROGRAM || o->kind == OBJ_APPLIANCE ||
        o->kind == OBJ_GAME_MEDIA || o->kind == OBJ_LAPTOP)
        (void)snprintf(text, sizeof text, "%s - open", o->name);
    else if (o->kind == OBJ_DOOR || o->kind == OBJ_PORTAL)
        (void)snprintf(text, sizeof text, "%s - enter", o->name);
    else if (o->kind == OBJ_ITEM)
        (void)snprintf(text, sizeof text, "%s - drag", o->name);
    else
        (void)snprintf(text, sizeof text, "%s", o->name);
    return text;
}

static void handle_panel_command(PanelCommand command)
{
    if (command == PANEL_COMMAND_RETURN_TOTE_ITEM) {
        for (int i = 1; i < STORE_OBJS; i++)
            if (store_objs[i].container == ITEM_TOTE) {
                store_objs[i].container = ITEM_LEFT_SHELF;
                sound_play(SOUND_CONTAIN);
                break;
            }
        layout_container_items();
    } else if (command == PANEL_COMMAND_RESTORE_TRASH_ITEM) {
        for (int i = 1; i < STORE_OBJS; i++)
            if (store_objs[i].container == ITEM_TRASH) {
                store_objs[i].container = ITEM_LEFT_SHELF;
                sound_play(SOUND_CONTAIN);
                break;
            }
        layout_container_items();
    } else if (command == PANEL_COMMAND_EMPTY_TRASH) {
        for (int i = 1; i < STORE_OBJS; i++)
            if (store_objs[i].container == ITEM_TRASH)
                store_objs[i].container = ITEM_DISCARDED;
        layout_container_items();
    } else if (command == PANEL_COMMAND_RESET_WORKSPACE) {
        SceneId stay = current;
        reset_world(stay);
    } else if (command == PANEL_COMMAND_SAVE_MAIL_TARGET) {
        mail_registration_pending = true;
    } else if (command == PANEL_COMMAND_LAUNCH_APP) {
        PanelId id = panel_current();
        if (id >= PANEL_CLOCK && id <= PANEL_WEB) {
            pending_launch = (LaunchAppId)(id - PANEL_CLOCK);
            launch_pending = true;
        }
    }
}

static void activate(Object *o)
{
    if (o == NULL) return;
    if (panel_owns(o)) {
        PanelCommand command = panel_activate(o);
        handle_panel_command(command);
        return;
    }
    if ((o->kind == OBJ_DOOR || o->kind == OBJ_PORTAL) && o->target >= 0) {
        begin_transition((SceneId)o->target, o->visual);
        return;
    }
    if (o->kind == OBJ_LAPTOP) {
        laptop_menu_request_pending = true;
        return;
    }
    for (int i = 0; i < DESK_ITEMS; i++)
        if (o == &desk_objs[i]) {
            pending_launch = (LaunchAppId)o->target;
            launch_pending = true;
            return;
        }
    for (int i = 1; i < SERVER_OBJS; i++)
        if (o == &server_objs[i]) {
            pending_tool_launch = (LaunchToolId)o->target;
            tool_launch_pending = true;
            return;
        }
    for (int i = 0; i < game_entry_count; i++)
        if (o == &game_objs[i + 1]) {
            (void)snprintf(pending_game_id, sizeof pending_game_id, "%s",
                           game_entries[i].id);
            pending_game_kind = game_entries[i].launch_kind;
            game_launch_pending = true;
            return;
        }
    for (int i = 0; i < LIBRARY_BOOKS; i++)
        if (o == &library_objs[i + 1]) {
            pending_tool_launch = (LaunchToolId)o->target;
            tool_launch_pending = true;
            return;
        }
    for (int i = 1; i < CLEANING_OBJS; i++)
        if (o == &cleaning_objs[i]) {
            pending_tool_launch = (LaunchToolId)o->target;
            tool_launch_pending = true;
            return;
        }
    for (int i = 1; i < BALCONY_OBJS; i++)
        if (o == &balcony_objs[i]) {
            pending_tool_launch = (LaunchToolId)o->target;
            tool_launch_pending = true;
            return;
        }
    for (int i = 0; i < BAR_OBJS; i++)
        if (o == &bar_objs[i]) {
            if (i == 0) {
                panel_close(panel_active());
                if (current != SCENE_DESK)
                    begin_transition(SCENE_DESK, o->visual);
            } else if (i == 1) {
                panel_close(panel_active());
                if (current != SCENE_HALLWAY)
                    begin_transition(SCENE_HALLWAY, o->visual);
            } else if (i == 2) {
                lamp_on = !lamp_on;
                bar_objs[i].active = lamp_on;
                sound_play(SOUND_SWITCH);
            } else if (i == 3) {
                panel_close(panel_active());
                if (current != SCENE_STOREROOM)
                    begin_transition(SCENE_STOREROOM, o->visual);
            } else if (i == 4) {
                panel_close(panel_active());
                if (current != SCENE_SERVER_ROOM)
                    begin_transition(SCENE_SERVER_ROOM, o->visual);
            } else if (i == 5) {
                panel_close(panel_active());
                if (current != SCENE_GAME_ROOM)
                    begin_transition(SCENE_GAME_ROOM, o->visual);
            } else if (i == 6) {
                panel_close(panel_active());
                if (current != SCENE_CLEANING_ROOM)
                    begin_transition(SCENE_CLEANING_ROOM, o->visual);
            }
            return;
        }
}

static void drop_item(Object *o, int mx, int my)
{
    int old_place = o->container;
    int new_place = old_place;

    for (int ci = 0; ci < scenes[current].ncontainers; ci++)
        if (ui_hit(scenes[current].containers[ci].rect, mx, my)) {
            new_place = ci;
            break;
        }
    o->container = new_place;
    if (new_place != old_place) {
        if (new_place == ITEM_TRASH) sound_play(SOUND_SWALLOW);
        else sound_play(SOUND_CONTAIN);
    }
    layout_container_items();
}

bool scene_handle(const input_event *ev)
{
    if (ev == NULL) return false;
    if (ev->kind == IN_MOUSE_LEAVE)
        scene_set_pointer(ev->mx, ev->my, false);
    else if (ev->kind == IN_MOUSE_MOVE || ev->kind == IN_MOUSE_DOWN ||
             ev->kind == IN_MOUSE_UP || ev->kind == IN_MOUSE_WHEEL)
        scene_set_pointer(ev->mx, ev->my, ev->in_view);
    if (web_boot.active) return true;
    if (trans.active) return false;
    /* The chooser is modal for the pointer: rooms, props, and the control
     * bar wait until it closes. */
    if (laptop_menu.open && ev->kind != IN_KEY_DOWN &&
        ev->kind != IN_KEY_REPEAT)
        return laptop_menu_handle(ev);
    if ((ev->kind == IN_KEY_DOWN || ev->kind == IN_KEY_REPEAT) &&
        active_obj != NULL && panel_active())
        cancel_gesture();
    if (ev->kind == IN_KEY_DOWN || ev->kind == IN_KEY_REPEAT) {
        bool handled = panel_handle_key(ev);
        handle_panel_command(panel_take_command());
        return handled;
    }

    switch (ev->kind) {
    case IN_MOUSE_DOWN:
        /* Every second down ends the old gesture, even when the new button
         * is unsupported or outside the viewport. */
        cancel_gesture();
        if (!ev->in_view || ev->button != 0) return false;
        active_obj = object_at(ev->mx, ev->my);
        if (active_obj != NULL) {
            active_button = ev->button;
            gesture_start_x = ev->mx;
            gesture_start_y = ev->my;
            gesture_error_played = false;
            active_obj->pressed = true;
            if (panel_current() == PANEL_KEYBOARD && panel_owns(active_obj))
                sound_play(SOUND_KEYBOARD);
            else
                sound_play(SOUND_TOUCH);
            if (active_obj->kind == OBJ_ITEM) {
                active_obj->held = true;
                active_obj->held_dx = ev->mx - active_obj->visual.x;
                active_obj->held_dy = ev->my - active_obj->visual.y;
                active_obj->draw_x = active_obj->visual.x;
                active_obj->draw_y = active_obj->visual.y;
            }
        }
        return active_obj != NULL || panel_active();

    case IN_MOUSE_MOVE:
        if (active_obj != NULL && !ev->in_view) {
            cancel_gesture();
        } else if (active_obj != NULL && active_obj->held) {
            active_obj->draw_x = ev->mx - active_obj->held_dx;
            active_obj->draw_y = ev->my - active_obj->held_dy;
        } else if (active_obj != NULL) {
            int distance = abs(ev->mx - gesture_start_x) +
                           abs(ev->my - gesture_start_y);
            bool inside = ui_object_hit(active_obj, ev->mx, ev->my);
            if (!gesture_error_played && distance > 8 && !inside) {
                sound_play(SOUND_ERROR);
                gesture_error_played = true;
            }
            active_obj->pressed = inside;
        }
        return active_obj != NULL;

    case IN_MOUSE_UP:
        if (active_obj != NULL) {
            Object *released = active_obj;
            bool held = released->held;
            if (!ev->in_view || ev->button != active_button) {
                cancel_gesture();
                return true;
            }
            released->pressed = false;
            released->held = false;
            active_obj = NULL;
            active_button = 3;
            if (held) drop_item(released, ev->mx, ev->my);
            else if (ui_object_hit(released, ev->mx, ev->my)) activate(released);
            return true;
        }
        return panel_active();

    case IN_MOUSE_LEAVE:
        cancel_gesture();
        return true;
    default:
        return false;
    }
}

void scene_update(double dt)
{
    if (!isfinite(dt) || dt <= 0.0) return;
    {
        /* The lid follows the injected running state, one tween in the
         * scene's dt idiom: closed <-> half-open <-> open, roughly a
         * tenth of a second per frame, reversing cleanly mid-swing. */
        double target = laptop_on ? (double)LAPTOP_LID_OPEN_FRAME : 0.0;
        double step = dt / LAPTOP_LID_STEP_SECONDS;
        if (laptop_lid_t < target)
            laptop_lid_t = laptop_lid_t + step > target
                               ? target : laptop_lid_t + step;
        else if (laptop_lid_t > target)
            laptop_lid_t = laptop_lid_t - step < target
                               ? target : laptop_lid_t - step;
        desk_objs[DESK_LAPTOP_INDEX].container =
            (int)(laptop_lid_t + 0.5);
    }
    if (transient_status_remaining > 0.0 &&
        !(web_boot.active &&
          strcmp(transient_status, "Computer booting Web...") == 0)) {
        transient_status_remaining -= dt;
        if (transient_status_remaining <= 0.0) {
            transient_status_remaining = 0.0;
            transient_status[0] = '\0';
        }
    }
    if (web_boot.active) {
        double previous = web_boot.elapsed;
        double remaining = dt;
        web_boot.elapsed += dt;
        if (previous < WEB_BOOT_SECONDS)
            remaining = web_boot.elapsed > WEB_BOOT_SECONDS
                            ? web_boot.elapsed - WEB_BOOT_SECONDS
                            : 0.0;
        if (web_boot.ready && remaining > 0.0) {
            web_boot.zoom_elapsed += remaining;
            if (web_boot.zoom_elapsed >= WEB_ZOOM_SECONDS) {
                web_boot.zoom_elapsed = WEB_ZOOM_SECONDS;
            }
        }
        if (web_boot.zoom_elapsed >= WEB_ZOOM_SECONDS) {
            if (!web_boot.focus_issued) {
                web_boot.focus_pending = true;
                web_boot.focus_issued = true;
            }
        }
    }
    if (!trans.active) return;
    {
        double previous = trans.t;
        trans.t += dt / TRANS_PHASE;
        if (previous < 1.0 && trans.t >= 1.0) {
            current = trans.to;
            clear_pressed();
        }
        if (trans.t >= 2.0) {
            trans.active = false;
            trans.t = 0.0;
        }
    }
}

static void draw_namebar(Canvas *c)
{
    const char *hover = scene_hover_text();
    const char *center = transient_status[0] != '\0'
                             ? transient_status
                             : (hover[0] != '\0' ? hover
                                                : scene_name(current));
    uint32_t ink = transient_status[0] != '\0'
                       ? (transient_status_success ? UI_GREEN : UI_CORAL)
                       : MC_WHITE;
    draw_gradient_v(c, 0, NAMEBAR_Y, CANVAS_W, NAMEBAR_H,
                    UI_NAVY_LIGHT, UI_NAVY);
    draw_rect(c, 0, NAMEBAR_Y + NAMEBAR_H - 2, CANVAS_W, 2, UI_GOLD);
    draw_text(c, 8, NAMEBAR_Y + 4, "KILIX CAP", UI_GOLD);
    draw_text_center(c, CANVAS_W / 2, NAMEBAR_Y + 4, center, ink);
}

static void draw_controlbar(Canvas *c)
{
    static const uint32_t accents[BAR_OBJS] = {
        UI_TEAL, UI_GOLD, UI_CORAL, UI_BLUE, UI_GREEN, UI_ORANGE, UI_PURPLE
    };
    draw_gradient_v(c, 0, CONTROLBAR_Y, CANVAS_W, CONTROLBAR_H,
                    UI_SLATE, UI_NAVY);
    draw_rect(c, 0, CONTROLBAR_Y, CANVAS_W, 2, UI_GOLD);
    for (int i = 0; i < BAR_OBJS; i++) {
        const Object *o = &bar_objs[i];
        int x = o->visual.x;
        int y = o->visual.y + (o->pressed ? 1 : 0);
        int w = o->visual.w;
        int h = o->visual.h;
        bool selected = (i == 0 && current == SCENE_DESK) ||
                        (i == 1 && current == SCENE_HALLWAY) ||
                        (i == 2 && lamp_on) ||
                        (i == 3 && current == SCENE_STOREROOM) ||
                        (i == 4 && current == SCENE_SERVER_ROOM) ||
                        (i == 5 && current == SCENE_GAME_ROOM) ||
                        (i == 6 && current == SCENE_CLEANING_ROOM);
        uint32_t fill = selected ? 0x35586du : 0x20394du;
        uint32_t border = selected ? accents[i] : 0x587182u;
        uint32_t ink = selected ? MC_WHITE : 0xdce9edu;

        if (o->pressed) {
            fill = accents[i];
            border = MC_WHITE;
            ink = UI_NAVY;
        }
        draw_round_rect(c, x, y, w, h, 6, fill);
        draw_frame(c, x, y, w, h, 1, border);
        draw_rect(c, x + 4, y + 5, 3, h - 10, accents[i]);
        draw_text_center(c, x + w / 2, y + (h - draw_text_height()) / 2,
                         o->label, ink);
    }
}

static void draw_desk_bg(Canvas *c)
{
    draw_gradient_v(c, 0, WALL_Y, CANVAS_W, WALL_H, UI_WALL, UI_CREAM);
    draw_gradient_v(c, 0, WALL_Y + WALL_H, CANVAS_W, CONTENT_H - WALL_H,
                    UI_WOOD, UI_WOOD_DARK);
    draw_rect(c, 0, DESK_EDGE_Y, CANVAS_W,
              CONTENT_Y + CONTENT_H - DESK_EDGE_Y, UI_WOOD_DARK);
    draw_rect(c, 0, DESK_EDGE_Y, CANVAS_W, 2, UI_GOLD);
}

static void draw_hallway_bg(Canvas *c)
{
    draw_gradient_v(c, 0, CONTENT_Y, CANVAS_W, 196, 0xe8d6b7, UI_WALL);
    draw_gradient_v(c, 0, CONTENT_Y + 196, CANVAS_W, CONTENT_H - 196,
                    UI_WOOD, UI_WOOD_DARK);
    draw_rect(c, 0, CONTENT_Y + 196, CANVAS_W, 2, UI_GOLD);
    draw_text(c, 16, 238, "Choose a room", MC_WHITE);
}

static void draw_room_shell(Canvas *c, const char *caption)
{
    draw_gradient_v(c, 0, CONTENT_Y, CANVAS_W, CONTENT_H,
                    UI_NAVY_LIGHT, UI_NAVY);
    draw_shadow(c, 82, 42, 382, 220);
    draw_round_rect(c, 82, 42, 382, 220, 10, UI_CREAM);
    draw_frame(c, 82, 42, 382, 220, DRAW_BORDER, UI_GOLD);
    draw_rect(c, 84, 44, 378, 28, UI_TEAL_DARK);
    draw_text(c, 96, 49, caption, MC_WHITE);
}

static void draw_storeroom_bg(Canvas *c)
{
    draw_gradient_v(c, 0, CONTENT_Y, CANVAS_W, CONTENT_H,
                    0x5f7885, UI_SLATE);
    for (int i = 0; i < STORE_CONTAINERS; i++) {
        UiRect r = store_containers[i].rect;
        draw_shadow(c, r.x, r.y, r.w, r.h);
        draw_gradient_v(c, r.x, r.y, r.w, r.h, UI_WOOD, UI_WOOD_DARK);
        draw_frame(c, r.x, r.y, r.w, r.h, DRAW_BORDER, UI_GOLD);
        draw_rect(c, r.x, r.y + r.h - 8, r.w, 8, UI_WOOD_DARK);
        draw_rect(c, r.x, r.y + r.h - 8, r.w, 2, UI_GOLD);
        draw_text(c, r.x + 6, r.y + 4, store_containers[i].name, MC_WHITE);
    }
    draw_text(c, 98, 196, "Drop items on Tote or Trash below.", MC_WHITE);
}

static void draw_server_bg(Canvas *c)
{
    if (!art_draw_server_room(c))
        draw_room_shell(c, "Server Room");
}

static void draw_game_bg(Canvas *c)
{
    if (!art_draw_game_room(c)) {
        draw_room_shell(c, "Kilix 95 game shelf");
        for (int row = 0; row < 3; row++) {
            int y = 92 + row * 42;
            draw_rect(c, 92, y, 216, 6, UI_WOOD_DARK);
            draw_rect(c, 92, y, 216, 2, UI_GOLD);
        }
        draw_rect(c, 168, 204, 292, 58, UI_WOOD);
        draw_frame(c, 168, 204, 292, 58, 2, UI_WOOD_DARK);
    }
    if (game_entry_count == 0) {
        const char *message = game_catalog_known
                                  ? "Kilix 95 offers no games right now."
                                  : "Kilix 95 game catalog not found.";
        draw_round_rect(c, 136, 205, 300, 34, 6, 0xf8edcfu);
        draw_frame(c, 136, 205, 300, 34, 1, UI_GOLD);
        draw_text_center(c, 286, 214, message, UI_NAVY);
    }
}

static void draw_library_bg(Canvas *c)
{
    if (!art_draw_library(c))
        draw_room_shell(c, "Library");
}

static void draw_cleaning_bg(Canvas *c)
{
    if (!art_draw_cleaning_room(c))
        draw_room_shell(c, "Cleaning Room");
}

static void draw_balcony_bg(Canvas *c)
{
    if (!art_draw_balcony(c))
        draw_room_shell(c, "Balcony");
}

static void draw_appliance_fallback(Canvas *c, const Object *o)
{
    int x = o->visual.x;
    int y = o->visual.y + (o->pressed ? 2 : 0);
    int w = o->visual.w;
    int h = o->visual.h;
    const char *label = o->label != NULL ? o->label : "Open";

    if (!o->pressed) draw_shadow(c, x, y, w, h);
    draw_round_rect(c, x, y, w, h, 5,
                    o->pressed ? 0x244f4au : 0x1a292du);
    draw_frame(c, x, y, w, h, 2, UI_TEAL);
    draw_text_center(c, x + w / 2,
                     y + (h - draw_text_height()) / 2,
                     label, o->pressed ? MC_WHITE : UI_GREEN);
}

static void draw_scene_object(Canvas *c, const Object *o, int index)
{
    (void)index;
    if (o->kind == OBJ_APPLIANCE && !art_ready()) {
        draw_appliance_fallback(c, o);
        return;
    }
    ui_draw_object(c, o);
}

static void draw_lamp(Canvas *c)
{
    if (!lamp_on) return;
    draw_line_hard(c, 454, 34, 420, 62, UI_GOLD);
    draw_line_hard(c, 454, 34, 454, 72, UI_GOLD);
    draw_line_hard(c, 454, 34, 474, 62, UI_GOLD);
    draw_frame(c, 2, CONTENT_Y + 2, CANVAS_W - 4, CONTENT_H - 4, 1,
               UI_GOLD);
}

/* A purpose-built 3x5 phosphor font keeps the boot console in scale with the
 * Study's 77x43 physical monitor. Each hexadecimal row uses its low 3 bits. */
#define MICRO_GLYPH(a, b, c, d, e) \
    ((uint16_t)(((a) << 12) | ((b) << 9) | ((c) << 6) | ((d) << 3) | (e)))

static uint16_t micro_glyph(char ch)
{
    switch (ch) {
    case 'A': return MICRO_GLYPH(2, 5, 7, 5, 5);
    case 'B': return MICRO_GLYPH(6, 5, 6, 5, 6);
    case 'C': return MICRO_GLYPH(3, 4, 4, 4, 3);
    case 'D': return MICRO_GLYPH(6, 5, 5, 5, 6);
    case 'E': return MICRO_GLYPH(7, 4, 6, 4, 7);
    case 'F': return MICRO_GLYPH(7, 4, 6, 4, 4);
    case 'G': return MICRO_GLYPH(3, 4, 5, 5, 3);
    case 'H': return MICRO_GLYPH(5, 5, 7, 5, 5);
    case 'I': return MICRO_GLYPH(7, 2, 2, 2, 7);
    case 'J': return MICRO_GLYPH(1, 1, 1, 5, 2);
    case 'K': return MICRO_GLYPH(5, 5, 6, 5, 5);
    case 'L': return MICRO_GLYPH(4, 4, 4, 4, 7);
    case 'M': return MICRO_GLYPH(5, 7, 7, 5, 5);
    case 'N': return MICRO_GLYPH(5, 7, 7, 7, 5);
    case 'O': return MICRO_GLYPH(2, 5, 5, 5, 2);
    case 'P': return MICRO_GLYPH(6, 5, 6, 4, 4);
    case 'Q': return MICRO_GLYPH(2, 5, 5, 3, 1);
    case 'R': return MICRO_GLYPH(6, 5, 6, 5, 5);
    case 'S': return MICRO_GLYPH(3, 4, 2, 1, 6);
    case 'T': return MICRO_GLYPH(7, 2, 2, 2, 2);
    case 'U': return MICRO_GLYPH(5, 5, 5, 5, 7);
    case 'V': return MICRO_GLYPH(5, 5, 5, 5, 2);
    case 'W': return MICRO_GLYPH(5, 5, 7, 7, 5);
    case 'X': return MICRO_GLYPH(5, 5, 2, 5, 5);
    case 'Y': return MICRO_GLYPH(5, 5, 2, 2, 2);
    case 'Z': return MICRO_GLYPH(7, 1, 2, 4, 7);
    case '0': return MICRO_GLYPH(7, 5, 5, 5, 7);
    case '1': return MICRO_GLYPH(2, 6, 2, 2, 7);
    case '2': return MICRO_GLYPH(6, 1, 2, 4, 7);
    case '3': return MICRO_GLYPH(6, 1, 2, 1, 6);
    case '4': return MICRO_GLYPH(5, 5, 7, 1, 1);
    case '5': return MICRO_GLYPH(7, 4, 6, 1, 6);
    case '6': return MICRO_GLYPH(3, 4, 6, 5, 2);
    case '7': return MICRO_GLYPH(7, 1, 2, 2, 2);
    case '8': return MICRO_GLYPH(2, 5, 2, 5, 2);
    case '9': return MICRO_GLYPH(2, 5, 3, 1, 6);
    case '.': return MICRO_GLYPH(0, 0, 0, 0, 2);
    case ':': return MICRO_GLYPH(0, 2, 0, 2, 0);
    case '-': return MICRO_GLYPH(0, 0, 7, 0, 0);
    case '/': return MICRO_GLYPH(1, 1, 2, 4, 4);
    default: return 0;
    }
}

static void draw_micro_text(Canvas *c, int x, int y, const char *text,
                            uint32_t color)
{
    if (c == NULL || text == NULL) return;
    for (int column = 0; text[column] != '\0'; column++) {
        uint16_t glyph = micro_glyph(text[column]);
        for (int row = 0; row < 5; row++) {
            unsigned int bits = (glyph >> ((4 - row) * 3)) & 7u;
            for (int bit = 0; bit < 3; bit++)
                if ((bits & (1u << (2 - bit))) != 0)
                    draw_rect(c, x + column * 4 + bit, y + row, 1, 1,
                              color);
        }
    }
}

#undef MICRO_GLYPH

static void draw_web_boot_screen(Canvas *c)
{
    static const char *const messages[] = {
        "KILIX ROM", "MEMORY .... OK", "VIDEO ..... OK",
        "NETWORK ... OK", "DNS ...... OK", "X11 ...... OK",
        "FIREFOX START"
    };
    const int message_count = (int)(sizeof messages / sizeof messages[0]);
    int visible = (int)(web_boot.elapsed / 0.40) + 1;
    int total;
    int first;

    if (!web_boot.active) return;
    if (visible < 1) visible = 1;
    if (visible > message_count) visible = message_count;
    total = visible + (visible == message_count ? 1 : 0);
    first = total > 6 ? total - 6 : 0;

    draw_rect(c, WEB_SCREEN_X, WEB_SCREEN_Y, WEB_SCREEN_W, WEB_SCREEN_H,
              0x020a07u);
    draw_frame(c, WEB_SCREEN_X, WEB_SCREEN_Y, WEB_SCREEN_W, WEB_SCREEN_H,
               1, 0x1d9b63u);
    for (int index = first; index < total; index++) {
        int row = index - first;
        bool live = index + 1 == total;
        const char *message = index < message_count
                                  ? messages[index]
                                  : (web_boot.ready ? "FRAME READY"
                                                    : "WAITING FRAME");
        uint32_t ink = live ? 0x72ffa3u : 0x287b52u;
        draw_micro_text(c, WEB_SCREEN_X + 2, WEB_SCREEN_Y + 2 + row * 6,
                        message, ink);
    }
    if (((int)(web_boot.elapsed * 6.0) & 1) == 0)
        draw_rect(c, WEB_SCREEN_X + WEB_SCREEN_W - 5,
                  WEB_SCREEN_Y + WEB_SCREEN_H - 5, 3, 3, 0x72ffa3u);
    for (int y = WEB_SCREEN_Y + 2;
         y < WEB_SCREEN_Y + WEB_SCREEN_H - 1; y += 4)
        draw_blend_rect(c, WEB_SCREEN_X + 1, y, WEB_SCREEN_W - 2, 1,
                        MC_BLACK, 42);
}

static void draw_web_zoom(Canvas *c)
{
    double amount;
    double eased;
    double source_x;
    double source_y;
    double source_w;
    double source_h;

    if (!web_boot.active || web_boot.zoom_elapsed <= 0.0) return;
    amount = web_boot.zoom_elapsed / WEB_ZOOM_SECONDS;
    if (amount < 0.0) amount = 0.0;
    if (amount > 1.0) amount = 1.0;
    eased = amount * amount * (3.0 - 2.0 * amount);

    memcpy(web_zoom_source, c->px, sizeof web_zoom_source);
    source_x = eased * (double)WEB_SCREEN_X;
    source_y = eased * (double)WEB_SCREEN_Y;
    source_w = (double)CANVAS_W +
               eased * ((double)WEB_SCREEN_W - (double)CANVAS_W);
    source_h = (double)CANVAS_H +
               eased * ((double)WEB_SCREEN_H - (double)CANVAS_H);

    for (int y = 0; y < CANVAS_H; y++) {
        int sy = (int)(source_y +
                       ((double)y + 0.5) * source_h / (double)CANVAS_H);
        sy = iclampi(sy, 0, CANVAS_H - 1);
        for (int x = 0; x < CANVAS_W; x++) {
            int sx = (int)(source_x +
                           ((double)x + 0.5) * source_w /
                               (double)CANVAS_W);
            sx = iclampi(sx, 0, CANVAS_W - 1);
            c->px[y * CANVAS_W + x] =
                web_zoom_source[sy * CANVAS_W + sx];
        }
    }
    for (int y = 2; y < CANVAS_H; y += 6)
        draw_blend_rect(c, 0, y, CANVAS_W, 1, MC_BLACK,
                        (unsigned)(24.0 + 34.0 * eased));
    draw_frame(c, 0, 0, CANVAS_W, CANVAS_H, 2, 0x1d9b63u);
}

static void draw_transition(Canvas *c)
{
    double u;
    unsigned alpha;
    if (!trans.active) return;
    u = trans.t < 1.0 ? trans.t : 2.0 - trans.t;
    if (u < 0.0) u = 0.0;
    if (u > 1.0) u = 1.0;
    alpha = (unsigned)(u * 255.0 + 0.5);
    draw_blend_rect(c, 0, CONTENT_Y, CANVAS_W, CONTENT_H, MC_BLACK, alpha);
}

void scene_draw(Canvas *c)
{
    bool layered_desk = false;
    if (c == NULL) return;
    draw_clear(c, MC_LIGHT);
    switch (current) {
    case SCENE_DESK:
        if (art_draw_workdesk(c))
            layered_desk = true;
        else
            draw_desk_bg(c);
        break;
    case SCENE_HALLWAY:
        if (!art_draw_hallway(c)) draw_hallway_bg(c);
        break;
    case SCENE_STOREROOM:
        if (!art_draw_storeroom(c)) draw_storeroom_bg(c);
        break;
    case SCENE_SERVER_ROOM: draw_server_bg(c); break;
    case SCENE_GAME_ROOM: draw_game_bg(c); break;
    case SCENE_LIBRARY: draw_library_bg(c); break;
    case SCENE_CLEANING_ROOM: draw_cleaning_bg(c); break;
    case SCENE_BALCONY: draw_balcony_bg(c); break;
    default: break;
    }
    draw_lamp(c);

    for (int i = 0; i < scenes[current].nobjs; i++) {
        const Object *o = &scenes[current].objs[i];
        /* Desk props own their overlap with the distant room-native exit.
         * Defer generated and procedural prop variants until after the room
         * plate so fallback rendering keeps the same semantic z order. */
        if (!o->held &&
            !(current == SCENE_DESK && o->kind == OBJ_PROGRAM))
            draw_scene_object(c, o, i);
    }
    if (layered_desk) {
        (void)art_draw_workdesk_items(c);
    } else if (current == SCENE_DESK) {
        for (int i = 0; i < scenes[current].nobjs; i++) {
            const Object *o = &scenes[current].objs[i];
            if (!o->held && o->kind == OBJ_PROGRAM)
                draw_scene_object(c, o, i);
        }
    }
    for (int i = 0; i < scenes[current].nobjs; i++) {
        const Object *o = &scenes[current].objs[i];
        if (o->held) draw_scene_object(c, o, i);
    }
    panel_draw(c);
    draw_laptop_menu(c);
    draw_transition(c);
    draw_namebar(c);
    draw_controlbar(c);
    if (web_boot.active) {
        draw_web_boot_screen(c);
        draw_web_zoom(c);
    }
}

static uint32_t fnv1a(uint32_t h, uint32_t value)
{
    h ^= value;
    return h * 16777619u;
}

static uint32_t fnv1a_text(uint32_t h, const char *text)
{
    if (text == NULL) return fnv1a(h, 0u);
    while (*text != '\0') h = fnv1a(h, (unsigned char)*text++);
    return fnv1a(h, 0u);
}

static uint32_t active_identity(void)
{
    uint32_t identity = 1;
    if (active_obj == NULL) return 0;
    for (int i = 0; i < BAR_OBJS; i++, identity++)
        if (active_obj == &bar_objs[i]) return identity;
    for (int s = 0; s < SCENE_COUNT; s++)
        for (int i = 0; i < scenes[s].nobjs; i++, identity++)
            if (active_obj == &scenes[s].objs[i]) return identity;
    for (int i = 0; i < panel_object_count(); i++, identity++)
        if (active_obj == panel_object(i)) return identity;
    return 0xffffffffu;
}

uint32_t scene_digest(void)
{
    uint32_t h = 2166136261u;
    h = fnv1a(h, (uint32_t)current);
    h = fnv1a(h, trans.active ? 1u : 0u);
    h = fnv1a(h, (uint32_t)trans.to);
    h = fnv1a(h, (uint32_t)(trans.t * 1000.0));
    h = fnv1a(h, web_boot.active ? 1u : 0u);
    h = fnv1a(h, web_boot.focus_pending ? 1u : 0u);
    h = fnv1a(h, web_boot.focus_issued ? 1u : 0u);
    h = fnv1a(h, (uint32_t)(web_boot.elapsed * 1000.0));
    h = fnv1a(h, lamp_on ? 1u : 0u);
    h = fnv1a(h, motion_on ? 1u : 0u);
    h = fnv1a(h, notices_on ? 1u : 0u);
    h = fnv1a(h, sound_is_enabled() ? 1u : 0u);
    h = fnv1a(h, (uint32_t)game_entry_count);
    h = fnv1a(h, game_catalog_known ? 1u : 0u);
    for (int i = 0; i < game_entry_count; i++) {
        h = fnv1a_text(h, game_entries[i].id);
        h = fnv1a_text(h, game_entries[i].label);
        h = fnv1a(h, (uint32_t)game_entries[i].launch_kind);
        for (int pixel = 0; pixel < GAME_ICON_PIXELS; pixel++)
            h = fnv1a(h, game_entries[i].icon_pixels[pixel]);
    }
    h = fnv1a(h, active_identity());
    h = fnv1a(h, panel_digest());
    h = fnv1a(h, launch_pending ? 1u : 0u);
    h = fnv1a(h, tool_launch_pending ? 1u : 0u);
    h = fnv1a(h, mail_registration_pending ? 1u : 0u);
    h = fnv1a(h, game_launch_pending ? 1u : 0u);
    h = fnv1a(h, (uint32_t)pending_launch);
    h = fnv1a(h, (uint32_t)pending_tool_launch);
    h = fnv1a_text(h, pending_game_id);
    h = fnv1a(h, (uint32_t)pending_game_kind);
    h = fnv1a(h, laptop_menu.open ? 1u : 0u);
    h = fnv1a(h, (uint32_t)(laptop_menu.pressed_row + 1));
    h = fnv1a(h, (uint32_t)laptop_menu.profiles.count);
    for (int i = 0; i < laptop_menu.profiles.count; i++)
        h = fnv1a_text(h, laptop_menu.profiles.ids[i]);
    h = fnv1a(h, laptop_menu_request_pending ? 1u : 0u);
    h = fnv1a(h, laptop_launch_pending ? 1u : 0u);
    h = fnv1a_text(h, pending_laptop_profile);
    h = fnv1a(h, laptop_on ? 1u : 0u);
    h = fnv1a(h, (uint32_t)(laptop_lid_t * 1000.0));
    h = fnv1a(h, laptop_close_pending ? 1u : 0u);
    h = fnv1a_text(h, pending_laptop_close);
    for (int i = 0; i < laptop_menu.profiles.count; i++)
        h = fnv1a(h, laptop_menu_running[i] ? 1u : 0u);
    for (int s = 0; s < SCENE_COUNT; s++)
        for (int i = 0; i < scenes[s].nobjs; i++) {
            const Object *o = &scenes[s].objs[i];
            h = fnv1a(h, (uint32_t)(o->container + 1));
            h = fnv1a(h, (uint32_t)o->visual.x);
            h = fnv1a(h, (uint32_t)o->visual.y);
            h = fnv1a(h, o->visible ? 1u : 0u);
            h = fnv1a(h, o->active ? 1u : 0u);
            h = fnv1a(h, o->pressed ? 1u : 0u);
            h = fnv1a(h, o->held ? 1u : 0u);
            if (o->held) {
                h = fnv1a(h, (uint32_t)o->draw_x);
                h = fnv1a(h, (uint32_t)o->draw_y);
            }
        }
    for (int i = 0; i < BAR_OBJS; i++)
        h = fnv1a(h, bar_objs[i].active ? 1u : 0u);
    return h;
}
