# 0.2.2 refresh conformance snapshot

The current binding is `providers.toml`; `providers-import.toml` preserves the
historical import campaign. The developer matrix passed **5/5 providers,
2 passes, 10 invocations and 90 ordered checks** against SDK implementation
`d5dc91d3df7afed99a972dbd760d3e5703ba8697` and external IceWM
`70ae6952fd3f28133b1ac027dcd558ba166b580b`. The TUI mirror is based on reviewed
`14d981c7f5d96621b6ec784f750f49c2c5b56521` with only the declared SDK adaptations.

Each provider was bound to its exact clean repository root and entry digest.
For in-tree providers, the source root is the SDK root and the entry path is
relative to that root. This uses the existing matrix API without omitting
source identity or pretending the component directory is a Git root. The API
checks each binding before the matrix and before/after each invocation: 25
source checks and 25 entry checks. The binding names the implementation commit
that was tested; this later metadata commit changes no component bytes.

Version, metadata, configuration, screenshot availability, migration dry-run
and read-only behavior are covered. Cap and IceWM truthfully report headless
screenshot unavailable; the other three providers produce an image. Land's
entry hash identifies the actual tested build and remains build-path dependent.
The full SDK gate, installed-wheel and runtime packaging, 398 historical import
identities, exact refresh sources, and all 19 recursive dependency pins were
also checked. The full root gate was rerun after the read-only version and
real-startup bootstrap test repairs; K95 passed 97/97 and TUI 30/30 modules.
This is developer qualification, not release acceptance.

The frozen contract and historical requirements are not rewritten to assert
acceptance. Installed/outer-launcher acceptance, peer-coupling removal, live
Grok and delivery behavior, physical desktop/audio/display, and ISO
boot/install/upgrade/rollback remain outside this return. Read the following
historical findings as the import campaign's measurements, not as claims about
the current source-bound snapshot.

---

# Conformance status — what is proven here and what is not

**This repository grades nothing.** The numbers below are what the builder
measured. They are evidence for a reviewer, not an acceptance.

## What the five-provider matrix measured

With the contract at `components/kilix-desktop-contract` and the five providers
bound in `providers.toml`, the common matrix ran: **1/1 runs, 5/5 providers,
2/2 passes, 10/10 invocations, 90/90 ordered checks, 30/30 source verifications
and 30/30 entry verifications.** The contract's own locked/offline gate ran
7/7 schemas, 8/8 valid fixtures, 7/7 invalid fixtures, 1/1 hostile catalogue,
62/62 unit methods, 1/1 C11-header leg, 54/54 manifest members and 172/172
rejected premature-adoption mutations.

That matrix was executed through a **developer** launcher, against local source
roots. Promotion to release authority requires the accepted outer
launcher/harness, which is **0/1**.

## What is explicitly not closed

| Gate | State | Owner of the missing return |
| --- | --- | --- |
| Contract freeze (P1/E1) | **not frozen** — `manifest.toml` says `frozen = false` | Track B / F119: result-schema shape and S5, behind Track A / F100's accepted authority return |
| Installed-conformance campaign (E3) | **0/1 accepted packets** | the shared-launcher implementer and the independent acceptance-harness owner (request 003) |
| Outer-launcher promotion | **0/1** | same as E3 |
| Parent creation, tags, redirects, archival (P8) | **not done, not requested here** | the owner; reserved authority |
| Consumer repoint to one closure pin (P9) | **not started** | F120 `release-lock` v1, then this stream |
| Independent acceptance of this candidate | **0/2 seats** | two eligible independent reviewers |

## Peer-coupling gates (P3) that this candidate does NOT yet satisfy

The import moved history; it did not delete couplings. All four remain live in
the imported trees and are the next behavioural work, not a documentation gap:

- `components/kilix-tui-utils/src/kilix_tui/xdgapps.py` is still the byte mirror
  of the host scanner, with its sync tool and parity test.
- `components/kilix-cap/src/game_catalog.c` still resolves a sibling `kilix-95`.
- `components/kilix-land-desktop/src/launcher.c` still probes a TUI-installed
  `kilix-launcher`.
- `kilix-launcher` is still shipped by `components/kilix-tui-utils/install.sh`.

A repository-wide grep gate asserting zero peer imports is therefore **0/1**.

## Finding: the harness cannot express a monorepo component's identity

This is what the import rehearsal was for, and it found something.

`kilix_desktop_contract.conformance._verify_matrix_source` binds each provider
by running, at the provider's `source_root`:

```sh
git -C <source_root> rev-parse --show-toplevel HEAD HEAD^{tree}
```

and requiring the three results to equal `source_root`, `source_commit` and
`source_tree` exactly. That model assumes **one Git repository per provider**.
Measured against this parent for `kilix-95`:

| Field | What the harness reads | What the binding requires |
| --- | --- | --- |
| `--show-toplevel` | the parent repository root | the provider directory |
| `HEAD` | the parent's commit | `daf4e3aa4f7be9708fd026110c2f7de180c0a1ec` |
| `HEAD^{tree}` | the parent's tree | `f1f659e2e6c8beb41d5ddfb08a17ddce93ee4dca` |

All three differ, so the check raises `conformance matrix source identity
changed` for **4/4** in-tree providers. Only `kilix-icewm`, which stays a
separate repository, still satisfies it — **1/5**.

### The matrix was then actually run against this layout — three ways

Reading the code is not evidence. All four in-tree providers were **built from
this monorepo** (Cap and Land compiled from their `components/` roots with the
19/19 upstream submodules materialised at their manifest gitlinks), and the
matrix was run through the harness's own API, unmodified, against the
E2-integrated Kilix host at `014e55b9…` (tree `68618b92…`):

| Run | Source binding | Population | Result |
| --- | --- | --- | --- |
| **A** | frozen, per-repository | 5/5 | `REFUSED — conformance matrix source identity changed for kilix-95 before matrix` |
| **B** | omitted (the harness permits it) | 5/5 | `REFUSED — conformance matrix entry digest changed for kilix-land-desktop before matrix` |
| **C** | omitted | 4/5 | **PASS — 4/5 providers, 2/2 passes, 8/8 invocations, 72/72 checks** |

Run A confirms the finding above by execution rather than by reading. Run C is
the useful number: with the source binding absent — **0/5 source identities
verified, and this candidate does not claim otherwise** — the relocated
providers **behaviourally conform at their new paths**, 72/72 checks over two
fresh passes.

### Second finding: Land's binary is not reproducible from a new root

Run B refuses before any provider executes, and the cause is not the contract.
Rebuilt from `components/`, three of the four in-tree entries reproduce their
frozen `entry_sha256` **byte for byte** — including Cap's compiled binary at
`4493e11b…`. Kilix Land's does not: bound `aee55e67…`, rebuilt `eecaad14…`.

Measured cause: Land compiles with `CFLAGS ?= -O2 -g` and Cap does not, so
Land's binary embeds its absolute build path — **16** occurrences of the
monorepo root, against **0** in Cap's. Rebuilding Land with
`-ffile-prefix-map` pointing back at the old root cuts that to **6** and still
does not reproduce the digest; the remaining six enter through the sub-makes
(`kilix-game-kit`, `kilix-ui`, `kilix-top-down-engine`), which pass absolute
build directories of their own.

**A relocation therefore changes Land's entry digest by construction**, and the
frozen requirements pin that digest. Closing it means making Land's build
path-independent — a change to `components/kilix-land-desktop` and its
sub-makes, which moves the tree the 90/90 matrix was measured against and so
must land as reviewed component work, not as a build-time flag someone passes
to make a number pass. It is recorded, not papered over: the run that would
have needed it is reported as REFUSED above.

Tree identity still holds and is independently checkable: **5/5** component
trees here are byte-identical to the revisions the 90/90 matrix was measured
against, and **4/4** in-tree ones are the exact `source_tree` values in
`providers.toml`.

Closing this needs the contract's source-binding surface to gain a component
identity — a repository root plus a component path plus that path's subtree —
rather than a repository HEAD. That is a **contract change**, so it belongs to
the E1 freeze, which is itself blocked. It is recorded here, not worked around:
no binding was loosened and no check was disabled to make a number look better.
