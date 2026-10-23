"""Live semantic actions, stale identities, modal policy and secret masking."""
import json
import socket
import struct

import harness as H
import apps
import wm
import widgets as W
from accessibility import Tree
from accessibility_protocol import Channel, LIMIT, state_words, text_span


def named(tree, name, role=None):
    tree.build()
    matches = [n for n in tree.nodes.values() if n['name'] == name and (role is None or n['role'] == role)]
    assert len(matches) == 1, (name, matches)
    return matches[0]


d = H.make_desk()
tree = Tree(d)
desktop = named(tree, 'Home', 'desktop icon')
assert tree.apply(desktop['id'], 'focus', [])
assert d.shell.grid.items[d.shell.grid._keyboard_item]['label'] == 'Home'
assert 'focused' in named(tree, 'Home', 'desktop icon')['states']
d.frontend_focused = False
assert 'focused' not in named(tree, 'Home', 'desktop icon')['states']
assert not tree.apply(desktop['id'], 'activate', [])
d.frontend_focused = True

# Real editor changes invoke its normal modified/save-confirmation behavior.
apps.open(d, 'notepad', None)
np = H.find_window(d, 'Notepad')
text = named(tree, 'Document text', 'text')
assert tree.apply(text['id'], 'set_text', ['café 日本語\nsecond line'])
assert np.ta.text() == 'café 日本語\nsecond line'
assert np.modified and np.title.startswith('*')
assert tree.apply(text['id'], 'caret', [8])
assert tree.text_position(np.ta)[0] == 8
assert tree.apply(text['id'], 'selection', [5, 8])
assert tree.text_position(np.ta)[1] == [5, 8]
assert tree.apply(text['id'], 'copy_text', [5, 8]) and d.clipboard == '日本語'
assert tree.apply(text['id'], 'delete_text', [5, 8])
assert np.ta.text() == 'café \nsecond line'
assert not tree.apply(text['id'], 'selection', [100, 101])

# Home/End stay on the current line; Ctrl and Shift use document boundaries.
np.ta.set_text('first\nsecond\nlast')
np.ta._move(1, 3, False)
assert np.ta.on_key(H.ev('key', key='Home'))
assert (np.ta.cr, np.ta.cc) == (1, 0)
assert np.ta.on_key(H.ev('key', key='Home', ctrl=True))
assert (np.ta.cr, np.ta.cc) == (0, 0)
assert np.ta.on_key(H.ev('key', key='End', ctrl=True))
assert (np.ta.cr, np.ta.cc) == (2, 4)
assert np.ta.on_key(H.ev('key', key='Home', ctrl=True, shift=True))
assert np.ta._sel() == ((0, 0), (2, 4))

# GrabFocus must actually transfer focus out of an open popup.
d.menus.open([W.MenuItem('Popup command', action=lambda: None)], 20, 20)
assert d.menus.active
assert tree.apply(text['id'], 'focus', [])
assert not d.menus.active and np.focus is np.ta

# A modal dialog blocks underlying text, taskbar and window actions.
answers = []
box = wm.msgbox(d, 'Confirm', 'Proceed?', buttons=('Yes', 'No'), cb=answers.append)
yes = named(tree, 'Yes', 'button')
assert not tree.apply(text['id'], 'set_text', ['blocked'])
assert not tree.apply('start', 'open', [])
assert tree.apply(yes['id'], 'activate', [])
assert answers == ['Yes'] and box not in d.wm.windows
assert not tree.apply(yes['id'], 'activate', [])

secret = W.TextField(5, 5, 120, 'controlled-secret', mask=True)
np.add(secret)
secret.on_change = lambda value: None
node = named(tree, 'Text', 'password text')
assert 'controlled-secret' not in json.dumps(tree.build())
assert node['text'] == '\u2022' * len('controlled-secret')
assert not tree.apply(node['id'], 'copy_text', [0, len(secret.text)])
secret.enabled = False
assert not tree.apply(node['id'], 'set_text', ['refused'])

# A replaced file item reusing an index/name gets a new accessible identity.
grid = np.add(W.IconGrid(5, 50, 160, 100, on_activate=lambda item: answers.append(item['data'])))
grid.items = [dict(label='same.txt', icon='file', data='old')]
old = named(tree, 'same.txt', 'list item')
grid.set_items([dict(label='same.txt', icon='file', data='new')])
new = named(tree, 'same.txt', 'list item')
assert old['id'] != new['id']
assert not tree.apply(old['id'], 'activate', [])
assert not tree.apply(tree.identity(grid), 'select_child', [0, old['id']])
assert tree.apply(tree.identity(grid), 'select_child', [0, new['id']])
assert tree.apply(new['id'], 'activate', []) and answers[-1] == 'new'

# Closed/replaced popup actions cannot activate a newly opened menu row.
d.menus.open([W.MenuItem('Do old', action=lambda: answers.append('old'))], 20, 20)
old = named(tree, 'Do old', 'menu item')
d.menus.close_all()
d.menus.open([W.MenuItem('Do old', action=lambda: answers.append('replacement'))], 20, 20)
assert not tree.apply(old['id'], 'activate', [])
assert tree.apply(named(tree, 'Do old', 'menu item')['id'], 'activate', [])
assert answers[-1] == 'replacement'

# Keyboard and screen-reader activation use the same live page/choice callbacks.
pages = np.add(W.TabBar(5, 170, 180, ['First', 'Second'], cb=answers.append))
np.set_focus(pages)
assert pages.on_key(H.ev('key', key='ArrowRight')) and pages.active == 1 and answers[-1] == 1
assert tree.apply(named(tree, 'First', 'page tab')['id'], 'activate', [])
assert pages.active == 0 and answers[-1] == 0
choice = np.add(W.Dropdown(5, 200, 160, ['One', 'Two'], cb=answers.append))
np.set_focus(choice)
assert choice.on_key(H.ev('key', key='End')) and choice.value == 'Two' and answers[-1] == 'Two'
assert choice.on_key(H.ev('key', key=' ', text=' ')) and d.menus.active
d.menus.close_all()

assert state_words(['focused', 'checkable']) == [1 << 12, 1 << 9]
assert text_span('café 日本語\nsecond', 5, 1) == ('日本語\n', 5, 9)
assert text_span('café 日本語\nsecond', 10, 3) == ('second', 9, 15)
assert text_span('a\nb', 2, 5, legacy=True) == ('b', 2, 3)
assert text_span('ab', 2, 0) == ('', 2, 2)

# Fragmented frames do not get parsed early or escape the declared bound.
a, b = socket.socketpair()
channel = Channel(a)
packet = json.dumps({'type': 'test', 'text': '日本語'}).encode()
wire = struct.pack('!I', len(packet)) + packet
for byte in wire[:-1]:
    b.send(bytes([byte]))
    assert channel.receive() == []
b.send(wire[-1:])
assert channel.receive() == [{'type': 'test', 'text': '日本語'}]
b.send(struct.pack('!I', LIMIT + 1))
try:
    channel.receive()
except ValueError:
    pass
else:
    raise AssertionError('oversized accessibility frame accepted')
a.close()
b.close()

# Focus reports must stay out of editor text, including fragmented CSI input.
t = H.desk_main.DeskTerm.__new__(H.desk_main.DeskTerm)
assert t._parse_csi('', 'I') == {'kind': 'focus', 'focused': True}
assert t._parse_csi('', 'O') == {'kind': 'focus', 'focused': False}
print('ok')
