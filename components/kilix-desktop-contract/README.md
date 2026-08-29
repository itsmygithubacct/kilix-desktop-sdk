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

## Shared persistence command

The staged F120 prefix exports either the absolute
`KILIX_DESKTOP_CONTRACT_COMMAND` or an absolute `KILIX_DESKTOP_SDK_PREFIX`
whose command is `bin/kilix-desktop-contract`. Providers never search an
ambient checkout for this helper. The command owns path selection, validation,
the global lock, private modes, atomic writes and the migration record:

```text
kilix-desktop-contract storage authority
kilix-desktop-contract storage path PROVIDER {config,state,data,cache,session,runtime}
kilix-desktop-contract storage schema PROVIDER
kilix-desktop-contract storage get PROVIDER [KEY]
kilix-desktop-contract storage value PROVIDER KEY
kilix-desktop-contract storage set PROVIDER KEY VALUE
kilix-desktop-contract storage policy-path
kilix-desktop-contract storage policy {get,value,set} ...
kilix-desktop-contract storage shared-settings {get,update} ...
kilix-desktop-contract storage migrate PROVIDER --from VERSION [--dry-run]
kilix-desktop-contract storage rollback --from VERSION
```

The XDG policy is `$XDG_CONFIG_HOME/kilix/desktop.toml`; provider configuration
is `$XDG_CONFIG_HOME/kilix/desktops/<id>.toml`; state is rooted at
`$XDG_STATE_HOME/kilix/desktops/<id>/`, with corresponding XDG data and cache
roots. `~/.local/gpu_terminal` and its explicit legacy overrides remain the
sole authority until Land, TUI, Cap and Kilix 95 complete in that order. The
Kilix 95 step re-synchronizes all earlier inert copies before atomically
committing the authority flip. Rollback records legacy authority without
deleting the retained XDG copy. IceWM consumes the same resolver and contract
but is not a member of that four-provider migration order.

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

The same process-isolated non-interactive conformance runner is used for every
provider. During the ordered adapter-only window, before shared persistence is
available, invoke it with `--adapter-stage`; this requires migration to fail
explicitly with exit 4. The final gate omits that flag and instead requires a
valid dry-run migration record:

```sh
kilix-desktop-contract conformance \
  --kilix-home /absolute/bound/kilix \
  --contract-command /absolute/bound/kilix-desktop-contract-bridge \
  --state-library /absolute/bound/libkilix-state.so \
  --land-assets /absolute/bound/kilix-land-desktop \
  --adapter-stage -- PROVIDER [ARG ...]
kilix-desktop-contract conformance \
  --kilix-home /absolute/bound/kilix \
  --contract-command /absolute/bound/kilix-desktop-contract-bridge \
  --state-library /absolute/bound/libkilix-state.so \
  --land-assets /absolute/bound/kilix-land-desktop \
  -- PROVIDER [ARG ...]
```

The four authority paths are mandatory inputs rather than ambient environment
lookups. Provider children receive the closed 39-name F110 profile: caller
variables (including Python, loader, plugin, source-path and provider override
state) are not inherited. The release gate binds the four absolute inputs before
this runner starts; these command-line flags do not establish that outer
trusted-launcher authority by themselves.

`contracts/trusted-launcher-consumer-requirements-v1.json` makes the owned side
of that future interface machine-checkable. It fixes the E3 surface, child,
provider, environment and terminal populations, records the exact local E2/E4
evidence, and fixes the E4 installed-command migration/rollback sequence
without defining a competing launcher profile. The OD-13 component return and
the independently rejected OD-14 candidate remain non-consumable, so the
checker fails closed if either is promoted without an accepted return packet:

```sh
make launcher-consumer-readiness UV=/absolute/path/to/release-pinned-uv-0.12.5
make f110-local-gate UV=/absolute/path/to/release-pinned-uv-0.12.5
```

Passing this developer-readiness check does not adopt the shared launcher or
turn the local E3/E4 construction evidence into release acceptance.

The common developer gate takes a canonical command-set document with schema
`kilix.desktop.conformance-command-set/v1`. Its `commands` array must contain
the exact five provider IDs, in contract order, and each command must start
with an absolute executable. It runs two fresh final-mode passes and refuses a
changed provider identity or ordered nine-check tuple:

```sh
make common-conformance-gate \
  UV=/absolute/path/to/release-pinned-uv-0.12.5 \
  COMMANDS=/absolute/provider-commands.json \
  KILIX_HOME=/absolute/bound/kilix \
  CONTRACT_COMMAND=/absolute/bound/kilix-desktop-contract-bridge \
  STATE_LIBRARY=/absolute/bound/libkilix-state.so \
  LAND_ASSETS=/absolute/bound/kilix-land-desktop
```

A 5/5-provider, 2/2-pass, 10/10-invocation and 90/90-check result from this
runner is local SDK evidence only. The separate launcher must still supply and
protect all required return identities before release acceptance.

Both modes enforce bounded output and deadlines, exact JSON/newline rules,
schema and semantic validation, consistent provider identities, truthful
screenshot behavior, unavailable diagnostics, and zero live descendants after
each non-interactive endpoint. They redirect provider storage into an isolated
sandbox and reject filesystem changes from describe, check, config reads,
unavailable config writes, and migration dry-runs within that sandbox.
Launch/SIGTERM and terminal-restoration coverage remains in the host
integration suite because it requires a real presentation session.

After v1 is frozen, a change that invalidates an accepted v1 document or alters
a closed vocabulary requires a new schema identity. Additive optional fields
may be clarified without changing accepted bytes only through a separately
reviewed contract release.
