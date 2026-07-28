kilix sound assets
==================

These WAV files are the built-in sound schemes:

- `95/`: softer classic desktop cues for `kilix 95`
- `xp/`: brighter desktop cues for `kilix XP`

The UI cues are original Strudel-rendered audio. The `startup` and `shutdown`
cues are short excerpts cut from generated instrumental suites — see
[PROVENANCE.md](PROVENANCE.md) for the model, prompts, pinned source hashes,
exact cut windows, and the licensing position including its known limitation.

Files are mono 44.1 kHz 16-bit PCM and normalized for UI playback. If a
bundled asset is missing or unreadable, `sounds.py` falls back to its
pure-Python synthesizer for the same event id.
