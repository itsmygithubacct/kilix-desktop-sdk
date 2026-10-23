"""Pane geometry is observed only while wanted, and a refusal backs off."""
import sys
import types

import harness as H          # noqa: sets up sys.path for the imports below
import accessibility


class Stop:
    def __init__(self, limit):
        self.delays, self.limit = [], limit

    def is_set(self):
        return len(self.delays) >= self.limit

    def wait(self, delay):
        self.delays.append(delay)
        return self.is_set()


class Wake:
    def __init__(self, stop, limit):
        self.stop, self.limit, self.waits = stop, limit, 0

    def clear(self):
        pass

    def wait(self, _timeout):
        self.waits += 1
        if self.waits >= self.limit:
            self.stop.delays.extend([None] * self.stop.limit)
        return False


def observe(answers, wanted=True):
    controller = object.__new__(accessibility.Controller)
    controller._geometry = None
    controller._geometry_stop = Stop(len(answers) or 1)
    controller._geometry_wake = Wake(controller._geometry_stop, 5)
    controller._geometry_wanted_until = float('inf') if wanted else 0.0
    replies = iter(answers)
    calls = []

    def current(timeout):
        calls.append(timeout)
        answer = next(replies)
        if answer is None:
            raise RuntimeError('get-pane-geometry is not authorised')
        return answer, None

    fake = types.ModuleType('kilix_sdk.geometry')
    fake.current = current
    saved = sys.modules.get('kilix_sdk.geometry')
    sys.modules['kilix_sdk.geometry'] = fake
    try:
        controller._observe_geometry()
    finally:
        if saved is None:
            del sys.modules['kilix_sdk.geometry']
        else:
            sys.modules['kilix_sdk.geometry'] = saved
    controller.calls = calls
    return controller, controller._geometry_stop.delays


controller, delays = observe([None] * 10)
assert delays == [.5, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0, 30.0], delays
assert controller._geometry is None

controller, delays = observe([None, None, {'pane': 1}, None])
assert delays == [.5, 1.0, .25, .5], delays

# Idle: no screen coordinates requested, so no remote-control query at all.
controller, delays = observe([], wanted=False)
assert controller.calls == [] and controller._geometry_wake.waits == 5, controller.calls

# A geometry-wanted message from the service starts observation.
controller = object.__new__(accessibility.Controller)
controller._geometry_wanted_until = 0.0
controller._geometry_wake = accessibility.threading.Event()
controller.channel = types.SimpleNamespace(receive=lambda: [{'type': 'geometry-wanted'}])
controller.closed = False
controller.publish = lambda: None
controller.read()
assert controller._geometry_wake.is_set()
assert controller._geometry_wanted_until > accessibility.time.monotonic() + 25

print('Geometry observation checks passed.')
