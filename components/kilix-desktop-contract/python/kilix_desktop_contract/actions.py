"""Parse untrusted action strings into typed protocol-v1 requests."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import urlsplit

from .constants import ACTION_VERBS, POWER_ACTIONS


MAX_ACTION_CHARS = 4096
MAX_ACTION_BYTES = 4096
_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:[._/-][a-z0-9]+)*$")
_IDENTIFIER_VERBS = frozenset(
    {
        "app.open",
        "desktop.launch",
        "desktop.make-default",
        "game.play",
        "session.open",
        "settings.open",
    }
)


class ActionError(ValueError):
    """The action is not safe or valid under protocol v1."""


@dataclass(frozen=True)
class Action:
    """A validated action split at its first colon."""

    verb: str
    payload: str
    schema_version: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "payload": self.payload,
            "schema_version": self.schema_version,
            "verb": self.verb,
        }


def _contains_control(value: str) -> bool:
    return any(unicodedata.category(character) in {"Cc", "Cs"} for character in value)


def _validate_https_url(payload: str) -> None:
    try:
        parsed = urlsplit(payload)
        port = parsed.port
    except ValueError as error:
        raise ActionError("url.open payload is not a valid URL") from error
    if parsed.scheme != "https" or not parsed.hostname:
        raise ActionError("url.open requires an https URL with a host")
    if parsed.username is not None or parsed.password is not None:
        raise ActionError("url.open refuses embedded credentials")
    if port is not None and not 1 <= port <= 65535:
        raise ActionError("url.open port is outside 1..65535")


def parse_action(raw: str) -> Action:
    """Validate `verb:payload`, splitting only at the first colon."""

    if not isinstance(raw, str):
        raise ActionError("action must be text")
    if len(raw) > MAX_ACTION_CHARS or len(raw.encode("utf-8")) > MAX_ACTION_BYTES:
        raise ActionError("action exceeds the 4096-character/byte bound")
    if _contains_control(raw):
        raise ActionError("action contains a control or invalid Unicode code point")
    verb, separator, payload = raw.partition(":")
    if not separator:
        raise ActionError("action must contain a colon")
    if verb not in ACTION_VERBS:
        raise ActionError(f"unknown action verb: {verb or '<empty>'}")
    if not payload:
        raise ActionError("action payload must not be empty")
    if verb in _IDENTIFIER_VERBS and _IDENTIFIER.fullmatch(payload) is None:
        raise ActionError(f"{verb} payload is not a catalog identifier")
    if verb == "power.request" and payload not in POWER_ACTIONS:
        raise ActionError("power.request payload is not a protocol-v1 power action")
    if verb == "url.open":
        _validate_https_url(payload)
    return Action(verb=verb, payload=payload)
