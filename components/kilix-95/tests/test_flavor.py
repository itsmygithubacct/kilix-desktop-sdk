"""Desktop flavor switching: Start -> Settings -> Desktop Flavor."""
import json
import os
import tempfile

_cache = tempfile.mkdtemp(prefix="kilix95-flavor-xdg-")
os.environ["XDG_DATA_HOME"] = _cache

import harness as H
import sounds
import theme as T
from apps.winhelp import Help


def _item(items, label):
    for it in items:
        if it.label == label:
            return it
    raise AssertionError("missing menu item %r; got %r"
                         % (label, [it.label for it in items]))


T.apply_flavor("95")
with H.desktop_dir() as desktop:
    d = H.make_desk()
    assert T.flavor_name() == "95"

    d.taskbar.open_start_menu()
    root = d.menus.stack[0]
    assert root.sidebar == "kilix 95"
    settings = _item(root.items, "Settings")
    flavor = _item(settings.submenu, "Desktop Flavor")
    assert flavor.submenu is not None
    assert _item(flavor.submenu, "kilix 95").checked
    assert not _item(flavor.submenu, "kilix XP").checked

    _item(flavor.submenu, "kilix XP").action()
    assert T.flavor_name() == "xp"
    assert T.PRODUCT_NAME == "kilix XP"
    assert d.shell.state["flavor"] == "xp"
    assert d.shell.state["wall_color"] == list(T.DESKTOP)
    assert sounds._active_name == sounds.XP_SCHEME
    assert sounds.events(generate=False)[0][2] == \
        sounds.path_for("startup", "xp")
    with open(os.path.join(desktop, ".state.json")) as f:
        assert json.load(f)["flavor"] == "xp"

    d.menus.close_all()
    d.taskbar.open_start_menu()
    root = d.menus.stack[0]
    assert root.sidebar == "kilix XP"
    settings = _item(root.items, "Settings")
    flavor = _item(settings.submenu, "Desktop Flavor")
    assert _item(flavor.submenu, "kilix XP").checked
    assert not _item(flavor.submenu, "kilix 95").checked

    help_win = Help(d)
    assert help_win.title == "Help Topics - kilix XP"
    assert "Welcome to kilix XP" in help_win.body.plain()

    T.apply_flavor("95")
    d2 = H.make_desk()
    assert d2.shell.state["flavor"] == "xp"
    assert T.flavor_name() == "xp"
    d2.shell.set_flavor("95")
    assert T.flavor_name() == "95"
    assert sounds._active_name == sounds.DEFAULT_SCHEME

print("ok")
