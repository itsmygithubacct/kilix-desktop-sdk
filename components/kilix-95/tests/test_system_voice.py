"""First-run offer, opt-in setup, durable greeting and desktop ownership."""
import json
import os
from pathlib import Path
from unittest import mock
import harness as H
import system_voice as V

with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_SYSTEM_VOICE_OFFER':'1'}):
    desk=H.make_desk()
    voice=V.controller(desk)
    with mock.patch.object(voice,'start') as start:
        voice.startup()
        assert H.find_window(desk,'SystemVoice')
        assert voice.state['offered'] and not voice.state['enabled']
        assert voice.state['greeting']=='hello'
        start.assert_not_called()
    count=len(desk.wm.windows)
    voice.startup()
    assert len(desk.wm.windows)==count
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), mock.patch.object(desk.shell,'_tab',return_value=True):
        voice.enable('Hello from home')
        assert not voice.state['enabled']
        Path(voice.job[1]).write_text(json.dumps({'exit_code':3}))
        voice.tick(0)
        assert not voice.state['enabled'] and voice.job is None
        voice.enable('Hello from home')
        Path(voice.job[1]).write_text(json.dumps({'exit_code':0}))
        with mock.patch.object(voice,'start') as start:
            voice.tick(0)
            start.assert_called_once()
    assert voice.state['enabled'] and voice.state['greeting']=='Hello from home'
    # A later desktop launch reads the same durable preference and greets.
    later=V.Controller(desk)
    assert later.state['enabled'] and later.state['greeting']=='Hello from home'
    with mock.patch.object(later,'start') as start:
        later.startup()
        start.assert_called_once()
    with mock.patch.object(voice,'stop') as stop:
        voice.disable()
        stop.assert_called_once()
    assert not V.Controller(desk).state['enabled']
    voice.close();later.close()

with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_SYSTEM_VOICE_OFFER':'0'}):
    desk=H.make_desk();voice=V.controller(desk)
    voice.startup()
    assert H.find_window(desk,'SystemVoice') is None
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), mock.patch('system_voice.subprocess.Popen') as spawn:
        process=spawn.return_value;process.poll.return_value=None
        voice.state['greeting']='hello; $(false)'
        voice.start();voice.start()
        spawn.assert_called_once()
        assert spawn.call_args.args[0][-1]=='--speak=hello; $(false)'
        voice.close()
        process.stdin.close.assert_called_once()
        process.terminate.assert_called_once()
    # Persist failure must not falsely claim enablement.
    with mock.patch.object(voice.store,'save_dict',side_effect=OSError('disk full')):
        try:voice.save(enabled=True)
        except OSError:pass
        else:raise AssertionError('save error swallowed')
        assert not voice.state['enabled']
print('ok')

# Shutdown requests use the existing worker, await its acknowledgement, and
# leave it alive in case the OS refuses power-off. Never power off in tests.
with H.desktop_dir():
    desk=H.make_desk();voice=V.controller(desk)
    voice.state['enabled']=True
    with mock.patch.object(desk.shell,'kilix_tts_target',return_value=['/fixture/kilix','tts']), mock.patch('system_voice.subprocess.Popen') as spawn:
        process=spawn.return_value;process.poll.return_value=None
        voice.start()
        def acknowledge():
            with open(voice.log.name,'ab') as log:
                log.write(b'System voice goodbye complete\n')
        process.stdin.flush.side_effect=acknowledge
        voice.goodbye()
        process.stdin.write.assert_called_once_with(b'g')
        process.terminate.assert_not_called()
        process.stdin.write.reset_mock()
        voice.state['enabled']=False
        voice.goodbye()
        process.stdin.write.assert_not_called()
        voice.state['enabled']=True
        process.stdin.flush.side_effect=None
        with mock.patch('system_voice.time.monotonic',side_effect=[0,1,5]), mock.patch('system_voice.time.sleep'):
            voice.goodbye()  # No acknowledgement: bounded wait, then power-off can proceed.
        process.stdin.write.side_effect=BrokenPipeError()
        voice.goodbye()  # failed speech cannot block shutdown
        voice.close()
    order=[]
    with mock.patch.object(voice,'goodbye',side_effect=lambda:order.append('goodbye')), mock.patch.object(desk.shell,'_spawn_kitty_launch',side_effect=lambda *a:order.append(a[1])):
        desk.shell._power_off()
    assert order==['goodbye','systemctl poweroff']
