#!/usr/bin/env python3
"""Deterministic executable fixture for the conformance runner."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def emit(document: dict[str, object]) -> None:
    print(json.dumps(document, separators=(",", ":"), sort_keys=True))


def main(argv: list[str]) -> int:
    if argv == ["--version"]:
        print("fake-provider 1.2.3")
        return 0
    if argv == ["provider", "describe", "--json"]:
        emit(
            {
                "capabilities": {
                    "audio": False,
                    "headless_screenshot": True,
                    "keyboard": True,
                    "launcher": False,
                    "mouse": False,
                    "reduced_motion": True,
                    "settings": False,
                },
                "config_schema": "kilix.desktop.config.provider.v1",
                "contract_version": 1,
                "display_modes": ["terminal-text"],
                "provider_id": "fake-provider",
                "provider_version": "1.2.3",
                "required_capabilities": ["keyboard"],
                "schema_version": 1,
            }
        )
        return 0
    if argv == ["provider", "check", "--json"]:
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
                "provider_id": "fake-provider",
                "schema_version": 1,
                "status": "ready",
                "summary": "The fake provider is ready.",
            }
        )
        return 0
    if argv == ["provider", "config", "schema", "--json"]:
        emit(
            {
                "$id": "https://schemas.kilix.org/desktop/config/fake-provider/v1",
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "additionalProperties": True,
                "properties": {},
                "type": "object",
                "x-kilix-contract-version": 1,
                "x-kilix-provider-id": "fake-provider",
            }
        )
        return 0
    if argv == ["provider", "config", "get", "--json"]:
        emit(
            {
                "contract_version": 1,
                "provider_id": "fake-provider",
                "revision": 0,
                "schema_version": 1,
                "values": {},
            }
        )
        return 0
    if len(argv) == 5 and argv[:3] == ["provider", "config", "set"]:
        print("fake-provider: configuration writes are unavailable", file=sys.stderr)
        return 4
    if len(argv) == 3 and argv[:2] == ["provider", "screenshot"]:
        Path(argv[2]).write_bytes(b"fixture screenshot\n")
        return 0
    if len(argv) == 5 and argv[:2] == ["provider", "migrate"]:
        print("fake-provider: migration is unavailable", file=sys.stderr)
        return 4
    print("fake-provider: unsupported fixture command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
