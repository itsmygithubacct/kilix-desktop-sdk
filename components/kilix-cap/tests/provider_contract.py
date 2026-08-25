#!/usr/bin/env python3
"""Exercise the protocol-v1 surface of the compiled Cap provider."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import unittest


BINARY = Path("bin/kilix-cap")


class ProviderContractTests(unittest.TestCase):
    def run_provider(self, *arguments: str):
        return subprocess.run(
            [str(BINARY), *arguments],
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

    def test_describe_and_check(self):
        description = self.json_endpoint("provider", "describe", "--json")
        self.assertEqual(description["provider_id"], "kilix-cap")
        self.assertEqual(description["contract_version"], 1)
        self.assertFalse(
            description["capabilities"]["headless_screenshot"]["available"]
        )
        check = self.json_endpoint("provider", "check", "--json")
        self.assertEqual(check["status"], "ready")

    def test_config_reads_and_unavailable_endpoints(self):
        schema = self.json_endpoint("provider", "config", "schema", "--json")
        self.assertEqual(schema["x-kilix-provider-id"], "kilix-cap")
        values = self.json_endpoint("provider", "config", "get", "--json")
        self.assertEqual(values["values"], {})
        for arguments in (
            ("provider", "config", "set", "web_home", "https://example.test/"),
            ("provider", "migrate", "--from", "3.0.0", "--dry-run"),
            ("provider", "screenshot", "ignored.png"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_provider(*arguments)
                self.assertEqual(result.returncode, 4)
                self.assertEqual(result.stdout, "")
                self.assertIn("unavailable", result.stderr)

    def test_invalid_session_id_fails_closed(self):
        result = self.run_provider(
            "provider", "launch", "--session-id", "bad/session"
        )
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--binary", default=str(BINARY))
    arguments, remaining = parser.parse_known_args()
    BINARY = Path(arguments.binary)
    unittest.main(argv=[__file__, *remaining])
