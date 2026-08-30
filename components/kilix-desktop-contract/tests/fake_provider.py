#!/usr/bin/env python3
"""Deterministic executable fixture for the conformance runner."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def emit(document: dict[str, object]) -> None:
    print(json.dumps(document, separators=(",", ":"), sort_keys=True))


def main(argv: list[str]) -> int:
    provider_id = os.environ.get("KILIX_FAKE_PROVIDER_ID", "fake-provider")
    settings_available = os.environ.get("KILIX_FAKE_SETTINGS") == "1"
    screenshot_available = os.environ.get("KILIX_FAKE_SCREENSHOT", "1") == "1"
    if argv == ["--version"]:
        print("fake-provider 1.2.3")
        return 0
    if argv == ["provider", "describe", "--json"]:
        if os.environ.get("KILIX_FAKE_MUTATE_DESCRIBE") == "1":
            (Path.home() / "describe-side-effect").write_text(
                "unexpected\n", encoding="utf-8"
            )
        emit(
            {
                "capabilities": {
                    "audio": False,
                    "headless_screenshot": screenshot_available,
                    "keyboard": True,
                    "launcher": False,
                    "mouse": False,
                    "reduced_motion": True,
                    "settings": settings_available,
                },
                "config_schema": "kilix.desktop.config.provider.v1",
                "contract_version": 1,
                "display_modes": ["terminal-text"],
                "provider_id": provider_id,
                "provider_version": "1.2.3",
                "required_capabilities": ["keyboard"],
                "schema_version": 1,
            }
        )
        return 0
    if argv == ["provider", "check", "--json"]:
        if os.environ.get("KILIX_FAKE_ORPHAN_CHECK") == "1":
            subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        emit(
            {
                "checks": [
                    {
                        "id": "fixture",
                        "required": True,
                        "status": "pass",
                        "summary": "The fixture is ready.",
                    }
                ],
                "contract_version": 1,
                "provider_id": provider_id,
                "schema_version": 1,
                "status": "ready",
                "summary": "The fake provider is ready.",
            }
        )
        return 0
    if argv == ["provider", "config", "schema", "--json"]:
        emit(
            {
                "$id": f"https://schemas.kilix.org/desktop/config/{provider_id}/v1",
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "additionalProperties": True,
                "properties": {},
                "type": "object",
                "x-kilix-contract-version": 1,
                "x-kilix-provider-id": provider_id,
            }
        )
        return 0
    if (
        argv == ["provider", "config", "get", "--json"]
        or len(argv) == 5
        and argv[:3] == ["provider", "config", "get"]
        and argv[4] == "--json"
    ):
        state_path = Path(os.environ["KILIX_CONFIG_HOME"]) / "fixture.json"
        state = {"revision": 0, "values": {}}
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        values = state["values"]
        if len(argv) == 5:
            key = argv[3]
            values = {key: values[key]} if key in values else {}
        emit(
            {
                "contract_version": 1,
                "provider_id": provider_id,
                "revision": state["revision"],
                "schema_version": 1,
                "values": values,
            }
        )
        return 0
    if len(argv) == 5 and argv[:3] == ["provider", "config", "set"]:
        if settings_available:
            state_path = Path(os.environ["KILIX_CONFIG_HOME"]) / "fixture.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {"revision": 0, "values": {}}
            if state_path.is_file():
                state = json.loads(state_path.read_text(encoding="utf-8"))
            state["revision"] += 1
            state["values"][argv[3]] = json.loads(argv[4])
            state_path.write_text(
                json.dumps(state, separators=(",", ":"), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return 0
        print(f"{provider_id}: configuration writes are unavailable", file=sys.stderr)
        return 4
    if len(argv) == 3 and argv[:2] == ["provider", "screenshot"]:
        if not screenshot_available:
            print(f"{provider_id}: screenshot is unavailable", file=sys.stderr)
            return 4
        Path(argv[2]).write_bytes(b"fixture screenshot\n")
        return 0
    if len(argv) == 5 and argv[:2] == ["provider", "migrate"]:
        if os.environ.get("KILIX_FAKE_MIGRATION") == "1":
            emit(
                {
                    "authoritative_store": "legacy",
                    "contract_version": 1,
                    "dry_run": True,
                    "from_version": argv[3],
                    "migration_id": f"{provider_id}-fixture-to-contract-v1",
                    "operations": [],
                    "provider_id": provider_id,
                    "recovery_paths": [],
                    "schema": "kilix.desktop.migration/v1",
                    "schema_version": 1,
                    "state": "planned",
                    "to_contract_version": 1,
                }
            )
            return 0
        print(f"{provider_id}: migration is unavailable", file=sys.stderr)
        return 4
    print("fake-provider: unsupported fixture command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
