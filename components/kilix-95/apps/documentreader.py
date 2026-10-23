"""Read local documents with the shared Kilix read-aloud voice."""
import os

import filedialog
import widgets as W
import wm
from apps.manual import _ReadOnlyTextArea
from document_reader import KristinSetup, Session


class DocumentReader(wm.Window):
    def __init__(self, desk, path=None):
        super().__init__(desk, 'Document Reader', 640, 420, icon='speak')
        self.min_w, self.min_h = 610, 380
        self.session = self.setup = None
        self.path = None
        self.state = 'empty'
        self.add(W.Button(12, 12, 100, 26, 'Open…', cb=self.choose))
        self.add(W.Button(124, 12, 218, 26, 'Use Kristin for read-aloud…', cb=self.enable_kristin))
        self.add(W.Button(354, 12, 130, 26, 'Voice settings…', cb=desk.shell.open_kilix_tts))
        self.filename = self.add(W.Label(12, 50, 'Open a TXT, Markdown, or PDF document.'))
        self.voice = self.add(W.Label(12, 72, 'Uses your shared read-aloud voice. Kristin is optional.'))
        self.preview = self.add(_ReadOnlyTextArea(12, 98, 600, 194))
        self.preview.set_text('The current passage will appear here.\n\n'
                              'Markdown formatting and fenced code are skipped.\n'
                              'PDFs need selectable text; scanned pages need OCR.')
        self.play = self.add(W.Button(12, 306, 90, 26, 'Play', cb=lambda: self.command('p')))
        self.pause = self.add(W.Button(110, 306, 90, 26, 'Pause', cb=lambda: self.command('a')))
        self.stop = self.add(W.Button(208, 306, 90, 26, 'Stop', cb=lambda: self.command('s')))
        self.previous = self.add(W.Button(306, 306, 90, 26, 'Previous', cb=lambda: self.command('b')))
        self.next = self.add(W.Button(404, 306, 90, 26, 'Next', cb=lambda: self.command('n')))
        self.status = self.add(W.Label(12, 344, 'Ready. Pause resumes from the start of the passage.'))
        self.buttons = [self.play, self.pause, self.stop, self.previous, self.next]
        self.controls(False)
        self.desk.tick_hooks.append(self.tick)
        self.on_close = self.cleanup
        self.on_resize()
        if path:
            self.load(path)

    def on_resize(self):
        cw, ch = self.client_size()
        self.preview.w, self.preview.h = cw-24, max(90, ch-192)
        for button in self.buttons:
            button.y = ch-80
        self.status.y = ch-42

    def controls(self, ready):
        for button in self.buttons:
            button.enabled = ready
        self.play.text = 'Resume' if self.state == 'paused' else 'Play'
        self.play.enabled = ready and self.state not in {'loading', 'playing'}
        self.pause.enabled = ready and self.state in {'loading', 'playing'}
        self.invalidate()

    def choose(self):
        filedialog.open_file(self.desk, 'Read a document', lambda path: path and self.load(path),
                             start=os.path.dirname(self.path) if self.path else None,
                             filters=[('Readable documents', '*.txt;*.md;*.markdown;*.pdf')])

    def load(self, path):
        self.end_session()
        target = self.desk.shell.kilix_tts_target()
        if not target:
            self.failure('The Kilix speech launcher is not installed.')
            return
        self.path = os.path.abspath(os.path.expanduser(path))
        self.filename.set(os.path.basename(self.path)[:88])
        self.title = os.path.basename(self.path) + ' - Document Reader'
        self.state = 'opening'
        self.status.set('Opening document…')
        self.controls(False)
        try:
            self.session = Session(target, self.path)
        except Exception as error:
            self.failure(str(error))

    def command(self, command):
        if self.session:
            try:
                self.session.command(command)
            except (OSError, ValueError) as error:
                self.failure(str(error))

    def enable_kristin(self):
        if self.setup:
            return
        def confirmed(answer):
            if answer != 'Enable':
                return
            self.command('a')
            try:
                self.setup = KristinSetup(self.desk.shell)
                self.status.set('Finish the download notice in the Kristin setup terminal.')
            except Exception as error:
                self.failure(str(error))
        wm.msgbox(self.desk, 'Use Piper Kristin?',
                  'Download Piper Kristin and make it your default voice for\n'
                  'documents and Kilix read-aloud?\n\n'
                  'Setup opens a terminal with the voice download notice.\n'
                  'Your preference changes only after setup succeeds.\n'
                  'You can change it later in Voice settings.',
                  icon='speak', buttons=('Enable', 'Cancel'), cb=confirmed)

    def event(self, event):
        state = event.get('state', 'error')
        if state == 'closed':
            if self.state != 'error':
                self.failure(event.get('error') or 'Reader stopped. Open the document again to retry.')
            self.controls(False)
            return
        self.state = state
        if event.get('error'):
            self.failure(event['error'])
            return
        if 'text' in event:
            self.preview.set_text(event['text'])
            engine = {'piper': 'Piper Kristin', 'espeak': 'eSpeak', 'mbrola': 'MBROLA'}.get(event.get('engine'), event.get('engine', 'default'))
            self.voice.set('Read-aloud voice: ' + engine)
            label = {'loading':'Preparing speech', 'playing':'Reading', 'ready':'Ready',
                     'paused':'Paused — Resume repeats this passage', 'finished':'Finished — Play to read again'}.get(state, state)
            self.status.set(f"{label} · Passage {event['index']} of {event['total']}")
        self.controls(state in {'ready', 'loading', 'playing', 'paused', 'finished'})

    def tick(self, _now):
        try:
            if self.session and not self.session.exited:
                for event in self.session.poll():
                    self.event(event)
            if self.setup:
                code = self.setup.poll()
                if code is not None:
                    self.setup.close()
                    self.setup = None
                    if code == 0:
                        self.voice.set('Read-aloud voice: Piper Kristin')
                        self.status.set('Kristin enabled. Press Play to read your document.')
                        if self.session and not self.session.exited:
                            self.state = 'paused'
                            self.controls(True)
                    else:
                        wm.msgbox(self.desk, 'Kristin setup', 'Setup was cancelled or failed. Your voice preference was not changed.', icon='warn')
        except Exception as error:
            self.end_session()
            self.failure(str(error))

    def failure(self, message):
        self.state = 'error'
        self.status.set('Could not read the document. See the message for details.')
        self.controls(False)
        wm.msgbox(self.desk, 'Document Reader', message, icon='error')

    def end_session(self):
        if self.session:
            self.session.close()
            self.session = None

    def cleanup(self):
        self.end_session()
        if self.setup:
            self.setup.close()
            self.setup = None
        if self.tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.tick)
