"""A direct games setup keeps persistent Kilix 95 storage private."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sandbox = Path(tempfile.mkdtemp(prefix="kilix95-games-storage-"))
home = sandbox / "home"
gpu_root = sandbox / "gpu-terminal"
storage_root = gpu_root / "kilix-95"
bin_dir = sandbox / "bin"
home.mkdir(mode=0o700)
bin_dir.mkdir(mode=0o700)


def executable(name, body):
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o700)


try:
    # A fake system DOSBox makes --setup-only exercise its successful save
    # path without a download.  The fake pactl keeps the audio probe local.
    executable("dosbox", "exit 0\n")
    executable("pactl", "exit 1\n")
    for directory in (storage_root, storage_root / "config",
                      storage_root / "data"):
        directory.mkdir(parents=True, exist_ok=True, mode=0o755)
        directory.chmod(0o755)
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "GPU_TERMINAL_HOME": str(gpu_root),
        "KILIX95_STORAGE_HOME": str(storage_root),
        "KILIX_HOME": str(ROOT.parent / "kilix"),
        "PATH": str(bin_dir) + os.pathsep + "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for name in ("KILIX95_CONFIG_HOME", "KILIX95_STATE_HOME",
                 "KILIX95_CACHE_HOME", "KILIX95_DATA_HOME",
                 "KILIX95_SESSION_HOME"):
        env.pop(name, None)

    result = subprocess.run(
        ["/bin/sh", "-c", 'umask 002; exec "$@"', "sh", sys.executable,
         str(ROOT / "games.py"), "dosbox", "--setup-only"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

    for directory in (storage_root, storage_root / "config",
                      storage_root / "data"):
        assert directory.is_dir(), directory
        assert not directory.is_symlink(), directory
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700, directory

    config = storage_root / "config" / "games.conf"
    assert config.is_file()
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert (storage_root / "data" / "games" / "dosbox-kilix.conf").is_file()

    # A stale config symlink must be replaced, not followed during the next
    # setup.  The target represents unrelated operator data.
    unrelated = sandbox / "unrelated.conf"
    unrelated.write_text("do not replace\n")
    config.unlink()
    config.symlink_to(unrelated)
    result = subprocess.run(
        ["/bin/sh", "-c", 'umask 002; exec "$@"', "sh", sys.executable,
         str(ROOT / "games.py"), "dosbox", "--setup-only"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert config.is_file() and not config.is_symlink()
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert unrelated.read_text() == "do not replace\n"
finally:
    shutil.rmtree(sandbox, ignore_errors=True)

print("ok")
