"""Typed AT-SPI text RPCs through the real helper/UI socket transport."""
import itertools
import math
import socket
import threading
import time
from types import SimpleNamespace
import unittest

import harness as H
import apps
from accessibility import Controller, Tree
from accessibility_protocol import Channel, PREFIX

try:
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import GLib
except ImportError:
    GLib = None

if GLib is not None:
    import accessibility_service as bridge


class Bus:
    def register_object(self, *args): return len(args)
    def unregister_object(self, *args): pass
    def emit_signal(self, *args): pass
    def call(self, *args): pass


class Invocation:
    def __init__(self): self.value = self.error = None
    def return_value(self, value): self.value = value
    def return_dbus_error(self, name, message): self.error = name


@unittest.skipUnless(GLib is not None, 'Run with system python3-gi for GIO protocol checks')
class TextServiceTests(unittest.TestCase):
    def setUp(self):
        self.desk = H.make_desk(size=(800, 600))
        apps.open(self.desk, 'notepad', None)
        self.win = H.find_window(self.desk, 'Notepad')
        self.ta = self.win.ta
        self.ta.set_text('café 日本語\nsecond line\n')
        self.desk.term = SimpleNamespace(cols=80, rows=30)
        self.desk.frontend_focused = True
        parent, child = socket.socketpair()
        self.controller = Controller.__new__(Controller)
        self.controller.desk, self.controller.tree = self.desk, Tree(self.desk)
        self.controller.channel = Channel(parent)
        self.controller.closed, self.controller.last = False, None
        self.controller._geometry_wake = threading.Event()
        self.controller._geometry_wanted_until = 0.0
        self.data = dict(version=1, pane_id=9, render_rect=[20, 60, 820, 660],
                         grid=[80, 30], cell_size=[10, 20], framebuffer_size=[1600, 1200],
                         window_size=[800, 600], screen_origin=[-800, 25],
                         screen_coordinates_supported=True, visible=True, focused=True)
        self.service = bridge.Service.__new__(bridge.Service)
        self.service.bus, self.service.name = Bus(), ':1.9'
        self.service.nodes, self.service.registrations = {}, {}
        self.service.registry_parent, self.service.embedded = ('', bridge.NULL), True
        self.service.viewport, self.service.viewport_observed = None, 0
        self.service.geometry_wanted_sent = float('-inf')
        self.service.canvas_size = self.service.canvas_grid = None
        self.service.pending, self.service.counter = {}, itertools.count(1)
        self.service.channel = Channel(child)
        self.service.loop = SimpleNamespace(quit=lambda: self.fail('Unexpected transport closure'))
        self.publish()
        self.key = self.controller.tree.identity(self.ta)

    def tearDown(self):
        for item in self.service.pending.values(): GLib.source_remove(item[2])
        self.service.channel.sock.close()
        self.controller.channel.sock.close()

    def publish(self):
        self.controller._geometry = (time.monotonic(), dict(self.data))
        self.controller.publish()
        self.service.read(self.service.channel.sock.fileno(), 0)

    def queue(self, method, args):
        invocation = Invocation()
        signature = ''.join(bridge.METHODS['Text'][method][0])
        self.service.call(None, ':1.10', self.service.path(self.key), PREFIX + 'Text', method,
                          GLib.Variant('(' + signature + ')', args), invocation)
        return invocation

    def finish(self, invocation):
        self.controller.read()
        self.service.read(self.service.channel.sock.fileno(), 0)
        self.assertTrue(invocation.value is not None or invocation.error is not None)
        return invocation

    def call(self, method, args): return self.finish(self.queue(method, args))

    def value(self, method, args):
        invocation = self.call(method, args)
        self.assertIsNone(invocation.error)
        return invocation.value.unpack()

    def unsupported(self, invocation):
        self.finish(invocation)
        self.assertEqual(invocation.error, 'org.freedesktop.DBus.Error.NotSupported')
        self.assertIsNone(invocation.value)

    def test_screen_rectangles_use_real_typed_replies_and_negative_fractional_placement(self):
        pending = self.queue('GetCharacterExtents', (5, 0))
        self.assertIsNone(pending.value)  # The helper cannot measure a pixel widget by itself.
        self.finish(pending)
        self.assertEqual(pending.value.get_type_string(), '(iiii)')
        local = self.value('GetCharacterExtents', (5, 1))
        x, y, w, h = local
        expected = (math.floor(-790 + x / 2), math.floor(55 + y / 2),
                    math.ceil(-790 + (x + w) / 2) - math.floor(-790 + x / 2),
                    math.ceil(55 + (y + h) / 2) - math.floor(55 + y / 2))
        self.assertEqual(pending.value.unpack(), expected)
        point = (expected[0] + max(1, expected[2] // 2), expected[1] + expected[3] // 2, 0)
        result = self.call('GetOffsetAtPoint', point)
        self.assertEqual(result.value.get_type_string(), '(i)')
        self.assertEqual(result.value.unpack(), (5,))

    def test_window_parent_unicode_range_and_empty_caret(self):
        x, y, w, h = self.value('GetCharacterExtents', (3, 1))
        parent = self.service.nodes[self.service.nodes[self.key]['parent']]['rect']
        self.assertEqual(self.value('GetCharacterExtents', (3, 2)), (x-parent[0], y-parent[1], w, h))
        self.assertEqual(self.value('GetOffsetAtPoint', (x + w // 2, y + h // 2, 1)), (3,))
        self.assertEqual(self.value('GetOffsetAtPoint', (x-parent[0] + w // 2, y-parent[1] + h // 2, 2)), (3,))
        self.assertEqual(self.value('GetRangeExtents', (0, 9, 1))[3], self.ta.LH)
        self.assertEqual(self.value('GetRangeExtents', (0, 10, 1))[3], 2*self.ta.LH)
        self.assertEqual(self.value('GetRangeExtents', (3, 3, 1))[2], 0)
        self.assertEqual(self.value('GetCharacterExtents', (len(self.ta.text()), 1))[2], 0)

    def test_scroll_and_visible_point_clipping(self):
        self.ta.sb.pos, self.ta.hx = 1, 10
        self.publish()
        x, y, w, h = self.value('GetCharacterExtents', (11, 1))
        self.assertEqual(self.value('GetOffsetAtPoint', (x+w//2, y+h//2, 1)), (11,))
        vx, vy, width, height = self.ta.text_viewport()
        ox, oy = self.win.client_origin()
        for point in ((ox+vx-1, oy+vy+2), (ox+vx+width, oy+vy+2), (ox+vx+2, oy+vy+height)):
            self.assertEqual(self.value('GetOffsetAtPoint', (*point, 1)), (-1,))

    def test_invalid_offsets_and_coordinate_types_are_invalid_args(self):
        for method, args in (('GetCharacterExtents', (-1, 1)), ('GetCharacterExtents', (100, 1)),
                             ('GetCharacterExtents', (0, 3)), ('GetRangeExtents', (7, 3, 1))):
            result = self.queue(method, args)
            self.assertEqual(result.error, 'org.freedesktop.DBus.Error.InvalidArgs')
        self.assertFalse(self.service.pending)

    def test_closed_or_hidden_controls_are_refused_by_actual_ui(self):
        pending = self.queue('GetCharacterExtents', (0, 1))
        self.win.minimized = True
        self.unsupported(pending)
        self.win.minimized = False
        self.publish()
        pending = self.queue('GetCharacterExtents', (0, 1))
        self.win.modified = False
        self.win.request_close()
        self.unsupported(pending)

    def test_native_move_while_waiting_cannot_transform_an_old_screen_query(self):
        pending = self.queue('GetCharacterExtents', (0, 0))
        self.data['screen_origin'] = [-600, 50]
        self.publish()
        self.unsupported(pending)

    def test_parent_move_while_waiting_refuses_a_point_in_the_old_parent_coordinates(self):
        x, y, w, h = self.value('GetCharacterExtents', (0, 2))
        pending = self.queue('GetOffsetAtPoint', (x+w//2, y+h//2, 2))
        self.win.x += 40
        self.unsupported(pending)

    def test_read_only_text_is_measured_without_mutating_it(self):
        self.ta.enabled = False
        self.publish()
        before = self.ta.text(), self.ta.cr, self.ta.cc
        self.assertEqual(len(self.value('GetCharacterExtents', (3, 1))), 4)
        self.assertEqual(before, (self.ta.text(), self.ta.cr, self.ta.cc))

    def test_expiry_grid_mismatch_and_hidden_native_pane_refuse_screen_geometry(self):
        for field, value in (('visible', False), ('grid', [79, 30])):
            old = self.data[field]
            self.data[field] = value
            self.publish()
            result = self.queue('GetCharacterExtents', (0, 0))
            self.assertEqual(result.error, 'org.freedesktop.DBus.Error.NotSupported')
            self.data[field] = old
        self.publish()
        self.service.viewport_observed = time.monotonic()-1
        result = self.queue('GetOffsetAtPoint', (0, 0, 0))
        self.assertEqual(result.error, 'org.freedesktop.DBus.Error.NotSupported')

    def test_layout_changes_between_measurement_and_snapshot_refuse_stale_replies(self):
        # Inject a UI change after measuring, before its snapshot/reply is sent.
        real_query = self.controller.tree.query
        for change in (lambda: self.ta.set_text('different text'),
                       lambda: setattr(self.ta, 'hx', self.ta.hx+5),
                       lambda: setattr(self.win, 'x', self.win.x+10)):
            self.publish()
            pending = self.queue('GetCharacterExtents', (0, 1))
            def query(*args):
                value = real_query(*args)
                change()
                return value
            self.controller.tree.query = query
            self.unsupported(pending)
            self.controller.tree.query = real_query

    def test_expired_pending_query_returns_a_typed_error_and_ignores_late_reply(self):
        pending = self.queue('GetCharacterExtents', (0, 1))
        serial, item = next(iter(self.service.pending.items()))
        GLib.source_remove(item[2])
        self.service.expire(serial)
        self.assertEqual(pending.error, 'org.freedesktop.DBus.Error.NotSupported')
        self.finish(pending)
        self.assertIsNone(pending.value)
        self.assertFalse(self.service.pending)


if __name__ == '__main__': unittest.main()
