"""Real owned processes: retain leader identity and preserve discovery errors."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from owned_job import OwnedJob
from model_discovery import Discovery


def until(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('owned fixture did not reach its expected state')


class OwnedProcessTests(unittest.TestCase):
    def test_exited_leader_keeps_ownership_until_remaining_worker_is_stopped(self):
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        worker = None
        job = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                ready = Path(directory) / 'worker'
                child = ('import os,signal,time; from pathlib import Path; '
                         'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                         f'Path({str(ready)!r}).write_text(str(os.getpid())); '
                         'time.sleep(60)')
                parent = ('import subprocess,sys,time; from pathlib import Path; '
                          f'subprocess.Popen([sys.executable,"-c",{child!r}]); '
                          f'p=Path({str(ready)!r}); '
                          '\nwhile not p.exists(): time.sleep(.01)')
                job = OwnedJob([sys.executable, '-c', parent],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                until(lambda: ready.exists() and job.poll() is not None)
                worker = int(ready.read_text())
                self.assertEqual(os.getpgid(worker), job.pid)
                # The exited leader is still waitable; observing completion did
                # not release the group identity before escalation.
                self.assertIsNotNone(os.waitid(os.P_PID, job.pid,
                    os.WEXITED | os.WNOHANG | os.WNOWAIT))
                job.stop()
                until(lambda: os.waitid(os.P_PID, worker,
                    os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None)
                pid, status = os.waitpid(worker, 0)
                worker = None
                self.assertTrue(os.WIFSIGNALED(status))
                self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
                self.assertEqual(job.poll(), 0)
                job.stop()
        finally:
            if job is not None:
                job.stop()
            if worker is not None:
                try:
                    os.kill(worker, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(worker, 0)
            self.assertEqual(libc.prctl(36, previous.value, 0, 0, 0), 0)

    def test_discovery_failure_retains_complete_private_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'model_wizard.py').write_text(
                'def pages(**kwargs):\n'
                '    raise RuntimeError("fixture discovery failure")\n')
            with patch.object(sys, 'path', [directory, *sys.path]):
                task = Discovery(root)
            try:
                until(task.done)
                with self.assertRaisesRegex(RuntimeError, 'fixture discovery failure'):
                    task.result()
                self.assertTrue(task.output.closed)
                self.assertIn('Traceback', task.log_path.read_text())
                self.assertIn('fixture discovery failure', task.log_path.read_text())
                self.assertEqual(task.log_path.stat().st_mode & 0o777, 0o600)
            finally:
                task.close()


if __name__ == '__main__':
    unittest.main()
