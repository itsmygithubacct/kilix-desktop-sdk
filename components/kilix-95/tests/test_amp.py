"""Kilix-Amp uses isolated Kilix 95 runtime roots and fails visibly."""
import os
import stat
import tempfile

import harness as H
from apps import amp
import storage


env = amp._runtime_env()
assert env == {
    "XDG_CONFIG_HOME": storage.config_dir("app-state"),
    "XDG_DATA_HOME": storage.data_dir("app-state"),
    "XDG_STATE_HOME": storage.state_dir("app-state"),
    "XDG_CACHE_HOME": storage.cache_dir("app-state"),
}
assert all(path.startswith(storage.storage_home() + os.sep)
           for path in env.values())
assert all(stat.S_IMODE(os.stat(path).st_mode) == 0o700
           for path in env.values())


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
