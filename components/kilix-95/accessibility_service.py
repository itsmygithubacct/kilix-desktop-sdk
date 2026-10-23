"""Owned AT-SPI D-Bus server for Kilix 95's live pixel controls.

GIO runs here rather than in the rendering loop. Mutation replies wait for the
desktop to accept the request against its current UI; no hidden GTK controls
or coordinate-injected stand-ins implement these objects.
"""
import ctypes
import itertools
import locale
import math
import os
import signal
import socket
import sys
import time

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

from accessibility_protocol import (CACHE, ROOT, NULL, PREFIX, Channel,
                                    MAX_NODES, ROLES, STATES, state_words, text_span)

import host
host.add_kilix_config_path()
try:
    from kilix_sdk.geometry import PaneGeometry, GeometryUnavailable
except ImportError:
    PaneGeometry = None
    GeometryUnavailable = ValueError

# Protocol metadata, independently stated from the upstream AT-SPI XML API.
METHODS = {
    'Accessible': {
        'GetChildAtIndex': (['i'], ['(so)']), 'GetChildren': ([], ['a(so)']),
        'GetIndexInParent': ([], ['i']), 'GetRelationSet': ([], ['a(ua(so))']),
        'GetRole': ([], ['u']), 'GetRoleName': ([], ['s']), 'GetLocalizedRoleName': ([], ['s']),
        'GetState': ([], ['au']), 'GetAttributes': ([], ['a{ss}']),
        'GetApplication': ([], ['(so)']), 'GetInterfaces': ([], ['as'])},
    'Application': {'GetLocale': (['u'], ['s']), 'GetApplicationBusAddress': ([], ['s'])},
    'Action': {'GetDescription': (['i'], ['s']), 'GetName': (['i'], ['s']),
               'GetLocalizedName': (['i'], ['s']), 'GetKeyBinding': (['i'], ['s']),
               'GetActions': ([], ['a(sss)']), 'DoAction': (['i'], ['b'])},
    'Component': {'Contains': (['i', 'i', 'u'], ['b']),
                  'GetAccessibleAtPoint': (['i', 'i', 'u'], ['(so)']),
                  'GetExtents': (['u'], ['(iiii)']), 'GetPosition': (['u'], ['i', 'i']),
                  'GetSize': ([], ['i', 'i']), 'GetLayer': ([], ['u']),
                  'GetMDIZOrder': ([], ['n']), 'GrabFocus': ([], ['b']),
                  'GetAlpha': ([], ['d']), 'SetExtents': (['i', 'i', 'i', 'i', 'u'], ['b']),
                  'SetPosition': (['i', 'i', 'u'], ['b']), 'SetSize': (['i', 'i'], ['b']),
                  'ScrollTo': (['u'], ['b']), 'ScrollToPoint': (['u', 'i', 'i'], ['b'])},
    'Text': {'GetText': (['i', 'i'], ['s']), 'GetStringAtOffset': (['i', 'u'], ['s', 'i', 'i']),
             'GetTextBeforeOffset': (['i', 'u'], ['s', 'i', 'i']),
             'GetTextAtOffset': (['i', 'u'], ['s', 'i', 'i']),
             'GetTextAfterOffset': (['i', 'u'], ['s', 'i', 'i']),
             'GetCharacterAtOffset': (['i'], ['i']), 'SetCaretOffset': (['i'], ['b']),
             'GetNSelections': ([], ['i']), 'GetSelection': (['i'], ['i', 'i']),
             'AddSelection': (['i', 'i'], ['b']), 'SetSelection': (['i', 'i', 'i'], ['b']),
             'RemoveSelection': (['i'], ['b']), 'GetAttributeValue': (['i', 's'], ['s']),
             'GetAttributes': (['i'], ['a{ss}', 'i', 'i']),
             'GetAttributeRun': (['i', 'b'], ['a{ss}', 'i', 'i']),
             'GetDefaultAttributes': ([], ['a{ss}']), 'GetDefaultAttributeSet': ([], ['a{ss}']),
             'GetCharacterExtents': (['i', 'u'], ['i', 'i', 'i', 'i']),
             'GetOffsetAtPoint': (['i', 'i', 'u'], ['i']),
             'GetRangeExtents': (['i', 'i', 'u'], ['i', 'i', 'i', 'i']),
             'GetBoundedRanges': (['i', 'i', 'i', 'i', 'u', 'u', 'u'], ['a(iisv)']),
             'ScrollSubstringTo': (['i', 'i', 'u'], ['b']),
             'ScrollSubstringToPoint': (['i', 'i', 'u', 'i', 'i'], ['b'])},
    'EditableText': {'SetTextContents': (['s'], ['b']), 'InsertText': (['i', 's', 'i'], ['b']),
                     'CopyText': (['i', 'i'], []), 'CutText': (['i', 'i'], ['b']),
                     'DeleteText': (['i', 'i'], ['b']), 'PasteText': (['i'], ['b'])},
    'Selection': {'GetSelectedChild': (['i'], ['(so)']), 'SelectChild': (['i'], ['b']),
                  'DeselectSelectedChild': (['i'], ['b']), 'DeselectChild': (['i'], ['b']),
                  'IsChildSelected': (['i'], ['b']), 'SelectAll': ([], ['b']),
                  'ClearSelection': ([], ['b'])},
    'Cache': {'GetItems': ([], ['a((so)(so)(so)iiassusau)'])},
}
PROPERTIES = {
    'Accessible': {'Name': 's', 'Description': 's', 'Parent': '(so)', 'ChildCount': 'i',
                   'Locale': 's', 'AccessibleId': 's', 'HelpText': 's', 'version': 'u'},
    'Application': {'ToolkitName': 's', 'ToolkitVersion': 's', 'Version': 's',
                    'AtspiVersion': 's', 'InterfaceVersion': 'u', 'Id': 'i'},
    'Action': {'NActions': 'i', 'version': 'u'}, 'Component': {'version': 'u'},
    'Text': {'CharacterCount': 'i', 'CaretOffset': 'i', 'version': 'u'},
    'EditableText': {'version': 'u'}, 'Selection': {'NSelectedChildren': 'i', 'version': 'u'},
    'Cache': {'version': 'u'},
}


def interface_xml(name):
    text = '<node><interface name="' + PREFIX + name + '">'
    for method, (inputs, outputs) in METHODS[name].items():
        text += '<method name="' + method + '">'
        for direction, types in (('in', inputs), ('out', outputs)):
            text += ''.join('<arg direction="' + direction + '" type="' + t + '"/>' for t in types)
        text += '</method>'
    for prop, typ in PROPERTIES[name].items():
        text += '<property name="' + prop + '" type="' + typ + '" access="' + (
            'readwrite' if name == 'Application' and prop == 'Id' else 'read') + '"/>'
    if name == 'Cache':
        text += '<signal name="AddAccessible"><arg type="((so)(so)(so)iiassusau)"/></signal>'
        text += '<signal name="RemoveAccessible"><arg type="(so)"/></signal>'
    return text + '</interface></node>'


INFOS = {name: Gio.DBusNodeInfo.new_for_xml(interface_xml(name)).interfaces[0] for name in METHODS}


class Service:
    def __init__(self, channel):
        self.channel = channel
        self.nodes = {}
        self.registrations = {}
        self.pending = {}
        self.counter = itertools.count(1)
        self.application_id = 0
        self.registry_parent = ('', NULL)
        self.embedded = False
        self.viewport = None
        self.viewport_observed = 0
        self.geometry_wanted_sent = float('-inf')
        self.canvas_size = self.canvas_grid = None
        self.loop = GLib.MainLoop()
        # Pleb's original physical session bus is preserved for private apps.
        env_address = os.environ.get('PLEB_DESKTOP_BUS_ADDRESS')
        flags = Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
        session = (Gio.DBusConnection.new_for_address_sync(env_address, flags, None, None)
                   if env_address else Gio.bus_get_sync(Gio.BusType.SESSION, None))
        address = session.call_sync('org.a11y.Bus', '/org/a11y/bus', 'org.a11y.Bus',
                                    'GetAddress', None, GLib.VariantType.new('(s)'),
                                    Gio.DBusCallFlags.NONE, 1500, None).unpack()[0]
        self.bus = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
        self.bus.set_exit_on_close(False)
        self.bus.connect('closed', lambda *unused: self.loop.quit())
        self.name = self.bus.get_unique_name()
        self.bus.register_object(CACHE, INFOS['Cache'], self.call, self.get_property, None)
        self.input_watch = GLib.io_add_watch(channel.sock.fileno(), GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, self.read)
        GLib.timeout_add(20, self.flush)

    @staticmethod
    def path(key):
        return ROOT if key == 'root' else '/org/a11y/atspi/accessible/' + key

    @staticmethod
    def key(path):
        return 'root' if path == ROOT else path.rsplit('/', 1)[-1]

    def ref(self, key):
        return (self.name, self.path(key)) if key is not None else ('', NULL)

    def interfaces(self, node):
        names = ['Accessible', 'Component']
        if node['id'] == 'root':
            names.append('Application')
        if node['actions']:
            names.append('Action')
        if 'text' in node:
            names.append('Text')
            if 'editable' in node['states']:
                names.append('EditableText')
        if node.get('selection_container'):
            names.append('Selection')
        return names

    def selected(self, node):
        return [key for key in node['children'] if 'selected' in self.nodes[key]['states']]

    def parent(self, node):
        return self.registry_parent if node['id'] == 'root' else self.ref(node['parent'])

    def cache_item(self, node):
        parent = self.nodes.get(node['parent'])
        index = parent['children'].index(node['id']) if parent is not None else -1
        return (self.ref(node['id']), self.ref('root'), self.parent(node), index,
                len(node['children']), [PREFIX + name for name in self.interfaces(node)],
                node['name'], ROLES[node['role']], node.get('description', ''), state_words(node['states']))

    def event(self, node, signal_name, detail='', a=0, b=0, value=None, window=False):
        self.bus.emit_signal(None, self.path(node['id']), PREFIX + ('Event.Window' if window else 'Event.Object'),
                             signal_name, GLib.Variant('(siiva{sv})',
                             (detail, a, b, value or GLib.Variant('i', 0), {})))

    def update(self, snapshot):
        prior_bounds = {}
        for key, node in self.nodes.items():
            try:
                prior_bounds[key] = self.screen_rect(node['rect'])
            except (ValueError, NotImplementedError):
                pass
        self.viewport = None
        self.canvas_size = snapshot.get('canvas_size')
        self.canvas_grid = snapshot.get('canvas_grid')
        viewport = snapshot.get('viewport')
        if PaneGeometry is not None and isinstance(viewport, dict):
            observed = viewport.get('observed')
            if type(observed) in (int, float) and math.isfinite(observed):
                try:
                    self.viewport = PaneGeometry.parse(viewport.get('geometry'))
                    self.viewport_observed = observed
                except GeometryUnavailable:
                    pass
        records = snapshot['nodes']
        if len(records) > MAX_NODES:
            raise ValueError('too many accessibility objects')
        nodes = {n['id']: n for n in records}
        if len(nodes) != len(records) or 'root' not in nodes:
            raise ValueError('invalid accessibility tree')
        for node in records:
            key = node['id']
            if not key.replace('_', '').isalnum() or node['role'] not in ROLES:
                raise ValueError('invalid accessibility object')
            state_words(node['states'])
            if any(k not in nodes or nodes[k]['parent'] != key for k in node['children']):
                raise ValueError('invalid accessibility children')
        visited, work = set(), ['root']
        while work:
            key = work.pop()
            if key in visited:
                raise ValueError('cyclic accessibility tree')
            visited.add(key)
            work.extend(nodes[key]['children'])
        if visited != set(nodes):
            raise ValueError('disconnected accessibility tree')
        previous, self.nodes = self.nodes, nodes
        for key, old in previous.items():
            if key not in nodes:
                self.event(old, 'StateChanged', 'defunct', 1)
                self.bus.emit_signal(None, CACHE, PREFIX + 'Cache', 'RemoveAccessible', GLib.Variant('((so))', (self.ref(key),)))
                for registration in self.registrations.pop(key, []):
                    self.bus.unregister_object(registration)
        for key, node in nodes.items():
            old = previous.get(key)
            if old is None or self.interfaces(old) != self.interfaces(node):
                for registration in self.registrations.pop(key, []):
                    self.bus.unregister_object(registration)
                self.registrations[key] = [self.bus.register_object(
                    self.path(key), INFOS[name], self.call, self.get_property, self.set_property)
                    for name in self.interfaces(node)]
            if old != node:
                self.bus.emit_signal(None, CACHE, PREFIX + 'Cache', 'AddAccessible',
                                     GLib.Variant('(((so)(so)(so)iiassusau))', (self.cache_item(node),)))
            if old is not None:
                try:
                    bounds = self.screen_rect(node['rect'])
                    if prior_bounds.get(key) != bounds:
                        self.event(node, 'BoundsChanged', value=GLib.Variant('(iiii)', bounds))
                except (ValueError, NotImplementedError):
                    pass
                if old['name'] != node['name']:
                    self.event(node, 'PropertyChange', 'accessible-name', value=GLib.Variant('s', node['name']))
                if old['children'] != node['children']:
                    for i, child in enumerate(old['children']):
                        if child not in node['children']:
                            self.event(node, 'ChildrenChanged', 'remove', i, value=GLib.Variant('(so)', self.ref(child)))
                    for i, child in enumerate(node['children']):
                        if child not in old['children']:
                            self.event(node, 'ChildrenChanged', 'add', i, value=GLib.Variant('(so)', self.ref(child)))
                if 'text' in node and old.get('text') != node['text']:
                    before, after = old.get('text', ''), node['text']
                    common = 0
                    while common < min(len(before), len(after)) and before[common] == after[common]:
                        common += 1
                    tail = 0
                    while tail < min(len(before), len(after)) - common and before[-1-tail] == after[-1-tail]:
                        tail += 1
                    removed, added = before[common:len(before)-tail], after[common:len(after)-tail]
                    if removed:
                        self.event(node, 'TextChanged', 'delete', common, len(removed), GLib.Variant('s', removed))
                    if added:
                        self.event(node, 'TextChanged', 'insert', common, len(added), GLib.Variant('s', added))
                if node.get('caret') != old.get('caret') and 'caret' in node:
                    self.event(node, 'TextCaretMoved', a=node['caret'])
                if node.get('selection') != old.get('selection'):
                    self.event(node, 'TextSelectionChanged')
                if self.selected(node) != [k for k in old['children'] if k in previous and 'selected' in previous[k]['states']]:
                    self.event(node, 'SelectionChanged')
            old_states = set(old['states']) if old else set()
            new_states = set(node['states'])
            for state in sorted(old_states ^ new_states):
                self.event(node, 'StateChanged', state, int(state in new_states))
                if state == 'active' and node['role'] in ('frame', 'internal frame', 'dialog'):
                    self.event(node, 'Activate' if state in new_states else 'Deactivate', window=True)
        if not self.embedded:
            self.embedded = True
            self.bus.call('org.a11y.atspi.Registry', ROOT, PREFIX + 'Socket', 'Embed',
                          GLib.Variant('((so))', (self.ref('root'),)), GLib.VariantType.new('((so))'),
                          Gio.DBusCallFlags.NONE, 1500, None, self.did_embed)

    def did_embed(self, connection, result):
        try:
            self.registry_parent = connection.call_finish(result).unpack()[0]
            root = self.nodes['root']
            self.bus.emit_signal(None, CACHE, PREFIX + 'Cache', 'AddAccessible',
                                 GLib.Variant('(((so)(so)(so)iiassusau))', (self.cache_item(root),)))
            self.event(root, 'PropertyChange', 'accessible-parent', value=GLib.Variant('(so)', self.registry_parent))
        except GLib.Error:
            self.loop.quit()

    def get_property(self, bus, sender, path, interface, prop):
        name = interface.removeprefix(PREFIX)
        node = self.nodes.get(self.key(path), {})
        values = {'version': 1, 'Name': node.get('name', ''), 'Description': node.get('description', ''),
                  'Parent': self.parent(node) if node else ('', NULL), 'ChildCount': len(node.get('children', [])),
                  'Locale': locale.setlocale(locale.LC_CTYPE), 'AccessibleId': node.get('id', ''), 'HelpText': '',
                  'ToolkitName': 'Kilix 95', 'ToolkitVersion': '0.2.2', 'Version': '0.2.2',
                  'AtspiVersion': '2.1', 'InterfaceVersion': 1, 'Id': self.application_id,
                  'NActions': len(node.get('actions', [])), 'CharacterCount': len(node.get('text', '')),
                  'CaretOffset': node.get('caret', 0),
                  'NSelectedChildren': len(self.selected(node)) if node else 0}
        return GLib.Variant(PROPERTIES[name][prop], values[prop])

    def set_property(self, bus, sender, path, interface, prop, value):
        if interface == PREFIX + 'Application' and prop == 'Id':
            self.application_id = value.unpack()
            return True
        return False

    def request(self, invocation, node, kind, args=(), output='b', convert=None):
        if len(self.pending) >= 64:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.LimitsExceeded', 'Too many pending accessibility actions')
            return
        serial = next(self.counter)
        timer = GLib.timeout_add(1000, self.expire, serial)
        self.pending[serial] = (invocation, output, timer, convert)
        self.channel.queue({'type': 'request', 'request': serial, 'node': node['id'],
                            'kind': kind, 'args': list(args), 'deadline': time.monotonic() + 0.9})

    def want_geometry(self):
        # Native pane geometry costs a remote-control round trip, so the
        # frontend observes it only while screen coordinates are being asked
        # for. The first screen query after an idle spell is refused until a
        # fresh observation arrives, as for any expired placement.
        now = time.monotonic()
        if now - self.geometry_wanted_sent >= 1:
            self.geometry_wanted_sent = now
            self.channel.queue({'type': 'geometry-wanted'})

    def screen_rect(self, rect):
        self.want_geometry()
        age = time.monotonic() - self.viewport_observed
        if self.viewport is None or not 0 <= age < .8:
            raise NotImplementedError()
        try:
            return self.viewport.screen_rect(rect, self.canvas_size, self.canvas_grid)
        except GeometryUnavailable:
            raise NotImplementedError() from None

    def screen_point(self, x, y):
        self.want_geometry()
        age = time.monotonic() - self.viewport_observed
        if self.viewport is None or not 0 <= age < .8:
            raise NotImplementedError()
        try:
            return self.viewport.canvas_point(x, y, self.canvas_size, self.canvas_grid)
        except GeometryUnavailable:
            raise NotImplementedError() from None

    def expire(self, serial):
        item = self.pending.pop(serial, None)
        if item:
            self.reply(item, False)
        return False

    @staticmethod
    def reply(item, accepted, value=None):
        invocation, output, timer, convert = item
        if convert is not None:
            try:
                if not accepted:
                    raise NotImplementedError()
                result = convert(value)
                invocation.return_value(GLib.Variant('(' + output + ')', result))
            except (NotImplementedError, ValueError, TypeError, KeyError, OverflowError):
                invocation.return_dbus_error('org.freedesktop.DBus.Error.NotSupported', 'Live text geometry is unavailable')
            return
        if not output and not accepted:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.Failed', 'Accessibility action was refused')
        else:
            invocation.return_value(GLib.Variant('(' + output + ')', (bool(accepted),) if output else ()))

    def read(self, fd, condition):
        try:
            for message in self.channel.receive():
                if message.get('type') == 'snapshot':
                    self.update(message)
                elif message.get('type') == 'reply':
                    item = self.pending.pop(message['request'], None)
                    if item:
                        GLib.source_remove(item[2])
                        self.reply(item, message.get('accepted') is True, message.get('value'))
        except (EOFError, OSError, ValueError, KeyError):
            self.loop.quit()
            return False
        return True

    def text_geometry(self, method, node, args, invocation):
        coordinate = args[-1]
        if coordinate not in (0, 1, 2):
            raise ValueError()
        key = node['id']
        kind = {'GetCharacterExtents': 'character_rect', 'GetRangeExtents': 'range_rect',
                'GetOffsetAtPoint': 'offset_at_point'}[method]
        query_args = args[:-1]
        origin = self.nodes.get(node['parent']) if coordinate == 2 else self.nodes['desktop']
        origin_rect = tuple(origin['rect']) if origin else None
        native = self.viewport if coordinate == 0 else None
        if coordinate == 0:
            self.screen_rect(node['rect'])  # Refuse unsupported/expired placements immediately.
        if kind == 'offset_at_point':
            if coordinate == 0:
                query_args = self.screen_point(*query_args)
            elif origin:
                query_args = (query_args[0] + origin['rect'][0], query_args[1] + origin['rect'][1])
        else:
            if any(type(n) is not int or not 0 <= n <= len(node['text']) for n in query_args):
                raise ValueError()
            if kind == 'range_rect' and query_args[1] < query_args[0]:
                raise ValueError()

        def convert(value):
            current = self.nodes.get(key)
            if (not isinstance(value, dict) or current is None or 'showing' not in current['states']
                    or value.get('node_rect') != current['rect']
                    or value.get('text_view') != current.get('text_view')
                    or value.get('canvas_size') != self.canvas_size
                    or value.get('canvas_grid') != self.canvas_grid):
                raise NotImplementedError()
            if coordinate == 0 and native != self.viewport:
                raise NotImplementedError()
            result = value['value']
            if kind == 'offset_at_point':
                if coordinate == 2:
                    current_origin = self.nodes.get(current['parent'])
                    if (tuple(current_origin['rect']) if current_origin else None) != origin_rect:
                        raise NotImplementedError()
                if type(result) is not int or not -1 <= result <= len(current['text']):
                    raise ValueError()
                if coordinate == 0:
                    self.screen_rect(current['rect'])  # The request can expire while waiting for the UI.
                return (result,)
            if (not isinstance(result, (list, tuple)) or len(result) != 4
                    or any(type(n) is not int or abs(n) > 10000000 for n in result)
                    or result[2] < 0 or result[3] < 0):
                raise ValueError()
            if coordinate == 0:
                return self.screen_rect(result)
            current_origin = self.nodes.get(current['parent']) if coordinate == 2 else self.nodes['desktop']
            x, y, width, height = result
            return (x - (current_origin['rect'][0] if current_origin else 0),
                    y - (current_origin['rect'][1] if current_origin else 0), width, height)

        self.request(invocation, node, kind, query_args,
                     'i' if kind == 'offset_at_point' else 'iiii', convert)

    def flush(self):
        try:
            if self.channel.has_message():
                self.read(self.channel.sock.fileno(), 0)
            self.channel.flush()
        except (EOFError, OSError, ValueError):
            self.loop.quit()
            return False
        return True

    def call(self, bus, sender, path, interface, method, parameters, invocation):
        name = interface.removeprefix(PREFIX)
        args = parameters.unpack()
        try:
            if name == 'Cache':
                result = ([self.cache_item(node) for node in self.nodes.values()],)
            else:
                node = self.nodes[self.key(path)]
                result = self.dispatch(name, method, node, args, invocation)
                if result is None:
                    return  # Mutation result comes from the actual UI thread.
            output = METHODS[name][method][1]
            invocation.return_value(GLib.Variant('(' + ''.join(output) + ')', result))
        except (IndexError, KeyError, TypeError, ValueError):
            invocation.return_dbus_error('org.freedesktop.DBus.Error.InvalidArgs', 'Invalid accessibility request')
        except NotImplementedError:
            invocation.return_dbus_error('org.freedesktop.DBus.Error.NotSupported', 'Accessibility operation is unavailable')

    def dispatch(self, name, method, node, args, invocation):
        if name == 'Accessible':
            if method == 'GetChildAtIndex':
                if args[0] < 0:
                    raise IndexError()
                return (self.ref(node['children'][args[0]]),)
            if method == 'GetChildren':
                return ([self.ref(k) for k in node['children']],)
            if method == 'GetIndexInParent':
                parent = self.nodes.get(node['parent'])
                return (parent['children'].index(node['id']) if parent else -1,)
            return {'GetRelationSet': ([],), 'GetRole': (ROLES[node['role']],),
                    'GetRoleName': (node['role'],), 'GetLocalizedRoleName': (node['role'],),
                    'GetState': (state_words(node['states']),),
                    'GetAttributes': ({'toolkit': 'Kilix 95'},),
                    'GetApplication': (self.ref('root'),),
                    'GetInterfaces': ([PREFIX + i for i in self.interfaces(node)],)}[method]
        if name == 'Application':
            return ('',) if method == 'GetApplicationBusAddress' else (locale.setlocale(locale.LC_CTYPE),)
        if name == 'Action':
            if method == 'GetActions':
                return ([(action, '', '') for action in node['actions']],)
            index = args[0]
            if not 0 <= index < len(node['actions']):
                raise IndexError()
            action = node['actions'][index]
            if method == 'DoAction':
                self.request(invocation, node, action)
                return None
            return (action if method in ('GetName', 'GetLocalizedName') else '',)
        if name == 'Component':
            if method == 'GrabFocus':
                self.request(invocation, node, 'focus')
                return None
            if method == 'GetSize':
                return tuple(node['rect'][2:])
            if method == 'GetLayer':
                return (7 if node['role'] in ('frame', 'dialog') else 4 if node['role'] == 'internal frame' else 3,)
            if method == 'GetMDIZOrder':
                return (0,)
            if method == 'GetAlpha':
                return (1.0,)
            if method.startswith('Set') or method.startswith('Scroll'):
                return (False,)
            coordinate = args[-1]
            if coordinate not in (0, 1, 2):
                raise ValueError()
            # Only the live native frontend establishes a screen placement.
            if coordinate == 0:
                r = self.screen_rect(node['rect'])
                if method == 'GetExtents':
                    return (r,)
                if method == 'GetPosition':
                    return tuple(r[:2])
                px, py = self.screen_point(args[0], args[1])
                origin = None
                r = list(node['rect'])
            else:
                px, py = args[:2] if len(args) >= 3 else (0, 0)
                r = list(node['rect'])
                origin = self.nodes.get(node['parent']) if coordinate == 2 else self.nodes['desktop']
                if origin:
                    r[0] -= origin['rect'][0]
                    r[1] -= origin['rect'][1]
            if method == 'GetExtents':
                return (tuple(r),)
            if method == 'GetPosition':
                return tuple(r[:2])
            contains = r[0] <= px < r[0] + r[2] and r[1] <= py < r[1] + r[3]
            if method == 'Contains':
                return (contains,)
            if method == 'GetAccessibleAtPoint':
                if not contains:
                    return (('', NULL),)
                gx = px + (origin['rect'][0] if origin else 0)
                gy = py + (origin['rect'][1] if origin else 0)
                def deepest(current):
                    for child in reversed(current['children']):
                        candidate = self.nodes[child]
                        x, y, w, h = candidate['rect']
                        if 'showing' in candidate['states'] and x <= gx < x + w and y <= gy < y + h:
                            return deepest(candidate)
                    return current['id']
                return (self.ref(deepest(node)),)
        if name == 'Text':
            text = node['text']
            if method in ('GetCharacterExtents', 'GetRangeExtents', 'GetOffsetAtPoint'):
                self.text_geometry(method, node, args, invocation)
                return None
            if method == 'GetText':
                start, end = args
                end = len(text) if end == -1 else end
                if not 0 <= start <= end <= len(text):
                    raise ValueError()
                return (text[start:end],)
            if method in ('GetStringAtOffset', 'GetTextAtOffset', 'GetTextBeforeOffset', 'GetTextAfterOffset'):
                return text_span(text, args[0], args[1],
                                 {'GetTextBeforeOffset': -1, 'GetTextAfterOffset': 1}.get(method, 0),
                                 method != 'GetStringAtOffset')
            if method == 'GetCharacterAtOffset':
                if not 0 <= args[0] < len(text):
                    raise IndexError()
                return (ord(text[args[0]]),)
            if method == 'SetCaretOffset':
                self.request(invocation, node, 'caret', args)
                return None
            selection = node.get('selection', [])
            if method == 'GetNSelections':
                return (int(bool(selection)),)
            if method == 'GetSelection':
                if args[0] != 0 or not selection:
                    raise IndexError()
                return tuple(selection)
            if method in ('AddSelection', 'SetSelection', 'RemoveSelection'):
                if method != 'AddSelection' and args[0] != 0:
                    return (False,)
                selected = args if method == 'AddSelection' else args[1:]
                if method == 'RemoveSelection':
                    selected = [node['caret'], node['caret']]
                self.request(invocation, node, 'selection', selected)
                return None
            if method in ('GetAttributes', 'GetAttributeRun'):
                return {}, 0, len(text)
            if method in ('GetDefaultAttributes', 'GetDefaultAttributeSet'):
                return ({},)
            if method == 'GetAttributeValue':
                return ('',)
            if method.startswith('Scroll'):
                return (False,)
            raise NotImplementedError()
        if name == 'EditableText':
            kind = {'SetTextContents': 'set_text', 'InsertText': 'insert_text',
                    'CopyText': 'copy_text', 'CutText': 'cut_text',
                    'DeleteText': 'delete_text', 'PasteText': 'paste_text'}[method]
            if method == 'InsertText':
                if args[2] < 0 or args[2] > len(args[1]):
                    return (False,)
                args = (args[0], args[1][:args[2]])
            self.request(invocation, node, kind, args, '' if method == 'CopyText' else 'b')
            return None
        if name == 'Selection':
            selected = self.selected(node)
            if method == 'GetSelectedChild':
                if args[0] < 0:
                    raise IndexError()
                return (self.ref(selected[args[0]]),)
            if method == 'IsChildSelected':
                return (0 <= args[0] < len(node['children']) and node['children'][args[0]] in selected,)
            if method == 'DeselectSelectedChild':
                if not 0 <= args[0] < len(selected):
                    return (False,)
                args = (node['children'].index(selected[args[0]]),)
            kind = {'SelectChild': 'select_child', 'DeselectChild': 'deselect_child',
                    'DeselectSelectedChild': 'deselect_child', 'SelectAll': 'select_all',
                    'ClearSelection': 'clear_selection'}[method]
            if kind in ('select_child', 'deselect_child'):
                if not 0 <= args[0] < len(node['children']):
                    return (False,)
                args = (args[0], node['children'][args[0]])
            self.request(invocation, node, kind, args)
            return None
        raise NotImplementedError()


def main():
    fd, parent = map(int, sys.argv[1:])
    # Install the death signal before discovery, then close the fork/exec race.
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        return 1
    if os.getppid() != parent:
        return 1
    channel = Channel(socket.socket(fileno=fd))
    service = Service(channel)
    try:
        service.loop.run()
    finally:
        channel.sock.close()
        service.bus.close_sync(None)
    return 0


if __name__ == '__main__':
    sys.exit(main())
