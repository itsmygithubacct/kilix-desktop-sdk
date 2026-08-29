from __future__ import annotations

import copy
from pathlib import Path
import unittest
from unittest import mock

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
        self.assertEqual(self_test(self.requirements), (8, 8))

    def test_third_consumer_cannot_be_smuggled_into_the_interface(self) -> None:
        candidate = copy.deepcopy(self.requirements)
        candidate["consumer_requirements"].append({"requirement_id": "TE-E5"})
        with self.assertRaisesRegex(ReadinessError, "population is not two"):
            validate_requirements(candidate)

    def test_command_set_requires_the_exact_provider_order(self) -> None:
        commands = {
            "commands": [
                {"command": ["/bin/true"], "provider_id": provider["provider_id"]}
                for provider in self.requirements["consumer_requirements"][0]["providers"]
            ],
            "schema": "kilix.desktop.conformance-command-set/v1",
        }
        with mock.patch(
            "pathlib.Path.read_bytes", return_value=canonical_bytes(commands)
        ), mock.patch(
            "kilix_desktop_contract.readiness.load_json", return_value=commands
        ):
            result = load_command_set(Path("commands.json"), self.requirements)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0].provider_id, "kilix-95")


if __name__ == "__main__":
    unittest.main()
