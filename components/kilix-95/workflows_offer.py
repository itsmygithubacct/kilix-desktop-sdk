"""Opt-in local workflow model setup; the selected host owns acquisition."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

SCHEMA = 'kilix.workflows/v1'
MAX_OUTPUT = 65536
CHECK_TIMEOUT = 90
SETUP_TIMEOUT = 3600


def offer_enabled():
    value = os.environ.get('KILIX_WORKFLOWS_OFFER')
    return value == '1' if value is not None else os.path.isfile('/etc/plebian-os/build-info.env')


def read_status(output, code):
    """Allow host installation notices before the final bounded JSON record."""
    if len(output) > MAX_OUTPUT or code not in (0, 1):
        raise ValueError('Workflow setup is unavailable in the selected installation.')
    try:
        record = json.loads(output.decode('utf-8').strip().splitlines()[-1])
    except (UnicodeError, ValueError, IndexError) as error:
        raise ValueError('The selected installation did not report workflow model readiness.') from error
    if not isinstance(record, dict) or record.get('schema') != SCHEMA \
            or type(record.get('ready')) is not bool \
            or record.get('status') != ('ready' if record['ready'] else 'not-ready') \
            or (code == 0) != record['ready']:
        raise ValueError('The selected installation returned an invalid workflow status.')
    return record


def ready_detail(record):
    detail = record.get('detail')
    return detail[:180] if isinstance(detail, str) and detail else 'Kilix Workflows is ready.'


def stop(process):
    """Only terminate the process group created for this owned probe."""
    from owned_job import OwnedJob
    if isinstance(process, OwnedJob):
        process.stop()
        return
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)


def process_stamp(pid):
    """PID reuse cannot make a finished setup look like an unrelated process."""
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
        fields = stat.rpartition(')')[2].split()
        return fields[19] if fields[0] != 'Z' else False
    except FileNotFoundError:
        return False
    except (OSError, IndexError):
        return None


def worker_active(result):
    try:
        with open(Path(result).with_name('worker.json'), 'rb') as stream:
            record = json.loads(stream.read(4096))
        pid = record['pid']
        if type(pid) is not int or pid <= 0 or not isinstance(record['start'], str):
            return None
        stamp = process_stamp(pid)
        return None if stamp is None else stamp == record['start']
    except (OSError, ValueError, KeyError, TypeError):
        return None


def checked_status(target):
    """Bound the duration and captured bytes while the selected probe runs."""
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([*target, 'workflows', 'status', '--json'],
                                   stdin=subprocess.DEVNULL, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + CHECK_TIMEOUT
        try:
            while process.poll() is None:
                if os.fstat(output.fileno()).st_size > MAX_OUTPUT:
                    raise ValueError('Workflow status exceeded its output limit.')
                if time.monotonic() > deadline:
                    raise ValueError('Workflow status timed out.')
                time.sleep(.02)
            output.seek(0)
            return read_status(output.read(MAX_OUTPUT + 1), process.returncode)
        finally:
            stop(process)


class Controller:
    def __init__(self, desk):
        import durable_state
        self.desk = desk
        self.store = durable_state.JsonState('workflows-offer.state')
        self.state = {'answer': None}
        self.state.update(self.store.load_dict())
        if self.state['answer'] not in ('yes', 'no'):
            self.state['answer'] = None
        self.job = None
        self.probe = None
        self.pending = None
        self.ready = False
        self.status = 'Local workflow models have not been checked.'
        desk.tick_hooks.append(self.tick)

    def save(self, **changes):
        state = dict(self.state, **changes)
        self.store.save_dict(state)
        self.state = state

    def startup(self):
        if self.pending or self.job or self.probe:
            return
        if self.state['answer'] == 'yes':
            self.pending = 'check'
        elif self.state['answer'] is None and offer_enabled():
            self.pending = 'offer'
        self.tick(0)

    def other_offer_busy(self):
        for name in ('system_voice', 'dictation_offer'):
            offer = getattr(self.desk, name, None)
            if offer is not None and (getattr(offer, 'job', None) or getattr(offer, 'pending', False)):
                return True
        return any(type(w).__name__ in ('SystemVoice', 'DictationOffer') for w in self.desk.wm.windows)

    def open(self):
        from apps.workflows import open_window
        return open_window(self.desk)

    def enable(self):
        if self.job or self.probe:
            raise ValueError('Workflow setup is already running. Finish its terminal first.')
        target = self.desk.shell.kilix_workflows_target()
        if not target:
            raise ValueError('The selected Kilix launcher is not installed.')
        output = tempfile.TemporaryFile()
        try:
            process = subprocess.Popen([*target, 'workflows', 'status', '--json'],
                                       stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            output.close()
            raise
        self.probe = (process, output, time.monotonic(), target)
        self.ready = False
        self.status = 'Checking local workflow models…'

    def begin_setup(self, target):
        directory = tempfile.TemporaryDirectory(prefix='kilix-workflows-setup-')
        result = str(Path(directory.name) / 'result.json')
        command = [sys.executable, __file__, '--prepare', result, *target]
        if not self.desk.shell._tab(command, 'Enable Kilix Workflows', os.path.expanduser('~')):
            directory.cleanup()
            raise ValueError('Could not open the workflow setup terminal.')
        self.job = (directory, result, time.monotonic())
        self.status = 'Finish the model download and licence screen in the setup terminal.'

    def decline(self):
        if self.job or self.probe:
            raise ValueError('Finish or close the setup terminal before changing this choice.')
        self.save(answer='no')
        self.pending = None
        self.ready = False
        self.status = 'Automatic workflow model setup is off. Downloaded files are kept.'

    def finish_probe(self):
        process, output, started, target = self.probe
        code = process.poll()
        if time.monotonic() - started > CHECK_TIMEOUT or os.fstat(output.fileno()).st_size > MAX_OUTPUT:
            stop(process)
            self.probe = None
            output.close()
            self.status = 'Model check did not finish. Check your connection and choose Enable to retry.'
            self.open()
            return
        if code is None:
            return
        self.probe = None
        try:
            output.seek(0)
            record = read_status(output.read(MAX_OUTPUT + 1), code)
            if record['ready']:
                self.save(answer='yes')
                self.ready = True
                self.status = ready_detail(record)
            else:
                # Only an already opted-in startup or an explicit Enable click
                # reaches this path. The terminal still owns licence consent.
                self.open()
                self.begin_setup(target)
        except (OSError, ValueError) as error:
            self.status = str(error)[:180]
            self.open()
        finally:
            output.close()

    def finish_setup(self, outcome):
        code = outcome.get('exit_code')
        report = outcome.get('report')
        if type(code) is int and code == 0 and isinstance(report, dict):
            read_status(json.dumps(report).encode('utf-8'), code)
            self.save(answer='yes')
            self.ready = True
            self.status = ready_detail(report)
        else:
            self.ready = False
            self.status = 'Setup was cancelled or failed. Choose Enable to retry.'

    def tick(self, _now):
        if self.pending and not self.other_offer_busy():
            pending, self.pending = self.pending, None
            if pending == 'offer':
                self.open()
            else:
                try:
                    self.enable()
                except (OSError, ValueError) as error:
                    self.status = str(error)[:180]
                    self.open()
        if self.probe:
            self.finish_probe()
        if self.job:
            directory, result, started = self.job
            if os.path.isfile(result):
                try:
                    with open(result, 'rb') as saved:
                        data = saved.read(MAX_OUTPUT + 1)
                    if len(data) > MAX_OUTPUT:
                        raise ValueError('The setup result was too large.')
                    self.finish_setup(json.loads(data))
                except (OSError, ValueError, AttributeError) as error:
                    self.status = f'Could not verify workflow setup: {str(error)[:100]}'
                self.job = None
                directory.cleanup()
                self.open()
            elif worker_active(result) is False:
                self.job = None
                directory.cleanup()
                self.status = 'The setup terminal closed before finishing. Choose Enable to retry.'
                self.open()
            elif time.monotonic() - started > SETUP_TIMEOUT:
                # A slow or unresolved terminal is not proof that its download
                # stopped. Keep the job and retry guard until it reports/exits.
                self.status = 'Setup is still pending. Finish or close its terminal first.'
                self.open()

    def close(self):
        if self.probe:
            process, output, _started, _target = self.probe
            try:
                stop(process)
            finally:
                output.close()
                self.probe = None
        if self.job:
            self.job[0].cleanup()
            self.job = None
        if self.tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.tick)


def controller(desk):
    if getattr(desk, 'workflows_offer', None) is None:
        desk.workflows_offer = Controller(desk)
    return desk.workflows_offer


def prepare(result, target):
    """Use the host-selected installer with its ordinary interactive consent."""
    outcome = {'exit_code': 1, 'report': None}
    worker = Path(result).with_name('worker.json')
    worker.write_text(json.dumps({'pid': os.getpid(), 'start': process_stamp(os.getpid())}) + '\n')
    try:
        code = subprocess.call([*target, 'workflows', 'setup'])
        outcome['exit_code'] = code
        if code == 0:
            report = checked_status(target)
            if not report['ready']:
                raise ValueError('Workflow models are still unavailable after setup.')
            outcome['report'] = report
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        outcome = {'exit_code': 1, 'report': None, 'detail': str(error)[:180]}
        print(error, file=sys.stderr)
    except KeyboardInterrupt:
        outcome = {'exit_code': 130, 'report': None}
    path = Path(result)
    try:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(outcome) + '\n')
        temporary.replace(path)
    except OSError:
        pass  # Desktop closed while its independently visible terminal ran.
    return outcome['exit_code']


if __name__ == '__main__':
    if len(sys.argv) < 4 or sys.argv[1] != '--prepare':
        raise SystemExit('usage: workflows_offer.py --prepare RESULT LAUNCHER [ARG ...]')
    raise SystemExit(prepare(sys.argv[2], sys.argv[3:]))
