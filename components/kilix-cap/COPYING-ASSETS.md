# Runtime assets and clean-room boundary

kilix-cap 3.0.0 has a closed, committed visual inventory of 33 files under
`assets/art/`. The complete per-file roles, dimensions, formats, and SHA-256
hashes are recorded in `docs/visual-provenance.json` and enforced by
`tools/validate_visual.py`.

## License scope

The project code, documentation, generated visual pixels, project-authored
visual transformations, and rendered audio outputs are made available under
the repository's MIT License to the extent that kilix-cap contributors hold
copyright or other licensable rights in them.

For clarity, this grant includes the files under `assets/art/`: the generated
room and object imagery, the losslessly prepared runtime plates, the masks and
semantic hit map, and the project-authored composition layers. AI-generated
output may not be copyrightable or exclusive in every jurisdiction; the
project does not assert otherwise. The MIT grant covers whatever rights the
contributors can grant and does not create rights the contributors do not
hold.

The project does not relicense third-party material under MIT. Provider-issued
C2PA manifests, signatures, certificates, and marks remain provenance
metadata; CC0/public-domain audio inputs retain the status recorded in
`docs/audio-provenance.json`; and vendored code retains the notices in its
own `LICENSE` files. Those identified materials are distributed subject to
their own notices or legal status.

## Room backgrounds

Each of the eight rooms has a 1717×916 generated PNG source, preserved either
byte-for-byte or as a decoded-pixel-identical public snapshot, and an
offline-prepared 480×256 opaque P6 runtime plate. Seven rooms also preserve a
1717×916 room-specific door edit made directly from that room source:

| Room | Input source | Runtime source | Runtime plate |
|---|---|---|---|
| Study | `workdesk-room.png` | `workdesk-room-door-source.png` | `workdesk-room.ppm` |
| Grand Gallery | `hallway-room.png` | `hallway-room-doors-source.png` | `hallway-room.ppm` |
| Storeroom | `storeroom-room.png` | `storeroom-room-door-source.png` | `storeroom-room.ppm` |
| Server Room | `server-room.png` | `server-room-door-source.png` | `server-room.ppm` |
| Game Room | `game-room.png` | `game-room-door-source.png` | `game-room.ppm` |
| Library | `library-room.png` | `library-room-door-source.png` | `library-room.ppm` |
| Cleaning Room | `cleaning-room.png` | `cleaning-room-door-source.png` | `cleaning-room.ppm` |
| Balcony | `balcony-room.png` | `balcony-room.png` | `balcony-room.ppm` |

Server consoles, Cleaning Room stations, Library books, and Balcony
instruments are intentionally baked into those room plates. Project-authored
hotspots make the depicted objects interactive without adding textual menu
boxes over them. Doors are likewise depicted in their room plates: each edit
inherits that exact scene's perspective, trim, materials, illumination, and
shadows. The Grand Gallery's six leaves are individually generated along its
vanishing point; its central glazed Balcony entrance and the Balcony's return
entrance were already part of their source art.

## Layered object assets

- The Study uses `workdesk-items-source.png` as its preserved furnished
  source. `workdesk-items.ppm`, `workdesk-items-mask.ppm`, and
  `workdesk-items-hit.ppm` provide the 13-prop RGB layer, antialiased
  coverage, and exact semantic hit IDs. `telephone-sprite-source.png` and
  `telephone-sprite.png` preserve the generated and locally keyed repair
  source used during preparation.
- The live Game Room catalog uses `game-media-source.png`,
  `game-media.png`, `game-media.ppm`, and `game-media-mask.ppm` as a
  nine-variant CD/floppy/manual source and runtime atlas. Each present title
  receives an original project-owned 16×16 icon exported from Kilix 95's
  code-authored `icons.py`.
- The optional small-prop atlas uses `mansion-items-source.png`,
  `mansion-items.png`, `mansion-items.ppm`, and `mansion-items-mask.ppm`
  as a four-variant source and runtime layer for the Storeroom's storage
  box, wooden crate, and tin canister, and the Study laptop. Its prompts,
  hashes, and preparation live in `docs/visual-provenance-gemini.json`;
  when the group is absent the four props keep their procedural drawings.
Storeroom movable objects, dynamic state, borders, cursor, name bar, and house
map are drawn by project code as the standing fallback. No
commercial-product icon or artwork is included.

## Generated visual sources

Gemini image generation was requested during the original visual work, but no
Gemini CLI, SDK, credential, Vertex endpoint, or Gemini image-generation tool
was available. The committed generated sources were created with the
available OpenAI built-in image generation tool; its model identifier was not
exposed.

The 3.0 mansion pass generated a new Grand Gallery plus the Server Room,
Library, Cleaning Room, and Balcony as independent text-to-image sources.
Earlier Study, Storeroom, Game Room, telephone, and game-media passes
used only recorded text or previously generated project-owned art as
references. No screenshot, commercial-product image, or third-party artwork
was supplied to any generation. The seven room-door passes each used only its
corresponding project-owned room source as the edit target.

`docs/visual-provenance.json` records all 19 complete prompts, generation
modes, reference lineage, review assertions, dimensions, roles, and hashes.
These prompts include the five new mansion-room sources generated for 3.0.

Three provider outputs are committed as losslessly normalized public
snapshots. Only their compressed PNG `IDAT` representation changed; their
decoded RGB pixels are byte-identical to the provider outputs. Recompression
invalidates a C2PA credential's cryptographic hard binding, so the affected
files do not retain a credential that would fail validation. Provenance
version 5 records each original provider-output hash, committed-file hash,
decoded-RGB hash, and complete original `caBX` chunk hash. Other generated
sources retain their provider-issued C2PA data unchanged.

## Offline preparation and runtime

`tools/prepare_visual.py` uses Pillow 9.4.0 to convert each selected room
edition to RGB, center-fit it to 480×256 with Lanczos resampling, retain full
color, and write binary P6. The other preparation scripts create the Study
object layer and maps and the 144×168 game-media RGB/alpha atlas. The
image-generation skill's `remove_chroma_key.py` helper produced the telephone
and game-media intermediate RGBA sprite sources.

These are one-time authoring steps. Version 3.0.0 has no runtime palette
quantizer, image-generation dependency, or asset download. The runtime loads
all 13 P6 files as one atomic bundle so it cannot silently mix plates and
masks from different locations. Interactive mode has procedural fallbacks;
visual and release tests require the complete committed bundle. Door picking
uses project-authored architectural rectangles and does not require a runtime
door overlay.

## Audio assets

The twelve WAV files under `assets/sfx/` are original local renders. Complete
recipes, hashes, formats, and any CC0/public-domain source recordings are
recorded in `docs/audio-provenance.json`. Audio availability never changes
whether an interaction works. `KILIX_CAP_AUDIO=0` forces silent operation;
otherwise the mixer may use a locally installed `pacat`, `pw-play`, `aplay`,
or SoX `play` sink.

## Clean-room boundary

- No bytes from a commercial product may enter the runtime tree.
- No screenshot, executable, ROM, extracted font, extracted sound, or product
  artwork may be copied, traced, transcribed, or used as authoring input.
- Behavior and written interface specifications may inform an original
  implementation, but specific artwork may not be reproduced.
- Kilix 95 media-face icons are original project-authored pixel art, not an
  input to generated artwork.
- External desktop applications are discovered and launched at runtime; they
  are not bundled assets. Their network, filesystem, persistence, and license
  behavior remain their own.

`python3 tools/validate_visual.py` checks the exact 33-file inventory,
provenance status and lineage, dimensions, hashes, P6 structure, color
diversity, coverage masks, semantic IDs, and layer relationships.
`python3 tools/validate_audio.py` validates the audio inventory and provenance.
`make forbidden-check` scans the compiled binary and `assets/` for prohibited
product-data markers, extracted-binary formats, and symlinks.

Font provenance is in `docs/FONT.md`; vendored library licenses and visual
tooling notes are in `docs/THIRD_PARTY.md`.
