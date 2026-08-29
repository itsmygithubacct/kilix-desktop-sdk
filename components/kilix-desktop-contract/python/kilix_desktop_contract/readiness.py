"""Validate Track E's consumer side of the non-forking launcher interface."""

from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
import sys
from typing import Any, Callable

from .jsonio import DocumentError, canonical_bytes, load_json
from .conformance import ConformanceError, MatrixProvider, verify_matrix_provider
from .persistence import MIGRATION_ORDER, SEPARATE_CONSUMERS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REQUIREMENTS = (
    ROOT / "contracts" / "trusted-launcher-consumer-requirements-v1.json"
)
SCHEMA = "kilix.track-e.trusted-launcher-consumer-requirements/v1"
STATUS = "developer-readiness-only-not-a-launch-profile"
COMMAND_SET_SCHEMA = "kilix.desktop.conformance-command-set/v1"
COMMON_CASES = ("ID-02", "ID-04", "SUB-04", "SUB-05", "SUB-06", "RES-10")
RETURN_IDENTITIES = (
    "public_commit",
    "public_tree",
    "launcher_sha256",
    "bootstrap_sha256",
    "interpreter_sha256",
    "result_schema_sha256",
    "profile_schema_sha256",
    "e3_profile_sha256",
    "e3_terminal_check_set_sha256",
    "installed_command_profile_sha256",
)
E3_SURFACES = (
    "installed-conformance",
    "provider-kilix-95",
    "provider-kilix-cap",
    "provider-kilix-land-desktop",
    "provider-kilix-tui",
    "provider-kilix-icewm",
    "installed-contract-command",
)
E3_CHILD_PROFILES = (
    "f110.provider.kilix-95/v1",
    "f110.provider.kilix-cap/v1",
    "f110.provider.kilix-land-desktop/v1",
    "f110.provider.kilix-tui/v1",
    "f110.provider.kilix-icewm/v1",
    "f110.installed-command/v1",
)
E3_ENVIRONMENT_NAMES = (
    "LC_ALL", "TZ", "PATH", "HOME", "TMP", "TEMP", "TMPDIR",
    "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR",
    "XDG_STATE_HOME", "GPU_TERMINAL_HOME", "GPU_TERMINAL_SETTINGS_FILE",
    "KILIX_HOME", "KILIX_STORAGE_HOME", "KILIX_CONFIG_HOME",
    "KILIX_STATE_DIRECTORY", "KILIX_CACHE_HOME", "KILIX_DATA_HOME",
    "KILIX_SESSION_HOME", "KILIX_BUILD_DIRECTORY", "KILIX_STATE_LIBRARY",
    "KILIX95_STORAGE_HOME", "KILIX95_CONFIG_HOME", "KILIX95_STATE_HOME",
    "KILIX95_CACHE_HOME", "KILIX95_DATA_HOME", "KILIX95_SESSION_HOME",
    "KILIX_CAP_CONFIG_HOME", "KILIX_LAND_DESKTOP_CONFIG_HOME",
    "KILIX_LAND_DESKTOP_ASSETS", "KILIX_ICEWM_STORAGE_HOME",
    "KILIX_ICEWM_PREFIX", "KILIX_TUI_UTILS_PREFIX", "KILIX_DESKTOP_DIR",
    "KILIX_RECYCLE_DIR", "KILIX_DESKTOP_CONTRACT_COMMAND",
    "PYTHONDONTWRITEBYTECODE",
)
E3_BRANCH_LABELS = (
    "version", "describe", "check", "config-schema", "config-get",
    "config-set", "config-set-unavailable", "screenshot",
    "screenshot-unavailable", "migration-gate", "migration-dry-run",
    "read-only-endpoints",
)
E3_CAMPAIGNS = (
    "common-matrix",
    "CHN-01-through-CHN-06-for-every-intentional-child",
    "hostile-cwd-and-environment-for-three-python-providers",
    "two-independent-disposable-exports",
    "two-final-mode-provider-passes",
)
E3_PROVIDER_FIXTURES = (
    (
        "kilix-95",
        "f110.provider.kilix-95/v1",
        "daf4e3aa4f7be9708fd026110c2f7de180c0a1ec",
        "f1f659e2e6c8beb41d5ddfb08a17ddce93ee4dca",
        "da69c4c170a0b097e545479eb9ad7d504957e1847e6ffd08322aa1e7e0ab15f6",
        ("version", "describe", "check", "config-schema", "config-get", "config-set", "screenshot", "migration-dry-run", "read-only-endpoints"),
    ),
    (
        "kilix-cap",
        "f110.provider.kilix-cap/v1",
        "7cc98eece67f9b6547d5fb0149d483117721a5cf",
        "720cf436517157d35112b2aab2ce3e2e81c97efd",
        "4493e11b8817b5d9f6cc820e8580e5dd677927b72ab9381b60195b8dbbc7854d",
        ("version", "describe", "check", "config-schema", "config-get", "config-set", "screenshot-unavailable", "migration-dry-run", "read-only-endpoints"),
    ),
    (
        "kilix-land-desktop",
        "f110.provider.kilix-land-desktop/v1",
        "c0594aeb955352b904f006fed4c9774e496a2d38",
        "394ccac938a1738b30be56f742d0fabd0f3ea610",
        "aee55e67f65289630c4e17b1becb85d19abac8b2d43ef6f8288d4bb1086dec75",
        ("version", "describe", "check", "config-schema", "config-get", "config-set", "screenshot", "migration-dry-run", "read-only-endpoints"),
    ),
    (
        "kilix-tui",
        "f110.provider.kilix-tui/v1",
        "63187ee199aa16f71a460ef0e95ec876bee8b787",
        "3387e4305ba7ad840602dfadd5caf04e3949259a",
        "d3da3a50337bce28eaa8419daf7af441249672dac2f8b97534099bfca38a1277",
        ("version", "describe", "check", "config-schema", "config-get", "config-set", "screenshot", "migration-dry-run", "read-only-endpoints"),
    ),
    (
        "kilix-icewm",
        "f110.provider.kilix-icewm/v1",
        "ea45b9abf13688154fdb4146cdfa4ffdef4399f1",
        "c08eec603dfb400d35bd29272a4d7e4e1b42d9c3",
        "89bcbf1cdad30043b7d8a4b455fc0d78c746f600633915ad4fbaa0a5933f7a12",
        ("version", "describe", "check", "config-schema", "config-get", "config-set", "screenshot-unavailable", "migration-dry-run", "read-only-endpoints"),
    ),
)
E4_COMMAND_TEMPLATES = (
    "storage authority",
    "storage path PROVIDER CATEGORY",
    "storage schema PROVIDER",
    "storage get PROVIDER [KEY]",
    "storage value PROVIDER KEY",
    "storage set PROVIDER KEY VALUE",
    "storage policy-path",
    "storage policy get [KEY]",
    "storage policy value KEY",
    "storage policy set KEY VALUE",
    "storage shared-settings get",
    "storage shared-settings update CHANGES_JSON",
    "storage migrate PROVIDER --from VERSION --dry-run",
    "storage migrate PROVIDER --from VERSION",
    "storage rollback --from VERSION",
)
E4_OBSERVATIONS = (
    "dry-run-side-effects-zero",
    "legacy-authority-through-first-three-migration-members",
    "xdg-authority-only-after-kilix-95",
    "legacy-bytes-unchanged",
    "configuration-fingerprint-preserved",
    "rollback-restores-legacy-authority",
    "rollback-retains-inert-xdg-payload",
)
E4_SEQUENCE = (
    ("migrate-dry-run", "kilix-land-desktop", "0.1.0"),
    ("migrate-dry-run", "kilix-tui", "0.3.1"),
    ("migrate-dry-run", "kilix-cap", "3.0.0"),
    ("migrate-dry-run", "kilix-95", "0.2.0"),
    ("migrate", "kilix-land-desktop", "0.1.0"),
    ("migrate", "kilix-tui", "0.3.1"),
    ("migrate", "kilix-cap", "3.0.0"),
    ("migrate", "kilix-95", "0.2.0"),
    ("rollback", None, "0.2.0"),
)
PROFILE_SCHEMA = "kilix.trusted-launcher.profile/v1"
PROFILE_ADOPTION_STATE = "construction-inputs-only-upstream-review-pending"
E1_PROFILE = {
    "argument_mode": "forbidden",
    "command_name": "qualify",
    "freeze_legs": [
        {
            "child_id": "freeze-1",
            "child_kind": "python-script",
            "child_profile_id": "f110.contract-freeze.freeze-1/v1",
        },
        {
            "child_id": "freeze-2",
            "child_kind": "python-script",
            "child_profile_id": "f110.contract-freeze.freeze-2/v1",
        },
    ],
    "post_child_verification": "required-after-every-child",
    "profile_id": "f110.contract-freeze/v1",
    "subject_entry": {"path": "validate_contract.py", "root": "subject"},
}
E3_PROFILE_CHILDREN = (
    ("python-script", "f110.provider.kilix-95/v1", "provider-kilix-95"),
    ("native-executable", "f110.provider.kilix-cap/v1", "provider-kilix-cap"),
    (
        "native-executable",
        "f110.provider.kilix-land-desktop/v1",
        "provider-kilix-land-desktop",
    ),
    ("python-script", "f110.provider.kilix-tui/v1", "provider-kilix-tui"),
    (
        "python-script",
        "f110.provider.kilix-icewm/v1",
        "provider-kilix-icewm",
    ),
    ("python-module", "f110.installed-command/v1", "installed-contract-command"),
)
PROFILE_INTERFACE_CONTROLS = (
    "canonical-duplicate-free-profile-json",
    "closed-profile-command-and-child-members",
    "data-driven-child-table-without-profile-id-branches",
    "exact-retained-root-and-path-bindings",
    "closed-environment-and-typed-argv",
    "descriptor-bound-python-and-native-provider-execution",
    "installed-distribution-record-bound-before-import",
    "result-writer-unavailable-before-any-subject-descendant",
    "post-child-authority-subject-runtime-dependency-verification",
    "ordered-child-terminal-set-digest",
    "one-bounded-canonical-outer-result",
    "exact-profile-and-result-schema-digests",
)
F119_ADAPTER_KINDS = ("unittest", "plain-assert", "shell", "make")
F119_CONSUMER_INVARIANTS = (
    "anonymous-transport-with-null-path",
    "kernel-type-attested-before-subject-start",
    "adapter-retains-only-reader",
    "launcher-receives-only-writer",
    "adapter-writer-copy-closed-before-subject",
    "subject-and-descendants-receive-zero-channel-access",
    "one-bounded-canonical-record",
    "descendants-writers-eof-and-launcher-final-before-grade",
    "grade-direct-bounded-in-memory-bytes",
    "persistent-copy-never-authoritative",
)
F119_PHASE_IDS = tuple(f"CH-{ordinal:02d}" for ordinal in range(1, 13))
F119_TRANSITION_IDS = tuple(f"CT-{ordinal:02d}" for ordinal in range(1, 12))
F119_DISPOSITION_IDS = tuple(f"CD-{ordinal:02d}" for ordinal in range(1, 7))
F119_ADDITIVE_GROUP_IDS = tuple(f"OD20-A{ordinal:02d}" for ordinal in range(1, 13))
F119_R3_FIELD_MAPPINGS = (
    "id:transport.object_identity",
    "writer_identity:writer_endpoint.holder",
    "bounded_bytes:bounds.max_bytes",
    "records_seen:terminal_record.records_seen",
    "unique_to_run:transport.unique_to_run",
    "descendant_writable:writer_endpoint.descendant_inheritable-inverse",
)
F119_REQUIRED_FIELDS = (
    "schema", "run_id", "case_id", "adapter", "subject_uid", "creator_uid",
    "transport", "writer_endpoint", "reader_endpoint", "subject_access",
    "bounds", "terminal_record", "finality", "grade_source",
    "persistent_capture", "kernel_attestation", "handoff", "od20",
)
F119_PREPARATION_ARTIFACTS = {
    "adapter_handoff_sha256": "7d687df52d7b910d18d33b54d71743903bd13f9d735e84ee8e232fb8815618c1",
    "packet_manifest_sha256": "7589fe45120192a6f937ab17442fd23b2603638b7b67facd569a4727391f56a3",
    "readiness_record_sha256": "46b6fd213e4909f8a9354ef9f40ad9ec88bedcc4b4595a1929e2eeb8da69a0a3",
    "result_channel_schema_sha256": "f65b092332fadb05dbbba29a7d45bbeaf808b4eda7e891eefa797dd325edf11e",
    "schema_adapter_delta_sha256": "aa90d728623d47b53c7a92bb4091ec85cf39512799553b5e6e059dc5ab550efe",
}
F119_R5_EXECUTABLE_PREPARATION = {
    "adapter_plans": {"denominator": 4, "numerator": 4},
    "adoption_state": "preparation-only-formal-entry-blocked",
    "anonymous_result_channels": {"denominator": 12, "numerator": 12},
    "authority_bindings": {"denominator": 9, "numerator": 9},
    "common_cli_options": {"denominator": 6, "numerator": 6},
    "corrected_selftest": {"denominator": 40, "numerator": 40},
    "execution_phases": {"denominator": 17, "numerator": 17},
    "formal_adapters_implemented": {"denominator": 4, "numerator": 0},
    "formal_p1_entered": {"denominator": 1, "numerator": 0},
    "formal_schema_freezes": {"denominator": 2, "numerator": 0},
    "formal_vectors_executed": {"denominator": 84, "numerator": 0},
    "leak_survivors": {"denominator": 1, "numerator": 0},
    "negative_execution_controls": {"denominator": 5, "numerator": 5},
    "packet_manifest_sha256": "baeccf5b7cf2b138eb6c30b55d22e75793297e7989f058b987f750c46d93d7cf",
    "positive_adapter_executions": {"denominator": 8, "numerator": 8},
    "preparation_record_sha256": "3bec924011be0da5b5876aad7bb4a39c3b409c0a91f0109c425dff05aba426db",
    "reference_runner_sha256": "4b51815f253bae6823fc449779dae61f4149ee1369b7cb6bbcdee6c1b194eb4e",
    "regular_file_negative_subject_starts": {"denominator": 1, "numerator": 0},
    "report_sha256": "cedd565f1dfc1e1a84853636999b0749add5eca02229ad690b1601956b4be1f0",
    "runner_contract_sha256": "ce73bf52113881283fc4f88465052e528c7aa61cfbdb4b6619e1f04eb50a55d8",
    "runtime_capture_files": {"denominator": 0, "numerator": 0},
    "timeout_survivors": {"denominator": 1, "numerator": 0},
}
E1_PARENT = {
    "commit": "b34fa9b85cad80cbfb33588378fac50f7fda21d3",
    "inner_manifest_members": 49,
    "outer_regular_files": 50,
    "tree": "83fbb08934367c79120177dae5d095e373346c9f",
    "version": "1.0.0rc1",
}
E2_LOCAL = {
    "commit": "014e55b9b3fc40774b2558aca9395abef9a9d546",
    "focused_tests": {"passed": 111, "population": 112, "skipped": 1},
    "patch_sha256": "ec6b7cee53f1b3c4e5b31c41b29991020364623ae40fbf4f9bfbba08acb05bdd",
    "publication": "owner-integrated-local-only-not-live-authority",
    "request_commit": "6facfadba8d730302da2e8577683096a875c282e",
    "stable_patch_id": "8fe0aa3fce380694597c854e8cc73c6806cf408e",
    "tree": "68618b9235d825ca14e6537ae74fe2fc5f1fded7",
}
E4_LOCAL = {
    "cleanup_probes": {"passing": 1, "population": 1},
    "config_fingerprint_sha256": "be04fc889a170e4295caebcc847f2b29b6867ca2ed1eb82f48a50507d4805111",
    "contract_commit": "5767b0442add4b83694008580e4cdc57f43508ac",
    "dry_run_members": {"passing": 4, "population": 4},
    "final_authority": "legacy",
    "inert_xdg_payload_sha256": "0bd925df41d2ec51fa21dd2a1a53c13e0d9b8474d72a9e7d7010c1b2b3a1c36e",
    "legacy_bundle_sha256": "32c8c79021508e44c8b3794e82bda64231181521e777ec5b8795641328c1fb47",
    "migration_members": {"passing": 4, "population": 4},
    "observations": {"passing": 7, "population": 7},
    "publication": "isolated-local-rehearsal-not-live-authority",
    "rollback": {"passing": 1, "population": 1},
    "source_snapshot": {"bytes": 167866372, "files": 3576},
}


class ReadinessError(ValueError):
    """The owned requirements cannot safely consume an upstream return."""


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        observed = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ReadinessError(
            f"{label}: expected keys {sorted(keys)}, observed {observed}"
        )
    return value


def load_requirements(path: Path = DEFAULT_REQUIREMENTS) -> dict[str, Any]:
    try:
        value = load_json(path)
    except (DocumentError, OSError) as error:
        raise ReadinessError(f"{path}: invalid requirements: {error}") from error
    if not isinstance(value, dict):
        raise ReadinessError("requirements: top level is not an object")
    if path.read_bytes() != canonical_bytes(value):
        raise ReadinessError(f"{path}: requirements are not canonical JSON")
    return value


def load_command_set(
    path: Path, requirements: dict[str, Any]
) -> tuple[MatrixProvider, ...]:
    try:
        value = load_json(path)
    except (DocumentError, OSError) as error:
        raise ReadinessError(f"{path}: invalid command set: {error}") from error
    if path.read_bytes() != canonical_bytes(value):
        raise ReadinessError(f"{path}: command set is not canonical JSON")
    document = _object(value, {"commands", "schema"}, "command_set")
    if document["schema"] != COMMAND_SET_SCHEMA:
        raise ReadinessError("command_set: schema identity changed")
    expected = requirements["consumer_requirements"][0]["providers"]
    commands = document["commands"]
    if not isinstance(commands, list) or len(commands) != len(expected):
        raise ReadinessError(
            f"command_set: provider population is not {len(expected)}"
        )
    result: list[MatrixProvider] = []
    for ordinal, (item, provider) in enumerate(
        zip(commands, expected, strict=True), start=1
    ):
        command_item = _object(
            item,
            {
                "command", "entry_path", "entry_sha256", "provider_id",
                "source_commit", "source_root", "source_tree",
            },
            f"command_set provider {ordinal}",
        )
        provider_id = provider["provider_id"]
        if command_item["provider_id"] != provider_id:
            raise ReadinessError(
                f"command_set provider {ordinal}: expected {provider_id}"
            )
        if command_item["source_commit"] != provider["commit"]:
            raise ReadinessError(
                f"command_set provider {ordinal}: source commit changed"
            )
        if command_item["source_tree"] != provider["tree"]:
            raise ReadinessError(
                f"command_set provider {ordinal}: source tree changed"
            )
        if command_item["entry_sha256"] != provider["entry_sha256"]:
            raise ReadinessError(
                f"command_set provider {ordinal}: entry digest changed"
            )
        command = command_item["command"]
        if (
            not isinstance(command, list)
            or not command
            or any(
                not isinstance(value, str) or not value or "\0" in value
                for value in command
            )
            or not Path(command[0]).is_absolute()
        ):
            raise ReadinessError(
                f"command_set provider {ordinal}: command must start with an absolute executable"
            )
        entry_path_value = command_item["entry_path"]
        if (
            not isinstance(entry_path_value, str)
            or not entry_path_value
            or "\0" in entry_path_value
            or not Path(entry_path_value).is_absolute()
            or command.count(entry_path_value) != 1
        ):
            raise ReadinessError(
                f"command_set provider {ordinal}: entry path is not one exact command member"
            )
        entry_path = Path(entry_path_value)
        try:
            entry_path.lstat()
            entry_digest = hashlib.sha256(entry_path.read_bytes()).hexdigest()
        except OSError as error:
            raise ReadinessError(
                f"command_set provider {ordinal}: cannot read entry: {error}"
            ) from error
        if entry_path.is_symlink() or not entry_path.is_file():
            raise ReadinessError(
                f"command_set provider {ordinal}: entry is not a regular non-symlink"
            )
        if entry_digest != command_item["entry_sha256"]:
            raise ReadinessError(
                f"command_set provider {ordinal}: entry bytes changed"
            )
        source_root_value = command_item["source_root"]
        if (
            not isinstance(source_root_value, str)
            or not source_root_value
            or "\0" in source_root_value
            or not Path(source_root_value).is_absolute()
        ):
            raise ReadinessError(
                f"command_set provider {ordinal}: source root is not absolute"
            )
        matrix_provider = MatrixProvider(
            provider_id,
            tuple(command),
            tuple(provider["expected_checks"]),
            entry_path,
            entry_digest,
            Path(source_root_value),
            command_item["source_commit"],
            command_item["source_tree"],
        )
        try:
            verify_matrix_provider(matrix_provider, "while loading command set")
        except ConformanceError as error:
            raise ReadinessError(
                f"command_set provider {ordinal}: {error}"
            ) from error
        result.append(matrix_provider)
    return tuple(result)


def _validate_upstream(value: Any) -> None:
    gate = _object(
        value,
        {
            "accepted_result_states", "assignments", "blocked_result_states",
            "common_case_ids", "consumed_return_identities",
            "independent_exports", "required_return_identities", "state",
        },
        "upstream_gate",
    )
    if gate["accepted_result_states"] != ["PASS", "REFUSED-AS-NAMED"]:
        raise ReadinessError("upstream_gate: accepted result states changed")
    if gate["blocked_result_states"] != ["NULL", "HARNESS-FAIL"]:
        raise ReadinessError("upstream_gate: blocked result states changed")
    if tuple(gate["common_case_ids"]) != COMMON_CASES:
        raise ReadinessError("upstream_gate: common case population changed")
    if tuple(gate["required_return_identities"]) != RETURN_IDENTITIES:
        raise ReadinessError("upstream_gate: required identity population changed")
    if gate["consumed_return_identities"] != []:
        raise ReadinessError("upstream_gate: unreturned identities were consumed")
    if gate["independent_exports"] != {"passing": 2, "population": 2}:
        raise ReadinessError("upstream_gate: independent export requirement changed")
    if gate["state"] != "blocked-upstream-returns-not-accepted":
        raise ReadinessError("upstream_gate: an assignment was promoted without a result")
    expected_assignments = [
        {
            "decision_id": "OD-13",
            "owner": "reviewer2",
            "state": "component-returned-release-integration-blocked",
            "work": "ID-04-facility-implementation",
        },
        {
            "construction_commit": "debff369aea2fc98b11c338ea973c93326a16b40",
            "construction_ref": "refs/heads/work/0.2.1-f120-profile-interface",
            "construction_tree": "9ac05d8226d23c849c0b6bb2b0a2a19ebf7b3b61",
            "decision_id": "OD-14",
            "owner": "Track H",
            "state": "correction-published-independent-review-pending",
            "work": "non-forking-profile-child-table-interface",
        },
    ]
    if gate["assignments"] != expected_assignments:
        raise ReadinessError("upstream_gate: OD-13/OD-14 assignment boundary changed")


def _validate_launcher_profiles(value: Any) -> None:
    profiles = _object(
        value,
        {
            "adoption_state", "e1_profile", "e3_profile", "interface_controls",
            "profile_schema", "top_level_profile_count",
        },
        "launcher_profile_requirements",
    )
    if profiles["adoption_state"] != PROFILE_ADOPTION_STATE:
        raise ReadinessError("launcher profiles: construction was promoted without review")
    if profiles["profile_schema"] != PROFILE_SCHEMA:
        raise ReadinessError("launcher profiles: upstream profile schema changed")
    if profiles["top_level_profile_count"] != 2:
        raise ReadinessError("launcher profiles: top-level profile population changed")
    if profiles["e1_profile"] != E1_PROFILE:
        raise ReadinessError("launcher profiles: E1 profile input changed")
    e3 = _object(
        profiles["e3_profile"],
        {
            "argument_mode", "check_occurrences_total", "child_profiles",
            "command_name", "passes", "post_child_verification", "profile_id",
            "provider_invocations",
        },
        "launcher profiles E3",
    )
    if (
        e3["argument_mode"],
        e3["command_name"],
        e3["passes"],
        e3["post_child_verification"],
        e3["profile_id"],
        e3["provider_invocations"],
        e3["check_occurrences_total"],
    ) != (
        "forbidden",
        "qualify",
        2,
        "required-after-every-child",
        "f110.installed-conformance/v1",
        10,
        90,
    ):
        raise ReadinessError("launcher profiles: E3 aggregate profile changed")
    children = e3["child_profiles"]
    if not isinstance(children, list) or len(children) != len(E3_PROFILE_CHILDREN):
        raise ReadinessError("launcher profiles: E3 child-table population changed")
    observed = []
    for ordinal, child in enumerate(children, start=1):
        item = _object(
            child,
            {"child_kind", "child_profile_id", "surface_id"},
            f"launcher profiles E3 child {ordinal}",
        )
        observed.append(
            (item["child_kind"], item["child_profile_id"], item["surface_id"])
        )
    if tuple(observed) != E3_PROFILE_CHILDREN:
        raise ReadinessError("launcher profiles: E3 child-table mapping changed")
    if tuple(profiles["interface_controls"]) != PROFILE_INTERFACE_CONTROLS:
        raise ReadinessError("launcher profiles: interface-control population changed")


def _validate_f119_result_channel(value: Any) -> None:
    channel = _object(
        value,
        {
            "adapter_kinds", "adoption_state", "candidate_schema",
            "consumer_invariants", "formal_state", "handoff_contract_id",
            "handoff_phase_ids", "launcher_result_fd",
            "od20_additive_group_ids", "od20_authority",
            "preparation_artifacts", "r3_field_mappings",
            "r5_executable_preparation",
            "required_top_level_fields", "schema", "success_transition_ids",
            "terminal_disposition_ids", "transport_kinds",
        },
        "f119_result_channel_requirements",
    )
    if channel["schema"] != "kilix.track-e.f119-result-channel-consumer/v1":
        raise ReadinessError("F119 channel: consumer schema changed")
    if channel["adoption_state"] != "preparation-only-accepted-return-pending":
        raise ReadinessError("F119 channel: preparation was promoted without acceptance")
    if channel["candidate_schema"] != "kilix.test.od20-result-channel/v1":
        raise ReadinessError("F119 channel: preparation schema identity changed")
    if tuple(channel["adapter_kinds"]) != F119_ADAPTER_KINDS:
        raise ReadinessError("F119 channel: adapter population changed")
    if tuple(channel["consumer_invariants"]) != F119_CONSUMER_INVARIANTS:
        raise ReadinessError("F119 channel: consumer invariant population changed")
    if tuple(channel["required_top_level_fields"]) != F119_REQUIRED_FIELDS:
        raise ReadinessError("F119 channel: required field population changed")
    if tuple(channel["r3_field_mappings"]) != F119_R3_FIELD_MAPPINGS:
        raise ReadinessError("F119 channel: R3 field mapping changed")
    if tuple(channel["od20_additive_group_ids"]) != F119_ADDITIVE_GROUP_IDS:
        raise ReadinessError("F119 channel: OD-20 additive population changed")
    if tuple(channel["handoff_phase_ids"]) != F119_PHASE_IDS:
        raise ReadinessError("F119 channel: handoff phase population changed")
    if tuple(channel["success_transition_ids"]) != F119_TRANSITION_IDS:
        raise ReadinessError("F119 channel: handoff transition population changed")
    if tuple(channel["terminal_disposition_ids"]) != F119_DISPOSITION_IDS:
        raise ReadinessError("F119 channel: terminal disposition population changed")
    if channel["transport_kinds"] != ["anonymous_pipe", "unnamed_socketpair"]:
        raise ReadinessError("F119 channel: anonymous transport population changed")
    if channel["handoff_contract_id"] != "kilix.f119.adapter-channel-handoff/v1":
        raise ReadinessError("F119 channel: handoff contract identity changed")
    if channel["launcher_result_fd"] != {
        "owner": "Track A / F100 accepted launcher profile",
        "returned": {"denominator": 1, "numerator": 0},
        "value": None,
    }:
        raise ReadinessError("F119 channel: unreturned F100 result descriptor consumed")
    if channel["formal_state"] != {
        "adapters_implemented": {"denominator": 4, "numerator": 0},
        "p1_entered": {"denominator": 1, "numerator": 0},
        "schema_freezes": {"denominator": 2, "numerator": 0},
        "vectors_executed": {"denominator": 84, "numerator": 0},
    }:
        raise ReadinessError("F119 channel: formal state was overstated")
    if channel["od20_authority"] != {
        "authority_id": "OD-20",
        "owner_decision_sha256": "b7c70acba32ca74518868e894330c6c8158f4436765d0a556a258fe4c4f1de3e",
        "ratification_status": "RATIFIED_AS_FILED",
    }:
        raise ReadinessError("F119 channel: OD-20 authority binding changed")
    if channel["preparation_artifacts"] != F119_PREPARATION_ARTIFACTS:
        raise ReadinessError("F119 channel: preparation artifact identity changed")
    if channel["r5_executable_preparation"] != F119_R5_EXECUTABLE_PREPARATION:
        raise ReadinessError("F119 channel: R5 executable preparation changed")


def _validate_e3(value: Any) -> None:
    e3 = _object(
        value,
        {
            "absolute_bindings", "campaigns", "check_occurrences_per_pass",
            "check_occurrences_total", "child_profile_ids", "passes",
            "post_child_verification", "profile_id", "provider_environment_names",
            "provider_invocations", "providers", "requirement_id", "surface_ids",
            "terminal_branch_labels",
        },
        "TE-E3",
    )
    if e3["requirement_id"] != "TE-E3" or e3["profile_id"] != "f110.installed-conformance/v1":
        raise ReadinessError("TE-E3: requirement or top-level profile identity changed")
    if tuple(e3["surface_ids"]) != E3_SURFACES:
        raise ReadinessError("TE-E3: seven-surface population changed")
    if tuple(e3["campaigns"]) != E3_CAMPAIGNS:
        raise ReadinessError("TE-E3: campaign population changed")
    if tuple(e3["child_profile_ids"]) != E3_CHILD_PROFILES:
        raise ReadinessError("TE-E3: six-child-profile population changed")
    if tuple(e3["provider_environment_names"]) != E3_ENVIRONMENT_NAMES:
        raise ReadinessError("TE-E3: 39-name provider environment changed")
    if tuple(e3["terminal_branch_labels"]) != E3_BRANCH_LABELS:
        raise ReadinessError("TE-E3: twelve-label branch population changed")
    if e3["absolute_bindings"] != [
        {"environment_name": "KILIX_HOME", "token": "H"},
        {"environment_name": "KILIX_DESKTOP_CONTRACT_COMMAND", "token": "C"},
        {"environment_name": "KILIX_STATE_LIBRARY", "token": "S"},
        {"environment_name": "KILIX_LAND_DESKTOP_ASSETS", "token": "L"},
    ]:
        raise ReadinessError("TE-E3: H/C/S/L binding population changed")
    if (e3["passes"], e3["provider_invocations"], e3["check_occurrences_per_pass"], e3["check_occurrences_total"]) != (2, 10, 45, 90):
        raise ReadinessError("TE-E3: two-pass/ten-invocation/ninety-check denominator changed")
    if e3["post_child_verification"] != "required-after-every-child":
        raise ReadinessError("TE-E3: post-child verification weakened")
    providers = e3["providers"]
    if not isinstance(providers, list) or len(providers) != 5:
        raise ReadinessError("TE-E3: provider population is not five")
    for ordinal, (provider, expected) in enumerate(
        zip(providers, E3_PROVIDER_FIXTURES, strict=True), start=1
    ):
        item = _object(
            provider,
            {
                "child_profile_id", "commit", "entry_sha256", "expected_checks",
                "provider_id", "tree",
            },
            f"TE-E3 provider {ordinal}",
        )
        provider_id, profile_id, commit, tree, entry_sha256, checks = expected
        observed = (
            item["provider_id"], item["child_profile_id"], item["commit"],
            item["tree"], item["entry_sha256"], tuple(item["expected_checks"]),
        )
        if observed != (
            provider_id, profile_id, commit, tree, entry_sha256, checks
        ):
            raise ReadinessError(f"TE-E3 provider {ordinal}: exact fixture changed")
    if sum(len(provider["expected_checks"]) for provider in providers) != 45:
        raise ReadinessError("TE-E3: one-pass check occurrence population is not 45")


def _validate_e4(value: Any) -> None:
    e4 = _object(
        value,
        {
            "child_profile_id", "command_templates", "migration_members",
            "migration_sequence", "post_child_verification", "profile_relation",
            "required_observations", "requirement_id", "separate_consumers",
        },
        "TE-E4",
    )
    if e4["requirement_id"] != "TE-E4":
        raise ReadinessError("TE-E4: requirement identity changed")
    if e4["child_profile_id"] != "f110.installed-command/v1":
        raise ReadinessError("TE-E4: installed-command child profile changed")
    if e4["profile_relation"] != "reuses-installed-command-child-not-a-third-top-level-profile":
        raise ReadinessError("TE-E4: a third top-level profile was introduced")
    if tuple(e4["command_templates"]) != E4_COMMAND_TEMPLATES:
        raise ReadinessError("TE-E4: fifteen-command template population changed")
    if tuple(e4["migration_members"]) != MIGRATION_ORDER:
        raise ReadinessError("TE-E4: four-member migration order changed")
    if tuple(e4["separate_consumers"]) != SEPARATE_CONSUMERS:
        raise ReadinessError("TE-E4: separate-consumer population changed")
    sequence = e4["migration_sequence"]
    if not isinstance(sequence, list) or len(sequence) != 9:
        raise ReadinessError("TE-E4: migration/rollback sequence is not nine")
    expected_sequence = []
    for order, (operation, provider_id, source_version) in enumerate(
        E4_SEQUENCE, start=1
    ):
        item = {
            "operation": operation,
            "order": order,
            "source_version": source_version,
        }
        if provider_id is not None:
            item["provider_id"] = provider_id
        expected_sequence.append(item)
    if sequence != expected_sequence:
        raise ReadinessError("TE-E4: exact dry-run/migrate/rollback sequence changed")
    if tuple(e4["required_observations"]) != E4_OBSERVATIONS:
        raise ReadinessError("TE-E4: seven-observation population changed")
    if e4["post_child_verification"] != "required-after-every-command":
        raise ReadinessError("TE-E4: post-command verification weakened")


def validate_requirements(value: Any) -> None:
    document = _object(
        value,
        {
            "consumer_requirements", "f119_result_channel_requirements",
            "launcher_profile_requirements", "local_evidence", "schema",
            "status", "upstream_gate",
        },
        "requirements",
    )
    if document["schema"] != SCHEMA:
        raise ReadinessError("requirements: schema identity changed")
    if document["status"] != STATUS:
        raise ReadinessError("requirements: readiness-only disclaimer changed")
    consumers = document["consumer_requirements"]
    if not isinstance(consumers, list) or len(consumers) != 2:
        raise ReadinessError("requirements: consumer population is not two")
    _validate_e3(consumers[0])
    _validate_e4(consumers[1])
    _validate_f119_result_channel(document["f119_result_channel_requirements"])
    _validate_launcher_profiles(document["launcher_profile_requirements"])
    local = _object(
        document["local_evidence"],
        {"e1_parent", "e2_host_integration", "e4_installed_state_rehearsal"},
        "local_evidence",
    )
    if local["e1_parent"] != E1_PARENT:
        raise ReadinessError("local_evidence: E1 parent identity changed")
    if local["e2_host_integration"] != E2_LOCAL:
        raise ReadinessError("local_evidence: E2 local integration changed")
    if local["e4_installed_state_rehearsal"] != E4_LOCAL:
        raise ReadinessError("local_evidence: E4 rehearsal evidence changed")
    _validate_upstream(document["upstream_gate"])


def _mutations() -> list[Callable[[dict[str, Any]], None]]:
    def r5(key: str, replacement: Any) -> Callable[[dict[str, Any]], None]:
        return lambda value: value["f119_result_channel_requirements"][
            "r5_executable_preparation"
        ].__setitem__(key, replacement)

    return [
        lambda value: value["upstream_gate"]["common_case_ids"].pop(),
        lambda value: value["upstream_gate"].__setitem__("state", "accepted"),
        lambda value: value["upstream_gate"]["assignments"][1].__setitem__("construction_commit", "0" * 40),
        lambda value: value["consumer_requirements"][0]["providers"].pop(),
        lambda value: value["consumer_requirements"][0]["providers"][0].__setitem__("entry_sha256", "0" * 64),
        lambda value: value["consumer_requirements"][0]["provider_environment_names"].pop(),
        lambda value: value["consumer_requirements"][1]["migration_sequence"].reverse(),
        lambda value: value["consumer_requirements"].append({"requirement_id": "TE-E5"}),
        lambda value: value["launcher_profile_requirements"].__setitem__("adoption_state", "accepted"),
        lambda value: value["launcher_profile_requirements"].__setitem__("profile_schema", "kilix.trusted-launcher.profile/v2"),
        lambda value: value["launcher_profile_requirements"].__setitem__("top_level_profile_count", 3),
        lambda value: value["launcher_profile_requirements"]["e1_profile"].__setitem__("profile_id", "f110.contract-freeze/v2"),
        lambda value: value["launcher_profile_requirements"]["e1_profile"]["freeze_legs"].pop(),
        lambda value: value["launcher_profile_requirements"]["e1_profile"].__setitem__("post_child_verification", "after-all-children"),
        lambda value: value["launcher_profile_requirements"]["e3_profile"].__setitem__("profile_id", "f110.installed-conformance/v2"),
        lambda value: value["launcher_profile_requirements"]["e3_profile"]["child_profiles"].pop(),
        lambda value: value["launcher_profile_requirements"]["e3_profile"]["child_profiles"][1].__setitem__("child_kind", "python-script"),
        lambda value: value["launcher_profile_requirements"]["interface_controls"].pop(),
        lambda value: value["f119_result_channel_requirements"].__setitem__("adoption_state", "accepted"),
        lambda value: value["f119_result_channel_requirements"].__setitem__("candidate_schema", "kilix.test.od20-result-channel/v2"),
        lambda value: value["f119_result_channel_requirements"]["consumer_invariants"].pop(),
        lambda value: value["f119_result_channel_requirements"]["formal_state"]["adapters_implemented"].__setitem__("numerator", 1),
        lambda value: value["f119_result_channel_requirements"]["formal_state"]["p1_entered"].__setitem__("numerator", 1),
        lambda value: value["f119_result_channel_requirements"]["handoff_phase_ids"].pop(),
        lambda value: value["f119_result_channel_requirements"]["launcher_result_fd"]["returned"].__setitem__("numerator", 1),
        lambda value: value["f119_result_channel_requirements"]["od20_additive_group_ids"].pop(),
        lambda value: value["f119_result_channel_requirements"]["preparation_artifacts"].__setitem__("readiness_record_sha256", "0" * 64),
        lambda value: value["f119_result_channel_requirements"]["r3_field_mappings"].pop(),
        lambda value: value["f119_result_channel_requirements"]["required_top_level_fields"].pop(),
        lambda value: value["f119_result_channel_requirements"]["success_transition_ids"].pop(),
        lambda value: value["f119_result_channel_requirements"]["terminal_disposition_ids"].pop(),
        lambda value: value["f119_result_channel_requirements"]["transport_kinds"].pop(),
        lambda value: value["f119_result_channel_requirements"]["adapter_kinds"].pop(),
        r5("adapter_plans", {"denominator": 4, "numerator": 3}),
        r5("adoption_state", "accepted"),
        r5("anonymous_result_channels", {"denominator": 12, "numerator": 11}),
        r5("authority_bindings", {"denominator": 9, "numerator": 8}),
        r5("common_cli_options", {"denominator": 6, "numerator": 5}),
        r5("corrected_selftest", {"denominator": 40, "numerator": 39}),
        r5("execution_phases", {"denominator": 17, "numerator": 16}),
        r5("formal_adapters_implemented", {"denominator": 4, "numerator": 1}),
        r5("formal_p1_entered", {"denominator": 1, "numerator": 1}),
        r5("formal_schema_freezes", {"denominator": 2, "numerator": 1}),
        r5("formal_vectors_executed", {"denominator": 84, "numerator": 1}),
        r5("leak_survivors", {"denominator": 1, "numerator": 1}),
        r5("negative_execution_controls", {"denominator": 5, "numerator": 4}),
        r5("packet_manifest_sha256", "0" * 64),
        r5("positive_adapter_executions", {"denominator": 8, "numerator": 7}),
        r5("preparation_record_sha256", "0" * 64),
        r5("reference_runner_sha256", "0" * 64),
        r5("regular_file_negative_subject_starts", {"denominator": 1, "numerator": 1}),
        r5("report_sha256", "0" * 64),
        r5("runner_contract_sha256", "0" * 64),
        r5("runtime_capture_files", {"denominator": 1, "numerator": 0}),
        r5("timeout_survivors", {"denominator": 1, "numerator": 1}),
        lambda value: value["local_evidence"]["e2_host_integration"].__setitem__("commit", "0" * 40),
        lambda value: value["local_evidence"]["e2_host_integration"]["focused_tests"].__setitem__("passed", 110),
        lambda value: value["local_evidence"]["e2_host_integration"]["focused_tests"].__setitem__("population", 113),
        lambda value: value["local_evidence"]["e2_host_integration"]["focused_tests"].__setitem__("skipped", 0),
        lambda value: value["local_evidence"]["e2_host_integration"].__setitem__("patch_sha256", "0" * 64),
        lambda value: value["local_evidence"]["e2_host_integration"].__setitem__("publication", "live-authority"),
        lambda value: value["local_evidence"]["e2_host_integration"].__setitem__("request_commit", "0" * 40),
        lambda value: value["local_evidence"]["e2_host_integration"].__setitem__("stable_patch_id", "0" * 40),
        lambda value: value["local_evidence"]["e2_host_integration"].__setitem__("tree", "0" * 40),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["cleanup_probes"].__setitem__("passing", 0),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["cleanup_probes"].__setitem__("population", 2),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"].__setitem__("config_fingerprint_sha256", "0" * 64),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"].__setitem__("contract_commit", "0" * 40),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["dry_run_members"].__setitem__("passing", 3),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["dry_run_members"].__setitem__("population", 5),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["observations"].__setitem__("passing", 6),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"].__setitem__("final_authority", "xdg"),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"].__setitem__("inert_xdg_payload_sha256", "0" * 64),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"].__setitem__("legacy_bundle_sha256", "0" * 64),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["migration_members"].__setitem__("passing", 3),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["migration_members"].__setitem__("population", 5),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["observations"].__setitem__("population", 8),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"].__setitem__("publication", "live-authority"),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["rollback"].__setitem__("passing", 0),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["rollback"].__setitem__("population", 2),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["source_snapshot"].__setitem__("bytes", 0),
        lambda value: value["local_evidence"]["e4_installed_state_rehearsal"]["source_snapshot"].__setitem__("files", 0),
    ]


def self_test(value: dict[str, Any]) -> tuple[int, int]:
    mutations = _mutations()
    rejected = 0
    for mutate in mutations:
        candidate = copy.deepcopy(value)
        mutate(candidate)
        try:
            validate_requirements(candidate)
        except ReadinessError:
            rejected += 1
    if rejected != len(mutations):
        raise ReadinessError(
            f"readiness self-test rejected {rejected}/{len(mutations)} mutations"
        )
    return rejected, len(mutations)


def summary(value: dict[str, Any], mutation_result: tuple[int, int] | None = None) -> str:
    e3, e4 = value["consumer_requirements"]
    channel = value["f119_result_channel_requirements"]
    profiles = value["launcher_profile_requirements"]
    gate = value["upstream_gate"]
    parts = [
        "PASS (developer readiness only; launcher adoption remains blocked)",
        f"{len(COMMON_CASES)}/{len(COMMON_CASES)} common cases retained",
        "2/2 consumer requirements retained",
        f"{len(e3['surface_ids'])}/{len(E3_SURFACES)} E3 surfaces retained",
        f"{len(e3['child_profile_ids'])}/{len(E3_CHILD_PROFILES)} E3 child profiles retained",
        f"{len(e3['provider_environment_names'])}/{len(E3_ENVIRONMENT_NAMES)} provider environment names retained",
        f"{len(e3['providers'])}/5 providers retained",
        f"{e3['provider_invocations']}/10 provider invocations retained",
        f"{e3['check_occurrences_total']}/90 check occurrences retained",
        f"{profiles['top_level_profile_count']}/2 top-level profile inputs retained",
        f"{len(profiles['e1_profile']['freeze_legs'])}/2 E1 freeze legs retained",
        f"{len(profiles['e3_profile']['child_profiles'])}/{len(E3_PROFILE_CHILDREN)} E3 child-table rows retained",
        f"{len({item['child_kind'] for item in profiles['e3_profile']['child_profiles']})}/3 E3 child kinds retained",
        f"{len(profiles['interface_controls'])}/{len(PROFILE_INTERFACE_CONTROLS)} launcher interface controls retained",
        f"{len(channel['required_top_level_fields'])}/{len(F119_REQUIRED_FIELDS)} F119 channel fields retained",
        f"{len(channel['r3_field_mappings'])}/{len(F119_R3_FIELD_MAPPINGS)} F119 R3 field mappings retained",
        f"{len(channel['od20_additive_group_ids'])}/{len(F119_ADDITIVE_GROUP_IDS)} OD-20 additive groups retained",
        f"{len(channel['adapter_kinds'])}/{len(F119_ADAPTER_KINDS)} F119 adapter kinds retained",
        f"{len(channel['handoff_phase_ids'])}/{len(F119_PHASE_IDS)} result-channel phases retained",
        f"{len(channel['success_transition_ids'])}/{len(F119_TRANSITION_IDS)} result-channel transitions retained",
        f"{len(channel['terminal_disposition_ids'])}/{len(F119_DISPOSITION_IDS)} channel dispositions retained",
        f"{len(channel['transport_kinds'])}/2 anonymous transports retained",
        f"{len(channel['consumer_invariants'])}/{len(F119_CONSUMER_INVARIANTS)} channel invariants retained",
        f"{channel['launcher_result_fd']['returned']['numerator']}/{channel['launcher_result_fd']['returned']['denominator']} F100 result-descriptor values consumed",
        "22/22 F119 R5 executable-preparation leaves retained",
        f"{channel['r5_executable_preparation']['anonymous_result_channels']['numerator']}/{channel['r5_executable_preparation']['anonymous_result_channels']['denominator']} R5 anonymous-channel executions retained",
        f"{len(e4['command_templates'])}/{len(E4_COMMAND_TEMPLATES)} E4 command templates retained",
        f"{len(e4['migration_sequence'])}/9 E4 migration/rollback commands retained",
        "9/9 E2 local-evidence leaves retained",
        "18/18 E4 local-evidence leaves retained",
        f"{E2_LOCAL['focused_tests']['passed']}/{E2_LOCAL['focused_tests']['population']} E2 focused tests passed",
        f"{E2_LOCAL['focused_tests']['skipped']}/{E2_LOCAL['focused_tests']['population']} E2 focused tests skipped as external-provider dependent",
        f"{E4_LOCAL['observations']['passing']}/{E4_LOCAL['observations']['population']} E4 observations retained",
        f"{len(gate['consumed_return_identities'])}/{len(RETURN_IDENTITIES)} upstream return identities consumed",
    ]
    if mutation_result is not None:
        parts.append(
            f"{mutation_result[0]}/{mutation_result[1]} premature-adoption mutations rejected"
        )
    return "; ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args(argv)
    value = load_requirements(arguments.requirements.resolve(strict=True))
    validate_requirements(value)
    mutations = self_test(value) if arguments.self_test else None
    print(summary(value, mutations))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ReadinessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
