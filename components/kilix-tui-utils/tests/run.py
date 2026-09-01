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
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
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
