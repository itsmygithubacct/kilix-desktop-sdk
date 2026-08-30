"""Programs ▸ Cameras opens the camera list, however this machine has it.

Two branches, the same discipline as every other pinned tool here: an
installed `kilix-cameras` wins, and otherwise the host's own verb — which
installs the viewer on first use rather than reporting it missing. A source
checkout is deliberately not consulted.
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


d = H.make_desk()
d.taskbar.open_start_menu()
programs = _find(d.menus.stack[0].items, "Programs")
assert programs is not None and programs.submenu
entry = _find(programs.submenu, "Cameras")
assert entry is not None, [i.label for i in programs.submenu if i.label != "-"]
assert entry.icon == "display", entry.icon
assert "display" in icons.ICONS
for size in (16, 32):
    image = icons.get("display", size)
    assert image.size == (size, size)
    assert image.getbbox() is not None, "the display icon drew nothing"

opened = []
d.shell._tab = lambda argv, title, cwd=None, env=None: opened.append(
    (list(argv), title))
entry.action()
assert len(opened) == 1, opened
assert opened[0][1] == "Cameras", opened

saved = shutil.which
try:
    shutil.which = lambda name: "/opt/bin/kilix-cameras" \
        if name == "kilix-cameras" else None
    assert d.shell.kilix_cameras_target() == ["/opt/bin/kilix-cameras"]

    # Nothing installed: the host verb, which installs the viewer rather
    # than leaving the menu item dead.
    shutil.which = lambda name: None
    target = d.shell.kilix_cameras_target()
    assert target is not None, "no fallback at all"
    assert target[0].endswith("kilix") and target[1] == "rtsp", target

    source_home = os.environ.get("GPU_TERMINAL_SOURCE_HOME") or \
        os.path.expanduser("~/.local/gpu_terminal/sources")
    checkout = os.path.join(source_home, "kilix-modules", "kilix-rtsp",
                            "build", "kilix-rtsp")
    if os.path.isfile(checkout):
        assert checkout not in target, target
finally:
    shutil.which = saved

print("ok")
