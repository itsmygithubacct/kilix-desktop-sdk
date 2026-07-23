#!/usr/bin/env python3
"""Validate deterministic P6 render-test output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


WIDTH = 480
HEIGHT = 320
CHANNELS = 3
RASTER_BYTES = WIDTH * HEIGHT * CHANNELS
DEFAULT_EXPECTED = (
    "base-desk.ppm",
    "base-hallway.ppm",
    "base-storeroom.ppm",
    "base-server-room.ppm",
    "base-game-room.ppm",
    "base-library.ppm",
    "base-cleaning-room.ppm",
    "base-balcony.ppm",
    "state-desk-hover.ppm",
    "state-desk-web-boot.ppm",
    "state-desk-web-zoom.ppm",
    "state-server-hover.ppm",
    "state-cleaning-hover.ppm",
    "state-game-hover.ppm",
    "state-store-moved.ppm",
)
WHITESPACE = frozenset(b" \t\r\n\v\f")
ROOT = Path(__file__).resolve().parents[1]
GOLDEN_MANIFEST = ROOT / "docs" / "render-fixtures.json"


class ValidationError(Exception):
    """A concise, user-facing validation failure."""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that a render directory contains the exact expected P6 "
            "files and deterministic 480x320 full-color RGB pixels."
        )
    )
    parser.add_argument("directory", type=Path, help="render directory to validate")
    parser.add_argument(
        "--expected",
        nargs="+",
        metavar="FILE",
        help=(
            "exact PPM basenames expected in the directory; defaults to the "
            "the fifteen built-in release fixtures"
        ),
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        metavar="N",
        help=(
            "expected number of PPM files; when used without --expected, "
            "accept any PPM basenames"
        ),
    )
    return parser.parse_args(argv)


def _header_token(data: bytes, position: int, label: str) -> tuple[bytes, int]:
    length = len(data)

    while position < length:
        byte = data[position]
        if byte in WHITESPACE:
            position += 1
            continue
        if byte == ord("#"):
            newline = data.find(b"\n", position + 1)
            if newline < 0:
                raise ValidationError(f"unterminated comment before {label}")
            position = newline + 1
            continue
        break

    start = position
    while position < length:
        byte = data[position]
        if byte in WHITESPACE or byte == ord("#"):
            break
        position += 1

    if position == start:
        raise ValidationError(f"missing {label} in P6 header")
    return data[start:position], position


def _decimal(token: bytes, label: str) -> int:
    try:
        text = token.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"non-ASCII {label} in P6 header") from exc
    if not text.isdecimal():
        raise ValidationError(f"invalid {label} {text!r} in P6 header")
    return int(text, 10)


def _raster_offset(data: bytes) -> int:
    position = 0
    magic, position = _header_token(data, position, "magic")
    width_token, position = _header_token(data, position, "width")
    height_token, position = _header_token(data, position, "height")
    maxval_token, position = _header_token(data, position, "maxval")

    if magic != b"P6":
        try:
            shown_magic = magic.decode("ascii")
        except UnicodeDecodeError:
            shown_magic = repr(magic)
        raise ValidationError(f"expected P6 magic, found {shown_magic!r}")

    width = _decimal(width_token, "width")
    height = _decimal(height_token, "height")
    maxval = _decimal(maxval_token, "maxval")
    if (width, height) != (WIDTH, HEIGHT):
        raise ValidationError(
            f"expected dimensions {WIDTH}x{HEIGHT}, found {width}x{height}"
        )
    if maxval != 255:
        raise ValidationError(f"expected maxval 255, found {maxval}")

    if position >= len(data) or data[position] not in WHITESPACE:
        raise ValidationError("missing whitespace separator after P6 maxval")

    # Treat the conventional CRLF line ending as one separator. Do not skip
    # arbitrary whitespace here: every following byte belongs to the raster.
    if data[position] == ord("\r") and data[position : position + 2] == b"\r\n":
        return position + 2
    return position + 1


def validate_ppm(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read file: {exc}") from exc

    offset = _raster_offset(data)
    raster = memoryview(data)[offset:]
    if len(raster) != RASTER_BYTES:
        qualifier = "truncated" if len(raster) < RASTER_BYTES else "has trailing data"
        raise ValidationError(
            f"{qualifier}: expected {RASTER_BYTES} raster bytes, found {len(raster)}"
        )

    colors: set[tuple[int, int, int]] = set()
    chromatic = 0
    for pixel in range(WIDTH * HEIGHT):
        base = pixel * CHANNELS
        red = raster[base]
        green = raster[base + 1]
        blue = raster[base + 2]
        colors.add((red, green, blue))
        if max(red, green, blue) - min(red, green, blue) >= 12:
            chromatic += 1

    if len(colors) < 16:
        raise ValidationError(
            f"flat image: only {len(colors)} distinct RGB colors"
        )
    if chromatic < 5000:
        raise ValidationError(
            f"grayscale regression: only {chromatic} chromatic pixels"
        )
    return hashlib.sha256(data).hexdigest()


def _load_golden_hashes() -> dict[str, str]:
    try:
        manifest = json.loads(GOLDEN_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read golden manifest: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "kilix-cap-render-fixtures-v1"
        or manifest.get("release") != "3.0.0"
        or manifest.get("width") != WIDTH
        or manifest.get("height") != HEIGHT
    ):
        raise ValidationError("golden manifest has an invalid release contract")
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(DEFAULT_EXPECTED):
        raise ValidationError("golden manifest does not name the release fixtures")
    for name, digest in hashes.items():
        if not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64:
            raise ValidationError("golden manifest contains an invalid SHA-256")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValidationError(
                f"golden manifest contains an invalid SHA-256 for {name}"
            ) from exc
    return hashes


def _validate_expected_names(names: list[str]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for name in names:
        if (
            not name
            or name in (".", "..")
            or Path(name).name != name
            or os.sep in name
            or (os.altsep is not None and os.altsep in name)
        ):
            errors.append(f"expected name must be a plain basename: {name!r}")
        elif Path(name).suffix.lower() != ".ppm":
            errors.append(f"expected name must end in .ppm: {name!r}")
        elif name in seen:
            errors.append(f"duplicate expected name: {name!r}")
        seen.add(name)
    if errors:
        raise ValidationError("; ".join(errors))
    return names


def run(args: argparse.Namespace) -> int:
    directory: Path = args.directory
    golden_hashes = _load_golden_hashes()
    if args.expected_count is not None and args.expected_count < 0:
        raise ValidationError("--expected-count must be non-negative")
    if not directory.is_dir():
        raise ValidationError(f"not a directory: {directory}")

    explicit_names = args.expected is not None
    if explicit_names:
        expected_names = _validate_expected_names(list(args.expected))
    elif args.expected_count is None:
        expected_names = list(DEFAULT_EXPECTED)
    else:
        expected_names = []

    if (
        args.expected_count is not None
        and explicit_names
        and args.expected_count != len(expected_names)
    ):
        raise ValidationError(
            f"--expected-count is {args.expected_count}, but --expected lists "
            f"{len(expected_names)} files"
        )

    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        raise ValidationError(f"cannot list {directory}: {exc}") from exc

    ppm_entries = {
        entry.name: entry for entry in entries if entry.suffix.lower() == ".ppm"
    }
    errors: list[str] = []

    if expected_names:
        expected_set = set(expected_names)
        actual_set = set(ppm_entries)
        missing = sorted(expected_set - actual_set)
        unexpected = sorted(actual_set - expected_set)
        if missing:
            errors.append("missing PPM files: " + ", ".join(missing))
        if unexpected:
            errors.append("unexpected PPM files: " + ", ".join(unexpected))
        names_to_validate = sorted(expected_set & actual_set)
    else:
        expected_count = args.expected_count
        assert expected_count is not None
        if len(ppm_entries) != expected_count:
            errors.append(
                f"expected {expected_count} PPM files, found {len(ppm_entries)}"
            )
        names_to_validate = sorted(ppm_entries)

    golden_checked = 0
    for name in names_to_validate:
        path = ppm_entries[name]
        if path.is_symlink() or not path.is_file():
            errors.append(f"{name}: expected a regular, non-symlink file")
            continue
        try:
            digest = validate_ppm(path)
            expected_digest = golden_hashes.get(name)
            if expected_digest is not None:
                golden_checked += 1
                if digest != expected_digest:
                    raise ValidationError(
                        f"SHA-256 mismatch: expected {expected_digest}, found {digest}"
                    )
        except ValidationError as exc:
            errors.append(f"{name}: {exc}")

    if errors:
        for error in errors:
            print(f"check_render: {error}", file=sys.stderr)
        return 1

    print(
        f"check_render: ok ({len(ppm_entries)} P6 files, "
        f"{WIDTH}x{HEIGHT}, opaque full-color RGB, "
        f"{golden_checked} golden SHA-256 checks)"
    )
    return 0


def main() -> int:
    try:
        return run(parse_args(sys.argv[1:]))
    except ValidationError as exc:
        print(f"check_render: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
