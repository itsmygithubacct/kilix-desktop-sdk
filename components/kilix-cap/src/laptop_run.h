/* laptop_run.h — the Study laptop's session lifecycle: the shared run
 * registry, the host-verb handoff, and the fallback spawn.
 *
 * kilix-cap. Owning .c: src/laptop_run.c. Spec: docs/LAPTOP.md.
 *
 * RUN REGISTRY — one contract shared by every laptop surface (this
 * desktop, kilix-land-desktop, `kilix laptop`, and the launcher TUI;
 * spelled out in the kilix checkout's config/laptop.py):
 * <profiles>/run/<id>.pid holds the ASCII decimal pid of a pane
 * profile's live session process, one line plus a trailing newline,
 * written 0600 via a same-directory temp file + rename at spawn time by
 * whichever surface spawned it. Liveness is a real process check —
 * kill(pid, 0), where EPERM still counts as alive and a /proc zombie
 * does not — never the file alone; a stale or unparsable file is
 * deleted by whichever reader notices it. Desktop profiles are never
 * tracked: their wrapper exits once the provider tab exists.
 *
 * Opening and closing PREFER the host's own verb — `kilix laptop
 * open|close <id>` — probed once per process the way the games handoff
 * probes `kilix games play`, so every surface agrees on one registry
 * entry. On a host that predates the verb, the fallback here spawns the
 * generated session UN-detached (a fixed argv, no shell), so the child
 * pid IS the session window and this module records the truth itself.
 * The spawn lives here rather than in launcher.c because the registry
 * owner must know the spawned pid, and a --detach launch hides it. */
#ifndef KILIX_CAP_LAPTOP_RUN_H
#define KILIX_CAP_LAPTOP_RUN_H

#include "laptop.h"

/* The registry directory, <profiles>/run. */
bool laptop_run_directory(char *path, size_t size);
/* Records a freshly spawned session's pid. */
bool laptop_run_record(const char *id, long pid);
/* 1 = running (pid filled in when asked), 0 = not running (a stale file
 * is cleaned up on the way), -1 = no registry or invalid id. */
int laptop_run_status(const char *id, long *pid);
/* True while any profile session is live — the laptop's power light.
 * Never creates the profile directory. */
bool laptop_run_any(void);

/* Opens a profile: the host verb when it exists, the tracked fallback
 * otherwise. Requires a live Kilix session, like every app launch. On
 * failure error holds one short user-facing sentence. */
bool laptop_run_open(const char *profile_id, char *error,
                     size_t error_size);
/* Closes a running session: `kilix laptop close` when the verb exists,
 * else SIGTERM to the recorded pid; the registry's stale-cleanup rule
 * clears the file once the process is gone. An already-stopped session
 * counts as closed. */
bool laptop_run_close(const char *profile_id, char *error,
                      size_t error_size);

/* Headless self-checks of the registry rules over a private temp
 * directory. */
bool laptop_run_selftest(void);

#endif /* KILIX_CAP_LAPTOP_RUN_H */
