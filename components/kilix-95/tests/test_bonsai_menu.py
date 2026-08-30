"""Programs ▸ BitNet Models launches Kilix Bonsai, and its icon exists.

Two things worth pinning. The entry has to resolve the *same* way the Kilix CLI
resolves it — an installed command, otherwise the pinned installer — or a
Start-menu launch and a `kilix bonsai` typed in a pane could end up running
different builds of a tool that downloads gigabytes. And the model store must
open with nothing downloaded, because that is its normal first run: the entry
must not gate itself on weights being present.
"""
import os
import shutil

import harness as H
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
entry = _find(programs.submenu, "BitNet Models")
assert entry is not None, _labels(programs.submenu)
assert entry.icon == "bonsai", entry.icon

# The icon is drawn in code like every other one here, at both rendered sizes.
assert "bonsai" in icons.ICONS
for size in (16, 32):
    image = icons.get("bonsai", size)
    assert image.size == (size, size), image.size
    assert image.getbbox() is not None, "the bonsai icon drew nothing"

# The entry opens a tab rather than doing anything itself.
opened = []
d.shell._tab = lambda argv, title, cwd=None, env=None: opened.append(
    (list(argv), title))
entry.action()
assert len(opened) == 1, opened
argv, title = opened[0]
assert title == "BitNet Models", title

# Exactly two branches, the same two the Kilix CLI resolves: an installed
# command wins, and otherwise the Kilix launcher runs the pinned installer.
# A source checkout is deliberately not consulted — a working tree is not the
# pinned closure, and this is the tool that downloads gigabytes.
saved_which = shutil.which
try:
    shutil.which = lambda name: "/opt/bin/kilix-bonsai" \
        if name == "kilix-bonsai" else None
    assert d.shell.kilix_bonsai_target() == ["/opt/bin/kilix-bonsai"]

    shutil.which = lambda name: None
    target = d.shell.kilix_bonsai_target()
    assert target is not None, "no fallback at all"
    assert target[-1] == "bonsai" and target[0].endswith("kilix"), target

    # Even with a source checkout present and importable, it must not win.
    source_home = os.environ.get("GPU_TERMINAL_SOURCE_HOME") or \
        os.path.expanduser("~/.local/gpu_terminal/sources")
    checkout = os.path.join(source_home, "kilix-apps", "kilix-bonsai",
                            "tools", "kilix-bonsai", "main.py")
    if os.path.isfile(checkout):
        assert checkout not in target, target
finally:
    shutil.which = saved_which

print("ok")
