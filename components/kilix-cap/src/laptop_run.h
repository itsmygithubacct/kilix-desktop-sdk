/* laptop_run.h — the Study laptop's session lifecycle: the shared run
 * registry, the host-verb handoff, and the fallback spawn.
 *
 * kilix-cap. Owning .c: src/laptop_run.c. Spec: docs/LAPTOP.md.
 *
 * RUN REGISTRY: <profiles>/run/<id>.pid retains the shared decimal PID
 * line. Cap also writes <id>.pid.identity: "v1 PID START_TICKS BOOT_UUID\n",
 * both 0600 via same-directory rename, metadata first. Identity comes from
 * Linux procfs field 22 and boot_id. Missing/mismatched metadata is never
 * trusted for signaling, and shared records are not deleted during reads.
 * Other providers must adopt the metadata and stable-handle validation;
 * see docs/LAPTOP.md for interoperability and migration limitations.
 *
 * Opening prefers the host verb; fallback spawning is un-detached so Cap
 * owns and tracks the session child. Closing uses a pidfd acquired before
 * identity validation, with no numeric-signal or legacy-host fallback. */
#ifndef KILIX_CAP_LAPTOP_RUN_H
#define KILIX_CAP_LAPTOP_RUN_H

#include "laptop.h"

/* The registry directory, <profiles>/run. */
bool laptop_run_directory(char *path, size_t size);
/* Records a freshly spawned session's PID and birth/boot identity. */
bool laptop_run_record(const char *id, long pid);
/* 1 = verified running (pid filled in), 0 = absent/dead,
 * -1 = invalid id, unreadable record, or unverifiable identity. */
int laptop_run_status(const char *id, long *pid);
/* True while any profile session is live — the laptop's power light.
 * Never creates the profile directory. */
bool laptop_run_any(void);

/* Opens a profile: the host verb when it exists, the tracked fallback
 * otherwise. Requires a live Kilix session, like every app launch. On
 * failure error holds one short user-facing sentence. */
bool laptop_run_open(const char *profile_id, char *error,
                     size_t error_size);
/* Closes a verified session using a stable process handle. Unknown identity
 * or unavailable pidfd support fails closed. Absent/dead counts as closed. */
bool laptop_run_close(const char *profile_id, char *error,
                      size_t error_size);

/* Headless self-checks of the registry rules over a private temp
 * directory. */
bool laptop_run_selftest(void);

#endif /* KILIX_CAP_LAPTOP_RUN_H */
