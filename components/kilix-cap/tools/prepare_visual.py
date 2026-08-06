#!/usr/bin/env python3
"""Prepare the generated workroom source for the fixed Kilix Cap content zone."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


WIDTH = 1440
HEIGHT = 768
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("assets/art/workdesk-room.png"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/art/runtime/workdesk-room.png"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with Image.open(args.source) as source:
        image = ImageOps.fit(
            source.convert("RGB"),
            (WIDTH, HEIGHT),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, format="PNG", optimize=True)
    print(
        f"prepare_visual: {args.source} -> {args.output} "
        f"({WIDTH}x{HEIGHT}, full RGB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
