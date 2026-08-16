"""Super (Win) key: a bare tap toggles the Start menu.

The kitty keyboard protocol reports Super_L/Super_R (X11 keycode 133/134) as
functional codes 57444/57450 with press AND release edges (>15u). A tap —
press then release with nothing in between — toggles the Start menu; any
other key or click while Super is held disarms it, so Super+<key> combos are
never stolen.
"""
import os

import harness as H
import apps
import main as desk_main
import widgets as W
import wm


def _super_down(d):
    d.dispatch_key(W.Ev(kind="key", key="Super", press=True))


def _super_up(d):
    d.dispatch_key(W.Ev(kind="key", key="Super", press=False))


# ── _norm_key: L/R Super surface both edges, other bare mods stay dropped ────
def test_norm_key_super_edges():
    d = H.make_desk()
    for code in (57444, 57450):            # Super_L, Super_R
        down = d._norm_key({"key": chr(code), "mods": 9, "evt": 1})
        up = d._norm_key({"key": chr(code), "mods": 1, "evt": 3})
        assert down.key == "Super" and down.press is True, code
        assert up.key == "Super" and up.press is False, code
    # a repeat is still a press (the tap stays armed across auto-repeat)
    rep = d._norm_key({"key": chr(57444), "mods": 9, "evt": 2})
    assert rep.key == "Super" and rep.press is True
    # Shift/Ctrl/Hyper/Meta bare-modifier codes stay filtered out
    for code in (57441, 57442, 57445, 57446, 57447, 57448, 57451, 57452):
        assert d._norm_key({"key": chr(code), "mods": 1, "evt": 1}) is None, code


# ── a bare tap opens the Start menu; a second tap closes it ──────────────────
def test_super_tap_toggles_start_menu():
    d = H.make_desk((1024, 768))
    assert d.taskbar.menu_open == -1
    _super_down(d)
    assert not d.menus.active              # nothing happens until the release
    _super_up(d)
    assert d.taskbar.menu_open == 1 and d.menus.active
    _super_down(d)
    _super_up(d)
    assert d.taskbar.menu_open == -1 and not d.menus.active


# ── auto-repeat of the held Super key does not disarm the tap ────────────────
def test_super_repeat_keeps_tap():
    d = H.make_desk((1024, 768))
    _super_down(d)
    d.dispatch_key(d._norm_key({"key": chr(57444), "mods": 9, "evt": 2}))
    _super_up(d)
    assert d.taskbar.menu_open == 1


# ── Super+<key> is not stolen: another key while held disarms the tap ────────
def test_super_combo_not_stolen():
    d = H.make_desk((1024, 768))
    _super_down(d)
    ev = d._norm_key({"key": "d", "mods": 9, "text": "", "evt": 1})  # Super+D
    d.dispatch_key(ev)
    _super_up(d)
    assert d.taskbar.menu_open == -1 and not d.menus.active
    # once disarmed, a fresh clean tap still works
    _super_down(d)
    _super_up(d)
    assert d.taskbar.menu_open == 1


# ── clicking while Super is held is not a tap either ─────────────────────────
def test_super_click_disarms_tap():
    d = H.make_desk((1024, 768))
    _super_down(d)
    H.press(d, 200, 200)
    H.release(d, 200, 200)
    _super_up(d)
    assert d.taskbar.menu_open == -1 and not d.menus.active


# ── a tap with a context popup open replaces it with the Start menu ──────────
def test_super_tap_replaces_context_popup():
    d = H.make_desk((1024, 768))
    d.menus.open([W.MenuItem("Item", action=lambda: None)], 100, 100)
    assert d.menus.active and d.taskbar.menu_open == -1
    _super_down(d)
    _super_up(d)
    assert d.taskbar.menu_open == 1 and d.menus.active


# ── a modal dialog owns all input: the tap re-activates it, no menu ──────────
def test_super_blocked_by_modal():
    d = H.make_desk((1024, 768))
    apps.open(d, "notepad", None)
    dlg = wm.msgbox(d, "T", "hi", buttons=("OK",))
    _super_down(d)
    _super_up(d)
    assert not d.menus.active and d.wm.active is dlg


# ── mid Alt+Tab, Super is not a tap and Alt-up still commits ─────────────────
def test_super_during_switcher_does_not_open():
    d = H.make_desk((1024, 768))
    for _ in range(2):
        apps.open(d, "notepad", None)
    d.dispatch_key(W.Ev(kind="key", key="Alt", press=True, alt=True))
    d.dispatch_key(W.Ev(kind="key", key="Tab", alt=True))
    assert d.switcher is not None
    _super_down(d)
    _super_up(d)
    assert not d.menus.active
    d.dispatch_key(W.Ev(kind="key", key="Alt", press=False))
    assert d.switcher is None


# ── end-to-end: raw kitty-protocol bytes through DeskTerm open the menu ──────
def _desk_term_feed(data):
    t = object.__new__(desk_main.DeskTerm)
    r, w = os.pipe()
    os.set_blocking(r, False)
    t.fd = r
    t.inbuf = b""
    try:
        os.write(w, data)
        return t.read_input()
    finally:
        os.close(r)
        os.close(w)


def test_kitty_protocol_end_to_end():
    d = H.make_desk((1024, 768))
    press_release = b"\x1b[57444;9:1u\x1b[57444;9:3u"
    for raw in _desk_term_feed(press_release):
        ev = d._norm_key(raw)
        if ev is not None:
            d.dispatch_key(ev)
    assert d.taskbar.menu_open == 1 and d.menus.active
    # Super_R taps too (and toggles the open menu closed)
    for raw in _desk_term_feed(b"\x1b[57450;9:1u\x1b[57450;9:3u"):
        ev = d._norm_key(raw)
        if ev is not None:
            d.dispatch_key(ev)
    assert d.taskbar.menu_open == -1 and not d.menus.active


for _name, _fn in sorted(list(globals().items())):
    if _name.startswith("test_") and callable(_fn):
        _fn()
print("ok")
