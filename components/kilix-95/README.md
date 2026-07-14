# Kilix 95

A Windows 95-style desktop rendered as **pixels** inside a Kilix pane, with an
optional Windows XP-style flavor.

Kilix 95 is not a window manager for the host X session. It is a Python desktop
surface that draws a complete desktop into a PIL framebuffer, sends that
framebuffer through the Kitty graphics protocol, and routes terminal keyboard
and mouse input back into its own widgets, windows, menus, and apps.

The normal entry point is:

```bash
kilix desktop
```

Quit through Start -> Shut Down..., or press `Ctrl+Alt+Q`.

## Release 0.1.1

Version 0.1.1 declares the provider/SDK contract, preserves the default-password
security baseline across provider choices, writes settings only to XDG user
configuration, and pins optional downloaded game/app sources to immutable
commits with safe archive extraction.

## Quick Start

From a normal Kilix session:

```bash
kilix desktop
```

For local development from this checkout:

```bash
cd ~/kilix-95
KILIX_HOME=~/kilix python3 main.py
```

For screenshot/test rendering without taking over the terminal:

```bash
KILIX_HOME=~/kilix python3 main.py --screenshot /tmp/shot.png --scene all
```

Useful screenshot scenes:

```text
desktop start filemgr notepad settings dialog launcher menu startup shutdown bsod all
```

## Relationship To Kilix

Kilix 95 is the authoritative desktop-provider checkout, intentionally hosted
by Kilix. The copy bundled in Kilix is a compatibility fallback; the launcher
reports which one it selected instead of silently preferring a divergent tree.
The Kilix launcher passes `KILIX_HOME` so this repo can use the host SDK and
launch helpers. If `KILIX_HOME` is unset, `host.py` falls back to `~/kilix`,
then a sibling `../kilix`, then `~/kilix` again.

The boundary is:

- `kilix_sdk.term`: raw mode and terminal input parsing.
- `kilix_sdk.graphics`: inline Kitty graphics for streamed sessions.
- Kilix CLI helpers: `kilix run`, `kilix browse`, `kilix serve`.
- Kitty remote control: `kitten @ launch` for new tabs and windows.

`provider.json` declares provider API 1, the required `kilix_sdk` 1.0 contract,
and the security behaviors the provider implements. Kilix validates that
data-only manifest and its implementation markers before executing the
provider. `main.py` also calls `kilix_sdk.require_compatible("1.0")` as a
defense-in-depth runtime check. Incompatible hosts fail early with a clear
version error.

Everything specific to the desktop lives here: the shell, taskbar, window
manager, widgets, built-in apps, Help, System Manual browser, games registry,
and tests.

## How Rendering Works

The desktop owns a single RGB framebuffer. On every dirty frame it draws:

1. the wallpaper and desktop icons;
2. normal and modal windows;
3. the taskbar;
4. menus, switcher overlays, tooltips, and cursor;
5. startup/shutdown/BSOD system screens when active.

The framebuffer is blitted through the Kitty graphics protocol:

- Local Kilix sessions write frame bytes to private files in `/dev/shm` and
  place them with Kitty `t=t`.
- Streamed `kilix serve` sessions use inline `t=d` when `KILIX_STREAM=1`.
- tmux passthrough is handled when `KILIX_STREAM=1` and `TMUX` are set.

Input uses the Kitty keyboard protocol plus SGR-pixel mouse reporting
(`?1003h` and `?1016h`). Mouse coordinates therefore map directly onto
framebuffer pixels.

Rendering is damage-driven. The event loop repaints only when something marks
the desktop dirty: input, resize, clock tick, caret blink, window/app updates,
screen saver changes, or periodic keepalive.

## Main Modules

| file | role |
|---|---|
| `main.py` | entry point, `Desk`, raw-mode lifecycle, input dispatch, render loop, blitting, screenshots |
| `theme.py` | Win95/XP identity, palettes, metrics, fonts, bevel primitives |
| `icons.py` | original pixel icons drawn on a 16x16 grid |
| `widgets.py` | retained widget toolkit: buttons, fields, text areas, lists, grids, menus, tabs, scrollbars |
| `wm.py` | window chrome, z-order, focus, modality, move/resize, dialogs |
| `taskbar.py` | Start menu, Help/System/Find menus, task buttons, quick launch, tray, clock |
| `shell.py` | desktop surface, launcher files, file associations, spawn verbs, browser/default-browser paths |
| `xdgapps.py` | freedesktop `.desktop` discovery and Start menu grouping |
| `games.py` | Games registry, on-demand installers, CLI launcher |
| `recycle.py` | recycle-bin backing store |
| `clipboard.py` | clipboard hub across desktop widgets, host X, and XPane displays |
| `vbox.py` | VirtualBox launcher detection and VM command construction |
| `apps/` | built-in windows such as File Manager, Settings, Help, System Manual, Notepad, Paint, WordPad, XPane |

Input dispatch order is:

```text
Desk -> MenuHost | drag owner | active/window hit | taskbar | shell
```

Windows capture the pressed widget until release. That is why buttons,
scrollbars, text selections, window drags, and list gestures keep working even
when the pointer moves during a drag.

## Start Menu

The Start menu is built in `taskbar.py`.

Top-level sections:

- **Programs**: built-in accessories, games, browser entries, terminals,
  media player, user launchers, and discovered XDG apps.
- **Documents**: recently opened files.
- **Settings**: Kilix settings, display properties, sound schemes, desktop
  flavor.
- **Help**: Help Topics, project how-tos, terminal how-tos, System Manual.
- **System**: update and maintenance entries when the relevant helpers exist.
- **Find**: file search.
- **Run**: command launcher.
- **Shut Down**: shutdown, restart, exit-to-terminal, update-and-restart.

The menu is data-driven through `widgets.MenuItem`, so submenus can be nested
without new widget code.

## Help And Manuals

Start -> Help contains:

- **System Manual**: searchable browser for installed man pages.
- **List**: opens the System Manual browser with the full local man-page list.
- **Kilix**: how-tos for Kilix, Kilix 95, Pleb, and Plebian-OS.
- **Terminal**: how-tos for terminal basics, tmux, and bash.
- **Help Topics**: the general two-pane desktop guide.

The System Manual browser scans the active manpath, lists entries as
`name (section)`, and renders the selected page in a read-only text pane.
It uses `man <section> <name>` with pager output disabled, then strips terminal
formatting so the result is readable in the desktop text widget.

Blue underlined Help links are live links. They call
`Shell.open_default_browser_tab()`, which tries:

1. `xdg-open`
2. `sensible-browser`
3. `gio open`

The opener runs inside a filled Kilix tab. This is deliberately separate from
launcher URL files and Start -> Programs -> Web Browser, which continue to use
the Kilix browser flow.

Current built-in Help link targets include:

- Kilix repository
- Kilix 95 repository
- Pleb repository
- Plebian-OS repository
- GNU Bash manual
- Bash source repository
- tmux project
- tmux manual
- Linux man-pages project

## Launch Modes

Kilix 95 has several launch paths, each with a different containment model.

| mode | used by | behavior |
|---|---|---|
| `tab` | terminal apps, launcher default | `kitten @ launch --type=tab` |
| `window` | launcher option | `kitten @ launch --type=os-window` |
| `run` | X11 apps | `kilix run COMMAND` in a Kilix tab |
| `fullscreen` | X11 app launcher option | XPane fullscreen-sized app window |
| `browse` | URL launcher files, Chromium tab mode | `kilix browse URL` |
| default browser | Help links | `xdg-open`/`sensible-browser`/`gio open` in a tab |

Firefox defaults to a filled `kilix run` tab so it stays contained in the
terminal pane. Chromium defaults to the Kilix browser path in tab mode because
GUI Chromium can be fragile under software rendering.

VirtualBox is special-cased. `.vbox` files and VirtualBox `.desktop` entries
open through `kilix run --refit-windows` so the VM window stays contained.

## Desktop Folder And Launchers

The desktop folder is:

```text
~/.local/share/kilix/desktop
```

Override it with:

```bash
KILIX_DESKTOP_DIR=/path/to/desktop kilix desktop
```

Real files and directories in this folder appear as icons. `.desktop` files,
including those created by **Create Launcher...**, appear as shortcuts.

Launcher example:

```ini
[Desktop Entry]
Type=Application
Name=htop
Exec=htop
Path=~/
Icon=terminal
X-Kilix-Open=tab
```

Supported `X-Kilix-Open` values:

- `tab`: run in a Kilix tab.
- `window`: run in a Kilix OS window.
- `run`: run an X11 app through `kilix run`.
- `fullscreen`: run as a full-desktop XPane window.
- `browse`: open a URL through `kilix browse`.

For URL launchers:

```ini
[Desktop Entry]
Type=Link
Name=Project page
URL=https://example.invalid/
Icon=browser
```

## Built-In Apps

Built-in apps are `wm.Window` subclasses opened through `apps.open(desk, name)`.
The shell catches app-launch exceptions and shows an error dialog, so a broken
app should not take down the desktop.

Notable apps:

| app | purpose | notes |
|---|---|---|
| File Manager | folder browsing and file operations | opens directories, routes files through shell associations, and supports context menus |
| Notepad | plain text editing | uses the shared text area widget and file dialogs |
| WordPad | richer document editing | targets `.krt` and RTF-style content |
| Paint | bitmap editing | useful for quick pixel/image edits inside the desktop |
| Viewer | image display | opens supported image files through Pillow |
| Amp | media playback front end | pairs with the sound scheme controls and external media helpers |
| Sound Control Panel | UI sound scheme editor | saves schemes under user data, not the repo |
| Settings | Kilix/Kitty configuration editor | writes the active `kitty.conf` and attempts live reload |
| Help | two-pane guide with live links | link rows open through the system default browser helper |
| System Manual | searchable man-page browser | scans manpath and renders selected pages as text |
| Task Manager | running-window list | can switch to windows, request close, or open Run |
| Recycle Bin | deleted-file browser | restores or purges files from the recycle backing store |
| Find Files | bounded desktop file search | walks in chunks from a tick hook so large trees do not block the UI |
| XPane | X11-app embedding | used by external graphical apps that should stay inside the desktop |

File associations live in `shell.py`. Important routes include directories to
File Manager, text files to Notepad, `.krt`/RTF files to WordPad, images to
Viewer, audio files to Amp, `.desktop` files to launcher handling, `.vbox` files
to VirtualBox handling, and executables through a Run/Edit prompt.

## Runtime State And User Data

Runtime state is intentionally outside the repo.

| data | default location |
|---|---|
| desktop folder | `~/.local/share/kilix/desktop` |
| desktop state | `.state.json` inside the desktop folder |
| recycle bin | `$KILIX_RECYCLE_DIR`, beside `$KILIX_DESKTOP_DIR`, or `~/.local/share/kilix/recycled` |
| generated/bundled sound cache | `~/.local/share/kilix/sounds` |
| games config | `~/.config/kilix/games.conf` |
| game/app downloads | `~/.local/share/kilix/games`, `~/.local/share/kilix/apps` |
| Kitty/Kilix settings | `$KITTY_CONFIG_DIRECTORY/kitty.conf`, else `${XDG_CONFIG_HOME:-~/.config}/kilix/kitty.conf` |

Settings is the most important host mutation: it edits the active Kitty/Kilix
configuration, not only desktop-local state.

Most user data can be reset independently:

- Delete the desktop `.state.json` to reset desktop layout, flavor, recent
  documents, first-run Help state, volume, and wallpaper choices.
- Remove or point `KILIX_DESKTOP_DIR` elsewhere to test with a fresh desktop
  folder.
- Empty the recycle directory only when you intentionally want to permanently
  discard recycled files.
- Delete generated sound caches if bundled sound assets or synth output need to
  regenerate; sound schemes live beside them and should be preserved when they
  are user-authored.
- Game installs are disposable caches, but `games.conf` records discovered or
  installed paths and should be kept if the user configured custom locations.

Tests rely on this separation. The harness sets `KILIX_DESKTOP_DIR` to a temp
folder, which also isolates the default recycle bin beside that folder.

## Desktop Flavor

Switch at runtime from:

```text
Start -> Settings -> Desktop Flavor
```

The same selector is available in kilix Settings on the Appearance tab.

The choice is saved in desktop state. For screenshots or first launch before
state exists:

```bash
KILIX_DESKTOP_FLAVOR=xp kilix desktop
KILIX_DESKTOP_FLAVOR=95 kilix desktop
```

`KILIX_FLAVOR` is also accepted as a fallback.

XP flavor reference:

![Kilix 95 XP flavor desktop](docs/kilix-xp.png)

## Settings App

The Settings app edits the active `kitty.conf`.

It normally writes:

```text
$KITTY_CONFIG_DIRECTORY/kitty.conf
```

or, when that variable is absent:

```text
${XDG_CONFIG_HOME:-~/.config}/kilix/kitty.conf
```

The Kilix launcher creates that user file with a relative include of its
managed `.kilix-defaults.conf` link. The launcher refreshes the link after a
checkout move. Settings atomically writes only the user file and never dirties
the host checkout.

Form tabs rewrite only managed keys and preserve the rest of the file,
including comments. The raw `kitty.conf` tab exposes the whole file. Apply
reloads live through:

```bash
kitten @ action load_config_file
```

If remote control is unavailable, Settings falls back to `SIGUSR1` at
`$KITTY_PID`. If neither path works, it saves the file and tells the user to
reload manually.

The form tabs cover common appearance and behavior settings:

- font family and font size;
- foreground/background colors and opacity;
- cursor shape;
- tab bar style;
- scrollback and close-confirmation behavior;
- audio bell, copy-on-select, mouse-hide timing, and cursor blink timing.

Settings rewrites only a key that the user changed. If a key is already present
more than once, the last occurrence is treated as the active one, matching
Kitty's normal semantics. If a managed key is missing, Settings appends it under
a small Kilix desktop marker block instead of rearranging the file.

The raw `kitty.conf` tab is intentionally available for settings not modeled by
the form. Switching away from that tab preserves raw edits in the in-memory
buffer; pressing Apply or OK writes them.

Failure modes should be user-visible:

- inability to read the config opens an empty buffer rather than crashing;
- inability to write shows an error dialog;
- reload failure leaves the saved file in place and gives a manual reload hint.

## XPane

XPane embeds a host X11 application inside a Kilix 95 window:

1. start a private Xvfb;
2. run the app on that display;
3. capture frames with ffmpeg rawvideo;
4. chroma-key the X root background;
5. inject mouse/keyboard input through XTest;
6. bridge clipboard selections back into the desktop clipboard hub.

This is dependency-heavy, but it lets skinned or graphical apps live inside
the pixel desktop rather than escaping as unmanaged host windows.

XPane windows are chromeless from the Kilix 95 point of view. The app draws its
own skin or title bar inside the captured Xvfb surface, and Kilix 95 composites
only the opaque pixels. Chroma-keyed background pixels fall through so clicks can
land on desktop icons or windows behind the app.

The app's native Xvfb size is fixed at launch. When the Kilix 95 window is
resized, the captured frame is scaled and mouse coordinates are mapped back to
the native size. This avoids restarting Xvfb/ffmpeg on every resize.

XPane also advertises a tiny EWMH-compatible surface to the private X server.
That lets many GTK/Qt title-bar minimize/maximize requests turn into Kilix 95
window operations without taking over as a full window manager.

Every XPane owns a stream supervisor. Closing the window tears down the app,
ffmpeg, Xvfb, clipboard bridge, fd hooks, and tick hooks. A startup failure
should become a dialog rather than an uncaught exception from the desktop loop.

Limitations:

- terminal/TUI apps should not be launched through XPane because private Xvfb
  has no usable TTY for them;
- GL-heavy apps may be constrained by software rendering;
- clipboard bridging handles text-oriented CLIPBOARD selection, not arbitrary
  large binary clipboard transfers;
- ffmpeg/Xvfb failures close the pane or show an error instead of retrying
  indefinitely.

## Games

The Games menu is backed by `games.py`. Some entries are built-in desktop games,
while others are installed on demand under user data directories.

The installers avoid writing into this checkout. Downloaded archives that ship
with pinned checksums are verified before use, and tar extraction rejects unsafe
paths, links, devices, and FIFOs.

Games and optional apps currently include Doom/DOSBox paths plus terminal or
Kitty-graphics projects such as Bashed Earth, Joustix, Terminal Lander, Kitty
Brokeout, and kilix-amp support.

Game readiness checks are conservative. `games.py` first looks for a configured
working install, then for tools already on `$PATH`, then for previously vendored
assets under user data. Only if those paths fail does it offer an installer.

The installer path is designed for visible progress:

1. the desktop opens a tab or installer window;
2. stdout/stderr are captured into a short log;
3. successful setup records paths in `games.conf`;
4. failure leaves a readable error instead of closing silently.

Doom/DOSBox support writes a DOSBox config tuned for full-pane display and sound.
Native terminal/Kitty-graphics games are fetched at full immutable commit SHAs
and built under user data with `make`. Existing source caches must retain the
expected origin, pinned HEAD, and a clean tracked worktree. Build failures
include a dependency hint in the error text.
An explicitly configured different `dir` in `games.conf` remains user-managed
and is treated as a trusted local executable rather than a Kilix-managed cache.

Because these are optional downloads and builds, a fresh Plebian-OS image should
still boot the desktop and pass the core UI tests without preinstalling every
game dependency.

## Requirements

This repository does not currently ship packaging metadata such as
`pyproject.toml` or a requirements file. The surrounding Kilix/Plebian-OS
provisioning is expected to install the runtime dependencies.

Common requirements by feature:

- Python 3
- Pillow
- Kilix checkout with `config/kilix_sdk`
- Kitty/kitten remote control
- ffmpeg for XPane capture
- Xvfb and XTest support for XPane
- python-xlib for XPane and clipboard bridging
- `man`/`manpath` for System Manual
- `xdg-open`, `sensible-browser`, or `gio` for Help live links
- audio players such as `paplay`, `aplay`, `ffplay`, or `play` for UI sounds
- browsers/VirtualBox only when those launch paths are used

Dependency failures should degrade by feature:

- missing `man` affects only System Manual;
- missing default-browser openers affects only live Help links;
- missing audio players mutes UI sounds;
- missing Xvfb/ffmpeg/python-xlib affects XPane and GUI app embedding;
- missing browser binaries affects browser launch entries;
- missing Kitty remote control affects tab/window launches.

This split is deliberate. The desktop should still render, handle input, open
built-in pure-Python apps, and show useful error dialogs when optional host
features are absent.

For provisioning, install dependencies at the Plebian-OS/Pleb layer rather than
vendoring them into this repo. This keeps Kilix 95 as a desktop source checkout
with user state and system packages managed by the surrounding system.

## Testing

Run the full suite:

```bash
python3 tests/run.py
```

The test runner executes each `test_*.py` in a fresh subprocess and gives it a
temporary `KILIX_DESKTOP_DIR`. Most tests construct an offscreen `Desk(term=None)`
and feed synthetic widget/input events, so they do not require taking over the
terminal.

Focused checks:

```bash
python3 tests/test_winhelp.py
python3 tests/test_manual.py
python3 tests/test_shell_xpane.py
python3 tests/test_start_help_menu.py
```

Render screenshot fixtures:

```bash
KILIX_HOME=~/kilix python3 main.py --screenshot /tmp/shot.png --scene all
```

Test style:

- Tests are plain Python scripts, not pytest modules.
- Each script should be runnable directly with `python3 tests/test_name.py`.
- Use `tests/harness.py` for offscreen desks and synthetic input events.
- Prefer temp directories and monkeypatching over touching the real desktop,
  manpath, recycle bin, or system apps.
- Keep integration launch tests at the shell boundary by stubbing `_tab`,
  `_popen`, `open_in_xpane`, or external discovery helpers.

When adding a desktop feature, add the narrowest test that proves the contract:

- menu entries: open Start offscreen and walk `MenuItem` trees;
- widgets/windows: construct a `Desk(term=None)`, add the window, and send
  synthetic key/mouse events;
- file behavior: isolate with temp dirs and environment overrides;
- host launch behavior: monkeypatch discovery/spawn methods and assert argv;
- parser behavior: feed raw bytes through the harness term helpers.

The full suite is intentionally fast enough to run before every commit.

## Environment Variables

| variable | effect |
|---|---|
| `KILIX_HOME` | host Kilix checkout |
| `KILIX_DESKTOP_DIR` | desktop folder override |
| `KILIX_RECYCLE_DIR` | recycle-bin override |
| `KILIX_DESKTOP_FLAVOR` | `95` or `xp` first-launch flavor |
| `KILIX_FLAVOR` | fallback flavor selector |
| `KILIX_STREAM=1` | inline graphics mode for streamed sessions |
| `KILIX_NO_SOUND=1` | disable UI sound playback |
| `KILIX_HOST_CLIP=0` | disable host clipboard bridge |
| `KILIX_XPANE_WM=0` | disable XPane's minimal EWMH bridge |
| `KILIX_STARTUP_SCREEN_SECONDS` | startup screen duration clamp override |
| `KILIX_SHUTDOWN_SCREEN_SECONDS` | shutdown screen duration clamp override |
| `MANPATH` | manual page roots for System Manual |
| `KITTY_CONFIG_DIRECTORY` | settings file directory |
| `KITTY_LISTEN_ON` | required for Kitty remote-control launches |
| `KITTY_PID` | fallback reload signal target for Settings |

Common development examples:

```bash
# fresh, isolated desktop state
KILIX_DESKTOP_DIR=$(mktemp -d) KILIX_HOME=~/kilix python3 main.py

# XP flavor screenshot without changing saved state
KILIX_DESKTOP_FLAVOR=xp KILIX_HOME=~/kilix \
  python3 main.py --screenshot /tmp/xp.png --scene desktop

# disable sound while debugging UI behavior
KILIX_NO_SOUND=1 KILIX_HOME=~/kilix python3 main.py

# test System Manual against a controlled manpath
MANPATH=/tmp/test-man KILIX_HOME=~/kilix python3 main.py
```

Variables set by the host environment, such as `KITTY_LISTEN_ON`,
`KITTY_WINDOW_ID`, `KITTY_CONFIG_DIRECTORY`, `DISPLAY`, `TMUX`, and
`KILIX_STREAM`, should generally be inherited from Kilix rather than invented by
tests or launch scripts unless the test is explicitly about that path.

## Troubleshooting

**Start menu opens but launching a tab fails**

Check that `KITTY_LISTEN_ON` is set and that `kitten` is reachable from the
Kilix checkout or `$PATH`.

If this happens only outside Kilix, it is expected: tab/window launches require
Kitty remote control from a live Kilix/Kitty session. Use screenshot mode or
offscreen tests for noninteractive development.

**System Manual is empty**

Check that manual pages are installed and that `manpath -q` returns useful
roots. If needed, set `MANPATH` explicitly before launching the desktop.

Also check that the man directories contain section folders such as `man1`,
`man5`, or `man8`, and files named like `bash.1.gz` or `ssh_config.5.gz`.

**Help links do not open**

Install or configure one of `xdg-open`, `sensible-browser`, or `gio`. Help links
use the system default browser path; URL launcher files still use `kilix browse`.

If the opener exists but nothing appears, try the same URL from a regular
terminal with `xdg-open URL`. The Help path launches the opener in a filled
Kilix tab; it does not choose or install a browser itself.

**X11 apps fail to open in desktop windows**

Check for Xvfb, ffmpeg, python-xlib, XTest support, and an available browser/app
binary. XPane failures should show an error dialog instead of killing the
desktop.

**Settings saves but the terminal does not change**

The config file was written, but live reload failed. Use Kitty's reload action
manually or restart Kilix.

Check whether `KITTY_LISTEN_ON` is set for `kitten @ action load_config_file`.
If it is not, Settings tries `SIGUSR1` through `KITTY_PID`. If neither is
available, saved changes will apply on the next Kilix restart.

**A file opens in the wrong app**

File associations are centralized in `shell.py`. Check the extension routing in
`open_path()` and the launcher handling for `.desktop` files before changing an
individual app.

**Recycle Bin restore lands at a different name**

Restore avoids overwriting existing files. If the original path is occupied, the
restored item gets a disambiguated name like `file (2).txt`.

**A game installer fails**

Read the installer tab/log text first. Network failures, checksum mismatches,
missing compilers, and missing development libraries should be reported there.
Installed or partially installed assets live under user data, not the repo.

**The desktop appears blank or mis-sized**

Resize the terminal once, or run a screenshot scene to separate rendering
problems from terminal graphics transport problems:

```bash
KILIX_HOME=~/kilix python3 main.py --screenshot /tmp/shot.png --scene desktop
```

## Fonts And Authenticity

No Microsoft artwork or fonts are bundled. Icons are original pixel art and
text is DejaVu Sans 11px rendered without antialiasing. If you own period fonts,
drop `.ttf` or `.otf` files into `assets/fonts/` (gitignored) and they are
picked up by preference.
