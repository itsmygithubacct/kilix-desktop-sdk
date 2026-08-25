"""Sanitize untrusted catalog text before a provider renders it."""

from __future__ import annotations

from collections.abc import Mapping
import unicodedata
from typing import Any


DEFAULT_MAX_CHARS = 256
DEFAULT_MAX_BYTES = 1024

_STRING_LIMITS = {
    "catalog_id": (256, 512),
    "category": (64, 256),
    "comment": (256, 1024),
    "name": (128, 512),
    "path": (1024, 4096),
    "title": (128, 512),
}


def _consume_csi(value: str, index: int) -> int:
    while index < len(value):
        codepoint = ord(value[index])
        index += 1
        if 0x40 <= codepoint <= 0x7E:
            break
    return index


def _consume_string_control(value: str, index: int) -> int:
    while index < len(value):
        if value[index] == "\x07":
            return index + 1
        if value[index] == "\x9c":
            return index + 1
        if value[index] == "\x1b" and index + 1 < len(value) and value[index + 1] == "\\":
            return index + 2
        index += 1
    return index


def _without_terminal_controls(value: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        codepoint = ord(character)
        if character == "\x1b":
            if index + 1 >= len(value):
                break
            introducer = value[index + 1]
            index += 2
            if introducer == "[":
                index = _consume_csi(value, index)
            elif introducer in {"]", "P", "X", "^", "_"}:
                index = _consume_string_control(value, index)
            continue
        if codepoint == 0x9B:
            index = _consume_csi(value, index + 1)
            continue
        if codepoint in {0x90, 0x98, 0x9D, 0x9E, 0x9F}:
            index = _consume_string_control(value, index + 1)
            continue
        category = unicodedata.category(character)
        if character.isspace():
            output.append(" ")
        elif category not in {"Cc", "Cf", "Cs"}:
            output.append(character)
        index += 1
    return "".join(output)


def _bounded(value: str, *, max_chars: int, max_bytes: int) -> str:
    output: list[str] = []
    used_bytes = 0
    for character in value:
        if len(output) >= max_chars:
            break
        encoded = character.encode("utf-8")
        if used_bytes + len(encoded) > max_bytes:
            break
        output.append(character)
        used_bytes += len(encoded)
    return "".join(output)


def sanitize_catalog_text(
    value: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """Return inert, normalized and bounded text suitable for terminal display."""

    if not isinstance(value, str):
        raise TypeError("catalog text must be str")
    if max_chars < 0 or max_bytes < 0:
        raise ValueError("catalog bounds must be non-negative")
    value = unicodedata.normalize("NFC", _without_terminal_controls(value))
    value = " ".join(value.split())
    return _bounded(value, max_chars=max_chars, max_bytes=max_bytes).rstrip()


def _sanitize_value(value: Any, key: str = "") -> Any:
    if isinstance(value, str):
        max_chars, max_bytes = _STRING_LIMITS.get(
            key, (DEFAULT_MAX_CHARS, DEFAULT_MAX_BYTES)
        )
        return sanitize_catalog_text(
            value, max_chars=max_chars, max_bytes=max_bytes
        )
    if isinstance(value, list):
        item_key = "category" if key == "categories" else ""
        return [_sanitize_value(item, item_key) for item in value]
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise TypeError("catalog object keys must be str")
            clean_key = sanitize_catalog_text(
                raw_key, max_chars=128, max_bytes=256
            )
            if not clean_key:
                raise ValueError("catalog object key became empty after sanitization")
            if clean_key in sanitized:
                raise ValueError("catalog keys collide after sanitization")
            sanitized[clean_key] = _sanitize_value(item, clean_key)
        return sanitized
    return value


def sanitize_catalog_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize every string reachable from one catalog entry."""

    if not isinstance(entry, Mapping):
        raise TypeError("catalog entry must be a mapping")
    result = _sanitize_value(entry)
    assert isinstance(result, dict)
    return result
