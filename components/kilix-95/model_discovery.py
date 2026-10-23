"""Cancellable model discovery in a separately owned session, never a thread."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from owned_job import OwnedJob


class Discovery:
    def __init__(self, directory=None):
        if directory is None:
            from model_wizard import new_run_directory
            directory = new_run_directory()
        self.directory = Path(directory)
        self.log_path = self.directory / 'error.log'
        self.output = tempfile.TemporaryFile()
        self.closed = False
        try:
            fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as diagnostic:
                self.process = OwnedJob(
                    [sys.executable, str(Path(__file__).resolve()), '--worker'],
                    stdin=subprocess.DEVNULL, stdout=self.output,
                    stderr=diagnostic,
                    env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path)))
        except BaseException:
            self.output.close()
            raise

    def done(self):
        return self.process.poll() is not None

    def result(self):
        try:
            if not self.done():
                raise RuntimeError('Model discovery is still running.')
            if self.process.returncode != 0:
                # Keep the complete stderr on disk; only bound the UI detail.
                with self.log_path.open('rb') as diagnostic:
                    diagnostic.seek(0, os.SEEK_END)
                    diagnostic.seek(max(0, diagnostic.tell() - 8192))
                    detail = diagnostic.read().decode('utf-8', 'replace').strip()
                raise RuntimeError(detail or
                    f'Model discovery exited with status {self.process.returncode}.')
            self.output.seek(0)
            return json.load(self.output)
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        try:
            self.process.stop()
        finally:
            self.output.close()
        self.closed = True


def discover():
    import model_wizard as backend
    # Backend notices must not contaminate the structured response.
    from contextlib import redirect_stdout
    with redirect_stdout(sys.stderr):
        pages = backend.pages(ensure_sizer=True)
    json.dump(pages, sys.stdout)


if __name__ == '__main__':
    discover()
