"""A private PTY rendered as a licence terminal inside the desktop."""
import codecs
import fcntl
import os
import pty
import re
import struct
import termios
from datetime import datetime, timezone

import widgets as W
import wm
from owned_job import OwnedJob


class Transcript(W.TextArea):
    def on_key(self, ev):
        if ev.key in ('Up', 'Down', 'Left', 'Right', 'Home', 'End', 'PageUp', 'PageDown') \
                or (getattr(ev, 'ctrl', False) and ev.key.lower() in ('c', 'a')):
            return super().on_key(ev)
        return True


class LicenceTerminal(wm.Window):
    def __init__(self, desk, command, *, log_path=None):
        super().__init__(desk, 'Model licence agreements', 740, 485,
                         icon='terminal', resizable=True)
        self.min_w, self.min_h = 480, 300
        self.output = ''
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.master, slave = pty.openpty()
        self.process = None
        self.finished = False
        self.answered_at = -1
        self.log = None
        try:
            if log_path is not None:
                fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                self.log = os.fdopen(fd, 'wb')
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 26, 95, 0, 0))
            self.process = OwnedJob(command, stdin=slave, stdout=slave, stderr=slave,
                                    env=dict(os.environ, TERM='dumb', NO_COLOR='1'))
            self.log_event(f'Installer started; pid={self.process.pid}')
        except BaseException:
            os.close(self.master)
            if self.log is not None:
                self.log.close()
            raise
        finally:
            os.close(slave)
        os.set_blocking(self.master, False)
        self.transcript = self.add(Transcript(8, 8, 710, 368))
        self.note = self.add(W.Label(12, 385, 'Read the terms, then answer Yes or No for the named models.'))
        self.yes = self.add(W.Button(12, 415, 110, 26, 'Yes', cb=lambda: self.answer(b'y\n')))
        self.no = self.add(W.Button(136, 415, 110, 26, 'No', cb=lambda: self.answer(b'n\n')))
        self.close_button = self.add(W.Button(535, 415, 170, 26, 'Cancel setup', cb=self.close))
        self.yes.enabled = self.no.enabled = False
        self.desk.add_fd(self.master, self.pump)
        self.desk.tick_hooks.append(self.tick)
        self.on_close = self.cleanup
        self.on_resize()

    def on_resize(self):
        width, height = self.client_size()
        self.transcript.w, self.transcript.h = width - 16, height - 76
        self.note.y = height - 58
        self.yes.y = self.no.y = self.close_button.y = height - 34
        self.close_button.x = width - 182
        if self.process is not None and not self.finished:
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH',
                        max(8, self.transcript.h // 15), max(40, self.transcript.w // 6), 0, 0))

    def pump(self, *_args):
        try:
            data = os.read(self.master, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b''  # PTY EIO after the worker exits.
        if not data:
            self.desk.remove_fd(self.master)
            return
        self.output = (self.output + self.decoder.decode(data))[-4 * 1024 * 1024:]
        if self.log is not None:
            try:
                self.log.write(data)
                # Retain late errors without rewriting the entire transcript
                # for every chunk of download progress.
                if self.log.tell() > 8 * 1024 * 1024:
                    self.log.seek(0)
                    self.log.write(self.output.encode('utf-8')[-4 * 1024 * 1024:])
                    self.log.truncate()
                self.log.flush()
            except OSError as error:
                self.output += f'\nCould not save diagnostic transcript: {error}\n'
                try:
                    self.log.close()
                except OSError:
                    pass
                self.log = None
        clean = re.sub(r'\x1b\][^\x07]*(?:\x07|\x1b\\)', '', self.output)
        clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', clean)
        clean = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', clean.replace('\r\n', '\n').replace('\r', '\n'))
        self.transcript.set_text(clean)
        self.transcript.sb.pos = max(0, len(self.transcript.lines) - self.transcript._rows())
        prompt = bool(re.search(r'\[(?:y/N|Y/n)\]\s*$', clean))
        self.yes.enabled = self.no.enabled = prompt and len(self.output) != self.answered_at
        self.invalidate()

    def answer(self, data):
        if not self.yes.enabled or self.finished: return
        os.write(self.master, data)
        self.answered_at = len(self.output)
        self.yes.enabled = self.no.enabled = False
        self.invalidate()

    def log_event(self, message):
        if self.log is not None:
            try:
                stamp = datetime.now(timezone.utc).isoformat()
                self.log.write(f'\n[{stamp}] {message}\n'.encode())
                self.log.flush()
            except OSError as error:
                self.output += f'\nCould not save diagnostic transcript: {error}\n'

    def tick(self, _now):
        if not self.finished and self.process.poll() is not None:
            self.pump()
            self.finished = True
            self.log_event(f'Installer exited; status={self.process.returncode}')
            self.yes.enabled = self.no.enabled = False
            self.note.set('Setup complete.' if self.process.returncode == 0 else
                          'Setup did not finish. Your choices are saved for retry.')
            self.close_button.text = 'Close'
            self.invalidate()

    def cleanup(self):
        from workflows_offer import stop
        try:
            if self.process is not None:
                if not self.finished:
                    self.log_event('Setup terminal closed before installer completion')
                stop(self.process)
        finally:
            try:
                if self.tick in self.desk.tick_hooks:
                    self.desk.tick_hooks.remove(self.tick)
                if self.master is not None:
                    descriptor, self.master = self.master, None
                    try:
                        self.desk.remove_fd(descriptor)
                    finally:
                        os.close(descriptor)
            finally:
                log, self.log = getattr(self, 'log', None), None
                if log is not None:
                    log.close()


def open_window(desk, command, *, log_path=None):
    window = LicenceTerminal(desk, command, log_path=log_path)
    desk.wm.add(window)
    return window
