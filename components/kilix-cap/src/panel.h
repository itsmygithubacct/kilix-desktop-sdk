/* panel.h — stateful Desk interiors and control-bar overlays.
 *
 * kilix-cap. Owning .c: src/panel.c. Spec: docs/ENGINE.md section 4.
 *
 * Panels are modal inside the content zone, while the name and control bars
 * remain available.  The module owns all panel-local state and touch targets;
 * scene.c owns rooms, transitions, and draggable room objects.
 */
#ifndef KILIX_CAP_PANEL_H
#define KILIX_CAP_PANEL_H

#include "input.h"
#include "ui.h"

typedef enum PanelId {
    PANEL_NONE = 0,
    PANEL_CLOCK,
    PANEL_INBOX,
    PANEL_OUTBOX,
    PANEL_MAIL,
    PANEL_PROFILE,
    PANEL_NOTES,
    PANEL_DATES,
    PANEL_CARDS,
    PANEL_FILES,
    PANEL_PHONE,
    PANEL_PAPER,
    PANEL_CALCULATOR,
    PANEL_WEB,
    PANEL_STAMPER,
    PANEL_TOTE,
    PANEL_TOOL_HOLDER,
    PANEL_KEYBOARD,
    PANEL_TRASH,
    PANEL_BOOK,
    PANEL_COUNT
} PanelId;

typedef enum PanelCommand {
    PANEL_COMMAND_NONE = 0,
    PANEL_COMMAND_RETURN_TOTE_ITEM,
    PANEL_COMMAND_RESTORE_TRASH_ITEM,
    PANEL_COMMAND_EMPTY_TRASH,
    PANEL_COMMAND_RESET_WORKSPACE,
    PANEL_COMMAND_SAVE_MAIL_TARGET,
    PANEL_COMMAND_LAUNCH_APP
} PanelCommand;

void panel_init(void);
void panel_open(PanelId id);
void panel_open_book(int book);
void panel_open_keyboard(void);
void panel_close(bool audible);

bool        panel_active(void);
PanelId     panel_current(void);
const char *panel_title(void);

/* Modal object routing.  A live panel blocks room objects even when no panel
 * object occupies the queried point. */
Object *panel_object_at(int x, int y);
bool    panel_owns(const Object *o);
PanelCommand panel_activate(Object *o);
bool    panel_handle_key(const input_event *ev);
PanelCommand panel_take_command(void);

void panel_draw(Canvas *c);

/* Counts supplied by scene.c for the Tote/Trash status pages. */
void panel_set_storage_counts(int tote_items, int trash_items);
/* Mail target configuration is runtime state and survives scene resets. */
void panel_set_mail_target(const char *target);
bool panel_mail_target_configured(void);
const char *panel_mail_target_edit(void);
/* A nonempty reason is shown immediately whenever Telephone opens.  This is
 * runtime capability state, so it intentionally survives scene resets. */
void panel_set_phone_unavailable(const char *reason);
void panel_set_launch_status(const char *status, bool success);
int  panel_copy_count(void);

/* Headless introspection covers dynamic targets as well as room targets. */
int           panel_object_count(void);
const Object *panel_object(int index);
const char   *panel_status_text(void);
bool          panel_status_success(void);
uint32_t      panel_digest(void);

#endif /* KILIX_CAP_PANEL_H */
