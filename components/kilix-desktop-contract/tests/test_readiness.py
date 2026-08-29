from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import subprocess
import unittest

from kilix_desktop_contract.readiness import (
    DEFAULT_REQUIREMENTS,
    ReadinessError,
    load_command_set,
    load_requirements,
    self_test,
    summary,
    validate_requirements,
)
from kilix_desktop_contract.jsonio import canonical_bytes


class TrustedLauncherReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.requirements = load_requirements(DEFAULT_REQUIREMENTS)

    def test_shipped_requirements_are_exact_and_still_blocked(self) -> None:
        validate_requirements(self.requirements)
        result = summary(self.requirements)
        self.assertIn("2/2 consumer requirements", result)
        self.assertIn("90/90 check occurrences", result)
        self.assertIn("9/9 E4 migration/rollback commands", result)
        self.assertIn("0/10 upstream return identities consumed", result)

    def test_all_premature_adoption_mutations_are_rejected(self) -> None:
        self.assertEqual(self_test(self.requirements), (124, 124))

    def test_f119_result_channel_preparation_is_bound_but_not_consumed(self) -> None:
        channel = self.requirements["f119_result_channel_requirements"]
        self.assertEqual(len(channel["required_top_level_fields"]), 18)
        self.assertEqual(len(channel["r3_field_mappings"]), 6)
        self.assertEqual(len(channel["od20_additive_group_ids"]), 12)
        self.assertEqual(len(channel["adapter_kinds"]), 4)
        self.assertEqual(len(channel["handoff_phase_ids"]), 12)
        self.assertEqual(len(channel["success_transition_ids"]), 11)
        self.assertEqual(len(channel["terminal_disposition_ids"]), 6)
        self.assertEqual(len(channel["transport_kinds"]), 2)
        self.assertEqual(len(channel["consumer_invariants"]), 10)
        self.assertEqual(
            channel["launcher_result_fd"]["returned"],
            {"denominator": 1, "numerator": 0},
        )
        self.assertEqual(channel["formal_state"]["p1_entered"]["numerator"], 0)
        executable = channel["r5_executable_preparation"]
        self.assertEqual(len(executable), 22)
        self.assertEqual(
            executable["corrected_selftest"],
            {"denominator": 40, "numerator": 40},
        )
        self.assertEqual(
            executable["anonymous_result_channels"],
            {"denominator": 12, "numerator": 12},
        )
        self.assertEqual(
            executable["formal_p1_entered"],
            {"denominator": 1, "numerator": 0},
        )
        conformance = channel["r6_conformance_preparation"]
        self.assertEqual(len(conformance), 32)
        self.assertEqual(len(conformance["packet_artifacts"]), 8)
        self.assertEqual(len(conformance["result_required_top_level_fields"]), 23)
        self.assertEqual(len(conformance["result_channel_required_fields"]), 17)
        self.assertEqual(
            conformance["authority_independent_field_bindings"],
            {"denominator": 98, "numerator": 98},
        )
        self.assertEqual(
            conformance["accepted_f100_bound_values_supplied"],
            {"denominator": 32, "numerator": 0},
        )
        self.assertEqual(
            conformance["formal_schema_freezes"],
            {"denominator": 2, "numerator": 0},
        )

    def test_f111_bridge_repairs_are_bound_without_inventing_acceptance(self) -> None:
        bridge = self.requirements["f119_result_channel_requirements"][
            "f111_bridge_requirements"
        ]
        self.assertEqual(len(bridge), 10)
        self.assertEqual(bridge["owner"], "F119/Track B")
        self.assertEqual(
            bridge["requested_repair_ids"],
            [
                "F111-F119-BRIDGE-01",
                "F111-F119-BRIDGE-02",
                "F111-F119-BRIDGE-03",
                "F111-F119-BRIDGE-04",
            ],
        )
        self.assertEqual(
            bridge["acceptance_vectors"],
            {"denominator": 9, "numerator": 9},
        )
        self.assertEqual(
            bridge["bridge_accepted"],
            {"denominator": 1, "numerator": 0},
        )

    def test_f110_profile_inputs_cover_the_required_interface(self) -> None:
        profiles = self.requirements["launcher_profile_requirements"]
        self.assertEqual(profiles["top_level_profile_count"], 2)
        self.assertEqual(len(profiles["e1_profile"]["freeze_legs"]), 2)
        children = profiles["e3_profile"]["child_profiles"]
        self.assertEqual(len(children), 6)
        self.assertEqual(
            {child["child_kind"] for child in children},
            {"native-executable", "python-module", "python-script"},
        )
        self.assertEqual(len(profiles["interface_controls"]), 12)
        self.assertEqual(profiles["adoption_state"], "construction-inputs-only-upstream-review-pending")
        self.assertEqual(len(self.requirements["upstream_gate"]["consumed_return_identities"]), 0)

    def test_third_consumer_cannot_be_smuggled_into_the_interface(self) -> None:
        candidate = copy.deepcopy(self.requirements)
        candidate["consumer_requirements"].append({"requirement_id": "TE-E5"})
        with self.assertRaisesRegex(ReadinessError, "population is not two"):
            validate_requirements(candidate)

    def test_command_set_requires_the_exact_provider_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_root, entry_path, commit, tree = self._git_source(Path(directory))
            entry_sha256 = hashlib.sha256(entry_path.read_bytes()).hexdigest()
            requirements = copy.deepcopy(self.requirements)
            for provider in requirements["consumer_requirements"][0]["providers"]:
                provider["commit"] = commit
                provider["tree"] = tree
                provider["entry_sha256"] = entry_sha256
            commands = {
                "commands": [
                    {
                        "command": ["/bin/true", str(entry_path)],
                        "entry_path": str(entry_path),
                        "entry_sha256": entry_sha256,
                        "provider_id": provider["provider_id"],
                        "source_commit": commit,
                        "source_root": str(source_root),
                        "source_tree": tree,
                    }
                    for provider in requirements["consumer_requirements"][0]["providers"]
                ],
                "schema": "kilix.desktop.conformance-command-set/v1",
            }
            command_path = Path(directory) / "commands.json"
            command_path.write_bytes(canonical_bytes(commands))
            result = load_command_set(command_path, requirements)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0].provider_id, "kilix-95")

    def test_command_set_rejects_entry_byte_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_root, entry_path, commit, tree = self._git_source(Path(directory))
            requirements = copy.deepcopy(self.requirements)
            for item in requirements["consumer_requirements"][0]["providers"]:
                item["commit"] = commit
                item["tree"] = tree
            provider = requirements["consumer_requirements"][0]["providers"][0]
            commands = {
                "commands": [
                    {
                        "command": ["/bin/true", str(entry_path)],
                        "entry_path": str(entry_path),
                        "entry_sha256": item["entry_sha256"],
                        "provider_id": item["provider_id"],
                        "source_commit": commit,
                        "source_root": str(source_root),
                        "source_tree": tree,
                    }
                    for item in requirements["consumer_requirements"][0]["providers"]
                ],
                "schema": "kilix.desktop.conformance-command-set/v1",
            }
            commands["commands"][0]["entry_sha256"] = provider["entry_sha256"]
            command_path = Path(directory) / "commands.json"
            command_path.write_bytes(canonical_bytes(commands))
            with self.assertRaisesRegex(ReadinessError, "entry bytes changed"):
                load_command_set(command_path, requirements)

    def test_command_set_rejects_a_dirty_bound_source_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_root, entry_path, commit, tree = self._git_source(Path(directory))
            requirements = copy.deepcopy(self.requirements)
            entry_sha256 = hashlib.sha256(entry_path.read_bytes()).hexdigest()
            for provider in requirements["consumer_requirements"][0]["providers"]:
                provider["commit"] = commit
                provider["tree"] = tree
                provider["entry_sha256"] = entry_sha256
            commands = {
                "commands": [
                    {
                        "command": ["/bin/true", str(entry_path)],
                        "entry_path": str(entry_path),
                        "entry_sha256": entry_sha256,
                        "provider_id": provider["provider_id"],
                        "source_commit": commit,
                        "source_root": str(source_root),
                        "source_tree": tree,
                    }
                    for provider in requirements["consumer_requirements"][0]["providers"]
                ],
                "schema": "kilix.desktop.conformance-command-set/v1",
            }
            (source_root / "support.txt").write_text("drift\n")
            command_path = Path(directory) / "commands.json"
            command_path.write_bytes(canonical_bytes(commands))
            with self.assertRaisesRegex(ReadinessError, "source worktree changed"):
                load_command_set(command_path, requirements)

    def _git_source(self, parent: Path) -> tuple[Path, Path, str, str]:
        source_root = parent / "source"
        source_root.mkdir()
        entry_path = source_root / "provider.py"
        entry_path.write_text("#!/usr/bin/env python3\n")
        (source_root / "support.txt").write_text("clean\n")
        subprocess.run(("/usr/bin/git", "init", "-q", str(source_root)), check=True)
        subprocess.run(("/usr/bin/git", "-C", str(source_root), "add", "."), check=True)
        subprocess.run(
            (
                "/usr/bin/git", "-C", str(source_root),
                "-c", "user.name=F110 Test", "-c", "user.email=f110@example.invalid",
                "commit", "-q", "-m", "fixture",
            ),
            check=True,
        )
        commit, tree = subprocess.check_output(
            ("/usr/bin/git", "-C", str(source_root), "rev-parse", "HEAD", "HEAD^{tree}"),
            text=True,
        ).splitlines()
        return source_root, entry_path, commit, tree


if __name__ == "__main__":
    unittest.main()
