"""Sampling, cancellation, scenes, private persistence and real composition."""
from concurrent.futures import Future
from pathlib import Path
import tempfile
from unittest import mock

import harness as H
import paperclips as P
from apps.displayprops import DisplayProperties


class Executor:
    def __init__(self, **_kw):
        self.calls = []
    def submit(self, sampler, cancel):
        future = Future()
        self.calls.append((sampler, cancel, future))
        return future
    def shutdown(self, **kw):
        self.stopped = kw


assert [P.scene_level(x) for x in (0, 9.9, 10, 29, 30, 60, 89.9, 90, 99.9, 100)] == [0, 5, 10, 20, 30, 60, 60, 90, 90, 100]
assert all(P.interval(x) == 300 for x in (None, '60', True, -1, 0, 1e12))
with tempfile.TemporaryDirectory() as root:
    root = Path(root)
    def fixture(cpu, swap_free, pages):
        (root/'stat').write_text('cpu ' + cpu + '\n')
        (root/'meminfo').write_text(f'SwapTotal: 1048576 kB\nSwapFree: {swap_free} kB\n')
        (root/'vmstat').write_text(f'pswpin {pages}\npswpout 0\n')
    fixture('100 0 0 900 0 0 0 0 100 0', 1048576, 0)
    cancel = mock.Mock()
    cancel.is_set.return_value = False
    cancel.wait.side_effect = lambda _: fixture('190 0 0 910 0 0 0 0 190 0', 300000, 0)
    # Guest time does not double count CPU. High occupancy heats the machine.
    percent, hot = P.measure(cancel, root, mock.Mock(side_effect=[0, 1]))
    assert percent == 90 and hot
    fixture('100 0 0 900', 1048576, 0)
    cancel.wait.side_effect = lambda _: fixture('100 0 0 1000', 1048576, 0)
    assert P.measure(cancel, root, mock.Mock(side_effect=[0, 1])) == (0, False)
    cancel.wait.side_effect = None
    cancel.wait.return_value = True
    assert P.measure(cancel, root) is None

with H.desktop_dir(), mock.patch.object(P, 'ThreadPoolExecutor', Executor):
    desk = H.make_desk(size=(640, 480))
    p = desk.paperclips
    assert not p.enabled()
    assert desk.shell.state["wall_image"].endswith("plebian-os.png")
    desk.shell.state["paperclips_enabled"] = True
    now = [0]
    p.clock = lambda: now[0]
    desk.frontend_focused = False
    p.tick()
    assert p.executor is None
    desk.frontend_focused = True
    p.tick()
    assert len(p.executor.calls) == 1
    p.executor.calls[-1][2].set_result((90, True))
    p.tick()
    assert p.level == 90 and p.hot
    assert p.wallpaper().endswith('kilix-paperclips-90.png')
    for n in (1, 30, 299):
        now[0] = n
        p.tick()
    assert len(p.executor.calls) == 1
    desk.frontend_focused = False
    now[0] = 900
    frame = p.frame
    p.tick()
    assert len(p.executor.calls) == 1 and p.frame == frame
    desk.frontend_focused = True
    p.tick()
    assert len(p.executor.calls) == 2  # One overdue sample, no catch-up burst.
    cancel, future = p.executor.calls[-1][1:]
    desk.frontend_focused = False
    p.tick()
    assert cancel.is_set()
    future.set_result((100, False))
    p.tick()
    assert p.level == 90 and p.hot  # Lost-focus result cannot replace the scene.
    desk.frontend_focused = True
    now[0] = 1200
    p.tick()
    p.executor.calls[-1][2].set_result((100, False))
    p.tick()
    assert p.level == 100 and not p.hot
    desk.shell.state['paperclips_animate'] = False
    p.tick()
    frame = p.frame
    now[0] += 2
    p.tick()
    assert p.frame == frame
    # Display choices persist; selecting a custom image disables the scenes.
    win = DisplayProperties(desk)
    win.paperclip_interval.index = 2
    win._apply()
    assert desk.shell.state_store.load_dict()['paperclips_interval'] == 600
    assert all(widget.y + widget.h <= win.client_size()[1] for widget in win.panels[0])
    win.bg_image.set('/missing/custom-wallpaper.png')
    win._apply()
    assert desk.shell.state['wall_custom'] and not desk.shell.state['paperclips_enabled']
    assert p.wallpaper() is None
    # Re-enabling the checkbox intentionally selects the bundled firekitten.
    win.paperclips.checked = True
    win._apply()
    assert not desk.shell.state['wall_custom'] and p.enabled()
    for level in P.LEVELS:
        p.level = level
        assert Path(p.wallpaper()).is_file()
        desk.shell._wall = None
        desk.dirty = True
        desk.render()
        assert desk.fb.size == (640, 480)
    assert len(p.frames) == 4 and p.frames[0].mode == 'RGBA'
    p.close()
    calls = len(p.executor.calls)
    now[0] += 3600
    p.tick()
    assert len(p.executor.calls) == calls and p.executor.stopped['cancel_futures']
print('ok')
