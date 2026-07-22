#!/usr/bin/env python3
"""Run every test_*.py in this dir, each in its own subprocess.

Usage: python3 desktop/tests/run.py [name-substring ...]
Prints PASS/FAIL per file (captured output shown on failure); exits nonzero
on any failure. Each subprocess gets a complete throwaway home and provider
storage environment so inherited category overrides cannot reach live data.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_HOME = os.path.dirname(os.path.dirname(HERE))


def main():
    names = sorted(f for f in os.listdir(HERE)
                   if f.startswith("test_") and f.endswith(".py"))
    if sys.argv[1:]:
        names = [n for n in names if any(a in n for a in sys.argv[1:])]
    failed = []
    native_sandbox = None
    state_library = os.environ.get("KILIX_STATE_LIBRARY")
    if not state_library or not os.path.isfile(state_library):
        native_sandbox = tempfile.mkdtemp(prefix="kilix95-native-test-")
        native_storage = os.path.join(native_sandbox, "storage")
        native_build = os.path.join(native_storage, "build")
        helper = os.path.join(SOURCE_HOME, "kilix", "scripts",
                              "build-state-library.sh")
        native_env = dict(os.environ, KILIX_STORAGE_HOME=native_storage,
                          KILIX_BUILD_DIRECTORY=native_build)
        try:
            result = subprocess.run(
                [helper, "--print-path"], capture_output=True, text=True,
                check=True, env=native_env, timeout=30)
        except (OSError, subprocess.SubprocessError) as error:
            shutil.rmtree(native_sandbox, ignore_errors=True)
            print(f"FAIL  native state setup: {error}")
            if isinstance(error, subprocess.CalledProcessError):
                print((error.stdout or "") + (error.stderr or ""))
            return 1
        state_library = result.stdout.strip()
    for name in names:
        env = dict(os.environ)
        sandbox = tempfile.mkdtemp(prefix="kilix95-test-")
        home = os.path.join(sandbox, "home")
        data_root = os.path.join(sandbox, "gpu-terminal-data")
        kilix_root = os.path.join(data_root, "kilix")
        kilix95_root = os.path.join(data_root, "kilix-95")
        os.makedirs(home, mode=0o700)
        env.update({
            "HOME": home,
            "GPU_TERMINAL_SOURCE_HOME": SOURCE_HOME,
            "GPU_TERMINAL_HOME": data_root,
            "KILIX_HOME": os.path.join(SOURCE_HOME, "kilix"),
            "KILIX_STORAGE_HOME": kilix_root,
            "KILIX_CONFIG_HOME": os.path.join(kilix_root, "config"),
            "KILIX_STATE_DIRECTORY": os.path.join(kilix_root, "state"),
            "KILIX_CACHE_HOME": os.path.join(kilix_root, "cache"),
            "KILIX_DATA_HOME": os.path.join(kilix_root, "data"),
            "KILIX_SESSION_HOME": os.path.join(kilix_root, "session"),
            "KILIX_BUILD_DIRECTORY": os.path.join(kilix_root, "build"),
            "KILIX95_STORAGE_HOME": kilix95_root,
            "KILIX95_CONFIG_HOME": os.path.join(kilix95_root, "config"),
            "KILIX95_STATE_HOME": os.path.join(kilix95_root, "state"),
            "KILIX95_CACHE_HOME": os.path.join(kilix95_root, "cache"),
            "KILIX95_DATA_HOME": os.path.join(kilix95_root, "data"),
            "KILIX95_SESSION_HOME": os.path.join(kilix95_root, "session"),
            "KILIX_DESKTOP_DIR": os.path.join(sandbox, "desktop"),
            "KILIX_RECYCLE_DIR": os.path.join(sandbox, "recycle"),
            "XDG_CONFIG_HOME": os.path.join(sandbox, "xdg", "config"),
            "XDG_STATE_HOME": os.path.join(sandbox, "xdg", "state"),
            "XDG_CACHE_HOME": os.path.join(sandbox, "xdg", "cache"),
            "XDG_DATA_HOME": os.path.join(sandbox, "xdg", "data"),
            "KILIX_STATE_LIBRARY": state_library,
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        env.pop("KITTY_CONFIG_DIRECTORY", None)
        t0 = time.time()
        try:
            p = subprocess.run([sys.executable, os.path.join(HERE, name)],
                               capture_output=True, text=True, env=env,
                               timeout=30)
            ok, out = p.returncode == 0, p.stdout + p.stderr
        except subprocess.TimeoutExpired as e:
            ok = False
            out = ((e.stdout or b"").decode("utf-8", "replace")
                   + (e.stderr or b"").decode("utf-8", "replace")
                   + "\n[timeout after 30s]")
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ({time.time() - t0:.1f}s)")
        if not ok:
            failed.append(name)
            if out.strip():
                print("  " + out.strip().replace("\n", "\n  "))
    print(f"{len(names) - len(failed)}/{len(names)} passed")
    if native_sandbox:
        shutil.rmtree(native_sandbox, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
