# Import evidence — every number with its denominator

Measured on the revision this file is committed at. Nothing here is a grade.

## What was imported

| Component | Source revision | Imported revision | Commits |
| --- | --- | --- | --- |
| `kilix-desktop-contract` | `50e5e8686bf1d15cfcec9db9fb23fe57f700f1d2` | `09c2f1dca431596ee71846db3629d62c282642c6` | 19 |
| `kilix-95` | `daf4e3aa4f7be9708fd026110c2f7de180c0a1ec` | `0febf62021548cd9697f2abfed83dbc905d73dbc` | 125 |
| `kilix-cap` | `7cc98eece67f9b6547d5fb0149d483117721a5cf` | `2e7b99ec76167818162423891f17a1a5c6d3f5d8` | 30 |
| `kilix-land-desktop` | `c0594aeb955352b904f006fed4c9774e496a2d38` | `298687c5e712e3636879a9e61f5fd31badda28ef` | 145 |
| `kilix-tui-utils` | `63187ee199aa16f71a460ef0e95ec876bee8b787` | `43d7fe829c6cf19a907597ef01f83e635ca33ffc` | 79 |
| **Total** | | | **398** |

The commit population is the union of every published ref of each component and
the revision F110's conformance matrix bound — 28 source refs in total. It is
not the mainline alone.

## Faithfulness

- **398/398** imported commits keep their original message, author, committer
  and timestamps byte for byte.
- **398/398** have the same parent count as their originals, and every parent
  maps to the imported form of the original's parent.
- **398/398** have a `components/<name>` subtree byte-identical to the original
  commit's whole tree, and nothing at all outside `components/`.
- **398/398** are reachable from this branch's tip.
- **0/398** duplicate imported commits across the five maps.
- **5/5** component trees at the tip are byte-identical to the unmodified
  source repositories at their recorded revisions. That identity is what
  carries F110's conformance evidence into this parent: four of these five trees
  are the exact `source_tree` values in `integration/conformance/providers.toml`.

`tools/verify-provenance.py` and `tools/verify-layout.py` re-derive all of the
above offline from this repository alone: **398/398** and **5/5** respectively.

## Published lines preserved but not adopted

**7/28** source refs are not ancestors of the revision their component was
imported at. They are ancestors of the `preserve published history` commit, so
every published commit is present, and that commit's tree is byte-identical to
its first parent's, so nothing was silently merged.

| Component | Ref | Imported tip |
| --- | --- | --- |
| `kilix-95` | `integrate/shared-libraries-20260721` | `63cb60f9c3cb8d76a12ca0a547392b125bc2ad6d` |
| `kilix-95` | `v0.1.1` | `05134ecf224fc6a06dc04cf59f69a4e27d20212e` |
| `kilix-95` | `v0.1.2` | `7a44c15040dfcc582726097ea61d327305992764` |
| `kilix-land-desktop` | `pre-reconcile-2026-08-04` | `1989d4f13ccc4c94c46072a8507fe62a80e81093` |
| `kilix-tui-utils` | `main` | `ea7c5932c3ed9247246379953701fe809fa9620a` |
| `kilix-tui-utils` | `release/0.2.0` | `c6898714ea15b5d51922c1ab928595b4c884c54d` |
| `kilix-tui-utils` | `licence/0.2.1-pin-v2` (= tag `catalog/0.2.1`) | `6547df315bc7de60ec3653d2edf7e9cb313b6be5` |

**The one that matters:** `kilix-tui-utils`'s published `main` carries two
commits, `b042e87` and `b53c259`, that the F110 line does not contain — a pane
center for live session coordination, and a fix to a credential path that panes
exposed. `components/kilix-tui-utils` here is the F110 conformance-bound
revision and therefore **does not** contain them. Adopting them would change the
tree the five-provider matrix was measured against, so a builder must not do it
unilaterally; deciding how they land is TUI-relocation work (E5/E6), which the
master orders last within this stream.

## Tags

**0** tags were created. Release tags are owner-reserved. The namespaced tags
the design suggests — `kilix-desktop-contract/v1.0.0`, `kilix-95/v0.2.1`,
`kilix-cap/v3.1.0`, `kilix-land-desktop/v0.2.1`, `kilix-tui-utils/v0.2.1`,
`desktop-sdk/v0.2.1` — are recorded as intended names in this file and nowhere
else. Source-repository tags survive as reachable commits, listed above and in
`preserved-refs.tsv`; they are not re-tagged here.

## Clone weight, measured

Packed size of each component's imported history, after `gc --prune=now`:

| Component | Packed |
| --- | --- |
| `kilix-desktop-contract` | 153.77 KiB |
| `kilix-95` | 8.07 MiB |
| `kilix-cap` | **76.86 MiB** |
| `kilix-land-desktop` | 34.79 MiB |
| `kilix-tui-utils` | 606.64 KiB |

**This contradicts the assumption in the scoping plan.** The keep-separate
criterion on binary weight was written against Kilix Land's 32 MB of assets. The
measured driver is **Kilix Cap at 76.86 MiB — roughly 2.2× Land** — so a decision
to split assets on weight alone would split the wrong component. Land remains
the licensing question (its assets are NonCommercial); Cap is the size question.
Both are open and neither is dispositioned by this candidate.

## What this candidate does not do

It does not freeze the contract, delete a single peer coupling, migrate an
installed machine, create a tag, repoint a consumer, or create a public
repository. `integration/conformance/STATUS.md` names each open gate and who
owns the missing return.
