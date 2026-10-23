"""Default Control Panel paths reach real host controls rather than opt-in extras."""
from unittest.mock import patch

import harness as H
from apps.controlpanel import ControlPanel
from apps.printers import Printers


def test_controls_available_without_nostalgia():
    desk = H.make_desk()
    assert not desk.shell.full_experience_enabled()
    panel = ControlPanel(desk)
    desk.wm.add(panel)
    calls = []
    with patch.object(desk.shell, 'open_device_settings', side_effect=calls.append):
        for item in panel.grid.items:
            if item['data'][0] == 'host-settings':
                panel._activate(item)
    assert set(calls) == {'power', 'bluetooth', 'storage', 'audio', 'input-method', 'accessibility', 'lock'}
    assert any(item['label'] == 'Printers' for item in panel.grid.items)
    desk.render()


def test_physical_printer_action_is_distinct_from_printing_to_a_folder():
    desk = H.make_desk()
    printers = Printers(desk)
    desk.wm.add(printers)
    first, second = printers.grid.items[:2]
    assert first['label'] == 'Configure Physical Printers'
    assert second['label'] == 'Print to Folder'
    calls = []
    with patch.object(desk.shell, 'open_device_settings', side_effect=calls.append):
        printers._activate(first)
    assert calls == ['printers']
    assert not any(win.title == 'Print to Folder' for win in desk.wm.windows)
    desk.render()


def test_lock_uses_the_session_command_and_missing_control_is_visible():
    desk = H.make_desk()
    with patch.object(desk.shell, '_resolve_program', return_value='/fixture/pleb'), \
            patch.object(desk.shell, '_tab', return_value=True) as launch:
        assert desk.shell.open_device_settings('lock')
        assert launch.call_args.args[0] == ['/fixture/pleb', 'lock']
    with patch.object(desk.shell, '_resolve_program', return_value=None):
        assert desk.shell.open_device_settings('bluetooth') is False
        assert any(win.title == 'Bluetooth' for win in desk.wm.windows)


test_controls_available_without_nostalgia()
test_physical_printer_action_is_distinct_from_printing_to_a_folder()
test_lock_uses_the_session_command_and_missing_control_is_visible()
print('desktop device controls passed')
