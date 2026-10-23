"""First-launch offer and persistent startup greeting controls."""
import widgets as W
import wm
from system_voice import controller


class SystemVoice(wm.Window):
    def __init__(self, desk):
        super().__init__(desk, 'Enable system voice', 510, 255,
                         icon='speak', resizable=False)
        self.voice = controller(desk)
        self.add(W.Label(16, 16, 'Let Piper Kristin greet you when Kilix 95 starts.'))
        self.add(W.Label(16, 40, 'The voice downloads once and stays ready during your session.'))
        self.add(W.Label(16, 58, 'Also speaks system health, power and update messages.'))
        self.add(W.Label(16, 76, 'Startup message (leave blank for a silent startup):'))
        self.message = self.add(W.TextField(16, 98, 472, self.voice.state['greeting']))
        self.status = self.add(W.Label(16, 138, self.voice.status))
        self.apply = self.add(W.Button(16, 177, 164, 26,
            'Save' if self.voice.state['enabled'] else 'Enable system voice', cb=self.enable))
        self.disable_button = self.add(W.Button(190, 177, 136, 26,
            'Turn off' if self.voice.state['enabled'] else 'Not now', cb=self.disable))
        self.add(W.Button(336, 177, 100, 26, 'Close', cb=self.close))
        self.desk.tick_hooks.append(self.refresh)
        self.on_close = self.cleanup
        self.set_focus(self.message)

    def refresh(self, _now):
        # Keep one concise line in the dialog; errors remain available as a box.
        state = (self.voice.status, self.voice.state['enabled'], bool(self.voice.job))
        if state == getattr(self, '_last_status', None):
            return
        self._last_status = state
        self.status.set(self.voice.status[:76])
        self.apply.text = 'Save' if self.voice.state['enabled'] else 'Enable system voice'
        self.disable_button.text = 'Turn off' if self.voice.state['enabled'] else 'Not now'
        self.apply.enabled = not bool(self.voice.job)
        self.invalidate()

    def enable(self):
        try:
            self.voice.enable(self.message.text)
        except Exception as error:
            wm.msgbox(self.desk, 'System voice', str(error), icon='error')

    def disable(self):
        try:
            self.voice.disable()
        except Exception as error:
            wm.msgbox(self.desk, 'System voice', str(error), icon='error')
            return
        self.close()

    def cleanup(self):
        if self.refresh in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.refresh)


def open_window(desk):
    for window in desk.wm.windows:
        if isinstance(window, SystemVoice):
            desk.wm.activate(window)
            return window
    window = SystemVoice(desk)
    desk.wm.add(window)
    return window
