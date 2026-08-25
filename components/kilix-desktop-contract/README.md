# kilix-desktop-contract

Language-neutral protocol v1 for Kilix desktop providers.

This tree is a **1.0.0 release candidate**. Its schemas, fixtures, vocabulary,
helpers, and import-identity record are byte-bound by `SHA256SUMS`. The v1
identity is not declared frozen until the F119 result-schema dependency is
available and an independent contract review has closed all findings.

## Provider interface

Every provider executable implements:

```text
<provider> --version
<provider> provider describe --json
<provider> provider check --json
<provider> provider launch [--session-id ID]
<provider> provider screenshot OUTPUT [provider options]
<provider> provider config schema --json
<provider> provider config get [KEY] --json
<provider> provider config set KEY VALUE
<provider> provider migrate --from VERSION [--dry-run]
```

JSON stdout is exactly one UTF-8 JSON document followed by one newline.
Diagnostics go to stderr. Non-interactive endpoints do not prompt. The host
supervises every endpoint, owns timeouts, kills the complete provider process
group on a deadline, and force-restores terminal modes after abnormal exit.
`launch` runs in the foreground and handles `SIGTERM` with best-effort cleanup
inside the shutdown grace period.

`provider describe` and `provider check` emit documents validated by
`kilix.desktop.provider-description/v1` and
`kilix.desktop.provider-check/v1`. `provider config schema` emits a Draft
2020-12 schema whose Kilix metadata conforms to the config-schema contract.
`provider config get` emits `kilix.desktop.provider-config/v1`.
`provider migrate` emits `kilix.desktop.migration/v1` for both dry runs and
executed migrations.

The closed action verbs, capability and display-mode vocabularies, deadline
defaults, and exit statuses live in `contracts/vocabulary-v1.json`. Unknown
compatible JSON fields are ignored. An unknown value in a closed vocabulary or
an unknown mandatory capability fails closed. A host refuses contract versions
newer than it supports; older versions require an explicit compatibility
adapter.

## Stable import and command identities

`contracts/import-identities-v1.json` records names that survive repository and
install-path relocation. In particular:

- Python imports `kilix_tui` and `kilix_desk` do not change.
- Every existing `tools/*` launcher keeps its installed command name.
- The composed desktop and center command names also remain stable.

The parent repository, source URL, and install prefix may change. These public
identities may not.

## Security boundaries

Desktop catalog text is untrusted. `sanitize_catalog_text` removes ANSI
CSI/OSC/DCS and related escape sequences, terminal controls, bidi formatting
controls, and invalid Unicode; it normalizes whitespace and enforces both
character and UTF-8 byte bounds before providers render the text.

Actions split on the first colon. Verbs are closed. `url.open` accepts HTTPS
URLs without credentials. `document.open` is data only: the host resolves it
through document-handler policy, refuses executable types and paths outside
permitted roots, and never executes the payload.

The shared XDG store is authoritative only after a completed migration record.
Before completion and after rollback, the legacy store remains authoritative.
Providers fail closed if authority cannot be determined.

## Validation

Use the release-selected uv 0.12.5 binary:

```sh
uv run --locked --offline python validate_contract.py --self-test
sha256sum -c SHA256SUMS
```

The self-test checks Draft 2020-12 schemas, canonical JSON, duplicate-key and
size rejection, valid and invalid fixtures, action parsing, hostile catalog
sanitization, the C11 header, import identities, and every byte listed in
`SHA256SUMS`. Run it twice against an unchanged tree for the freeze gate.

After v1 is frozen, a change that invalidates an accepted v1 document or alters
a closed vocabulary requires a new schema identity. Additive optional fields
may be clarified without changing accepted bytes only through a separately
reviewed contract release.
