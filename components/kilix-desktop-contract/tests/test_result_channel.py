from __future__ import annotations

import copy
import json
import unittest

from kilix_desktop_contract.jsonio import canonical_bytes
from kilix_desktop_contract.result_channel import (
    ResultChannelError,
    parse_result_channel,
    validate_result_channel,
)


BOUND = 1048576


def _valid(adapter: str = "unittest", kind: str = "anonymous_pipe") -> dict:
    pipe = kind == "anonymous_pipe"
    return {
        "schema": "kilix.test.od20-result-channel/v1",
        "run_id": f"r25-{adapter}-001",
        "case_id": f"od20-{adapter}-positive",
        "adapter": adapter,
        "subject_uid": 1000,
        "creator_uid": 1000,
        "transport": {
            "kind": kind,
            "path": None,
            "object_identity": ("pipe:" if pipe else "socket:") + f"r25-{adapter}-001",
            "unique_to_run": True,
            "pathname_reachable_by_subject_uid": False,
            "persistent_bytes": False,
        },
        "writer_endpoint": {
            "holder": "trusted-launcher",
            "mode": "write-only",
            "cloexec": True,
            "passed_to_subject": False,
            "descendant_inheritable": False,
            "adapter_copy_closed_before_subject": True,
        },
        "reader_endpoint": {
            "holder": "adapter-parent",
            "mode": "read-only",
            "cloexec": True,
            "passed_to_subject": False,
        },
        "subject_access": {
            "path_disclosed": False,
            "argv_path_count": 0,
            "environment_path_count": 0,
            "inherited_channel_fd_count": 0,
            "procfd_reachable": False,
        },
        "bounds": {
            "max_bytes": BOUND,
            "records_expected": 1,
            "line_terminators_expected": 1,
        },
        "terminal_record": {
            "canonical_utf8": True,
            "exact_json_values": 1,
            "trailing_newline": True,
            "records_seen": 1,
        },
        "finality": {
            "descendants_dead": True,
            "writer_set_closed": True,
            "eof_seen": True,
            "launcher_waited": True,
        },
        "grade_source": {
            "source": "bounded-endpoint-bytes",
            "bounded_in_memory": True,
            "persistent_copy_used": False,
            "parse_before_persist": True,
        },
        "persistent_capture": {
            "mode": "none",
            "path": None,
            "authoritative": False,
            "subject_uid_pathname_reachable": False,
        },
        "kernel_attestation": {
            "method": "fstat",
            "observed_type": "S_IFIFO" if pipe else "S_IFSOCK",
            "path_absence_observed": True,
            "before_subject_start": True,
            "observer": "adapter-parent",
        },
        "handoff": {
            "contract_id": "kilix.f119.adapter-channel-handoff/v1",
            "phase_ids": [f"CH-{ordinal:02d}" for ordinal in range(1, 13)],
        },
        "od20": {
            "authority_id": "OD-20",
            "owner_decision_sha256": "b7c70acba32ca74518868e894330c6c8158f4436765d0a556a258fe4c4f1de3e",
            "ratification_status": "RATIFIED_AS_FILED",
            "compliant": True,
        },
    }


def _replace(document: dict, pointer: str, value: object) -> None:
    parts = pointer.strip("/").split("/")
    target = document
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


class ResultChannelConsumerTests(unittest.TestCase):
    def test_four_adapters_and_two_transports_are_accepted(self) -> None:
        transports = set()
        for ordinal, adapter in enumerate(("unittest", "plain-assert", "shell", "make")):
            kind = "anonymous_pipe" if ordinal % 2 == 0 else "unnamed_socketpair"
            transports.add(kind)
            document = _valid(adapter, kind)
            self.assertEqual(
                parse_result_channel(canonical_bytes(document), trusted_max_bytes=BOUND),
                document,
            )
        self.assertEqual(len(transports), 2)

    def test_thirty_two_prepared_negative_mutations_are_rejected(self) -> None:
        mutations = (
            ("/transport/kind", "regular_file"),
            ("/transport/kind", "named_fifo"),
            ("/transport/kind", "filesystem_unix_socket"),
            ("/transport/kind", "pathname_character_device"),
            ("/transport/path", "/tmp/f119-result.json"),
            ("/transport/pathname_reachable_by_subject_uid", True),
            ("/transport/persistent_bytes", True),
            ("/writer_endpoint/passed_to_subject", True),
            ("/writer_endpoint/descendant_inheritable", True),
            ("/writer_endpoint/adapter_copy_closed_before_subject", False),
            ("/reader_endpoint/passed_to_subject", True),
            ("/subject_access/path_disclosed", True),
            ("/subject_access/argv_path_count", 1),
            ("/subject_access/environment_path_count", 1),
            ("/subject_access/inherited_channel_fd_count", 1),
            ("/subject_access/procfd_reachable", True),
            ("/bounds/max_bytes", 0),
            ("/bounds/records_expected", 2),
            ("/terminal_record/exact_json_values", 2),
            ("/terminal_record/trailing_newline", False),
            ("/finality/descendants_dead", False),
            ("/finality/writer_set_closed", False),
            ("/finality/eof_seen", False),
            ("/finality/launcher_waited", False),
            ("/grade_source/source", "persistent-copy"),
            ("/grade_source/persistent_copy_used", True),
            ("/persistent_capture/mode", "shared-regular-file"),
            ("/persistent_capture/path", "/tmp/f119-capture.json"),
            ("/kernel_attestation/before_subject_start", False),
            ("/kernel_attestation/path_absence_observed", False),
            ("/od20/compliant", False),
            ("/od20/authority_id", "OD-19"),
        )
        rejected = 0
        for pointer, value in mutations:
            candidate = copy.deepcopy(_valid())
            _replace(candidate, pointer, value)
            with self.assertRaises(ResultChannelError, msg=pointer):
                validate_result_channel(candidate, trusted_max_bytes=BOUND)
            rejected += 1
        self.assertEqual(rejected, len(mutations))
        self.assertEqual(len(mutations), 32)

    def test_direct_byte_envelope_fails_closed(self) -> None:
        document = _valid()
        cases = (
            json.dumps(document).encode("utf-8"),
            b'{"schema":1,"schema":2}\n',
            b"\xff\n",
            b"",
            canonical_bytes(document) + b" ",
        )
        rejected = 0
        for payload in cases:
            with self.assertRaises(ResultChannelError):
                parse_result_channel(payload, trusted_max_bytes=BOUND)
            rejected += 1
        self.assertEqual(rejected, 5)

    def test_transport_relations_fail_closed(self) -> None:
        rejected = 0
        for kind, identity, observed_type in (
            ("anonymous_pipe", "socket:r25-mismatch-001", "S_IFIFO"),
            ("unnamed_socketpair", "pipe:r25-mismatch-001", "S_IFSOCK"),
            ("anonymous_pipe", "pipe:r25-mismatch-001", "S_IFSOCK"),
            ("unnamed_socketpair", "socket:r25-mismatch-001", "S_IFIFO"),
        ):
            candidate = _valid(kind=kind)
            candidate["transport"]["object_identity"] = identity
            candidate["kernel_attestation"]["observed_type"] = observed_type
            with self.assertRaises(ResultChannelError):
                validate_result_channel(candidate, trusted_max_bytes=BOUND)
            rejected += 1
        self.assertEqual(rejected, 4)


if __name__ == "__main__":
    unittest.main()
