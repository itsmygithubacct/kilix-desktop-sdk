"""Text rectangles, actual ink, Unicode offsets, clipping and live identity."""
import json
from PIL import Image, ImageChops

import harness as H
import apps
import theme as T
import widgets as W
from accessibility import Tree
from accessibility_text import TextGeometry


def invalid(callback):
    try:
        callback()
    except (ValueError, KeyError):
        return
    raise AssertionError('Invalid text geometry request was accepted')


d = H.make_desk()
apps.open(d, 'notepad', None)
win = H.find_window(d, 'Notepad')
ta = win.ta
ta.set_text('café 日本語\nsecond line\n')
origin = win.client_origin()
layout = TextGeometry(ta, origin)
for i, char in enumerate(ta.text()):
    rect = layout.character(i)
    if char != '\n' and rect[2]:
        assert layout.offset_at(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2) == i
assert layout.extent(0, 0)[2] == 0
assert layout.character(len(ta.text()))[2] == 0
assert layout.extent(0, 9)[3] == ta.LH  # exclusive end at the next row's start
assert layout.extent(0, 10)[3] == 2 * ta.LH
invalid(lambda: layout.character(-1))
invalid(lambda: layout.character(True))
invalid(lambda: layout.extent(10, 9))
invalid(lambda: layout.offset_at(float('nan'), 1))

# Verify that the measured box actually contains the widget's rendered ink.
for cls in ('area', 'field'):
    for char in ('W', 'é', '日'):
        widget = W.TextArea(5, 5, 130, 40, char) if cls == 'area' else W.TextField(5, 5, 130, char)
        image = Image.new('RGB', (180, 80), T.WINDOW_BG)
        widget.draw(W.drawer(image), image)
        vx, vy, width, height = widget.text_viewport()
        crop = image.crop((vx, vy, vx + width, vy + height))
        ink = ImageChops.difference(crop, Image.new('RGB', crop.size, T.WINDOW_BG)).getbbox()
        assert ink is not None
        x, y, rw, rh = TextGeometry(widget, (0, 0)).character(0)
        assert x <= vx + ink[0] and y <= vy + ink[1]
        assert x + rw >= vx + ink[2] and y + rh >= vy + ink[3], (
            cls, char, (x, y, rw, rh), (vx, vy), ink)
        # The last visible pixel of overhanging ink still hits the character.
        assert TextGeometry(widget, (0, 0)).offset_at(vx + ink[2] - 1, vy + ink[1]) == 0

    # Full-string rendering preserves fractional prefix advances. An isolated
    # glyph test alone misses the one-pixel overhang after preceding text.
    text = 'W   é   日'
    widget = W.TextArea(5, 5, 130, 40, text) if cls == 'area' else W.TextField(5, 5, 130, text)
    image = Image.new('RGB', (180, 80), T.WINDOW_BG)
    widget.draw(W.drawer(image), image)
    geometry = TextGeometry(widget, (0, 0))
    for offset in (0, 4, 8):
        x, y, rw, rh = geometry.character(offset)
        crop = image.crop((x-1, y, x+rw+2, y+rh))
        ink = ImageChops.difference(crop, Image.new('RGB', crop.size, T.WINDOW_BG)).getbbox()
        assert ink is not None and 1 <= ink[0] and ink[2] <= rw+1, (cls, offset, ink, rw)

# Scrolling changes layout positions, not the Unicode document offsets.
ta.sb.pos = 1; ta.hx = 10
scrolled = TextGeometry(ta, origin)
box = scrolled.character(11)
assert scrolled.offset_at(box[0] + box[2] / 2, box[1] + box[3] / 2) == 11
vx, vy, width, height = ta.text_viewport()
assert scrolled.offset_at(origin[0] + vx - 1, origin[1] + vy + 5) == -1
assert scrolled.offset_at(origin[0] + vx + width, origin[1] + vy + 5) == -1
assert scrolled.offset_at(origin[0] + vx + 3, origin[1] + vy + height) == -1
assert scrolled.character(0)[1] < origin[1] + vy

# Password geometry uses bullets rather than the secret's varying widths.
field = W.TextField(5, 5, 40, 'Wiié秘密', mask=True)
field.scroll = 5
password = TextGeometry(field, (20, 30))
assert password.lines == ['•' * len(field.text)]
masked_boxes = [password.character(i) for i in range(len(field.text))]
field.text = 'iiiiii'
assert [TextGeometry(field, (20, 30)).character(i) for i in range(6)] == masked_boxes
assert field.text not in json.dumps(password.context())

# Queries revalidate actual controls and use current window/scroll placement.
tree = Tree(d); tree.build(); key = tree.identity(ta)
before = tree.query(key, 'character_rect', [11])
win.x += 17
after = tree.query(key, 'character_rect', [11])
assert after['value'][0] == before['value'][0] + 17
ta.enabled = False
assert tree.query(key, 'range_rect', [0, 4])['value']
win.minimized = True
invalid(lambda: tree.query(key, 'character_rect', [0]))
win.minimized = False
ta.visible = False
invalid(lambda: tree.query(key, 'character_rect', [0]))
ta.visible = True
win.modified = False; win.request_close()
invalid(lambda: tree.query(key, 'character_rect', [0]))
print('Text geometry and live widget checks passed.')
