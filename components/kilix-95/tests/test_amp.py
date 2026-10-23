"""Kilix-Amp uses isolated Kilix 95 runtime roots and fails visibly."""
import os
import stat
import tempfile

import harness as H
from apps import amp
import games
import storage


env = amp._runtime_env()
assert env == {
    "XDG_CONFIG_HOME": storage.config_dir("app-state"),
    "XDG_DATA_HOME": storage.data_dir("app-state"),
    "XDG_STATE_HOME": storage.state_dir("app-state"),
    "XDG_CACHE_HOME": storage.cache_dir("app-state"),
    "KILIX_CONTENT_ROOT": os.path.normpath(games.APPS_DIR),
}
assert all(path.startswith(storage.storage_home() + os.sep)
           for path in env.values())
assert all(stat.S_IMODE(os.stat(path).st_mode) == 0o700
           for name, path in env.items() if name.startswith("XDG_"))

# Receipt authority belongs to the installer, not an inherited value or the
# private XDG app-state directory. Merely planning launch creates no catalog.
old_apps = games.APPS_DIR
old_content = os.environ.get("KILIX_CONTENT_ROOT")
try:
    with tempfile.TemporaryDirectory() as temporary:
        games.APPS_DIR = os.path.join(temporary, "unused", "..", "quoted 'apps'")
        os.environ["KILIX_CONTENT_ROOT"] = "/stale/receipts"
        selected = amp._runtime_env()["KILIX_CONTENT_ROOT"]
        assert selected == os.path.join(temporary, "quoted 'apps'")
        assert not os.path.exists(selected)
        assert os.environ["KILIX_CONTENT_ROOT"] == "/stale/receipts"
        installer = games.kilix_content.Installer(games.APPS_DIR)
        assert selected == installer.root
finally:
    games.APPS_DIR = old_apps
    if old_content is None:
        os.environ.pop("KILIX_CONTENT_ROOT", None)
    else:
        os.environ["KILIX_CONTENT_ROOT"] = old_content


class FakeWM:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)


class FakeDesk:
    def __init__(self):
        self.wm = FakeWM()


seen = {}
old_xpane = amp.xpane.XPane
old_msgbox = amp.wm.msgbox
try:
    amp.xpane.XPane = lambda *args, **kwargs: seen.update(
        args=args, kwargs=kwargs) or object()
    amp.wm.msgbox = lambda *args, **kwargs: seen.update(
        error_args=args, error_kwargs=kwargs)

    app_dir = tempfile.mkdtemp(prefix="kilix95-amp-launch-")
    executable = os.path.join(app_dir, "kilix-amp")
    with open(executable, "w") as handle:
        handle.write("#!/bin/sh\n")
    os.chmod(executable, 0o700)

    desk = FakeDesk()
    media = os.path.join(app_dir, "example.ogg")
    amp._spawn(desk, executable, media)
    assert seen["args"][1][0] == executable
    assert seen["args"][1][1] == media
    assert seen["kwargs"]["env"] == env
    assert seen["kwargs"]["cwd"] == app_dir
    assert len(desk.wm.added) == 1

    seen.clear()
    amp._spawn(desk, None)
    assert "readiness check" in seen["error_args"][2]
    assert seen["error_kwargs"]["icon"] == "error"
finally:
    amp.xpane.XPane = old_xpane
    amp.wm.msgbox = old_msgbox

print("ok")
