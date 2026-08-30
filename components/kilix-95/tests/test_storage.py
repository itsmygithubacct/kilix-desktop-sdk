"""Canonical Kilix 95 storage paths and private session permissions."""
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage


sandbox = tempfile.mkdtemp(prefix="kilix95-storage-contract-")
gpu_root = os.path.join(sandbox, "gpu-terminal")
root = os.path.join(gpu_root, "kilix-95-explicit")
old = {name: os.environ.get(name) for name in (
    "GPU_TERMINAL_HOME", "KILIX95_STORAGE_HOME", "KILIX95_CONFIG_HOME",
    "KILIX95_STATE_HOME",
    "KILIX95_CACHE_HOME", "KILIX95_DATA_HOME", "KILIX95_SESSION_HOME")}
try:
    os.environ.pop("KILIX95_STORAGE_HOME", None)
    os.environ["GPU_TERMINAL_HOME"] = gpu_root
    assert storage.storage_home() == os.path.join(gpu_root, "kilix-95")

    os.makedirs(root, mode=0o755)
    os.chmod(root, 0o755)
    os.environ["KILIX95_STORAGE_HOME"] = root
    for name in old:
        if name not in ("GPU_TERMINAL_HOME", "KILIX95_STORAGE_HOME"):
            os.environ.pop(name, None)

    assert storage.config_dir("x") == os.path.join(root, "config", "x")
    assert storage.state_dir("x") == os.path.join(root, "state", "x")
    assert storage.cache_dir("x") == os.path.join(root, "cache", "x")
    assert storage.data_dir("x") == os.path.join(root, "data", "x")
    assert storage.session_dir("x") == os.path.join(root, "session", "x")
    for directory in (root, *(os.path.join(root, leaf) for leaf in
                              ("config", "state", "cache", "data", "session"))):
        assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700, directory

    private = storage.private_session_dir("installer-logs")
    assert private == os.path.join(root, "session", "installer-logs")
    assert stat.S_IMODE(os.stat(os.path.join(root, "session")).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(private).st_mode) == 0o700

    # An explicit category override remains authoritative.
    override = os.path.join(sandbox, "session-override")
    os.mkdir(override, mode=0o755)
    os.chmod(override, 0o755)
    os.environ["KILIX95_SESSION_HOME"] = override
    assert storage.private_session_dir() == override
    assert stat.S_IMODE(os.stat(override).st_mode) == 0o700

    # An external non-session category override stays operator-managed.  Kilix
    # 95 secures private leaves below it where required instead of chmodding a
    # potentially shared parent directory.
    external_config = os.path.join(sandbox, "external-config")
    os.mkdir(external_config, mode=0o755)
    os.chmod(external_config, 0o755)
    os.environ["KILIX95_CONFIG_HOME"] = external_config
    assert storage.config_dir("x") == os.path.join(external_config, "x")
    assert stat.S_IMODE(os.stat(external_config).st_mode) == 0o755

    # Never follow a final symlink while repairing a private boundary.
    target = os.path.join(sandbox, "symlink-target")
    link = os.path.join(sandbox, "symlink-storage")
    os.mkdir(target, mode=0o755)
    os.chmod(target, 0o755)
    os.symlink(target, link)
    try:
        storage.private_dir(link)
    except OSError:
        pass
    else:
        raise AssertionError("private_dir followed a symlink")
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o755

    # The component root must not alias the shared GPU root itself.
    os.environ["KILIX95_STORAGE_HOME"] = gpu_root
    try:
        storage.cache_dir()
    except ValueError:
        pass
    else:
        raise AssertionError("broad KILIX95_STORAGE_HOME was accepted")
finally:
    for name, value in old.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    shutil.rmtree(sandbox, ignore_errors=True)

print("ok")
