#!/usr/bin/env python3
"""Extract the generated Desk props into a masked runtime overlay atlas.

The telephone is supplied as a separately generated transparent sprite.  The
telephone in the original room composite was malformed and its silhouette
overlapped neighboring props, so it is intentionally not sampled here.

Each prop is rasterized on its own coverage layer.  The visual mask is their
union, so it is exactly what a single shared canvas would have produced, but
keeping the layers apart lets the semantic map credit every pixel to the
silhouette that actually covers it rather than to whichever declared box
happens to be listed first.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps


WIDTH = 1440
HEIGHT = 768
SCALE = 4
# The shapes below are authored in the original 480x256 room space. ART_SCALE
# carries them to the canvas the runtime actually uses; SCALE stays what it
# always was, the supersampling factor the drawing is antialiased through.
# Multiplying only the output size would leave every shape in the top-left
# corner at its original size, which is exactly what a stale ART_SCALE looks
# like.
ART_SCALE = 3
PEN = SCALE * ART_SCALE
WHITE = 255
PHONE_ICON = 10
PHONE_X = 1020
PHONE_Y = 366  # content-local; the full-canvas y coordinate is 438
PHONE_W = 276
PHONE_H = 159


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
        default=Path("assets/art/runtime/workdesk-items.png"),
    )
    parser.add_argument(
        "--mask",
        type=Path,
        default=Path("assets/art/runtime/workdesk-items-mask.png"),
    )
    parser.add_argument(
        "--hit",
        type=Path,
        default=Path("assets/art/runtime/workdesk-items-hit.png"),
    )
    return parser.parse_args()


def scaled_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple(value * PEN for value in box)  # type: ignore[return-value]


def scaled_points(
    points: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    return [(x * PEN, y * PEN) for x, y in points]


def draw_clock(draw: ImageDraw.ImageDraw) -> None:
    """Wooden base plus the complete round face."""
    draw.polygon(
        scaled_points([(141, 151), (146, 147), (179, 147), (184, 152),
                       (183, 156), (141, 156)]),
        fill=WHITE,
    )
    draw.ellipse(scaled_box((143, 117, 182, 154)), fill=WHITE)


def draw_in_tray(draw: ImageDraw.ImageDraw) -> None:
    """Upper half of the stacked trays.  Sloped fronts keep its silhouette
    distinct from the rectangular interaction boxes used by the previous UI."""
    draw.polygon(
        scaled_points([(72, 130), (80, 126), (138, 126), (140, 151),
                       (136, 157), (72, 157)]),
        fill=WHITE,
    )


def draw_out_tray(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(
        scaled_points([(72, 150), (79, 145), (138, 145), (139, 169),
                       (135, 174), (71, 174)]),
        fill=WHITE,
    )


def draw_envelope(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(
        scaled_points([(56, 181), (88, 172), (112, 186), (108, 193),
                       (64, 198), (56, 190)]),
        fill=WHITE,
    )


def draw_notebook(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(
        scaled_points([(147, 169), (191, 169), (185, 197), (142, 198),
                       (140, 194)]),
        fill=WHITE,
    )
    draw.line(scaled_points([(143, 196), (165, 199)]), fill=WHITE,
              width=3 * PEN)


def draw_name_card(draw: ImageDraw.ImageDraw) -> None:
    """Freestanding name card."""
    draw.polygon(
        scaled_points([(253, 170), (273, 172), (275, 186), (250, 185)]),
        fill=WHITE,
    )


def draw_calendar(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle(
        scaled_box((281, 78, 313, 114)), radius=2 * PEN, fill=WHITE
    )
    draw.ellipse(scaled_box((285, 73, 291, 82)), fill=WHITE)
    draw.ellipse(scaled_box((304, 73, 310, 82)), fill=WHITE)


def draw_card_file(draw: ImageDraw.ImageDraw) -> None:
    """Tray plus the fanned cards standing in it."""
    draw.rounded_rectangle(
        scaled_box((278, 137, 318, 159)), radius=2 * PEN, fill=WHITE
    )
    for left, top, right in (
        (282, 128, 290), (289, 126, 299), (297, 127, 307),
        (305, 126, 315)
    ):
        draw.polygon(
            scaled_points([(left, 143), (left + 1, top), (right, top),
                           (right + 1, 143)]),
            fill=WHITE,
        )


def draw_cabinet(draw: ImageDraw.ImageDraw) -> None:
    """Compact wooden file cabinet."""
    draw.rounded_rectangle(
        scaled_box((320, 120, 363, 162)), radius=2 * PEN, fill=WHITE
    )


def draw_paper(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(
        scaled_points([(301, 161), (342, 161), (349, 183), (344, 190),
                       (300, 189), (296, 178)]),
        fill=WHITE,
    )


def draw_calculator(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(
        scaled_points([(356, 176), (393, 181), (394, 185), (391, 204),
                       (388, 210), (385, 212), (346, 203), (343, 199),
                       (350, 183)]),
        fill=WHITE,
    )


def draw_monitor(draw: ImageDraw.ImageDraw) -> None:
    """Bezel, neck, and foot. The screen face itself is physical and therefore
    deliberately belongs to the semantic hit mask."""
    draw.rounded_rectangle(
        scaled_box((188, 82, 275, 137)), radius=3 * PEN, fill=WHITE
    )
    draw.rectangle(scaled_box((226, 136, 239, 149)), fill=WHITE)
    draw.polygon(
        scaled_points([(216, 148), (249, 148), (253, 153), (212, 153)]),
        fill=WHITE,
    )


# IconId (src/icon.h) -> declared bounds and silhouette, front to back.  The
# bounds are the extents src/art.c's desk_sprites table declares, minus
# CONTENT_Y; art.c re-checks that containment when it loads the bundle, so a
# prop may only ever claim pixels inside its own box.  Listing order settles
# genuine ties, where two silhouettes cover one pixel equally.  The replacement
# telephone has no hand-authored outline: it is composited later from its own
# generated RGBA source and so carries its exact alpha as coverage.
# Declared bounds are in the runtime canvas space (content-local), and must
# stay in step with src/art.c's desk_sprites table: build_hit() lets a prop
# claim pixels only inside these, so a stale table silently empties the mask
# of every prop rather than failing loudly.
ITEMS: tuple[tuple[int, tuple[int, int, int, int], object], ...] = (
    (5, (750, 510, 75, 51), draw_name_card),
    (6, (417, 504, 159, 102), draw_notebook),
    (11, (888, 480, 162, 93), draw_paper),
    (12, (1029, 528, 156, 111), draw_calculator),
    (PHONE_ICON, (PHONE_X, PHONE_Y, PHONE_W, PHONE_H), None),
    (1, (420, 348, 135, 123), draw_clock),
    (2, (213, 378, 210, 75), draw_in_tray),
    (3, (213, 435, 210, 90), draw_out_tray),
    (4, (165, 513, 174, 84), draw_envelope),
    (7, (840, 216, 105, 129), draw_calendar),
    (8, (831, 375, 126, 105), draw_card_file),
    (9, (957, 357, 135, 132), draw_cabinet),
    (13, (561, 243, 267, 219), draw_monitor),
)


def erase_phone_remnants(draw: ImageDraw.ImageDraw) -> None:
    """Remove every remnant of the malformed telephone from neighboring source
    silhouettes (it physically occluded the cabinet and calculator in the
    furnished composite). The pristine generated phone is added afterward.

    Stop above the calculator at y=176.  The source calculator's raised display
    housing begins there; extending this cleanup farther down makes its top
    appear clipped in the final 480px scene.
    """
    draw.rounded_rectangle(
        scaled_box((350, 140, 432, 175)), radius=8 * PEN, fill=0
    )
    draw.ellipse(scaled_box((401, 151, 433, 198)), fill=0)


def build_layers() -> tuple[Image.Image, dict[int, Image.Image]]:
    """Return the combined visual mask and one coverage layer per prop."""
    size = (WIDTH * SCALE, HEIGHT * SCALE)
    combined = Image.new("L", size, 0)
    layers: dict[int, Image.Image] = {}
    for icon_id, _bounds, shape in ITEMS:
        if shape is None:
            continue
        layer = Image.new("L", size, 0)
        shape(ImageDraw.Draw(layer))
        combined = ImageChops.lighter(combined, layer)
        erase_phone_remnants(ImageDraw.Draw(layer))
        layers[icon_id] = layer.resize(
            (WIDTH, HEIGHT), Image.Resampling.LANCZOS
        )
    erase_phone_remnants(ImageDraw.Draw(combined))
    return (
        combined.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS),
        layers,
    )


def build_hit(
    mask: Image.Image, coverage: dict[int, Image.Image]
) -> Image.Image:
    """Credit each covered pixel to the silhouette that actually claims it.

    A prop may only claim pixels inside its declared bounds, so the runtime
    containment check in src/art.c holds by construction.  Among the props
    whose bounds do contain the pixel, the front-most one that covers at least
    half of it wins -- the same >=128 threshold the runtime treats as covered.
    Where no silhouette reaches that, the largest partial coverage wins, which
    settles antialiased seams in favor of whichever prop is really there.  A
    pixel no silhouette claims at all stays 0 rather than falling to a
    neighbor: the trays' hidden lower edges run past their declared bounds, and
    an inert pixel beats one that opens the wrong drawer.
    """
    hit = Image.new("L", (WIDTH, HEIGHT), 0)
    alpha = mask.load()
    hit_pixels = hit.load()
    layers = [
        (icon_id, bounds, coverage[icon_id].load())
        for icon_id, bounds, _shape in ITEMS
    ]
    for py in range(HEIGHT):
        for px in range(WIDTH):
            if alpha[px, py] < 128:
                continue
            best_id = 0
            best_cover = 0
            for icon_id, (left, top, width, height), cover in layers:
                if not (left <= px < left + width and
                        top <= py < top + height):
                    continue
                value = cover[px, py]
                if value >= 128:
                    best_id = icon_id
                    break
                if value > best_cover:
                    best_id = icon_id
                    best_cover = value
            hit_pixels[px, py] = best_id
    return hit


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
    mask, coverage = build_layers()
    phone = prepare_phone(args.phone)
    phone_alpha = phone.getchannel("A")
    phone_layer = Image.new("L", (WIDTH, HEIGHT), 0)
    phone_layer.paste(phone_alpha, (PHONE_X, PHONE_Y))
    mask = ImageChops.lighter(mask, phone_layer)
    coverage[PHONE_ICON] = phone_layer
    hit = build_hit(mask, coverage)
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
    atlas.save(args.atlas, format="PNG", optimize=True)
    mask_rgb.save(args.mask, format="PNG", optimize=True)
    hit_rgb.save(args.hit, format="PNG", optimize=True)
    print(
        f"prepare_workdesk_items: {args.source} -> {args.atlas}, {args.mask}, "
        f"{args.hit} ({WIDTH}x{HEIGHT} full RGB + visual alpha + semantic "
        f"hit IDs; phone {args.phone})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
