"""Helpers for the Kilix desktop-provider protocol v1."""

from .actions import Action, ActionError, parse_action
from .catalog import sanitize_catalog_entry, sanitize_catalog_text
from .constants import (
    ACTION_VERBS,
    CAPABILITIES,
    CONTRACT_VERSION,
    DISPLAY_MODES,
    EXIT_STATUSES,
)

__all__ = [
    "ACTION_VERBS",
    "CAPABILITIES",
    "CONTRACT_VERSION",
    "DISPLAY_MODES",
    "EXIT_STATUSES",
    "Action",
    "ActionError",
    "parse_action",
    "sanitize_catalog_entry",
    "sanitize_catalog_text",
]
