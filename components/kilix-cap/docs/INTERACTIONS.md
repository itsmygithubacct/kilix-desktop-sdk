# Interaction guide

This is the user-visible interaction surface for kilix-cap 3.0.0.

Physical objects have no surrounding button, title plaque, hover highlight,
or rectangular artwork. Pointing at one shows its name and action in the top
name bar. Selecting an app, book, console, monitor, instrument, or game
dispatches its real application immediately; it does not open an intermediate
text list or built-in status panel.

## Mansion flow

| Room | Physical behavior |
|---|---|
| Study | Thirteen separated desk props launch Clock, Inbox, Outbox, Mail, Profile, Notepad, Dates, Contacts, Files, Phone, Writer, Calculator, and Web. The right door enters the Grand Gallery. |
| Grand Gallery | Three diminishing side-door pairs, each fitted to its own position and vanishing lines, lead to Study, Library, Server Room, Cleaning Room, Game Room, and Storeroom. The glazed door at the end leads to the Balcony. |
| Storeroom | Storage box, wooden crate, and tin canister can be dragged between the two shelves. The left door returns to the Gallery. |
| Server Room | Two monitor screens launch live system TUIs. Four separate equipment zones open system settings, storage, network, and software administration apps. |
| Game Room | Every live Kilix 95 catalog entry appears as a clickable physical CD, floppy, or manual and launches directly in a new Kilix tab. |
| Library | Five large books open README, room/interaction guidance, app mappings, and engine documentation in the system viewer. |
| Cleaning Room | Basin, copper bin, cache drawers, and maintenance terminal launch Housekeeping focused on temp, Trash, cache, or all tasks. |
| Balcony | The glazed door returns inside. The weather cabinet and telescope open installed Weather and astronomy apps. |

Door transitions darken the content area briefly, change rooms, and restore
the scene. The Grand Gallery provides the intended spatial route; the bottom
house map offers direct Study, Gallery, Store, Server, Games, and Clean
shortcuts. Lamp is a direct persistent toggle.

## Study props

| Prop | Direct mapping |
|---|---|
| Clock | Installed clocks app, then `https://time.is` through the system opener. |
| In box / Out box | Installed mail client, then `xdg-email`. |
| New-message postcard | Saved mail target when present; otherwise installed mail client or `xdg-email`. |
| Own name card / Name card file | Installed contacts app or fixed file/mail fallback. |
| Notepad | Default/lightweight text editor with `~/Documents` as its child working directory. |
| Datebook | Installed calendar app, then the fixed calendar web URL. |
| File cabinet | Installed file manager at Kilix Cap's startup directory. |
| Telephone | Installed native phone app or a registered `tel:` handler. |
| Stationery | Installed word processor. |
| Desk accessories | Installed calculator. |
| Computer | Starts Firefox ESR on Hacker News in a background Kilix tab, animates the monitor boot sequence, zooms into the screen, then focuses that exact tab. |

Only visible prop pixels are selectable. The Study's separate semantic hit map
distinguishes all thirteen objects from the empty pixels between them.
Unavailable and disabled launches leave the room unchanged and report a short
reason in the name bar.

### Computer boot and Web home

The Computer creates the browser tab with Kilix `--keep-focus`, so startup
work happens behind the Study. A monitor-scale 3x5 phosphor font shows ROM,
memory, video, network, DNS, X11, and Firefox startup without oversized UI
lettering. The sequence remains on `WAITING FRAME` until Kilix's app streamer
reports capture readiness from either a changed capture or the three-second
initial-frame grace path. Kilix Cap waits another 0.75 seconds for settling,
then uses a 0.8-second smooth pixel-preserving zoom from the complete room into
the physical screen. Only after that final frame is presented does Kilix Cap
focus the numeric window ID returned by the original launch.

Firefox ESR receives `https://news.ycombinator.com/` through an explicit
`--new-window` argument by default. Each streamed instance gets a private
temporary profile so another Firefox process cannot absorb the URL or move the
window onto a different display. A private local override may be placed in
`~/.local/gpu_terminal/kilix-cap/config`:

~~~text
web_home=https://example.org/
~~~

The value must be one bounded `http(s)` URL with no whitespace. Invalid,
relative, and non-Web schemes are ignored in favor of Hacker News.

## Server Room monitors

The left monitor opens:

- recent system log entries;
- warning-or-higher system alerts; and
- the current user's local system mail.

The right monitor opens:

- active processes owned by the current user, sorted by resident memory; and
- active TCP/UDP connections from `ss`, with a `netstat` fallback.

Both are read-only green-on-black curses TUIs. They refresh every two seconds;
`r` refreshes immediately and `q` or Escape closes the tab. They launch
through Kilix's authenticated `kitten @ launch --type=tab` boundary with a
fixed `python3 tools/mansion_tui.py` argument vector.

The settings console, storage rack, network patch panel, and software cabinet
select the first installed candidate from a fixed allowlist. They are direct
desktop app launches, not menus maintained by Kilix Cap.

## Cleaning Room

Every cleaning station opens the same bounded Housekeeping console with a
different focus. Housekeeping scans and previews:

1. user-owned top-level `/tmp` entries older than seven days;
2. the current user's thumbnail cache;
3. `/var/cache/apt/archives`;
4. the system journal's reported disk use; and
5. the current user's desktop Trash.

Number keys select an action. Nothing changes until `y` confirms the selected
fixed operation. `n`, `q`, or Escape cancels.

User-space removal is restricted to the displayed fixed locations. Symlinks
are never followed. APT cache and journal vacuum operations execute only as
the fixed vectors `pkexec apt-get clean` and
`pkexec journalctl --vacuum-time=14d`; the desktop controls authorization.
Entering the room, hovering a station, opening the TUI, refreshing, or running
its self-test performs no cleanup.

## Game Room

Discovery imports Kilix 95's current registry under temporary storage and does
not modify real Kilix 95 state. The room polls once per second and atomically
rebuilds the dynamic media layer when the catalog changes. Up to thirty
non-overlapping placements are available across the rear shelf, side rack,
and foreground desk.

Each object shows the original project-owned 16×16 Kilix 95 icon and no title
plaque. Hover shows the exact title in the name bar. Click launches its fixed,
validated ID in a fresh authenticated Kilix tab. An unavailable or empty
catalog leaves a readable room state without stale hit targets.

## Pointer and keyboard behavior

- Left-button down owns one object gesture. Release over the same object
  activates it.
- Moving an immovable pressed object outside its shape cancels activation and
  produces error feedback.
- Storeroom items follow the pointer while held. A drop on either shelf moves
  the item there; any other drop snaps it back.
- A second button-down, leaving the canvas, changing rooms, or a mismatched
  release cancels the old gesture safely.
- `q` and Escape exit when no legacy modal surface is active.

The name bar normally shows the room, changes to object help on hover, and
temporarily shows green success or coral failure after a direct launch.

## State and boundaries

Lamp state, Storeroom placement, and the live game catalog remain in memory
for the process. Mail's optional registered target and the optional Web home
are the two private Kilix Cap configuration values. State owned by launched
programs is outside this contract.

Kilix Cap makes no network request. Clicking Web, a configured webmail URL, a
fallback web mapping, or a Kilix 95 game crosses into another program that may
use the network or persist data. Set `KILIX_CAP_EXTERNAL_APPS=0` to disable
all external app/tool launches while retaining room navigation and object
inspection.

## Audio

Audio is optional feedback and never decides whether an action succeeds:

| Cue | Current trigger |
|---|---|
| touch | Accepted pointer-down on a physical object or map control. |
| error | Invalid drag gesture or failed direct launch. |
| door | Room transition begins. |
| switch | Lamp changes state. |
| contain | Storeroom item changes shelf. |
| magic | External app, TUI, document, or game launch succeeds. |

The complete twelve-cue bank remains format- and mix-tested for compatibility;
legacy cues are retained in the asset bank even when the 3.0 mansion flow no
longer exposes their former panel action.
