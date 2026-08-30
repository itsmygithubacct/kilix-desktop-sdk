# Fixtures

The frozen fixture population lives with the contract, not here, so that a
fixture cannot drift from the schema it exercises:

- `components/kilix-desktop-contract/fixtures/valid/` — 8 files
- `components/kilix-desktop-contract/fixtures/invalid/` — 7 files
- `components/kilix-desktop-contract/fixtures/hostile/` — 1 catalogue and its
  expected sanitized output

The hostile catalogue is the load-bearing one: it carries escapes, OSC and DCS
sequences, hyperlinks, bidi overrides and oversized runs, and the expected file
is what a provider must render after the shared client neutralises them.

This directory exists for fixtures that span more than one component and
therefore belong to no single one. It is empty by intent at this revision.
