#!/usr/bin/env python3
"""Prepare the generated 3x3 game-media sheet for runtime composition."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


COLS = 3
ROWS = 3
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
        default=Path("assets/art/game-media.png"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/art/runtime/game-media.png"),
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=Path("assets/art/runtime/game-media-mask.png"),
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
        raise ValueError("game-media grid cell has no visible subject")
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
    rgb.save(args.output, format="PNG", optimize=True)
    alpha_rgb.save(args.mask, format="PNG", optimize=True)
    print(
        f"prepare_game_media: {args.source} -> {args.output}, {args.mask} "
        f"({ATLAS_W}x{ATLAS_H}, nine {CELL_W}x{CELL_H} sprites)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
