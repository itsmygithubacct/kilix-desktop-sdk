"""Direct Kilix 95 startup repairs its private storage boundaries."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sandbox = Path(tempfile.mkdtemp(prefix="kilix95-bootstrap-storage-"))
gpu_root = sandbox / "gpu-terminal"
storage_root = gpu_root / "kilix-95"
cache_root = storage_root / "cache"
env = dict(os.environ)
env.update({
    "GPU_TERMINAL_HOME": str(gpu_root),
    "KILIX95_STORAGE_HOME": str(storage_root),
    "KILIX95_CACHE_HOME": str(cache_root),
    "PYTHONDONTWRITEBYTECODE": "1",
})


def run_version():
    result = subprocess.run(
        ["/bin/sh", "-c", 'umask 022; exec "$@"', "sh", sys.executable,
         str(ROOT / "main.py"), "--version"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    version = (ROOT / "VERSION").read_text().strip()
    assert result.stdout.strip() == f"kilix-95 {version}", result.stdout


try:
    # Missing parents must not inherit 0755 from a conventional umask.
    run_version()
    for directory in (storage_root, cache_root, cache_root / "pycache"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700, directory

    # Existing public boundaries from an older launch are reconciled too.
    storage_root.chmod(0o755)
    cache_root.chmod(0o755)
    run_version()
    assert stat.S_IMODE(storage_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(cache_root.stat().st_mode) == 0o700
finally:
    shutil.rmtree(sandbox, ignore_errors=True)

print("ok")
