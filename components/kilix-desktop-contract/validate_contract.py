#!/usr/bin/env python3
"""Validate and self-test the Kilix desktop-provider contract candidate."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any


ROOT = Path(__file__).resolve().parent
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from kilix_desktop_contract.catalog import sanitize_catalog_entry
from kilix_desktop_contract.constants import (
    ACTION_VERBS,
    CAPABILITIES,
    CONTRACT_VERSION,
    DEADLINES_SECONDS,
    DISPLAY_MODES,
    EXIT_STATUSES,
    POWER_ACTIONS,
)
from kilix_desktop_contract.jsonio import (
    MAX_DOCUMENT_BYTES,
    DocumentError,
    canonical_bytes,
    load_json,
)
from kilix_desktop_contract.validation import errors_for, validators


VALID_FIXTURES = {
    "action-document.json": "action",
    "action-url.json": "action",
    "catalog-entry.json": "catalog-entry",
    "config-schema.json": "config-schema",
    "migration-dry-run.json": "migration",
    "provider-check.json": "provider-check",
    "provider-config.json": "provider-config",
    "provider-description.json": "provider-description",
}

EXPECTED_INVALID = {
    "action-http-url.json": ("action", "does not match '^https://'"),
    "action-unknown-verb.json": ("action", "is not one of"),
    "config-schema-closed.json": ("config-schema", "True was expected"),
    "migration-complete-legacy.json": (
        "migration",
        "completed migration must make xdg authoritative",
    ),
    "provider-check-inconsistent.json": (
        "provider-check",
        "required failed/unavailable check requires unavailable",
    ),
    "provider-config-missing-revision.json": (
        "provider-config",
        "'revision' is a required property",
    ),
    "provider-description-mode.json": (
        "provider-description",
        "is not one of",
    ),
}

EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


def _frozen_files() -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        relative = path.relative_to(ROOT)
        if any(
            part in EXCLUDED_PARTS or part.endswith(".egg-info")
            for part in relative.parts
        ):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        result.append(relative)
    return sorted(result, key=lambda item: item.as_posix())


def verify_canonical_json() -> list[str]:
    errors: list[str] = []
    json_files = sorted(
        [
            *ROOT.glob("contracts/*.json"),
            *ROOT.glob("fixtures/*/*.json"),
            *ROOT.glob("schemas/*.json"),
        ],
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    for path in json_files:
        try:
            document = load_json(path)
        except (OSError, DocumentError) as error:
            errors.append(f"cannot load {path.relative_to(ROOT)}: {error}")
            continue
        if path.read_bytes() != canonical_bytes(document):
            errors.append(f"non-canonical JSON: {path.relative_to(ROOT)}")
    return errors


def verify_hashes() -> list[str]:
    errors: list[str] = []
    manifest = ROOT / "SHA256SUMS"
    if not manifest.is_file():
        return ["SHA256SUMS is missing"]
    recorded: dict[Path, str] = {}
    for number, raw_line in enumerate(
        manifest.read_text(encoding="utf-8").splitlines(), start=1
    ):
        digest, separator, raw_path = raw_line.partition("  ")
        if (
            not separator
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            errors.append(f"malformed SHA256SUMS line {number}")
            continue
        relative = Path(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"unsafe SHA256SUMS path on line {number}: {raw_path}")
            continue
        if relative in recorded:
            errors.append(f"duplicate SHA256SUMS path: {raw_path}")
            continue
        recorded[relative] = digest

    expected = _frozen_files()
    missing = sorted(set(expected) - set(recorded), key=lambda item: item.as_posix())
    extra = sorted(set(recorded) - set(expected), key=lambda item: item.as_posix())
    for path in missing:
        errors.append(f"unbound file: {path}")
    for path in extra:
        errors.append(f"manifest names absent file: {path}")
    for relative in expected:
        path = ROOT / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if recorded.get(relative) != digest:
            errors.append(f"SHA-256 mismatch: {relative}")
    return errors


def verify_vocabulary() -> list[str]:
    errors: list[str] = []
    vocabulary = load_json(ROOT / "contracts" / "vocabulary-v1.json")
    comparisons = {
        "action_verbs": list(ACTION_VERBS),
        "capabilities": list(CAPABILITIES),
        "contract_version": CONTRACT_VERSION,
        "deadlines_seconds": DEADLINES_SECONDS,
        "display_modes": list(DISPLAY_MODES),
        "power_actions": list(POWER_ACTIONS),
    }
    for field, expected in comparisons.items():
        if vocabulary.get(field) != expected:
            errors.append(f"Python constant disagrees with vocabulary: {field}")
    recorded_statuses = {
        item["name"]: item["code"] for item in vocabulary["exit_statuses"]
    }
    if recorded_statuses != EXIT_STATUSES:
        errors.append("Python exit statuses disagree with vocabulary")
    for field in ("action_verbs", "capabilities", "display_modes", "power_actions"):
        values = vocabulary[field]
        if values != sorted(set(values)):
            errors.append(f"{field} must be sorted and unique")
    return errors


def verify_import_identities() -> list[str]:
    errors: list[str] = []
    identities = load_json(ROOT / "contracts" / "import-identities-v1.json")
    if identities.get("python_packages") != ["kilix_desk", "kilix_tui"]:
        errors.append("frozen Python imports are not kilix_desk and kilix_tui")
    expected_tools = {
        "kilix-calculator",
        "kilix-cameras",
        "kilix-character-map",
        "kilix-cpu",
        "kilix-disk",
        "kilix-file",
        "kilix-find-files",
        "kilix-launcher",
        "kilix-memory",
        "kilix-music",
        "kilix-notepad",
        "kilix-package",
        "kilix-rollout-resume",
        "kilix-session-log",
        "kilix-switch",
        "kilix-system",
        "kilix-temps",
        "kilix-volume",
        "kilix-weather",
        "plebian-os",
    }
    recorded_tools = {
        item["name"] for item in identities.get("tool_console_scripts", [])
    }
    if recorded_tools != expected_tools:
        errors.append("tools/* console-script identity set changed")
    all_entries = [
        *identities.get("tool_console_scripts", []),
        *identities.get("composed_console_scripts", []),
    ]
    names = [item["name"] for item in all_entries]
    if len(names) != len(set(names)):
        errors.append("duplicate frozen console-script name")
    for group in ("tool_console_scripts", "composed_console_scripts"):
        values = identities.get(group, [])
        if values != sorted(values, key=lambda item: item["name"]):
            errors.append(f"{group} must be sorted by name")
    return errors


def verify_fixtures() -> tuple[list[str], int, int]:
    errors: list[str] = []
    available = validators()
    valid_count = 0
    invalid_count = 0
    valid_root = ROOT / "fixtures" / "valid"
    invalid_root = ROOT / "fixtures" / "invalid"
    actual_valid = {path.name for path in valid_root.glob("*.json")}
    actual_invalid = {path.name for path in invalid_root.glob("*.json")}
    if actual_valid != set(VALID_FIXTURES):
        errors.append("valid fixture inventory disagrees with validator")
    if actual_invalid != set(EXPECTED_INVALID):
        errors.append("invalid fixture inventory disagrees with validator")

    for name, kind in sorted(VALID_FIXTURES.items()):
        document = load_json(valid_root / name)
        fixture_errors = errors_for(kind, document, available)
        if fixture_errors:
            errors.append(f"valid fixture {name}: {'; '.join(fixture_errors)}")
        else:
            valid_count += 1

    for name, (kind, expected) in sorted(EXPECTED_INVALID.items()):
        document = load_json(invalid_root / name)
        fixture_errors = errors_for(kind, document, available)
        if not fixture_errors:
            errors.append(f"invalid fixture passed: {name}")
        elif expected not in " ".join(fixture_errors):
            errors.append(
                f"invalid fixture {name} lacked expected diagnostic {expected!r}: "
                f"{'; '.join(fixture_errors)}"
            )
        else:
            invalid_count += 1

    raw = load_json(ROOT / "fixtures" / "hostile" / "catalog.json")
    expected = load_json(
        ROOT / "fixtures" / "hostile" / "catalog.expected.json"
    )
    sanitized = sanitize_catalog_entry(raw)
    if sanitized != expected:
        errors.append(
            "hostile catalog mismatch: "
            + json.dumps(sanitized, ensure_ascii=True, sort_keys=True)
        )
    elif errors_for("catalog-entry", sanitized, available):
        errors.append("sanitized hostile catalog does not satisfy catalog schema")
    return errors, valid_count, invalid_count


def verify_loader_guards() -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="kilix-desktop-contract-") as directory:
        root = Path(directory)
        duplicate = root / "duplicate.json"
        duplicate.write_text('{"key": 1, "key": 2}\n', encoding="utf-8")
        try:
            load_json(duplicate)
            errors.append("duplicate JSON key was accepted")
        except DocumentError as error:
            if "duplicate JSON key" not in str(error):
                errors.append(f"wrong duplicate-key diagnostic: {error}")

        oversized = root / "oversized.json"
        oversized.write_bytes(b" " * (MAX_DOCUMENT_BYTES + 1))
        try:
            load_json(oversized)
            errors.append("oversized JSON document was accepted")
        except DocumentError as error:
            if "exceeds" not in str(error):
                errors.append(f"wrong oversized-document diagnostic: {error}")
    return errors


def verify_c_header() -> list[str]:
    compiler = shutil.which("cc")
    if compiler is None:
        return ["C11 compiler 'cc' is unavailable"]
    source = r'''
#include "kilix_desktop_contract.h"
#include <string.h>

int main(void)
{
    struct kilix_desktop_action action;
    if (KILIX_DESKTOP_CONTRACT_VERSION != 1)
        return 1;
    if (kilix_desktop_action_parse(
            "url.open:https://example.invalid/a:b", &action) !=
        KILIX_DESKTOP_PARSE_OK)
        return 2;
    if (action.verb != KILIX_DESKTOP_ACTION_URL_OPEN)
        return 3;
    if (strncmp(action.payload, "https://", 8u) != 0)
        return 4;
    if (kilix_desktop_action_parse("command.run:echo", &action) !=
        KILIX_DESKTOP_PARSE_UNKNOWN_VERB)
        return 5;
    if (kilix_desktop_action_parse("power.request:format", &action) !=
        KILIX_DESKTOP_PARSE_INVALID_PAYLOAD)
        return 6;
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="kilix-desktop-contract-c-") as directory:
        root = Path(directory)
        source_path = root / "contract_test.c"
        binary_path = root / "contract_test"
        source_path.write_text(source, encoding="utf-8")
        compile_result = subprocess.run(
            [
                compiler,
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wpedantic",
                "-I",
                str(ROOT / "include"),
                str(source_path),
                "-o",
                str(binary_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if compile_result.returncode != 0:
            return [
                "C11 header compile failed: "
                + (compile_result.stderr or compile_result.stdout).strip()
            ]
        run_result = subprocess.run(
            [str(binary_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if run_result.returncode != 0:
            return [f"C11 header self-test exited {run_result.returncode}"]
    return []


def run_unit_tests() -> tuple[list[str], int]:
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), pattern="test_*.py"
    )
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if result.wasSuccessful():
        return [], result.testsRun
    return ["unit tests failed:\n" + stream.getvalue().rstrip()], result.testsRun


def self_test() -> int:
    errors: list[str] = []
    fixture_errors, valid_count, invalid_count = verify_fixtures()
    errors.extend(fixture_errors)
    errors.extend(verify_canonical_json())
    errors.extend(verify_vocabulary())
    errors.extend(verify_import_identities())
    errors.extend(verify_loader_guards())
    errors.extend(verify_c_header())
    unit_errors, unit_count = run_unit_tests()
    errors.extend(unit_errors)
    errors.extend(verify_hashes())
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PASS: "
        f"{len(validators())} schemas, {valid_count} valid fixtures, "
        f"{invalid_count} invalid fixtures, 1 hostile catalog, "
        f"{unit_count} unit tests, C11 header, canonical JSON and SHA256SUMS"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--kind", choices=sorted(validators()))
    parser.add_argument("document", nargs="?", type=Path)
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        return self_test()
    if arguments.kind is None or arguments.document is None:
        parser.error("--kind and document are required without --self-test")
    try:
        document = load_json(arguments.document)
    except (DocumentError, OSError) as error:
        print(f"cannot load JSON: {error}", file=sys.stderr)
        return 3
    errors = errors_for(arguments.kind, document, validators())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
