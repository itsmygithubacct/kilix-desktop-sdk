# Desktop parity refresh for 0.2.2

The original 398 imported commits, maps, `source_revision` and
`imported_revision` values are historical and unchanged. Each component now
also records `refresh_revision` and the exact `refresh_local_changes` relative
to that source. `tools/verify-refresh.py --source NAME=REPO` accepts one local
source repository per component and checks Git blob identities, modes and
submodule pins at those immutable revisions. It does not trust the source's
working files or current branch, and missing sources are unresolved, not passes.

The selected Kilix 95 and TUI sources supply current settings, version and game
catalog compatibility, XPane test ownership, accessibility, document recovery,
workflow lifecycle, music controls and pane tools. The SDK's provider protocol
and persistence adapters remain. Kilix 95's selected source declares
GPL-3.0-only; its licence text and the root licence map follow that source.
Original protocol/persistence adapters retain their MIT terms.

Cap and Land retain their SDK protocol/persistence adapters while adopting the
standalone lifecycle repairs, bounded child registration and shared process
identity format. Land's full-suite fixture now removes its identity sidecar.
Cap's normal test target includes the lifecycle and chooser regression harnesses.
The root test gate now includes Kilix 95. TUI tests use isolated homes/storage
and short temporary paths, retaining explicit source and native dependencies.

Contract distributions include schemas and side contracts. An sdist-to-wheel
check removes the source trees before validating the installed resources.
Actions accept schema-permitted extension keys without relaxing required-field,
verb or type validation. Schema bytes and historical acceptance records are
unchanged; source checksums include the packaging implementation and tests.

## Integration requirements

Deploy the SDK, matching standalone Cap/Land sources and the host laptop registry
companion together. The registry consists of a canonical decimal `.pid` plus
`.pid.identity` (`v1 PID START_TICKS BOOT_UUID`). Legacy or mismatched records
fail closed, readers retain shared records, and close uses a revalidated pidfd.
An older host or standalone provider is not a supported mixed deployment.
Existing legacy sessions should be closed through their owning windows.

The host companion is based on the selected 0.2.2 host. Other host workstreams
must merge their changes with it, then rerun the provider and registry checks.
The selected Python provider requires host SDK 1.16. The external IceWM source
is separately bound by its reviewed candidate revision; it is not imported.
Exact integration revisions and qualification commands are recorded in the
worker report; no shared release manifest or installed desktop is changed here.

## Qualification boundaries

Full component suites, installed-wheel checks, historical provenance and exact
refresh comparisons are separate from release acceptance. Mocked process
identity combinations do not qualify physical desktop lifecycle. Source-bound
conformance uses the monorepo root as the source identity and the component
entry beneath it; it does not pretend each component is a standalone Git root.
Land entry hashes bind the actual build tested and remain build-path dependent.
Historical conformance records do not grade this refresh. ISO, installation,
upgrade/rollback, live desktop and physical audio/display acceptance remain.
