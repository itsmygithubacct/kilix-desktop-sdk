"""Canonical Kilix 95 storage paths and private session permissions."""
import os
from pathlib import Path
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage


root = tempfile.mkdtemp(prefix="kilix95-storage-contract-")
old = {name: os.environ.get(name) for name in (
    "GPU_TERMINAL_HOME", "KILIX95_STORAGE_HOME", "KILIX95_CONFIG_HOME",
    "KILIX95_STATE_HOME",
    "KILIX95_CACHE_HOME", "KILIX95_DATA_HOME", "KILIX95_SESSION_HOME")}
try:
    os.environ.pop("KILIX95_STORAGE_HOME", None)
    os.environ["GPU_TERMINAL_HOME"] = root
    assert storage.storage_home() == os.path.join(root, "kilix-95")

    os.environ["KILIX95_STORAGE_HOME"] = root
    for name in old:
        if name not in ("GPU_TERMINAL_HOME", "KILIX95_STORAGE_HOME"):
            os.environ.pop(name, None)

    assert storage.config_dir("x") == os.path.join(root, "config", "x")
    assert storage.state_dir("x") == os.path.join(root, "state", "x")
    assert storage.cache_dir("x") == os.path.join(root, "cache", "x")
    assert storage.data_dir("x") == os.path.join(root, "data", "x")
    assert storage.session_dir("x") == os.path.join(root, "session", "x")

    private = storage.private_session_dir("installer-logs")
    assert private == os.path.join(root, "session", "installer-logs")
    assert stat.S_IMODE(os.stat(os.path.join(root, "session")).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(private).st_mode) == 0o700

    # An explicit category override remains authoritative.
    override = tempfile.mkdtemp(prefix="kilix95-session-override-")
    os.chmod(override, 0o755)
    os.environ["KILIX95_SESSION_HOME"] = override
    assert storage.private_session_dir() == override
    assert stat.S_IMODE(os.stat(override).st_mode) == 0o700
finally:
    for name, value in old.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

print("ok")
