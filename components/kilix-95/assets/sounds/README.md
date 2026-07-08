kilix sound assets
==================

These WAV files are original Strudel-rendered UI cues for the built-in sound
schemes:

- `95/`: softer classic desktop cues for `kilix 95`
- `xp/`: brighter desktop cues for `kilix XP`

Files are mono 44.1 kHz 16-bit PCM and normalized for UI playback. If a
bundled asset is missing or unreadable, `sounds.py` falls back to its
pure-Python synthesizer for the same event id.
