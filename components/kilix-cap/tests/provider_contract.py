#!/usr/bin/env python3
"""Exercise the protocol-v1 surface of the compiled Cap provider."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


BINARY = Path("bin/kilix-cap")


class ProviderContractTests(unittest.TestCase):
    def run_provider(self, *arguments: str, env: dict[str, str] | None = None):
        selected = dict(os.environ)
        if env:
            selected.update(env)
        return subprocess.run(
            [str(BINARY), *arguments],
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

    def test_missing_authority_resolver_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            marker = state / "kilix/desktops/migration-v1.json"
            marker.parent.mkdir(parents=True)
            marker.write_text("{}\n", encoding="utf-8")
            result = self.run_provider(
                "provider",
                "describe",
                "--json",
                env={
                    "KILIX_DESKTOP_CONTRACT_COMMAND": "",
                    "KILIX_DESKTOP_SDK_PREFIX": "",
                    "XDG_STATE_HOME": str(state),
                },
            )
        self.assertEqual(result.returncode, 4)
        self.assertEqual(result.stdout, "")
        self.assertIn("persistence resolver", result.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--binary", default=str(BINARY))
    arguments, remaining = parser.parse_known_args()
    BINARY = Path(arguments.binary)
    unittest.main(argv=[__file__, *remaining])
