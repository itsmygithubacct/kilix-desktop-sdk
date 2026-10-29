"""Linux session jobs whose leader is retained until group cleanup finishes.

Only this object may reap its child. WNOWAIT leaves an exited leader waitable,
reserving its PID (and hence our process-group identity) through escalation.
Use on the desktop thread; do not hand the underlying Popen to other waiters.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class OwnedJob:
    def __init__(self, command, *, controlling_terminal=False, **kwargs):
        if controlling_terminal:
            # Attach after setsid in a fresh interpreter, not preexec_fn in
            # the threaded desktop. exec retains the leader we own and reap.
            command = [sys.executable, str(Path(__file__).resolve()), *command]
        kwargs['start_new_session'] = True
        self._process = subprocess.Popen(command, **kwargs)
        self.pid = self._process.pid
        self.returncode = None
        self._closed = False

    def _status(self):
        return os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)

    def poll(self):
        if not self._closed:
            status = self._status()
            if status is not None:
                self.returncode = (status.si_status if status.si_code == os.CLD_EXITED
                                   else -status.si_status)
        return self.returncode

    def stop(self):
        if self._closed:
            return
        # Raises ChildProcessError if another waiter broke our ownership. Never
        # signal an identity that is no longer reserved by our unreaped child.
        self._status()
        try:
            os.killpg(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        else:
            # Leader exit is not evidence that all its workers have exited.
            time.sleep(2)
            self._status()
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.returncode = self._process.wait(timeout=2)
        self._closed = True


if __name__ == '__main__':
    import fcntl
    import termios

    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
