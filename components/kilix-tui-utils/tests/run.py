#!/usr/bin/env python3
"""Run every tool's suite in a fresh subprocess.

Same shape as Kilix 95's runner: one process per file so a tool that leaves
curses or an import in a bad state cannot affect the next one, and so a crash
is attributed to the tool that caused it.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    names = sorted(
        name for name in os.listdir(HERE)
        if name.startswith("test_") and name.endswith(".py")
    )
    if sys.argv[1:]:
        names = [n for n in names if any(a in n for a in sys.argv[1:])]
    failed = []
    skipped = {}
    for name in names:
        # Tests must not discover the operator's agents, launch preferences,
        # live sockets or storage. Keep explicit host/native dependency paths.
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("KILIX", "KITTY_", "GPU_TERMINAL_",
                                      "XDG_", "BASH_FUNC_", "CODEX_"))}
        for key in ("KILIX_HOME", "GPU_TERMINAL_SOURCE_HOME"):
            if key in os.environ:
                env[key] = os.environ[key]
        # Unix socket names have a small fixed limit; the runner's inherited
        # TMPDIR can already be longer than that limit before a fixture starts.
        with tempfile.TemporaryDirectory(
                prefix="kt-", dir="/tmp" if os.name == "posix" else None) as tmp:
            root = Path(tmp)
            for key, leaf in {
                "HOME": "home", "TMPDIR": "tmp",
                "XDG_CONFIG_HOME": "config", "XDG_CACHE_HOME": "cache",
                "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state",
                "XDG_RUNTIME_DIR": "run", "GPU_TERMINAL_HOME": "storage",
                "KILIX_STORAGE_HOME": "storage/kilix",
            }.items():
                path = root / leaf
                path.mkdir(mode=0o700, parents=True, exist_ok=True)
                env[key] = str(path)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [sys.executable, os.path.join(HERE, name), "-v"],
                capture_output=True, text=True, env=env,
            )
        output = result.stdout + result.stderr
        # A skipped test is a test that did not run. Reporting it as a plain
        # PASS makes a conditional gate indistinguishable from a green one,
        # so the reasons are surfaced here and counted in the summary.
        reasons = re.findall(r"skipped ['\"](.*?)['\"]", output)
        if reasons:
            skipped[name] = reasons
        if result.returncode == 0:
            note = f"  ({len(reasons)} skipped)" if reasons else ""
            print(f"PASS  {name}{note}")
        else:
            failed.append(name)
            print(f"FAIL  {name}")
            for line in output.splitlines():
                print(f"  {line}")
    total_skipped = sum(len(v) for v in skipped.values())
    if skipped:
        print(f"skipped {total_skipped} test(s) in {len(skipped)}/{len(names)} modules:")
        for name in sorted(skipped):
            for reason in skipped[name]:
                print(f"  SKIP  {name}: {reason}")
    print(f"{len(names) - len(failed)}/{len(names)} passed; "
          f"{total_skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
