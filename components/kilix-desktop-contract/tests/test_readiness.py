from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
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
        self.assertEqual(self_test(self.requirements), (9, 9))

    def test_third_consumer_cannot_be_smuggled_into_the_interface(self) -> None:
        candidate = copy.deepcopy(self.requirements)
        candidate["consumer_requirements"].append({"requirement_id": "TE-E5"})
        with self.assertRaisesRegex(ReadinessError, "population is not two"):
            validate_requirements(candidate)

    def test_command_set_requires_the_exact_provider_order(self) -> None:
        entry_path = Path(__file__).resolve().parent / "fake_provider.py"
        entry_sha256 = hashlib.sha256(entry_path.read_bytes()).hexdigest()
        requirements = copy.deepcopy(self.requirements)
        for provider in requirements["consumer_requirements"][0]["providers"]:
            provider["entry_sha256"] = entry_sha256
        commands = {
            "commands": [
                {
                    "command": ["/bin/true", str(entry_path)],
                    "entry_path": str(entry_path),
                    "entry_sha256": entry_sha256,
                    "provider_id": provider["provider_id"],
                    "source_commit": provider["commit"],
                    "source_tree": provider["tree"],
                }
                for provider in requirements["consumer_requirements"][0]["providers"]
            ],
            "schema": "kilix.desktop.conformance-command-set/v1",
        }
        with tempfile.TemporaryDirectory() as directory:
            command_path = Path(directory) / "commands.json"
            command_path.write_bytes(canonical_bytes(commands))
            result = load_command_set(command_path, requirements)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0].provider_id, "kilix-95")

    def test_command_set_rejects_entry_byte_drift(self) -> None:
        entry_path = Path(__file__).resolve().parent / "fake_provider.py"
        provider = self.requirements["consumer_requirements"][0]["providers"][0]
        commands = {
            "commands": [
                {
                    "command": ["/bin/true", str(entry_path)],
                    "entry_path": str(entry_path),
                    "entry_sha256": "0" * 64,
                    "provider_id": item["provider_id"],
                    "source_commit": item["commit"],
                    "source_tree": item["tree"],
                }
                for item in self.requirements["consumer_requirements"][0]["providers"]
            ],
            "schema": "kilix.desktop.conformance-command-set/v1",
        }
        commands["commands"][0]["entry_sha256"] = provider["entry_sha256"]
        with tempfile.TemporaryDirectory() as directory:
            command_path = Path(directory) / "commands.json"
            command_path.write_bytes(canonical_bytes(commands))
            with self.assertRaisesRegex(ReadinessError, "entry bytes changed"):
                load_command_set(command_path, self.requirements)


if __name__ == "__main__":
    unittest.main()
