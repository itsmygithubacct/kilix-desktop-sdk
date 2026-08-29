from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from kilix_desktop_contract.conformance import (
    ConformanceError,
    MatrixProvider,
    PROVIDER_ENVIRONMENT_NAMES,
    _sandbox_environment,
    run_conformance,
    run_conformance_matrix,
    run_endpoint,
)


ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fake_provider.py"


class ConformanceTests(unittest.TestCase):
    PROFILE = {
        "kilix_home": ROOT,
        "contract_command": Path(sys.executable),
        "state_library": ROOT / "build" / "libkilix-state.so",
        "land_assets": ROOT,
    }

    def test_adapter_stage_exercises_the_complete_open_surface(self) -> None:
        report = run_conformance(
            [sys.executable, str(FAKE)],
            adapter_stage=True,
            **self.PROFILE,
        )
        self.assertEqual(report.provider_id, "fake-provider")
        self.assertEqual(len(report.checks), 9)
        self.assertIn("migration-gate", report.checks)
        self.assertIn("read-only-endpoints", report.checks)
        self.assertTrue(report.adapter_stage)

    def test_read_only_side_effect_is_rejected(self) -> None:
        command = [
            "/usr/bin/env",
            "KILIX_FAKE_MUTATE_DESCRIBE=1",
            sys.executable,
            str(FAKE),
        ]
        with self.assertRaisesRegex(
            ConformanceError,
            "read-only provider describe mutated the sandbox",
        ):
            run_conformance(command, adapter_stage=True, **self.PROFILE)

    def test_orphan_process_is_rejected_and_terminated(self) -> None:
        command = [
            "/usr/bin/env",
            "KILIX_FAKE_ORPHAN_CHECK=1",
            sys.executable,
            str(FAKE),
        ]
        with self.assertRaisesRegex(
            ConformanceError,
            "left a live process-group member",
        ):
            run_conformance(command, adapter_stage=True, **self.PROFILE)

    def test_provider_environment_is_the_closed_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"PYTHONPATH": "/hostile", "UNDECLARED_PROVIDER_INPUT": "1"},
        ):
            environment = _sandbox_environment(
                Path(directory), **self.PROFILE
            )
        self.assertEqual(set(environment), PROVIDER_ENVIRONMENT_NAMES)
        self.assertEqual(len(environment), 39)
        self.assertEqual(environment["LC_ALL"], "C.UTF-8")
        self.assertEqual(environment["TZ"], "UTC")
        self.assertEqual(environment["PATH"], "/usr/bin:/bin")
        self.assertEqual(environment["KILIX_HOME"], str(ROOT))
        self.assertEqual(
            environment["KILIX_DESKTOP_CONTRACT_COMMAND"], sys.executable
        )
        self.assertEqual(
            environment["KILIX_STATE_LIBRARY"],
            str(ROOT / "build" / "libkilix-state.so"),
        )
        self.assertEqual(environment["KILIX_LAND_DESKTOP_ASSETS"], str(ROOT))
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("UNDECLARED_PROVIDER_INPUT", environment)

    def test_provider_environment_requires_absolute_authority_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ConformanceError, "Kilix host root must be an absolute path"
            ):
                _sandbox_environment(
                    Path(directory),
                    kilix_home="relative/kilix",
                    contract_command=sys.executable,
                    state_library=ROOT / "build" / "libkilix-state.so",
                    land_assets=ROOT,
                )

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
                run_conformance(
                    ["ignored"], adapter_stage=True, **self.PROFILE
                )

    def test_common_matrix_runs_exact_provider_pass_and_check_populations(self) -> None:
        identities = (
            "kilix-95", "kilix-cap", "kilix-land-desktop", "kilix-tui",
            "kilix-icewm",
        )
        providers = tuple(
            MatrixProvider(
                identity,
                (
                    "/usr/bin/env", f"KILIX_FAKE_PROVIDER_ID={identity}",
                    "KILIX_FAKE_MIGRATION=1", "KILIX_FAKE_SETTINGS=1",
                    f"KILIX_FAKE_SCREENSHOT={int(identity not in {'kilix-cap', 'kilix-icewm'})}",
                    sys.executable, str(FAKE),
                ),
                (
                    "version", "describe", "check", "config-schema", "config-get",
                    "config-set",
                    "screenshot" if identity not in {"kilix-cap", "kilix-icewm"}
                    else "screenshot-unavailable",
                    "migration-dry-run", "read-only-endpoints",
                ),
            )
            for identity in identities
        )
        report = run_conformance_matrix(providers, passes=2, **self.PROFILE)
        self.assertEqual(len(report.providers), 5)
        self.assertEqual(report.passes, 2)
        self.assertEqual(report.invocation_count, 10)
        self.assertEqual(report.check_count, 90)

    def test_common_matrix_rejects_a_changed_check_tuple(self) -> None:
        provider = MatrixProvider(
            "fake-provider",
            ("/usr/bin/env", "KILIX_FAKE_MIGRATION=1", sys.executable, str(FAKE)),
            ("version",),
        )
        with self.assertRaisesRegex(ConformanceError, "check tuple changed"):
            run_conformance_matrix((provider,), passes=1, **self.PROFILE)

    def test_common_matrix_rejects_entry_digest_drift_before_execution(self) -> None:
        provider = MatrixProvider(
            "fake-provider",
            (sys.executable, str(FAKE)),
            ("version",),
            FAKE,
            "0" * 64,
        )
        self.assertNotEqual(
            hashlib.sha256(FAKE.read_bytes()).hexdigest(), provider.entry_sha256
        )
        with self.assertRaisesRegex(ConformanceError, "entry digest changed"):
            run_conformance_matrix((provider,), passes=1, **self.PROFILE)


if __name__ == "__main__":
    unittest.main()
