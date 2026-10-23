# The Study laptop

A laptop sits on the front-left corner of the Study desk. Touching it
opens a chooser listing your **laptop profiles**; picking one opens a
configured Kilix terminal session in its own window, or switches to another
Kilix desktop provider. The chooser's Close row (or a touch outside the
card) dismisses it.

The laptop is **stateful art**: its lid is closed while nothing runs and
open while any profile session is live, with a short
closed → half-open → open swing between (about a tenth of a second per
frame, reversing cleanly mid-swing). The open frame comes from the
generated small-prop atlas (`assets/art/mansion-items.ppm`) and the two
lid frames from a second optional pair (`assets/art/laptop-lid.ppm` +
`laptop-lid-mask.ppm`, prepared by `tools/prepare_laptop_lid.py`, only
loaded alongside the atlas whose open laptop it animates); the procedural
closed/ajar/open drawings remain the complete fallback — like every other
prop, missing art degrades, it never breaks.

## Profiles: one convention across the Kilix desktops

Profiles live in a directory shared by every Kilix desktop that ships a
laptop object:

```
~/.local/gpu_terminal/laptop/<id>.profile
```

(`KILIX_LAPTOP_PROFILES` overrides the directory with an absolute path —
tests use this.) A profile is a plain `KEY=value` file; `#` starts a
comment. The `<id>` file stem uses `[A-Za-z0-9._-]` and is what the chooser
lists. On the laptop's very first use — when the directory does not exist
yet — it is created and seeded with the bundled examples from
`assets/laptop/`; an existing directory is never reseeded, so deleting
every profile is a respected choice.

### Keys

| Key            | Meaning                                                    |
|----------------|------------------------------------------------------------|
| `name=`        | display name (defaults to the file stem)                   |
| `desktop=`     | open a provider instead of a session: `desktop`, `95`, `xp`, `cap`, `tui`, `land` |
| `layout=`      | `splits` (panes tile one tab, default) or `tabs` (one tab per pane) |
| `pane.N.title=`| pane/tab title (N = 1..8, contiguous)                      |
| `pane.N.cwd=`  | working directory; `~/…` allowed. With `ssh=`, the remote directory |
| `pane.N.ssh=`  | remote destination, `[user@]host` only                     |
| `pane.N.cmd=`  | command to run (default: your shell). With `ssh=`, runs remotely |

A profile is either `desktop=` **or** panes, never both. Values cannot
contain double quotes or control characters — they feed a kitty session
file, and the parser refuses anything that could change how kitty splits
them. `pane.N.ssh=` accepts only `[user@]host` characters, so a
destination can never smuggle ssh options or a command.

### Examples

A local coding bench, split into two panes:

```
name=Coding Bench
layout=splits
pane.1.title=workspace
pane.1.cwd=~/projects
pane.2.title=monitor
pane.2.cmd=htop
```

A local tab plus a remote log tab:

```
name=Remote Ops
layout=tabs
pane.1.cwd=~
pane.2.ssh=admin@example-host
pane.2.cwd=/var/log
pane.2.cmd=tail -f syslog
```

Another desktop as a profile:

```
name=Kilix Land House
desktop=land
```

## What a launch does

Opening prefers the host's own verb: the laptop probes `kilix laptop
help` once (the same probe-never-assume pattern as the games handoff) and
delegates to `kilix laptop open <id>`, which spawns the session and
records it in the shared **run registry**. On a host that predates the
verb, the fallback keeps everything working:

- A **pane profile** becomes a generated kitty `--session` file in the
  private config directory (`~/.local/gpu_terminal/kilix-cap/`), spawned
  as `kilix --session <file>` — un-detached, so the child pid is the
  session window itself and the laptop records it in the registry. The
  session opens as its own Kilix window, which is what a laptop would do.
  `layout=splits` panes alternate right/down splits; `layout=tabs` panes
  each get a tab.
- A **desktop profile** runs `kilix <provider>` (`95` maps to
  `kilix desktop 95`), which opens the provider the way Kilix itself
  would — usually a new tab of the current Kilix window. Desktop
  profiles are not tracked in the registry: the wrapper exits once the
  provider tab exists.

All paths are fixed argv vectors through `posix_spawn`; no shell ever
interprets profile text. Launching requires running Kilix Cap inside a
Kilix session (the same rule as every app tab).

## Running sessions and closing

The shared `run/<id>.pid` still contains one decimal PID and a newline,
written 0600. Cap adds `run/<id>.pid.identity`, also 0600, containing exactly:

```text
v1 PID START_TICKS BOOT_UUID
```

The line ends with a newline. `START_TICKS` is decimal field 22 of Linux
`/proc/PID/stat`; `BOOT_UUID` is `/proc/sys/kernel/random/boot_id`. The
metadata is published before the PID, each by a same-directory rename.
Readers must compare all three values with the current process. A missing
or mismatched pair is unverifiable, including a partial publication; Cap
retains shared files and refuses both closing and duplicate pane launches.
Absent processes and zombies do not count as running. Cap checks roughly
once a second and tweens the lid for verified running sessions.

Closing acquires a Linux pidfd **before** checking identity and signals
that handle. If pidfds or identity data are unavailable, close fails with
an instruction to close the owning window. Cap does not delegate closing
to a potentially older PID-only host command.

**Provider integration remains required.** The additive sidecar preserves
PID-file readability for kilix-land-desktop, the host CLI and launcher TUI;
it does not fix older consumers' PID-only signaling. Those providers must
write the same metadata and validate identity with a stable handle before
signaling. Legacy records cannot safely be upgraded just by observing a
currently live PID: the originating owner must establish identity. Sessions
opened by a host that writes only the legacy record remain managed by that
host; Cap will refuse to trust them. No other provider is modified here.
Validate both directions of launch/status/close before claiming shared
registry qualification. Readers should not unlink records during validation,
which could delete a concurrent provider's replacement.

Fallback launch success requires publishing both records. Failure cancels
only the newly owned child, waits nonblockingly for up to 250 ms, then sends
SIGKILL if necessary and retains it for later nonblocking reaping. Tracking
has space for all 16 profiles plus eight helpers. A full table rejects new
launches before spawning, with a capacity message.

The chooser displays at most six profiles per page. Next page cycles through
all pages; Close remains visible on every page. A verified running row says
`<id> - running, close` and requests closing that session.

## Testing

`kilix-cap --laptop-test` covers discovery, seeding, strict parsing (the
rejection catalogue), session emission, provider argv mapping, and the
run registry's rules (identity read-back, legacy refusal, zombie rejection);
`--interaction-test` covers the chooser's request/geometry behavior plus
the lid tween and the running-row close request; `--scene-test`/
`--selftest` cover the object like any other.

`python3 tests/laptop_repairs.py` builds two small vendor-free tests. Process
creation, waiting, numeric signals, pidfds, and delays are mocked, with
synthetic procfs and registry files in a private temporary directory under
this checkout. It checks capacity rejection, interrupted reaping, registration
rollback, identity changes, unavailable pidfds, and every chooser profile's
open/close hit target for counts 0 through 16. Add `--sanitize` for UBSan.
These checks do not qualify terminal rendering or cross-provider integration.
