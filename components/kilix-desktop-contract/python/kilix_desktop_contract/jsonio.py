"""Bounded JSON loading with duplicate-key rejection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MAX_DOCUMENT_BYTES = 4 * 1024 * 1024


class DocumentError(ValueError):
    """A JSON document cannot be used as a contract document."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, *, max_bytes: int = MAX_DOCUMENT_BYTES) -> Any:
    size = path.stat().st_size
    if size > max_bytes:
        raise DocumentError(f"document exceeds {max_bytes} bytes")
    with path.open("r", encoding="utf-8") as handle:
        try:
            return json.load(handle, object_pairs_hook=_reject_duplicates)
        except UnicodeDecodeError as error:
            raise DocumentError("document is not valid UTF-8") from error
        except json.JSONDecodeError as error:
            raise DocumentError(f"invalid JSON: {error}") from error


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
