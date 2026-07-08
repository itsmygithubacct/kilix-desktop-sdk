# Kilix 95

A Windows 95-style desktop rendered as **pixels** inside a Kilix pane, with an
optional Windows XP-style flavor.

The normal entry point is still:

```bash
kilix desktop
```

When this repository is checked out separately, the Kilix launcher passes
`KILIX_HOME` so Kilix 95 can use the host's Kitty graphics helpers, `kilix run`,
`kilix browse`, and remote-control launcher. If `KILIX_HOME` is unset, Kilix 95
looks for the host checkout at `~/kilix`.

Quit via Start ▸ Shut Down…, or `Ctrl+Alt+Q`.

## How it works

The whole desktop is a PIL RGB framebuffer blitted through the kitty
graphics protocol — the same transport `kilix browse` uses: `t=t` via
`/dev/shm` locally, inline `t=d` when `KILIX_STREAM=1` (inside
`kilix serve` sessions). Input is the kitty keyboard protocol plus
SGR-pixel mouse reporting (`?1003h`/`?1016h`), so mouse coordinates map
1:1 onto framebuffer pixels. Rendering is damage-driven: the loop only
repaints when something is dirty (input, clock tick, caret blink).

Reuses from the Kilix host checkout: `config/browse.py` (`Term`, raw mode and
input parsing), `config/gfx.py` (inline graphics for streamed sessions), and
the XPane helpers used by embedded X11 apps. The window manager, shell, widgets,
apps, games registry, and tests live in this repository.

## Modules

| file | what |
|---|---|
| `main.py` | entry point: `Desk` (event loop, dispatch, blit), `--screenshot` test mode |
| `theme.py` | flavor identity, Win95/XP palettes, metrics, fonts, bevel primitives |
| `icons.py` | the icon set, drawn in code on a 16×16 grid (crisp at 16/32 px) |
| `widgets.py` | toolkit: Button, TextField, TextArea, ListBox, IconGrid, Menu/MenuHost, TabBar, Dropdown, Scrollbar… |
| `wm.py` | `Window` (chrome, sysbuttons) + `WM` (z-order, drags, modality) + `msgbox`/`inputbox` |
| `taskbar.py` | start bar: Start button/menu, task buttons, clock |
| `shell.py` | desktop surface: wallpaper, icon grid, launcher files, spawn verbs |
| `games.py` | Games/app registry + on-demand installers (Doom, Bashed Earth, kilix-amp) + CLI launcher |
| `apps/` | `filemgr` `notepad` `settings` `viewer` `amp`; `xpane` (X11-app-in-a-window) — each a `Window` subclass |

Input events flow Desk → (MenuHost | dragged owner | window | taskbar |
shell); windows capture the pressed widget until release, which is what
gives every widget drag behavior for free.

## The desktop folder

`~/.local/share/kilix/desktop` (override: `$KILIX_DESKTOP_DIR`). Real files
and directories in it appear as desktop icons; `*.desktop` files (created by
**Create Launcher…**) appear as shortcuts. Launcher spec, freedesktop-style:

```ini
[Desktop Entry]
Type=Application          ; or Link (+ URL=…) for kilix browse
Name=htop
Exec=htop
Path=~/                   ; optional working dir
Icon=terminal             ; a name from icons.py
X-Kilix-Open=tab          ; tab | window | run (X11 via kilix run) | browse
```

## Desktop flavor

Switch at runtime from Start -> Settings -> Desktop Flavor. The choice is saved
in the desktop state file. For screenshots or first launch before state exists,
set `KILIX_DESKTOP_FLAVOR=xp` or `KILIX_DESKTOP_FLAVOR=95`.

## Settings app

Edits `$KITTY_CONFIG_DIRECTORY/kitty.conf` (i.e. `config/kitty.conf`).
Form tabs rewrite only the managed keys (last occurrence, preserving the
rest of the file); the `kitty.conf` tab is the raw file. Apply reloads the
running kilix live via `kitten @ action load_config_file`, falling back to
`SIGUSR1` at `$KITTY_PID`.

## Testing without a terminal

```bash
KILIX_HOME=~/kilix python3 main.py --screenshot /tmp/shot.png --scene all
# scenes: desktop start filemgr notepad settings dialog launcher menu all
```

## Fonts / authenticity

No Microsoft artwork or fonts are bundled; icons are original pixel art and
text is DejaVu Sans 11px rendered without antialiasing. If you own period
fonts, drop `.ttf` files into `assets/fonts/` (gitignored) and they are picked
up by preference.
