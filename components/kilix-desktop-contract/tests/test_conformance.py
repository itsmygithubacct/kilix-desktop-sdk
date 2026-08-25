from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from kilix_desktop_contract.conformance import (
    ConformanceError,
    run_conformance,
)


ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fake_provider.py"


class ConformanceTests(unittest.TestCase):
    def test_adapter_stage_exercises_the_complete_open_surface(self) -> None:
        report = run_conformance(
            [sys.executable, str(FAKE)], adapter_stage=True
        )
        self.assertEqual(report.provider_id, "fake-provider")
        self.assertEqual(len(report.checks), 8)
        self.assertIn("migration-gate", report.checks)
        self.assertTrue(report.adapter_stage)

    def test_duplicate_json_is_rejected(self) -> None:
        original = subprocess.Popen

        class DuplicateProvider:
            def __init__(self, command, *args, **kwargs):
                replacement = [
                    sys.executable,
                    "-c",
                    "import sys; print('{\\\"provider_id\\\":1,\\\"provider_id\\\":2}')",
                ]
                self._process = original(replacement, *args, **kwargs)
                self.pid = self._process.pid

            def wait(self, *args, **kwargs):
                return self._process.wait(*args, **kwargs)

        with mock.patch(
            "kilix_desktop_contract.conformance.subprocess.Popen",
            DuplicateProvider,
        ):
            with self.assertRaises(ConformanceError):
                run_conformance(["ignored"], adapter_stage=True)


if __name__ == "__main__":
    unittest.main()
