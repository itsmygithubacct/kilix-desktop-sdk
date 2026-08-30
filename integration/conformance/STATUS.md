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
