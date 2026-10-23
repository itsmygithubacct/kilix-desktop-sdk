"""Screen bounds/hit testing use current native placements and expire safely."""
import copy
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import GLib
except ImportError:
    GLib = None

if GLib is not None:
    import accessibility_service as bridge
    from kilix_sdk.geometry import PaneGeometry


class Bus:
    def __init__(self): self.events = []
    def register_object(self, *args): return len(args)
    def unregister_object(self, *args): pass
    def emit_signal(self, destination, path, interface, name, body):
        self.events.append((path, name, body.unpack()))
    def call(self, *args): pass


@unittest.skipUnless(GLib is not None, 'Run with system python3-gi for GIO protocol checks')
class GeometryServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = bridge.Service.__new__(bridge.Service)
        self.service.bus = Bus()
        self.service.name = ':1.9'
        self.service.nodes = {}
        self.service.registrations = {}
        self.service.registry_parent = ('', bridge.NULL)
        self.service.embedded = True
        self.service.viewport = None
        self.service.viewport_observed = 0
        self.service.canvas_size = self.service.canvas_grid = None
        self.wanted = []
        self.service.channel = type('Channel', (), {'queue': staticmethod(self.wanted.append)})()
        self.service.geometry_wanted_sent = float('-inf')
        self.data = dict(version=1, pane_id=9, render_rect=[20, 60, 820, 660],
                         grid=[80, 30], cell_size=[10, 20], framebuffer_size=[1600, 1200],
                         window_size=[800, 600], screen_origin=[-800, 25],
                         screen_coordinates_supported=True, visible=True, focused=True)
        self.nodes = [dict(id='root', parent=None, name='Desktop app', role='application',
                           rect=[0, 0, 800, 600], states=['visible'], children=['desktop'], actions=[]),
                      dict(id='desktop', parent='root', name='Desktop', role='frame',
                           rect=[0, 0, 800, 600], states=['visible'], children=['button'], actions=[]),
                      dict(id='button', parent='desktop', name='Save', role='button',
                           rect=[10, 20, 100, 30], states=['visible', 'showing'], children=[], actions=[])]
        self.publish()

    def publish(self):
        self.service.update({'nodes': copy.deepcopy(self.nodes), 'canvas_size': [800, 600],
                             'canvas_grid': [80, 30],
                             'viewport': {'observed': time.monotonic(), 'geometry': dict(self.data)}})

    def call(self, method, args, key='button'):
        return self.service.dispatch('Component', method, self.service.nodes[key], args, None)

    def test_screen_queries_ask_the_frontend_to_observe_geometry_at_most_once_a_second(self):
        self.call('GetExtents', (0,))
        self.call('GetPosition', (0,))
        self.call('Contains', (-780, 70, 0))
        self.assertEqual(self.wanted, [{'type': 'geometry-wanted'}])
        self.call('GetExtents', (1,))  # window-relative coordinates need no screen geometry
        self.assertEqual(len(self.wanted), 1)

    def test_physical_bounds_and_hit_testing_share_the_native_transform(self):
        self.assertEqual(self.call('GetExtents', (0,)), ((-785, 65, 50, 15),))
        self.assertEqual(self.call('GetPosition', (0,)), (-785, 65))
        self.assertEqual(self.call('Contains', (-780, 70, 0)), (True,))
        self.assertEqual(self.call('Contains', (-730, 70, 0)), (False,))
        self.assertEqual(self.call('GetAccessibleAtPoint', (-780, 70, 0), 'desktop'),
                         (self.service.ref('button'),))
        self.assertEqual(self.call('GetAccessibleAtPoint', (-900, 70, 0), 'desktop'),
                         (('', bridge.NULL),))

    def test_a_moved_native_window_updates_bounds_and_emits_real_screen_rectangles(self):
        self.data['screen_origin'] = [-700, 40]
        self.publish()
        self.assertEqual(self.call('GetExtents', (0,)), ((-685, 80, 50, 15),))
        bounds = [(path, data[3]) for path, name, data in self.service.bus.events if name == 'BoundsChanged']
        self.assertIn((self.service.path('button'), (-685, 80, 50, 15)), bounds)

    def test_expired_hidden_or_resizing_sources_cannot_return_plausible_stale_screen_bounds(self):
        self.service.viewport_observed = time.monotonic() - 1
        with self.assertRaises(NotImplementedError): self.call('GetExtents', (0,))
        self.data['visible'] = False
        self.publish()
        with self.assertRaises(NotImplementedError): self.call('GetExtents', (0,))
        self.data['visible'] = True
        self.publish()
        self.service.canvas_grid = [79, 30]
        with self.assertRaises(NotImplementedError): self.call('GetExtents', (0,))

    def test_window_and_parent_coordinates_remain_local_and_invalid_coordinate_types_fail(self):
        self.assertEqual(self.call('GetExtents', (1,)), ((10, 20, 100, 30),))
        self.assertEqual(self.call('GetExtents', (2,)), ((10, 20, 100, 30),))
        with self.assertRaises(ValueError): self.call('GetExtents', (3,))


if __name__ == '__main__': unittest.main()
