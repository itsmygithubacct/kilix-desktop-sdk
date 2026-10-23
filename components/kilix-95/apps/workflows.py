"""Opt-in setup for Kilix Workflows and their local language models."""
import widgets as W
import wm
from workflows_offer import controller


class WorkflowsOffer(wm.Window):
    def __init__(self, desk):
        super().__init__(desk, 'Kilix Workflows', 550, 230,
                         icon='terminal', resizable=False)
        self.offer = controller(desk)
        busy = bool(self.offer.job or self.offer.probe)
        enabled = (self.offer.state.get('answer') == 'yes'
                   or bool(self.offer.ready))
        self.add(W.Label(16, 16, 'Enable local models for Kilix workflows that use them.'))
        self.add(W.Label(16, 40, 'Grammar and direct actions work without downloads.'))
        self.add(W.Label(16, 64, 'Verified model files already here are reused.'))
        self.add(W.Label(16, 88, 'Setup shows licences before fetching missing models.'))
        self.add(W.Label(16, 106, 'Missing models are offered again after updates.'))
        self.status = self.add(W.Label(16, 137, self.offer.status[:68]))
        self.enable_button = self.add(W.Button(
            16, 174, 190, 26,
            'Check models' if enabled else 'Enable Kilix Workflows',
            cb=self.enable))
        self.decision_button = self.add(W.Button(
            218, 174, 150, 26,
            'Turn off' if enabled else 'No thanks', cb=self.decline))
        self.close_button = self.add(W.Button(
            382, 174, 110, 26,
            'Close' if enabled else 'Later', cb=self.close))
        self.enable_button.enabled = not busy
        self.decision_button.enabled = not busy
        self.desk.tick_hooks.append(self.refresh)
        self.on_close = self.cleanup
        self.refresh(0)

    def refresh(self, _now):
        busy = bool(self.offer.job or self.offer.probe)
        enabled = self.offer.state.get('answer') == 'yes' or bool(self.offer.ready)
        state = (self.offer.status, self.offer.state.get('answer'),
                 bool(self.offer.ready), busy)
        if state == getattr(self, '_last_status', None):
            return
        self._last_status = state
        self.status.set(self.offer.status[:68])
        self.enable_button.text = (
            'Check models' if enabled else 'Enable Kilix Workflows')
        self.decision_button.text = 'Turn off' if enabled else 'No thanks'
        self.close_button.text = 'Close' if enabled else 'Later'
        self.enable_button.enabled = not busy
        self.decision_button.enabled = not busy
        self.invalidate()

    def enable(self):
        try:
            self.offer.enable()
        except Exception as error:
            wm.msgbox(self.desk, 'Kilix Workflows', str(error), icon='error')

    def decline(self):
        try:
            self.offer.decline()
        except Exception as error:
            wm.msgbox(self.desk, 'Kilix Workflows', str(error), icon='error')
            return
        self.close()

    def cleanup(self):
        if self.refresh in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.refresh)


def open_window(desk):
    for window in desk.wm.windows:
        if isinstance(window, WorkflowsOffer):
            desk.wm.activate(window)
            return window
    window = WorkflowsOffer(desk)
    desk.wm.add(window)
    return window
