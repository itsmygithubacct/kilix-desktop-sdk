#!/usr/bin/env python3
"""Validate the committed twelve-cue bank and its closed provenance."""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import sys
import wave
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GAINS = {
    "touch": 0.75,
    "error": 0.55,
    "keyboard": 0.18,
    "swallow": 0.16,
    "contain": 0.55,
    "copy": 0.18,
    "door": 0.20,
    "switch": 0.25,
    "dismiss": 0.55,
    "magic": 0.25,
    "ring": 0.35,
    "no_mail": 0.50,
}
EXPECTED_FILES = {f"{name}.wav" for name in EXPECTED_GAINS}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dbfs(value: float) -> float:
    return round(20.0 * math.log10(max(value, 1.0e-12)), 3)


def inspect_wav(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.getnframes()
            compression = wav.getcomptype()
            payload = wav.readframes(frames)
    except (OSError, EOFError, wave.Error) as error:
        errors.append(f"{path}: cannot read WAV: {error}")
        return None

    if (channels, width, rate, compression) != (1, 2, 44_100, "NONE"):
        errors.append(
            f"{path}: expected mono/16-bit/44100 Hz PCM, got "
            f"{channels}ch/{width * 8}bit/{rate} Hz/{compression}"
        )
        return None
    if frames == 0 or frames > 44_100:
        errors.append(f"{path}: frame count {frames} is outside 1..44100")

    values = array.array("h")
    values.frombytes(payload)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != frames:
        errors.append(f"{path}: payload has {len(values)} samples for {frames} frames")
        return None
    if not values or not any(values):
        errors.append(f"{path}: cue is silent")
        return None
    if any(value in (-32768, 32767) for value in values):
        errors.append(f"{path}: cue contains clipped PCM samples")

    peak = max(abs(value) for value in values) / 32768.0
    rms = math.sqrt(sum(value * value for value in values) / len(values)) / 32768.0
    dc = sum(values) / len(values) / 32768.0
    if abs(dc) > 0.05:
        errors.append(f"{path}: excessive DC offset {dc:.6f}")
    return {
        "frame_count": frames,
        "duration_seconds": round(frames / 44_100.0, 6),
        "peak_dbfs": dbfs(peak),
        "rms_dbfs": dbfs(rms),
        "dc_offset": round(dc, 8),
        "sha256": sha256(path),
    }


def close_enough(left: Any, right: Any, tolerance: float = 0.001) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def validate_generator_hashes(manifest: dict[str, Any], generators: Path,
                              errors: list[str]) -> None:
    for generator, snapshot in manifest.get("generator_snapshots", {}).items():
        for record in snapshot.get("files", []):
            path = generators / record.get("file", "")
            if not path.is_file():
                errors.append(f"missing generator input {path}")
            elif sha256(path) != record.get("sha256"):
                errors.append(f"generator input changed: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path,
                        default=PROJECT_ROOT / "assets" / "sfx")
    parser.add_argument("--provenance", type=Path,
                        default=PROJECT_ROOT / "docs" / "audio-provenance.json")
    parser.add_argument("--check-generators", action="store_true",
                        help="also compare the development generator snapshot")
    parser.add_argument("--generators", type=Path,
                        default=PROJECT_ROOT.parent / "python_sound_assets")
    args = parser.parse_args()
    errors: list[str] = []

    if not args.assets.is_dir():
        errors.append(f"missing audio directory {args.assets}")
        wav_names: set[str] = set()
    else:
        wav_names = {path.name for path in args.assets.glob("*.wav")}
        for path in args.assets.iterdir():
            if path.is_symlink():
                errors.append(f"runtime audio symlink is forbidden: {path}")
    missing = sorted(EXPECTED_FILES - wav_names)
    extra = sorted(wav_names - EXPECTED_FILES)
    if missing:
        errors.append(f"missing WAV files: {', '.join(missing)}")
    if extra:
        errors.append(f"unexpected WAV files: {', '.join(extra)}")

    try:
        manifest = json.loads(args.provenance.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"cannot read {args.provenance}: {error}")
        manifest = {}

    if manifest.get("schema") != "kilix-cap-audio-provenance-v1":
        errors.append("audio provenance has an unknown schema")
    if manifest.get("asset_count") != 12:
        errors.append("audio provenance asset_count must be 12")
    if manifest.get("originality", {}).get("commercial_product_bytes_used") is not False:
        errors.append("audio provenance does not close the commercial-input boundary")

    tool = manifest.get("recipe_tool", {})
    recipe_path = PROJECT_ROOT / tool.get("file", "")
    if not recipe_path.is_file() or sha256(recipe_path) != tool.get("sha256"):
        errors.append("regeneration recipe hash does not match provenance")

    artifacts = manifest.get("artifacts", [])
    by_cue: dict[str, dict[str, Any]] = {}
    if not isinstance(artifacts, list):
        errors.append("audio provenance artifacts must be a list")
        artifacts = []
    for artifact in artifacts:
        cue = artifact.get("cue") if isinstance(artifact, dict) else None
        if not isinstance(cue, str) or cue in by_cue:
            errors.append(f"invalid or duplicate cue in provenance: {cue!r}")
            continue
        by_cue[cue] = artifact
    if set(by_cue) != set(EXPECTED_GAINS):
        errors.append("provenance cue set does not equal the twelve-cue contract")

    for cue, gain in EXPECTED_GAINS.items():
        artifact = by_cue.get(cue)
        path = args.assets / f"{cue}.wav"
        if artifact is None or not path.is_file():
            continue
        if artifact.get("file") != f"assets/sfx/{cue}.wav":
            errors.append(f"{cue}: noncanonical manifest path")
        if not close_enough(artifact.get("runtime_gain"), gain, 0.000001):
            errors.append(f"{cue}: runtime gain does not match sound.c contract")
        if not artifact.get("trigger"):
            errors.append(f"{cue}: missing trigger provenance")
        if not isinstance(artifact.get("command"), list) or not artifact.get("command"):
            errors.append(f"{cue}: missing exact generator command")
        if not isinstance(artifact.get("base_seed"), int) or not isinstance(
                artifact.get("effective_seed"), int):
            errors.append(f"{cue}: missing deterministic seed")

        measured = inspect_wav(path, errors)
        if measured is None:
            continue
        for field in ("frame_count", "sha256"):
            if artifact.get(field) != measured[field]:
                errors.append(f"{cue}: manifest {field} does not match WAV")
        for field in ("duration_seconds", "peak_dbfs", "rms_dbfs", "dc_offset"):
            if not close_enough(artifact.get(field), measured[field]):
                errors.append(f"{cue}: manifest {field} does not match WAV")

        source_audio = str(artifact.get("source_audio", ""))
        sources = artifact.get("sources", [])
        if source_audio.startswith("none;") and sources:
            errors.append(f"{cue}: procedural cue unexpectedly lists recordings")
        for source in sources:
            if source.get("license") not in ("CC0 1.0", "Public domain"):
                errors.append(f"{cue}: source license is not CC0/public domain")
            if not source.get("sha256") or not source.get("source_page"):
                errors.append(f"{cue}: recorded source provenance is incomplete")

    if args.check_generators:
        if not args.generators.is_dir():
            errors.append(f"generator directory does not exist: {args.generators}")
        else:
            validate_generator_hashes(manifest, args.generators, errors)

    for error in errors:
        print(f"validate_audio: {error}", file=sys.stderr)
    if errors:
        return 1
    print("validate_audio: 12 cues, PCM format, hashes, levels, and provenance OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
