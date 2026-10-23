"""Document UI lifecycle and explicit shared-voice opt-in."""
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest import mock
import harness as H
import apps
from apps.documentreader import DocumentReader
from document_reader import Session, KristinSetup
import system_voice

with H.desktop_dir():
    desk=H.make_desk()
    with mock.patch('apps.documentreader.Session') as factory:
        session=factory.return_value
        session.exited=False
        session.poll.return_value=[]
        window=DocumentReader(desk)
        desk.wm.add(window)
        assert not window.play.enabled
        factory.assert_not_called()  # Opening the UI does not download or speak.
        with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']):
            window.load('/tmp/a document.md')
        factory.assert_called_once_with(['/fixture/kilix','tts'],'/tmp/a document.md')
        window.event({'state':'ready','index':1,'total':4,'text':'First passage.','engine':'piper'})
        assert window.play.enabled and not window.pause.enabled
        assert window.preview.text()=='First passage.'
        window.command('p');session.command.assert_called_with('p')
        window.event({'state':'playing','index':1,'total':4,'text':'First passage.','engine':'piper'})
        assert window.pause.enabled and not window.play.enabled
        window.event({'state':'paused','index':1,'total':4,'text':'First passage.','engine':'piper'})
        assert window.play.text=='Resume'
        # Cancel means no setup/download/default mutation.
        with mock.patch('apps.documentreader.KristinSetup') as setup, mock.patch('apps.documentreader.wm.msgbox') as dialog:
            window.enable_kristin();dialog.call_args.kwargs['cb']('Cancel')
            setup.assert_not_called()
            window.enable_kristin();dialog.call_args.kwargs['cb']('Enable')
            setup.assert_called_once()
            setup.return_value.poll.return_value=0
            window.tick(0)
            assert window.setup is None and window.play.enabled
        window.close()
        session.close.assert_called_once()
        assert window.tick not in desk.tick_hooks
    apps.open(desk,'documentreader')
    assert H.find_window(desk,'DocumentReader')
    H.find_window(desk,'DocumentReader').close()

# Setup runs through the terminal and writes a result only after CLI returns.
with H.desktop_dir():
    desk=H.make_desk()
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), mock.patch.object(desk.shell,'_tab',return_value=True) as tab:
        setup=KristinSetup(desk.shell)
        assert '--prepare-kristin' in tab.call_args.args[0]
        assert setup.poll() is None
        with mock.patch('system_voice.subprocess.call',return_value=3) as call:
            system_voice.prepare(str(setup.result), ['/fixture/kilix','tts'], '--enable-kristin')
            call.assert_called_once_with(['/fixture/kilix','tts','--enable-kristin'])
        assert setup.poll()==3
        setup.close()

# Exercise actual pipes: partial JSON, control command and owner cleanup.
with H.desktop_dir() as directory:
    path=Path(directory)/'reader.py'
    path.write_text('import json,sys\nprint(json.dumps({"state":"ready"}),flush=True)\ncommand=sys.stdin.buffer.read(1)\nprint(json.dumps({"state":"paused","command":command.decode()}),flush=True)\nsys.stdin.buffer.read()\n')
    session=Session([sys.executable,str(path)], '/tmp/book.txt')
    def events():
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            result=session.poll()
            if result:return result
            time.sleep(.01)
        raise AssertionError('reader status timeout')
    assert events()[0]['state']=='ready'
    session.command('a')
    assert events()[0]['command']=='a'
    process=session.process
    session.close()
    assert process.poll() is not None
print('ok')
