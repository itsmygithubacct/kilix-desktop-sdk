#!/usr/bin/env python3
"""Protocol-v1 adapter tests that do not initialize provider storage."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "main.py"


class ProviderProtocolV1Tests(unittest.TestCase):
    def run_provider(self, *arguments: str, env: dict[str, str] | None = None):
        selected = dict(os.environ)
        selected["PYTHONDONTWRITEBYTECODE"] = "1"
        if env:
            selected.update(env)
        return subprocess.run(
            [sys.executable, str(ENTRY), *arguments],
            cwd=ROOT,
            env=selected,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def json_endpoint(self, *arguments: str) -> dict[str, object]:
        result = self.run_provider(*arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("\n"))
        self.assertFalse(result.stdout.endswith("\n\n"))
        return json.loads(result.stdout)

    def test_describe_is_early_read_only_and_truthful(self):
        with tempfile.TemporaryDirectory() as temporary:
            storage = Path(temporary) / "must-not-exist"
            result = self.run_provider(
                "provider",
                "describe",
                "--json",
                env={"KILIX95_STORAGE_HOME": str(storage)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(storage.exists())
            document = json.loads(result.stdout)
        self.assertEqual(document["provider_id"], "kilix-95")
        self.assertEqual(document["contract_version"], 1)
        self.assertEqual(document["display_modes"], ["kitty-graphics"])
        self.assertTrue(document["capabilities"]["headless_screenshot"])
        self.assertFalse(document["capabilities"]["settings"]["available"])

    def test_check_and_config_documents_have_v1_identity(self):
        check = self.json_endpoint("provider", "check", "--json")
        self.assertEqual(check["provider_id"], "kilix-95")
        self.assertIn(check["status"], ("ready", "unavailable"))
        schema = self.json_endpoint("provider", "config", "schema", "--json")
        self.assertEqual(schema["x-kilix-provider-id"], "kilix-95")
        self.assertTrue(schema["additionalProperties"])
        values = self.json_endpoint("provider", "config", "get", "--json")
        self.assertEqual(values["values"], {})
        self.assertEqual(values["revision"], 0)

    def test_gated_mutations_report_unavailable_without_stdout(self):
        for arguments in (
            ("provider", "config", "set", "theme", "classic"),
            ("provider", "migrate", "--from", "0.2.0", "--dry-run"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_provider(*arguments)
                self.assertEqual(result.returncode, 4)
                self.assertEqual(result.stdout, "")
                self.assertIn("unavailable", result.stderr)

    def test_launch_and_screenshot_translate_to_existing_entry_points(self):
        sys.path.insert(0, str(ROOT))
        try:
            import provider_protocol

            self.assertEqual(
                provider_protocol.dispatch(
                    ["provider", "launch", "--session-id", "session-1"]
                ),
                [],
            )
            self.assertEqual(os.environ["KILIX_DESKTOP_SESSION_ID"], "session-1")
            self.assertEqual(
                provider_protocol.dispatch(
                    ["provider", "screenshot", "out.png", "--scene", "start"]
                ),
                ["--screenshot", "out.png", "--scene", "start"],
            )
            self.assertEqual(os.environ["KILIX_PROVIDER_SCREENSHOT"], "1")
        finally:
            sys.path.remove(str(ROOT))
            sys.modules.pop("provider_protocol", None)
            os.environ.pop("KILIX_DESKTOP_SESSION_ID", None)
            os.environ.pop("KILIX_PROVIDER_SCREENSHOT", None)

    def test_invalid_session_id_fails_closed(self):
        result = self.run_provider(
            "provider", "launch", "--session-id", "bad/session"
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
