/* ui.h — touchable object model and hit testing.
 *
 * kilix-cap. FROZEN CONTRACT. Owning .c: src/ui.c (LOC ~130).
 * Spec: docs/ENGINE.md §4; asset contract §4 (drawing rules).
 *
 * OBJ_PROGRAM and OBJ_ITEM are separately rendered physical objects. Their
 * visible pixels, not a surrounding rectangle, define pointer interaction.
 */
#ifndef KILIX_CAP_UI_H
#define KILIX_CAP_UI_H

#include "canvas.h"
#include "icon.h"

typedef struct UiRect {
    int x, y, w, h;
} UiRect;

typedef enum ObjKind {
    OBJ_PLAIN = 0,  /* scenery; never touchable                           */
    OBJ_PROGRAM,    /* generated Desk prop that launches a real program   */
    OBJ_BUTTON,     /* touchable; fires an action                         */
    OBJ_DOOR,       /* touchable; changes scene                           */
    OBJ_ITEM,       /* touchable; draggable between containers            */
    OBJ_PORTAL,     /* doorway already painted into a generated room      */
    OBJ_GAME_MEDIA, /* generated CD/floppy/manual; launches a game        */
    OBJ_APPLIANCE,  /* physical object already painted into a room plate  */
    OBJ_LAPTOP,     /* the portable computer; opens the profile chooser   */
    OBJ_BREAKER     /* the wall breaker panel; opens the power menu       */
} ObjKind;

typedef struct Object {
    const char *name;   /* full accessible name, used by tests and docs */
    const char *label;  /* short drawn label                            */
    ObjKind kind;
    IconId icon;        /* procedural drawing; ICON_NONE for plain plates */
    UiRect visual;
    UiRect hit;         /* broad target contract; semantic picking may narrow it */
    int  target;        /* destination SceneId for a door or portal      */
    int  container;     /* container index for OBJ_ITEM, else -1        */
    bool tall;          /* draw as a door leaf rather than a flat plate  */
    bool visible;       /* hidden objects neither draw nor receive input */
    bool active;        /* persistent selected/on state                  */
    bool pressed;
    bool held;
    int  held_dx, held_dy;
    int  draw_x, draw_y;  /* live position while held                    */
    const uint8_t *game_icon; /* 16x16 Kilix 95 palette indices, media only */
} Object;

UiRect ui_rect(int x, int y, int w, int h);
bool   ui_hit(UiRect r, int x, int y);
bool   ui_contains(UiRect outer, UiRect inner);

/* Grow a visual rect about its center to at least the minimum target size. */
UiRect ui_target(UiRect visual);

bool ui_touchable(const Object *o);
bool ui_target_valid(const Object *o);
/* Applies visible-pixel semantics to physical objects and generated door
 * leaves, and ordinary rectangle semantics to buttons and baked portals.
 * Callers should not substitute ui_hit(). */
bool ui_object_hit(const Object *o, int x, int y);

void ui_draw_object(Canvas *c, const Object *o);

#endif /* KILIX_CAP_UI_H */
