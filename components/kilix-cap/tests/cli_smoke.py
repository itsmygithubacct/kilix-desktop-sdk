#!/usr/bin/env python3
"""Verify output-producing render commands reject ambiguous arguments."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    binary = args.binary.expanduser().resolve()
    if not binary.is_file():
        print(f"cli_smoke: FAIL: binary does not exist: {binary}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="kilix-cap-cli-") as raw_dir:
        workdir = Path(raw_dir)
        for command in ("--render-test", "--render-review"):
            bad_argv = (
                [str(binary), command],
                [str(binary), command, ""],
                [str(binary), command, raw_dir, "unexpected"],
            )
            for argv in bad_argv:
                result = subprocess.run(
                    argv,
                    cwd=workdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if result.returncode != 2:
                    print(
                        f"cli_smoke: FAIL: {' '.join(argv[1:])} returned "
                        f"{result.returncode}, expected 2",
                        file=sys.stderr,
                    )
                    return 1
                if any(workdir.iterdir()):
                    print(
                        f"cli_smoke: FAIL: {command} wrote files after invalid "
                        "arguments",
                        file=sys.stderr,
                    )
                    return 1

    print("cli_smoke: ok (render commands require exactly one DIR)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
