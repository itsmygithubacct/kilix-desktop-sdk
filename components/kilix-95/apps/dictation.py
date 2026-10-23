"""First-boot offer to set up dictation with the recommended model."""
import widgets as W
import wm
from dictation_offer import HOTKEY, controller


class DictationOffer(wm.Window):
    def __init__(self, desk):
        super().__init__(desk, 'Set up dictation', 510, 235,
                         icon='speak', resizable=False)
        self.offer = controller(desk)
        self.add(W.Label(16, 16, 'Type with your voice: dictate into any Kilix pane.'))
        self.add(W.Label(16, 40, 'Setup installs the recommended speech model for this'))
        self.add(W.Label(16, 58, 'computer after showing its licence. Speech stays local.'))
        self.add(W.Label(16, 82, f'Once set up, press {HOTKEY} to start or stop dictating.'))
        self.status = self.add(W.Label(16, 118, self.offer.status))
        self.setup = self.add(W.Button(16, 157, 164, 26, 'Set up dictation', cb=self.accept))
        self.add(W.Button(190, 157, 136, 26, 'No thanks', cb=self.decline))
        self.add(W.Button(336, 157, 100, 26, 'Later', cb=self.close))
        self.desk.tick_hooks.append(self.refresh)
        self.on_close = self.cleanup

    def refresh(self, _now):
        state = (self.offer.status, self.offer.state['answer'], bool(self.offer.job))
        if state == getattr(self, '_last_status', None):
            return
        self._last_status = state
        self.status.set(self.offer.status[:76])
        self.setup.enabled = not self.offer.job and self.offer.state['answer'] != 'yes'
        self.invalidate()

    def accept(self):
        try:
            self.offer.accept()
        except Exception as error:
            wm.msgbox(self.desk, 'Dictation', str(error), icon='error')

    def decline(self):
        try:
            self.offer.decline()
        except Exception as error:
            wm.msgbox(self.desk, 'Dictation', str(error), icon='error')
            return
        self.close()

    def cleanup(self):
        if self.refresh in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.refresh)


def open_window(desk):
    for window in desk.wm.windows:
        if isinstance(window, DictationOffer):
            desk.wm.activate(window)
            return window
    window = DictationOffer(desk)
    desk.wm.add(window)
    return window
