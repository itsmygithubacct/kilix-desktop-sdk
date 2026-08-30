# Sound asset provenance

Two classes of audio ship in this directory, with different origins and
different licensing positions. Both are recorded here so the distinction is on
file rather than assumed.

## UI cues (open, close, error, asterisk, …)

Original Strudel-rendered cues, unchanged. Mono 44.1 kHz 16-bit PCM.

## Startup and shutdown chimes

The four marquee cues are short excerpts cut from instrumental suites generated
with **MiniMax Music `music-2.5+`**, in instrumental mode, at 44.1 kHz /
256 kbps, from project-authored text prompts. **No reference audio, no lyrics,
no vocals, and no existing melody were supplied to generation.** The prompts
describe instrumentation, key, tempo and phrase shape only; no product, brand,
artist or composition is named in any prompt, so no specific existing chime was
targeted.

| Installed cue | Source suite | Window | Length |
|---|---|---|---|
| `95/startup.wav` | `kilix95-horn2.mp3` | from 16.033s | 7.59s |
| `95/shutdown.wav` | `kilix95-horn2.mp3` | from 85.496s | 7.56s |
| `xp/startup.wav` | `kilixxp-trombone.mp3` | from 0.000s | 8.00s |
| `xp/shutdown.wav` | `kilixxp-trombone.mp3` | from 132.493s | 9.60s |

Each flavour's pair is cut from one suite, so startup and shutdown are related
within a flavour and distinct across them: solo french horn for `95`, solo
tenor trombone for `xp`.

### Pinned sources

The suites are **not** part of this repository. They are retained privately
outside the source tree together with the exact prompt files that produced them,
and pinned here by digest so any cue can be re-derived and verified against the
same source:

| File | SHA-256 | Bytes |
|---|---|---|
| `kilix95-horn2.mp3` | `87e947e84376c2a722921b266912511f0db427d23a75485cc33eba083fc94f1e` | 3192567 |
| `kilixxp-trombone.mp3` | `a67c5aaee6721ba34896b9dbd3f5f1cc5f45619f45a307ba470284c7e5aaf875` | 5095347 |

### How the cuts were made

`tools/cut_chimes.py` (stdlib + ffmpeg, deterministic) selects a window whose
edges are already musical rather than cutting to a fixed length: it builds an
onset-strength curve, scores onset-to-onset windows, and prefers one that opens
on a decisive attack out of a quieter bar and **ends on a later onset** — the
instant the next phrase begins, and therefore the instant the previous one has
resolved. Both edges are then moved to the nearest zero crossing, with a 12 ms
seat-in and a 180 ms release, and the result is peak-normalised to 0.708 to
match the rest of the bank. Every installed cue measures exactly `+0` at its
first and last sample.

Two cues were positioned by ear instead of by the ranking, using the tool's
`--at` option; the table above records the exact windows either way.

## Licensing position, and its known limitation

Only these short, processed excerpts ship. The generated suites themselves are
deliberately **not redistributed** — not in this repository, not in Plebian-OS,
and not as a playable track. `apps/amp.py` copies the four installed cues into
`~/Music/Kilix` for playback in the media player; those are the same files the
desktop already ships, so nothing additional is distributed by that copy.

**The limitation:** MiniMax's output rights for API use could not be verified.
The publicly retrievable MiniMax Terms of Service is a framework document that
incorporates product-specific terms by reference and states that those product
terms control; the Open Platform (API) terms governing this account were not
publicly retrievable in English. The retrievable App and Web terms permit use
"for personal, non-commercial use only" and take a broad licence over generated
content, but those govern the app rather than the API and cannot safely be
transposed to it. The Music Creation terms place the rights obligation on the
user and warrant nothing about the originality, non-infringement or commercial
usability of output.

Consequently:

- shipping the raw generated suites is **not** claimed to be permitted, and is
  not done;
- the short derived cues ship on the same footing as the rest of this project's
  generated audio, with the boundary above recorded rather than a rights grant
  asserted;
- before any wider use — redistributing a full track, or relying on these cues
  commercially — the Open Platform terms attached to the generating account
  should be obtained from MiniMax and this file updated with what they say.

No Microsoft audio, artwork or fonts are bundled anywhere in this project.
