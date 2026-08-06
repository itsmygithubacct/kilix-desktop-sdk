#!/usr/bin/env python3
"""Prepare the generated Server Room breaker face for runtime composition.

One subject — the master breaker panel — arrives as a keyed RGBA image and
is fitted into a single 30x50 cell, written as an RGB raster plus a
grayscale coverage mask. The pair is an OPTIONAL add-on to the mandatory
bundle (src/art.c loads it both-or-neither), so this tool never touches the
thirteen mandatory runtime files and a tree without it keeps the procedural
drawing.

The cell is exactly the size the panel occupies on the wall, so the runtime
draws it one-to-one. Fitting a taller-than-wide subject into a cell of some
other shape would leave transparent margins that the draw path stretches
along with the art, which is how a correctly drawn panel ends up looking
squashed on the wall.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


CELL_W = 90
CELL_H = 150
PADDING = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("assets/art/breaker.png"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/art/breaker.ppm"),
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=Path("assets/art/breaker-mask.ppm"),
    )
    return parser.parse_args()


def only_the_panel(image: Image.Image) -> Image.Image:
    """Drop everything not joined to the largest visible shape.

    Chroma removal leaves a few near-transparent specks of key noise in the
    corners, and the bounding box does not care how faint they are: one
    stray pixel in a corner stretches the box to the whole frame and the
    subject is then fitted as if it were tiny. This asset is exactly one
    prop, so anything not connected to the biggest shape is noise by
    definition.
    """
    alpha = image.getchannel("A")
    width, height = alpha.size
    pixels = alpha.load()
    seen = bytearray(width * height)
    best_size = 0
    best_seed: tuple[int, int] | None = None
    for start_y in range(height):
        for start_x in range(width):
            if not pixels[start_x, start_y] or seen[start_y * width + start_x]:
                continue
            stack = [(start_x, start_y)]
            seen[start_y * width + start_x] = 1
            size = 0
            while stack:
                x, y = stack.pop()
                size += 1
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if (0 <= nx < width and 0 <= ny < height
                            and not seen[ny * width + nx]
                            and pixels[nx, ny]):
                        seen[ny * width + nx] = 1
                        stack.append((nx, ny))
            if size > best_size:
                best_size, best_seed = size, (start_x, start_y)
    if best_seed is None:
        raise ValueError("breaker source has no visible subject")

    keep = Image.new("L", (width, height), 0)
    kept = keep.load()
    seen = bytearray(width * height)
    stack = [best_seed]
    seen[best_seed[1] * width + best_seed[0]] = 1
    while stack:
        x, y = stack.pop()
        kept[x, y] = 255
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (0 <= nx < width and 0 <= ny < height
                    and not seen[ny * width + nx] and pixels[nx, ny]):
                seen[ny * width + nx] = 1
                stack.append((nx, ny))
    result = image.copy()
    result.putalpha(Image.composite(alpha, Image.new("L", alpha.size, 0),
                                    keep))
    return result


def fitted_sprite(image: Image.Image) -> Image.Image:
    image = only_the_panel(image)
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("breaker source has no visible subject")
    subject = image.crop(bounds)
    max_w = CELL_W - 2 * PADDING
    max_h = CELL_H - 2 * PADDING
    scale = min(max_w / subject.width, max_h / subject.height)
    width = max(1, round(subject.width * scale))
    height = max(1, round(subject.height * scale))
    # Resize premultiplied channels so antialiased edges do not regain the
    # removed green backdrop when reduced to the small runtime cell.
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
        keyed = source.convert("RGBA")

    cell = fitted_sprite(keyed)
    alpha = cell.getchannel("A")
    visible = alpha.point(lambda value: 255 if value else 0)
    rgb = Image.new("RGB", cell.size, (0, 0, 0))
    rgb.paste(cell.convert("RGB"), mask=visible)
    alpha_rgb = Image.merge("RGB", (alpha, alpha, alpha))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.mask.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(args.output, format="PPM")
    alpha_rgb.save(args.mask, format="PPM")
    print(
        f"prepare_breaker: {args.source} -> {args.output}, {args.mask} "
        f"(one {CELL_W}x{CELL_H} breaker face)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
