from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from kilix_desktop_contract.conformance import (
    ConformanceError,
    run_conformance,
    run_endpoint,
)


ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fake_provider.py"


class ConformanceTests(unittest.TestCase):
    def test_adapter_stage_exercises_the_complete_open_surface(self) -> None:
        report = run_conformance(
            [sys.executable, str(FAKE)], adapter_stage=True
        )
        self.assertEqual(report.provider_id, "fake-provider")
        self.assertEqual(len(report.checks), 9)
        self.assertIn("migration-gate", report.checks)
        self.assertIn("read-only-endpoints", report.checks)
        self.assertTrue(report.adapter_stage)

    def test_read_only_side_effect_is_rejected(self) -> None:
        with mock.patch.dict(
            os.environ, {"KILIX_FAKE_MUTATE_DESCRIBE": "1"}
        ):
            with self.assertRaisesRegex(
                ConformanceError,
                "read-only provider describe mutated the sandbox",
            ):
                run_conformance([sys.executable, str(FAKE)], adapter_stage=True)

    def test_orphan_process_is_rejected_and_terminated(self) -> None:
        with mock.patch.dict(os.environ, {"KILIX_FAKE_ORPHAN_CHECK": "1"}):
            with self.assertRaisesRegex(
                ConformanceError,
                "left a live process-group member",
            ):
                run_conformance([sys.executable, str(FAKE)], adapter_stage=True)

    def test_endpoint_timeout_is_bounded(self) -> None:
        with self.assertRaisesRegex(ConformanceError, "timed out"):
            run_endpoint(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                [],
                timeout=0.05,
            )

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
