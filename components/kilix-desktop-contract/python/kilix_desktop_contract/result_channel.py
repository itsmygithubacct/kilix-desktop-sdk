"""Validate F110's consumer view of the prepared F119 result channel.

This module does not construct the channel, choose the launcher descriptor, or
promote the preparation to an accepted schema.  It fails closed when direct
endpoint bytes do not satisfy the F110-bound R4 consumer requirement and when
an R6 result candidate's nested channel does not satisfy the authority-
independent OD-20 boundary.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .jsonio import canonical_bytes


SCHEMA = "kilix.test.od20-result-channel/v1"
ADAPTERS = ("unittest", "plain-assert", "shell", "make")
PHASE_IDS = tuple(f"CH-{ordinal:02d}" for ordinal in range(1, 13))
HANDOFF_CONTRACT = "kilix.f119.adapter-channel-handoff/v1"
OD20_DECISION_SHA256 = (
    "b7c70acba32ca74518868e894330c6c8158f4436765d0a556a258fe4c4f1de3e"
)
MAX_CHANNEL_BYTES = 1024 * 1024 * 1024
R6_RESULT_CHANNEL_FIELDS = (
    "authority_id", "kind", "path", "object_identity", "subject_uid",
    "creator_uid", "writer_identity", "reader_identity", "bounded_bytes",
    "records_seen", "unique_to_run", "descendant_writable",
    "pathname_reachable_by_subject_uid", "persistent_bytes", "grade_source",
    "persistent_copy_authority", "kernel_attested_before_subject",
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_OBJECT_IDENTITY = re.compile(r"^(pipe|socket):[a-z0-9][a-z0-9._-]{2,127}$")


class ResultChannelError(ValueError):
    """Direct result-channel bytes fail the prepared consumer requirement."""


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResultChannelError(f"{label} is not an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise ResultChannelError(
            f"{label} has wrong members (missing={missing}, extra={extra})"
        )
    return value


def _exact(value: Any, expected: dict[str, Any], label: str) -> None:
    observed = _closed(value, set(expected), label)
    if observed != expected:
        raise ResultChannelError(f"{label} has a nonconforming value")


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ResultChannelError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _trusted_bound(value: Any) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > MAX_CHANNEL_BYTES
    ):
        raise ResultChannelError(
            f"trusted_max_bytes must be an integer in 1..{MAX_CHANNEL_BYTES}"
        )
    return value


def parse_result_channel(
    payload: bytes, *, trusted_max_bytes: int
) -> dict[str, Any]:
    """Parse canonical bytes read directly from the anonymous endpoint.

    ``trusted_max_bytes`` is an outer launcher/adapter input.  The record's own
    bound is checked against it and never determines how much input is read.
    """

    trusted_bound = _trusted_bound(trusted_max_bytes)
    if not isinstance(payload, bytes):
        raise ResultChannelError("result-channel payload is not bytes")
    if not payload or len(payload) > trusted_bound:
        raise ResultChannelError(
            f"result-channel payload size is not in 1..{trusted_bound} bytes"
        )
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ResultChannelError("result-channel payload is not UTF-8") from error
    try:
        document = json.loads(text, object_pairs_hook=_reject_duplicates)
    except ResultChannelError:
        raise
    except json.JSONDecodeError as error:
        raise ResultChannelError(f"invalid result-channel JSON: {error}") from error
    if canonical_bytes(document) != payload:
        raise ResultChannelError("result-channel payload is not canonical JSON")
    return validate_result_channel(document, trusted_max_bytes=trusted_bound)


def validate_result_channel(
    value: Any, *, trusted_max_bytes: int
) -> dict[str, Any]:
    """Validate the 18-field F110 consumer envelope and its invariants."""

    trusted_bound = _trusted_bound(trusted_max_bytes)
    channel = _closed(
        value,
        {
            "schema", "run_id", "case_id", "adapter", "subject_uid",
            "creator_uid", "transport", "writer_endpoint", "reader_endpoint",
            "subject_access", "bounds", "terminal_record", "finality",
            "grade_source", "persistent_capture", "kernel_attestation",
            "handoff", "od20",
        },
        "result channel",
    )
    if channel["schema"] != SCHEMA:
        raise ResultChannelError("result channel has wrong schema")
    for name in ("run_id", "case_id"):
        if not isinstance(channel[name], str) or not _IDENTIFIER.fullmatch(channel[name]):
            raise ResultChannelError(f"result channel {name} is not an identifier")
    if channel["adapter"] not in ADAPTERS:
        raise ResultChannelError("result channel has unknown adapter")
    for name in ("subject_uid", "creator_uid"):
        uid = channel[name]
        if isinstance(uid, bool) or not isinstance(uid, int) or not 0 <= uid <= 4294967295:
            raise ResultChannelError(f"result channel {name} is not a uid")

    transport = _closed(
        channel["transport"],
        {
            "kind", "path", "object_identity", "unique_to_run",
            "pathname_reachable_by_subject_uid", "persistent_bytes",
        },
        "transport",
    )
    kind = transport["kind"]
    if kind not in ("anonymous_pipe", "unnamed_socketpair"):
        raise ResultChannelError("transport is not anonymous")
    identity = transport["object_identity"]
    if not isinstance(identity, str) or not _OBJECT_IDENTITY.fullmatch(identity):
        raise ResultChannelError("transport object identity is invalid")
    expected_prefix = "pipe:" if kind == "anonymous_pipe" else "socket:"
    if not identity.startswith(expected_prefix):
        raise ResultChannelError("transport kind and object identity disagree")
    expected_transport = {
        "kind": kind,
        "path": None,
        "object_identity": identity,
        "unique_to_run": True,
        "pathname_reachable_by_subject_uid": False,
        "persistent_bytes": False,
    }
    if transport != expected_transport:
        raise ResultChannelError("transport violates anonymity invariants")

    _exact(channel["writer_endpoint"], {
        "holder": "trusted-launcher",
        "mode": "write-only",
        "cloexec": True,
        "passed_to_subject": False,
        "descendant_inheritable": False,
        "adapter_copy_closed_before_subject": True,
    }, "writer endpoint")
    _exact(channel["reader_endpoint"], {
        "holder": "adapter-parent",
        "mode": "read-only",
        "cloexec": True,
        "passed_to_subject": False,
    }, "reader endpoint")
    _exact(channel["subject_access"], {
        "path_disclosed": False,
        "argv_path_count": 0,
        "environment_path_count": 0,
        "inherited_channel_fd_count": 0,
        "procfd_reachable": False,
    }, "subject access")
    bounds = _closed(
        channel["bounds"],
        {"max_bytes", "records_expected", "line_terminators_expected"},
        "bounds",
    )
    if isinstance(bounds["max_bytes"], bool) or not isinstance(
        bounds["max_bytes"], int
    ):
        raise ResultChannelError("bounds max_bytes is not an integer")
    _exact(bounds, {
        "max_bytes": trusted_bound,
        "records_expected": 1,
        "line_terminators_expected": 1,
    }, "bounds")
    _exact(channel["terminal_record"], {
        "canonical_utf8": True,
        "exact_json_values": 1,
        "trailing_newline": True,
        "records_seen": 1,
    }, "terminal record")
    _exact(channel["finality"], {
        "descendants_dead": True,
        "writer_set_closed": True,
        "eof_seen": True,
        "launcher_waited": True,
    }, "finality")
    _exact(channel["grade_source"], {
        "source": "bounded-endpoint-bytes",
        "bounded_in_memory": True,
        "persistent_copy_used": False,
        "parse_before_persist": True,
    }, "grade source")
    _exact(channel["persistent_capture"], {
        "mode": "none",
        "path": None,
        "authoritative": False,
        "subject_uid_pathname_reachable": False,
    }, "persistent capture")
    observed_type = "S_IFIFO" if kind == "anonymous_pipe" else "S_IFSOCK"
    _exact(channel["kernel_attestation"], {
        "method": "fstat",
        "observed_type": observed_type,
        "path_absence_observed": True,
        "before_subject_start": True,
        "observer": "adapter-parent",
    }, "kernel attestation")
    _exact(channel["handoff"], {
        "contract_id": HANDOFF_CONTRACT,
        "phase_ids": list(PHASE_IDS),
    }, "handoff")
    _exact(channel["od20"], {
        "authority_id": "OD-20",
        "owner_decision_sha256": OD20_DECISION_SHA256,
        "ratification_status": "RATIFIED_AS_FILED",
        "compliant": True,
    }, "OD-20 binding")
    return channel


def validate_r6_result_channel(
    value: Any, *, trusted_max_bytes: int
) -> dict[str, Any]:
    """Validate the 17-field channel nested in an F119 R6 result candidate.

    The byte bound is supplied by the trusted outer environment/launcher.  The
    candidate's own value cannot enlarge it.  This function deliberately does
    not validate or promote the complete, still-unfrozen F119 result schema.
    """

    trusted_bound = _trusted_bound(trusted_max_bytes)
    channel = _closed(value, set(R6_RESULT_CHANNEL_FIELDS), "R6 result channel")
    if channel["authority_id"] != "OD-20":
        raise ResultChannelError("R6 result channel has wrong authority")
    kind = channel["kind"]
    if kind not in ("anonymous_pipe", "unnamed_socketpair"):
        raise ResultChannelError("R6 result channel is not anonymous")
    if channel["path"] is not None:
        raise ResultChannelError("R6 result channel has a pathname")
    identity = channel["object_identity"]
    if not isinstance(identity, str) or not _OBJECT_IDENTITY.fullmatch(identity):
        raise ResultChannelError("R6 result channel object identity is invalid")
    expected_prefix = "pipe:" if kind == "anonymous_pipe" else "socket:"
    if not identity.startswith(expected_prefix):
        raise ResultChannelError("R6 result channel kind and identity disagree")
    for name in ("subject_uid", "creator_uid"):
        uid = channel[name]
        if isinstance(uid, bool) or not isinstance(uid, int) or not 0 <= uid <= 4294967295:
            raise ResultChannelError(f"R6 result channel {name} is not a uid")
    if channel["writer_identity"] != "trusted-launcher":
        raise ResultChannelError("R6 result channel writer is not trusted launcher")
    if channel["reader_identity"] != "adapter-parent":
        raise ResultChannelError("R6 result channel reader is not adapter parent")
    bounded_bytes = channel["bounded_bytes"]
    if (
        isinstance(bounded_bytes, bool)
        or not isinstance(bounded_bytes, int)
        or bounded_bytes != trusted_bound
    ):
        raise ResultChannelError("R6 result channel byte bound changed")
    if type(channel["records_seen"]) is not int or channel["records_seen"] != 1:
        raise ResultChannelError("R6 result channel record population is not 1/1")
    expected = {
        "unique_to_run": True,
        "descendant_writable": False,
        "pathname_reachable_by_subject_uid": False,
        "persistent_bytes": False,
        "grade_source": "bounded-endpoint-bytes",
        "persistent_copy_authority": False,
        "kernel_attested_before_subject": True,
    }
    for name, required in expected.items():
        if type(channel[name]) is not type(required) or channel[name] != required:
            raise ResultChannelError(f"R6 result channel {name} is nonconforming")
    return channel
