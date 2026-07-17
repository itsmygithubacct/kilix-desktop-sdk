import os
from unittest.mock import patch

import harness as H
import icons


def test_mux_icon_renders():
    icons.get("mux", 16)
    icons.get("mux", 32)


def test_desktop_mux_terminal_launcher():
    d = H.make_desk()
    items = {item["label"]: item for item in d.shell.grid.items}
    item = items["Mux Terminal"]
    assert item["icon"] == "mux"
    assert item["data"] == ("builtin", ("mux", None))

    seen = {}

    def fake_tab(argv, title, cwd=None):
        seen["argv"] = argv
        seen["title"] = title
        seen["cwd"] = cwd
        return True

    d.shell._tab = fake_tab
    assert d.shell.open_mux_terminal()
    assert os.path.basename(seen["argv"][0]) == "kilix"
    assert seen["argv"][1:] == ["serve", "main"]
    assert seen["title"] == "Mux: main"
    assert seen["cwd"] == os.path.expanduser("~")

    seen.clear()
    d.shell._activate(item)
    assert seen["argv"][1:] == ["serve", "main"]


def test_remote_launch_uses_private_credential():
    d = H.make_desk()
    with patch.dict(os.environ, {"KILIX_RC_PASSWORD_FILE": "/tmp/rc-pass"}):
        assert d.shell._kitten_remote("kitten", "launch") == [
            "kitten", "@", "--password-file", "/tmp/rc-pass", "launch",
        ]


test_mux_icon_renders()
test_desktop_mux_terminal_launcher()
test_remote_launch_uses_private_credential()
print("ok")
