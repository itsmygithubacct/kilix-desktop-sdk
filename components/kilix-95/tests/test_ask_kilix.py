"""Run… falls back to `kilix ask` for non-programs; Start menu has a voice item."""
import os
import stat
import tempfile
from unittest.mock import patch

import harness as H
import wm


def _run(text):
    """Open Run… on a fresh desk, submit `text`, and report what happened."""
    d = H.make_desk()
    shown = {"input": None, "confirm": []}
    launched, tabs = [], []

    def fake_inputbox(desk, title, label, initial="", cb=None, **kw):
        shown["input"] = (title, cb)

    def fake_msgbox(desk, title, body, icon="info", buttons=("OK",), cb=None,
                    **kw):
        shown["confirm"].append((title, body, tuple(buttons), cb))

    d.shell._spawn_kitty_launch = lambda opts, cmd, title, **kw: (
        launched.append((opts, cmd, title)) or True)
    d.shell._tab = lambda argv, title, **kw: tabs.append((argv, title)) or True
    with patch.object(wm, "inputbox", fake_inputbox), \
            patch.object(wm, "msgbox", fake_msgbox):
        d.shell.run_dialog()
        assert shown["input"][0] == "Run"
        shown["input"][1](text)
    return shown, launched, tabs


def program_on_path_is_launched_as_before():
    shown, launched, tabs = _run("sh -c true")
    assert launched == [(["--type=tab"], "sh -c true", "sh")], launched
    assert not tabs and not shown["confirm"]


def executable_path_is_launched_as_before():
    shown, launched, tabs = _run("/bin/sh -c true")
    assert launched == [(["--type=tab"], "/bin/sh -c true", "/bin/sh")], launched
    assert not tabs and not shown["confirm"]


def non_program_asks_then_ok_launches_kilix_ask_argv():
    text = "please open the downloads folder"
    shown, launched, tabs = _run(text)
    assert not launched and not tabs, (launched, tabs)
    [(title, body, buttons, cb)] = shown["confirm"]
    assert title == "Run" and body == f"Ask Kilix: {text}?", (title, body)
    assert buttons == ("OK", "Cancel"), buttons
    cb("OK")
    assert tabs == [(["kilix", "ask", "--hold", "--", text], "Ask Kilix")], tabs
    assert not launched


def cancel_launches_nothing():
    shown, launched, tabs = _run("tidy up my notes")
    shown["confirm"][0][3]("Cancel")
    assert not launched and not tabs, (launched, tabs)


def empty_input_does_nothing():
    for text in ("", "   ", None):
        shown, launched, tabs = _run(text)
        assert not launched and not tabs and not shown["confirm"], text


def missing_path_goes_to_ask_path():
    text = "/no/such/dir/tool --flag"
    shown, launched, tabs = _run(text)
    assert not launched and len(shown["confirm"]) == 1
    shown["confirm"][0][3]("OK")
    assert tabs == [(["kilix", "ask", "--hold", "--", text], "Ask Kilix")], tabs


def hostile_text_stays_one_literal_argv_item():
    text = 'say "hi" $(touch /tmp/x); echo `id` \'q\' && rm -rf ~'
    shown, launched, tabs = _run(text)
    assert not launched
    shown["confirm"][0][3]("OK")
    assert tabs == [(["kilix", "ask", "--hold", "--", text], "Ask Kilix")], tabs
    assert len(tabs[0][0]) == 5


def dash_text_is_the_request_not_an_option():
    text = "--yes close tab 2"
    shown, launched, tabs = _run(text)
    assert not launched and len(shown["confirm"]) == 1
    shown["confirm"][0][3]("OK")
    assert tabs == [(["kilix", "ask", "--hold", "--", text], "Ask Kilix")], tabs


def tab_receives_argv_without_a_shell():
    """End to end through _tab: the text is one argv element after `--`."""
    text = 'a "b" $(c); d'
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("kitten", "kilix"):
            path = os.path.join(tmp, name)
            with open(path, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        d = H.make_desk()
        popen = []
        d.shell._popen = lambda argv: popen.append(argv) or True
        env = {"KILIX_KITTEN": os.path.join(tmp, "kitten"),
               "KITTY_LISTEN_ON": "unix:/nonexistent",
               "PATH": tmp + os.pathsep + os.environ.get("PATH", "")}
        with patch.dict(os.environ, env):
            d.shell.ask_kilix(text)
        [argv] = popen
        tail = argv[argv.index("--") + 1:]
        assert tail == [os.path.join(tmp, "kilix"), "ask", "--hold", "--", text], tail
        assert "Ask Kilix" in argv and "bash" not in argv, argv


def start_menu_has_voice_item_after_run():
    d = H.make_desk()
    d.taskbar.open_start_menu()
    top = d.menus.stack[0].items
    labels = [it.label for it in top]
    i = labels.index("Run…")
    assert labels[i + 1] == "Ask Kilix by voice…", labels
    item = top[i + 1]
    assert item.icon == "microphone", item.icon
    tabs = []
    d.shell._tab = lambda argv, title, **kw: tabs.append((argv, title)) or True
    item.action()
    assert tabs == [(["kilix", "ask", "--voice", "--hold"], "Ask Kilix")], tabs


for fn in (program_on_path_is_launched_as_before,
           executable_path_is_launched_as_before,
           non_program_asks_then_ok_launches_kilix_ask_argv,
           cancel_launches_nothing, empty_input_does_nothing,
           missing_path_goes_to_ask_path,
           dash_text_is_the_request_not_an_option,
           hostile_text_stays_one_literal_argv_item,
           tab_receives_argv_without_a_shell,
           start_menu_has_voice_item_after_run):
    fn()
print("ok")
