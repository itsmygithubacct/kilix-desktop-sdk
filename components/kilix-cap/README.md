# kilix-cap

kilix-cap 3.0.0 is a graphical mansion interface for terminals that support
the Kitty graphics protocol. It renders a true-RGB 480×320 logical canvas and
presents it at an integer scale so the room art, physical objects, and bitmap
type remain crisp.

The mansion has eight connected, full-color rooms:

- **Study** — thirteen physical desk props launch their mapped desktop apps
  immediately. No prop opens a built-in textual list first.
- **Grand Gallery** — an elegant perspective corridor with six side doors and
  a glazed Balcony entrance at the far end.
- **Storeroom** — movable boxes and containers can be dragged between two
  shelves.
- **Server Room** — two live monitors and four administration consoles sit
  among racks, copper pipes, patch cables, and status lights.
- **Game Room** — the live Kilix 95 catalog appears as physical CDs, floppies,
  and manuals; selecting one starts that title in a new Kilix tab.
- **Library** — five physical volumes open the real project documents in the
  system viewer.
- **Cleaning Room** — the basin, copper bin, cache drawers, and maintenance
  terminal open a bounded Housekeeping TUI.
- **Balcony** — the Gallery's end door opens onto a panoramic exterior with
  direct Weather and stargazing launchers.

Every room begins with a committed generated background image. Doors are
generated as edits of their respective rooms and remain native to those
plates. Dynamic Study props, Storeroom items, and Game Room media stay in
separate layers where their state needs to change. Baked physical consoles,
books, instruments, and doors use explicit object-sized hit regions and
identify themselves in the name bar without painting button boxes over the
room.

## Build and run

Kilix Cap currently targets Linux desktop systems. The renderer and input core
use C11 and POSIX interfaces; direct app launching, authenticated Kilix tabs,
system monitors, and housekeeping additionally integrate with Linux facilities
such as `/proc`, XDG desktop tools, `pkexec`, and optional APT/systemd
utilities. Missing optional desktop utilities disable only their mapped
interaction and produce a concise status message.

The build requires a C11 compiler, POSIX threads, zlib, libm, Python 3, and
Python's standard `curses` module. It downloads nothing.

~~~sh
make
./bin/kilix-cap
~~~

Run it in Kitty, Kilix, Ghostty, WezTerm, or another terminal implementing the
Kitty graphics protocol. With no modal surface open, `q` or Escape exits.

The bottom strip is a direct **house map**: Study, Gallery, Store, Server,
Games, and Clean navigate immediately; Lamp toggles the room-light accent.
The Gallery doors provide the spatial mansion route, including Library and
Balcony.

Optional audio uses `pacat`, `pw-play`, `aplay`, or SoX `play` when available:

~~~sh
KILIX_CAP_AUDIO=0 ./bin/kilix-cap
~~~

External launches can likewise be disabled:

~~~sh
KILIX_CAP_EXTERNAL_APPS=0 ./bin/kilix-cap
~~~

When launching is disabled or an app is unavailable, the room remains in
place and the concise reason appears temporarily in the name bar.

## Direct app behavior

The Study's Clock, Inbox, Outbox, Mail, Profile, Notepad, Dates, Contacts,
Files, Phone, Writer, Calculator, and Web props all queue their real mapping
from the object click itself. The launcher uses fixed argument vectors passed
directly to `posix_spawn`; it never invokes a shell.

Mail uses the saved target when one exists. Without one, it opens the first
installed desktop mail program (or `xdg-email`) directly. The optional saved
target and Web home remain a private file at
`~/.local/gpu_terminal/kilix-cap/config`; set `KILIX_CAP_CONFIG_HOME` to an
absolute directory to relocate it. A target is one executable name/absolute
path or one `http(s)` webmail URL, never a command line.

The Computer defaults to `https://news.ycombinator.com/`. Its click creates a
Firefox ESR tab in the background with an isolated temporary profile and an
explicit `--new-window` start page. A compact green boot sequence runs on the
physical Study monitor while Kilix captures the browser. The glass zoom begins
only after Kilix reports a changed content frame beyond the blank startup
snapshot, and only then does the exact captured tab receive focus. Override the
start page by adding a single strict URL line to the private config:

~~~text
web_home=https://example.org/
~~~

Only an `http://` or `https://` URL without whitespace is accepted. A missing
or invalid value falls back to Hacker News.

The Server Room maps:

| Physical object | Direct result |
|---|---|
| Left monitor | Live green-on-black TUI with system logs, warning-or-higher alerts, and local system mail. |
| Right monitor | Live TUI with user processes and active TCP/UDP network connections. |
| Brass console | Installed system settings application. |
| Service rack | Installed disk/storage administration application. |
| Patch panel | Installed network settings application. |
| Right cabinet | Installed software administration application. |

The two monitor TUIs are read-only, refresh every two seconds, and open in
fresh authenticated Kilix tabs. Press `r` to refresh or `q` to close.

Library books use `xdg-open` on actual files under this checkout. Balcony
instruments prefer installed Weather and astronomy applications. Exact
candidate order is documented in [docs/APPS.md](docs/APPS.md).

## Housekeeping safety

Cleaning Room stations open `tools/mansion_tui.py cleanup` in a fresh Kilix
tab. It previews every target and requires a second explicit `y`
confirmation before changing anything.

The fixed actions are:

- user-owned `/tmp` entries older than seven days;
- the current user's thumbnail cache;
- the APT download cache via `pkexec apt-get clean`;
- system journals older than fourteen days via
  `pkexec journalctl --vacuum-time=14d`; and
- desktop Trash via `gio trash --empty`, with a bounded user-Trash fallback.

Symlinks are unlinked rather than followed. The helper never accepts a path or
command from room text, and privileged work remains behind the desktop's
`pkexec` policy and authentication prompt. Merely entering the Cleaning Room
or opening Housekeeping removes nothing.

## Game Room

The Game Room reads Kilix 95's own `games.GAMES` registry without modifying
its storage, prepends Minesweeper and Solitaire, and polls its source once per
second. Each current title becomes one generated CD case, floppy disk, or
manual carrying that title's original Kilix 95 pixel icon. Hover reveals the
full title; click launches it in a fresh authenticated Kilix terminal tab.

By default the checkout is the `kilix-95` sibling of this project.
`KILIX95_PROJECT_HOME` can select another absolute checkout. Catalog discovery
is read-only. A selected game's normal Kilix 95 installer may download and
persist its pinned content after that explicit launch.

## Verify

~~~sh
make test

./bin/kilix-cap --interaction-test
./bin/kilix-cap --launcher-test
./bin/kilix-cap --game-catalog-test
./bin/kilix-cap --visual-test
./bin/kilix-cap --audio-test
python3 tools/mansion_tui.py selftest
python3 tools/validate_visual.py
python3 tests/pty_smoke.py --binary ./bin/kilix-cap

render_dir=$(mktemp -d)
./bin/kilix-cap --render-test "$render_dir"
python3 tools/check_render.py "$render_dir"

make sanitize
~~~

The release render set contains all eight base rooms plus direct-object hover
and Storeroom movement states. The visual validator checks the exact
33-file art inventory, dimensions, hashes, generation prompts, eight opaque
RGB plates, game-media alpha, and all thirteen semantic Study hit IDs.

## Runtime boundary and provenance

Kilix Cap itself makes no runtime network request, downloads nothing, and
never regenerates committed art. A separately launched desktop application or
selected Kilix 95 game may access the network or persist data according to its
own behavior.

The mansion plates and seven room-specific door editions were created with
the OpenAI built-in image generation tool, then center-fitted offline to
480×256 P6 RGB with `tools/prepare_visual.py`. Every door edition edits its
own room source, so its perspective, trim, materials, illumination, and
shadows belong to that scene. Their complete prompts, dimensions, roles,
generator-output hashes, lossless public-snapshot records, and earlier
room/sprite lineage are in
[docs/visual-provenance.json](docs/visual-provenance.json). The clean-room
asset boundary and explicit asset-license scope are recorded in
[COPYING-ASSETS.md](COPYING-ASSETS.md).

Detailed behavior is in [docs/INTERACTIONS.md](docs/INTERACTIONS.md), app and
TUI launch vectors in [docs/APPS.md](docs/APPS.md), and engine invariants in
[docs/ENGINE.md](docs/ENGINE.md).

## License

Kilix Cap's code, documentation, generated visual pixels, project-authored
visual transformations, and rendered audio outputs are available under the
[MIT License](LICENSE) to the extent contributors hold licensable rights in
them. Identified third-party code, CC0/public-domain source recordings, and
provider-issued C2PA metadata retain their own notices or legal status. The
precise asset scope and exceptions are documented in
[COPYING-ASSETS.md](COPYING-ASSETS.md), and vendored notices are indexed in
[docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).
