from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest import mock

from kilix_desktop_contract import persistence
from kilix_desktop_contract.persistence import (
    AuthorityError,
    Layout,
    MIGRATION_ORDER,
    MigrationError,
    PersistenceStore,
)


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="kilix-desktop-persistence-"
        )
        self.root = Path(self.temporary.name)
        home = self.root / "home"
        home.mkdir(mode=0o700)
        self.environment = {
            "HOME": str(home),
            "GPU_TERMINAL_HOME": str(self.root / "legacy"),
            "XDG_CACHE_HOME": str(self.root / "xdg/cache"),
            "XDG_CONFIG_HOME": str(self.root / "xdg/config"),
            "XDG_DATA_HOME": str(self.root / "xdg/data"),
            "XDG_STATE_HOME": str(self.root / "xdg/state"),
        }
        self.layout = Layout.from_environment(self.environment)
        self.store = PersistenceStore(self.layout)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def write_private(path: Path, data: bytes) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)

    def snapshot(self) -> list[str]:
        return sorted(
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
        )

    def seed_all_legacy_stores(self) -> dict[str, bytes]:
        land = self.layout.legacy_provider_root("kilix-land-desktop")
        profile = b"KILIX-STATE\x00profile\xff\n"
        world = b"KILIX-STATE\x00world\x80\n"
        self.write_private(land / "profile.state", profile)
        self.write_private(land / "world.state", world)
        self.write_private(land / "desktop.conf", b"debug_menu=true\n")
        self.write_private(
            land / "bindings.conf",
            b"study.terminal = app kilix\n",
        )

        cap = self.layout.legacy_provider_root("kilix-cap")
        self.write_private(
            cap / "config",
            b"mail_target=thunderbird\nweb_home=https://example.test/start\n",
        )

        category_bytes: dict[str, bytes] = {}
        for category, name in (
            ("config", "nostalgia.json"),
            ("state", "shell.state"),
            ("data", "briefcase.bin"),
            ("cache", "thumbnail.bin"),
            ("session", "frame.bin"),
        ):
            data = f"{category}-bytes\x00".encode("utf-8")
            category_bytes[category] = data
            self.write_private(
                self.layout.legacy_95_category(category) / name, data
            )

        self.write_private(
            self.layout.legacy_settings,
            b"# shared settings\nKILIX_DESKTOP_PROVIDER=kilix-tui\nunknown=yes\n",
        )
        self.write_private(
            self.layout.legacy_kilix_environment,
            b"export KILIX_DESKTOP_PROVIDER=kilix-tui\nKEEP_ME=1\n",
        )
        return {"profile": profile, "world": world, **category_bytes}

    def migrate_all(self) -> list[dict[str, object]]:
        return [
            self.store.migrate(provider, "0.2.0", dry_run=False)
            for provider in MIGRATION_ORDER
        ]

    def test_fresh_reads_and_dry_runs_have_no_side_effects(self) -> None:
        before = self.snapshot()
        self.assertEqual(self.store.authority(), "legacy")
        self.assertEqual(
            self.store.config_get("kilix-tui")["values"], {}
        )
        report = self.store.migrate(
            "kilix-land-desktop", "0.2.0", dry_run=True
        )
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["state"], "planned")
        self.assertEqual(report["authoritative_store"], "legacy")
        self.assertEqual(self.snapshot(), before)

    def test_broad_or_relative_storage_roots_are_rejected(self) -> None:
        broad = dict(self.environment, GPU_TERMINAL_HOME=self.environment["HOME"])
        with self.assertRaisesRegex(AuthorityError, "dedicated storage"):
            Layout.from_environment(broad)
        relative = dict(self.environment, XDG_STATE_HOME="relative/state")
        with self.assertRaisesRegex(AuthorityError, "must be an absolute path"):
            Layout.from_environment(relative)
        provider = dict(self.environment, KILIX95_STATE_HOME=self.environment["HOME"])
        layout = Layout.from_environment(provider)
        with self.assertRaisesRegex(AuthorityError, "dedicated provider"):
            layout.legacy_95_category("state")

    def test_legacy_config_round_trip_preserves_unknown_values_and_modes(self) -> None:
        legacy = self.layout.legacy_provider_root("kilix-cap") / "config"
        self.write_private(
            legacy,
            b"# operator comment\nfuture_native=alpha\nweb_home=https://old.test/\n",
        )
        self.store.config_set("kilix-cap", "future-option", '["one","two"]')
        self.store.config_set(
            "kilix-cap", "web_home", "https://example.test/landing"
        )
        document = self.store.config_get("kilix-cap")
        self.assertEqual(document["revision"], 2)
        self.assertEqual(document["values"]["future-option"], ["one", "two"])
        self.assertEqual(
            document["values"]["web_home"], "https://example.test/landing"
        )
        self.assertEqual(document["values"]["future_native"], "alpha")
        sidecar = self.layout.legacy_provider_sidecar("kilix-cap")
        legacy_text = legacy.read_text(encoding="utf-8")
        self.assertIn("# operator comment", legacy_text)
        self.assertIn("future_native=alpha", legacy_text)
        self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(legacy.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(sidecar.parent.stat().st_mode), 0o700)

    def test_out_of_order_migration_fails_without_opening_authority(self) -> None:
        with self.assertRaisesRegex(MigrationError, "expected kilix-land-desktop"):
            self.store.migrate("kilix-cap", "3.0.0", dry_run=False)
        self.assertEqual(self.store.authority(), "legacy")
        self.assertFalse(self.layout.migration_record.exists())

    def test_ordered_migration_flips_only_on_kilix_95_and_preserves_bytes(self) -> None:
        expected = self.seed_all_legacy_stores()
        self.store.config_set("kilix-tui", "future-option", "kept")
        reports = []
        for provider in MIGRATION_ORDER[:-1]:
            reports.append(self.store.migrate(provider, "0.2.0", dry_run=False))
            self.assertEqual(self.store.authority(), "legacy")
            self.assertEqual(reports[-1]["state"], "in-progress")
        reports.append(self.store.migrate("kilix-95", "0.2.0", dry_run=False))
        self.assertEqual(reports[-1]["state"], "completed")
        self.assertEqual(reports[-1]["authoritative_store"], "xdg")
        self.assertEqual(self.store.authority(), "xdg")
        self.assertEqual(
            self.store.config_get("kilix-cap")["values"]["mail_target"],
            "thunderbird",
        )
        self.assertEqual(
            self.store.config_get("kilix-tui")["values"]["future-option"],
            "kept",
        )
        self.assertEqual(
            (self.layout.xdg_provider_state("kilix-land-desktop") / "profile.state").read_bytes(),
            expected["profile"],
        )
        self.assertEqual(
            (self.layout.xdg_provider_state("kilix-land-desktop") / "world.state").read_bytes(),
            expected["world"],
        )
        self.assertEqual(
            (
                self.layout.xdg_provider_config_dir("kilix-land-desktop")
                / "bindings.conf"
            ).read_bytes(),
            b"study.terminal = app kilix\n",
        )
        targets = {
            "config": self.layout.xdg_provider_config_dir("kilix-95") / "nostalgia.json",
            "state": self.layout.xdg_provider_state("kilix-95") / "shell.state",
            "data": self.layout.xdg_provider_data("kilix-95") / "briefcase.bin",
            "cache": self.layout.xdg_provider_cache("kilix-95") / "thumbnail.bin",
            "session": self.layout.xdg_provider_state("kilix-95") / "session/frame.bin",
        }
        for category, path in targets.items():
            with self.subTest(category=category):
                self.assertEqual(path.read_bytes(), expected[category])
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        policy = self.store.policy_get()["values"]
        self.assertEqual(policy["default_provider"], "kilix-tui")
        record = json.loads(self.layout.migration_record.read_text(encoding="utf-8"))
        self.assertEqual(record["completed_providers"], list(MIGRATION_ORDER))

    def test_mixed_window_observes_legacy_changes_and_xdg_is_inert(self) -> None:
        self.seed_all_legacy_stores()
        self.store.migrate("kilix-land-desktop", "0.2.0", dry_run=False)
        self.store.config_set("kilix-land-desktop", "debug_menu", "false")
        self.assertFalse(
            self.store.config_get("kilix-land-desktop")["values"]["debug_menu"]
        )
        xdg = self.layout.xdg_provider_config("kilix-land-desktop")
        self.assertIn("debug_menu = true", xdg.read_text(encoding="utf-8"))
        self.assertIn(
            "debug_menu=false",
            (self.layout.legacy_provider_root("kilix-land-desktop") / "desktop.conf").read_text(
                encoding="utf-8"
            ),
        )

    def test_final_step_resynchronizes_mixed_window_changes(self) -> None:
        self.seed_all_legacy_stores()
        self.store.migrate("kilix-land-desktop", "0.2.0", dry_run=False)
        land = self.layout.legacy_provider_root("kilix-land-desktop")
        self.write_private(land / "profile.state", b"profile-after-stage\x00")
        (land / "world.state").unlink()
        self.store.config_set("kilix-land-desktop", "debug_menu", "false")

        self.store.migrate("kilix-tui", "0.2.0", dry_run=False)
        self.store.config_set("kilix-tui", "after-stage", "visible")
        self.store.migrate("kilix-cap", "3.0.0", dry_run=False)
        self.store.config_set("kilix-cap", "mail_target", "after-stage")
        self.store.policy_set("default_provider", "kilix-cap")

        report = self.store.migrate("kilix-95", "0.2.0", dry_run=False)
        self.assertEqual(report["state"], "completed")
        self.assertEqual(self.store.authority(), "xdg")
        xdg_land = self.layout.xdg_provider_state("kilix-land-desktop")
        self.assertEqual(
            (xdg_land / "profile.state").read_bytes(),
            b"profile-after-stage\x00",
        )
        self.assertFalse((xdg_land / "world.state").exists())
        self.assertFalse(
            self.store.config_get("kilix-land-desktop")["values"]["debug_menu"]
        )
        self.assertEqual(
            self.store.config_get("kilix-tui")["values"]["after-stage"],
            "visible",
        )
        self.assertEqual(
            self.store.config_get("kilix-cap")["values"]["mail_target"],
            "after-stage",
        )
        self.assertEqual(
            self.store.policy_value("default_provider"), "kilix-cap"
        )
        self.assertEqual(
            {operation["provider_id"] for operation in report["operations"]},
            set(MIGRATION_ORDER),
        )
        self.assertTrue(
            all(
                operation["phase"] == "final-sync"
                for operation in report["operations"]
                if operation["provider_id"] != "kilix-95"
            )
        )

    def test_completed_authority_ignores_later_legacy_changes(self) -> None:
        self.seed_all_legacy_stores()
        self.migrate_all()
        legacy_cap = self.layout.legacy_provider_root("kilix-cap") / "config"
        self.write_private(legacy_cap, b"mail_target=legacy-after-flip\n")
        self.assertEqual(
            self.store.config_get("kilix-cap")["values"]["mail_target"],
            "thunderbird",
        )
        self.store.config_set("kilix-cap", "mail_target", "xdg-after-flip")
        self.assertEqual(
            self.store.config_get("kilix-cap")["values"]["mail_target"],
            "xdg-after-flip",
        )
        self.assertIn("legacy-after-flip", legacy_cap.read_text(encoding="utf-8"))

    def test_default_policy_stays_consistent_and_detects_split_brain(self) -> None:
        self.seed_all_legacy_stores()
        self.store.policy_set("default_provider", "kilix-cap")
        for path in (
            self.layout.legacy_settings,
            self.layout.legacy_kilix_environment,
        ):
            self.assertIn(
                "KILIX_DESKTOP_PROVIDER=kilix-cap",
                path.read_text(encoding="utf-8"),
            )
        self.write_private(
            self.layout.legacy_kilix_environment,
            b"KILIX_DESKTOP_PROVIDER=kilix-95\n",
        )
        with self.assertRaisesRegex(AuthorityError, "disagree"):
            self.store.policy_get()

    def test_shared_settings_preserve_unknowns_before_and_after_flip(self) -> None:
        self.seed_all_legacy_stores()
        before = self.store.shared_settings_get()
        self.assertEqual(before["values"]["unknown"], "yes")
        self.store.shared_settings_update(
            {"KILIX_TRANSCRIPT": "0", "KILIX_FUTURE_SETTING": "kept"}
        )
        legacy_text = self.layout.legacy_settings.read_text(encoding="utf-8")
        self.assertIn("KILIX_TRANSCRIPT=0", legacy_text)
        self.assertIn("KILIX_FUTURE_SETTING=kept", legacy_text)
        self.migrate_all()
        migrated = self.store.shared_settings_get()
        self.assertEqual(migrated["values"]["unknown"], "yes")
        self.assertEqual(migrated["values"]["KILIX_TRANSCRIPT"], "0")
        self.assertEqual(
            migrated["values"]["KILIX_FUTURE_SETTING"], "kept"
        )
        self.store.shared_settings_update({"KILIX_TRANSCRIPT": "1"})
        self.assertEqual(
            self.store.shared_settings_get()["values"]["KILIX_TRANSCRIPT"],
            "1",
        )
        self.assertIn(
            "KILIX_TRANSCRIPT=0",
            self.layout.legacy_settings.read_text(encoding="utf-8"),
        )

    def test_interrupted_default_update_fails_closed_and_is_repairable(self) -> None:
        self.seed_all_legacy_stores()
        original = persistence._rewrite_assignment
        failed = False

        def interrupted(path, key, value):
            nonlocal failed
            if path == self.layout.legacy_kilix_environment and not failed:
                failed = True
                raise OSError(errno.ENOSPC, "simulated disk full")
            return original(path, key, value)

        with mock.patch.object(persistence, "_rewrite_assignment", interrupted):
            with self.assertRaises(OSError):
                self.store.policy_set("default_provider", "kilix-cap")
        with self.assertRaisesRegex(AuthorityError, "disagree"):
            self.store.policy_get()
        self.store.policy_set("default_provider", "kilix-cap")
        self.assertEqual(self.store.policy_value("default_provider"), "kilix-cap")

    def test_interrupted_copy_leaves_legacy_authoritative_and_can_resume(self) -> None:
        self.seed_all_legacy_stores()
        original = persistence.PersistenceStore._copy_item
        attempts = 0

        def interrupted(store, item, *, replace=False):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError(errno.ENOSPC, "simulated disk full")
            return original(store, item, replace=replace)

        with mock.patch.object(
            persistence.PersistenceStore, "_copy_item", interrupted
        ):
            with self.assertRaisesRegex(MigrationError, "migration write failed"):
                self.store.migrate(
                    "kilix-land-desktop", "0.2.0", dry_run=False
                )
        self.assertEqual(self.store.authority(), "legacy")
        failed = json.loads(
            self.layout.migration_record.read_text(encoding="utf-8")
        )
        self.assertEqual(failed["state"], "failed")
        resumed = self.store.migrate(
            "kilix-land-desktop", "0.2.0", dry_run=False
        )
        self.assertEqual(resumed["state"], "in-progress")
        self.assertEqual(self.store.authority(), "legacy")

    def test_symlinked_record_and_source_fail_closed(self) -> None:
        attacker = self.root / "attacker"
        attacker.mkdir()
        (self.layout.xdg_state).mkdir(parents=True)
        (self.layout.xdg_state / "kilix").symlink_to(attacker, target_is_directory=True)
        with self.assertRaisesRegex(AuthorityError, "symlink"):
            self.store.authority()

        self.temporary.cleanup()
        self.setUp()
        land = self.layout.legacy_provider_root("kilix-land-desktop")
        land.mkdir(parents=True)
        outside = self.root / "outside.state"
        self.write_private(outside, b"outside")
        (land / "profile.state").symlink_to(outside)
        with self.assertRaises(MigrationError):
            self.store.migrate("kilix-land-desktop", "0.2.0", dry_run=False)
        self.assertEqual(self.store.authority(), "legacy")

    def test_broken_legacy_symlink_is_not_treated_as_absent(self) -> None:
        land = self.layout.legacy_provider_root("kilix-land-desktop")
        land.mkdir(parents=True)
        (land / "profile.state").symlink_to(self.root / "missing-target")
        with self.assertRaises(MigrationError):
            self.store.migrate("kilix-land-desktop", "0.2.0", dry_run=False)

    def test_concurrent_writers_do_not_lose_values(self) -> None:
        barrier = threading.Barrier(3)
        failures: list[BaseException] = []

        def writer(key: str) -> None:
            try:
                barrier.wait()
                for value in range(10):
                    self.store.config_set("kilix-tui", key, str(value))
            except BaseException as error:  # captured for the main test thread
                failures.append(error)

        threads = [
            threading.Thread(target=writer, args=("writer-a",)),
            threading.Thread(target=writer, args=("writer-b",)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(failures)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        document = self.store.config_get("kilix-tui")
        self.assertEqual(document["revision"], 20)
        self.assertEqual(document["values"]["writer-a"], 9)
        self.assertEqual(document["values"]["writer-b"], 9)

    def test_corrupt_or_insecure_migration_record_fails_closed(self) -> None:
        self.write_private(self.layout.migration_record, b"{not-json}\n")
        with self.assertRaisesRegex(AuthorityError, "invalid migration record"):
            self.store.authority()
        self.write_private(self.layout.migration_record, b"{}\n")
        self.layout.migration_record.chmod(0o666)
        with self.assertRaisesRegex(AuthorityError, "group/world writable"):
            self.store.authority()

    def test_rollback_moves_authority_without_deleting_xdg_state(self) -> None:
        self.seed_all_legacy_stores()
        self.migrate_all()
        xdg_state = self.layout.xdg_provider_state("kilix-land-desktop") / "world.state"
        expected = xdg_state.read_bytes()
        report = self.store.rollback("0.2.0")
        self.assertEqual(report["state"], "rolled-back")
        self.assertEqual(report["authoritative_store"], "legacy")
        self.assertEqual(self.store.authority(), "legacy")
        self.assertEqual(xdg_state.read_bytes(), expected)
        self.assertEqual(
            self.store.resolved_path("kilix-95", "state"),
            self.layout.legacy_95_category("state"),
        )

    def test_python_310_fallback_reads_canonical_unknown_keys(self) -> None:
        document = {
            "provider_id": "kilix-tui",
            "revision": 7,
            "schema_version": 1,
            "values": {"future.option": ["one", "two"], "enabled": True},
        }
        encoded = persistence._toml_bytes(document).decode("utf-8")
        self.assertEqual(persistence._fallback_toml_loads(encoded), document)


if __name__ == "__main__":
    unittest.main()
