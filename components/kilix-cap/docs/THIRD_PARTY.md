# Third-party code

The shared stack arrives as one pinned submodule, `third_party/kilix-game-sdk`,
the way every SDK-backed game in this workspace takes it. The SDK pins
`kilix-game-kit`, which pins the components below; a build resolves them from
that closure rather than fetching anything itself.

Separately vendored copies used to sit here instead. They drifted: the
framebuffer snapshot had reached 0.2.0 carrying a local patch while upstream
was at 0.3.0 with a shared-memory frame transport. A pin cannot drift without
saying so, which is the reason for the change.

| Component | Version macros | Location under `third_party/kilix-game-sdk/kilix-game-kit/third_party/` |
|---|---:|---|
| kitty-terminal-session | 0.2.0 | `kitty-terminal-session/` |
| kitty-framebuffer | 0.3.0 | `kitty-terminal-session/third_party/kitty-framebuffer/` |
| kitty-input | 0.1.0 | `kitty-terminal-session/third_party/kitty-input/` |
| kitty-keyboard | 0.1.0 | `kitty-terminal-session/third_party/kitty-input/third_party/kitty_keyboard/` |
| soft-raster | 0.2.0 | `soft-raster/` |
| pcm-mixer | — | `pcm-mixer/` |

Each component's license is retained as `LICENSE` in its directory.

Text is drawn with soft-raster's `SR_FONT_COMPACT_7X14` face, scaled by whole
pixels to the canvas. Those are Cap's own authored glyphs: they moved into the
shared module on 2026-08-06 as a selectable face, so there is one glyph
rasterizer in the binary rather than a private one beside the linked one. The
face is chosen by name rather than taken as the default, because soft-raster's
default descends from the X11 8x16 fixed BDF by way of Debian's console-setup
and carries the permissive notices that implies, while these glyphs were
authored from generic bitmap-letterform practice and the written legibility
requirement alone.

The audio wrapper uses pcm-mixer's strict WAV loader and optional POSIX sink
transport. Audio source provenance is separate from code provenance and is
recorded in [audio-provenance.json](audio-provenance.json).

## Generation-time visual tooling

The room and isolated-sprite sources used by 3.0.0 were generated with the OpenAI built-in image
generation tool. Gemini image generation was requested, but no Gemini CLI,
SDK, credential, Vertex endpoint, or Gemini image-generation tool was
available; Gemini did not generate the committed assets. The OpenAI tool did
not expose its model identifier.

The initial Study composition, original Hallway, and object-free Storeroom
were text-only generations. A first Desk image edit used only the generated
Desk as its reference to replace one prop with the calendar. A second used
that generated result to clear the interactive props and reconstruct the
object-free background. The telephone used that generated Desk only as a
style reference. The object-free Game Room used the Storeroom and Desk as
architectural/style references, and its nine-cell media sheet used only the
new room and generated Desk objects as material/style references. Seven later
door editions each edited only their corresponding project-owned room source.
No third-party or commercial-product image was an input.

The 3.0 mansion pass added independent Grand Gallery, Server Room, Library,
Cleaning Room, and Balcony text-to-image sources. No third-party or
commercial-product image was an input.

Pillow 9.4.0 was used locally by tools/prepare_visual.py to produce the eight
1440×768 P6 room plates and by tools/prepare_workdesk_items.py to produce the
Desk RGB object layer, anti-aliased visual mask, and semantic hit-ID map.
The same offline Pillow preparation produces the nine-cell game-media
RGB/alpha atlas after local chroma-key removal. These
were offline, one-time preparation steps. Neither the image-generation
service nor Pillow is a linked, vendored, build-time, or runtime dependency of
kilix-cap. All 19 prompts, transformations, roles, hashes, and review are in
[visual-provenance.json](visual-provenance.json).

## Optional external programs

Game Room icon faces are Kilix 95's original project-authored 16×16 pixel art,
not third-party artwork. The live helper exports the selected checkout's exact
palette pixels; Kilix Cap retains matching compact snapshots solely for
deterministic offline render fixtures.

Live audio may invoke an installed pacat, pw-play, aplay, or SoX play process.
Clicking a Study prop or a mansion appliance may directly invoke one of the
installed desktop programs listed in [APPS.md](APPS.md); a selected Game Room
item may invoke a sibling Kilix 95 checkout. These programs are discovered at
runtime, are not linked into or redistributed with kilix-cap, and are not
required for the built-in interactions. Their own licenses, network use,
filesystem access, and persistence behavior remain their responsibility.
