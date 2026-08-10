"""Programs ▸ Region Painter launches kilix-mask, after asking what to paint.

Two things worth pinning. It has to resolve the *same* way the Kilix CLI does —
an installed command, otherwise the pinned installer — or a Start-menu launch
and a `kilix mask` typed in a pane could edit the same file with two different
builds of its format.

And it must not open onto an error. The painter needs a picture before it can
do anything, so the entry asks for one and then for where the mask should go;
a menu item whose only outcome is a usage message is not a menu item.
"""
import os
import shutil

import harness as H

# After the harness: it is what puts the desktop's modules on the path.
import filedialog
import icons


def _find(items, label):
    for item in items:
        if item.label == label:
            return item
    return None


def _labels(items):
    return [item.label for item in items if item.label != "-"]


d = H.make_desk()
d.taskbar.open_start_menu()
top = d.menus.stack[0].items

programs = _find(top, "Programs")
assert programs is not None and programs.submenu, _labels(top)
entry = _find(programs.submenu, "Region Painter")
assert entry is not None, _labels(programs.submenu)
assert entry.icon == "paint", entry.icon

assert "paint" in icons.ICONS
for size in (16, 32):
    image = icons.get("paint", size)
    assert image.size == (size, size), image.size
    assert image.getbbox() is not None, "the paint icon drew nothing"

# Asked for a picture, then for a mask, then opened with both.
opened = []
asked = []
saved_open, saved_save = filedialog.open_file, filedialog.save_file
try:
    filedialog.open_file = lambda _desk, title, cb, **_kw: (
        asked.append(title), cb("/pictures/hallway.png"))
    filedialog.save_file = lambda _desk, title, cb, **kw: (
        asked.append((title, kw.get("filename"))),
        cb("/pictures/hallway.mask.png"))
    d.shell._tab = lambda argv, title, cwd=None, env=None: opened.append(
        (list(argv), title))
    entry.action()
finally:
    filedialog.open_file, filedialog.save_file = saved_open, saved_save

assert len(asked) == 2, asked
# The mask is named after the picture rather than left blank, but it is still
# offered for confirmation: writing one silently beside somebody's photograph
# is not this program's business.
assert asked[1][1] == "hallway.mask.png", asked
assert len(opened) == 1, opened
argv, title = opened[0]
assert title == "Region Painter", title
assert "--image" in argv and "/pictures/hallway.png" in argv, argv
assert argv[-1] == "/pictures/hallway.mask.png", argv

# Cancelling at either step opens nothing.
for cancel_at in (0, 1):
    opened.clear()
    saved_open, saved_save = filedialog.open_file, filedialog.save_file
    try:
        filedialog.open_file = lambda _desk, _title, cb, **_kw: cb(
            None if cancel_at == 0 else "/pictures/hallway.png")
        filedialog.save_file = lambda _desk, _title, cb, **_kw: cb(None)
        entry.action()
    finally:
        filedialog.open_file, filedialog.save_file = saved_open, saved_save
    assert opened == [], (cancel_at, opened)

# Exactly two branches, the same two the Kilix CLI resolves.
saved_which = shutil.which
try:
    shutil.which = lambda name: "/opt/bin/kilix-mask" \
        if name == "kilix-mask" else None
    assert d.shell.kilix_mask_target() == ["/opt/bin/kilix-mask"]

    shutil.which = lambda name: None
    target = d.shell.kilix_mask_target()
    assert target is not None, "no fallback at all"
    assert target[-1] == "mask" and target[0].endswith("kilix"), target

    # A source checkout must not win, for the reason above: one build of the
    # format, whichever way the painter was started.
    source_home = os.environ.get("GPU_TERMINAL_SOURCE_HOME") or \
        os.path.expanduser("~/.local/gpu_terminal/sources")
    checkout = os.path.join(source_home, "kilix-modules", "kilix-mask",
                            "build", "kilix-mask")
    if os.path.isfile(checkout):
        assert checkout not in target, target
finally:
    shutil.which = saved_which

print("ok")
