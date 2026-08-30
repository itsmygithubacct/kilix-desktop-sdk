"""Programs ▸ Default Desktop, and the same choice from every desktop.

Launching a desktop and choosing the one every later session starts with are
different acts. `kilix cap` runs Cap now; nothing here used to mean "and keep
doing that", so the choice lived in an environment variable an image shipped
and a user could not reach. This entry writes it through the launcher, which
is the one place that persists it.
"""
import harness as H
import shell as shell_module


def _find(items, label):
    for item in items:
        if item.label == label:
            return item
    return None


d = H.make_desk()
d.taskbar.open_start_menu()
programs = _find(d.menus.stack[0].items, "Programs")
assert programs is not None and programs.submenu

entry = _find(programs.submenu, "Default Desktop")
assert entry is not None, [i.label for i in programs.submenu]
assert entry.action is not None
assert entry.context, "each desktop must be choosable directly"
labels = [i.label for i in entry.context if i.label != "-"]
assert labels == ["Kilix 95", "Kilix XP", "Kilix Cap", "Kilix TUI",
                  "Kilix Land", "Automatic"], labels

# It goes through the launcher's own subcommand rather than writing config here.
show = shell_module.Shell.default_desktop_target()
assert show is None or show[-2:] == ["default-desktop", "show"], show
one = shell_module.Shell.default_desktop_target("cap")
assert one is None or one[-3:] == ["default-desktop", "set", "cap"], one

print("ok test_default_desktop_menu")
