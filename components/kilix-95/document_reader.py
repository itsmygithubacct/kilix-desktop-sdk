"""Nonblocking bridge to the voice module's private document-reader session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


class Session:
    def __init__(self, target, filename):
        self.log = tempfile.TemporaryFile()
        self.process = None
        self.buffer = b''
        self.exited = False
        try:
            self.process = subprocess.Popen(
                [*target, '--reader-session', filename], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.log)
            os.set_blocking(self.process.stdout.fileno(), False)
        except Exception:
            self.close()
            raise

    def command(self, command):
        if self.process and self.process.poll() is None:
            self.process.stdin.write(command.encode('ascii'))
            self.process.stdin.flush()

    def poll(self):
        events = []
        try:
            block = os.read(self.process.stdout.fileno(), 65536)
        except BlockingIOError:
            block = None
        if block:
            self.buffer += block
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError('Invalid reader status.')
                events.append(event)
            if len(self.buffer) > 65536:
                raise ValueError('Reader status exceeded its limit.')
        elif block == b'' and not self.exited and self.process.poll() is not None:
            self.exited = True
            self.log.seek(0, os.SEEK_END)
            self.log.seek(max(0, self.log.tell()-4096))
            detail = self.log.read().decode('utf-8', errors='replace').strip()
            events.append({'state': 'closed', 'error': detail or None})
        return events

    def close(self):
        if self.process:
            self.process.stdin.close()
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stdout.close()
            self.process = None
        self.log.close()


class KristinSetup:
    def __init__(self, shell):
        target = shell.kilix_tts_target()
        if not target:
            raise ValueError('The Kilix speech launcher is not installed.')
        self.directory = tempfile.TemporaryDirectory(prefix='kilix-kristin-setup-')
        self.result = Path(self.directory.name)/'result.json'
        self.started = time.monotonic()
        helper = Path(__file__).with_name('system_voice.py')
        command = [sys.executable, str(helper), '--prepare-kristin', str(self.result), *target]
        if not shell._tab(command, 'Use Kristin for read-aloud', os.path.expanduser('~')):
            self.close()
            raise ValueError('Could not open the Kristin setup terminal.')

    def poll(self):
        if self.result.is_file():
            return json.loads(self.result.read_text())['exit_code']
        if time.monotonic()-self.started > 1800:
            return 1
        return None

    def close(self):
        self.directory.cleanup()
