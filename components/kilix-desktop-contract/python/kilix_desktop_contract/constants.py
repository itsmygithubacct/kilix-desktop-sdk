"""Closed protocol-v1 vocabulary."""

from __future__ import annotations


CONTRACT_VERSION = 1

ACTION_VERBS = (
    "app.open",
    "desktop.launch",
    "desktop.make-default",
    "document.open",
    "game.play",
    "power.request",
    "session.open",
    "settings.open",
    "url.open",
)

CAPABILITIES = (
    "audio",
    "headless_screenshot",
    "keyboard",
    "launcher",
    "mouse",
    "reduced_motion",
    "settings",
)

DISPLAY_MODES = (
    "kitty-graphics",
    "terminal-text",
    "x11",
)

POWER_ACTIONS = (
    "logout",
    "reboot",
    "shutdown",
    "suspend",
)

EXIT_STATUSES = {
    "ok": 0,
    "usage": 2,
    "invalid-request": 3,
    "unavailable": 4,
    "incompatible-contract": 5,
    "migration-failed": 6,
    "internal-error": 70,
}

DEADLINES_SECONDS = {
    "describe": 2,
    "check": 5,
    "config": 5,
    "migrate": 30,
    "screenshot": 30,
    "shutdown_grace": 3,
}
