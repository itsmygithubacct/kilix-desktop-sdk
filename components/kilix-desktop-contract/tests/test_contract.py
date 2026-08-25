from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kilix_desktop_contract.actions import ActionError, parse_action
from kilix_desktop_contract.catalog import (
    sanitize_catalog_entry,
    sanitize_catalog_text,
)
from kilix_desktop_contract.jsonio import DocumentError, load_json
from kilix_desktop_contract.validation import errors_for, validators


ROOT = Path(__file__).resolve().parents[1]


class ActionTests(unittest.TestCase):
    def test_url_splits_on_first_colon(self) -> None:
        action = parse_action("url.open:https://example.invalid/a:b?c=d")
        self.assertEqual(action.verb, "url.open")
        self.assertEqual(action.payload, "https://example.invalid/a:b?c=d")

    def test_http_and_credentials_are_refused(self) -> None:
        with self.assertRaisesRegex(ActionError, "https URL"):
            parse_action("url.open:http://example.invalid/")
        with self.assertRaisesRegex(ActionError, "credentials"):
            parse_action("url.open:https://user:secret@example.invalid/")

    def test_unknown_verb_and_controls_are_refused(self) -> None:
        with self.assertRaisesRegex(ActionError, "unknown action verb"):
            parse_action("command.run:echo")
        with self.assertRaisesRegex(ActionError, "control"):
            parse_action("document.open:notes/\nunsafe")

    def test_document_payload_is_data(self) -> None:
        action = parse_action("document.open:documents:notes/release 0.2.1.txt")
        self.assertEqual(action.payload, "documents:notes/release 0.2.1.txt")


class CatalogTests(unittest.TestCase):
    def test_hostile_fixture_has_exact_safe_output(self) -> None:
        raw = load_json(ROOT / "fixtures" / "hostile" / "catalog.json")
        expected = load_json(
            ROOT / "fixtures" / "hostile" / "catalog.expected.json"
        )
        self.assertEqual(sanitize_catalog_entry(raw), expected)

    def test_osc_dcs_csi_bidi_and_controls_are_removed(self) -> None:
        hostile = (
            "\x1b[2Jleft\x1b]8;;https://example.invalid/\x07link"
            "\x1b]8;;\x07\x1bPpayload\x1b\\\u202eright\nline"
        )
        self.assertEqual(sanitize_catalog_text(hostile), "leftlinkright line")

    def test_character_and_utf8_bounds_are_both_enforced(self) -> None:
        self.assertEqual(
            sanitize_catalog_text("ééé", max_chars=3, max_bytes=4),
            "éé",
        )
        self.assertEqual(
            sanitize_catalog_text("abcdef", max_chars=3, max_bytes=100),
            "abc",
        )

    def test_key_collision_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "collide"):
            sanitize_catalog_entry({"safe": 1, "\x1b[31msafe": 2})


class JsonTests(unittest.TestCase):
    def test_duplicate_keys_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"key": 1, "key": 2}\n', encoding="utf-8")
            with self.assertRaisesRegex(DocumentError, "duplicate JSON key"):
                load_json(path)


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.available = validators()

    def test_valid_fixtures(self) -> None:
        cases = {
            "action": ["action-document.json", "action-url.json"],
            "catalog-entry": ["catalog-entry.json"],
            "config-schema": ["config-schema.json"],
            "migration": ["migration-dry-run.json"],
            "provider-check": ["provider-check.json"],
            "provider-config": ["provider-config.json"],
            "provider-description": ["provider-description.json"],
        }
        for kind, names in cases.items():
            for name in names:
                with self.subTest(kind=kind, name=name):
                    document = load_json(ROOT / "fixtures" / "valid" / name)
                    self.assertEqual(
                        errors_for(kind, document, self.available), []
                    )

    def test_semantic_status_and_authority_rules(self) -> None:
        check = load_json(
            ROOT / "fixtures" / "invalid" / "provider-check-inconsistent.json"
        )
        migration = load_json(
            ROOT / "fixtures" / "invalid" / "migration-complete-legacy.json"
        )
        self.assertIn(
            "requires unavailable",
            " ".join(errors_for("provider-check", check, self.available)),
        )
        self.assertIn(
            "make xdg authoritative",
            " ".join(errors_for("migration", migration, self.available)),
        )

    def test_provider_schema_preserves_unknown_keys(self) -> None:
        schema = load_json(ROOT / "fixtures" / "valid" / "config-schema.json")
        self.assertIs(schema["additionalProperties"], True)
        self.assertEqual(
            errors_for("config-schema", schema, self.available), []
        )


if __name__ == "__main__":
    unittest.main()
