"""One startup window for the shared Kilix model wizard."""
from concurrent.futures import Future
import os
from pathlib import Path
import sys
import textwrap
import time

import widgets as W
import wm
import model_wizard as backend
from model_discovery import Discovery


class ModelWizard(wm.Window):
    ROWS = 5

    def __init__(self, desk):
        super().__init__(desk, 'Model setup', 650, 440, icon='speak', resizable=False)
        self.pages = []
        self.index = 0
        self.offset = 0
        self.selected = set()
        self.job = None
        self.error = ''
        self.batch = False
        self.log_path = ''
        try:
            previous = backend.read_json(backend.state_root() / 'model-wizard-last-result.json')
            if previous.get('ok') is False:
                self.error = previous.get('error', '')
                self.log_path = previous.get('error_log', '')
        except (OSError, ValueError):
            pass
        self._closed = False
        try:
            self.future = Discovery()
        except Exception as error:
            # Present and log startup errors through the ordinary failure path.
            self.future = Future()
            self.future.set_exception(error)
        self.add(W.Label(18, 20, 'Checking available models and sizing recommendations…'))
        self.add(W.Button(510, 365, 110, 26, 'Later', cb=self.close))
        self.desk.tick_hooks.append(self.refresh)
        self.on_close = self.cleanup

    @property
    def page(self):
        return self.pages[self.index]

    def text(self, value, y, width=88, limit=3):
        lines = textwrap.wrap(value, width) or ['']
        for line in lines[:limit]:
            self.add(W.Label(18, y, line))
            y += 17
        return y

    def show_page(self):
        for widget in list(self.widgets):
            self.remove(widget)
        page = self.page
        self.add(W.Label(18, 14, f'{page["title"]}  ({self.index + 1} of {len(self.pages)})'))
        self.text(page['recommendation'], 40, limit=3)
        self.add(W.Label(18, 99, 'Check the models to install. The recommended/default model starts checked.'))
        self.checks = []
        for position, row in enumerate(page['models'][self.offset:self.offset + self.ROWS]):
            y = 124 + position * 37
            label = row['label']
            if row['id'] == page['default']:
                label += ' (default)'
            checkbox = self.add(W.Checkbox(18, y, label[:87], row['id'] in self.selected,
                cb=lambda checked, key=row['id']: self.toggle(key, checked)))
            self.checks.append(checkbox)
            detail = f'Download {backend.size_text(row["download_bytes"])}; disk {backend.size_text(row["installed_bytes"])}'
            memory = backend.memory_text(row)
            if memory:
                detail += f'; {memory}'
            self.add(W.Label(36, y + 17, detail))
        if len(page['models']) > self.ROWS:
            self.add(W.Button(18, 312, 120, 22, 'More models', cb=self.more))
            self.add(W.Label(150, 315, 'Checked models on other rows remain selected.'))
        self.status = self.add(W.Label(18, 341, self.error[:88]))
        self.accept_button = self.add(W.Button(18, 370, 160, 26, 'Accept checked', cb=self.accept))
        self.decline_button = self.add(W.Button(190, 370, 125, 26, 'No thanks', cb=self.decline))
        self.continue_button = self.add(W.Button(330, 370, 125, 26, 'Continue', cb=self.advance))
        self.add(W.Button(490, 370, 125, 26, 'Later', cb=self.close))
        self.update_controls()
        self.set_focus(self.checks[0] if self.checks else self.decline_button)
        self.invalidate()

    def update_controls(self):
        answered = backend.answers().get(self.page['id'], {}).get('answer') in ('yes', 'no')
        busy = self.job is not None
        self.accept_button.enabled = bool(self.selected) and not busy and not answered
        self.decline_button.enabled = not busy and not answered
        self.continue_button.enabled = answered and not busy
        for checkbox in self.checks:
            checkbox.enabled = not busy and not answered
        if not answered and not busy and not self.error:
            rows = [row for row in self.page['models'] if row['id'] in self.selected]
            download = sum(row['download_bytes'] for row in rows)
            peak = sum(row['installed_bytes'] for row in rows) + max((row['temporary_bytes'] for row in rows), default=0)
            free = self.page.get('disk_available_bytes')
            self.status.set(f'Selected: {backend.size_text(download)} download; up to {backend.size_text(peak)} disk.'
                            + (f' Free: {backend.size_text(free)}.' if free is not None else ''))
        if answered and not self.error:
            self.status.set('Choice saved. Choose Continue for the next unanswered page.')
        self.invalidate()

    def toggle(self, key, checked):
        if checked: self.selected.add(key)
        else: self.selected.discard(key)
        self.update_controls()

    def more(self):
        self.offset += self.ROWS
        if self.offset >= len(self.page['models']): self.offset = 0
        self.show_page()

    def accept(self):
        if not self.accept_button.enabled: return
        selected = [row['id'] for row in self.page['models'] if row['id'] in self.selected]
        if self.page['default'] in selected:
            selected.remove(self.page['default']); selected.insert(0, self.page['default'])
        try:
            backend.apply(self.page['id'], selected, 'yes')
            self.error = ''
        except Exception as error:
            self.report_failure(error, 'save model choice')
            self.status.set(self.error[:88])
        self.update_controls()

    def show_batch(self):
        self.batch = True
        self._batch_state = (repr(backend.pending()), self.error, self.job is not None)
        for widget in list(self.widgets): self.remove(widget)
        plans = backend.pending()
        count = sum(len(plan['models']) for plan in plans.values())
        self.add(W.Label(18, 20, 'Model choices saved'))
        self.text(f'{count} selected models await licence review and installation. '
                  'Licences are grouped at the end, with one Yes/No question naming all '
                  'affected models. Declining a licence skips those models.', 55, limit=5)
        self.text('The agreement terminal opens as a box inside this desktop. '
                  'Closing it leaves unfinished setup available for retry.', 155, limit=3)
        self.text(self.error, 215, limit=3)
        if self.log_path:
            self.text('Diagnostic log: ' + self.log_path, 272, limit=3)
        self.status = self.add(W.Label(18, 328, ''))
        self.review_button = self.add(W.Button(18, 350, 235, 28, 'Review licences and install', cb=self.start_batch))
        self.review_button.enabled = bool(plans) and self.job is None
        self.finish_button = self.add(W.Button(280, 350, 130, 28, 'Finish' if not plans else 'Later', cb=self.close))
        if not plans and not self.error: self.status.set('All model setup choices are complete.')
        self.invalidate()

    def start_batch(self):
        if self.job or not backend.pending(): return
        try:
            directory = backend.new_run_directory()
            result = str(directory / 'result.json')
            self.log_path = str(directory / 'transcript.log')
            command = [sys.executable, backend.__file__, 'finish', '--result', result]
            from apps.licenseterminal import open_window
            open_window(self.desk, command, log_path=self.log_path)
        except Exception as error:
            self.report_failure(error, 'start installer', locals().get('directory'))
        else:
            self.job = (directory, result, time.monotonic())
            self.error = 'Answer the grouped licence questions in the desktop terminal.'
        self.show_batch()

    def report_failure(self, error, phase, directory=None):
        outcome = backend.record_failure(error, phase=phase, directory=directory)
        self.error = outcome['error']
        self.log_path = outcome.get('error_log', self.log_path)

    def decline(self):
        if not self.decline_button.enabled: return
        try:
            backend.apply(self.page['id'], [], 'no')
            self.error = ''
            self.sync_controllers()
        except Exception as error:
            self.report_failure(error, 'decline model choice')
            self.status.set(self.error[:88])
        self.update_controls()

    def sync_controllers(self):
        # Existing settings windows and startup speech use the same saved choice.
        for name in ('system_voice', 'dictation_offer', 'workflows_offer'):
            controller = getattr(self.desk, name, None)
            if controller is not None:
                controller.state.update(controller.store.load_dict())
        voice = getattr(self.desk, 'system_voice', None)
        if voice is not None and (self.batch or self.page['id'] == 'speech'):
            if voice.state.get('enabled'): voice.start()
            else: voice.stop()

    def advance(self):
        if not self.continue_button.enabled: return
        decisions = backend.answers()
        self.index += 1
        while self.index < len(self.pages) and decisions.get(self.page['id'], {}).get('answer') in ('yes', 'no'):
            self.index += 1
        if self.index == len(self.pages):
            self.error = ''
            self.show_batch()
            return
        self.selected = {self.page['default']} if self.page['default'] else set()
        self.offset = 0
        self.error = ''
        self.show_page()

    def refresh(self, _now):
        if self._closed:
            return
        if self.future is not None:
            if not self.future.done(): return
            future, self.future = self.future, None
            try:
                self.pages = future.result()
                if not self.pages:
                    if backend.pending(): self.show_batch()
                    else: self.close()
                    return
                self.selected = {self.page['default']} if self.page['default'] else set()
                self.show_page()
            except Exception as error:
                self.report_failure(error, 'load model setup',
                                    getattr(future, 'directory', None))
                for widget in list(self.widgets): self.remove(widget)
                self.text('Model setup could not be loaded: ' + self.error, 20, limit=8)
                if self.log_path:
                    self.text('Diagnostic log: ' + self.log_path, 190, limit=5)
                self.add(W.Button(18, 365, 110, 26, 'Close', cb=self.close))
                self.invalidate()
            return
        if self.job:
            directory, result, started = self.job
            from workflows_offer import worker_active
            if Path(result).exists():
                try:
                    outcome = backend.read_json(result)
                    self.error = '' if outcome.get('ok') is True else outcome.get('error', 'Setup did not finish.')
                    self.log_path = outcome.get('error_log') or self.log_path
                except (OSError, ValueError) as error:
                    self.report_failure(error, 'read installer result', directory)
                self.job = None
                self.sync_controllers()
                self.desk.shell._application_scan_after = 0
                self.status.set(self.error[:88])
            elif worker_active(result) is False:
                self.job = None
                self.report_failure(RuntimeError(
                    'Setup terminal closed before finishing. Review licences to retry.'),
                    'installer exited without a result', directory)
                self.status.set(self.error)
            elif time.monotonic() - started > 30 and not Path(result).with_name('worker.json').exists():
                self.job = None
                self.report_failure(RuntimeError(
                    'Setup did not start. Review licences to retry.'),
                    'installer did not start', directory)
                self.status.set(self.error)
        if self.batch:
            if (repr(backend.pending()), self.error, self.job is not None) != self._batch_state:
                self.show_batch()
        elif self.pages and hasattr(self, 'status'):
            self.update_controls()

    def close(self):
        if self.job:
            self.status.set('Finish or close the setup terminal before closing this window.')
            return
        super().close()

    def cleanup(self):
        if self.refresh in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.refresh)
        self._closed = True
        if self.future is not None:
            future, self.future = self.future, None
            close = getattr(future, 'close', None)
            if close is not None:
                close()
            elif future.done():
                # A startup failure is held in a completed Future with no
                # worker to stop. Retain it even if closed before a UI tick.
                try:
                    future.result()
                except Exception as error:
                    self.report_failure(error, 'load model setup')
            else:
                future.cancel()


def open_window(desk):
    for window in desk.wm.windows:
        if isinstance(window, ModelWizard):
            desk.wm.activate(window)
            return window
    window = ModelWizard(desk)
    desk.wm.add(window)
    return window


def startup(desk):
    from system_voice import controller
    voice = controller(desk)
    if voice.state.get('enabled') is True:
        voice.start()
    value = os.environ.get('KILIX_MODEL_WIZARD_OFFER')
    enabled = value == '1' if value is not None else os.path.isfile('/etc/plebian-os/build-info.env')
    if enabled:
        if not desk.shell.state.get('wallpaper_offer_answered', False):
            from apps.wallpaperoffer import open_window as offer_wallpaper
            offer_wallpaper(desk, lambda: open_window(desk))
        else:
            open_window(desk)
