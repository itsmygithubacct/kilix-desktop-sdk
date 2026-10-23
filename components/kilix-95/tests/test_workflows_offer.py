"""Workflow opt-in, verified setup, update repair and probe ownership; no downloads."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock
import harness as H
import workflows_offer as W

READY = {'schema': W.SCHEMA, 'status': 'ready', 'ready': True}
MISSING = {'schema': W.SCHEMA, 'status': 'not-ready', 'ready': False}


def finish_probe(offer, report, code):
    stream = tempfile.TemporaryFile()
    stream.write(json.dumps(report).encode())
    stream.flush()
    process = mock.Mock()
    process.poll.return_value = code
    offer.probe = (process, stream, W.time.monotonic(), ['/fixture/kilix', 'app', 'run', 'kilix-needle', '--'])
    offer.finish_probe()


with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_WORKFLOWS_OFFER': '1'}):
    desk = H.make_desk()
    offer = W.controller(desk)
    with mock.patch('workflows_offer.subprocess.Popen') as start:
        offer.startup()
        assert H.find_window(desk, 'WorkflowsOffer')
        assert offer.state['answer'] is None and not offer.ready
        start.assert_not_called()  # Opening an offer is not consent to install.
    window = H.find_window(desk, 'WorkflowsOffer')
    window.close()
    offer.decline()
    later = W.Controller(desk)
    with mock.patch.object(later, 'enable') as enable:
        later.startup()
        enable.assert_not_called()
    assert later.state['answer'] == 'no'
    later.close()
    # Changing the choice is possible through the persistent menu, and already
    # verified models never open an acquisition terminal.
    with mock.patch.object(offer, 'begin_setup') as setup:
        finish_probe(offer, READY, 0)
        setup.assert_not_called()
    assert offer.state['answer'] == 'yes' and offer.ready
    later = W.Controller(desk)
    with mock.patch.object(later, 'enable') as enable:
        later.startup()
        enable.assert_called_once()
    later.close()
    # A later selected stack with missing models uses its pinned installer.
    offer.ready = False
    with mock.patch.object(desk.shell, '_tab', return_value=True) as tab:
        finish_probe(offer, MISSING, 1)
        argv, title, cwd = tab.call_args.args
        assert argv[-5:] == ['/fixture/kilix', 'app', 'run', 'kilix-needle', '--']
        assert title == 'Enable Kilix Workflows' and offer.job
        result = Path(offer.job[1])
        result.write_text(json.dumps({'exit_code': 1, 'report': None}))
        offer.tick(0)
        assert offer.job is None and not offer.ready
        assert 'cancelled or failed' in offer.status
        finish_probe(offer, MISSING, 1)
        Path(offer.job[1]).write_text(json.dumps({'exit_code': 0, 'report': READY}))
        offer.tick(0)
        assert offer.ready and offer.state['answer'] == 'yes'
    offer.close()

with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_WORKFLOWS_OFFER': '0'}):
    desk = H.make_desk()
    offer = W.controller(desk)
    with mock.patch.object(offer, 'open') as opened:
        offer.startup()
        opened.assert_not_called()
    # Failed or obsolete CLI output cannot mark readiness or start an installer.
    for report, code in [({}, 0), (READY, 1), (MISSING, 0), ({**READY, 'ready': 1}, 0)]:
        with mock.patch.object(offer, 'begin_setup') as setup:
            finish_probe(offer, report, code)
            assert offer.state['answer'] is None and not offer.ready
            setup.assert_not_called()
    # Setup exit0 alone is insufficient; state writes also must succeed.
    offer.finish_setup({'exit_code': 0, 'report': None})
    assert not offer.ready and offer.state['answer'] is None
    with mock.patch.object(offer.store, 'save_dict', side_effect=OSError('disk full')):
        try:
            offer.finish_setup({'exit_code': 0, 'report': READY})
        except OSError:
            pass
        else:
            raise AssertionError('failed state persistence was accepted')
        assert offer.state['answer'] is None and not offer.ready
    with mock.patch.object(desk.shell, '_tab', return_value=False):
        finish_probe(offer, MISSING, 1)
        assert offer.job is None and not offer.ready
    offer.close()

# Offers queue behind voice/dictation, and startup checks never run before them.
with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_WORKFLOWS_OFFER': '1'}):
    desk = H.make_desk()
    desk.dictation_offer = mock.Mock(pending=True, job=None)
    offer = W.controller(desk)
    with mock.patch.object(offer, 'open') as opened:
        offer.startup()
        opened.assert_not_called()
        assert offer.pending == 'offer'
        desk.dictation_offer.pending = False
        offer.tick(0)
        opened.assert_called_once()
    offer.close()

# Exact source argv, background checks, timeout cleanup and duplicate protection.
with H.desktop_dir():
    desk = H.make_desk()
    offer = W.controller(desk)
    with mock.patch.object(desk.shell, 'kilix_workflows_target', return_value=['/fixture/a b/kilix', 'app', 'run', 'kilix-needle', '--']), \
         mock.patch('workflows_offer.subprocess.Popen') as spawn, \
         mock.patch('workflows_offer.stop') as stop:
        spawn.return_value.poll.return_value = None
        offer.enable()
        assert spawn.call_args.args[0] == ['/fixture/a b/kilix', 'app', 'run', 'kilix-needle', '--', 'workflows', 'status', '--json']
        assert spawn.call_args.kwargs['start_new_session'] is True
        try:
            offer.enable()
        except ValueError:
            pass
        else:
            raise AssertionError('duplicate setup admitted')
        try:
            offer.decline()
        except ValueError:
            pass
        else:
            raise AssertionError('pending acquisition choice changed')
        with mock.patch('workflows_offer.time.monotonic', return_value=offer.probe[2] + W.CHECK_TIMEOUT + 1):
            offer.tick(0)
        stop.assert_called_once_with(spawn.return_value)
        assert offer.probe is None and not offer.ready
    offer.close()

# The terminal helper invokes only setup, then independently checks status.
with tempfile.TemporaryDirectory() as folder:
    target = [sys.executable, str(Path(folder) / 'fake.py')]
    result = str(Path(folder) / 'result.json')
    script = Path(target[-1])
    script.write_text("import sys,json\nassert sys.argv[1] == 'workflows'\nif sys.argv[2] == 'status': print(json.dumps(" + repr(READY) + "))\n")
    assert W.prepare(result, target) == 0
    assert json.loads(Path(result).read_text())['report'] == READY
    script.write_text("import sys,json\nif sys.argv[2] == 'status':\n print(json.dumps(" + repr(MISSING) + "));sys.exit(1)\n")
    assert W.prepare(result, target) == 1
    assert json.loads(Path(result).read_text())['report'] is None
    with mock.patch('workflows_offer.subprocess.call', return_value=1), \
         mock.patch('workflows_offer.subprocess.Popen') as probe:
        assert W.prepare(result, target) == 1
        probe.assert_not_called()

# The pinned host is required; unrelated PATH entries cannot substitute.
with mock.patch('shell.os.path.isfile', return_value=False), mock.patch('shell.shutil.which') as lookup:
    import shell
    assert shell.Shell.kilix_workflows_target() is None
    lookup.assert_not_called()
assert W.read_status(b'host source notice\n' + json.dumps(READY).encode(), 0) == READY
try:
    W.read_status(b'x' * (W.MAX_OUTPUT + 1), 0)
except ValueError:
    pass
else:
    raise AssertionError('oversized status accepted')
print('ok')

# An unresolved or live setup stays guarded after its deadline; a proven exit
# without a receipt is retryable. Never kill a separately visible terminal.
with H.desktop_dir():
    desk = H.make_desk()
    offer = W.controller(desk)
    with mock.patch.object(desk.shell, '_tab', return_value=True):
        offer.begin_setup(['/fixture/kilix'])
    directory, result, started = offer.job
    with mock.patch('workflows_offer.time.monotonic', return_value=started + W.SETUP_TIMEOUT + 1):
        offer.tick(0)
        assert offer.job and Path(directory.name).exists()
    Path(result).with_name('worker.json').write_text(json.dumps({'pid': os.getpid(), 'start': W.process_stamp(os.getpid())}))
    with mock.patch('workflows_offer.time.monotonic', return_value=started + W.SETUP_TIMEOUT + 1):
        offer.tick(0)
        assert offer.job
    with mock.patch('workflows_offer.process_stamp', return_value=None):
        offer.tick(0)
        assert offer.job  # unreadable proc metadata is not proof of exit
    with mock.patch('workflows_offer.process_stamp', return_value=False):
        offer.tick(0)
        assert offer.job is None
    assert 'closed before finishing' in offer.status
    offer.close()

# Post-setup check overflow is refused while its owned process is still running.
with tempfile.TemporaryDirectory() as folder:
    script = Path(folder) / 'overflow.py'
    script.write_text("import sys,time\nsys.stdout.write('x'*70000);sys.stdout.flush();time.sleep(30)\n")
    started = W.time.monotonic()
    try:
        W.checked_status([sys.executable, str(script)])
    except ValueError as error:
        assert 'output limit' in str(error)
    else:
        raise AssertionError('postcheck overflow was accepted')
    assert W.time.monotonic() - started < 5
