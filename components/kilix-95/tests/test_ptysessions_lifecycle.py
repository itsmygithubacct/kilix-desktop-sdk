"""Owned launcher group cleanup when a graphical read times out."""
import os
from pathlib import Path
import signal
import tempfile
import time

import harness as H  # noqa: F401
from apps import ptysessions as P

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    marker = root / 'child'
    launcher = root / 'launcher'
    launcher.write_text('#!/usr/bin/env python3\n'
                        'import os, subprocess, time\n'
                        'child = subprocess.Popen(["sleep", "30"])\n'
                        f'open({str(marker)!r}, "w").write(str(child.pid))\n'
                        'try:\n    child.wait()\n'
                        'finally:\n    child.terminate()\n    child.wait()\n')
    launcher.chmod(0o700)
    try:
        P.run_pty(['list', '--json'], str(launcher), timeout=0.4)
        raise AssertionError('expected timeout')
    except P.PtyError as error:
        assert 'did not answer' in str(error)
    pid = int(marker.read_text())
    # A reparented zombie is stopped; it is reaped by the host's init.
    end = time.monotonic() + 2
    while True:
        try:
            state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            break
        if state == 'Z':
            break
        assert time.monotonic() < end, 'owned child survived timeout'
        time.sleep(0.02)
print('owned launcher timeout cleanup passed')

# Invalid output is decoded only after reaping, outside signal cleanup.
from unittest import mock
import subprocess

with tempfile.TemporaryDirectory() as directory:
    launcher = Path(directory) / "invalid-output"
    launcher.write_text("#!/usr/bin/env python3\nimport os\nos.write(1, b'\\xff')\n")
    launcher.chmod(0o700)
    with mock.patch.object(P.os, "killpg") as signal_spy:
        try:
            P.run_pty(["list"], str(launcher))
            raise AssertionError("expected invalid UTF-8 refusal")
        except P.PtyError as error:
            assert "invalid UTF-8" in str(error)
        signal_spy.assert_not_called()

# A reaped leader with a pipe retained elsewhere must never receive a signal,
# and cleanup must use a deadline then close the local pipe handles.
process = mock.Mock()
process.returncode = 0
process.communicate.side_effect = subprocess.TimeoutExpired("fixture", 0.1)
with mock.patch.object(P.subprocess, "Popen", return_value=process), mock.patch.object(P.os, "killpg") as signal_spy:
    try:
        P.run_pty(["list"], "fixture", timeout=0.1)
        raise AssertionError("expected timeout")
    except P.PtyError as error:
        assert "did not answer" in str(error)
    signal_spy.assert_not_called()
    assert process.communicate.call_args_list == [mock.call(timeout=0.1), mock.call(timeout=1)]
    process.stdout.close.assert_called_once()
    process.stderr.close.assert_called_once()
    process.wait.assert_called_once_with(timeout=1)
print("reaped leader and bounded cleanup controls passed")

# An exited but unreaped leader still owns its group. Its helper inherits the
# pipes and must be stopped before cleanup reaps the leader.
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    marker = root / "helper"
    launcher = root / "early-exit"
    launcher.write_text("#!/usr/bin/env python3\nimport subprocess\n"
                        "child = subprocess.Popen(['sleep', '30'])\n"
                        f"open({str(marker)!r}, 'w').write(str(child.pid))\n")
    launcher.chmod(0o700)
    started = time.monotonic()
    try:
        P.run_pty(["list"], str(launcher), timeout=0.4)
        raise AssertionError("expected inherited-pipe timeout")
    except P.PtyError as error:
        assert "did not answer" in str(error)
    assert time.monotonic() - started < 4
    pid = int(marker.read_text())
    end = time.monotonic() + 2
    while True:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            break
        if state == "Z":
            break
        assert time.monotonic() < end, "early-exit leader's helper survived timeout"
        time.sleep(0.02)
print("early-exit leader helper cleanup passed")
