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

The run registry — `run/<id>.pid` beside the profiles, one ASCII pid per
file written 0600 at spawn — is one contract shared with
kilix-land-desktop, `kilix laptop`, and the launcher TUI, so a session
opened anywhere shows as running everywhere. Liveness is a real check:
`kill(pid, 0)` (EPERM counts as alive, a /proc zombie does not), never
the file alone; a stale or garbled entry is deleted by whichever reader
notices it. Kilix Cap consults the registry about once a second and
tweens the lid to match.

The chooser marks live sessions (`<id> - running, close`), and touching
such a row **closes** that session — `kilix laptop close <id>` when the
host verb exists, a SIGTERM to the recorded pid otherwise — instead of
opening a duplicate. Walking away just leaves the session running and
the lid open.

## Testing

`kilix-cap --laptop-test` covers discovery, seeding, strict parsing (the
rejection catalogue), session emission, provider argv mapping, and the
run registry's rules (record/read-back, stale cleanup, close semantics);
`--interaction-test` covers the chooser's request/geometry behavior plus
the lid tween and the running-row close request; `--scene-test`/
`--selftest` cover the object like any other.
