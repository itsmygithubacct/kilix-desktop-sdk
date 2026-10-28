# Desktop parity refresh for 0.2.2

The original 398 imported commits, maps, `source_revision` and
`imported_revision` values are historical and unchanged. Each component now
also records `refresh_revision` and the exact `refresh_local_changes` relative
to that source. `tools/verify-refresh.py --source NAME=REPO` accepts one local
source repository per component and checks Git blob identities, modes and
submodule pins at those immutable revisions. It does not trust the source's
working files or current branch, and missing sources are unresolved, not passes.

The selected Kilix 95 source and reviewed TUI source supply current settings, version and game
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
The reviewed TUI source is `3cad13ef9fe863c9c3bdaa1f212e46e14db15eb7`;
the separately reviewed IceWM source is `f6f52b044538c47fcac85d734a6862bb702f43d0`.
The Kilix 95 mirror follows `caf8921492d6e038e47f14d1c51f4a6226331a42`, whose
only change from `ca4c0403a7067a1a123cfecfa084cd53f828bdb8` pairs its required
CI with coordinated host `f5334e1c8c2076a21b3ac1800c4ea0b0bf489263`. It now follows `e22950d76b411cafddaf688da029c8b9abaf2528`,
whose only change from that source pairs the same CI with the coordinated host
repairs `3fdc6dbb78b70e23b488b2d3cbc52d209c3ede87`.
It now follows `657f0d39350ac92ef851dba0b6d2cb5a560d7602`, which merges main's
`b1f71aa6959943e0e9934d8f753c10b01808eab8` (workflow readiness names the selected
Ask backend) and pairs the same CI with merged host
`b80a543638301615f80c9794cdd98a587afb39b0`.
It now follows `39d1daf4d7bba57c09889759b81540d8dc7fa248`, whose only change pairs the same
CI with host `7a1c3622a83c486fb19ca0dc14bef09b89f46e0c`, which keeps the Qwen
provider's Content authority on the merged Content.
It now follows `13740a44c68409dfe2b67e8fec041c630d1143de`, which names the checked Ask backend
before setup, marks its saved answers as Ask answers, and pairs the same CI
with host `99ad9cb877466d416ffd41fb2ce0dcdf8fecced9`.
It now follows `6f9f07059d70b5fe82f5326c98b6bbf1dfb29017`, which exposes the shared coding-session
grid preference in Settings, keeps its choices out of kitty.conf, and pairs CI
with host `3ca4e9c73917392062f65b5ed5eb51f5aecbb060`. The Tools tab keeps both
coding controls and their explanations above the action buttons.
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
