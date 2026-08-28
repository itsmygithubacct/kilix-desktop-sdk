"""Command-line interface for contract helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .actions import ActionError, parse_action
from .catalog import sanitize_catalog_text
from .conformance import ConformanceError, run_conformance
from .jsonio import DocumentError, load_json
from .persistence import (
    PersistenceError,
    PersistenceStore,
    emit_json,
    emit_value,
    provider_config_schema,
)
from .validation import errors_for, validators


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kilix-desktop-contract")
    commands = parser.add_subparsers(dest="command", required=True)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("kind")
    validate_parser.add_argument("document", type=Path)
    action_parser = commands.add_parser("parse-action")
    action_parser.add_argument("action")
    sanitize_parser = commands.add_parser("sanitize")
    sanitize_parser.add_argument("text")
    conformance_parser = commands.add_parser("conformance")
    conformance_parser.add_argument("--adapter-stage", action="store_true")
    conformance_parser.add_argument("--kilix-home", type=Path, required=True)
    conformance_parser.add_argument(
        "--contract-command", type=Path, required=True
    )
    conformance_parser.add_argument("--state-library", type=Path, required=True)
    conformance_parser.add_argument("--land-assets", type=Path, required=True)
    conformance_parser.add_argument("provider", nargs=argparse.REMAINDER)

    storage_parser = commands.add_parser("storage")
    storage_commands = storage_parser.add_subparsers(
        dest="storage_command", required=True
    )
    schema_parser = storage_commands.add_parser("schema")
    schema_parser.add_argument("provider_id")
    get_parser = storage_commands.add_parser("get")
    get_parser.add_argument("provider_id")
    get_parser.add_argument("key", nargs="?")
    set_parser = storage_commands.add_parser("set")
    set_parser.add_argument("provider_id")
    set_parser.add_argument("key")
    set_parser.add_argument("value")
    value_parser = storage_commands.add_parser("value")
    value_parser.add_argument("provider_id")
    value_parser.add_argument("key")
    migrate_parser = storage_commands.add_parser("migrate")
    migrate_parser.add_argument("provider_id")
    migrate_parser.add_argument("--from", dest="from_version", required=True)
    migrate_parser.add_argument("--dry-run", action="store_true")
    path_parser = storage_commands.add_parser("path")
    path_parser.add_argument("provider_id")
    path_parser.add_argument("category")
    authority_parser = storage_commands.add_parser("authority")
    authority_parser.set_defaults(storage_command="authority")
    storage_commands.add_parser("policy-path")
    policy_parser = storage_commands.add_parser("policy")
    policy_commands = policy_parser.add_subparsers(
        dest="policy_command", required=True
    )
    policy_get = policy_commands.add_parser("get")
    policy_get.add_argument("key", nargs="?")
    policy_value = policy_commands.add_parser("value")
    policy_value.add_argument("key")
    policy_set = policy_commands.add_parser("set")
    policy_set.add_argument("key")
    policy_set.add_argument("value")
    shared_parser = storage_commands.add_parser("shared-settings")
    shared_commands = shared_parser.add_subparsers(
        dest="shared_command", required=True
    )
    shared_commands.add_parser("get")
    shared_update = shared_commands.add_parser("update")
    shared_update.add_argument("changes")
    rollback_parser = storage_commands.add_parser("rollback")
    rollback_parser.add_argument("--from", dest="from_version", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "validate":
            document = load_json(arguments.document)
            errors = errors_for(arguments.kind, document, validators())
            if errors:
                for error in errors:
                    print(error, file=sys.stderr)
                return 3
            return 0
        if arguments.command == "parse-action":
            print(json.dumps(parse_action(arguments.action).as_dict(), sort_keys=True))
            return 0
        if arguments.command == "sanitize":
            print(sanitize_catalog_text(arguments.text))
            return 0
        if arguments.command == "conformance":
            provider = list(arguments.provider)
            if provider and provider[0] == "--":
                provider.pop(0)
            report = run_conformance(
                provider,
                adapter_stage=arguments.adapter_stage,
                kilix_home=arguments.kilix_home,
                contract_command=arguments.contract_command,
                state_library=arguments.state_library,
                land_assets=arguments.land_assets,
            )
            stage = "adapter-stage" if report.adapter_stage else "final"
            print(
                f"PASS {report.provider_id}: {len(report.checks)} "
                f"non-interactive checks ({stage})"
            )
            return 0
        if arguments.command == "storage":
            store = PersistenceStore()
            if arguments.storage_command == "schema":
                emit_json(provider_config_schema(arguments.provider_id))
                return 0
            if arguments.storage_command == "get":
                emit_json(store.config_get(arguments.provider_id, arguments.key))
                return 0
            if arguments.storage_command == "set":
                store.config_set(
                    arguments.provider_id, arguments.key, arguments.value
                )
                return 0
            if arguments.storage_command == "value":
                emit_value(
                    store.config_value(arguments.provider_id, arguments.key)
                )
                return 0
            if arguments.storage_command == "migrate":
                emit_json(
                    store.migrate(
                        arguments.provider_id,
                        arguments.from_version,
                        dry_run=arguments.dry_run,
                    )
                )
                return 0
            if arguments.storage_command == "path":
                print(
                    store.resolved_path(
                        arguments.provider_id, arguments.category
                    )
                )
                return 0
            if arguments.storage_command == "authority":
                print(store.authority())
                return 0
            if arguments.storage_command == "policy-path":
                print(store.policy_path())
                return 0
            if arguments.storage_command == "policy":
                if arguments.policy_command == "get":
                    emit_json(store.policy_get(arguments.key))
                    return 0
                if arguments.policy_command == "value":
                    emit_value(store.policy_value(arguments.key))
                    return 0
                store.policy_set(arguments.key, arguments.value)
                return 0
            if arguments.storage_command == "shared-settings":
                if arguments.shared_command == "get":
                    emit_json(store.shared_settings_get())
                    return 0
                changes = json.loads(arguments.changes)
                if not isinstance(changes, dict):
                    raise ValueError("shared settings update must be a JSON object")
                store.shared_settings_update(changes)
                return 0
            if arguments.storage_command == "rollback":
                emit_json(store.rollback(arguments.from_version))
                return 0
    except (
        ActionError,
        ConformanceError,
        DocumentError,
        PersistenceError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return getattr(error, "exit_status", 3)
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
