# Third-party code

The repository vendors source snapshots so a build does not fetch code from
the network.

| Component | Version macros | Location |
|---|---:|---|
| kitty-terminal-session | 0.1.0 | `third_party/kitty-terminal-session/` |
| kitty-framebuffer | 0.2.0 | `third_party/kitty-terminal-session/third_party/kitty-framebuffer/` |
| kitty-keyboard | 0.1.0 | `third_party/kitty-terminal-session/third_party/kitty_keyboard/` |
| soft-raster | 0.2.0 | `third_party/soft-raster/` |
| pcm-mixer | commit `9cc695cde53a` | `third_party/pcm-mixer/` |

Each component's license is retained as `LICENSE` in its directory. The audio
wrapper uses pcm-mixer's strict WAV loader and optional POSIX sink
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
480×256 P6 room plates and by tools/prepare_workdesk_items.py to produce the
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
