"""Defensive lifecycle invariants: synthetic workers, no live process signals."""
import ast
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import owned_job as jobs
import model_discovery as discovery
import workflows_offer


def load_class(file, name, **namespace):
    """Load actual UI methods without optional graphics/host dependencies."""
    tree = ast.parse((ROOT / file).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), file, 'exec'), namespace)
    return namespace[name]


# WNOWAIT polling must not reap the group leader. Escalate even if it exited
# before cancellation or during TERM grace. Reserve identity until final wait.
for exited_before in (False, True):
    events = []
    status = SimpleNamespace(si_code=os.CLD_EXITED, si_status=0)
    process = Mock(pid=43210)
    process.wait.side_effect = lambda **kw: events.append('reap') or 0
    with patch.object(jobs.subprocess, 'Popen', return_value=process) as spawn, \
         patch.object(jobs.os, 'waitid', side_effect=[status if exited_before else None, status, status]) as waitid, \
         patch.object(jobs.os, 'killpg', side_effect=lambda pid, sig: events.append(sig)) as kill, \
         patch.object(jobs.time, 'sleep', side_effect=lambda seconds: events.append('grace')):
        job = jobs.OwnedJob(['fixture'])
        assert spawn.call_args.kwargs['start_new_session'] is True
        assert job.poll() == (0 if exited_before else None)
        process.poll.assert_not_called()
        process.wait.assert_not_called()
        workflows_offer.stop(job)
        job.stop()
        assert events == [signal.SIGTERM, 'grace', signal.SIGKILL, 'reap']
        assert all(call.args[2] & os.WNOWAIT for call in waitid.call_args_list)
        assert job.poll() == 0
        process.wait.assert_called_once_with(timeout=2)

# Lost ownership must fail closed without sending any signal to a reused PID.
with patch.object(jobs.subprocess, 'Popen', return_value=Mock(pid=43210)), \
     patch.object(jobs.os, 'waitid', side_effect=ChildProcessError), \
     patch.object(jobs.os, 'killpg') as kill:
    job = jobs.OwnedJob(['fixture'])
    try:
        job.stop()
    except ChildProcessError:
        pass
    else:
        raise AssertionError('lost ownership accepted')
    kill.assert_not_called()

# A vanished group is harmless and still reaped.
with patch.object(jobs.subprocess, 'Popen', return_value=Mock(pid=43210)) as spawn, \
     patch.object(jobs.os, 'waitid', return_value=None), \
     patch.object(jobs.os, 'killpg', side_effect=ProcessLookupError), \
     patch.object(jobs.time, 'sleep') as sleep:
    jobs.OwnedJob(['fixture']).stop()
    spawn.return_value.wait.assert_called_once_with(timeout=2)
    sleep.assert_not_called()


class Window:
    def __init__(self, desk, *args, **kwargs):
        self.desk = desk
        self.widgets = []
    def client_size(self):
        return 480, 300
    def add(self, widget):
        self.widgets.append(widget)
        return widget
    def close(self):
        self.on_close()


Installer = load_class('apps/xpane.py', 'InstallerWindow',
    wm=SimpleNamespace(Window=Window), W=Mock(), storage=Mock(), tempfile=Mock(),
    OwnedJob=Mock(), os=os, subprocess=subprocess, _here=str(ROOT))
for ordinary in (False, True):
    desk = SimpleNamespace(tick_hooks=[])
    window = Installer(desk, 'fixture', 'Fixture')
    worker, log = window.proc, window.log
    worker.reset_mock(); log.reset_mock()
    assert window.on_close == window.cleanup and window._tick in desk.tick_hooks
    if ordinary:
        window.request_close()
    else:
        # Exercise the desktop's actual forced-cleanup dispatcher.
        Desk = load_class('main.py', 'Desk')
        desk.wm = SimpleNamespace(windows=[window])
        Desk._cleanup_windows(desk)
        assert desk.wm.windows == []
    window.cleanup()
    assert window._done and window.log is None
    assert window._tick not in desk.tick_hooks
    log.close.assert_called_once()
    # OwnedJob.stop itself is idempotent; all paths use it.
    worker.stop.assert_called()

# Resource cleanup is retained even when worker stopping fails.
window = Installer(SimpleNamespace(tick_hooks=[]), 'fixture', 'Fixture')
log = window.log
window.proc.stop.side_effect = RuntimeError('stop failed')
try:
    window.cleanup()
except RuntimeError:
    pass
assert window.log is None and window._tick not in window.desk.tick_hooks
assert log.close.called
window.proc.stop.side_effect = None

# Installer launch failures close the log before the window can register.
factory = Installer.__init__.__globals__['OwnedJob']
factory.side_effect = OSError('spawn failed')
log = Installer.__init__.__globals__['tempfile'].NamedTemporaryFile.return_value
log.reset_mock()
try:
    Installer(SimpleNamespace(tick_hooks=[]), 'fixture', 'Fixture')
except OSError:
    pass
else:
    raise AssertionError('spawn failure hidden')
log.close.assert_called_once()
factory.side_effect = None

Wizard = load_class('apps/modelwizard.py', 'ModelWizard',
    wm=SimpleNamespace(Window=Window), W=Mock(), Discovery=Mock(),
    backend=SimpleNamespace(read_json=lambda path: {}, state_root=lambda: Path("/unused")))
for desktop_exit in (False, True):
    desk = SimpleNamespace(tick_hooks=[])
    window = Wizard(desk)
    future = window.future
    future.reset_mock()
    future.done.return_value = False
    window.refresh(0)
    future.result.assert_not_called()
    if desktop_exit:
        desk.wm = SimpleNamespace(windows=[window])
        Desk._cleanup_windows(desk)
    else:
        window.close()
    window.cleanup()
    window.refresh(0)
    assert window._closed and window.future is None
    assert window.refresh not in desk.tick_hooks
    future.close.assert_called_once()
    future.result.assert_not_called()  # No page handling once cancelled.

# Discovery output handling and cleanup, including invalid results and spawn failure.
for payload, code, expected in [(b'[{"id":"fixture"}]', 0, True), (b'invalid', 0, False), (b'', 1, False)]:
    output = io.BytesIO(payload)
    process = Mock(returncode=code)
    process.poll.return_value = code
    with tempfile.TemporaryDirectory() as directory, \
         patch.object(discovery.tempfile, 'TemporaryFile', return_value=output), \
         patch.object(discovery, 'OwnedJob', return_value=process):
        task = discovery.Discovery(directory)
        try:
            result = task.result()
            assert expected and result == [{'id': 'fixture'}]
        except (ValueError, RuntimeError):
            assert not expected
        assert output.closed
        process.stop.assert_called_once()
output = io.BytesIO()
with tempfile.TemporaryDirectory() as directory, \
         patch.object(discovery.tempfile, 'TemporaryFile', return_value=output), \
     patch.object(discovery, 'OwnedJob', side_effect=OSError('spawn failed')):
    try:
        discovery.Discovery(directory)
    except OSError:
        pass
    assert output.closed

# Worker entry point uses the selected backend and separates notices from JSON.
backend = Mock()
def pages(**kwargs):
    assert kwargs == {'ensure_sizer': True}
    print('fixture notice')
    return [{'id': 'fixture'}]
backend.pages.side_effect = pages
with patch.dict(sys.modules, model_wizard=backend), \
     patch.object(sys, 'stdout', io.StringIO()) as out, \
     patch.object(sys, 'stderr', io.StringIO()) as err:
    discovery.discover()
    assert json.loads(out.getvalue()) == [{'id': 'fixture'}]
    assert 'fixture notice' in err.getvalue()

# Terminal cleanup still releases its descriptor if group stopping raises.
Terminal = load_class('apps/licenseterminal.py', 'LicenceTerminal',
                      wm=SimpleNamespace(Window=Window), os=Mock())
window = Terminal.__new__(Terminal)
window.desk = SimpleNamespace(tick_hooks=[window.tick], remove_fd=Mock())
window.process = Mock()
window.finished = True
window.master = 9876
with patch.object(workflows_offer, 'stop', side_effect=RuntimeError('stop failed')):
    try:
        window.cleanup()
    except RuntimeError:
        pass
assert window.master is None and not window.desk.tick_hooks
window.desk.remove_fd.assert_called_once_with(9876)
Terminal.cleanup.__globals__['os'].close.assert_called_once_with(9876)
print('owned lifecycle: OK (mock workers only)')
