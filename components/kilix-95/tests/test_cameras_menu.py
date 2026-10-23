"""Cameras opens its catalog terminal window inside Kilix 95."""
import os

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
d.shell._tab = lambda *_args, **_kwargs: (_ for _ in ()).throw(
    AssertionError("desktop cameras escaped into a terminal pane"))
d.shell.open_in_xpane = lambda argv, title, **kwargs: opened.append(
    (list(argv), title, kwargs)) or True
assert entry.action()
assert len(opened) == 1, opened
argv, title, options = opened[0]
assert argv == [os.path.join(H.KILIX_HOME, "kilix"), "app", "window",
                "kilix-camera-manager"], argv
assert title == "Camera Manager", title
assert options["application_id"] == "kilix-camera-manager"
assert options["app_size"] == (900, 620)
print("ok")
