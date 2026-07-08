"""Startup/shutdown screens and the code-rendered BSOD state."""
import os
import shutil
import tempfile

import harness as H
import main as desk_main
from PIL import Image, ImageDraw

d = H.make_desk()

for name in ("startup", "shutdown"):
    img = d._system_screen(name)
    assert img.size == d.size(), (name, img.size)


# Wide screens must not crop the splash artwork. The real startup art has
# important content near both vertical edges; a fit/crop scale loses it.
old_dir = desk_main.SCREEN_DIR
tmp = tempfile.mkdtemp(prefix="kilix95-screen-")
try:
    desk_main.SCREEN_DIR = tmp
    src = Image.new("RGB", (100, 100), (20, 30, 40))
    draw = ImageDraw.Draw(src)
    draw.rectangle([0, 0, 99, 14], fill=(250, 0, 0))
    draw.rectangle([0, 85, 99, 99], fill=(0, 0, 250))
    src.save(os.path.join(tmp, "startup.png"))
    wide = H.make_desk(size=(180, 100))
    img = wide._system_screen("startup")
    assert img.size == (180, 100)
    assert img.getpixel((90, 0))[0] > 200, "top edge was cropped"
    assert img.getpixel((90, 99))[2] > 200, "bottom edge was cropped"
finally:
    desk_main.SCREEN_DIR = old_dir
    shutil.rmtree(tmp, ignore_errors=True)

for key in ("KILIX_STARTUP_SCREEN_SECONDS", "KILIX_SHUTDOWN_SCREEN_SECONDS"):
    os.environ.pop(key, None)
assert d._system_screen_seconds("startup") == 1.2
os.environ["KILIX_STARTUP_SCREEN_SECONDS"] = "0"
assert d._system_screen_seconds("startup") == 1.0
os.environ["KILIX_STARTUP_SCREEN_SECONDS"] = "9"
assert d._system_screen_seconds("startup") == 2.0
os.environ["KILIX_STARTUP_SCREEN_SECONDS"] = "bad"
assert d._system_screen_seconds("startup") == 1.2
os.environ.pop("KILIX_STARTUP_SCREEN_SECONDS", None)

d.show_bsod()
assert d.bsod
d.render()
assert not d.dirty
assert d.fb.getpixel((d.w // 2, d.h // 2))[:2] == (0, 0)

H.key(d, "Escape")
assert not d.bsod

d.taskbar.open_start_menu()
labels = [it.label for it in d.menus.stack[0].items]
assert "BSOD" in labels, labels

print("test_system_screens OK")
