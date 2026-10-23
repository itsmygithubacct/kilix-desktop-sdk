"""Keyboard access to desktop launchers and files, including offscreen rows."""
import harness as H          # noqa: sets up sys.path for the imports below
import widgets as W
import theme as T
from main import Desk
from kilix_sdk.term import SPECIAL_CSI


def key(grid, name, **mods):
    # Feed the same arrow names emitted by the terminal parser and Desk.
    letters = {'Up': 'A', 'Down': 'B', 'Right': 'C', 'Left': 'D'}
    parsed = SPECIAL_CSI[letters[name]][0] if name in letters else name
    event = Desk._norm_key(None, {'key': parsed, 'mods': 2 if mods.get('shift') else 1})
    assert grid.on_key(event)


activated = []
desktop = W.IconGrid(0, 0, 300, 4 * T.CELL_H + 4, desktop=True,
                     on_activate=lambda item: activated.append(item['label']))
desktop.set_items([{'label': str(i)} for i in range(10)])
key(desktop, 'End')
assert desktop.sel == {9}
key(desktop, 'Home')
assert desktop.sel == {0}
key(desktop, 'Up')
assert desktop.sel == {0}
key(desktop, 'Down')
assert desktop.sel == {1}
key(desktop, 'Left')
assert desktop.sel == {1}
key(desktop, 'Right')
assert desktop.sel == {5}
key(desktop, 'Left')
assert desktop.sel == {1}
key(desktop, 'Down', shift=True)
key(desktop, 'Down', shift=True)
assert desktop.sel == {1, 2, 3}
key(desktop, 'Down', shift=True)
assert desktop.sel == {1, 2, 3}, 'Down must not wrap into another desktop column'
key(desktop, 'End')
assert desktop.sel == {9}
key(desktop, 'Enter')
assert activated == ['9']
assert not desktop.on_key(W.Ev(key='Left', alt=True))
desktop.set_items([])
key(desktop, 'Home')
assert desktop.sel == set()

files = W.IconGrid(0, 0, 3 * T.CELL_W + T.SCROLL_W + 8,
                   2 * T.CELL_H + 8)
files.set_items([{'label': str(i)} for i in range(11)])
key(files, 'Home')
key(files, 'Right')
key(files, 'Up')
assert files.sel == {1}
key(files, 'Home')
key(files, 'Down')
assert files.sel == {3}
key(files, 'Left')
assert files.sel == {3}, 'Left must not wrap into the preceding file row'
key(files, 'Right')
assert files.sel == {4}
key(files, 'End')
assert files.sel == {10} and files.sb.pos == 2
key(files, 'Home', shift=True)
assert files.sel == set(range(11)) and files.sb.pos == 0
files.on_mouse(W.Ev(kind='mouse', x=5, y=5, btn=1, press=True))
key(files, 'Right', shift=True)
assert files.sel == {0, 1}, 'A mouse selection must reset the keyboard range anchor'
print('Icon grid keyboard navigation, activation, ranges and scrolling passed')
