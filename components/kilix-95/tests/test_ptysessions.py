"""PTY Sessions window: list, details, observe/attach/preview, end, journals.

Drives the real window with synthetic input against a fake `kilix pty`
executable (tests/pty_fake.py). Launching a Kilix tab is stubbed at the shell
boundary, as the README's test style asks; nothing touches a live broker.
"""
import os
import sys
import time
import unicodedata

import harness as H
import pty_fake as F
import icons
import theme as T
import widgets as W
import wm
from accessibility import Tree
from apps import ptysessions as P
import apps

os.environ.pop("KITTY_PTY_BROKER_SESSION", None)
fake = F.FakeKilix(F.standard_responses())
P.kilix_launcher = lambda: fake.path
DET, ATT, UNR = F.DETACHED["id"], F.ATTACHED["id"], F.UNREACHABLE["id"]

d = H.make_desk()
launches = []
d.shell._spawn_kitty_launch = lambda opts, cmd, title, cwd=None, \
    pause_on_error=True: launches.append((opts, cmd, title)) or True

dialogs = []
_real_msgbox = wm.msgbox


def recording_msgbox(desk, title, text, **kw):
    dialogs.append((title, text, kw))
    return _real_msgbox(desk, title, text, **kw)


wm.msgbox = recording_msgbox


def settle(win, limit=8.0):
    end = time.time() + limit
    while win.futures and time.time() < end:
        win._tick(time.time())
        time.sleep(0.02)
    assert not win.futures, f"jobs never finished: {list(win.futures)}"


def modal():
    top = [w for w in d.wm.windows if w.modal]
    return top[-1] if top else None


def button(win, text):
    found = [w for w in win.widgets if isinstance(w, W.Button)
             and w.text == text and w.visible]
    assert len(found) == 1, (text, [w.text for w in win.widgets
                                    if isinstance(w, W.Button)])
    return found[0]


def press(win, text):
    """A real left click at the middle of a button of `win`."""
    b = button(win, text)
    ox, oy = win.client_origin()
    H.click(d, ox + b.x + b.w // 2, oy + b.y + b.h // 2)


def select(win, index):
    win.set_focus(win.list)
    win.list.sel = index
    win._select_session(win.list.items[index])


def kill_calls():
    return [c for c in fake.calls() if c[:2] == ["pty", "kill"]]


# ── opening: Start menu, Control Panel, singleton ───────────────────────────
d.taskbar.open_start_menu()
top = d.menus.stack[0].items
programs = [i for i in top if i.label == "Programs"][0].submenu
accessories = [i for i in programs if i.label == "Accessories"][0].submenu
entry = [i for i in accessories if i.label == "PTY Sessions"]
assert len(entry) == 1, [i.label for i in accessories]
assert entry[0].icon == "ptysessions" and callable(entry[0].action)
labels = [i.label for i in accessories if i.label != "-"]
assert labels.index("Paint") < labels.index("PTY Sessions") < labels.index(
    "Task Manager"), labels
# the broker's TUI entry in Programs is "PTY Sessions (Terminal)"; the plain
# name belongs to this app alone
assert [i.label for i in programs].count("PTY Sessions (Terminal)") == 1
assert "PTY Sessions" not in [i.label for i in programs]
assert "PTY Session Manager" not in labels
d.menus.close_all()
from apps import controlpanel
assert ("PTY Sessions", "ptysessions", "ptysessions", None) \
    in controlpanel.CONTROL_ITEMS
for size in (16, 32):
    image = icons.get("ptysessions", size)
    assert image.size == (size, size)
    assert any(px[3] for px in image.getdata()), "the icon draws nothing"
assert icons.get("ptysessions", 16).tobytes() != icons.get("taskmgr", 16).tobytes()

entry[0].action()
win = H.find_window(d, "PtySessions")
assert win is not None
apps.open(d, "ptysessions")
assert len([w for w in d.wm.windows if isinstance(w, P.PtySessions)]) == 1
assert win.icon == "ptysessions" and win._tick in d.tick_hooks
settle(win)

# ── the list: every session, unreachable ones distinct, none absent ─────────
assert [item[2]["session"]["id"] for item in win.list.items] == [ATT, DET, UNR]
rows = {item[2]["session"]["id"]: item for item in win.list.items}
assert rows[ATT][2]["state"] == "attached"
assert rows[DET][2]["state"] == "detached"
assert rows[UNR][2]["state"] == "unreachable"
assert rows[UNR][0] == "warn" and rows[DET][0] == "ptysessions"
assert "UNREACHABLE" in rows[UNR][1] and "detached" in rows[DET][1]
assert rows[DET][2]["cells"][:4] == (DET, "detached", rows[DET][2]["cells"][2],
                                     "80x24")
assert rows[DET][2]["cells"][5] == "/srv/work/build"      # cwd_now, not cwd
assert rows[ATT][2]["cells"][5] == ""                      # cwd_now is null
assert win.session_status.startswith("3 sessions: 1 attached, 1 detached, "
                                     "1 unreachable"), win.session_status
assert fake.calls()[0] == ["pty", "list", "--json"]
assert all(call[0] == "pty" for call in fake.calls())

# the accessible tree names each row with its state in words
tree = Tree(d)
tree.build()
names = [n["name"] for n in tree.nodes.values() if n["role"] == "list item"]
assert any(UNR in n and "UNREACHABLE" in n for n in names), names
assert any(DET in n and "detached" in n for n in names), names

# ── details: status fields and the runtime path ─────────────────────────────
select(win, 1)
text = win.details.source
for needle in (DET, "detached", "80 columns x 24 rows",
               'sh -c echo "build ok"; sleep 300', "/srv/work",
               "/srv/work/build", "1574870", "1574871", F.RUNTIME,
               F.DETACHED["boot_id"], "11186224", "28 B"):
    assert needle in text, (needle, text)
assert "Started in: /srv/work\n" in text and "Now in: /srv/work/build" in text
select(win, 0)
assert "(not available)" in win.details.source          # cwd_now null
select(win, 2)
text = win.details.source
assert "unreachable" in text and "did not answer" in text and "timeout" in text
assert F.RUNTIME in text

# ── buttons follow the selection ────────────────────────────────────────────
def enabled(win):
    return {b.text: b.enabled for b in win.widgets
            if isinstance(b, W.Button) and b.visible}


select(win, 1)                                   # detached
assert enabled(win) == {"Refresh": True, "Observe": True, "Preview": True,
                        "Attach": True, "End Session…": True,
                        "Open in Terminal": True}, enabled(win)
select(win, 0)                                   # attached: not attachable
assert enabled(win)["Attach"] is False and enabled(win)["Observe"] is True
assert enabled(win)["End Session…"] is True
select(win, 2)                                   # unreachable: nothing works
assert enabled(win) == {"Refresh": True, "Observe": False, "Preview": False,
                        "Attach": False, "End Session…": False,
                        "Open in Terminal": True}, enabled(win)
win.list.sel = -1
win._sync_buttons()
assert not any(v for k, v in enabled(win).items()
               if k not in ("Refresh", "Open in Terminal"))

# ── observe / attach open a Kilix tab running the exact kilix pty command ──
del launches[:]
select(win, 1)
press(win, "Observe")
assert launches == [(["--type=tab"], f"{fake.path} pty observe {DET}",
                     f"Observe: {DET}")], launches
del launches[:]
press(win, "Attach")
assert launches == [(["--type=tab"], f"{fake.path} pty attach {DET}",
                     f"Attach: {DET}")], launches
del launches[:]
select(win, 0)                                   # attached: refused, twice
press(win, "Attach")
win._attach()
select(win, 2)                                   # unreachable: refused
win._observe()
win._attach()
win._preview()
assert launches == [], launches
select(win, 1)
win.list.on_activate(win.list.items[1])          # Enter / double-click observes
assert launches[-1][1].endswith(f"pty observe {DET}"), launches

# Open in Terminal is the same manager as Start > Programs > PTY Sessions
# (Terminal): it calls shell.open_pty_manager and nothing else
terminal = []
d.shell.open_pty_manager = lambda: terminal.append("tui") or True
del launches[:]
select(win, 2)                                   # works with nothing usable
press(win, "Open in Terminal")
assert terminal == ["tui"] and launches == [], (terminal, launches)
select(win, 1)

# a launcher path with spaces is quoted for the tab's shell
P.kilix_launcher = lambda: "/srv/my kilix/kilix"
win._observe()
assert launches[-1][1] == f"'/srv/my kilix/kilix' pty observe {DET}"
P.kilix_launcher = lambda: fake.path

# ── preview: a bounded snapshot, labelled as pane output ───────────────────
fake.clear()
press(win, "Preview")
settle(win)
view = H.find_window(d, "OutputWindow")
assert view is not None and view.title == f"Pane output: {DET}"
assert "Pane output of session " + DET in view.banner
assert "untrusted" in view.banner and "read-only" in view.banner
assert "build ok\ntests: 42 passed" in view.view.text()
assert fake.calls() == [["pty", "observe", DET, "--once", "--lines", "200",
                         "--text", "--json"]], fake.calls()
before = view.view.text()
H.key(d, "x")
H.key(d, "Delete")
assert view.view.text() == before, "the snapshot view is editable"
view.close()

# a snapshot that fails says so and opens no window
fake.set([F.response(["pty", "observe"], None, 1, "kilix pty: broker timed out\n")])
del dialogs[:]
win._preview()
settle(win)
assert H.find_window(d, "OutputWindow") is None
assert dialogs[-1][0] == "Preview" and "broker timed out" in dialogs[-1][1]
modal().close()
fake.set(F.standard_responses())

# ── End Session: confirmation shows the complete ID and command ────────────
def confirmation():
    return H.find_window(d, "ConfirmEnd")


select(win, 1)
fake.clear()
del dialogs[:]
press(win, "End Session…")
dlg = confirmation()
assert dlg is not None and dlg.modal and dlg is modal() and dialogs == []
assert dlg.sid == DET and dlg.command == 'sh -c echo "build ok"; sleep 300'
assert DET in dlg.view.source and dlg.command in dlg.view.source
assert [b.text for b in dlg.widgets if isinstance(b, W.Button)] == [
    "End Session", "Cancel"]
assert dlg.b_cancel.default and not dlg.b_end.default      # Cancel is default
assert dlg.focus is dlg.b_cancel
labels = " ".join(w.text for w in dlg.widgets if isinstance(w, W.Label))
assert "The program running in it will be terminated" in labels, labels
press(dlg, "Cancel")                              # declining ends nothing
settle(win)
assert modal() is None and kill_calls() == [], fake.calls()
for key in ("Enter", "Escape", " "):              # default-key paths: no kill
    win._end()
    H.key(d, key)
    settle(win)
    assert modal() is None and kill_calls() == [], (key, fake.calls())

# the whole ID and the whole command are shown, wrapped, nothing cut
long_id = "W" * 64
long_cmd = "run-" + "x" * 600 + " --target alpha"
sessions = [F.doc(F.DETACHED, id=long_id, command=long_cmd)]
fake.set([F.response(["pty", "list"], F.doc(F.LIST, sessions=sessions,
                                            unreachable=[]))])
win.refresh()
settle(win)
select(win, 0)
win._end()
dlg = confirmation()
shown = "".join(dlg.view.lines)
assert long_id in shown and long_cmd in shown, dlg.view.lines
assert all(T.text_w(dlg.view.font, line) <= dlg.view.w - T.SCROLL_W - 8
           for line in dlg.view.lines), "a row runs past the dialog"
assert len(dlg.view.lines) > 8, "a long command was not wrapped"
first = list(dlg.view.lines)
dlg.close()
# two commands that differ only at the very end show different confirmations
variants = []
for suffix in ("alpha", "bravo"):
    cmd = "runner " + "a" * 240 + f" --target {suffix}"
    fake.set([F.response(["pty", "list"], F.doc(F.LIST, sessions=[
        F.doc(F.DETACHED, command=cmd)], unreachable=[]))])
    win.refresh()
    settle(win)
    select(win, 0)
    win._end()
    variants.append(list(confirmation().view.lines))
    confirmation().close()
assert variants[0] != variants[1]
assert "".join(variants[0]).endswith("--target alpha")
assert "".join(variants[1]).endswith("--target bravo")
fake.set(F.standard_responses())
win.refresh()
settle(win)

# confirming sends exactly the bound kill, shows the receipt, then re-lists
select(win, 1)
fake.clear()
del dialogs[:]
press(win, "End Session…")
press(modal(), "End Session")
assert "kill" in win.futures and not win.b_end.enabled   # no double submits
settle(win)
assert kill_calls() == [["pty", "kill", DET, "--yes", "--expect-started",
                         str(F.DETACHED["started_millis"]), "--json"]]
title, text, kw = dialogs[-1]
assert title == "End Session" and kw["icon"] == "info"
assert "verified_absent" in text and DET in text and "has ended" in text
assert fake.calls()[-1] == ["pty", "list", "--json"], fake.calls()   # re-listed
settle(win)
modal().close()

# every other result is shown for what it is, never as an ending
for doc, token, forbidden in (
        (F.UNCERTAIN, "still_listed", "has ended"),
        (F.UNCERTAIN_UNSENT, "status_failed", "has ended"),
        (F.REFUSED_MISMATCH, "started_mismatch", "has ended"),
        (F.REFUSED_CANNOT_BIND, "cannot_bind", "has ended"),
        (F.REFUSED_CALLER_UNIDENTIFIED, "caller_unidentified", "has ended"),
        (F.NOT_FOUND_RECEIPT, "not_found", "has ended")):
    fake.set([F.kill_response(doc)] + F.standard_responses())
    select(win, 1)
    del dialogs[:]
    win._end()
    press(modal(), "End Session")
    settle(win)
    title, text, kw = dialogs[-1]
    assert token in text and forbidden not in text, (token, text)
    assert kw["icon"] == "warn", (token, kw)
    if token == "status_failed":
        assert "Nothing was sent" in text and "WAS sent" not in text, text
    if token == "cannot_bind":
        assert "older build" in text, text
        assert f"kilix pty kill {DET}" in text, text
        assert "Nothing was ended" in text, text
    if token == "caller_unidentified":
        assert "which pane" in text and "Nothing was ended" in text, text
    if token == "still_listed":
        assert "WAS sent" in text and "Nothing was sent" not in text, text
    settle(win)
    if modal():
        modal().close()

# no valid receipt: the window says it does not know
fake.set([F.response(["pty", "kill"], None, 2, "kilix pty: kill needs --yes\n")]
         + F.standard_responses())
select(win, 1)
win._confirmed_end(DET, F.DETACHED["started_millis"])
settle(win)
title, text, kw = dialogs[-1]
assert kw["icon"] == "error" and "No receipt" in text
assert "may or may not have ended" in text and "has ended" not in text
modal().close()
fake.set(F.standard_responses())

# a stale selection cannot kill another incarnation: the receipt says so
fake.set([F.kill_response(F.REFUSED_MISMATCH)] + F.standard_responses())
win._confirmed_end(DET, F.DETACHED["started_millis"] + 99)
settle(win)
mismatch = [c for c in fake.calls() if c[:2] == ["pty", "kill"]][-1]
assert mismatch[mismatch.index("--expect-started") + 1] == \
    str(F.DETACHED["started_millis"] + 99)
modal().close()
fake.set(F.standard_responses())
win.refresh()
settle(win)

# ── never offered for the session the desktop itself runs in ───────────────
os.environ["KITTY_PTY_BROKER_SESSION"] = DET
select(win, 1)
assert win.b_end.enabled is False, "End Session offered for the own session"
win._sync_buttons()
assert enabled(win)["End Session…"] is False
assert enabled(win)["Observe"] is True
win._select_session(win.list.items[1])
assert "this desktop runs in" in win.details.source
fake.clear()
del dialogs[:]
press(win, "End Session…")                        # a click on a dead button
assert dialogs == [] and kill_calls() == []
win._end()                                        # the keyboard/API path
assert dialogs[-1][0] == "End Session" and "Cannot end" in dialogs[-1][1]
assert "this desktop is running in this session" in dialogs[-1][1].lower()
modal().close()
win._confirmed_end(DET, F.DETACHED["started_millis"])   # even past the dialog
settle(win)
assert kill_calls() == [], ("the own session reached kilix", fake.calls())
title, text, kw = dialogs[-1]
assert "own_session" in text and "Nothing was ended" in text
modal().close()
select(win, 0)                                    # others are still endable
assert win.b_end.enabled is True
del os.environ["KITTY_PTY_BROKER_SESSION"]
win._sync_buttons()

# ── refresh: selection and scroll survive; failure never hides sessions ────
select(win, 1)
win._tick(win.last_refresh + P.REFRESH_SECONDS - 1)
assert "list" not in win.futures, "refreshed too early"
fake.clear()
win._tick(win.last_refresh + P.REFRESH_SECONDS + 1)
settle(win)
assert fake.calls() == [["pty", "list", "--json"]]
assert win._selected_row()["session"]["id"] == DET
reordered = F.doc(F.LIST, sessions=[F.ATTACHED, F.DETACHED, F.doc(
    F.DETACHED, id="bbbbbbbbbbbbbbbb", started_millis=1791337600000)])
fake.set([F.response(["pty", "list"], reordered)])
win.refresh()
settle(win)
assert win._selected_row()["session"]["id"] == DET
assert [i[2]["session"]["id"] for i in win.list.items] == [
    "bbbbbbbbbbbbbbbb", ATT, DET, UNR]

fake.set([F.response(["pty", "list"], None, 1, "kilix pty: runtime is gone\n")])
win.refresh()
settle(win)
assert len(win.list.items) == 4, "a failed refresh emptied the list"
assert "Could not list sessions: kilix pty: runtime is gone" in win.session_status
assert "Showing the list from" in win.session_status
# an empty runtime is a statement, not an error
fake.set([F.response(["pty", "list"], F.doc(F.LIST, sessions=[], unreachable=[]))])
win.refresh()
settle(win)
assert win.list.items == [] and win.session_status.startswith("0 sessions")
assert "No persistent sessions" in win.details.source
assert not any(v for k, v in enabled(win).items()
               if k not in ("Refresh", "Open in Terminal"))
# F5 refreshes
fake.set(F.standard_responses())
fake.clear()
H.key(d, "F5")
settle(win)
assert fake.calls() == [["pty", "list", "--json"]] and len(win.list.items) == 3

# ── archived journals ───────────────────────────────────────────────────────
win._switch(1)
settle(win)
press(win, "Open in Terminal")                   # also on the journals page
assert terminal == ["tui", "tui"], terminal
assert win.tabs.active == 1 and win.jlist.visible and not win.list.visible
assert [i[2]["journal"]["id"] for i in win.jlist.items] == ["90d1e57a2c4b8f36"]
assert win.journal_status == "1 archived journal"
assert enabled(win) == {"Refresh": True, "View Journal…": False,
                        "Open in Terminal": True}, enabled(win)
win.set_focus(win.jlist)
H.key(d, "ArrowDown")
assert win._selected_journal() is not None and win.b_jview.enabled
text = win.jdetails.source
assert "/srv/kilix/state/pty-journals/90d1e57a2c4b8f36.1791337517964" in text
assert "8 B" in text and "21 B" in text and F.RUNTIME in text
fake.clear()
press(win, "View Journal…")
settle(win)
view = H.find_window(d, "OutputWindow")
assert view.title == "Archived journal: 90d1e57a2c4b8f36"
assert "untrusted" in view.banner and "old out" in view.view.text()
assert fake.calls() == [["pty", "journals", "show",
                         "90d1e57a2c4b8f36.1791337517964", "--text", "--json",
                         "--lines", "200"]]
view.close()
fake.set([F.response(["pty", "journals", "list"], F.doc(F.JOURNALS, journals=[]))])
win.refresh_journals()
settle(win)
assert win.journal_status == "No archived journals." and win.jlist.items == []
assert "No archived journals" in win.jdetails.source
fake.set([F.response(["pty", "journals", "list"], None, 1,
                     "kilix pty: journals unavailable\n")])
win.refresh_journals()
settle(win)
assert "Could not list journals: kilix pty: journals unavailable" \
    in win.journal_status
win._switch(0)
assert win.list.visible and not win.jlist.visible

# ── rendering, resizing, closing ────────────────────────────────────────────
fake.set([F.response(["pty", "list"], F.doc(
    F.LIST, unreachable=[F.RECORDED_UNREACHABLE]))])
win.refresh()
settle(win)
select(win, 2)
recorded_row = win.list.items[2]
assert "recorded at start: python3 -c" in recorded_row[2]["cells"][4]
assert "recorded at start: python3 -c" in win.details.source
assert "build ok" in win.details.source
tree.build()
names = [n["name"] for n in tree.nodes.values() if n["role"] == "list item"]
assert any(UNR in n and "recorded at start: python3 -c" in n and
           "build ok" in n for n in names), names
assert enabled(win) == {"Refresh": True, "Observe": False, "Preview": False,
                        "Attach": False, "End Session…": False,
                        "Open in Terminal": True}, enabled(win)
d.render()

# Recorded format characters are neutralised or visibly escaped through the
# real window, its details widget and the accessibility tree after a refresh.
format_controls = "".join(chr(n) for n in range(sys.maxunicode + 1)
                          if unicodedata.category(chr(n)) == "Cf")
hostile = F.doc(F.RECORDED_UNREACHABLE)
hostile["recorded"]["argv"][-1] += format_controls + "\x00\x08\t\n\r\x1b\x7f\x85café"
fake.set([F.response(["pty", "list"], F.doc(F.LIST, unreachable=[hostile]))])
win.refresh()
settle(win)
select(win, 2)
recorded_row = win.list.items[2]
assert recorded_row[2]["session"] == hostile, "recorded facts were changed"
tree.build()
names = [n["name"] for n in tree.nodes.values() if n["role"] == "list item"]
assert recorded_row[1] in names, names
for text in (recorded_row[2]["cells"][4], recorded_row[1], win.details.source):
    assert "recorded at start: python3 -c" in text and "build ok" in text
    assert "café" in text
    assert all(unicodedata.category(c) not in ("Cc", "Cf")
               for c in text if c != "\n"), repr(text)
assert "\n" not in recorded_row[1] + recorded_row[2]["cells"][4]
assert enabled(win) == {"Refresh": True, "Observe": False, "Preview": False,
                        "Attach": False, "End Session…": False,
                        "Open in Terminal": True}, enabled(win)
fake.clear()
launches_before = list(launches)
win._observe(); win._preview(); win._attach(); win._end()
assert not fake.calls() and launches == launches_before and not win.futures
d.render()

fake.set(F.standard_responses())
win.refresh()
settle(win)
for page in (0, 1, 0):
    win._switch(page)
    d.dirty = True
    d.render()
win.w, win.h = 600, 420
win.on_resize()
d.dirty = True
d.render()
win.w, win.h = 1000, 640
win.on_resize()
d.dirty = True
d.render()
assert win.list.w == win.client_size()[0] - 16
# the other desktop flavor renders it too (colors come from the theme)
T.apply_flavor("xp")
try:
    for page in (0, 1, 0):
        win._switch(page)
        d.dirty = True
        d.render()
finally:
    T.apply_flavor("95")

# a window closed while a kill is in flight is held open and says why
fake.set([F.kill_response(F.VERIFIED, sleep=1)]
         + F.standard_responses())
select(win, 1)
win._confirmed_end(DET, F.DETACHED["started_millis"])
del dialogs[:]
win.request_close()
assert dialogs and "still running" in dialogs[-1][1] and win in d.wm.windows
modal().close()
settle(win)
modal().close()

tick = win._tick
win.close()
assert tick not in d.tick_hooks and win not in d.wm.windows
print("ok")
