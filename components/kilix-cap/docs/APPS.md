# App and system-tool launch contract

Every app-like mansion object dispatches a fixed executable/argument vector
from the object click itself. Kilix Cap never opens a shell, never expands
room text into arguments, and never passes note/draft/hover content to another
program.

## Study app mappings

Programs are searched through `PATH` in the order shown. If `PATH` is empty,
the search path is `/usr/local/bin:/usr/bin:/bin`.

| Study prop | Candidate programs and fixed fallback |
|---|---|
| Clock | `gnome-clocks` → `kclock` → `xdg-open https://time.is` |
| In box / Out box | `thunderbird` → `evolution` → `kmail` → `xdg-email` |
| Mail, no saved target | `thunderbird` → `evolution` → `kmail` → `xdg-email` |
| Mail, saved program | `kilix run PROGRAM` |
| Mail, saved URL | `kilix run firefox-esr URL` |
| Profile | `gnome-contacts` → `kaddressbook` → `thunar` → `nautilus` → `dolphin`, opening HOME or the startup directory |
| Notepad | `mousepad --disable-server` → registered `text/plain` app through `gtk-launch` → `xed` → `gedit` → `pluma` → `leafpad` → `featherpad` → `kate` → `kwrite` → `notepad.exe` → `libreoffice --writer` → `abiword`; child cwd is `~/Documents` |
| Dates | `gnome-calendar` → `korganizer` → `xdg-open https://calendar.google.com` |
| Contacts | `gnome-contacts` → `kaddressbook` → `xdg-email` |
| Files | `thunar` → `nautilus` → `dolphin` → `xdg-open`, opening Kilix Cap's startup directory |
| Phone | `gnome-calls` → `xdg-open tel:`, only when a default `x-scheme-handler/tel` exists |
| Writer | `libreoffice --writer` → `abiword` |
| Calculator | `gnome-calculator` → `kcalc` → `qalculate-gtk` → `xcalc` |
| Web | Hidden authenticated Kilix tab running `kilix run firefox-esr URL`, then exact-window focus after the Study animation |

Notepad requires an absolute HOME and an accessible `~/Documents`. The
registered editor fallback accepts one bounded `.desktop` identifier returned
by `xdg-mime query default text/plain`.

Mail and Web share the optional private configuration at
`~/.local/gpu_terminal/kilix-cap/config` (or the absolute
`KILIX_CAP_CONFIG_HOME`). `mail_target` may be an executable name, absolute
executable path, or `http(s)` URL. `web_home` must be one `http(s)` URL:

~~~text
web_home=https://news.ycombinator.com/
~~~

Hacker News is the compiled default when the line or file is absent or
invalid. Whitespace, relative URLs, non-HTTP schemes, and control characters
are rejected. Saving Mail preserves the validated Web value. With no mail
target, Mail opens an installed mail app directly rather than presenting
setup UI.

## Computer background handoff

The Computer does not immediately steal focus. It resolves `kilix`,
`python3`, `firefox-esr`, the authenticated `kitten`, its password file, and
the checkout-local browser helper, then invokes this literal plan:

~~~text
/absolute/kitten @ --password-file /absolute/rc-password launch \
  --type=tab --cwd=current --self --keep-focus --tab-title Web \
  --env KILIX_IN_OVERLAY=1 \
  --env KILIX_RUN_LOG=PRIVATE_READY_LOG -- \
  /resolved/kilix run /resolved/python3 \
  /absolute/kilix-cap/tools/kilix_browser.py \
  /resolved/firefox-esr VALIDATED_WEB_HOME
~~~

Kilix returns the new numeric window ID. Kilix Cap accepts only a bounded
all-digit nonzero ID. The helper starts Firefox with a unique temporary profile
and `--new-instance --new-window VALIDATED_WEB_HOME`, preventing an unrelated
Firefox instance from consuming the URL. Kilix Cap keeps the tab hidden until
the app-stream log reports capture readiness. Kilix 0.1.4 and newer record
`content-ready=changed` for the first changed capture after the startup
snapshot. If no changed capture arrives, it records
`content-ready=initial-grace` after an initial capture has been emitted and the
three-second grace has elapsed. The grace path accommodates applications that
completed a static first paint before capture began; it is a capture-handoff
heuristic, not proof that network navigation finished. Kilix Cap also accepts
the legacy `content-frames=1` changed-frame marker, including the timestamped
record produced by pre-0.1.4 Kilix versions, which do not provide the grace
path.

Kilix's event-driven XDamage capture atomically extracts the server's
accumulated damage through an XFixes region and checks python-xlib's in-process
event queue before sleeping, so a network-driven repaint cannot be cleared or
queued unseen. After a 0.75-second frame-settle interval and the final zoom
frame, Kilix Cap invokes:

~~~text
/absolute/kitten @ --password-file /absolute/rc-password \
  focus-window --match id:CAPTURED_ID
~~~

No title, URL fragment, process output, or pointer text participates in the
focus selector. The readiness log is a private regular file under the local
configuration directory and the browser helper removes it when the streamed
Firefox process exits.

## Server, Library, and Balcony desktop mappings

| Physical object | Candidate programs / fixed target |
|---|---|
| System settings console | `xfce4-settings-manager` → `gnome-control-center` → `systemsettings` |
| Storage rack | `gnome-disks` → `partitionmanager` → `gparted` |
| Software cabinet | `synaptic` → `gnome-software` → `plasma-discover` |
| Network patch panel | `nm-connection-editor` → `systemsettings` → `gnome-control-center network` |
| First Steps book | `xdg-open /absolute/kilix-cap/README.md` |
| Rooms book | `xdg-open /absolute/kilix-cap/docs/INTERACTIONS.md` |
| Objects book | `xdg-open /absolute/kilix-cap/docs/INTERACTIONS.md` |
| Sound book | `xdg-open /absolute/kilix-cap/docs/APPS.md` |
| Colophon book | `xdg-open /absolute/kilix-cap/docs/ENGINE.md` |
| Weather cabinet | `gnome-weather` → `kweather` → `meteo-qt` |
| Brass telescope | `stellarium` → `kstars` |

Document and helper paths are derived from `/proc/self/exe`, require regular
readable files beneath the checkout containing `bin/kilix-cap`, and are never
taken from pointer text.

## Monitor and Housekeeping tabs

The two Server monitors and all Cleaning Room stations launch through Kilix's
authenticated remote-control boundary:

~~~text
/absolute/kitten @ --password-file /absolute/rc-password launch \
  --type=tab --cwd /absolute/kilix-cap --self --tab-title FIXED_TITLE -- \
  /resolved/python3 /absolute/kilix-cap/tools/mansion_tui.py MODE [FOCUS]
~~~

`MODE` is exactly `logs`, `activity`, or `cleanup`. Cleanup `FOCUS` is exactly
`temp`, `trash`, `cache`, `packages`, or `all`. All values come from compiled
enum mappings; none is user-controlled.

The `logs` and `activity` modes are read-only. Cleanup actions remain inside
the helper and require an explicit second confirmation. The only privileged
vectors are:

~~~text
pkexec /resolved/apt-get clean
pkexec /resolved/journalctl --vacuum-time=14d
~~~

## Kilix 95 games

A validated game ID launches:

~~~text
/absolute/kitten @ --password-file /absolute/rc-password launch \
  --type=tab --cwd /absolute/kilix-95 --self --tab-title GAME_ID -- \
  /resolved/python3 /absolute/kilix-cap/tools/kilix95_games.py \
  launch /absolute/kilix-95 GAME_ID
~~~

Minesweeper and Solitaire use the same vector with helper mode `builtin`.
Registry IDs are limited to lowercase ASCII letters, digits, and internal
hyphens. Catalog discovery uses temporary storage and is read-only; launching
a selected title enters Kilix 95's normal installer/runner boundary.

## Process and safety boundary

All plans are literal arrays passed to `posix_spawn`. Child standard input,
output, and error are isolated for desktop apps. Live TUIs and games receive a
fresh terminal tab from Kilix remote control. Association probes use fixed
`xdg-mime` arguments, bounded output, and an approximately one-second timeout.

External launching is enabled only when real/effective user and group IDs
match. `KILIX_CAP_EXTERNAL_APPS=0` (also `off`, `false`, or `no`) disables it.
Kilix Cap reports success or the concise failure in the name bar and leaves
the originating room usable.

Kilix Cap itself does not make a network request. A mapped desktop program,
web mapping, or selected game may access the network, filesystem, or desktop
services according to that separate program's behavior.
