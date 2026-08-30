# kilix-desktop-sdk

The Kilix desktop domain monorepo: one frozen provider contract and the four
desktop components that implement it, assembled with their histories preserved.

**Status: BUILT — AWAITING INDEPENDENT ACCEPTANCE.** Nothing here is accepted.
This branch is a reviewable candidate published under `work/*`; it is not a
release, not a tag, and not a pin. It carries no acceptance grade from its
builder, and the builder may not grade it.

## Layout

```text
kilix-desktop-sdk/
├── README.md
├── LICENSES/                  MIT and CC BY-NC-SA 4.0 full texts
├── .reuse/dep5                per-path licence declarations
├── manifest.toml              component identities, edges, schema surface
├── components/
│   ├── kilix-desktop-contract/  the frozen contract: schemas, C11 header, Python package
│   ├── kilix-95/
│   ├── kilix-cap/
│   ├── kilix-land-desktop/
│   └── kilix-tui-utils/
├── integration/
│   ├── conformance/           the five-provider conformance binding
│   ├── fixtures/              pointers to the contract's frozen fixtures
│   └── migration/             the staged persistence-migration order
├── tools/                     provenance and layout verifiers
└── docs/provenance/           old→new commit maps for every imported commit
```

`kilix-icewm` is **not** a component here. Under OD-10
`SEPARATE_CONTRACT_CONSUMER` it stays in its own repository and consumes this
contract as a mandatory conformance consumer. Its binding is recorded in
`integration/conformance/providers.toml`; its history is not imported.

## Mixed licensing — read this before redistributing

This repository is **not uniformly permissive**. Every clone acquires
NonCommercial-licensed content.

| Path | Licence |
| --- | --- |
| `components/kilix-land-desktop/assets/**` | CC BY-NC-SA 4.0 |
| `components/kilix-cap/assets/**` | see `components/kilix-cap/COPYING-ASSETS.md` |
| everything else authored here | MIT |
| `components/*/third_party/**` | upstream submodules, retained as gitlinks, under their own licences |

The machine-readable mapping is `.reuse/dep5`. The upstream submodules under
`components/kilix-cap/third_party/` and `components/kilix-land-desktop/third_party/`
are **not** vendored: they remain gitlinks pointing at their own repositories,
and their licences are theirs.

## History preservation

Every commit of every imported component is present, with its original author,
committer, timestamps, message and tree. The only change is that each
component's tree now sits under `components/<name>/`. The old→new mapping for
all 398 imported commits is in `docs/provenance/`, and
`tools/verify-provenance.py` re-derives and checks it against this repository.

Published branches that are not ancestors of the imported tip were preserved by
reachability rather than adopted into the tree — they are ancestors of the
`preserve published history` commit, and they are listed with their originals in
`docs/provenance/preserved-refs.tsv`. Nothing published was dropped; nothing
unadopted was silently merged into a component tree.

## Verifying this candidate

```sh
python3 tools/verify-provenance.py     # 398 commits: identity, parents, trees
python3 tools/verify-layout.py         # component trees == their source revisions
```

Both run offline against this repository alone.
