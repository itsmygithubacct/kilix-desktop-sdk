"""Optional per-user startup speech, owned by the running desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def greeting(value):
    if not isinstance(value, str) or len(value.encode('utf-8')) > 1024 or '\0' in value:
        raise ValueError('Use a startup message of at most 1024 UTF-8 bytes.')
    return value.strip()


def offer_enabled():
    override = os.environ.get('KILIX_SYSTEM_VOICE_OFFER')
    return override == '1' if override is not None else os.path.isfile('/etc/plebian-os/build-info.env')


class Controller:
    def __init__(self, desk):
        import durable_state
        self.desk = desk
        self.store = durable_state.JsonState('system-voice.state')
        self.state = {'offered': False, 'enabled': False, 'greeting': 'hello'}
        self.state.update(self.store.load_dict())
        try:
            self.state['greeting'] = greeting(self.state['greeting'])
        except ValueError:
            self.state['greeting'] = 'hello'
        self.process = None
        self.job = None
        self.log = None
        self.directory = None
        self.status = 'System voice is off.'
        desk.tick_hooks.append(self.tick)

    def save(self, **changes):
        state = dict(self.state, **changes)
        self.store.save_dict(state)
        self.state = state

    def startup(self):
        if self.state['enabled'] is True:
            self.start()
        elif offer_enabled() and not self.state['offered']:
            self.open()
            self.save(offered=True)

    def open(self):
        from apps.systemvoice import open_window
        return open_window(self.desk)

    def enable(self, message):
        message = greeting(message)
        if self.job:
            raise ValueError('Setup is already open. Complete or close its terminal first.')
        if self.state['enabled'] is True:
            self.save(greeting=message, offered=True)
            if self.process is None:
                self.start()
            return
        target = self.desk.shell.kilix_tts_target()
        if not target:
            raise ValueError('The Kilix speech launcher is not installed.')
        directory = tempfile.TemporaryDirectory(prefix='kilix-system-voice-setup-')
        result = str(Path(directory.name)/'result.json')
        command = [sys.executable, __file__, '--prepare', result, *target]
        if not self.desk.shell._tab(command, 'Enable system voice', os.path.expanduser('~')):
            directory.cleanup()
            raise ValueError('Could not open the system voice setup terminal.')
        self.job = (directory, result, message, time.monotonic())
        self.status = 'Finish the download notice in the setup terminal.'

    def disable(self):
        self.save(enabled=False, offered=True)
        if self.job:
            self.job[0].cleanup()
            self.job = None
        self.stop()
        self.status = 'System voice is off.'

    def start(self):
        if self.process is not None:
            return
        target = self.desk.shell.kilix_tts_target()
        if not target:
            self.status = 'The Kilix speech launcher is not installed.'
            self.open()
            return
        self.directory = tempfile.TemporaryDirectory(prefix='kilix-system-voice-')
        self.log = open(Path(self.directory.name)/'session.log', 'w+b')
        try:
            self.process = subprocess.Popen(
                [*target, '--system-voice', '--speak=' + self.state['greeting']],
                stdin=subprocess.PIPE, stdout=self.log, stderr=self.log)
        except OSError as error:
            self.stop()
            self.status = f'Could not start system voice: {error}'
            self.open()
            return
        self.status = 'Loading Piper Kristin…'

    def tick(self, _now):
        if self.job:
            directory, result, message, started = self.job
            if os.path.isfile(result):
                try:
                    code = json.loads(Path(result).read_text())['exit_code']
                    if code == 0:
                        self.save(enabled=True, offered=True, greeting=message)
                        self.start()
                    else:
                        self.status = 'Setup was cancelled or failed. Choose Enable to retry.'
                except Exception as error:
                    self.status = f'Could not enable system voice: {error}'
                directory.cleanup()
                self.job = None
                self.open()
            elif time.monotonic()-started > 1800:
                directory.cleanup()
                self.job = None
                self.status = 'Setup did not finish. Choose Enable to retry.'
                self.open()
        if self.process is not None:
            code = self.process.poll()
            with open(self.log.name, 'rb') as log_reader:
                log_reader.seek(0, os.SEEK_END)
                log_reader.seek(max(0, log_reader.tell()-8192))
                text = log_reader.read(8192).decode('utf-8', errors='replace')
            if code is not None:
                self.stop()
                self.status = 'System voice stopped. ' + (text.strip().splitlines()[-1] if text.strip() else f'Exit {code}.')
                self.open()
            elif 'System voice ready: Piper Kristin' in text:
                self.status = 'Piper Kristin is ready for this session.'

    def goodbye(self):
        """Best-effort cached speech before the menu asks the OS to power off."""
        if not self.state['enabled'] or self.process is None or self.process.poll() is not None:
            return
        try:
            offset = os.path.getsize(self.log.name)
            self.process.stdin.write(b'g')
            self.process.stdin.flush()
            deadline = time.monotonic()+4
            while time.monotonic() < deadline and self.process.poll() is None:
                with open(self.log.name, 'rb') as reader:
                    reader.seek(offset)
                    if b'System voice goodbye complete' in reader.read(8192):
                        return
                time.sleep(.05)
        except (OSError, ValueError):
            pass  # A missing/broken voice must never prevent power-off.

    def stop(self):
        if self.process is not None:
            self.process.stdin.close()
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
        if self.log:
            self.log.close()
            self.log = None
        if self.directory:
            self.directory.cleanup()
            self.directory = None

    def close(self):
        self.stop()
        if self.job:
            self.job[0].cleanup()
            self.job = None
        if self.tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.tick)


def controller(desk):
    if getattr(desk, 'system_voice', None) is None:
        desk.system_voice = Controller(desk)
    return desk.system_voice


def prepare(result, target, option="--prepare-system-voice"):
    try:
        code = subprocess.call([*target, option])
    except OSError as error:
        print(error, file=sys.stderr)
        code = 1
    path = Path(result)
    try:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'exit_code': code}))
        os.replace(temporary, path)
    except OSError:
        pass  # Desktop cancelled/closed the job while setup was running.
    if code:
        print('Voice setup did not finish. You can retry from the desktop.')
    return code


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] not in ('--prepare', '--prepare-kristin'):
        raise SystemExit('usage: system_voice.py --prepare RESULT LAUNCHER [ARG ...]')
    raise SystemExit(prepare(sys.argv[2], sys.argv[3:], '--enable-kristin' if sys.argv[1] == '--prepare-kristin' else '--prepare-system-voice'))
