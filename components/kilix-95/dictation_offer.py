"""First-boot offer to set up dictation, asked until the user says yes or no.

The desktop offers the recommended speech-recognition model for this computer
(the model sizer's default) at every start until the user answers. Yes opens a
terminal running `kilix stt --setup-default`, which shows the licence, installs
the model and its runtime, asks for dictation consent and makes it the default.
A completed setup records yes; declining in that terminal, or choosing No
here, records no. Closing the window, or a setup that fails, leaves the
question open for the next start.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ANSWERS = ('yes', 'no')
SETUP_TIMEOUT = 3600          # large downloads on a slow link take a while
HOTKEY = 'Ctrl+Shift+D'


def offer_enabled():
    override = os.environ.get('KILIX_DICTATION_OFFER')
    return override == '1' if override is not None else os.path.isfile('/etc/plebian-os/build-info.env')


class Controller:
    def __init__(self, desk):
        import durable_state
        self.desk = desk
        self.store = durable_state.JsonState('dictation-offer.state')
        self.state = {'answer': None, 'model': None}
        self.state.update(self.store.load_dict())
        if self.state['answer'] not in ANSWERS:
            self.state['answer'] = None
        self.job = None
        self.pending = False
        self.status = 'Dictation is not set up yet.'
        desk.tick_hooks.append(self.tick)

    @property
    def answered(self):
        return self.state['answer'] in ANSWERS

    def save(self, **changes):
        state = dict(self.state, **changes)
        self.store.save_dict(state)
        self.state = state

    def startup(self):
        # Asked at every start until answered; shown once the system voice
        # offer (if any) is out of the way, so the two never stack.
        if offer_enabled() and not self.answered:
            self.pending = True
            self.tick(0)

    def voice_offer_busy(self):
        voice = getattr(self.desk, 'system_voice', None)
        if voice is not None and voice.job:
            return True
        return any(type(window).__name__ == 'SystemVoice' for window in self.desk.wm.windows)

    def open(self):
        from apps.dictation import open_window
        return open_window(self.desk)

    def accept(self):
        if self.job:
            raise ValueError('Setup is already open. Complete or close its terminal first.')
        target = self.desk.shell.kilix_stt_target()
        if not target:
            raise ValueError('The Kilix dictation launcher is not installed.')
        directory = tempfile.TemporaryDirectory(prefix='kilix-dictation-setup-')
        result = str(Path(directory.name)/'result.json')
        command = [sys.executable, __file__, '--prepare', result, *target]
        if not self.desk.shell._tab(command, 'Set up dictation', os.path.expanduser('~')):
            directory.cleanup()
            raise ValueError('Could not open the dictation setup terminal.')
        self.job = (directory, result, time.monotonic())
        self.status = 'Finish the setup in the terminal that opened.'

    def decline(self):
        self.save(answer='no')
        self.cancel_job()
        self.status = f'Dictation was not set up. Set it up later with "kilix stt --setup-default".'

    def cancel_job(self):
        if self.job:
            self.job[0].cleanup()
            self.job = None

    def finish(self, outcome):
        status = outcome.get('status')
        model = outcome.get('model') if isinstance(outcome.get('model'), str) else None
        if status == 'ready':
            self.save(answer='yes', model=model)
            self.status = f'Dictation is ready ({model or "default model"}). Press {HOTKEY} to dictate.'
        elif status == 'declined':
            self.save(answer='no')
            self.status = 'Dictation was not set up.'
        else:
            detail = outcome.get('detail') if isinstance(outcome.get('detail'), str) else ''
            self.status = ('Setup did not finish. ' + detail).strip() + ' Choose Set up to retry.'

    def tick(self, _now):
        if self.pending and not self.voice_offer_busy():
            self.pending = False
            self.open()
        if not self.job:
            return
        directory, result, started = self.job
        if os.path.isfile(result):
            try:
                self.finish(json.loads(Path(result).read_text()))
            except Exception as error:
                self.status = f'Could not read the dictation setup result: {error}'
            self.cancel_job()
            self.open()
        elif time.monotonic()-started > SETUP_TIMEOUT:
            self.cancel_job()
            self.status = 'Setup did not finish. Choose Set up to retry.'
            self.open()

    def close(self):
        self.cancel_job()
        if self.tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.tick)


def controller(desk):
    if getattr(desk, 'dictation_offer', None) is None:
        desk.dictation_offer = Controller(desk)
    return desk.dictation_offer


def prepare(result, target):
    """Run the setup in the terminal and always leave a result for the desktop.

    The launcher writes its own outcome to a private file; a launcher that
    fails before it can (an older Voice runtime, a crash) still yields one.
    """
    inner = str(Path(result).with_name('setup-result.json'))
    try:
        code = subprocess.call([*target, '--setup-default', '--result', inner])
    except OSError as error:
        print(error, file=sys.stderr)
        code = 2
    try:
        outcome = json.loads(Path(inner).read_text())
        if not isinstance(outcome, dict):
            raise ValueError('not an object')
    except (OSError, ValueError):
        outcome = {'status': 'declined' if code == 1 else 'failed', 'model': None,
                   'detail': f'The setup exited with status {code}.'}
    outcome['exit_code'] = code
    path = Path(result)
    try:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(outcome))
        os.replace(temporary, path)
    except OSError:
        pass  # Desktop cancelled/closed the job while setup was running.
    if outcome.get('status') != 'ready':
        print('Dictation setup did not finish. You can retry from the desktop.')
        try:
            input('Press Enter to close this terminal… ')
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] != '--prepare':
        raise SystemExit('usage: dictation_offer.py --prepare RESULT LAUNCHER [ARG ...]')
    raise SystemExit(prepare(sys.argv[2], sys.argv[3:]))
