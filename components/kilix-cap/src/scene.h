/* scene.h — eight places, layered room objects, tools, and transitions. */
#ifndef KILIX_CAP_SCENE_H
#define KILIX_CAP_SCENE_H

#include "canvas.h"
#include "game_catalog.h"
#include "input.h"
#include "laptop.h"
#include "launcher.h"
#include "ui.h"

typedef enum SceneId {
    SCENE_DESK = 0,
    SCENE_HALLWAY = 1,
    SCENE_STOREROOM = 2,
    SCENE_SERVER_ROOM = 3,
    SCENE_GAME_ROOM = 4,
    SCENE_LIBRARY = 5,
    SCENE_CLEANING_ROOM = 6,
    SCENE_BALCONY = 7,
    SCENE_COUNT
} SceneId;

typedef enum ItemPlace {
    ITEM_LEFT_SHELF = 0,
    ITEM_RIGHT_SHELF,
    ITEM_TOTE,
    ITEM_TRASH,
    ITEM_DISCARDED
} ItemPlace;

void    scene_init(void);
void    scene_goto(SceneId id);   /* immediate, no transition (tests) */
SceneId scene_current(void);
bool    scene_busy(void);         /* a door transition is in flight */

/* True when an event was consumed.  This lets Escape close a panel before
 * main.c treats a second Escape as a request to leave the application. */
bool scene_handle(const input_event *ev);
void scene_update(double dt);
void scene_draw(Canvas *c);

/* Pointer hover is resolved through the same object-aware hit test used for
 * clicks.  scene_handle() keeps this state current for ordinary terminal
 * events; the setter is exposed for headless fixtures and alternate hosts. */
void        scene_set_pointer(int x, int y, bool in_view);
const char *scene_hover_text(void);

/* Introspection, for the headless test subcommands. */
const char   *scene_name(SceneId id);
int           scene_object_count(SceneId id);
const Object *scene_object(SceneId id, int index);
int           scene_bar_count(void);
const Object *scene_bar_object(int index);

bool        scene_panel_open(void);
const char *scene_panel_title(void);
int         scene_panel_object_count(void);
const Object *scene_panel_object(int index);
ItemPlace   scene_item_place(int item_index); /* 0..2 Storeroom items */
int         scene_game_count(void);
bool        scene_lamp_enabled(void);

/* Replaces the Game Room's live media objects in one bounded rebuild. An
 * available-but-empty catalog intentionally retracts every game object. */
void scene_set_game_catalog(const GameCatalogEntry *entries, int count,
                            bool available);

/* Direct Study launches are handed to main once. */
bool scene_take_launch_request(LaunchAppId *app);
bool scene_take_tool_request(LaunchToolId *tool);
/* The Web launcher starts its hidden tab first. The scene owns the monitor
 * boot, waits for the launcher's validated capture-readiness signal, then zooms
 * and emits one focus request at its final presented frame. */
bool scene_begin_web_boot(void);
bool scene_web_boot_active(void);
void scene_mark_web_ready(void);
bool scene_take_web_focus_request(void);
void scene_finish_web_boot(void);
/* Mail setup is persisted by main, never by the scene/input layer. */
bool scene_take_mail_registration(const char **target);
/* A clicked CD/floppy/manual is handed to main once for shell-free launch. */
bool scene_take_game_request(const char **id, GameLaunchKind *kind);

/* The Study laptop. A click raises a take-and-clear menu request; main
 * scans the profile directory, injects the ids, and opens the chooser, so
 * the scene never touches the filesystem. Choosing a profile raises a
 * launch request the same take-and-clear way. */
bool scene_take_laptop_menu_request(void);
void scene_set_laptop_profiles(const LaptopList *profiles);
void scene_open_laptop_menu(void);
bool scene_laptop_menu_open(void);
bool scene_take_laptop_request(const char **profile_id);
/* Running state, injected by main from the run registry the same way the
 * profile ids are: `on` opens the lid (a short closed/half-open/open
 * tween drawn on the desk object), `running` parallels the injected
 * profile list so the chooser marks live sessions — whose rows then ask
 * to CLOSE the session, raised as this take-and-clear request. */
void scene_set_laptop_state(bool on, const bool *running, int count);
bool scene_take_laptop_close_request(const char **profile_id);

/* Short non-modal feedback belongs in the name bar so direct-launch objects
 * never need to open a textual status panel. */
void scene_set_status(const char *message, bool success);

/* Deterministic stable-state hash used by the synthetic interaction soak. */
uint32_t scene_digest(void);

#endif /* KILIX_CAP_SCENE_H */
