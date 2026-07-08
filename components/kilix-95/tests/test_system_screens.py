"""Startup/shutdown screens and the code-rendered BSOD state."""
import harness as H

d = H.make_desk()

for name in ("startup", "shutdown"):
    img = d._system_screen(name)
    assert img.size == d.size(), (name, img.size)

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
