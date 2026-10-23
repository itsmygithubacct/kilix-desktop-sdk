"""Desktop launchers use refreshed authentication and pane identity together."""
import os
from unittest.mock import patch

import harness as H
import shell as shell_mod


for launch in ('terminal', 'command'):
    desk = H.make_desk()
    stale = {'KITTY_PID': '10', 'KITTY_WINDOW_ID': '1',
             'KITTY_LISTEN_ON': 'unix:@kilix-10', 'KITTY_PUBLIC_KEY': 'old-public-key',
             'KILIX_RC_PASSWORD_FILE': '/old-password-file'}
    current = dict(stale, KITTY_PID='20', KITTY_WINDOW_ID='7',
                   KITTY_LISTEN_ON='unix:@kilix-20', KITTY_PUBLIC_KEY='new-public-key',
                   KILIX_RC_PASSWORD_FILE='/new-password-file')
    calls = []

    def refresh():
        os.environ.update(current)
        return True

    def capture(argv, **kwargs):
        calls.append((argv, {key: os.environ[key] for key in current}, kwargs))
        return object()

    with patch.dict(os.environ, stale), \
            patch.object(shell_mod.frontend_context, 'refresh', side_effect=refresh), \
            patch.object(desk.shell, '_kitten', return_value='/fixture/kitten'), \
            patch.object(shell_mod.subprocess, 'Popen', side_effect=capture):
        if launch == 'terminal':
            assert desk.shell.open_terminal()
        else:
            assert desk.shell._tab(['/usr/bin/python3', '-c', 'pass'], 'probe')
    assert len(calls) == 1
    argv, environment, kwargs = calls[0]
    assert argv[:5] == ['/fixture/kitten', '@', '--password-file',
                        '/new-password-file', 'launch'], argv
    assert environment == current, environment
    assert '--self' in argv, 'new window identity must accompany the new route'
    assert kwargs['start_new_session'] is True

print('ok')
