"""Programs ▸ Install Software and the Coding Agents entry.

Both resolve the same way every other Start-menu launcher resolves: through the
Kilix launcher, so what the menu offers and what `kilix install` prints are one
list. A menu that kept its own catalogue would be a second thing to keep true,
and the agents in particular install by running a vendor script — the command
must come from the place that prints it before running it.
"""
import harness as H
import shell as shell_module


def _find(items, label):
    for item in items:
        if item.label == label:
            return item
    return None


def _labels(items):
    return [i.label for i in items if i.label != "-"]


d = H.make_desk()
d.taskbar.open_start_menu()
top = d.menus.stack[0].items

programs = _find(top, "Programs")
assert programs is not None and programs.submenu, _labels(top)
entries = programs.submenu

installer = _find(entries, "Install Software")
assert installer is not None, _labels(entries)
assert installer.action is not None, "Install Software must launch something"

agents = _find(entries, "Coding Agents")
assert agents is not None, _labels(entries)
assert agents.context, "the agents entry must offer each agent directly"
assert _labels(agents.context) == ["Claude Code", "Codex", "Kimi Code"], \
    _labels(agents.context)

# Resolution goes through the launcher, and names the subcommand that owns the
# list rather than reaching for a catalogue of its own.
target = shell_module.Shell.install_target()
assert target is None or target[-1] == "install", target
one = shell_module.Shell.install_target("claude")
assert one is None or one[-1] == "claude", one

print("ok test_install_menu")
