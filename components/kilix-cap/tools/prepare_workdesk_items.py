#!/usr/bin/env python3
"""Extract the generated Desk props into a masked runtime overlay atlas.

The telephone is supplied as a separately generated transparent sprite.  The
telephone in the original room composite was malformed and its silhouette
overlapped neighboring props, so it is intentionally not sampled here.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps


WIDTH = 480
HEIGHT = 256
SCALE = 4
PHONE_X = 340
PHONE_Y = 122  # content-local; the full-canvas y coordinate is 146
PHONE_W = 92
PHONE_H = 53


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("assets/art/workdesk-items-source.png"),
    )
    parser.add_argument(
        "--phone",
        type=Path,
        default=Path("assets/art/telephone-sprite.png"),
    )
    parser.add_argument(
        "--atlas",
        type=Path,
        default=Path("assets/art/workdesk-items.ppm"),
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=Path("assets/art/workdesk-items-mask.ppm"),
    )
    parser.add_argument(
        "--hit",
        type=Path,
        default=Path("assets/art/workdesk-items-hit.ppm"),
    )
    return parser.parse_args()


def scaled_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple(value * SCALE for value in box)  # type: ignore[return-value]


def scaled_points(
    points: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    return [(x * SCALE, y * SCALE) for x, y in points]


def build_mask() -> Image.Image:
    mask = Image.new("L", (WIDTH * SCALE, HEIGHT * SCALE), 0)
    draw = ImageDraw.Draw(mask)
    white = 255

    # Clock: wooden base plus the complete round face.
    draw.polygon(
        scaled_points([(141, 151), (146, 147), (179, 147), (184, 152),
                       (183, 156), (141, 156)]),
        fill=white,
    )
    draw.ellipse(scaled_box((143, 117, 182, 154)), fill=white)

    # Stacked in/out trays. Sloped fronts keep their silhouette distinct from
    # the rectangular interaction boxes used by the previous UI.
    draw.polygon(
        scaled_points([(72, 130), (80, 126), (138, 126), (140, 151),
                       (136, 157), (72, 157)]),
        fill=white,
    )
    draw.polygon(
        scaled_points([(72, 150), (79, 145), (138, 145), (139, 169),
                       (135, 174), (71, 174)]),
        fill=white,
    )

    # Envelope, notebook, and freestanding name card.
    draw.polygon(
        scaled_points([(56, 181), (88, 172), (112, 186), (108, 193),
                       (64, 198), (56, 190)]),
        fill=white,
    )
    draw.polygon(
        scaled_points([(147, 169), (191, 169), (185, 197), (142, 198),
                       (140, 194)]),
        fill=white,
    )
    draw.line(scaled_points([(143, 196), (165, 199)]), fill=white,
              width=3 * SCALE)
    draw.polygon(
        scaled_points([(253, 170), (273, 172), (275, 186), (250, 185)]),
        fill=white,
    )

    # Calendar, card file, and compact wooden file cabinet.
    draw.rounded_rectangle(
        scaled_box((281, 78, 313, 114)), radius=2 * SCALE, fill=white
    )
    draw.ellipse(scaled_box((285, 73, 291, 82)), fill=white)
    draw.ellipse(scaled_box((304, 73, 310, 82)), fill=white)
    draw.rounded_rectangle(
        scaled_box((278, 137, 318, 159)), radius=2 * SCALE, fill=white
    )
    for left, top, right in (
        (282, 128, 290), (289, 126, 299), (297, 127, 307),
        (305, 126, 315)
    ):
        draw.polygon(
            scaled_points([(left, 143), (left + 1, top), (right, top),
                           (right + 1, 143)]),
            fill=white,
        )
    draw.rounded_rectangle(
        scaled_box((320, 120, 363, 162)), radius=2 * SCALE, fill=white
    )

    # Paper stack and calculator.  The replacement telephone is composited
    # later from its own generated RGBA source and therefore has its own exact
    # alpha rather than a hand-authored approximation.
    draw.polygon(
        scaled_points([(301, 161), (342, 161), (349, 183), (344, 190),
                       (300, 189), (296, 178)]),
        fill=white,
    )
    draw.polygon(
        scaled_points([(354, 180), (391, 184), (388, 207), (347, 199)]),
        fill=white,
    )

    # Monitor, including its bezel, neck, and foot. The screen face itself is
    # physical and therefore deliberately belongs to the semantic hit mask.
    draw.rounded_rectangle(
        scaled_box((188, 82, 275, 137)), radius=3 * SCALE, fill=white
    )
    draw.rectangle(scaled_box((226, 136, 239, 149)), fill=white)
    draw.polygon(
        scaled_points([(216, 148), (249, 148), (253, 153), (212, 153)]),
        fill=white,
    )

    # Remove every remnant of the malformed telephone from neighboring source
    # silhouettes (it physically occluded the cabinet and calculator in the
    # furnished composite). The pristine generated phone is added afterward.
    draw.rounded_rectangle(
        scaled_box((350, 140, 432, 181)), radius=8 * SCALE, fill=0
    )
    draw.ellipse(scaled_box((401, 151, 433, 198)), fill=0)

    return mask.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def prepare_phone(path: Path) -> Image.Image:
    """Return a premultiplied-safe, aspect-preserving RGBA phone sprite."""
    with Image.open(path) as source:
        rgba = source.convert("RGBA")
    bounds = rgba.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError(f"telephone sprite has no visible pixels: {path}")
    rgba = rgba.crop(bounds)
    scale = min(PHONE_W / rgba.width, PHONE_H / rgba.height)
    size = (
        max(1, round(rgba.width * scale)),
        max(1, round(rgba.height * scale)),
    )
    # Resize premultiplied channels so fully transparent chroma-key RGB cannot
    # bleed green into the antialiased silhouette.
    resized = rgba.convert("RGBa").resize(
        size, Image.Resampling.LANCZOS
    ).convert("RGBA")
    result = Image.new("RGBA", (PHONE_W, PHONE_H), (0, 0, 0, 0))
    result.alpha_composite(
        resized, ((PHONE_W - size[0]) // 2, (PHONE_H - size[1]) // 2)
    )
    return result


def main() -> int:
    args = parse_args()
    with Image.open(args.source) as source:
        runtime = ImageOps.fit(
            source.convert("RGB"),
            (WIDTH, HEIGHT),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    mask = build_mask()
    phone = prepare_phone(args.phone)
    phone_alpha = phone.getchannel("A")
    phone_layer = Image.new("L", (WIDTH, HEIGHT), 0)
    phone_layer.paste(phone_alpha, (PHONE_X, PHONE_Y))
    mask = ImageChops.lighter(mask, phone_layer)
    # Values match IconId in src/icon.h. The tight bounds disambiguate the
    # few natural front-to-back overlaps (notebook/name card over monitor).
    hit_bounds = (
        (5, (250, 170, 25, 17)),   # name card, foreground
        (6, (139, 168, 53, 34)),   # notebook
        (11, (296, 160, 54, 31)),  # paper
        (12, (347, 180, 45, 29)),  # calculator
        (10, (PHONE_X, PHONE_Y, PHONE_W, PHONE_H)),  # generated phone
        (1, (140, 116, 45, 41)),   # clock
        (2, (71, 126, 70, 25)),    # in tray
        (3, (71, 145, 70, 30)),    # out tray
        (4, (55, 171, 58, 28)),    # envelope
        (7, (280, 72, 35, 43)),    # calendar
        (8, (277, 125, 42, 35)),   # card file
        (9, (319, 119, 45, 44)),   # file drawers
        (13, (187, 81, 89, 73)),   # monitor, behind foreground props
    )
    hit = Image.new("L", (WIDTH, HEIGHT), 0)
    alpha = mask.load()
    hit_pixels = hit.load()
    for py in range(HEIGHT):
        for px in range(WIDTH):
            if alpha[px, py] < 128:
                continue
            for icon_id, (left, top, width, height) in hit_bounds:
                if left <= px < left + width and top <= py < top + height:
                    hit_pixels[px, py] = icon_id
                    break
    visible = mask.point(lambda value: 255 if value else 0)
    atlas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    atlas.paste(runtime, mask=visible)
    # Replace the malformed source telephone pixels with the separately
    # generated coherent handset/base sprite.  Its alpha has already replaced
    # that region in the visual mask above.
    phone_visible = phone_alpha.point(lambda value: 255 if value else 0)
    atlas.paste(phone.convert("RGB"), (PHONE_X, PHONE_Y), phone_visible)
    mask_rgb = Image.merge("RGB", (mask, mask, mask))
    hit_rgb = Image.merge("RGB", (hit, hit, hit))

    args.atlas.parent.mkdir(parents=True, exist_ok=True)
    args.mask.parent.mkdir(parents=True, exist_ok=True)
    args.hit.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(args.atlas, format="PPM")
    mask_rgb.save(args.mask, format="PPM")
    hit_rgb.save(args.hit, format="PPM")
    print(
        f"prepare_workdesk_items: {args.source} -> {args.atlas}, {args.mask}, "
        f"{args.hit} ({WIDTH}x{HEIGHT} full RGB + visual alpha + semantic "
        f"hit IDs; phone {args.phone})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
