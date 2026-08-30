#!/usr/bin/env python3
"""Cut short desktop chimes out of a long generated instrumental suite.

The generated source suites are minutes long; the desktop needs a few seconds.
A fixed-length cut lands mid-phrase and sounds truncated, so this tool looks for
a window whose edges are already musical: it starts on an onset that follows a
quiet moment and ends on a later onset, which is the instant the next phrase
begins and therefore the instant the previous one has finished resolving.

Deliberately stdlib plus ffmpeg, matching the rest of this project's audio
tooling: no third-party runtime, and the same source always yields the same cut.
"""
from __future__ import annotations

import argparse
import array
import math
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 44100
HOP = 512                  # ~11.6 ms novelty resolution
WINDOW = 2048
PEAK_TARGET = 0.708        # matches the existing cue bank (about -3 dBFS)
FADE_OUT = 0.180           # gentle release so a cut never clicks
FADE_IN = 0.012            # only enough to seat the first sample at zero


def decode(source: Path, sample_rate: int = SAMPLE_RATE) -> array.array:
    """Decode any ffmpeg-readable input to mono float samples."""
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-nostdin", "-i", str(source),
            "-map", "0:a:0", "-ac", "1", "-ar", str(sample_rate),
            "-f", "f32le", "-c:a", "pcm_f32le", "pipe:1",
        ],
        check=True,
        capture_output=True,
    )
    samples = array.array("f")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def frame_energy(samples: array.array) -> list[float]:
    """Root-mean-square energy per hop, in dB."""
    frames: list[float] = []
    for start in range(0, max(0, len(samples) - WINDOW), HOP):
        total = 0.0
        for index in range(start, start + WINDOW, 4):   # decimated: onsets are
            value = samples[index]                      # coarse features
            total += value * value
        mean = total / (WINDOW / 4)
        frames.append(10.0 * math.log10(mean + 1e-12))
    return frames


def novelty(energy: list[float]) -> list[float]:
    """Positive energy rise per frame — the onset strength curve."""
    curve = [0.0]
    for index in range(1, len(energy)):
        curve.append(max(0.0, energy[index] - energy[index - 1]))
    return curve


def find_onsets(curve: list[float], min_gap_frames: int) -> list[int]:
    """Local maxima above the mean, thinned so one attack yields one onset."""
    if not curve:
        return []
    average = sum(curve) / len(curve)
    spread = (sum((v - average) ** 2 for v in curve) / len(curve)) ** 0.5
    threshold = average + spread * 0.6
    peaks: list[int] = []
    for index in range(1, len(curve) - 1):
        if curve[index] < threshold:
            continue
        if curve[index] < curve[index - 1] or curve[index] < curve[index + 1]:
            continue
        if peaks and index - peaks[-1] < min_gap_frames:
            if curve[index] > curve[peaks[-1]]:
                peaks[-1] = index
            continue
        peaks.append(index)
    return peaks


@dataclass
class Candidate:
    start_frame: int
    end_frame: int
    score: float

    def start_seconds(self) -> float:
        return self.start_frame * HOP / SAMPLE_RATE

    def end_seconds(self) -> float:
        return self.end_frame * HOP / SAMPLE_RATE

    def seconds(self) -> float:
        return self.end_seconds() - self.start_seconds()


def rank_windows(
    energy: list[float],
    curve: list[float],
    onsets: list[int],
    minimum: float,
    maximum: float,
    region: tuple[float, float],
) -> list[Candidate]:
    """Score every onset-to-onset window that fits the duration bounds.

    A good chime opens with a clear attack out of relative quiet, keeps its
    energy up through the body, and stops where the music has just resolved.
    """
    per_second = SAMPLE_RATE / HOP
    low_frame = int(region[0] * per_second)
    high_frame = int(region[1] * per_second) if region[1] > 0 else len(energy)
    min_frames = int(minimum * per_second)
    max_frames = int(maximum * per_second)
    loudest = max(energy) if energy else 0.0
    candidates: list[Candidate] = []

    for start in onsets:
        if start < low_frame or start > high_frame:
            continue
        # An opening gesture reads best when the bar before it is quieter than
        # the note itself, so the chime feels like it begins rather than cuts in.
        before = energy[max(0, start - int(per_second * 0.6)):start]
        lead_in = (sum(before) / len(before)) if before else loudest
        attack = curve[start]

        for end in onsets:
            span = end - start
            if span < min_frames or span > max_frames:
                continue
            if end >= len(energy):
                continue
            body = energy[start:end]
            if not body:
                continue
            # Resolution: the tail should be decaying into the cut, not rising.
            tail = energy[max(start, end - int(per_second * 0.5)):end]
            decay = (tail[0] - tail[-1]) if len(tail) > 1 else 0.0
            loudness = sum(body) / len(body)
            target = (minimum + maximum) / 2.0
            fit = 1.0 - abs(span / per_second - target) / max(target, 1e-6)

            score = (
                attack * 1.6                       # decisive opening
                + (loudness - lead_in) * 0.5       # opens out of relative quiet
                + decay * 0.8                      # lands on a resolution
                + fit * 4.0                        # near the requested length
                + (loudness - loudest) * 0.25      # not a dead-quiet passage
            )
            candidates.append(Candidate(start, end, score))

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates


def nearest_zero_crossing(samples: array.array, index: int, radius: int) -> int:
    """Nudge a cut onto a zero crossing so no click survives the fade."""
    limit = min(len(samples) - 1, index + radius)
    for offset in range(0, radius):
        for probe in (index - offset, index + offset):
            if probe <= 0 or probe >= limit:
                continue
            if samples[probe - 1] <= 0.0 <= samples[probe]:
                return probe
            if samples[probe - 1] >= 0.0 >= samples[probe]:
                return probe
    return index


def shape(samples: array.array, start: int, end: int) -> list[float]:
    """Extract the window, seat both edges at zero, and normalise the peak."""
    start = nearest_zero_crossing(samples, start, int(SAMPLE_RATE * 0.02))
    end = nearest_zero_crossing(samples, end, int(SAMPLE_RATE * 0.02))
    clip = [float(value) for value in samples[start:end]]
    if not clip:
        raise ValueError("empty clip window")

    fade_in = min(int(FADE_IN * SAMPLE_RATE), len(clip) // 8)
    for index in range(fade_in):
        clip[index] *= 0.5 - 0.5 * math.cos(math.pi * index / max(1, fade_in))
    fade_out = min(int(FADE_OUT * SAMPLE_RATE), len(clip) // 2)
    for index in range(fade_out):
        position = index / max(1, fade_out - 1)
        clip[len(clip) - fade_out + index] *= 0.5 + 0.5 * math.cos(math.pi * position)

    peak = max(abs(value) for value in clip)
    if peak > 0.0:
        gain = PEAK_TARGET / peak
        clip = [value * gain for value in clip]
    return clip


def write_wav(path: Path, clip: list[float]) -> None:
    frames = array.array(
        "h", [max(-32768, min(32767, int(round(value * 32767.0)))) for value in clip]
    )
    if sys.byteorder != "little":
        frames.byteswap()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames.tobytes())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="generated suite to cut from")
    parser.add_argument("--out", type=Path, help="destination WAV")
    parser.add_argument("--min", type=float, default=4.0, help="shortest clip")
    parser.add_argument("--max", type=float, default=10.0, help="longest clip")
    parser.add_argument("--region-start", type=float, default=0.0)
    parser.add_argument("--region-end", type=float, default=0.0,
                        help="0 searches to the end of the source")
    parser.add_argument("--at", type=float, default=None,
                        help="cut from this exact second instead of searching")
    parser.add_argument("--list", type=int, default=0,
                        help="print the N best windows and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    samples = decode(args.source)
    energy = frame_energy(samples)
    curve = novelty(energy)
    onsets = find_onsets(curve, min_gap_frames=int(0.12 * SAMPLE_RATE / HOP))

    if args.at is not None:
        start = int(args.at * SAMPLE_RATE)
        end = start + int(args.max * SAMPLE_RATE)
        chosen = Candidate(start // HOP, end // HOP, 0.0)
    else:
        ranked = rank_windows(
            energy, curve, onsets, args.min, args.max,
            (args.region_start, args.region_end),
        )
        if not ranked:
            print("no window matched the duration bounds", file=sys.stderr)
            return 1
        if args.list:
            for item in ranked[:args.list]:
                print(f"{item.start_seconds():8.3f} -> {item.end_seconds():8.3f}"
                      f"  ({item.seconds():5.2f}s)  score {item.score:7.3f}")
            return 0
        chosen = ranked[0]

    clip = shape(
        samples,
        int(chosen.start_seconds() * SAMPLE_RATE),
        int(chosen.end_seconds() * SAMPLE_RATE),
    )
    if not args.out:
        print("no --out given", file=sys.stderr)
        return 1
    write_wav(args.out, clip)
    print(f"{args.out}: {len(clip) / SAMPLE_RATE:.2f}s "
          f"from {chosen.start_seconds():.3f}s of {args.source.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
