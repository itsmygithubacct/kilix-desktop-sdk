/* launcher.h — explicit, shell-free access to optional desktop programs. */
#ifndef KILIX_CAP_LAUNCHER_H
#define KILIX_CAP_LAUNCHER_H

#include "game_catalog.h"
#include "types.h"

typedef enum LaunchAppId {
    LAUNCH_CLOCK = 0,
    LAUNCH_INBOX,
    LAUNCH_OUTBOX,
    LAUNCH_MAIL,
    LAUNCH_PROFILE,
    LAUNCH_NOTES,
    LAUNCH_DATES,
    LAUNCH_CARDS,
    LAUNCH_FILES,
    LAUNCH_PHONE,
    LAUNCH_PAPER,
    LAUNCH_CALCULATOR,
    LAUNCH_WEB,
    LAUNCH_APP_COUNT
} LaunchAppId;

typedef enum LaunchToolId {
    LAUNCH_TOOL_LOGS = 0,
    LAUNCH_TOOL_ACTIVITY,
    LAUNCH_TOOL_SETTINGS,
    LAUNCH_TOOL_STORAGE,
    LAUNCH_TOOL_SOFTWARE,
    LAUNCH_TOOL_NETWORK,
    LAUNCH_TOOL_CLEAN_TEMP,
    LAUNCH_TOOL_CLEAN_TRASH,
    LAUNCH_TOOL_CLEAN_CACHE,
    LAUNCH_TOOL_CLEAN_PACKAGES,
    LAUNCH_TOOL_CLEAN_ALL,
    LAUNCH_TOOL_DOC_START,
    LAUNCH_TOOL_DOC_ROOMS,
    LAUNCH_TOOL_DOC_INTERACTIONS,
    LAUNCH_TOOL_DOC_APPS,
    LAUNCH_TOOL_DOC_ENGINE,
    LAUNCH_TOOL_WEATHER,
    LAUNCH_TOOL_STARGAZING,
    LAUNCH_TOOL_COUNT
} LaunchToolId;

void launcher_init(void);
void launcher_shutdown(void);
void launcher_poll(void);

bool        launcher_enabled(void);
const char *launcher_app_title(LaunchAppId id);
/* Native phone app or xdg-open backed by a registered tel: association. */
bool        launcher_phone_available(void);
bool        launcher_mail_configured(void);
const char *launcher_mail_target(void);
/* Defaults to Hacker News and may be overridden by web_home= in the same
 * private local config file used for mail_target. */
const char *launcher_web_home(void);
const char *launcher_config_directory(void);
bool        launcher_save_mail_target(const char *target);
bool        launcher_open(LaunchAppId id);
/* The Study computer uses a two-phase launch: create an exact hidden Kilix
 * browser tab first, wait for Kilix to emit its first changed content frame
 * after the startup snapshot, then focus that exact window after the room
 * animation. */
typedef enum LauncherWebStatus {
    LAUNCHER_WEB_WAITING = 0,
    LAUNCHER_WEB_READY,
    LAUNCHER_WEB_FAILED
} LauncherWebStatus;
bool        launcher_begin_web(void);
LauncherWebStatus launcher_web_status(void);
bool        launcher_focus_web(void);
void        launcher_discard_web(void);
/* Mansion appliances either open a fixed desktop program/document or launch
 * one of the bundled live system consoles in a fresh authenticated Kilix
 * terminal tab. */
const char *launcher_tool_title(LaunchToolId id);
bool        launcher_open_tool(LaunchToolId id);
/* Opens one validated Kilix 95 registry/built-in game in a fresh Kilix tab. */
bool        launcher_open_game(const char *game_id, GameLaunchKind kind,
                               const char *kilix95_root,
                               const char *catalog_helper);
const char *launcher_last_program(void);
const char *launcher_last_error(void);

/* Headless safety/lifecycle check; launches only this binary's hidden helper. */
bool launcher_selftest(void);

/* Exact sentinel returned only by the private lifecycle helper. */
enum { LAUNCHER_TEST_CHILD_EXIT = 73 };

#endif /* KILIX_CAP_LAUNCHER_H */
