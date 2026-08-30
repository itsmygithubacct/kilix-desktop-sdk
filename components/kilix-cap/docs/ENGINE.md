# Engine contract

This document records the implementation invariants of kilix-cap 3.0.0.

## 1. Platform and lifecycle

The runtime is C11 plus POSIX, pthreads, zlib, and libm. Terminal lifecycle,
Kitty graphics/keyboard parsing, software rasterization, and PCM mixing are
vendored and built from source. Python 3's standard library supplies the
separate monitor/Housekeeping TUIs. The build fetches nothing.

Platform code owns terminal I/O, 30 Hz pacing, resize handling,
integer-scaled presentation, and emergency restoration. Fatal-signal teardown
uses only the vendored async-signal-safe restore path. Headless subcommands
never initialize a terminal session.

## 2. Canvas and generated rooms

The logical canvas is exactly 480×320:

| Zone | Geometry |
|---|---|
| Name bar | y=0, h=24 |
| Room content | y=24, h=256 |
| House map | y=280, h=40 |

Compile-time assertions hold the adjacency and total. Presentation uses
integer scaling with black letterboxing. The canvas is opaque true RGB; there
is no palette quantizer.

All eight scenes begin with strict opaque 480×256 P6 room plates:

~~~text
workdesk-room.ppm
hallway-room.ppm
storeroom-room.ppm
server-room.ppm
game-room.ppm
library-room.ppm
cleaning-room.ppm
balcony-room.ppm
~~~

Their preserved 1717×916 PNGs are provenance sources and are not loaded at
runtime. Study props use a second full-room RGB layer, anti-aliased coverage
map, and thirteen-ID semantic map. Seven room plates are prepared from
room-specific image edits with their doors fitted directly into the
architecture; the Balcony entrance was already native to its source. Game
media uses a generated 3×3 RGB/alpha atlas. Storeroom items remain code-drawn
movable objects.

The executable locates all runtime P6 files relative to itself, with a
working-directory fallback. `KILIX_CAP_VISUAL_DIR` can select an alternate
directory. A candidate bundle loads atomically so room plates and masks from
different locations cannot mix. Interactive mode has procedural fallbacks;
visual/release commands require the complete bundle.

The exact 33-file visual inventory, prompts, preparation, dimensions, and
hashes are in [visual-provenance.json](visual-provenance.json).

## 3. Object model and picking

`Object.kind` distinguishes:

- scenery (`OBJ_PLAIN`);
- generated Study props (`OBJ_PROGRAM`);
- conventional map/panel controls (`OBJ_BUTTON`);
- room-native generated doors with project-authored bounds (`OBJ_DOOR`);
- code-drawn movable storage (`OBJ_ITEM`);
- baked navigable openings (`OBJ_PORTAL`);
- generated dynamic game media (`OBJ_GAME_MEDIA`); and
- physical consoles/books/instruments already painted into a room plate
  (`OBJ_APPLIANCE`).

Conventional controls keep hit rectangles of at least 32×32. Physical objects
keep their exact declared bounds. Study props further consult their semantic
ID map, game media consults generated alpha, and Storeroom items consult their
rendered silhouettes. Room-native doors and baked appliances use object-sized
rectangles aligned with the depicted architecture or object in the plate.

One left-button down owns a gesture. Only a matching release inside the same
target and viewport activates it. Leaving the viewport, changing rooms,
receiving a second down, or releasing another button cancels ownership.
Storeroom items follow the pointer while held and accept only the two shelf
containers.

Door transitions block room input, darken only the content zone, switch scene
at the midpoint, and clear pressed state. Hover identity uses the same object
resolver as clicks. Identification appears in the name bar; no physical object
receives hover artwork.

## 4. Scenes and direct dispatch

The eight scenes are Study, Grand Gallery, Storeroom, Server Room, Game Room,
Library, Cleaning Room, and Balcony.

Study props carry `LaunchAppId` values. Server/Cleaning/Library/Balcony
appliances carry `LaunchToolId` values. Game media carries validated catalog
indices. Activation queues one take-and-clear request:

~~~text
scene_take_launch_request
scene_take_tool_request
scene_take_game_request
~~~

The scene never starts a process. The main loop consumes each request and
hands it to the launcher. Success/failure returns through
`scene_set_status`, which temporarily replaces the room/hover string in the
name bar. This boundary is why a physical launcher never needs to open a
modal status list.

Web is a staged variant of that boundary. Main first asks the launcher to
create a background browser tab and capture its numeric window ID. Only then
does `scene_begin_web_boot` lock scene input and begin the minimum 2.8-second
monitor boot. The boot waits at `WAITING FRAME`; the launcher's private Kilix
run log must record a supported capture-readiness marker before main calls
`scene_mark_web_ready`. The launcher gives that marker 0.75 seconds to settle.
A 30-second no-readiness timeout aborts the handoff and returns control to the
Study. A valid signal starts the 0.8-second zoom. The final frame queues one
`scene_take_web_focus_request`; main presents that frame before asking the
launcher to focus the captured window. The scene never sees the URL, password,
readiness path, or window ID, and the launcher never draws.

The house map dispatches direct room transitions. Lamp is the only local map
toggle.

Game Room accepts at most thirty unique entries. A validated catalog
replacement atomically rebuilds the room as one exit plus one physical object
per title, preventing stale picks after contraction. Each object receives the
exact 16×16 palette icon exported from Kilix 95 and no text plaque.

## 5. Launcher boundary

Desktop plans are fixed executable/argument arrays passed directly to
`posix_spawn`. No shell interprets values. Child working directories are
validated absolute directories. Desktop association probes have fixed
arguments, bounded capture, and a roughly one-second timeout.

The Computer's Web plan uses authenticated `kitten @ launch` with
`--keep-focus`, a fixed `KILIX_IN_OVERLAY=1`, and a private `KILIX_RUN_LOG`.
Firefox stays on Kilix's event-driven XDamage/MIT-SHM path. That shared capture
path acknowledges damage by atomically moving the accumulated server region
into an XFixes region before reading pixels, so a browser repaint cannot land
between an old notification and a destructive clear. The Kilix event loop also
checks python-xlib's in-process queue before `select()`, covering notifications
consumed while a synchronous X reply drains the kernel socket.
The checkout-local Python helper gives `firefox-esr` a fresh temporary profile
and passes the validated `web_home` through `--new-window`. The launch response
must be one bounded nonzero decimal window ID. The private log must contain an
exact complete `content-ready=changed` or `content-ready=initial-grace` line
before the post-animation focus plan matches only that ID. The legacy
`content-frames=1` marker, including the strictly parsed timestamped record from
older Kilix versions, remains accepted for changed-frame readiness. The grace
reason is a capture-handoff heuristic rather than a page-load assertion.
`web_home` defaults to Hacker News and accepts only an `http(s)` URL from the
private local config.

Monitor and Housekeeping plans use Kilix's authenticated control interface:

~~~text
kitten @ --password-file PASSWORD launch --type=tab \
  --cwd PROJECT --self --tab-title TITLE -- \
  python3 PROJECT/tools/mansion_tui.py MODE [FOCUS]
~~~

The launcher derives `PROJECT` and the helper from `/proc/self/exe`, requires
the helper to be a regular readable file, and supplies all mode/focus values
from enums. Game plans use the same authenticated tab boundary with the
Kilix 95 helper and one validated game ID.

`KILIX_CAP_EXTERNAL_APPS=0` disables all process launches. It does not disable
navigation, hover, lamp, or Storeroom interaction. Kilix Cap has no runtime
network client; separately launched apps/games may have their own network and
persistence behavior.

Full mappings and vectors are in [APPS.md](APPS.md).

## 6. System TUI boundary

`tools/mansion_tui.py logs` and `activity` are read-only snapshots refreshed
every two seconds. They use fixed `journalctl`, `mail`, `ss`, or `netstat`
vectors and bounded output, with `/proc` and local-file fallbacks.

`cleanup` computes previews for five fixed targets. User-space deletion is
confined to old user-owned top-level `/tmp` entries, thumbnail-cache children,
or user Trash. Symlinks are not followed. APT and journal cleanup are fixed
`pkexec` vectors. Every change requires an in-TUI `y` confirmation.

## 7. Audio

The bank contains twelve mono 44.1 kHz signed 16-bit PCM WAV cues. Loading and
offline mixing remain strict. Missing audio, muting, or an unavailable sink
never changes interaction state. The 3.0 direct flow uses touch, error, door,
switch, contain, and magic; legacy bank entries remain validated assets.

## 8. Render and test gates

A release fixture is one P6 480×320 image with maxval 255, exactly 460,800
raster bytes, at least sixteen RGB colors, and at least 5,000 chromatic
pixels. The 3.0 hash-pinned set is:

~~~text
base-desk.ppm
base-hallway.ppm
base-storeroom.ppm
base-server-room.ppm
base-game-room.ppm
base-library.ppm
base-cleaning-room.ppm
base-balcony.ppm
state-desk-hover.ppm
state-desk-web-boot.ppm
state-desk-web-zoom.ppm
state-server-hover.ppm
state-cleaning-hover.ppm
state-game-hover.ppm
state-store-moved.ppm
~~~

Hashes live in [render-fixtures.json](render-fixtures.json).
`--render-review` additionally renders thirty legacy internal panel states for
regression coverage, although those panels are no longer reachable from the
3.0 mansion objects.

`make test-code` covers input ordering, exact object targets, transitions,
all eight room routes, direct app/tool dispatch, live catalog reflow,
authenticated game/monitor plan shapes, helper preview self-tests, launcher
configuration safety, font coverage, direct audio triggers, and three golden
behavioral digests.

`make test` adds standalone-header compilation, forbidden-input scanning,
strict audio validation/mixing, the exact visual inventory, opaque full-color
scene rendering, and golden render hashes. `make sanitize` repeats the suite
under ASan and non-recovering UBSan with warnings promoted to errors.

~~~sh
make test

render_dir=$(mktemp -d)
./bin/kilix-cap --render-test "$render_dir"
python3 tools/check_render.py "$render_dir"

panel_dir=$(mktemp -d)
./bin/kilix-cap --render-review "$panel_dir"
python3 tools/check_render.py "$panel_dir" --expected-count 30
~~~
