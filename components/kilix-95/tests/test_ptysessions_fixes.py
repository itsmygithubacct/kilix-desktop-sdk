"""Regressions from the B1 independent review (fix round 1).

1. Laying out the largest bounded output must not stall the UI thread.
2. The End confirmation and every message box expose their text to the
   accessibility tree.
3. A read-only text view refuses every edit, including through accessibility
   and paste, while navigation, selection and copy still work.
(The confirmation's complete-ID/command display and the receipt fixtures are
checked in test_ptysessions.py and test_ptysessions_contract.py.)
"""
import os
import time

import harness as H
import pty_fake as F
import theme as T
import widgets as W
import wm
from accessibility import Tree
from apps import ptysessions as P
from apps.notepad import Notepad

os.environ.pop("KITTY_PTY_BROKER_SESSION", None)
fake = F.FakeKilix(F.standard_responses())
P.kilix_launcher = lambda: fake.path
d = H.make_desk()


def best_of(n, fn):
    best = 1e9
    for _ in range(n):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


# ── 1. bounded UI cost, any text, cold cache ────────────────────────────────
# Opening and resizing cost the UI thread only a submit; the layout runs on a
# worker thread and lands from a tick hook. Bounds are loose for a loaded
# host (the old code stalled for 2-12 s).
BOUND = 0.3
distinct = lambda start, n: "".join(chr(start + i) for i in range(n))
cases = {"one ascii line": "x" * 65536,
         "one multibyte line": "界" * 65536,
         "mixed prose": "ab 界 W " * 9000,
         "200 long lines": "\n".join("x" * 326 for _ in range(200)),
         "repeated A (positive kerning)": "A" * 65536,
         "21,000 distinct CJK": distinct(0x4E00, 21000),
         "65,536 distinct plane-2": distinct(0x20000, 65536)}


def rows_fit(win, step=1):
    """Rows (every `step`th) that measure wider than the viewport as a
    whole string; empty means they all fit."""
    limit = win.view.w - T.SCROLL_W - 10
    return [line for line in win.view.lines[::step]
            if len(line) > 1 and T.text_w(win.view.font, line) > limit]


for name, text in cases.items():
    data = P._bounded_text({"text": text, "truncated": False}, "test")
    box = []
    opened = best_of(1, lambda: box.append(
        P.OutputWindow(d, "t", "banner", data["text"])))
    for old in box[:-1]:
        old.close()
    win = box[-1]
    assert opened < BOUND, (name, "open", opened)
    assert win.view.pending, (name, "large text must be laid out off-thread")
    # the layout is verified in full for the hard cases; the others (the
    # review's original repeated-character cases) only need to be cheap here
    # and are covered losslessly by the wrap_lines checks below
    hard = name.startswith(("repeated A", "65,536 distinct"))
    full = name.startswith(("repeated A", "65,536 distinct"))
    if hard:
        assert win.view.wait(60), name
        assert "".join(win.view.lines) == data["text"].replace("\n", ""), name
        assert not rows_fit(win, 1 if full else 4), (name, rows_fit(win)[:2])

    def resize():
        win.w += 23 if win.w < 900 else -300
        win.on_resize()
    resized = best_of(1, resize)
    assert resized < BOUND, (name, "resize", resized)
    if name == "65,536 distinct plane-2":                    # rest abandoned
        assert win.view.wait(60), name
        assert "".join(win.view.lines) == data["text"].replace("\n", ""), name
        assert not rows_fit(win, 5), (name, "after resize", rows_fit(win, 5)[:2])
    if name in ("mixed prose", "65,536 distinct plane-2"):
        d.dirty = True
        d.render()
    win.close()
    assert not win.view.pending and win.view._poll not in d.tick_hooks

# the placeholder is what is up while the first layout runs
win = P.OutputWindow(d, "t", "banner", "界" * 60000)
assert win.view.pending and win.view.text() == "Laying out the text…"
assert win.view._poll in d.tick_hooks
win.close()                                      # closing abandons the work
assert not win.view.pending and win.view._poll not in d.tick_hooks

# through the real job path: the UI-thread part of a finished preview
fake.set([F.response(["pty", "observe"], F.doc(
    F.OBSERVE, text=distinct(0x20000, 65536), total_bytes=262141))]
    + F.standard_responses())
win = P.PtySessions(d)
d.wm.add(win)
end = time.time() + 8
while win.futures and time.time() < end:
    win._tick(time.time())
    time.sleep(0.02)
win.list.sel = 1
win._select_session(win.list.items[1])
win._preview()
future = win.futures["preview"][0]
future.result(timeout=10)
spent = best_of(1, lambda: win._tick(time.time()))
assert spent < BOUND, spent
view = H.find_window(d, "OutputWindow")
assert view is not None and view.view.wait(60)
assert "".join(view.view.lines) == distinct(0x20000, 65536)
assert not rows_fit(view)
view.close()
win.close()

# ── wrap_lines: nothing lost, every row fits as a whole string ──────────────
limit = 570
for text in ("A" * 75, "A" * 1000, "AV To Ty " * 200, "W" * 64, "界" * 300,
             "e\u0301" * 200):
    rows = P.wrap_lines(text, limit)
    assert "".join(rows) == text
    assert all(T.text_w(T.FONT, r) <= limit for r in rows if len(r) > 1), text
row75 = P.wrap_lines("A" * 75, limit)
assert max(T.text_w(T.FONT, r) for r in row75) <= limit
assert P.wrap_lines("", 100) == [""]
assert P.wrap_lines("a\n\nb", 100) == ["a", "", "b"]
prose = P.wrap_lines("one two three four five six seven", 80, words=True)
assert " ".join(prose).split() == "one two three four five six seven".split()
assert all(T.text_w(T.FONT, r) <= 80 for r in prose), prose
assert len(P.wrap_lines("x" * 50, 1)) == 50          # always makes progress
assert P.wrap_lines("W", 1, words=True) == ["W"]     # no index past the end
assert P.wrap_lines("a " * 3, 1, words=True)
stop = P.threading.Event()
stop.set()
assert P.wrap_lines("x" * 5000, 100, cancel=stop) is None

# the same two commands, one differing letter at the very end, must render
# different End confirmations (the last character may not be clipped away)
images = []
for last in "BC":
    dlg = P.ConfirmEnd(d, "b12.clipped", "A" * 49 + last, lambda: None)
    d.wm.add(dlg)
    assert "".join(dlg.view.lines).count("A" * 49 + last) == 1
    assert not rows_fit(dlg)
    images.append(dlg.render().tobytes())
    dlg.close()
assert images[0] != images[1], "different commands look identical"

# a command too long to lay out at once: End waits until all of it is shown
huge = "run " + "界x" * 3000
dlg = P.ConfirmEnd(d, "3fa9c2d41b7e6a05", huge, lambda: seen.append("ended"))
d.wm.add(dlg)
seen = []
assert dlg.view.pending and not dlg.b_end.enabled
dlg._end()                                       # the API/keyboard path too
bx, by = dlg.client_origin()
H.click(d, bx + dlg.b_end.x + 5, by + dlg.b_end.y + 5)
assert seen == [] and dlg in d.wm.windows, "End worked before the layout"
assert dlg.view.wait(60) and dlg.b_end.enabled
assert huge in "".join(dlg.view.lines)
dlg._end()
assert seen == ["ended"] and dlg not in d.wm.windows

# ── 2. message boxes and the End dialog in the accessibility tree ───────────
tree = Tree(d)


def dialog_text(dialog):
    tree.build()
    root = tree.identity(dialog)
    nodes = [n for n in tree.nodes.values()
             if n["id"] == root or n["parent"] == root]
    return nodes, " ".join(n["name"] + " " + str(n.get("text", ""))
                           for n in nodes)


box = wm.msgbox(d, "Receipt", "Session 3fa9c2d41b7e6a05 has ended.\n\n"
                "Result: verified_absent", icon="info")
nodes, exposed = dialog_text(box)
assert "3fa9c2d41b7e6a05" in exposed and "verified_absent" in exposed, nodes
assert any(n["role"] == "label" for n in nodes), nodes
box.close()

# a word wider than the box is split instead of running off it
box = wm.msgbox(d, "Wide", "W" * 64)
lines = wm._wrap_text("W" * 64, T.FONT, 260)
assert "".join(lines) == "W" * 64 and len(lines) > 1
assert all(T.text_w(T.FONT, line) <= 260 for line in lines)
box.close()

win = P.PtySessions(d)
d.wm.add(win)
end = time.time() + 8
fake.set(F.standard_responses())
win.refresh()
while win.futures and time.time() < end:
    win._tick(time.time())
    time.sleep(0.02)
win.list.sel = 1
win._select_session(win.list.items[1])
win._end()
dlg = H.find_window(d, "ConfirmEnd")
nodes, exposed = dialog_text(dlg)
assert F.DETACHED["id"] in exposed, nodes
assert F.DETACHED["command"] in exposed, nodes
assert "will be terminated" in exposed and "Cancel" in exposed, nodes
text_node = [n for n in nodes if n["role"] == "text"][0]
assert "read-only" in text_node["states"] and "editable" not in text_node["states"]
dlg.close()

# the receipt dialog
fake.set([F.kill_response(F.UNCERTAIN_UNSENT)] + F.standard_responses())
win._confirmed_end(F.DETACHED["id"], F.DETACHED["started_millis"])
end = time.time() + 8
while win.futures and time.time() < end:
    win._tick(time.time())
    time.sleep(0.02)
receipt = [w for w in d.wm.windows if w.modal][-1]
nodes, exposed = dialog_text(receipt)
assert "uncertain" in exposed and "status_failed" in exposed, exposed
assert "Nothing was sent" in exposed, exposed
receipt.close()
win.close()

# ── 3. a read-only view is read-only everywhere ─────────────────────────────
view = P.OutputWindow(d, "Pane output: t", "untrusted pane output",
                      "original pane output\nsecond line")
d.wm.add(view)
tree.build()
node = tree.nodes[tree.identity(view.view)]
assert "read-only" in node["states"] and "editable" not in node["states"], node
assert view.view.read_only
before = view.view.text()
for kind, args in (("set_text", ["changed through accessibility"]),
                   ("insert_text", [0, "evil"]),
                   ("delete_text", [0, 8]),
                   ("cut_text", [0, 8]),
                   ("paste_text", [0])):
    d.clipboard = "pasted"
    assert not tree.apply(node["id"], kind, args), kind
    assert view.view.text() == before, (kind, view.view.text())
# navigation, selection and copying are still accessible actions
assert tree.apply(node["id"], "caret", [4])
assert tree.apply(node["id"], "selection", [0, 8])
d.clipboard = ""
assert tree.apply(node["id"], "copy_text", [0, 8])
assert d.clipboard == "original"
assert view.view.text() == before

# the keyboard, a paste and the direct API are refused too
view.set_focus(view.view)
for key in ("Backspace", "Delete", "Enter", "Tab", "x", "Z"):
    H.key(d, key)
H.key(d, "v", ctrl=True)
d.dispatch_paste("pasted text")
view.view.insert("direct")
assert view.view.text() == before, view.view.text()
H.key(d, "a", ctrl=True)                         # select all ...
d.clipboard = ""
H.key(d, "c", ctrl=True)                         # ... copy
assert d.clipboard == before, repr(d.clipboard)
d.clipboard = ""
H.key(d, "x", ctrl=True)                         # cut is only a copy here
assert d.clipboard == before and view.view.text() == before
H.key(d, "ArrowDown")
H.key(d, "End")
assert view.view.text() == before
view.close()

# the shared widget is read-only only where asked: editors still edit
d2 = H.make_desk()
pad = Notepad(d2, None)
d2.wm.add(pad)
tree2 = Tree(d2)
tree2.build()
pnode = tree2.nodes[tree2.identity(pad.ta)]
assert "editable" in pnode["states"] and "read-only" not in pnode["states"]
assert tree2.apply(pnode["id"], "set_text", ["still editable"])
assert pad.ta.text() == "still editable"

# ── 4. a layout that fails never unlocks End Session ────────────────────────
from concurrent.futures import Future
from unittest import mock


class HeldPool:
    """Layout jobs that finish only when the test says so (or fails)."""

    def __init__(self):
        self.futures = []

    def submit(self, fn, *args, **kwargs):
        future = Future()
        self.futures.append(future)
        return future


def kill_argv(fake_):
    return [c for c in fake_.calls() if c[:2] == ["pty", "kill"]]


big = "A" * 5000 + " SECRET-TAIL"
pool = HeldPool()
confirmed = []
with mock.patch.object(P, "_LAYOUT_POOL", pool):
    dlg = P.ConfirmEnd(d, "3fa9c2d41b7e6a05", big, lambda: confirmed.append(1))
    d.wm.add(dlg)
    assert dlg.view.pending and not dlg.b_end.enabled
    pool.futures[-1].set_exception(RuntimeError("injected layout failure"))
    dlg.view._poll(time.time())
    # the failure is not a layout: nothing is recorded as laid out, nothing
    # unlocks, and the dialog says the target cannot be shown
    assert dlg.view.failed and not dlg.view.pending and not dlg.view.complete
    assert dlg.view._laid_out is None
    assert dlg.view.text() == P._Viewer.FAILED_TEXT
    assert not dlg.b_end.enabled, "End Session unlocked after a failed layout"
    dlg._end()
    bx, by = dlg.client_origin()
    H.click(d, bx + dlg.b_end.x + 4, by + dlg.b_end.y + 4)
    H.key(d, "Enter")                                   # Cancel is the default
    assert confirmed == [], "a failed layout confirmed the end"
    assert dlg not in d.wm.windows                      # Enter cancelled it
    d.wm.add(dlg) if dlg not in d.wm.windows else None

with mock.patch.object(P, "_LAYOUT_POOL", HeldPool()) as held:
    dlg = P.ConfirmEnd(d, "3fa9c2d41b7e6a05", big, lambda: confirmed.append(1))
    d.wm.add(dlg)
    held.futures[-1].set_exception(RuntimeError("injected"))
    dlg.view._poll(time.time())
    labels = " ".join(w.text for w in dlg.widgets
                      if isinstance(w, W.Label) and w.visible)
    assert "could not be displayed" in labels and "cannot be ended from here" \
        in labels, labels
    assert "will be terminated" not in labels          # the usual line is gone
    assert dlg.focus is dlg.b_cancel and dlg.b_cancel.default
    nodes, exposed = dialog_text(dlg)
    assert "could not be displayed" in exposed and "cannot be ended" in exposed
    # a later successful layout of the same text cannot revive the dialog
    dlg.view.show(dlg.view.source)
    held.futures[-1].set_result(["Session ID:", "x"])
    dlg.view._poll(time.time())
    assert dlg.view.complete and not dlg.b_end.enabled
    dlg._end()
    assert confirmed == []
    dlg.close()

# `complete` itself: a viewer that is fully laid out stops being complete the
# moment it records a failure, whatever else it remembers
probe = P._Viewer(0, 0, 300, 100, "")
probe.show("short text")
assert probe.complete
probe.failed = True
assert not probe.complete
probe.failed = False
assert probe.complete

# the full flow: no kill argv may be produced
fake.set(F.standard_responses())
fake.clear()
mgr = P.PtySessions(d)
d.wm.add(mgr)
end = time.time() + 8
while mgr.futures and time.time() < end:
    mgr._tick(time.time())
    time.sleep(0.02)
mgr.list.sel = 1
mgr._select_session(mgr.list.items[1])
mgr._selected_row()["session"]["command"] = big
held = HeldPool()
with mock.patch.object(P, "_LAYOUT_POOL", held):
    mgr._end()
    dlg = H.find_window(d, "ConfirmEnd")
    assert dlg is not None and not dlg.b_end.enabled
    held.futures[-1].set_exception(RuntimeError("injected layout failure"))
    dlg.view._poll(time.time())
    bx, by = dlg.client_origin()
    H.click(d, bx + dlg.b_end.x + 4, by + dlg.b_end.y + 4)
    assert "kill" not in mgr.futures and kill_argv(fake) == [], fake.calls()
    dlg._end()
    assert kill_argv(fake) == [] and "kill" not in mgr.futures
    dlg.close()
mgr.close()

# the same through the real pool when the worker cannot get its own face
with mock.patch.object(P, "_worker_font", side_effect=OSError("gone")):
    dlg = P.ConfirmEnd(d, "3fa9c2d41b7e6a05", big, lambda: confirmed.append(1))
    d.wm.add(dlg)
    assert dlg.view.pending
    dlg.view.wait(30)
    assert dlg.view.failed and not dlg.b_end.enabled
    dlg._end()
    assert confirmed == []
    dlg.close()

# a failure while laying out short text on the UI thread locks it too
real_wrap = P.wrap_lines


def wrap_or_boom(text, width, font=None, words=False, cancel=None):
    if not words:                                  # only the viewer's layout
        raise ValueError("boom")
    return real_wrap(text, width, font, words, cancel)


with mock.patch.object(P, "wrap_lines", wrap_or_boom):
    dlg = P.ConfirmEnd(d, "3fa9c2d41b7e6a05", "sleep 300",
                       lambda: confirmed.append(1))
    d.wm.add(dlg)
    assert dlg.view.failed and not dlg.b_end.enabled
    dlg._end()
    assert confirmed == []
    dlg.close()

# the output window shows the failure and still closes
with mock.patch.object(P, "_LAYOUT_POOL", HeldPool()) as held:
    out = P.OutputWindow(d, "t", "banner", "z" * 5000)
    d.wm.add(out)
    held.futures[-1].set_exception(RuntimeError("injected"))
    out.view._poll(time.time())
    assert out.view.failed and out.view.text() == P._Viewer.FAILED_TEXT
    d.dirty = True
    d.render()
    out.close()
    assert out not in d.wm.windows

# ── 5. the worker never shares the UI's font face ──────────────────────────
import shutil
import tempfile
import threading
from pathlib import Path
from PIL import ImageFont
with tempfile.TemporaryDirectory(prefix="k95-font-") as temp:
    custom = Path(temp) / "custom.ttf"
    shutil.copyfile(T.FONT.path, custom)
    ui_font = ImageFont.truetype(str(custom), 11)
    # normal: a worker thread gets its own, reused, independent face
    got = []
    thread = threading.Thread(target=lambda: got.extend(
        [P._worker_font(ui_font), P._worker_font(ui_font)]))
    thread.start()
    thread.join()
    assert got[0] is not ui_font and got[0] is got[1]
    # the file is renamed after the UI loaded it: no fallback to the UI face
    custom.rename(Path(temp) / "renamed.ttf")
    problems = []

    def probe():
        try:
            problems.append(("shared", P._worker_font(ui_font)))
        except OSError as error:
            problems.append(("refused", error))
    threads = [threading.Thread(target=probe) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [kind for kind, _ in problems] == ["refused", "refused"], problems
    try:
        P._layout_job("x" * 100, 200, ui_font, threading.Event())
    except OSError:
        pass
    else:
        raise AssertionError("a layout ran on a font it could not reopen")

print("ok")
