import os
import tempfile
from pathlib import Path
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


def test_kilix_temps_launcher_forces_graphical_tab():
    d = H.make_desk()
    seen = {}

    def fake_tab(argv, title, cwd=None):
        seen.update(argv=argv, title=title, cwd=cwd)
        return True

    d.shell._tab = fake_tab
    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory) / "kilix-temps"
        executable = project / "build" / "kilix-temps"
        executable.parent.mkdir(parents=True)
        executable.write_text("#!/bin/sh\n")
        executable.chmod(0o755)
        with patch.dict(os.environ, {
                "GPU_TERMINAL_SOURCE_HOME": directory}), \
                patch("shell.shutil.which", return_value=None):
            assert d.shell.open_kilix_temps()
    assert seen["argv"] == [str(executable), "--graphics"]
    assert seen["title"] == "Kilix Temps"
    assert seen["cwd"] == str(project)


def test_kilix_temps_falls_back_to_kilix_installer():
    d = H.make_desk()
    seen = {}
    d.shell._tab = lambda argv, title, cwd=None: seen.update(
        argv=argv, title=title, cwd=cwd) or True
    with tempfile.TemporaryDirectory() as directory:
        kilix = Path(directory) / "kilix" / "kilix"
        kilix.parent.mkdir(parents=True)
        kilix.write_text("#!/bin/sh\n")
        kilix.chmod(0o755)
        with patch.dict(os.environ, {
                "GPU_TERMINAL_SOURCE_HOME": directory}, clear=True), \
                patch("shell.shutil.which", return_value=None):
            assert d.shell.open_kilix_temps()
    assert seen["argv"] == [str(kilix), "temps", "--graphics"]
    assert seen["cwd"] is None


def test_kilix_temps_installed_command_precedes_incomplete_source():
    d = H.make_desk()
    seen = {}
    d.shell._tab = lambda argv, title, cwd=None: seen.update(
        argv=argv, title=title, cwd=cwd) or True
    with tempfile.TemporaryDirectory() as directory:
        raw = Path(directory) / "kilix-temps" / "kilix-temps"
        raw.parent.mkdir(parents=True)
        raw.write_text("#!/bin/sh\n")
        raw.chmod(0o755)
        with patch.dict(os.environ, {
                "GPU_TERMINAL_SOURCE_HOME": directory}), \
                patch("shell.shutil.which",
                      return_value="/usr/local/bin/kilix-temps"):
            assert d.shell.open_kilix_temps()
    assert seen["argv"] == ["/usr/local/bin/kilix-temps", "--graphics"]
    assert seen["cwd"] is None


test_mux_icon_renders()
test_desktop_mux_terminal_launcher()
test_remote_launch_uses_private_credential()
test_kilix_temps_launcher_forces_graphical_tab()
test_kilix_temps_falls_back_to_kilix_installer()
test_kilix_temps_installed_command_precedes_incomplete_source()
print("ok")
