"""Thin, fail-closed bridge to the staged desktop-contract command."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
from typing import NoReturn


class BridgeUnavailable(RuntimeError):
    pass


class BridgeError(RuntimeError):
    pass


def command() -> str | None:
    candidate = os.environ.get("KILIX_DESKTOP_CONTRACT_COMMAND")
    if not candidate:
        prefix = os.environ.get("KILIX_DESKTOP_SDK_PREFIX")
        if prefix:
            if not os.path.isabs(prefix):
                return None
            candidate = os.path.join(prefix, "bin", "kilix-desktop-contract")
    if not candidate or not os.path.isabs(candidate):
        return None
    try:
        current = os.path.sep
        for part in os.path.abspath(candidate).split(os.path.sep)[1:]:
            current = os.path.join(current, part)
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode):
                return None
    except OSError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid not in {0, os.geteuid()}
        or info.st_mode & 0o022
        or not os.access(candidate, os.X_OK)
    ):
        return None
    return os.path.abspath(candidate)


def available() -> bool:
    return command() is not None


def required() -> bool:
    return bool(
        os.environ.get("KILIX_DESKTOP_CONTRACT_COMMAND")
        or os.environ.get("KILIX_DESKTOP_SDK_PREFIX")
        or migration_record_present()
    )


def exec_storage(*arguments: str) -> NoReturn:
    executable = command()
    if executable is None:
        raise BridgeUnavailable("the staged desktop-contract command is unavailable")
    try:
        os.execve(
            executable,
            [executable, "storage", *arguments],
            dict(os.environ),
        )
    except OSError as error:
        raise BridgeError(f"cannot execute desktop-contract storage: {error}") from error


def run_storage(*arguments: str) -> str:
    executable = command()
    if executable is None:
        raise BridgeUnavailable("the staged desktop-contract command is unavailable")
    try:
        result = subprocess.run(
            [executable, "storage", *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        raise BridgeError(f"desktop-contract storage failed: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise BridgeError(f"desktop-contract storage refused the request: {detail}")
    if result.stderr:
        raise BridgeError("desktop-contract storage wrote unexpected stderr")
    return result.stdout


def resolved_path(provider_id: str, category: str) -> str:
    output = run_storage("path", provider_id, category)
    if not output.endswith("\n") or output.endswith("\n\n"):
        raise BridgeError("desktop-contract path is not one canonical line")
    value = output[:-1]
    if not value or not os.path.isabs(value) or any(ord(ch) < 0x20 for ch in value):
        raise BridgeError("desktop-contract returned an invalid path")
    return os.path.abspath(value)


def migration_record_present() -> bool:
    home = os.environ.get("HOME") or str(Path.home())
    state = os.environ.get("XDG_STATE_HOME") or os.path.join(home, ".local/state")
    if not os.path.isabs(state):
        return True
    path = os.path.join(state, "kilix", "desktops", "migration-v1.json")
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True
