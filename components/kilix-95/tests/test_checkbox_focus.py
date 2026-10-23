"""A keyboard-focused Checkbox shows the dotted focus marquee.

In the RC5 VM the first-run Model setup dialog opened with focus on its first
checkbox and Tab moved through five checkboxes without any visible change;
only the buttons drew a focus rectangle.
"""
import harness as H
import wm
import widgets as W
import theme as T


def crop(win, wdg):
    win.invalidate()
    win.render()
    ox, oy = T.BORDER, T.BORDER + T.TITLE_H
    return win.surface.crop((ox + wdg.x - 2, oy + wdg.y - 2,
                             ox + wdg.x + wdg.w + 2, oy + wdg.y + wdg.h + 2)).convert("RGB")


d = H.make_desk()
win = wm.Window(d, "Focus", 320, 160)
d.wm.add(win)
box = win.add(W.Checkbox(12, 12, "Install the default voice", checked=True))
other = win.add(W.Checkbox(12, 40, "Install another voice"))
ok = win.add(W.Button(12, 80, 90, 24, "OK", cb=lambda: None))

assert win.focus is box, "the first focusable widget takes focus"
focused = crop(win, box)
win.focus = other
unfocused = crop(win, box)
assert focused.tobytes() != unfocused.tobytes(), \
    "focusing a checkbox must change its pixels (no visible keyboard focus)"

# Tab moves the visible marquee from one checkbox to the next and on to the button.
win.focus = box
before_other = crop(win, other)
win.on_key(H.ev("key", key="Tab"))
assert win.focus is other
assert crop(win, other).tobytes() != before_other.tobytes(), "Tab target must show focus"
assert crop(win, box).tobytes() != focused.tobytes(), "Tab source must drop its focus marquee"

# A disabled checkbox keeps its plain look even if focus was left on it.
other.enabled = False
win.focus = other
disabled_focused = crop(win, other)
win.focus = ok
assert disabled_focused.tobytes() == crop(win, other).tobytes(), \
    "a disabled checkbox must not advertise keyboard focus"
print("checkbox focus ok")
