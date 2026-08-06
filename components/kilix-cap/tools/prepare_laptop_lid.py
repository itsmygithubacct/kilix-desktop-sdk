#!/usr/bin/env python3
"""Prepare the generated laptop-lid pair for runtime composition.

Two frames of the Study laptop's lid — fully closed (0) and half-open
(1) — arrive as one keyed RGBA sheet on an invisible 2-column by 1-row
grid. Like mansion-items, each subject is fitted into a 48x56 cell and
the result is written as an RGB atlas plus a grayscale coverage mask.
The pair is an OPTIONAL add-on to the mandatory bundle (src/art.c loads
it both-or-neither, and only alongside the mansion-items pair whose open
laptop it animates), so this tool never touches the thirteen mandatory
runtime files. The open frame stays where it always was: mansion-items
cell 3.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


COLS = 2
ROWS = 1
CELL_W = 144
CELL_H = 168
PADDING = 6
ATLAS_W = COLS * CELL_W
ATLAS_H = ROWS * CELL_H


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("assets/art/laptop-lid.png"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/art/laptop-lid.ppm"),
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=Path("assets/art/laptop-lid-mask.ppm"),
    )
    return parser.parse_args()


def cell_bounds(width: int, height: int, col: int, row: int) -> tuple[int, ...]:
    return (
        round(col * width / COLS),
        round(row * height / ROWS),
        round((col + 1) * width / COLS),
        round((row + 1) * height / ROWS),
    )


def fitted_sprite(cell: Image.Image) -> Image.Image:
    bounds = cell.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("laptop-lid grid cell has no visible subject")
    subject = cell.crop(bounds)
    max_w = CELL_W - 2 * PADDING
    max_h = CELL_H - 2 * PADDING
    scale = min(max_w / subject.width, max_h / subject.height)
    width = max(1, round(subject.width * scale))
    height = max(1, round(subject.height * scale))
    # Resize premultiplied channels so antialiased edges do not regain the
    # removed green backdrop when reduced to the small runtime atlas.
    subject = subject.convert("RGBa").resize(
        (width, height), Image.Resampling.LANCZOS
    ).convert("RGBA")
    result = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
    result.alpha_composite(subject, ((CELL_W - width) // 2,
                                     (CELL_H - height) // 2))
    return result


def main() -> int:
    args = parse_args()
    with Image.open(args.source) as source:
        sheet = source.convert("RGBA")

    atlas = Image.new("RGBA", (ATLAS_W, ATLAS_H), (0, 0, 0, 0))
    for row in range(ROWS):
        for col in range(COLS):
            cell = sheet.crop(cell_bounds(sheet.width, sheet.height, col, row))
            sprite = fitted_sprite(cell)
            atlas.alpha_composite(sprite, (col * CELL_W, row * CELL_H))

    alpha = atlas.getchannel("A")
    visible = alpha.point(lambda value: 255 if value else 0)
    rgb = Image.new("RGB", atlas.size, (0, 0, 0))
    rgb.paste(atlas.convert("RGB"), mask=visible)
    alpha_rgb = Image.merge("RGB", (alpha, alpha, alpha))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.mask.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(args.output, format="PPM")
    alpha_rgb.save(args.mask, format="PPM")
    print(
        f"prepare_laptop_lid: {args.source} -> {args.output}, {args.mask} "
        f"({ATLAS_W}x{ATLAS_H}, two {CELL_W}x{CELL_H} lid frames)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
