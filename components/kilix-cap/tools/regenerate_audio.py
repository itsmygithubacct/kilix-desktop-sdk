#!/usr/bin/env python3
"""Rebuild kilix-cap's twelve-cue WAV bank from local generators.

The generator checkout is deliberately a development-only sibling of this
repository.  Runtime builds consume the committed WAVs and never import NumPy,
SciPy, or generator code.  Every cue is rendered in a private staging
directory so the generators' own `manifest.json` files cannot overwrite one
another; this script then measures the PCM actually shipped and writes the
single canonical provenance document.
"""

from __future__ import annotations

import argparse
import array
import fnmatch
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GENERATORS = PROJECT_ROOT.parent / "python_sound_assets"
DEFAULT_OUTPUT = PROJECT_ROOT / "assets" / "sfx"
DEFAULT_PROVENANCE = PROJECT_ROOT / "docs" / "audio-provenance.json"

FORMAT = {
    "container": "RIFF/WAVE",
    "encoding": "signed 16-bit little-endian PCM",
    "channels": 1,
    "sample_rate_hz": 44_100,
}


RECIPES: tuple[dict[str, Any], ...] = (
    {
        "name": "touch", "generator": "ui_game_state_generator",
        "generator_cue": "menu_move", "seed": 2026072101,
        "options": {"style": "acoustic", "step": 0, "count": 1},
        "arguments": ["render", "menu_move", "--style", "acoustic",
                      "--seed", "2026072101", "--out", "{stage}"],
        "produced": "menu_move.wav", "gain": 0.75,
        "trigger": "accepted pointer-down on a touchable object",
        "source_audio": "none; deterministic procedural synthesis",
    },
    {
        "name": "error", "generator": "ui_game_state_generator",
        "generator_cue": "menu_invalid", "seed": 2026072102,
        "options": {"style": "acoustic", "step": 0, "count": 1},
        "arguments": ["render", "menu_invalid", "--style", "acoustic",
                      "--seed", "2026072102", "--out", "{stage}"],
        "produced": "menu_invalid.wav", "gain": 0.55,
        "trigger": "first drag-threshold crossing on a non-movable object",
        "source_audio": "none; deterministic procedural synthesis",
    },
    {
        "name": "keyboard", "generator": "computer_sounds_generator",
        "generator_cue": "key", "seed": 2026072103,
        "options": {"size": "laptop", "region": "ntsc", "intensity": 0.35,
                    "count": 1, "stem": "keyboard"},
        "arguments": ["render", "key", "--size", "laptop", "--region",
                      "ntsc", "--intensity", "0.35", "--count", "1",
                      "--seed", "2026072103", "--stem", "keyboard",
                      "--out", "{stage}"],
        "produced": "keyboard.wav", "gain": 0.18,
        "trigger": "keyboard pointer-down or physical key acceptance",
        "source_audio": "CC0 1.0 recording",
    },
    {
        "name": "swallow", "generator": "magic_sound_generator",
        "generator_cue": "teleport", "seed": 2026072104,
        "options": {"style": "nature", "intensity": 0.25, "count": 1,
                    "stem": "swallow"},
        "arguments": ["render", "teleport", "--style", "nature",
                      "--intensity", "0.25", "--seed", "2026072104",
                      "--stem", "swallow", "--out", "{stage}"],
        "produced": "swallow.wav", "gain": 0.16,
        "trigger": "successful drop into an action container",
        "source_audio": "none; deterministic procedural synthesis",
    },
    {
        "name": "contain", "generator": "ui_game_state_generator",
        "generator_cue": "menu_accept", "seed": 2026072105,
        "options": {"style": "acoustic", "step": 0, "count": 1},
        "arguments": ["render", "menu_accept", "--style", "acoustic",
                      "--seed", "2026072105", "--out", "{stage}"],
        "produced": "menu_accept.wav", "gain": 0.55,
        "trigger": "successful move into a different ordinary container",
        "source_audio": "none; deterministic procedural synthesis",
    },
    {
        "name": "copy", "generator": "magic_sound_generator",
        "generator_cue": "cast", "seed": 2026072106,
        "options": {"style": "nature", "intensity": 0.30, "count": 1,
                    "stem": "copy"},
        "arguments": ["render", "cast", "--style", "nature",
                      "--intensity", "0.30", "--seed", "2026072106",
                      "--stem", "copy", "--out", "{stage}"],
        "produced": "copy.wav", "gain": 0.18,
        "trigger": "successful clone or Stamper/Magic-hat creation",
        "source_audio": "none; deterministic procedural synthesis",
    },
    {
        "name": "door", "generator": "door_sound_generator",
        "generator_cue": "open", "seed": 2026072107,
        "options": {"action": "open", "material": "light_wood",
                    "intensity": 0.30, "age": 0.10, "duration": 0.36,
                    "room": 0.02, "stereo": False},
        "arguments": ["{output}", "--action", "open", "--material",
                      "light_wood", "--intensity", "0.30", "--age", "0.10",
                      "--duration", "0.36", "--room", "0.02", "--seed",
                      "2026072107"],
        "produced": "door.wav", "gain": 0.20,
        "trigger": "accepted room-door transition",
        "source_audio": "CC0 1.0/public-domain recordings",
    },
    {
        "name": "switch", "generator": "computer_sounds_generator",
        "generator_cue": "switch", "seed": 2026072108,
        "options": {"size": "laptop", "region": "ntsc", "intensity": 0.35,
                    "count": 1, "stem": "switch"},
        "arguments": ["render", "switch", "--size", "laptop", "--region",
                      "ntsc", "--intensity", "0.35", "--count", "1",
                      "--seed", "2026072108", "--stem", "switch",
                      "--out", "{stage}"],
        "produced": "switch.wav", "gain": 0.25,
        "trigger": "successful switch-state change",
        "source_audio": "CC0 1.0 recording",
    },
    {
        "name": "dismiss", "generator": "ui_game_state_generator",
        "generator_cue": "menu_cancel", "seed": 2026072109,
        "options": {"style": "acoustic", "step": 0, "count": 1},
        "arguments": ["render", "menu_cancel", "--style", "acoustic",
                      "--seed", "2026072109", "--out", "{stage}"],
        "produced": "menu_cancel.wav", "gain": 0.55,
        "trigger": "accepted panel/window close",
        "source_audio": "none; deterministic procedural synthesis",
    },
    {
        "name": "magic", "generator": "magic_sound_generator",
        "generator_cue": "sparkle", "seed": 2026072110,
        "options": {"style": "holy", "intensity": 0.25, "count": 1,
                    "stem": "magic"},
        "arguments": ["render", "sparkle", "--style", "holy",
                      "--intensity", "0.25", "--seed", "2026072110",
                      "--stem", "magic", "--out", "{stage}"],
        "produced": "magic.wav", "gain": 0.25,
        "trigger": "message-arrival state commit",
        "source_audio": "none; deterministic procedural synthesis",
    },
    {
        "name": "ring", "generator": "ui_game_state_generator",
        "generator_cue": "warning", "seed": 2026072111,
        "options": {"style": "acoustic", "step": 0, "count": 1},
        "arguments": ["render", "warning", "--style", "acoustic",
                      "--seed", "2026072111", "--out", "{stage}"],
        "produced": "warning.wav", "gain": 0.35,
        "trigger": "telephone enters ringing state",
        "source_audio": "none; deterministic procedural synthesis",
        "design_note": "Four-pulse alert abstraction; the local banks contain no telephone-ringer cue.",
    },
    {
        "name": "no_mail", "generator": "powerup_generator",
        "generator_cue": "no_ammo", "seed": 2026072112,
        "options": {"style": "acoustic", "count": 1},
        "arguments": ["render", "no_ammo", "--style", "acoustic",
                      "--seed", "2026072112", "--out", "{stage}"],
        "produced": "no_ammo.wav", "gain": 0.50,
        "trigger": "mailbox check resolves with zero waiting messages",
        "source_audio": "none; deterministic procedural synthesis",
    },
)


GENERATOR_FILES: dict[str, tuple[str, ...]] = {
    "ui_game_state_generator": (
        "ui_game_state_generator/__init__.py",
        "ui_game_state_generator/__main__.py",
        "ui_game_state_generator/cli.py",
        "ui_game_state_generator/cues.py",
        "powerup_generator/engine.py",
        "powerup_generator/gestures.py",
        "powerup_generator/styles.py",
    ),
    "powerup_generator": (
        "powerup_generator/__init__.py",
        "powerup_generator/__main__.py",
        "powerup_generator/cli.py",
        "powerup_generator/cues.py",
        "powerup_generator/engine.py",
        "powerup_generator/gestures.py",
        "powerup_generator/styles.py",
    ),
    "computer_sounds_generator": (
        "computer_sounds_generator/__init__.py",
        "computer_sounds_generator/__main__.py",
        "computer_sounds_generator/cli.py",
        "computer_sounds_generator/cues.py",
        "computer_sounds_generator/engine.py",
        "combat_generators/lib/dsp.py",
        "environment_ambience_generator/loopdsp.py",
        "aircraft_spacecraft_generator/engine.py",
    ),
    "door_sound_generator": (
        "door_sound_generator/__init__.py",
        "door_sound_generator/__main__.py",
        "door_sound_generator/cli.py",
        "door_sound_generator/cues.py",
        "door_sound_generator/engine.py",
    ),
    "magic_sound_generator": (
        "magic_sound_generator/__init__.py",
        "magic_sound_generator/__main__.py",
        "magic_sound_generator/cli.py",
        "magic_sound_generator/cues.py",
        "magic_sound_generator/engine.py",
        "combat_generators/lib/dsp.py",
        "environment_ambience_generator/loopdsp.py",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dbfs(value: float) -> float:
    return round(20.0 * math.log10(max(value, 1.0e-12)), 3)


def measure_wav(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        frames = wav.getnframes()
        compression = wav.getcomptype()
        payload = wav.readframes(frames)
    if (channels != 1 or width != 2 or rate != 44_100 or compression != "NONE"):
        raise RuntimeError(f"{path} is not mono 44100 Hz signed 16-bit PCM")
    values = array.array("h")
    values.frombytes(payload)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != frames or frames == 0:
        raise RuntimeError(f"{path} has an invalid PCM payload")
    peak_i = max(abs(value) for value in values)
    if peak_i == 0:
        raise RuntimeError(f"{path} is silent")
    if any(value in (-32768, 32767) for value in values):
        raise RuntimeError(f"{path} contains clipped PCM samples")
    rms = math.sqrt(sum(value * value for value in values) / frames) / 32768.0
    dc = sum(values) / frames / 32768.0
    return {
        "frame_count": frames,
        "duration_seconds": round(frames / 44_100.0, 6),
        "peak_dbfs": dbfs(peak_i / 32768.0),
        "rms_dbfs": dbfs(rms),
        "dc_offset": round(dc, 8),
        "sha256": sha256(path),
    }


def run_recipe(recipe: dict[str, Any], generators: Path,
               staging: Path) -> tuple[Path, dict[str, Any], str]:
    cue_stage = staging / recipe["name"]
    cue_stage.mkdir(parents=True)
    arguments = [part.format(stage=str(cue_stage),
                             output=str(cue_stage / recipe["produced"]))
                 for part in recipe["arguments"]]
    command = [sys.executable, "-m", recipe["generator"], *arguments]
    env = os.environ.copy()
    old_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(generators) + (
        os.pathsep + old_pythonpath if old_pythonpath else "")
    completed = subprocess.run(
        command, cwd=generators, env=env, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = cue_stage / recipe["produced"]
    if not output.is_file():
        raise RuntimeError(f"generator did not create {output}")

    metadata: dict[str, Any] = {"effective_seed": recipe["seed"], "sources": []}
    own_manifest = cue_stage / "manifest.json"
    if own_manifest.is_file():
        generated = json.loads(own_manifest.read_text(encoding="utf-8"))
        artifacts = generated.get("artifacts", [])
        if len(artifacts) != 1:
            raise RuntimeError(f"unexpected generator manifest for {recipe['name']}")
        metadata["effective_seed"] = artifacts[0].get("seed", recipe["seed"])
        metadata["sources"] = artifacts[0].get("sources", [])
    if recipe["generator"] == "door_sound_generator":
        for line in completed.stdout.splitlines():
            if line.startswith("Sources: "):
                metadata["sources"] = [
                    item.strip() for item in line[9:].split(",") if item.strip()
                ]
    return output, metadata, completed.stdout


def source_collection(generator: str, source: str,
                      provenance: dict[str, Any]) -> dict[str, Any]:
    for collection in provenance.get("collections", []):
        if generator == "computer_sounds_generator":
            for item in collection.get("files", []):
                if item.get("file") == source:
                    return {**collection, "files": [item]}
        pattern = collection.get("bundled_files")
        if pattern and fnmatch.fnmatch(source, pattern):
            return collection
    raise RuntimeError(f"no source provenance for {generator}/{source}")


def recorded_sources(generator: str, names: list[str],
                     generators: Path) -> list[dict[str, Any]]:
    if not names:
        return []
    provenance_path = generators / generator / "sources" / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    records = []
    for name in names:
        source_path = generators / generator / "sources" / name
        if not source_path.is_file():
            raise RuntimeError(f"missing recorded source {source_path}")
        collection = source_collection(generator, name, provenance)
        upstream_file = collection.get("original_file") or collection.get("original_archive")
        upstream_sha256 = collection.get("original_sha256")
        derived_from = None
        if collection.get("upstream_provenance") and collection.get("files"):
            item = collection["files"][0]
            derived_from = item.get("original_bundled_file")
            upstream_ref = str(collection["upstream_provenance"])
            upstream_path = (provenance_path.parent / upstream_ref).resolve()
            if not upstream_path.is_file():
                # The computer bank's pointer is written relative to the
                # common generator root rather than its `sources/` directory.
                upstream_path = generators / upstream_ref.removeprefix("../")
            upstream_provenance = json.loads(
                upstream_path.read_text(encoding="utf-8"))
            upstream_collection = source_collection(
                "door_sound_generator", derived_from, upstream_provenance)
            upstream_file = (upstream_collection.get("original_file") or
                             upstream_collection.get("original_archive"))
            upstream_sha256 = upstream_collection.get("original_sha256")
        records.append({
            "file": name,
            "sha256": sha256(source_path),
            "collection": collection.get("name"),
            "author": collection.get("author"),
            "license": collection.get("license"),
            "source_page": collection.get("source_page"),
            "derived_from_bundled_file": derived_from,
            "upstream_file": upstream_file,
            "upstream_sha256": upstream_sha256,
        })
    return records


def generator_fingerprints(generators: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    used = sorted({recipe["generator"] for recipe in RECIPES})
    for generator in used:
        files = []
        for relative in GENERATOR_FILES[generator]:
            path = generators / relative
            if not path.is_file():
                raise RuntimeError(f"missing generator implementation {path}")
            files.append({"file": relative, "sha256": sha256(path)})
        provenance = generators / generator / "sources" / "provenance.json"
        if provenance.is_file():
            files.append({
                "file": provenance.relative_to(generators).as_posix(),
                "sha256": sha256(provenance),
            })
        result[generator] = {
            "revision": "unversioned local snapshot; identified by file hashes",
            "files": files,
        }
    return result


def runtime_versions() -> dict[str, str]:
    import numpy  # Generation-time dependencies; never imported by the game.
    import scipy
    return {
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
    }


def atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_name(destination.name + ".tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def atomic_json(payload: dict[str, Any], destination: Path) -> None:
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n",
                         encoding="utf-8")
    os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generators", type=Path, default=DEFAULT_GENERATORS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    args = parser.parse_args()
    generators = args.generators.resolve()
    output = args.out.resolve()
    provenance_path = args.provenance.resolve()
    if not generators.is_dir():
        parser.error(f"generator directory does not exist: {generators}")

    output.mkdir(parents=True, exist_ok=True)
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    pending_copies: list[tuple[Path, Path]] = []

    with tempfile.TemporaryDirectory(prefix="kilix-cap-audio-") as temporary:
        staging = Path(temporary)
        for recipe in RECIPES:
            rendered, generator_meta, log = run_recipe(recipe, generators, staging)
            destination = output / f"{recipe['name']}.wav"
            pending_copies.append((rendered, destination))
            sources = recorded_sources(recipe["generator"],
                                       list(generator_meta["sources"]), generators)
            artifact = {
                "cue": recipe["name"],
                "file": destination.relative_to(PROJECT_ROOT).as_posix()
                        if destination.is_relative_to(PROJECT_ROOT)
                        else destination.name,
                "generator": recipe["generator"],
                "generator_cue": recipe["generator_cue"],
                "command": ["python3", "-m", recipe["generator"], *[
                    part.format(stage=f"<staging>/{recipe['name']}",
                                output=f"<staging>/{recipe['name']}/{recipe['produced']}")
                    for part in recipe["arguments"]
                ]],
                "options": recipe["options"],
                "base_seed": recipe["seed"],
                "effective_seed": generator_meta["effective_seed"],
                "format": FORMAT,
                **measure_wav(rendered),
                "runtime_gain": recipe["gain"],
                "trigger": recipe["trigger"],
                "source_audio": recipe["source_audio"],
                "sources": sources,
            }
            if "design_note" in recipe:
                artifact["design_note"] = recipe["design_note"]
            artifacts.append(artifact)
            final_line = log.strip().splitlines()[-1] if log.strip() else "rendered"
            print(f"{recipe['name']:<8} {artifact['sha256']}  {final_line}")

        expected = {f"{recipe['name']}.wav" for recipe in RECIPES}
        extras = sorted(path.name for path in output.glob("*.wav")
                        if path.name not in expected)
        if extras:
            raise RuntimeError(f"unexpected WAV files already in {output}: {extras}")
        # No runtime file is touched until every generator and provenance
        # lookup has succeeded.
        for rendered, destination in pending_copies:
            atomic_copy(rendered, destination)

    payload = {
        "schema": "kilix-cap-audio-provenance-v1",
        "authored_date": "2026-07-21",
        "format": FORMAT,
        "asset_count": len(artifacts),
        "recipe_tool": {
            "file": "tools/regenerate_audio.py",
            "sha256": sha256(Path(__file__).resolve()),
        },
        "generation_runtime": runtime_versions(),
        "generator_snapshots": generator_fingerprints(generators),
        "licensing": {
            "output_license": "MIT; see repository LICENSE",
            "procedural_outputs": "Project-authored deterministic synthesis; no sampled audio.",
            "recorded_outputs": "Transformations of the CC0 1.0/public-domain sources listed per artifact.",
            "generator_code": "Development input only; generator code is not distributed with kilix-cap.",
            "generator_license_status": "The local generator tree has no project-level license file; only rendered outputs are included here.",
        },
        "originality": {
            "commercial_product_bytes_used": False,
            "extracted_or_transcribed_audio_used": False,
            "statement": "No audio, recording, executable, ROM, or artwork from the historical product was used as a generation input.",
        },
        "audition": {
            "status": "release-approved",
            "reviewed_date": "2026-07-21",
            "review_basis": "Cue semantics, generator mastering levels, runtime gains, strict PCM format, deterministic hashes, and complete in-application offline mixing were reviewed for the 1.0 bank.",
            "note": "Future subjective retuning is optional polish, not a release blocker; it must preserve this provenance and validation contract.",
        },
        "artifacts": artifacts,
    }
    atomic_json(payload, provenance_path)
    print(f"wrote {len(artifacts)} cues and {provenance_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"regenerate_audio: {error}", file=sys.stderr)
        raise SystemExit(1)
