"""Hidden input uses the controlling PTY and never enters the transcript."""
from pathlib import Path
import sys
import time

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
    log_path = Path(temporary) / 'transcript.log'
    script = """
import getpass
assert input('Install optional software? [y/N] ') == 'y'
while getpass.getpass('Administrator password: ') != 'fixture-secret':
    print('Try again.', flush=True)
print('Helper complete.', flush=True)
assert input('Install next model? [y/N] ') == 'n'
"""
    window = open_window(desk, [sys.executable, '-c', script], log_path=log_path)
    try:
        until(lambda: window.yes.enabled, window)
        assert not window.password.visible
        window.yes.cb()
        until(lambda: window.password.enabled, window)
        assert window.password.mask and not window.yes.enabled and not window.no.enabled
        assert not window.yes.visible and not window.no.visible
        H.type_text(desk, 'fixture-wrong')
        assert window.password._disp() == '•' * len('fixture-wrong')
        window.password_button.cb()
        assert not window.password.text and not window.password.enabled
        # A second click cannot queue an extra password or answer a later prompt.
        window.password_button.cb()
        until(lambda: 'Try again.' in window.output and window.password.enabled, window)
        assert window.focus is window.password
        H.type_text(desk, 'fixture-secret\n')
        assert not window.password.text
        until(lambda: window.no.enabled, window)
        assert not window.password.visible and not window.password.enabled
        assert 'Helper complete.' in window.output
        window.no.cb()
        until(lambda: window.finished, window)
        assert window.process.returncode == 0
        assert not window.password.enabled and not window.yes.enabled
        for secret in ('fixture-wrong', 'fixture-secret'):
            assert secret not in window.output
            assert secret not in window.transcript.text()
            assert secret not in log_path.read_text()
        assert log_path.stat().st_mode & 0o777 == 0o600
    finally:
        window.close()

    # Echo can return before the desktop observes another byte. Submission
    # must check the live terminal mode, clear the field and send nothing.
    restore = Path(temporary) / 'restore'
    restored = Path(temporary) / 'restored'
    script = f"""
import os, termios, time
from pathlib import Path
original = termios.tcgetattr(0)
hidden = termios.tcgetattr(0)
hidden[3] &= ~termios.ECHO
termios.tcsetattr(0, termios.TCSANOW, hidden)
print('Hidden input:', flush=True)
while not Path({str(restore)!r}).exists(): time.sleep(.01)
termios.tcsetattr(0, termios.TCSANOW, original)
Path({str(restored)!r}).touch()
assert input('Continue? [y/N] ') == 'n'
"""
    window = open_window(desk, [sys.executable, '-c', script])
    try:
        until(lambda: window.password.enabled, window)
        H.type_text(desk, 'must-not-be-sent')
        restore.touch()
        deadline = time.monotonic() + 4
        while not restored.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert restored.exists()
        assert window.password.enabled  # UI has deliberately not polled.
        window.submit_password()
        assert not window.password.text and not window.password.enabled
        until(lambda: window.no.enabled, window)
        window.no.cb()
        until(lambda: window.finished, window)
        assert window.process.returncode == 0
        assert 'must-not-be-sent' not in window.output
    finally:
        window.close()

    # Closing at a password prompt clears unsent text and stops the owned job.
    window = open_window(desk, [sys.executable, '-c',
        "import getpass; getpass.getpass('Administrator password: ')"])
    try:
        until(lambda: window.password.enabled, window)
        H.type_text(desk, 'unsent-secret')
    finally:
        window.close()
    assert not window.password.text and window.master is None
    assert window.process.poll() is not None
    assert 'unsent-secret' not in window.output

print('embedded terminal password input: OK')
