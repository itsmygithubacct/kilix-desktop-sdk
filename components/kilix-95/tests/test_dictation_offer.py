"""Dictation offer: asked at every start until yes or no, after the voice offer."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock
import harness as H
import dictation_offer as D
import system_voice as V

TAB = ['/fixture/kilix', 'stt']


def result(offer, outcome):
    Path(offer.job[1]).write_text(json.dumps(outcome))
    offer.tick(0)


with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_DICTATION_OFFER': '1',
                                                   'KILIX_SYSTEM_VOICE_OFFER': '0'}):
    desk = H.make_desk()
    offer = D.controller(desk)
    offer.startup()
    window = H.find_window(desk, 'DictationOffer')
    assert window and offer.state['answer'] is None
    # Closing without answering ("Later") asks again at the next start.
    window.close()
    assert H.find_window(desk, 'DictationOffer') is None
    later = D.Controller(desk)
    later.startup()
    assert H.find_window(desk, 'DictationOffer')
    H.find_window(desk, 'DictationOffer').close()
    later.close()

    with mock.patch.object(desk.shell, 'kilix_stt_target', return_value=TAB), \
            mock.patch.object(desk.shell, '_tab', return_value=True) as tab:
        offer.accept()
        command = tab.call_args.args[0]
        assert command[1:4] == [D.__file__, '--prepare', offer.job[1]] and command[4:] == TAB
        try:
            offer.accept()
        except ValueError:
            pass
        else:
            raise AssertionError('a second setup started while one was open')
        # A failed setup leaves the question open for the next start.
        result(offer, {'status': 'failed', 'model': None, 'detail': 'No network.'})
        assert offer.state['answer'] is None and offer.job is None
        assert 'No network.' in offer.status
        assert D.Controller(desk).state['answer'] is None
        offer.accept()
        result(offer, {'status': 'ready', 'model': 'whisper-small-en'})
        assert offer.state == {'answer': 'yes', 'model': 'whisper-small-en'}
        assert 'Ctrl+Shift+D' in offer.status
    # Answered yes: the next start does not ask.
    for window in list(desk.wm.windows):
        if type(window).__name__ == 'DictationOffer':
            window.close()
    again = D.Controller(desk)
    assert again.state['answer'] == 'yes'
    again.startup()
    again.tick(0)
    assert H.find_window(desk, 'DictationOffer') is None
    again.close()
    offer.close()

# Declining, here or in the setup terminal, is final.
with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_DICTATION_OFFER': '1',
                                                   'KILIX_SYSTEM_VOICE_OFFER': '0'}):
    desk = H.make_desk()
    offer = D.controller(desk)
    offer.startup()
    H.find_window(desk, 'DictationOffer').decline()
    assert H.find_window(desk, 'DictationOffer') is None
    later = D.Controller(desk)
    assert later.state['answer'] == 'no'
    later.startup()
    later.tick(0)
    assert H.find_window(desk, 'DictationOffer') is None
    later.close(); offer.close()

with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_DICTATION_OFFER': '1',
                                                   'KILIX_SYSTEM_VOICE_OFFER': '0'}):
    desk = H.make_desk()
    offer = D.controller(desk)
    with mock.patch.object(desk.shell, 'kilix_stt_target', return_value=TAB), \
            mock.patch.object(desk.shell, '_tab', return_value=True):
        offer.accept()
        result(offer, {'status': 'declined', 'model': None})
    assert D.Controller(desk).state['answer'] == 'no'
    # An unknown stored answer is treated as unanswered, never as yes or no.
    offer.save(answer='maybe')
    assert D.Controller(desk).state['answer'] is None
    offer.close()

# Off unless this is a Plebian OS install (or the override says so).
with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_DICTATION_OFFER': '0'}):
    desk = H.make_desk()
    offer = D.controller(desk)
    offer.startup()
    offer.tick(0)
    assert H.find_window(desk, 'DictationOffer') is None
    offer.close()

# The two first-boot offers never stack: dictation waits for the voice offer.
with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_DICTATION_OFFER': '1',
                                                   'KILIX_SYSTEM_VOICE_OFFER': '1'}):
    desk = H.make_desk()
    voice = V.controller(desk)
    voice.startup()
    offer = D.controller(desk)
    offer.startup()
    assert H.find_window(desk, 'SystemVoice') and H.find_window(desk, 'DictationOffer') is None
    offer.tick(0)
    assert H.find_window(desk, 'DictationOffer') is None
    voice.job = (mock.Mock(), 'unused', 0)
    H.find_window(desk, 'SystemVoice').close()
    offer.tick(0)
    assert H.find_window(desk, 'DictationOffer') is None   # voice setup still running
    voice.job = None
    offer.tick(0)
    assert H.find_window(desk, 'DictationOffer')
    offer.close(); voice.close()

# The terminal wrapper always leaves a result, even when the launcher cannot.
with tempfile.TemporaryDirectory() as tmp:
    outer = os.path.join(tmp, 'result.json')
    launcher = os.path.join(tmp, 'launcher')
    Path(launcher).write_text('#!/bin/sh\n[ "$1 $2" = "--setup-default --result" ] || exit 9\n'
                              'printf \'{"status": "ready", "model": "whisper-small-en"}\' > "$3"\n')
    os.chmod(launcher, 0o755)
    assert D.prepare(outer, [launcher]) == 0
    assert json.loads(Path(outer).read_text()) == {'status': 'ready', 'model': 'whisper-small-en',
                                                   'exit_code': 0}
    os.unlink(outer)
    Path(launcher).write_text('#!/bin/sh\nexit 2\n')
    os.unlink(os.path.join(tmp, 'setup-result.json'))
    with mock.patch('builtins.input', return_value=''):
        assert D.prepare(outer, [launcher]) == 2
    assert json.loads(Path(outer).read_text())['status'] == 'failed'
    with mock.patch('builtins.input', return_value=''):
        D.prepare(outer, [os.path.join(tmp, 'missing')])
    assert json.loads(Path(outer).read_text())['status'] == 'failed'
print('ok')
