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
        self.assertEqual(self_test(self.requirements), (45, 45))

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
