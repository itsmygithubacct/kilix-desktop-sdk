#!/usr/bin/env python3
"""Validate the complete layered room-art bundle and its provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "visual-provenance.json"
ART_DIRECTORY = ROOT / "assets" / "art"
WIDTH = 480
HEIGHT = 256

SOURCE_PNGS = {
    "assets/art/workdesk-items-source.png",
    "assets/art/workdesk-room.png",
    "assets/art/hallway-room.png",
    "assets/art/storeroom-room.png",
    "assets/art/server-room.png",
    "assets/art/game-room.png",
    "assets/art/library-room.png",
    "assets/art/cleaning-room.png",
    "assets/art/balcony-room.png",
    "assets/art/game-media-source.png",
    "assets/art/game-media.png",
    "assets/art/telephone-sprite-source.png",
    "assets/art/telephone-sprite.png",
    "assets/art/workdesk-room-door-source.png",
    "assets/art/hallway-room-doors-source.png",
    "assets/art/storeroom-room-door-source.png",
    "assets/art/server-room-door-source.png",
    "assets/art/game-room-door-source.png",
    "assets/art/library-room-door-source.png",
    "assets/art/cleaning-room-door-source.png",
}
BACKGROUND_PPMS = {
    "assets/art/workdesk-room.ppm",
    "assets/art/hallway-room.ppm",
    "assets/art/storeroom-room.ppm",
    "assets/art/server-room.ppm",
    "assets/art/game-room.ppm",
    "assets/art/library-room.ppm",
    "assets/art/cleaning-room.ppm",
    "assets/art/balcony-room.ppm",
}
ITEM_ATLAS = "assets/art/workdesk-items.ppm"
ITEM_ALPHA = "assets/art/workdesk-items-mask.ppm"
ITEM_HIT = "assets/art/workdesk-items-hit.ppm"
GAME_MEDIA = "assets/art/game-media.ppm"
GAME_MEDIA_ALPHA = "assets/art/game-media-mask.ppm"
EXPECTED_PATHS = SOURCE_PNGS | BACKGROUND_PPMS | {
    ITEM_ATLAS,
    ITEM_ALPHA,
    ITEM_HIT,
    GAME_MEDIA,
    GAME_MEDIA_ALPHA,
}
NORMALIZED_SOURCE_PNGS = {
    "assets/art/hallway-room.png",
    "assets/art/hallway-room-doors-source.png",
    "assets/art/server-room-door-source.png",
}

# The OPTIONAL small-prop group (Storeroom box/crate/tin + Study laptop).
# src/art.c loads the runtime pair both-or-neither after the mandatory
# bundle. The group ships only after by-eye review, so assets/art must
# contain either none of these files (review pending; procedural drawings
# serve) or all four plus their own provenance manifest below.
MANSION_MANIFEST = ROOT / "docs" / "visual-provenance-gemini.json"
MANSION_SOURCE = "assets/art/mansion-items-source.png"
MANSION_KEYED = "assets/art/mansion-items.png"
MANSION_ATLAS = "assets/art/mansion-items.ppm"
MANSION_ALPHA = "assets/art/mansion-items-mask.ppm"
MANSION_PATHS = {MANSION_SOURCE, MANSION_KEYED, MANSION_ATLAS,
                 MANSION_ALPHA}
MANSION_W = 96
MANSION_H = 112
MANSION_CELL_W = 48
MANSION_CELL_H = 56
MANSION_VARIANTS = 4

SEMANTIC_IDS = {
    1: "Clock",
    2: "In box",
    3: "Out box",
    4: "New-message postcard",
    5: "Own name card",
    6: "Notepad",
    7: "Datebook",
    8: "Name card file",
    9: "File cabinet",
    10: "Telephone",
    11: "Stationery drawer",
    12: "Desk accessories drawer",
    13: "Web access monitor",
}


class VisualError(Exception):
    """A concise, user-facing visual validation failure."""


def regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise VisualError(f"{path.relative_to(ROOT)} is not a regular file")
    return path.read_bytes()


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise VisualError("source is not a PNG with a complete IHDR chunk")
    if data[12:16] != b"IHDR":
        raise VisualError("source PNG does not begin with IHDR")
    width, height = struct.unpack(">II", data[16:24])
    bit_depth, color_type = data[24], data[25]
    if bit_depth != 8 or color_type not in (2, 6):
        raise VisualError("source PNG must be 8-bit RGB or RGBA")
    return width, height


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise VisualError("source is not a PNG")
    chunks: list[tuple[bytes, bytes]] = []
    position = 8
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        payload_start = position + 8
        payload_end = payload_start + length
        chunk_end = payload_end + 4
        if chunk_end > len(data):
            raise VisualError("source PNG has a truncated chunk")
        expected_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
        actual_crc = zlib.crc32(kind)
        actual_crc = zlib.crc32(data[payload_start:payload_end], actual_crc)
        if actual_crc & 0xFFFFFFFF != expected_crc:
            raise VisualError("source PNG has a bad chunk CRC")
        chunks.append((kind, data[payload_start:payload_end]))
        position = chunk_end
        if kind == b"IEND":
            break
    if position != len(data) or not chunks or chunks[-1][0] != b"IEND":
        raise VisualError("source PNG has an invalid chunk sequence")
    return chunks


def paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def png_decoded_rgb_sha256(data: bytes) -> str:
    width, height = png_dimensions(data)
    if data[25] != 2 or data[26:29] != b"\x00\x00\x00":
        raise VisualError(
            "normalized source PNG must be non-interlaced 8-bit RGB"
        )
    chunks = png_chunks(data)
    compressed = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    try:
        filtered = zlib.decompress(compressed)
    except zlib.error as exc:
        raise VisualError("normalized source PNG has invalid IDAT data") from exc
    bytes_per_pixel = 3
    stride = width * bytes_per_pixel
    if len(filtered) != height * (stride + 1):
        raise VisualError("normalized source PNG has an invalid scanline length")

    decoded = bytearray()
    previous = bytearray(stride)
    position = 0
    for _ in range(height):
        filter_type = filtered[position]
        position += 1
        current = bytearray(filtered[position : position + stride])
        position += stride
        for index in range(stride):
            left = (
                current[index - bytes_per_pixel]
                if index >= bytes_per_pixel
                else 0
            )
            up = previous[index]
            upper_left = (
                previous[index - bytes_per_pixel]
                if index >= bytes_per_pixel
                else 0
            )
            if filter_type == 1:
                current[index] = (current[index] + left) & 0xFF
            elif filter_type == 2:
                current[index] = (current[index] + up) & 0xFF
            elif filter_type == 3:
                current[index] = (current[index] + (left + up) // 2) & 0xFF
            elif filter_type == 4:
                current[index] = (
                    current[index] + paeth(left, up, upper_left)
                ) & 0xFF
            elif filter_type != 0:
                raise VisualError(
                    f"normalized source PNG uses unknown filter {filter_type}"
                )
        decoded.extend(current)
        previous = current
    return hashlib.sha256(decoded).hexdigest()


def is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def ppm_raster(data: bytes) -> tuple[int, int, bytes]:
    position = 0
    tokens: list[bytes] = []
    while len(tokens) < 4:
        while position < len(data) and data[position] in b" \t\r\n\v\f":
            position += 1
        if position < len(data) and data[position] == ord("#"):
            newline = data.find(b"\n", position)
            if newline < 0:
                raise VisualError("unterminated PPM comment")
            position = newline + 1
            continue
        start = position
        while position < len(data) and data[position] not in b" \t\r\n\v\f#":
            position += 1
        if start == position:
            raise VisualError("truncated PPM header")
        tokens.append(data[start:position])
    if tokens[0] != b"P6":
        raise VisualError("runtime art is not binary P6")
    try:
        width, height, maximum = map(int, tokens[1:])
    except ValueError as exc:
        raise VisualError("invalid numeric PPM header") from exc
    if width <= 0 or height <= 0 or maximum != 255:
        raise VisualError("runtime PPM has invalid dimensions or maxval")
    if position >= len(data) or data[position] not in b" \t\r\n\v\f":
        raise VisualError("missing PPM raster separator")
    position += 2 if data[position : position + 2] == b"\r\n" else 1
    raster = data[position:]
    expected = width * height * 3
    if len(raster) != expected:
        raise VisualError(
            f"runtime PPM raster is {len(raster)} bytes; expected {expected}"
        )
    return width, height, raster


def require_runtime_dimensions(path: str, data: bytes) -> bytes:
    width, height, raster = ppm_raster(data)
    if (width, height) != (WIDTH, HEIGHT):
        raise VisualError(
            f"{path} is {width}x{height}; expected {WIDTH}x{HEIGHT}"
        )
    return raster


def rgb_pixels(raster: bytes):
    for offset in range(0, len(raster), 3):
        yield (raster[offset], raster[offset + 1], raster[offset + 2])


def validate_color_art(path: str, raster: bytes, *, background: bool) -> None:
    colors: set[tuple[int, int, int]] = set()
    chromatic = 0
    black = 0
    for rgb in rgb_pixels(raster):
        colors.add(rgb)
        if max(rgb) - min(rgb) >= 12:
            chromatic += 1
        if rgb == (0, 0, 0):
            black += 1
    if len(colors) < 128:
        raise VisualError(f"{path} has only {len(colors)} RGB colors")
    pixel_count = len(raster) // 3
    if background:
        # The Server Room intentionally devotes substantial area to neutral
        # near-black monitor glass and charcoal racks. Half the plate still
        # has to carry measurable color, which rejects grayscale regressions
        # without rejecting that deliberate low-key environment.
        if chromatic < pixel_count // 2:
            raise VisualError(f"{path} is not substantially chromatic")
    else:
        if chromatic < 10000:
            raise VisualError(f"{path} does not contain a substantial item layer")
        if black < WIDTH * HEIGHT // 2:
            raise VisualError(f"{path} does not preserve an empty black exterior")


def gray_values(path: str, raster: bytes) -> list[int]:
    values: list[int] = []
    for red, green, blue in rgb_pixels(raster):
        if red != green or red != blue:
            raise VisualError(f"{path} is not an RGB-encoded grayscale map")
        values.append(red)
    return values


def validate_alpha(path: str, values: list[int], minimum_coverage: int) -> None:
    distinct = set(values)
    if 0 not in distinct or 255 not in distinct:
        raise VisualError(f"{path} must contain fully clear and fully opaque pixels")
    if len(distinct) < 16 or not any(0 < value < 255 for value in distinct):
        raise VisualError(f"{path} does not contain anti-aliased coverage")
    if sum(value > 0 for value in values) < minimum_coverage:
        raise VisualError(f"{path} contains too little object coverage")


def validate_media_art(path: str, raster: bytes) -> None:
    pixels = list(rgb_pixels(raster))
    colors = set(pixels)
    chromatic = sum(max(rgb) - min(rgb) >= 12 for rgb in pixels)
    black = pixels.count((0, 0, 0))
    if len(colors) < 128 or chromatic < len(pixels) // 3:
        raise VisualError(f"{path} lacks full-color generated media")
    if black < len(pixels) // 3:
        raise VisualError(f"{path} lacks a substantial masked exterior")


def validate_hit(path: str, values: list[int]) -> None:
    expected = {0, *SEMANTIC_IDS}
    actual = set(values)
    if actual != expected:
        raise VisualError(
            f"{path} semantic IDs are {sorted(actual)}; expected {sorted(expected)}"
        )
    for semantic_id, name in SEMANTIC_IDS.items():
        if values.count(semantic_id) < 100:
            raise VisualError(
                f"{path} has too little coverage for ID {semantic_id} ({name})"
            )


def validate_layer_relationships(
    atlas: bytes, alpha: list[int], hit: list[int]
) -> None:
    for index, (rgb, coverage, semantic_id) in enumerate(
        zip(rgb_pixels(atlas), alpha, hit)
    ):
        if coverage == 0 and rgb != (0, 0, 0):
            raise VisualError(
                f"item atlas has color outside its alpha at pixel {index}"
            )
        if semantic_id != 0 and coverage < 128:
            raise VisualError(
                f"semantic hit ID lies outside the item body at pixel {index}"
            )


def validate_manifest(
    manifest: dict,
) -> tuple[dict[str, dict], dict[str, dict]]:
    if manifest.get("schema") != "kilix-cap-visual-provenance-v5":
        raise VisualError("unexpected visual provenance schema")
    if manifest.get("status") != "release-approved":
        raise VisualError("visual bundle is not release-approved")
    if manifest.get("requested_generator") != "Gemini image generation":
        raise VisualError("requested image generator is not recorded")

    generator = manifest.get("actual_generator")
    if not isinstance(generator, dict):
        raise VisualError("actual image generator is not recorded")
    if (
        generator.get("provider") != "OpenAI built-in image generation tool"
        or generator.get("model_identifier") != "not exposed by the tool"
        or not isinstance(generator.get("reason"), str)
        or "Gemini" not in generator["reason"]
        or "unavailable" not in generator["reason"]
    ):
        raise VisualError("actual image generator record is incomplete")

    generations = manifest.get("generations")
    expected_generation_ids = {
        "desk-items-base",
        "desk-calendar-edit",
        "desk-clean-background",
        "hallway-grand-gallery",
        "storeroom-clean-background",
        "server-room",
        "game-room-clean-background",
        "library-room",
        "cleaning-room",
        "balcony-room",
        "game-media-sprite-sheet",
        "telephone-sprite",
        "study-door-edit",
        "hallway-doors-edit",
        "storeroom-door-edit",
        "server-room-door-edit",
        "game-room-door-edit",
        "library-door-edit",
        "cleaning-room-door-edit",
    }
    if not isinstance(generations, list) or any(
        not isinstance(entry, dict) for entry in generations
    ):
        raise VisualError("generation lineage must be a list of objects")
    by_id = {entry.get("id"): entry for entry in generations}
    if set(by_id) != expected_generation_ids or len(by_id) != len(generations):
        raise VisualError("generation lineage does not name the exact nineteen passes")
    for generation_id, entry in by_id.items():
        if (
            entry.get("tool") != "OpenAI built-in image generation tool"
            or entry.get("mode") not in ("text-to-image", "image-edit")
            or not isinstance(entry.get("prompt"), str)
            or not entry["prompt"].strip()
            or not is_sha256(entry.get("output_sha256"))
        ):
            raise VisualError(f"generation pass {generation_id!r} is incomplete")

    base_hash = by_id["desk-items-base"]["output_sha256"]
    calendar = by_id["desk-calendar-edit"]
    cleanup = by_id["desk-clean-background"]
    if (
        by_id["desk-items-base"].get("mode") != "text-to-image"
        or calendar.get("mode") != "image-edit"
        or calendar.get("input_sha256") != base_hash
        or cleanup.get("mode") != "image-edit"
        or cleanup.get("input_sha256") != calendar["output_sha256"]
        or by_id["hallway-grand-gallery"].get("mode") != "text-to-image"
        or by_id["storeroom-clean-background"].get("mode") != "text-to-image"
        or by_id["server-room"].get("mode") != "text-to-image"
        or by_id["game-room-clean-background"].get("mode") != "image-edit"
        or by_id["library-room"].get("mode") != "text-to-image"
        or by_id["cleaning-room"].get("mode") != "text-to-image"
        or by_id["balcony-room"].get("mode") != "text-to-image"
        or by_id["game-media-sprite-sheet"].get("mode") != "image-edit"
        or by_id["telephone-sprite"].get("mode") != "image-edit"
    ):
        raise VisualError("generated-image edit lineage is inconsistent")

    room_door_edits = {
        "study-door-edit": "desk-clean-background",
        "hallway-doors-edit": "hallway-grand-gallery",
        "storeroom-door-edit": "storeroom-clean-background",
        "server-room-door-edit": "server-room",
        "game-room-door-edit": "game-room-clean-background",
        "library-door-edit": "library-room",
        "cleaning-room-door-edit": "cleaning-room",
    }
    for edit_id, room_id in room_door_edits.items():
        edit = by_id[edit_id]
        room = by_id[room_id]
        if (
            edit.get("mode") != "image-edit"
            or edit.get("input_path") != room.get("output_path")
            or edit.get("input_sha256") != room.get("output_sha256")
        ):
            raise VisualError(f"generation pass {edit_id!r} has invalid room lineage")

    entries = manifest.get("assets")
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict) for entry in entries
    ):
        raise VisualError("asset inventory must be a list of objects")
    by_path = {entry.get("path"): entry for entry in entries}
    if set(by_path) != EXPECTED_PATHS or len(by_path) != len(entries):
        raise VisualError("manifest does not name the exact thirty-three-file art inventory")

    output_links = {
        "assets/art/workdesk-items-source.png": calendar["output_sha256"],
        "assets/art/workdesk-room.png": cleanup["output_sha256"],
        "assets/art/hallway-room.png": by_id["hallway-grand-gallery"][
            "output_sha256"
        ],
        "assets/art/storeroom-room.png": by_id["storeroom-clean-background"][
            "output_sha256"
        ],
        "assets/art/server-room.png": by_id["server-room"]["output_sha256"],
        "assets/art/game-room.png": by_id["game-room-clean-background"][
            "output_sha256"
        ],
        "assets/art/library-room.png": by_id["library-room"]["output_sha256"],
        "assets/art/cleaning-room.png": by_id["cleaning-room"]["output_sha256"],
        "assets/art/balcony-room.png": by_id["balcony-room"]["output_sha256"],
        "assets/art/game-media-source.png": by_id["game-media-sprite-sheet"][
            "output_sha256"
        ],
        "assets/art/telephone-sprite-source.png": by_id["telephone-sprite"][
            "output_sha256"
        ],
        "assets/art/workdesk-room-door-source.png": by_id["study-door-edit"][
            "output_sha256"
        ],
        "assets/art/hallway-room-doors-source.png": by_id[
            "hallway-doors-edit"
        ]["output_sha256"],
        "assets/art/storeroom-room-door-source.png": by_id[
            "storeroom-door-edit"
        ]["output_sha256"],
        "assets/art/server-room-door-source.png": by_id[
            "server-room-door-edit"
        ]["output_sha256"],
        "assets/art/game-room-door-source.png": by_id["game-room-door-edit"][
            "output_sha256"
        ],
        "assets/art/library-room-door-source.png": by_id[
            "library-door-edit"
        ]["output_sha256"],
        "assets/art/cleaning-room-door-source.png": by_id[
            "cleaning-room-door-edit"
        ]["output_sha256"],
    }

    normalization = manifest.get("public_snapshot_normalization")
    if (
        not isinstance(normalization, dict)
        or normalization.get("operation") != "lossless PNG IDAT recompression"
        or not isinstance(normalization.get("decoded_pixels"), str)
        or not normalization["decoded_pixels"].strip()
        or not isinstance(normalization.get("c2pa_policy"), str)
        or not normalization["c2pa_policy"].strip()
    ):
        raise VisualError("public-snapshot normalization policy is incomplete")
    normalization_files = normalization.get("files")
    if not isinstance(normalization_files, list) or any(
        not isinstance(entry, dict) for entry in normalization_files
    ):
        raise VisualError("public-snapshot normalizations must be a list")
    normalizations = {
        entry.get("path"): entry for entry in normalization_files
    }
    if (
        set(normalizations) != NORMALIZED_SOURCE_PNGS
        or len(normalizations) != len(normalization_files)
    ):
        raise VisualError(
            "public-snapshot normalizations do not name the exact three files"
        )

    for path, digest in output_links.items():
        if path in normalizations:
            record = normalizations[path]
            if (
                record.get("source_file_sha256") != digest
                or record.get("committed_file_sha256")
                != by_path[path].get("sha256")
                or not is_sha256(record.get("decoded_rgb_sha256"))
                or not is_sha256(record.get("source_c2pa_chunk_sha256"))
                or record.get("zlib_level") != 9
                or record.get("zlib_strategy")
                not in {"default", "filtered"}
            ):
                raise VisualError(
                    f"{path} has an incomplete normalization record"
                )
        elif by_path[path].get("sha256") != digest:
            raise VisualError(f"{path} does not match its generation output")

    semantic = manifest.get("semantic_hit_ids")
    expected_semantic = {str(key): value for key, value in SEMANTIC_IDS.items()}
    if semantic != expected_semantic:
        raise VisualError("semantic hit-ID legend is incomplete or inconsistent")

    preparation = manifest.get("preparation")
    if (
        not isinstance(preparation, dict)
        or preparation.get("pillow_version") != "9.4.0"
        or preparation.get("room_tool") != "tools/prepare_visual.py"
        or preparation.get("item_tool") != "tools/prepare_workdesk_items.py"
        or preparation.get("game_media_tool") != "tools/prepare_game_media.py"
        or preparation.get("chroma_tool")
        != "imagegen skill scripts/remove_chroma_key.py"
    ):
        raise VisualError("offline preparation record is incomplete")
    return by_path, normalizations


def validate_mansion_media(path: str, raster: bytes,
                           alpha: list[int]) -> None:
    """The 2x2 small-prop atlas mirrors the game-media layer rules."""
    visible = [0] * MANSION_VARIANTS
    partial = 0
    for index, value in enumerate(alpha):
        x = index % MANSION_W
        y = index // MANSION_W
        variant = (y // MANSION_CELL_H) * 2 + x // MANSION_CELL_W
        pixel = raster[index * 3:index * 3 + 3]
        if value == 0:
            if pixel != b"\x00\x00\x00":
                raise VisualError(
                    f"{path}: colored pixel outside the coverage mask"
                )
        else:
            visible[variant] += 1
            if value < 255:
                partial += 1
    for variant, count in enumerate(visible):
        if count < 100:
            raise VisualError(
                f"{path}: variant {variant} has under 100 visible pixels"
            )
    if partial == 0:
        raise VisualError(f"{path}: mask carries no antialiased coverage")


def validate_mansion_group(actual_paths: set[str]) -> str:
    present = actual_paths & MANSION_PATHS
    if not present:
        return "review pending (procedural props serve)"
    if present != MANSION_PATHS:
        missing = ", ".join(sorted(MANSION_PATHS - present))
        raise VisualError(
            f"optional mansion-items group is incomplete; missing {missing}"
        )
    manifest = json.loads(regular_file(MANSION_MANIFEST).decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != (
        "kilix-cap-visual-provenance-gemini-v1"
    ):
        raise VisualError("unexpected mansion-items provenance schema")
    generator = manifest.get("generator")
    if (
        not isinstance(generator, dict)
        or generator.get("requested") != "Gemini image generation"
        or generator.get("provider") != "Gemini image generation"
        or generator.get("model_identifier") != "gemini-3-pro-image"
    ):
        raise VisualError("mansion-items generator record is incomplete")
    generation = manifest.get("generation")
    if (
        not isinstance(generation, dict)
        or not isinstance(generation.get("prompt"), str)
        or len(generation["prompt"]) < 200
        or generation.get("mode") != "text-to-image"
    ):
        raise VisualError("mansion-items prompt record is incomplete")
    preparation = manifest.get("preparation")
    if (
        not isinstance(preparation, dict)
        or preparation.get("item_tool") != "tools/prepare_mansion_items.py"
        or preparation.get("chroma_tool")
        != "imagegen skill scripts/remove_chroma_key.py"
    ):
        raise VisualError("mansion-items preparation record is incomplete")
    entries = manifest.get("files")
    if not isinstance(entries, dict) or set(entries) != MANSION_PATHS:
        raise VisualError("mansion-items file inventory is wrong")
    rasters: dict[str, bytes] = {}
    for relative, entry in entries.items():
        if not isinstance(entry, dict):
            raise VisualError("mansion-items file entry must be an object")
        data = regular_file(ROOT / relative)
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            raise VisualError(
                f"{relative} SHA-256 does not match gemini provenance"
            )
        if relative == MANSION_SOURCE:
            # The generator writes JPEG bytes under the .png name; the
            # recorded format captures that honestly and structure is
            # validated on the keyed RGBA copy instead.
            if entry.get("format") != "JPEG-in-png-name":
                raise VisualError(f"{relative} has the wrong recorded format")
            dimensions = (entry.get("width"), entry.get("height"))
        elif relative.endswith(".png"):
            dimensions = png_dimensions(data)
            if entry.get("format") != "PNG":
                raise VisualError(f"{relative} has the wrong recorded format")
        else:
            width, height, raster = ppm_raster(data)
            dimensions = (width, height)
            if dimensions != (MANSION_W, MANSION_H):
                raise VisualError(
                    f"{relative} is {width}x{height}; expected "
                    f"{MANSION_W}x{MANSION_H}"
                )
            if entry.get("format") != "P6":
                raise VisualError(f"{relative} has the wrong recorded format")
            rasters[relative] = raster
        if (entry.get("width"), entry.get("height")) != dimensions:
            raise VisualError(f"{relative} recorded dimensions are wrong")
    alpha = gray_values(MANSION_ALPHA, rasters[MANSION_ALPHA])
    validate_mansion_media(MANSION_ATLAS, rasters[MANSION_ATLAS], alpha)
    return "present, validated"


def run() -> str:
    manifest = json.loads(regular_file(MANIFEST).decode("utf-8"))
    if not isinstance(manifest, dict):
        raise VisualError("visual provenance root must be an object")
    entries, normalizations = validate_manifest(manifest)

    try:
        art_entries = list(ART_DIRECTORY.iterdir())
    except OSError as exc:
        raise VisualError(f"cannot enumerate assets/art: {exc}") from exc
    actual_paths: set[str] = set()
    for path in art_entries:
        if path.is_symlink() or not path.is_file():
            raise VisualError(
                f"{path.relative_to(ROOT)} is not a regular visual asset"
            )
        actual_paths.add(path.relative_to(ROOT).as_posix())
    if actual_paths - MANSION_PATHS != EXPECTED_PATHS:
        raise VisualError(
            "assets/art does not match the exact thirty-three-file "
            "inventory plus the optional mansion-items group"
        )
    mansion_status = validate_mansion_group(actual_paths)

    rasters: dict[str, bytes] = {}
    for relative, entry in entries.items():
        path = ROOT / relative
        data = regular_file(path)
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry.get("sha256"):
            raise VisualError(f"{relative} SHA-256 does not match provenance")
        if relative.endswith(".png"):
            dimensions = png_dimensions(data)
            if entry.get("format") != "PNG":
                raise VisualError(f"{relative} has the wrong recorded format")
            if relative in normalizations:
                chunk_types = {kind for kind, _ in png_chunks(data)}
                if b"caBX" in chunk_types:
                    raise VisualError(
                        f"{relative} retains an invalidated caBX credential"
                    )
                if (
                    png_decoded_rgb_sha256(data)
                    != normalizations[relative].get("decoded_rgb_sha256")
                ):
                    raise VisualError(
                        f"{relative} decoded RGB does not match provenance"
                    )
        else:
            dimensions = ppm_raster(data)[:2]
            if relative in (GAME_MEDIA, GAME_MEDIA_ALPHA):
                if dimensions != (144, 168):
                    raise VisualError(
                        f"{relative} is {dimensions[0]}x{dimensions[1]}; "
                        "expected 144x168"
                    )
                rasters[relative] = ppm_raster(data)[2]
            else:
                rasters[relative] = require_runtime_dimensions(relative, data)
            if entry.get("format") != "P6":
                raise VisualError(f"{relative} has the wrong recorded format")
        expected = (entry.get("width"), entry.get("height"))
        if dimensions != expected:
            raise VisualError(
                f"{relative} is {dimensions[0]}x{dimensions[1]}, expected "
                f"{expected[0]}x{expected[1]}"
            )

    for path in BACKGROUND_PPMS:
        validate_color_art(path, rasters[path], background=True)
    validate_color_art(ITEM_ATLAS, rasters[ITEM_ATLAS], background=False)
    alpha = gray_values(ITEM_ALPHA, rasters[ITEM_ALPHA])
    hit = gray_values(ITEM_HIT, rasters[ITEM_HIT])
    validate_alpha(ITEM_ALPHA, alpha, 20000)
    validate_hit(ITEM_HIT, hit)
    validate_layer_relationships(rasters[ITEM_ATLAS], alpha, hit)
    validate_media_art(GAME_MEDIA, rasters[GAME_MEDIA])
    media_alpha = gray_values(GAME_MEDIA_ALPHA, rasters[GAME_MEDIA_ALPHA])
    validate_alpha(GAME_MEDIA_ALPHA, media_alpha, 3000)
    validate_layer_relationships(
        rasters[GAME_MEDIA], media_alpha, [0] * len(media_alpha)
    )
    return mansion_status


def main() -> int:
    try:
        mansion_status = run()
    except (OSError, KeyError, TypeError, json.JSONDecodeError, VisualError) as exc:
        print(f"validate_visual: {exc}", file=sys.stderr)
        return 1
    print(
        "validate_visual: eight room-native scenes, Desk/game sprites, 13 "
        "semantic hit IDs, three lossless source normalizations, hashes, and "
        "provenance OK; optional mansion-items: " + mansion_status
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
