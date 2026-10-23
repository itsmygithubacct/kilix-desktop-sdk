"""Expose the live Kilix 95 object tree without a duplicate, hidden GUI.

Snapshots contain presentation data only. Each action is rebuilt and checked
against current widgets on the UI thread, so a closed menu/window or a replaced
file-list item can never redirect an old screen-reader request to another item.
"""
import hashlib
import itertools
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import weakref

import theme as T
import widgets as W
from accessibility_protocol import Channel, MAX_NODES
from accessibility_text import TextGeometry


def clean_name(text):
    return str(text).split('\t', 1)[0]



# Edits a read-only text widget refuses; caret, selection and copy still work.
READ_ONLY_REFUSED = frozenset({'set_text', 'insert_text', 'delete_text',
                               'cut_text', 'paste_text'})

GEOMETRY_INTERVAL = .25
GEOMETRY_MAX_BACKOFF = 30.0
GEOMETRY_WANTED_SECONDS = 30.0

class Tree:
    def __init__(self, desk):
        self.desk = desk
        self._counter = itertools.count(1)
        self._objects = weakref.WeakKeyDictionary()
        self._items = weakref.WeakKeyDictionary()
        self.nodes = {}
        self.handlers = {}
        self.queries = {}

    def identity(self, obj, suffix=''):
        if obj not in self._objects:
            self._objects[obj] = 'n' + str(next(self._counter))
        return self._objects[obj] + suffix

    def item_ids(self, owner, items):
        old = self._items.get(owner, [])
        # Preserve identity only for the same live item, never its index/name.
        previous = {}
        for item, key in old:
            previous.setdefault(id(item), []).append((item, key))
        current = []
        for item in items:
            records = previous.get(id(item), [])
            record = records.pop(0) if records else None
            key = record[1] if record is not None and record[0] is item else 'n' + str(next(self._counter))
            current.append((item, key))
        self._items[owner] = current
        return [key for item, key in current]

    def add(self, key, parent, name, role, rect, states=(), actions=None,
            focus=None, **values):
        if len(self.nodes) >= MAX_NODES:
            raise ValueError('desktop accessibility tree exceeds node limit')
        node = dict(id=key, parent=parent, name=str(name), role=role,
                    rect=list(map(int, rect)), states=list(dict.fromkeys(states)),
                    children=[], actions=list((actions or {}).keys()), **values)
        if focus is not None:
            node['focusable'] = True
            self.handlers[(key, 'focus')] = focus
        self.nodes[key] = node
        if parent is not None:
            self.nodes[parent]['children'].append(key)
        for kind, cb in (actions or {}).items():
            self.handlers[(key, kind)] = cb
        return node

    def foreground(self):
        return bool(getattr(self.desk, 'frontend_focused', self.desk.term is None)) and not (
            self.desk.saving or self.desk.bsod or self.desk.switcher is not None)

    def states(self, enabled=True, showing=True, focused=False, focusable=False):
        out = ['visible']
        if enabled:
            out += ['enabled', 'sensitive']
        if showing:
            out.append('showing')
        if focusable:
            out.append('focusable')
        if focused and self.foreground():
            out.append('focused')
        return out

    def allowed_window(self, win):
        modal = self.desk.wm.modal_top()
        return win in self.desk.wm.windows and (modal is None or modal is win)

    def widget_focus(self, widget):
        win = widget.window
        if win is self.desk.shell:
            if self.desk.wm.modal_top() is not None:
                return False
            self.desk.menus.close_all()
            self.desk.wm.active = None
        elif not self.allowed_window(win):
            return False
        else:
            self.desk.menus.close_all()
            self.desk.wm.activate(win)
            win.set_focus(widget)
        self.desk.dirty = True
        return True

    def _widget_name(self, win, widget):
        if getattr(widget, 'accessibility_name', None):
            return widget.accessibility_name
        if isinstance(widget, (W.Button, W.Checkbox, W.Label)):
            return clean_name(widget.text) or (getattr(widget, 'icon', '') or '').replace('_', ' ').capitalize()
        labels = [w for w in win.widgets if isinstance(w, W.Label) and w.visible
                  and ((abs(w.y - widget.y) < 24 and w.x + w.w <= widget.x + 8)
                       or (0 <= widget.y - w.y <= 28 and abs(w.x - widget.x) < 20))]
        if labels:
            label = min(labels, key=lambda w: abs(w.y - widget.y) + abs(w.x - widget.x))
            return clean_name(label.text).rstrip(':')
        if isinstance(widget, W.TextArea):
            return 'Document text'
        return {W.TextField: 'Text', W.IconGrid: 'Files', W.ListBox: 'Items',
                W.TabBar: 'Pages', W.Dropdown: 'Selection', W.MenuBar: 'Menu bar',
                W.GroupBox: getattr(widget, 'label', '')}.get(type(widget), 'Content')

    def build(self):
        d = self.desk
        self.nodes, self.handlers, self.queries = {}, {}, {}
        whole = (0, 0, d.w, d.h)
        self.add('root', None, T.PRODUCT_NAME, 'application', whole, self.states())
        self.add('desktop', 'root', T.PRODUCT_NAME + ' desktop', 'frame', whole,
                 self.states(focused=False) + (['active'] if self.foreground() else []))
        self.widget(d.shell.grid, 'desktop', (0, 0), 'Desktop',
                    d.wm.active is None and not d.menus.active, True)
        for win in d.wm.windows:
            key = self.identity(win)
            allowed = self.allowed_window(win)
            showing = not win.minimized and not d.saving and not d.bsod
            active = d.wm.active is win and self.foreground()
            states = self.states(allowed, showing, focused=False)
            if active:
                states.append('active')
            if win.modal:
                states.append('modal')
            if win.minimized:
                states.append('iconified')
            if win.resizable:
                states.append('resizable')
            actions = {'activate': lambda win=win: self._activate(win)} if allowed else {}
            self.add(key, 'desktop', win.title, 'dialog' if win.modal else 'internal frame',
                     (win.x, win.y, win.w, win.h), states, actions,
                     focus=lambda win=win: self._activate(win))
            if not win.chromeless:
                self.add(key + '_close', key, 'Close', 'button',
                         (win.x + win.w - 23, win.y + T.BORDER + 2, 18, T.TITLE_H - 4),
                         self.states(allowed, showing),
                         {'activate': lambda win=win: self._close_window(win)} if allowed else {})
            for widget in win.widgets:
                if widget.visible:
                    self.widget(widget, key, win.client_origin(), self._widget_name(win, widget),
                                active and win.focus is widget and not d.menus.active,
                                showing, allowed)
        self.taskbar()
        self.menus()
        return {'type': 'snapshot', 'nodes': list(self.nodes.values()),
                'foreground': self.foreground()}

    def _activate(self, win):
        if not self.allowed_window(win):
            return False
        self.desk.menus.close_all()
        self.desk.wm.activate(win)
        return True

    def _close_window(self, win):
        if not self.allowed_window(win):
            return False
        win.request_close()
        return True

    def widget(self, widget, parent, origin, name, focused, showing, allowed=True):
        key = self.identity(widget)
        ox, oy = origin
        rect = (ox + widget.x, oy + widget.y, widget.w, widget.h)
        enabled = allowed and widget.enabled
        focus = lambda: self.widget_focus(widget)
        states = self.states(enabled, showing, focused,
                             focusable=widget.focusable)
        actions, values = {}, {}
        role = 'canvas'
        if isinstance(widget, W.Button):
            role = 'button'
            if widget.default:
                states.append('is-default')
            if enabled:
                actions['activate'] = lambda: self._button(widget)
        elif isinstance(widget, W.Checkbox):
            role = 'check box'
            states.append('checkable')
            if widget.checked:
                states.append('checked')
            if enabled:
                actions['toggle'] = lambda: self._checkbox(widget)
        elif isinstance(widget, W.Label):
            role = 'status bar' if getattr(widget, 'is_status', False) else 'label'
        elif isinstance(widget, W.GroupBox):
            role, name = 'panel', widget.label
        elif isinstance(widget, (W.TextField, W.TextArea)):
            role = 'password text' if getattr(widget, 'mask', False) else 'text'
            raw = widget.text if isinstance(widget, W.TextField) else widget.text()
            # Password contents never cross the helper socket, including diffs.
            values['text'] = '\u2022' * len(raw) if role == 'password text' else raw
            values['caret'], values['selection'] = self.text_position(widget)
            layout = TextGeometry(widget, origin)
            values['text_view'] = [self.identity(layout.font),
                                   hashlib.sha256(values['text'].encode()).hexdigest(),
                                   *layout.context()]
            if showing:
                self.queries[key] = lambda kind, args: TextGeometry(widget, origin).query(kind, args)
            states += ['selectable-text', 'single-line' if isinstance(widget, W.TextField) else 'multi-line']
            read_only = getattr(widget, 'read_only', False)
            if enabled:
                states.append('read-only' if read_only else 'editable')
                for kind in ('set_text', 'insert_text', 'delete_text', 'caret', 'selection', 'copy_text', 'cut_text', 'paste_text'):
                    if read_only and kind in READ_ONLY_REFUSED:
                        continue
                    if role != 'password text' or kind not in ('copy_text', 'cut_text'):
                        self.handlers[(key, kind)] = lambda args, kind=kind: self.edit(widget, kind, args)
            else:
                states.append('read-only')
        elif isinstance(widget, (W.ListBox, W.IconGrid)):
            role = 'list'
            if (isinstance(widget, W.IconGrid) and widget._keyboard_item is not None
                    or isinstance(widget, W.ListBox) and widget.sel >= 0):
                states = [state for state in states if state != 'focused']
            if isinstance(widget, W.IconGrid):
                states.append('multiselectable')
            values['selection_container'] = True
            if enabled:
                for kind in ('select_child', 'deselect_child', 'select_all', 'clear_selection'):
                    self.handlers[(key, kind)] = lambda args, kind=kind: self.select(widget, kind, args)
        elif isinstance(widget, W.MenuBar):
            role = 'menu bar'
        elif isinstance(widget, W.TabBar):
            role = 'page tab list'
        elif isinstance(widget, W.Dropdown):
            role, name = 'combo box', name + ': ' + widget.value
            states.append('has-popup')
            if enabled:
                actions['open'] = lambda: self._dropdown(widget)
        node = self.add(key, parent, name, role, rect, states, actions,
                        focus if widget.focusable and enabled else None, **values)
        if isinstance(widget, (W.IconGrid, W.ListBox)):
            items = widget.items
            keys = self.item_ids(widget, items)
            for i, (item, itemkey) in enumerate(zip(items, keys)):
                if isinstance(widget, W.IconGrid):
                    x, y = widget._cell(i)
                    label = item['label']
                    r = (ox + x, oy + y, T.CELL_W, T.CELL_H)
                    selected = i in widget.sel
                    hot = i == widget._keyboard_item
                    visible = showing and widget.y <= y < widget.y + widget.h
                else:
                    label = item[1]
                    r = (rect[0] + 2, rect[1] + 2 + (i - widget.sb.pos) * widget.RH,
                         max(0, widget.w - 4 - T.SCROLL_W), widget.RH)
                    selected = i == widget.sel
                    hot = selected
                    visible = showing and widget.sb.pos <= i < widget.sb.pos + widget._rows()
                childstates = self.states(enabled, visible, focused and hot, True) + ['selectable']
                if selected:
                    childstates.append('selected')
                self.add(itemkey, key, label, 'desktop icon' if getattr(widget, 'desktop', False) else 'list item',
                         r, childstates,
                         {'activate': lambda w=widget, i=i: self._item_activate(w, i)} if enabled and widget.on_activate else {},
                         lambda w=widget, i=i: self._item_focus(w, i) if enabled else False)
        elif isinstance(widget, W.MenuBar):
            entries = self.item_ids(widget, widget.items)
            for (i, label, x, width), itemkey in zip(widget._spans(), entries):
                self.add(itemkey, key, clean_name(label), 'menu',
                         (ox + x, rect[1], width, widget.h), self.states(enabled, showing),
                         {'open': lambda w=widget, i=i, x=x: self._bar(w, i, x)} if enabled else {})
        elif isinstance(widget, W.TabBar):
            # Tab ids belong to this actual strip and label object, not indices.
            keys = self.item_ids(widget, widget.tabs)
            x = rect[0] + 2
            for i, (label, width, itemkey) in enumerate(zip(widget.tabs, widget._tab_widths(), keys)):
                s = self.states(enabled, showing, focused and i == widget.active, True) + ['selectable']
                if i == widget.active:
                    s.append('selected')
                self.add(itemkey, key, label, 'page tab', (x, rect[1], width, widget.h), s,
                         {'activate': lambda w=widget, i=i: self._tab(w, i)} if enabled else {},
                         lambda w=widget, i=i: self._tab(w, i) if enabled else False)
                x += width
        return node

    def _button(self, widget):
        self.widget_focus(widget)
        if widget.cb:
            widget.cb()
        return True

    def _checkbox(self, widget):
        self.widget_focus(widget)
        widget.checked = not widget.checked
        widget.invalidate()
        if widget.cb:
            widget.cb(widget.checked)
        return True

    def _item_focus(self, widget, index):
        if not self.widget_focus(widget):
            return False
        return self.select(widget, 'select_child', [index])

    def _item_activate(self, widget, index):
        if not self._item_focus(widget, index):
            return False
        return widget.on_activate(widget.items[index]) is not False

    def select(self, widget, kind, args):
        index = args[0] if args else None
        if kind in ('select_child', 'deselect_child') and (
                type(index) is not int or not 0 <= index < len(widget.items)):
            return False
        if isinstance(widget, W.IconGrid):
            if kind == 'clear_selection':
                widget.sel.clear()
            elif kind == 'select_all':
                widget.sel = set(range(len(widget.items)))
            elif kind == 'deselect_child':
                widget.sel.discard(index)
            else:
                # Same reveal/selection behavior as physical arrow navigation.
                widget._keyboard_item = index
                widget.sel = {index}
                widget._selection_anchor = index
                if not widget.desktop:
                    _, per_row = widget._grid()
                    widget.sb.total = widget._rows_total()
                    widget.sb.page = max(1, (widget.h - 8) // T.CELL_H)
                    row = index // per_row
                    widget.sb.pos = min(widget.sb.pos, row)
                    if row >= widget.sb.pos + widget.sb.page:
                        widget.sb.pos = row - widget.sb.page + 1
                    widget.sb.clamp()
        else:
            if kind == 'select_all':
                return False  # a ListBox is single-selection
            widget.sel = -1 if kind == 'clear_selection' or kind == 'deselect_child' else index
            if widget.sel >= 0:
                widget.sb.total, widget.sb.page = len(widget.items), widget._rows()
                widget.sb.pos = min(widget.sb.pos, widget.sel)
                if widget.sel >= widget.sb.pos + widget.sb.page:
                    widget.sb.pos = widget.sel - widget.sb.page + 1
                widget.sb.clamp()
                if widget.on_select:
                    widget.on_select(widget.items[widget.sel])
        widget.invalidate()
        return True

    def _tab(self, widget, index):
        self.widget_focus(widget)
        if widget.active != index:
            widget.active = index
            widget.invalidate()
            if widget.cb:
                widget.cb(index)
        return True

    def _bar(self, widget, index, x):
        self.desk.wm.activate(widget.window)
        widget._open(index, x)
        self.desk.menus.stack[-1].move_hot(1, start=-1)
        return True

    def _dropdown(self, widget):
        self.widget_focus(widget)
        widget.on_mouse(W.Ev(kind='mouse', press=True, btn=1))
        self.desk.menus.stack[-1].move_hot(1, start=-1)
        return True

    def menus(self):
        host = self.desk.menus
        for menu in host.stack:
            key = self.identity(menu)
            self.add(key, 'desktop', 'Menu', 'menu', (menu.x, menu.y, menu.w, menu.h), self.states())
            keys = self.item_ids(menu, menu.items)
            for i, ((item, r), itemkey) in enumerate(zip(menu.item_rects(), keys)):
                top, bottom = menu._content()
                states = self.states(item.enabled, r[1] >= top and r[1] < bottom,
                                     menu is host.stack[-1] and i == menu.hot,
                                     item.label != '-' and item.enabled)
                if item.submenu is not None:
                    states += ['has-popup', 'expandable']
                if item.checked:
                    states += ['checkable', 'checked']
                self.add(itemkey, key, clean_name(item.label),
                         'separator' if item.label == '-' else 'check menu item' if item.checked else 'menu item',
                         (r[0], r[1], r[2] - r[0] + 1, r[3] - r[1] + 1), states,
                         {'activate': lambda m=menu, i=i: self._menu_action(m, i)} if item.enabled and item.label != '-' else {},
                         (lambda m=menu, i=i: self._menu_focus(m, i)) if item.enabled and item.label != '-' else None)

    def _menu_focus(self, menu, index):
        host = self.desk.menus
        if menu not in host.stack:
            return False
        del host.stack[host.stack.index(menu) + 1:]
        menu.hot = index
        menu._reveal(index)
        self.desk.dirty = True
        return True

    def _menu_action(self, menu, index):
        if not self._menu_focus(menu, index):
            return False
        self.desk.menus.on_key(W.Ev(kind='key', key='Enter'))
        return True

    def taskbar(self):
        bar, d = self.desk.taskbar, self.desk
        x0, y0, x1, y1 = bar.rect()
        allowed = d.wm.modal_top() is None
        self.add('taskbar', 'desktop', 'Taskbar', 'panel',
                 (x0, y0, x1 - x0, y1 - y0 + 1), self.states(allowed))
        self.add('start', 'taskbar', 'Start', 'button',
                 (x0 + 2, y0 + 2, bar._start_w(), y1 - y0 - 3), self.states(allowed),
                 {'open': bar.open_start_menu} if allowed else {})
        for i, name, tip, act, bx0, bx1 in bar._ql_buttons():
            self.add('quick_' + name, 'taskbar', tip, 'button',
                     (bx0, y0 + 4, bx1 - bx0 + 1, y1 - y0 - 6), self.states(allowed),
                     {'activate': act} if allowed else {})
        for win, bx0, bx1 in bar._buttons():
            enabled = self.allowed_window(win)
            self.add(self.identity(win, '_task'), 'taskbar', win.title, 'button',
                     (bx0, y0 + 4, bx1 - bx0 + 1, y1 - y0 - 6), self.states(enabled),
                     {'activate': lambda w=win: self._activate(w)} if enabled else {})
        for name, tip, bx0, bx1 in bar._tray_icons():
            self.add('tray_' + name, 'taskbar', tip, 'button',
                     (bx0, y0 + 4, bx1 - bx0 + 1, y1 - y0 - 6), self.states(allowed),
                     {'activate': lambda name=name: bar._tray_click(name)} if allowed else {})
        r = bar._clock_rect()
        self.add('clock', 'taskbar', bar._minute or time.strftime('%I:%M %p'), 'status bar',
                 (r[0], r[1], r[2] - r[0] + 1, r[3] - r[1] + 1), self.states())

    @staticmethod
    def text_position(widget):
        if isinstance(widget, W.TextField):
            return widget.cur, list(widget._sel() or ())
        def offset(point):
            row, col = point
            return sum(len(line) + 1 for line in widget.lines[:row]) + col
        selection = widget._sel()
        return offset((widget.cr, widget.cc)), [offset(p) for p in selection] if selection else []

    @staticmethod
    def _text_point(text, offset):
        before = text[:offset]
        return before.count('\n'), len(before.rsplit('\n', 1)[-1])

    def edit(self, widget, kind, args):
        if getattr(widget, 'read_only', False) and kind in READ_ONLY_REFUSED:
            return False
        text = widget.text if isinstance(widget, W.TextField) else widget.text()
        if kind == 'set_text':
            if len(args) != 1 or not isinstance(args[0], str):
                return False
            after, caret, anchor = args[0], len(args[0]), None
        else:
            if not args or type(args[0]) is not int or not 0 <= args[0] <= len(text):
                return False
            start = args[0]
            if kind in ('delete_text', 'selection', 'copy_text', 'cut_text'):
                if len(args) != 2 or type(args[1]) is not int or not start <= args[1] <= len(text):
                    return False
                end = args[1]
                if kind in ('copy_text', 'cut_text'):
                    if getattr(widget, 'mask', False):
                        return False
                    self.desk.set_clipboard(text[start:end])
                    if kind == 'copy_text':
                        return True
                after = text if kind == 'selection' else text[:start] + text[end:]
                caret, anchor = (end, start) if kind == 'selection' else (start, None)
            elif kind in ('insert_text', 'paste_text'):
                inserted = self.desk.clipboard if kind == 'paste_text' else args[1] if len(args) == 2 else None
                if not isinstance(inserted, str):
                    return False
                after = text[:start] + inserted + text[start:]
                caret, anchor = start + len(inserted), None
            elif kind == 'caret':
                after, caret, anchor = text, start, None
            else:
                return False
        if isinstance(widget, W.TextField):
            after = after.replace('\r', '').replace('\n', ' ')
            widget.text, widget.cur, widget.anchor = after, min(caret, len(after)), anchor
        else:
            widget.lines = after.split('\n') or ['']
            widget.cr, widget.cc = self._text_point(after, caret)
            widget.anchor = self._text_point(after, anchor) if anchor is not None else None
        widget._reveal()
        widget.invalidate()
        if after != text and widget.on_change:
            widget.on_change(after) if isinstance(widget, W.TextField) else widget.on_change()
        return True

    def apply(self, key, kind, args):
        self.build()  # Revalidate after asynchronous close/refresh/modal changes.
        if not self.foreground():
            return False
        cb = self.handlers.get((key, kind))
        if cb is None:
            return False
        if kind in ('select_child', 'deselect_child'):
            # The helper resolves an index to the actual item identity before
            # queueing. A refresh can replace that index before the UI reads it.
            if (len(args) != 2 or type(args[0]) is not int
                    or not 0 <= args[0] < len(self.nodes[key]['children'])
                    or self.nodes[key]['children'][args[0]] != args[1]):
                return False
            args = args[:1]
        result = cb(args) if kind in ('set_text', 'insert_text', 'delete_text', 'caret', 'selection',
                                     'copy_text', 'cut_text', 'paste_text', 'select_child',
                                     'deselect_child', 'select_all', 'clear_selection') else cb()
        return result is not False

    def query(self, key, kind, args):
        self.build()
        if kind not in ('character_rect', 'range_rect', 'offset_at_point'):
            raise ValueError('Unknown text geometry request')
        callback = self.queries.get(key)
        if callback is None:
            raise ValueError('Text control is closed or hidden')
        node = self.nodes[key]
        return {'value': callback(kind, args), 'node_rect': node['rect'], 'text_view': node['text_view'],
                'canvas_size': [self.desk.w, self.desk.h],
                'canvas_grid': [self.desk.term.cols, self.desk.term.rows] if self.desk.term else None}


class Controller:
    def __init__(self, desk):
        self.desk, self.tree = desk, Tree(desk)
        self.last = None
        self.closed = False
        self._geometry = None
        self._geometry_stop = threading.Event()
        self._geometry_wake = threading.Event()
        self._geometry_wanted_until = 0.0
        self._geometry_thread = None
        parent, child = socket.socketpair()
        try:
            interpreter = '/usr/bin/python3' if Path('/usr/bin/python3').is_file() else sys.executable
            self.process = subprocess.Popen(
                [interpreter, str(Path(__file__).with_name('accessibility_service.py')),
                 str(child.fileno()), str(os.getpid())], pass_fds=(child.fileno(),),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        except BaseException:
            parent.close()
            raise
        finally:
            child.close()
        self.channel = Channel(parent)
        self.fd = parent.fileno()
        desk.add_fd(self.fd, self.read)
        desk.tick_hooks.append(self.tick)
        if desk.term is not None and os.environ.get('KITTY_WINDOW_ID'):
            self._geometry_thread = threading.Thread(target=self._observe_geometry, daemon=True)
            self._geometry_thread.start()
        self.tick(time.time())

    def _observe_geometry(self):
        try:
            from kilix_sdk import geometry
        except ImportError:
            return
        delay = GEOMETRY_INTERVAL
        while not self._geometry_stop.is_set():
            if time.monotonic() >= self._geometry_wanted_until:
                # Nobody is asking for screen coordinates: spawn nothing.
                self._geometry = None
                self._geometry_wake.clear()
                if time.monotonic() >= self._geometry_wanted_until:
                    self._geometry_wake.wait(1)
                    continue
            try:
                value, unused = geometry.current(timeout=.4)
                self._geometry = (time.monotonic(), value)
                delay = GEOMETRY_INTERVAL
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
                # A refused or unavailable query is not retried four times a
                # second for the whole session: back off until it answers.
                self._geometry = None
                delay = min(delay * 2, GEOMETRY_MAX_BACKOFF)
            if self._geometry_stop.wait(delay):
                return

    def read(self):
        try:
            for message in self.channel.receive():
                if message.get('type') == 'geometry-wanted':
                    self._geometry_wanted_until = time.monotonic() + GEOMETRY_WANTED_SECONDS
                    self._geometry_wake.set()
                    continue
                if message.get('type') != 'request':
                    continue
                accepted = False
                value = None
                if time.monotonic() <= message.get('deadline', 0):
                    try:
                        kind = message['kind']
                        if kind in ('character_rect', 'range_rect', 'offset_at_point'):
                            value = self.tree.query(message['node'], kind, message.get('args', []))
                            accepted = True
                        else:
                            accepted = self.tree.apply(message['node'], kind, message.get('args', []))
                    except (IndexError, KeyError, TypeError, ValueError):
                        accepted = False
                self.publish()
                self.channel.queue({'type': 'reply', 'request': message['request'], 'accepted': accepted, 'value': value})
        except (EOFError, OSError, ValueError):
            self.close()

    def tick(self, now):
        if self.closed:
            return
        try:
            if self.process.poll() is not None:
                self.close()
                return
            if self.channel.has_message():
                self.read()
            self.publish()
        except (EOFError, OSError, ValueError):
            self.close()

    def publish(self):
        if self.closed:
            return
        try:
            self.channel.flush()
            current = self.tree.build()
            current['canvas_size'] = [self.desk.w, self.desk.h]
            if self.desk.term is not None:
                current['canvas_grid'] = [self.desk.term.cols, self.desk.term.rows]
            value = self._geometry
            if value is not None and time.monotonic() - value[0] < .8:
                current['viewport'] = {'observed': value[0], 'geometry': value[1]}
            if current != self.last:
                self.channel.queue(current)
                self.last = current
        except (EOFError, OSError, ValueError):
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._geometry_stop.set()
        self.desk.remove_fd(self.fd)
        if self.tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.tick)
        self.channel.sock.close()
        if self.process.poll() is None:
            self.process.terminate()
        # Do not block shutdown on a toolkit or accessibility bus.
        try:
            self.process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=1)
