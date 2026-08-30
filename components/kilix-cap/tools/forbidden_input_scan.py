#!/usr/bin/env python3
"""Enforce kilix-cap's standalone, clean-room runtime boundary."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


FORBIDDEN_BINARY_STRINGS = (
    b"magic cap",
    b"magic link",
    b"personalink",
    b"telescript",
    b"general magic",
    b"mcw.exe",
    b"mccom32s",
    b"pic-1000",
    b"envoy",
)
FORBIDDEN_SUFFIXES = {
    ".rom", ".exe", ".dll",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", type=Path, required=True)
    ap.add_argument("--assets", type=Path, required=True)
    args = ap.parse_args()
    errors: list[str] = []
    try:
        binary = args.binary.read_bytes()
    except OSError as exc:
        errors.append(str(exc))
        binary = b""
    for needle in FORBIDDEN_BINARY_STRINGS:
        if needle.lower() in binary.lower():
            errors.append(f"compiled binary contains forbidden token {needle.decode()}")
    if not args.assets.is_dir():
        errors.append(f"missing runtime asset directory {args.assets}")
    else:
        for root, dirs, files in os.walk(args.assets):
            dirs[:] = [d for d in dirs if d != "_build"]
            for name in dirs + files:
                path = Path(root) / name
                if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                    errors.append(f"forbidden extracted-binary artifact: {path}")
                if path.is_symlink():
                    errors.append(f"runtime asset symlink is not allowed: {path}")
    for error in errors:
        print(f"forbidden_input_scan: {error}", file=sys.stderr)
    if errors:
        return 1
    print("forbidden_input_scan: clean-room runtime boundary OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
