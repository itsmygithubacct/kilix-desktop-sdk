"""Schema and semantic validation for protocol-v1 documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .actions import ActionError, parse_action
from .jsonio import load_json


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATHS = {
    "action": PACKAGE_ROOT / "schemas" / "kilix.desktop.action-v1.schema.json",
    "catalog-entry": PACKAGE_ROOT
    / "schemas"
    / "kilix.desktop.catalog-entry-v1.schema.json",
    "config-schema": PACKAGE_ROOT
    / "schemas"
    / "kilix.desktop.config-schema-v1.schema.json",
    "migration": PACKAGE_ROOT
    / "schemas"
    / "kilix.desktop.migration-v1.schema.json",
    "provider-check": PACKAGE_ROOT
    / "schemas"
    / "kilix.desktop.provider-check-v1.schema.json",
    "provider-config": PACKAGE_ROOT
    / "schemas"
    / "kilix.desktop.provider-config-v1.schema.json",
    "provider-description": PACKAGE_ROOT
    / "schemas"
    / "kilix.desktop.provider-description-v1.schema.json",
}


class ContractValidationError(ValueError):
    """A document violates schema or protocol-v1 semantics."""


def validators() -> dict[str, Draft202012Validator]:
    result: dict[str, Draft202012Validator] = {}
    schema_store: dict[str, dict[str, Any]] = {}
    for path in SCHEMA_PATHS.values():
        schema = load_json(path)
        Draft202012Validator.check_schema(schema)
        schema_store[schema["$id"]] = schema
    registry = None
    try:
        from referencing import Registry, Resource

        registry = Registry().with_resources(
            (identity, Resource.from_contents(schema))
            for identity, schema in schema_store.items()
        )
    except ImportError:
        registry = None
    for name, path in SCHEMA_PATHS.items():
        schema = load_json(path)
        kwargs: dict[str, Any] = {"format_checker": FormatChecker()}
        if registry is not None:
            kwargs["registry"] = registry
        result[name] = Draft202012Validator(schema, **kwargs)
    return result


def _schema_errors(
    document: Any, validator: Draft202012Validator
) -> list[str]:
    return [
        f"schema at /{'/'.join(map(str, error.absolute_path))}: {error.message}"
        for error in sorted(
            validator.iter_errors(document),
            key=lambda item: list(item.absolute_path),
        )
    ]


def _semantic_errors(kind: str, document: Any) -> list[str]:
    if not isinstance(document, dict):
        return []
    errors: list[str] = []
    if kind == "action":
        try:
            parsed = parse_action(f"{document['verb']}:{document['payload']}")
            if parsed.as_dict() != document:
                errors.append("action document is not the canonical typed request")
        except (ActionError, KeyError) as error:
            errors.append(f"action semantics: {error}")
    elif kind == "config-schema":
        try:
            Draft202012Validator.check_schema(document)
        except Exception as error:
            errors.append(f"provider config is not a valid Draft 2020-12 schema: {error}")
        provider_id = document.get("x-kilix-provider-id")
        expected_id = f"https://schemas.kilix.org/desktop/config/{provider_id}/v1"
        if provider_id and document.get("$id") != expected_id:
            errors.append("provider config $id does not match x-kilix-provider-id")
    elif kind == "migration":
        state = document.get("state")
        authority = document.get("authoritative_store")
        dry_run = document.get("dry_run")
        if dry_run and state != "planned":
            errors.append("dry-run migration state must be planned")
        if state == "completed" and authority != "xdg":
            errors.append("completed migration must make xdg authoritative")
        if state in {"failed", "in-progress", "planned", "rolled-back"} and authority != "legacy":
            errors.append(f"{state} migration must keep legacy authoritative")
        if dry_run and any(
            operation.get("status") != "planned"
            for operation in document.get("operations", [])
            if isinstance(operation, dict)
        ):
            errors.append("dry-run operations must all be planned")
    elif kind == "provider-check":
        checks = document.get("checks", [])
        required_bad = any(
            isinstance(check, dict)
            and check.get("required") is True
            and check.get("status") in {"fail", "unavailable"}
            for check in checks
        )
        any_non_pass = any(
            isinstance(check, dict) and check.get("status") != "pass"
            for check in checks
        )
        status = document.get("status")
        if required_bad and status != "unavailable":
            errors.append("a required failed/unavailable check requires unavailable")
        elif not required_bad and any_non_pass and status != "degraded":
            errors.append("optional non-pass checks require degraded")
        elif not any_non_pass and status != "ready":
            errors.append("all passing checks require ready")
    elif kind == "provider-description":
        capabilities = document.get("capabilities", {})
        for capability in document.get("required_capabilities", []):
            value = capabilities.get(capability)
            available = value is True or (
                isinstance(value, dict) and value.get("available") is True
            )
            if not available:
                errors.append(
                    f"required capability is not available: {capability}"
                )
    return errors


def errors_for(
    kind: str,
    document: Any,
    available: dict[str, Draft202012Validator] | None = None,
) -> list[str]:
    if available is None:
        available = validators()
    if kind not in available:
        return [f"unknown document kind: {kind}"]
    errors = _schema_errors(document, available[kind])
    if not errors:
        errors.extend(_semantic_errors(kind, document))
    return errors


def validate(
    kind: str,
    document: Any,
    available: dict[str, Draft202012Validator] | None = None,
) -> None:
    errors = errors_for(kind, document, available)
    if errors:
        raise ContractValidationError("; ".join(errors))
