"""The embedded terminal is a real PTY; Yes/No input stays on the desktop."""
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

from types import SimpleNamespace
from unittest import mock
import harness as H
from apps.licenseterminal import open_window


def until(predicate, window, seconds=4):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        window.pump()
        window.tick(0)
        time.sleep(.01)
    assert predicate(), window.output


with H.desktop_dir() as temporary:
    desk = H.make_desk()
    script = """
import os, sys
print('TTY', sys.stdin.isatty(), sys.stdout.isatty(), flush=True)
with open('/dev/tty', 'rb', buffering=0) as terminal:
    assert os.tcgetpgrp(terminal.fileno()) == os.getpgrp() == os.getpid()
print('CONTROLLING TTY', flush=True)
a = input('Accept Apache 2.0 for model1, model2? [y/N] ')
print('ANSWER=' + a, flush=True)
"""
    log_path = Path(temporary) / 'transcript.log'
    window = open_window(desk, [sys.executable, '-c', script], log_path=log_path)
    until(lambda: window.yes.enabled, window)
    assert 'TTY True True' in window.output
    assert 'CONTROLLING TTY' in window.output
    assert window in desk.wm.windows
    preview = os.environ.get('LICENSE_PREVIEW')
    if preview: window.render().save(preview)
    window.yes.cb()
    assert not window.yes.enabled
    until(lambda: window.finished, window)
    assert 'ANSWER=y' in window.output and window.process.returncode == 0
    window.close()
    assert window.master is None and window.tick not in desk.tick_hooks
    assert 'ANSWER=y' in log_path.read_text()
    assert log_path.stat().st_mode & 0o777 == 0o600

    window = open_window(desk, [sys.executable, '-c',
        "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(60)"])
    until(lambda: 'ready' in window.output, window)
    window.close()
    assert window.process.poll() is not None
    assert window.master is None

    window = open_window(desk, [sys.executable, '-c', "print('worker survived')"],
                         log_path=Path(temporary) / 'unwritable.log')
    with patch.object(window.log, 'write', side_effect=OSError('disk full')):
        until(lambda: window.finished, window)
    assert 'worker survived' in window.output
    assert 'Could not save diagnostic transcript: disk full' in window.output
    assert window.log is None
    window.close()

print('embedded licence terminal: OK')

for failure in (None, KeyboardInterrupt(), SystemExit(0), RuntimeError('loop failed')):
    with H.desktop_dir():
        desk = H.make_desk()
        window = open_window(desk, [sys.executable, '-c',
            "import time; print('ready',flush=True); time.sleep(60)"])
        until(lambda: 'ready' in window.output, window)
        master = window.master
        restored = []
        cleaned = []
        desk.term = SimpleNamespace(restore=lambda: restored.append(True))
        desk.cleanup_shm = lambda: cleaned.append(True)
        # A busy window refuses ordinary close; forced shutdown must call its
        # ownership callback directly and continue after callback failure.
        callback = mock.Mock(side_effect=RuntimeError('cleanup failed'))
        busy = SimpleNamespace(on_close=callback, close=mock.Mock(side_effect=AssertionError('busy')))
        desk.wm.windows.insert(0, busy)
        def run():
            if failure is not None:
                raise failure
        desk._run = run
        try:
            desk.run()
        except (SystemExit, RuntimeError) as error:
            assert error is failure
        callback.assert_called_once()
        busy.close.assert_not_called()
        assert window.process.poll() is not None
        assert window.master is None and window.tick not in desk.tick_hooks
        assert master not in desk.fd_hooks
        try:
            os.fstat(master)
        except OSError:
            pass
        else:
            raise AssertionError('PTY survived desktop teardown')
        assert desk.wm.windows == [] and restored and cleaned

print('embedded licence terminal and desktop teardown: OK')
