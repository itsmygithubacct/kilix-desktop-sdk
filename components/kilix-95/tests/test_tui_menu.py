"""Programs ▸ Kilix TUI opens the text desktop, resolved like the CLI.

The entry has to resolve the *same* way the Kilix CLI resolves the desktop —
an installed command, otherwise the Kilix launcher — or a Start-menu launch
and a `kilix kilix-tui` typed in a pane could run different builds. It opens
in a tab beside Kilix 95 rather than replacing it: reaching the sibling
desktop must not change the session's provider.
"""
import os
import shutil
import tempfile
from unittest.mock import patch

import harness as H
import games


def _find(items, label):
    for item in items:
        if item.label == label:
            return item
    return None


def _labels(items):
    return [item.label for item in items if item.label != "-"]


d = H.make_desk()
d.taskbar.open_start_menu()
top = d.menus.stack[0].items

programs = _find(top, "Programs")
assert programs is not None and programs.submenu, _labels(top)
entry = _find(programs.submenu, "Kilix TUI")
assert entry is not None, _labels(programs.submenu)
assert entry.icon == "terminal", entry.icon

# The entry opens a tab rather than doing anything itself.
opened = []
original_tab = d.shell._tab
d.shell._tab = lambda argv, title, cwd=None, env=None: opened.append(
    (list(argv), title, env))
entry.action()
assert len(opened) == 1, opened
argv, title, environment = opened[0]
assert title == "Kilix TUI", title
assert environment == {"KILIX_CONTENT_ROOT": os.path.normpath(games.APPS_DIR)}

# Exactly two branches, the same two the Kilix CLI resolves: an installed
# command wins, and otherwise the Kilix launcher prepares the pinned desktop.
# A source checkout is deliberately not consulted.
saved_which = shutil.which
try:
    shutil.which = lambda name: "/opt/bin/kilix-tui" \
        if name == "kilix-tui" else None
    assert d.shell.kilix_tui_target() == ["/opt/bin/kilix-tui"]

    shutil.which = lambda name: None
    target = d.shell.kilix_tui_target()
    assert target is not None, "no fallback at all"
    assert target[0].endswith("kilix"), target
    assert target[1:] == ["kilix-tui", "--content-root",
                          os.path.normpath(games.APPS_DIR)], target

    # Even with a source checkout present, it must not win.
    source_home = os.environ.get("GPU_TERMINAL_SOURCE_HOME") or \
        os.path.expanduser("~/.local/gpu_terminal/sources")
    checkout = os.path.join(source_home, "kilix-desktops", "kilix-tui-utils",
                            "kilix-tui", "main.py")
    if os.path.isfile(checkout):
        assert checkout not in target, target
finally:
    shutil.which = saved_which

# An installed command and a host fallback both receive the actual 95 root,
# including distinct stores with spaces/quotes and lexical normalization.
# Neither planning nor constructing the real remote-launch argv installs or
# creates the missing content root, and inherited authority is not mutated.
with tempfile.TemporaryDirectory(prefix="kilix95-tui-roots-") as temporary:
    for name in ("store one", "store 'two'"):
        selected = os.path.join(temporary, name)
        raw = os.path.join(temporary, "unused", "..", name)
        for installed in (True, False):
            with patch.object(games, "APPS_DIR", raw), \
                    patch.dict(os.environ, {"KILIX_CONTENT_ROOT": "/stale/receipts"}), \
                    patch.object(shutil, "which", side_effect=lambda value:
                                 "/opt/bin/kilix-tui" if installed and value == "kilix-tui" else None):
                opened.clear()
                entry.action()
                assert len(opened) == 1, opened
                target, title, environment = opened[0]
                assert environment == {"KILIX_CONTENT_ROOT": selected}, environment
                if installed:
                    assert target == ["/opt/bin/kilix-tui"], target
                else:
                    assert target == [os.path.join(H.KILIX_HOME, "kilix"),
                                      "kilix-tui", "--content-root", selected], target
                assert not os.path.exists(selected), selected
                assert os.environ["KILIX_CONTENT_ROOT"] == "/stale/receipts"

                commands = []
                with patch.object(d.shell, "_kitten", return_value="/fixture/kitten"), \
                        patch.object(d.shell, "_resolve_program", side_effect=lambda value: value), \
                        patch.object(d.shell, "_popen", side_effect=lambda argv: commands.append(argv) or True), \
                        patch.dict(os.environ, {"KITTY_LISTEN_ON": "unix:/fixture/not-contacted"}):
                    assert original_tab(target, title, env=environment)
                assert len(commands) == 1
                command = commands[0]
                root_argument = "KILIX_CONTENT_ROOT=" + selected
                assert command.count(root_argument) == 1, command
                assert command[command.index(root_argument) - 1] == "--env", command
                assert command[command.index("--") + 1:] == target, command
                assert not os.path.exists(selected), selected

print("ok")
