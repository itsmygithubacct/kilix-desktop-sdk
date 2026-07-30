"""Programs ▸ Kilix TUI opens the text desktop, resolved like the CLI.

The entry has to resolve the *same* way the Kilix CLI resolves the desktop —
an installed command, otherwise the Kilix launcher — or a Start-menu launch
and a `kilix kilix-tui` typed in a pane could run different builds. It opens
in a tab beside Kilix 95 rather than replacing it: reaching the sibling
desktop must not change the session's provider.
"""
import os
import shutil

import harness as H


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
d.shell._tab = lambda argv, title, cwd=None, env=None: opened.append(
    (list(argv), title))
entry.action()
assert len(opened) == 1, opened
argv, title = opened[0]
assert title == "Kilix TUI", title

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
    assert target[-1] == "kilix-tui" and target[0].endswith("kilix"), target

    # Even with a source checkout present, it must not win.
    source_home = os.environ.get("GPU_TERMINAL_SOURCE_HOME") or \
        os.path.expanduser("~/.local/gpu_terminal/sources")
    checkout = os.path.join(source_home, "kilix-desktops", "kilix-tui-utils",
                            "kilix-tui", "main.py")
    if os.path.isfile(checkout):
        assert checkout not in target, target
finally:
    shutil.which = saved_which

print("ok")
