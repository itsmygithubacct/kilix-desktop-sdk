"""Single-authority desktop configuration and migration support.

The legacy ``~/.local/gpu_terminal`` tree remains authoritative until the
ordered four-provider migration record is committed as complete.  XDG state
may be populated before that point, but it is inert.  This module is the only
place that resolves that authority, writes desktop configuration, or advances
the migration record.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Iterator, Mapping, Sequence

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - exercised by the Python 3.10 gate
    tomllib = None  # type: ignore[assignment]

from .validation import validate


CONFIG_MAX_BYTES = 1024 * 1024
STATE_FILE_MAX_BYTES = 1024 * 1024 * 1024
MIGRATION_ORDER = (
    "kilix-land-desktop",
    "kilix-tui",
    "kilix-cap",
    "kilix-95",
)
SEPARATE_CONSUMERS = ("kilix-icewm",)
SUPPORTED_PROVIDERS = (*MIGRATION_ORDER, *SEPARATE_CONSUMERS)
DEFAULT_POLICY = {
    "default_provider": "kilix-95",
    "fallback_order": ["kilix-95", "kilix-tui", "kilix-cap", "kilix-land-desktop"],
}

_PROVIDER_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_CONFIG_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_BARE_TOML_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_ENV_PROVIDER = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class PersistenceError(RuntimeError):
    """Persistence cannot safely satisfy a request."""

    exit_status = 70


class ConfigurationError(PersistenceError):
    """A configuration request or value is invalid."""

    exit_status = 3


class AuthorityError(PersistenceError):
    """The authoritative store cannot be determined safely."""

    exit_status = 5


class UnavailableError(PersistenceError):
    """A requested optional value is not configured."""

    exit_status = 4


class MigrationError(PersistenceError):
    """A migration or rollback operation failed closed."""

    exit_status = 6


def _absolute_path(value: str, label: str) -> Path:
    if not value or "\0" in value:
        raise AuthorityError(f"{label} is empty or contains NUL")
    expanded = os.path.expanduser(value)
    if not os.path.isabs(expanded):
        raise AuthorityError(f"{label} must be an absolute path")
    return Path(os.path.abspath(expanded))


@dataclass(frozen=True)
class Layout:
    """All configured legacy and XDG roots for one process environment."""

    home: Path
    legacy_root: Path
    xdg_config: Path
    xdg_state: Path
    xdg_data: Path
    xdg_cache: Path
    environment: Mapping[str, str]

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "Layout":
        values = dict(os.environ if environment is None else environment)
        home = _absolute_path(values.get("HOME", str(Path.home())), "HOME")
        legacy = _absolute_path(
            values.get("GPU_TERMINAL_HOME", str(home / ".local/gpu_terminal")),
            "GPU_TERMINAL_HOME",
        )
        config = _absolute_path(
            values.get("XDG_CONFIG_HOME", str(home / ".config")),
            "XDG_CONFIG_HOME",
        )
        state = _absolute_path(
            values.get("XDG_STATE_HOME", str(home / ".local/state")),
            "XDG_STATE_HOME",
        )
        data = _absolute_path(
            values.get("XDG_DATA_HOME", str(home / ".local/share")),
            "XDG_DATA_HOME",
        )
        cache = _absolute_path(
            values.get("XDG_CACHE_HOME", str(home / ".cache")),
            "XDG_CACHE_HOME",
        )
        if legacy in {Path(os.path.sep), home}:
            raise AuthorityError(
                "GPU_TERMINAL_HOME must be a dedicated storage directory"
            )
        return cls(home, legacy, config, state, data, cache, values)

    def _dedicated_provider_path(
        self, path: Path, label: str, *additional: Path
    ) -> Path:
        if path in {Path(os.path.sep), self.home, self.legacy_root, *additional}:
            raise AuthorityError(f"{label} must be a dedicated provider path")
        return path

    @property
    def migration_record(self) -> Path:
        return self.xdg_state / "kilix/desktops/migration-v1.json"

    @property
    def migration_lock(self) -> Path:
        return self.xdg_state / "kilix/desktops/migration-v1.lock"

    @property
    def xdg_policy(self) -> Path:
        return self.xdg_config / "kilix/desktop.toml"

    def xdg_provider_config(self, provider_id: str) -> Path:
        return self.xdg_config / "kilix/desktops" / f"{provider_id}.toml"

    def xdg_provider_config_dir(self, provider_id: str) -> Path:
        return self.xdg_config / "kilix/desktops" / provider_id

    def xdg_provider_state(self, provider_id: str) -> Path:
        return self.xdg_state / "kilix/desktops" / provider_id

    def xdg_provider_data(self, provider_id: str) -> Path:
        return self.xdg_data / "kilix/desktops" / provider_id

    def xdg_provider_cache(self, provider_id: str) -> Path:
        return self.xdg_cache / "kilix/desktops" / provider_id

    def legacy_provider_root(self, provider_id: str) -> Path:
        names = {
            "kilix-95": "KILIX95_STORAGE_HOME",
            "kilix-cap": "KILIX_CAP_CONFIG_HOME",
            "kilix-land-desktop": "KILIX_LAND_DESKTOP_CONFIG_HOME",
            "kilix-icewm": "KILIX_ICEWM_STORAGE_HOME",
        }
        defaults = {
            "kilix-95": self.legacy_root / "kilix-95",
            "kilix-cap": self.legacy_root / "kilix-cap",
            "kilix-land-desktop": self.legacy_root / "kilix-land-desktop",
            "kilix-tui": self.legacy_root / "kilix-tui",
            "kilix-icewm": self.legacy_root / "kilix-icewm",
        }
        override_name = names.get(provider_id)
        if override_name and self.environment.get(override_name):
            return self._dedicated_provider_path(
                _absolute_path(self.environment[override_name], override_name),
                override_name,
            )
        return self._dedicated_provider_path(
            defaults[provider_id], f"legacy {provider_id} root"
        )

    def legacy_95_category(self, category: str) -> Path:
        overrides = {
            "config": "KILIX95_CONFIG_HOME",
            "state": "KILIX95_STATE_HOME",
            "data": "KILIX95_DATA_HOME",
            "cache": "KILIX95_CACHE_HOME",
            "session": "KILIX95_SESSION_HOME",
        }
        name = overrides[category]
        provider_root = self.legacy_provider_root("kilix-95")
        if self.environment.get(name):
            return self._dedicated_provider_path(
                _absolute_path(self.environment[name], name),
                name,
                provider_root,
            )
        return provider_root / category

    @property
    def legacy_settings(self) -> Path:
        value = self.environment.get("GPU_TERMINAL_SETTINGS_FILE")
        return (
            _absolute_path(value, "GPU_TERMINAL_SETTINGS_FILE")
            if value
            else self.legacy_root / "settings.conf"
        )

    @property
    def legacy_kilix_environment(self) -> Path:
        config_home = self.environment.get("KILIX_CONFIG_HOME")
        base = (
            _absolute_path(config_home, "KILIX_CONFIG_HOME")
            if config_home
            else self.legacy_root / "kilix/config"
        )
        return base / "kilix.env"

    @property
    def legacy_policy_sidecar(self) -> Path:
        return self.legacy_root / ".kilix-desktop-policy.toml"

    def legacy_provider_sidecar(self, provider_id: str) -> Path:
        return self.legacy_provider_root(provider_id) / ".kilix-desktop-provider.toml"


def _require_provider(provider_id: str) -> None:
    if provider_id not in SUPPORTED_PROVIDERS or not _PROVIDER_ID.fullmatch(
        provider_id
    ):
        raise ConfigurationError(f"unsupported desktop provider: {provider_id}")


def _existing_prefixes(path: Path) -> Iterator[Path]:
    current = Path(path.anchor)
    yield current
    for part in path.parts[1:]:
        current = current / part
        yield current


def _refuse_symlink_components(path: Path) -> None:
    for candidate in _existing_prefixes(path):
        try:
            status = candidate.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(status.st_mode):
            raise AuthorityError(f"storage path contains a symlink: {candidate}")


def _ensure_private_directory(path: Path) -> None:
    _refuse_symlink_components(path)
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    _refuse_symlink_components(cursor)
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode) or stat.S_ISLNK(status.st_mode):
            raise AuthorityError(f"storage path is not a real directory: {directory}")
        if status.st_uid != os.geteuid():
            raise AuthorityError(f"storage directory is not user-owned: {directory}")
        os.chmod(directory, 0o700)
    status = path.lstat()
    if not stat.S_ISDIR(status.st_mode) or stat.S_ISLNK(status.st_mode):
        raise AuthorityError(f"storage path is not a real directory: {path}")
    if status.st_uid != os.geteuid():
        raise AuthorityError(f"storage directory is not user-owned: {path}")
    os.chmod(path, 0o700)


def _read_secure_bytes(
    path: Path, *, maximum: int, missing_ok: bool = False
) -> bytes | None:
    _refuse_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise AuthorityError(f"storage record is not a regular file: {path}")
        if status.st_uid != os.geteuid():
            raise AuthorityError(f"storage record is not user-owned: {path}")
        if status.st_mode & 0o022:
            raise AuthorityError(f"storage record is group/world writable: {path}")
        if status.st_size > maximum:
            raise AuthorityError(f"storage record exceeds {maximum} bytes: {path}")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > maximum:
            raise AuthorityError(f"storage record exceeds {maximum} bytes: {path}")
        return data
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        try:
            count = os.write(descriptor, data[offset:])
        except OSError as error:
            if error.errno == errno.EINTR:
                continue
            raise
        if count <= 0:
            raise OSError(errno.EIO, "short atomic configuration write")
        offset += count


_TEMPORARY_COUNTER = 0


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    global _TEMPORARY_COUNTER
    _ensure_private_directory(path.parent)
    _refuse_symlink_components(path)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    directory = os.open(path.parent, directory_flags)
    descriptor = -1
    temporary = ""
    try:
        try:
            current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None and not stat.S_ISREG(current.st_mode):
            raise AuthorityError(f"atomic target is not a regular file: {path}")
        for _ in range(64):
            _TEMPORARY_COUNTER += 1
            temporary = f".{path.name}.tmp.{os.getpid()}.{_TEMPORARY_COUNTER}"
            try:
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    mode,
                    dir_fd=directory,
                )
                break
            except FileExistsError:
                continue
        if descriptor < 0:
            raise OSError(errno.EEXIST, "cannot allocate atomic temporary file")
        _write_all(descriptor, data)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temporary,
            path.name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
        temporary = ""
        os.fsync(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
        os.close(directory)


def _fsync_directory(path: Path) -> None:
    _refuse_symlink_components(path)
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityError(f"migration record repeats JSON key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path, *, missing_ok: bool = False) -> dict[str, Any] | None:
    data = _read_secure_bytes(path, maximum=CONFIG_MAX_BYTES, missing_ok=missing_ok)
    if data is None:
        return None
    try:
        text = data.decode("utf-8")
        document = json.loads(text, object_pairs_hook=_json_pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise AuthorityError(f"invalid migration record {path}: {error}") from error
    if not isinstance(document, dict):
        raise AuthorityError(f"migration record is not an object: {path}")
    return document


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _toml_key(key: str) -> str:
    return key if _BARE_TOML_KEY.fullmatch(key) else json.dumps(key, ensure_ascii=False)


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        if "\0" in value or any(
            ord(character) < 0x20 and character not in "\t"
            for character in value
        ):
            raise ConfigurationError("configuration string contains a control character")
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ConfigurationError("configuration number is not finite")
        return repr(value)
    if isinstance(value, list):
        if any(isinstance(item, (dict, list)) for item in value):
            raise ConfigurationError("nested configuration arrays are unsupported")
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise ConfigurationError(
        f"unsupported configuration value type: {type(value).__name__}"
    )


def _toml_lines(table: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> list[str]:
    scalars = sorted(key for key, value in table.items() if not isinstance(value, dict))
    children = sorted(key for key, value in table.items() if isinstance(value, dict))
    lines = [f"{_toml_key(key)} = {_toml_value(table[key])}" for key in scalars]
    for key in children:
        if lines:
            lines.append("")
        child_prefix = (*prefix, key)
        lines.append("[" + ".".join(_toml_key(item) for item in child_prefix) + "]")
        lines.extend(_toml_lines(table[key], child_prefix))
    return lines


def _toml_bytes(document: Mapping[str, Any]) -> bytes:
    text = "\n".join(_toml_lines(document)) + "\n"
    data = text.encode("utf-8")
    if len(data) > CONFIG_MAX_BYTES:
        raise ConfigurationError("configuration document exceeds the size limit")
    return data


def _split_toml_items(text: str, separator: str) -> list[str]:
    result: list[str] = []
    start = 0
    quote = False
    escaped = False
    depth = 0
    for index, character in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quote = False
            continue
        if character == '"':
            quote = True
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
        elif character == separator and depth == 0:
            result.append(text[start:index].strip())
            start = index + 1
    result.append(text[start:].strip())
    return result


def _fallback_toml_key(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('"'):
        value = json.loads(raw)
        if not isinstance(value, str):
            raise ValueError("quoted TOML key is not a string")
        return value
    if not _BARE_TOML_KEY.fullmatch(raw):
        raise ValueError(f"unsupported TOML key: {raw!r}")
    return raw


def _fallback_toml_value(raw: str) -> Any:
    raw = raw.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith('"'):
        value = json.loads(raw)
        if not isinstance(value, str):
            raise ValueError("TOML string did not decode as a string")
        return value
    if raw.startswith("[") and raw.endswith("]"):
        body = raw[1:-1].strip()
        return [] if not body else [
            _fallback_toml_value(item)
            for item in _split_toml_items(body, ",")
        ]
    try:
        return int(raw, 10)
    except ValueError:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("non-finite TOML number")
        return value


def _fallback_toml_loads(text: str) -> dict[str, Any]:
    """Read the deterministic TOML subset emitted by this module on 3.10."""
    root: dict[str, Any] = {}
    table = root
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            parts = [
                _fallback_toml_key(item)
                for item in _split_toml_items(line[1:-1], ".")
            ]
            table = root
            for part in parts:
                current = table.setdefault(part, {})
                if not isinstance(current, dict):
                    raise ValueError(f"TOML table collides on line {number}")
                table = current
            continue
        pieces = _split_toml_items(line, "=")
        if len(pieces) != 2:
            raise ValueError(f"unsupported TOML assignment on line {number}")
        key = _fallback_toml_key(pieces[0])
        if key in table:
            raise ValueError(f"duplicate TOML key on line {number}")
        table[key] = _fallback_toml_value(pieces[1])
    return root


def _read_toml(path: Path, *, missing_ok: bool = False) -> dict[str, Any] | None:
    data = _read_secure_bytes(path, maximum=CONFIG_MAX_BYTES, missing_ok=missing_ok)
    if data is None:
        return None
    try:
        text = data.decode("utf-8")
        document = (
            tomllib.loads(text)
            if tomllib is not None
            else _fallback_toml_loads(text)
        )
    except (UnicodeError, ValueError) as error:
        raise AuthorityError(f"invalid TOML configuration {path}: {error}") from error
    if not isinstance(document, dict):
        raise AuthorityError(f"configuration is not a TOML table: {path}")
    return document


def _configuration_document(
    provider_id: str, revision: int, values: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "contract_version": 1,
        "provider_id": provider_id,
        "revision": revision,
        "schema_version": 1,
        "values": dict(values),
    }


def _stored_configuration(
    document: Mapping[str, Any] | None, provider_id: str
) -> tuple[int, dict[str, Any]]:
    if document is None:
        return 0, {}
    if document.get("contract_version") != 1:
        raise AuthorityError("unsupported provider configuration contract version")
    if document.get("provider_id") != provider_id:
        raise AuthorityError(f"configuration provider identity is not {provider_id}")
    if document.get("schema_version") != 1:
        raise AuthorityError("unsupported provider configuration schema version")
    revision = document.get("revision")
    values = document.get("values")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise AuthorityError("provider configuration revision is invalid")
    if not isinstance(values, dict):
        raise AuthorityError("provider configuration values are not a table")
    return revision, dict(values)


def _line_assignments(path: Path) -> tuple[list[str], dict[str, str]]:
    data = _read_secure_bytes(path, maximum=CONFIG_MAX_BYTES, missing_ok=True)
    if data is None:
        return [], {}
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise AuthorityError(f"legacy configuration is not UTF-8: {path}") from error
    values: dict[str, str] = {}
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key in values and values[key] != value:
            raise AuthorityError(f"legacy configuration repeats conflicting key {key}")
        values[key] = value
    return lines, values


def _rewrite_assignment(path: Path, key: str, value: str) -> None:
    _rewrite_assignments(path, {key: value})


def _rewrite_assignments(path: Path, changes: Mapping[str, str]) -> None:
    lines, _ = _line_assignments(path)
    output: list[str] = []
    remaining = dict(changes)
    for raw in lines:
        stripped = raw.strip()
        candidate = stripped[7:].lstrip() if stripped.startswith("export ") else stripped
        candidate_key = candidate.split("=", 1)[0].strip() if "=" in candidate else ""
        if candidate_key in remaining:
            if remaining[candidate_key] is not None:
                prefix = "export " if stripped.startswith("export ") else ""
                output.append(
                    f"{prefix}{candidate_key}={remaining.pop(candidate_key)}"
                )
            continue
        output.append(raw)
    if remaining:
        if output and output[-1] != "":
            output.append("")
        output.extend(f"{key}={remaining[key]}" for key in sorted(remaining))
    _atomic_write(path, ("\n".join(output) + "\n").encode("utf-8"))


def _parse_raw_value(raw: str) -> Any:
    if len(raw.encode("utf-8")) > 65536:
        raise ConfigurationError("configuration value exceeds 65536 bytes")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    _toml_value(value)
    return value


def _validate_value(provider_id: str, key: str, value: Any) -> None:
    if not _CONFIG_KEY.fullmatch(key):
        raise ConfigurationError(f"invalid configuration key: {key!r}")
    if provider_id == "kilix-cap" and key == "web_home":
        if (
            not isinstance(value, str)
            or not value.startswith(("https://", "http://"))
            or len(value) > 2048
            or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
        ):
            raise ConfigurationError("kilix-cap web_home must be a bounded HTTP(S) URL")
    if provider_id == "kilix-cap" and key == "mail_target":
        if not isinstance(value, str) or not value or len(value) > 4096 or any(
            ord(character) < 0x21 or ord(character) > 0x7E for character in value
        ):
            raise ConfigurationError("kilix-cap mail_target is invalid")
    if provider_id == "kilix-land-desktop" and key == "debug_menu":
        if not isinstance(value, bool):
            raise ConfigurationError("kilix-land-desktop debug_menu must be boolean")


def provider_config_schema(provider_id: str) -> dict[str, Any]:
    _require_provider(provider_id)
    properties: dict[str, Any] = {}
    if provider_id == "kilix-cap":
        properties = {
            "mail_target": {"maxLength": 4096, "minLength": 1, "type": "string"},
            "web_home": {
                "maxLength": 2048,
                "pattern": "^https?://",
                "type": "string",
            },
        }
    elif provider_id == "kilix-land-desktop":
        properties = {"debug_menu": {"default": True, "type": "boolean"}}
    return {
        "$id": f"https://schemas.kilix.org/desktop/config/{provider_id}/v1",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": True,
        "properties": properties,
        "type": "object",
        "x-kilix-contract-version": 1,
        "x-kilix-provider-id": provider_id,
    }


@dataclass(frozen=True)
class CopyItem:
    kind: str
    source: Path
    target: Path
    source_label: str
    target_label: str


class PersistenceStore:
    """Resolve and mutate desktop persistence under one global lock."""

    def __init__(self, layout: Layout | None = None):
        self.layout = Layout.from_environment() if layout is None else layout

    @contextmanager
    def _locked(self) -> Iterator[None]:
        path = self.layout.migration_lock
        _ensure_private_directory(path.parent)
        _refuse_symlink_components(path)
        descriptor = os.open(
            path,
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            status = os.fstat(descriptor)
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_uid != os.geteuid()
                or status.st_mode & 0o022
            ):
                raise AuthorityError("migration lock is not a private user-owned file")
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _record(self) -> dict[str, Any] | None:
        document = _read_json(self.layout.migration_record, missing_ok=True)
        if document is None:
            return None
        try:
            validate("migration", document)
        except ValueError as error:
            raise AuthorityError(f"migration record violates contract v1: {error}") from error
        completed = document.get("completed_providers", [])
        if not isinstance(completed, list) or any(
            not isinstance(item, str) for item in completed
        ):
            raise AuthorityError("migration completed_providers is invalid")
        if completed != list(MIGRATION_ORDER[: len(completed)]):
            raise AuthorityError("migration completed_providers is out of order")
        if document["state"] == "completed" and completed != list(MIGRATION_ORDER):
            raise AuthorityError("completed migration does not cover all four providers")
        recorded_order = document.get("migration_order", list(MIGRATION_ORDER))
        if recorded_order != list(MIGRATION_ORDER):
            raise AuthorityError("migration record uses an unknown provider order")
        return document

    def authority(self) -> str:
        document = self._record()
        if document is None:
            return "legacy"
        if document["state"] == "completed":
            for provider_id in MIGRATION_ORDER:
                self._read_provider_file(provider_id, xdg=True)
            self._read_policy_file(xdg=True)
            return "xdg"
        return "legacy"

    def _read_provider_file(
        self, provider_id: str, *, xdg: bool
    ) -> tuple[int, dict[str, Any]]:
        path = (
            self.layout.xdg_provider_config(provider_id)
            if xdg
            else self.layout.legacy_provider_sidecar(provider_id)
        )
        return _stored_configuration(_read_toml(path, missing_ok=not xdg), provider_id)

    def _legacy_config(self, provider_id: str) -> tuple[int, dict[str, Any]]:
        revision, values = self._read_provider_file(provider_id, xdg=False)
        root = self.layout.legacy_provider_root(provider_id)
        if provider_id == "kilix-cap":
            _, assignments = _line_assignments(root / "config")
            values.update(assignments)
        elif provider_id == "kilix-land-desktop":
            _, assignments = _line_assignments(root / "desktop.conf")
            values.update(assignments)
            if "debug_menu" in assignments:
                raw = assignments["debug_menu"].lower()
                if raw not in {"0", "1", "false", "true", "no", "yes", "off", "on"}:
                    raise AuthorityError("legacy Land debug_menu is not boolean")
                values["debug_menu"] = raw in {"1", "true", "yes", "on"}
        for key, value in values.items():
            _validate_value(provider_id, key, value)
        return revision, values

    def config_get(
        self, provider_id: str, key: str | None = None
    ) -> dict[str, Any]:
        _require_provider(provider_id)
        xdg = self.authority() == "xdg"
        revision, values = (
            self._read_provider_file(provider_id, xdg=True)
            if xdg
            else self._legacy_config(provider_id)
        )
        if key is not None:
            if not _CONFIG_KEY.fullmatch(key):
                raise ConfigurationError(f"invalid configuration key: {key!r}")
            values = {key: values[key]} if key in values else {}
        document = _configuration_document(provider_id, revision, values)
        validate("provider-config", document)
        return document

    def config_value(self, provider_id: str, key: str) -> Any:
        document = self.config_get(provider_id, key)
        if key not in document["values"]:
            raise UnavailableError(
                f"{provider_id} configuration value is unavailable: {key}"
            )
        return document["values"][key]

    def _write_legacy_config(
        self, provider_id: str, revision: int, values: Mapping[str, Any]
    ) -> None:
        document = _configuration_document(provider_id, revision, values)
        _atomic_write(
            self.layout.legacy_provider_sidecar(provider_id),
            _toml_bytes(document),
        )
        root = self.layout.legacy_provider_root(provider_id)
        if provider_id == "kilix-cap":
            changes = {
                key: str(values[key])
                for key in ("mail_target", "web_home")
                if key in values
            }
            if changes:
                _rewrite_assignments(root / "config", changes)
        elif provider_id == "kilix-land-desktop" and "debug_menu" in values:
            raw = "true" if values["debug_menu"] else "false"
            _rewrite_assignment(root / "desktop.conf", "debug_menu", raw)

    def config_set(self, provider_id: str, key: str, raw_value: str) -> None:
        _require_provider(provider_id)
        value = _parse_raw_value(raw_value)
        _validate_value(provider_id, key, value)
        with self._locked():
            xdg = self.authority() == "xdg"
            revision, values = (
                self._read_provider_file(provider_id, xdg=True)
                if xdg
                else self._legacy_config(provider_id)
            )
            values[key] = value
            document = _configuration_document(provider_id, revision + 1, values)
            validate("provider-config", document)
            if xdg:
                _atomic_write(
                    self.layout.xdg_provider_config(provider_id),
                    _toml_bytes(document),
                )
            else:
                self._write_legacy_config(provider_id, revision + 1, values)

    def _read_policy_file(self, *, xdg: bool) -> tuple[int, dict[str, Any]]:
        path = self.layout.xdg_policy if xdg else self.layout.legacy_policy_sidecar
        document = _read_toml(path, missing_ok=not xdg)
        if document is None:
            return 0, dict(DEFAULT_POLICY)
        if document.get("schema_version") != 1:
            raise AuthorityError("unsupported desktop policy schema version")
        revision = document.get("revision")
        values = document.get("values")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise AuthorityError("desktop policy revision is invalid")
        if not isinstance(values, dict):
            raise AuthorityError("desktop policy values are not a table")
        merged = dict(DEFAULT_POLICY)
        merged.update(values)
        self._validate_policy(merged)
        return revision, merged

    def _legacy_policy(
        self, *, repair_default: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        revision, values = self._read_policy_file(xdg=False)
        observed: list[str] = []
        shared = values.get("shared_settings", {})
        if not isinstance(shared, dict):
            raise AuthorityError("legacy shared_settings policy is not a table")
        shared = dict(shared)
        for path in (
            self.layout.legacy_settings,
            self.layout.legacy_kilix_environment,
        ):
            _, assignments = _line_assignments(path)
            if "KILIX_DESKTOP_PROVIDER" in assignments:
                observed.append(assignments["KILIX_DESKTOP_PROVIDER"])
            if path == self.layout.legacy_settings:
                shared.update(
                    {
                        key: value
                        for key, value in assignments.items()
                        if key != "KILIX_DESKTOP_PROVIDER"
                    }
                )
        if len(set(observed)) > 1 and repair_default is None:
            raise AuthorityError("legacy default-provider records disagree")
        if repair_default is not None:
            values["default_provider"] = repair_default
        elif observed:
            values["default_provider"] = observed[0]
        values["shared_settings"] = shared
        self._validate_policy(values)
        return revision, values

    @staticmethod
    def _validate_policy(values: Mapping[str, Any]) -> None:
        provider = values.get("default_provider")
        if not isinstance(provider, str) or not _ENV_PROVIDER.fullmatch(provider):
            raise ConfigurationError("default_provider is not a provider identity")
        order = values.get("fallback_order")
        if (
            not isinstance(order, list)
            or not order
            or any(
                not isinstance(item, str) or not _ENV_PROVIDER.fullmatch(item)
                for item in order
            )
            or len(set(order)) != len(order)
        ):
            raise ConfigurationError("fallback_order must be a unique provider list")

    def policy_get(self, key: str | None = None) -> dict[str, Any]:
        xdg = self.authority() == "xdg"
        revision, values = self._read_policy_file(xdg=True) if xdg else self._legacy_policy()
        if key is not None:
            if not _CONFIG_KEY.fullmatch(key):
                raise ConfigurationError(f"invalid policy key: {key!r}")
            values = {key: values[key]} if key in values else {}
        return {"revision": revision, "schema_version": 1, "values": values}

    def policy_value(self, key: str) -> Any:
        document = self.policy_get(key)
        if key not in document["values"]:
            raise UnavailableError(f"desktop policy value is unavailable: {key}")
        return document["values"][key]

    def policy_path(self) -> Path:
        return (
            self.layout.xdg_policy
            if self.authority() == "xdg"
            else self.layout.legacy_settings
        )

    def policy_set(self, key: str, raw_value: str) -> None:
        if not _CONFIG_KEY.fullmatch(key):
            raise ConfigurationError(f"invalid policy key: {key!r}")
        value = _parse_raw_value(raw_value)
        with self._locked():
            xdg = self.authority() == "xdg"
            revision, values = (
                self._read_policy_file(xdg=True)
                if xdg
                else self._legacy_policy(
                    repair_default=(
                        value
                        if key == "default_provider" and isinstance(value, str)
                        else None
                    )
                )
            )
            values[key] = value
            self._validate_policy(values)
            document = {"revision": revision + 1, "schema_version": 1, "values": values}
            if xdg:
                _atomic_write(self.layout.xdg_policy, _toml_bytes(document))
            else:
                _atomic_write(self.layout.legacy_policy_sidecar, _toml_bytes(document))
                if key == "default_provider":
                    _rewrite_assignment(
                        self.layout.legacy_settings,
                        "KILIX_DESKTOP_PROVIDER",
                        value,
                    )
                    _rewrite_assignment(
                        self.layout.legacy_kilix_environment,
                        "KILIX_DESKTOP_PROVIDER",
                        value,
                    )

    def shared_settings_get(self) -> dict[str, Any]:
        xdg = self.authority() == "xdg"
        policy = self.policy_get()
        values = policy["values"].get("shared_settings", {})
        if not isinstance(values, dict):
            raise AuthorityError("desktop shared_settings policy is not a table")
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in values.items()
        ):
            raise AuthorityError("desktop shared_settings entries must be strings")
        return {
            "exists": (
                os.path.lexists(self.layout.xdg_policy)
                if xdg
                else os.path.lexists(self.layout.legacy_settings)
            ),
            "revision": policy["revision"],
            "schema_version": 1,
            "values": dict(values),
        }

    def shared_settings_update(self, changes: Mapping[str, Any]) -> None:
        if not changes:
            return
        normalized: dict[str, str] = {}
        for key, value in changes.items():
            if not isinstance(key, str) or not re.fullmatch(
                r"[A-Z][A-Z0-9_]{0,127}", key
            ):
                raise ConfigurationError(f"invalid shared setting key: {key!r}")
            if not isinstance(value, str):
                raise ConfigurationError(f"shared setting {key} must be a string")
            _toml_value(value)
            normalized[key] = value
        with self._locked():
            xdg = self.authority() == "xdg"
            revision, values = (
                self._read_policy_file(xdg=True)
                if xdg
                else self._legacy_policy()
            )
            shared = values.get("shared_settings", {})
            if not isinstance(shared, dict):
                raise AuthorityError("desktop shared_settings policy is not a table")
            shared = dict(shared)
            shared.update(normalized)
            values["shared_settings"] = shared
            self._validate_policy(values)
            document = {
                "revision": revision + 1,
                "schema_version": 1,
                "values": values,
            }
            if xdg:
                _atomic_write(self.layout.xdg_policy, _toml_bytes(document))
            else:
                _atomic_write(
                    self.layout.legacy_policy_sidecar, _toml_bytes(document)
                )
                _rewrite_assignments(self.layout.legacy_settings, normalized)

    def resolved_path(self, provider_id: str, category: str) -> Path:
        _require_provider(provider_id)
        if category not in {"config", "state", "data", "cache", "session", "runtime"}:
            raise ConfigurationError(f"unsupported storage category: {category}")
        xdg = self.authority() == "xdg"
        if xdg:
            if category == "config":
                return self.layout.xdg_provider_config_dir(provider_id)
            if category in {"state", "runtime"}:
                return self.layout.xdg_provider_state(provider_id)
            if category == "session":
                return self.layout.xdg_provider_state(provider_id) / "session"
            if category == "data":
                return self.layout.xdg_provider_data(provider_id)
            return self.layout.xdg_provider_cache(provider_id)
        if provider_id == "kilix-95" and category in {
            "config",
            "state",
            "data",
            "cache",
            "session",
        }:
            return self.layout.legacy_95_category(category)
        root = self.layout.legacy_provider_root(provider_id)
        if provider_id == "kilix-land-desktop" and category in {
            "state",
            "session",
            "runtime",
        }:
            return root
        if category == "session":
            return root / "session"
        if category in {"state", "data", "cache"}:
            return (
                root
                if provider_id == "kilix-land-desktop" and category == "state"
                else root / category
            )
        return root

    def _copy_items(self, provider_id: str) -> list[CopyItem]:
        items: list[CopyItem] = []
        if provider_id == "kilix-land-desktop":
            legacy = self.layout.legacy_provider_root(provider_id)
            target = self.layout.xdg_provider_state(provider_id)
            items.append(
                CopyItem(
                    "file",
                    legacy / "bindings.conf",
                    self.layout.xdg_provider_config_dir(provider_id)
                    / "bindings.conf",
                    "legacy:kilix-land-desktop/bindings.conf",
                    "xdg:config/kilix/desktops/kilix-land-desktop/bindings.conf",
                )
            )
            for name in ("profile.state", "world.state"):
                items.append(
                    CopyItem(
                        "state-record",
                        legacy / name,
                        target / name,
                        f"legacy:kilix-land-desktop/{name}",
                        f"xdg:state/kilix/desktops/kilix-land-desktop/{name}",
                    )
                )
        elif provider_id == "kilix-95":
            mappings = (
                ("config", self.layout.xdg_provider_config_dir(provider_id), "config"),
                ("state", self.layout.xdg_provider_state(provider_id), "state"),
                ("data", self.layout.xdg_provider_data(provider_id), "data"),
                ("cache", self.layout.xdg_provider_cache(provider_id), "cache"),
                (
                    "session",
                    self.layout.xdg_provider_state(provider_id) / "session",
                    "state/session",
                ),
            )
            for category, target, target_label in mappings:
                items.append(
                    CopyItem(
                        "directory",
                        self.layout.legacy_95_category(category),
                        target,
                        f"legacy:kilix-95/{category}",
                        f"xdg:{target_label}/kilix/desktops/kilix-95",
                    )
                )
        return items

    def _operation_plan(
        self, provider_id: str, *, phase: str = "stage"
    ) -> list[dict[str, str]]:
        operations = [
            {
                "kind": "config-record",
                "phase": phase,
                "provider_id": provider_id,
                "source": f"legacy:{provider_id}/configuration",
                "status": "planned",
                "target": f"xdg:config/kilix/desktops/{provider_id}.toml",
            }
        ]
        operations.extend(
            {
                "kind": item.kind,
                "phase": phase,
                "provider_id": provider_id,
                "source": item.source_label,
                "status": "planned",
                "target": item.target_label,
            }
            for item in self._copy_items(provider_id)
        )
        if provider_id == "kilix-95":
            operations.append(
                {
                    "kind": "config-record",
                    "phase": phase,
                    "provider_id": provider_id,
                    "source": "legacy:desktop-policy",
                    "status": "planned",
                    "target": "xdg:config/kilix/desktop.toml",
                }
            )
        return operations

    def _migration_document(
        self,
        provider_id: str,
        from_version: str,
        *,
        dry_run: bool,
        state: str,
        authority: str,
        operations: Sequence[Mapping[str, Any]],
        recovery_paths: Sequence[str],
        completed: Sequence[str],
        generation: int,
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "authoritative_store": authority,
            "completed_providers": list(completed),
            "contract_version": 1,
            "dry_run": dry_run,
            "from_version": from_version,
            "generation": generation,
            "migration_id": f"{provider_id}-to-contract-v1",
            "migration_order": list(MIGRATION_ORDER),
            "operations": list(operations),
            "provider_id": provider_id,
            "recovery_paths": sorted(set(recovery_paths)),
            "schema": "kilix.desktop.migration/v1",
            "schema_version": 1,
            "state": state,
            "to_contract_version": 1,
        }
        validate("migration", document)
        return document

    @staticmethod
    def _source_snapshot(path: Path) -> dict[str, str]:
        if not os.path.lexists(path):
            return {}
        _refuse_symlink_components(path)
        result: dict[str, str] = {}
        candidates = [path]
        if path.is_dir():
            candidates.extend(sorted(path.rglob("*"), key=lambda item: item.as_posix()))
        for candidate in candidates:
            status = candidate.lstat()
            relative = "." if candidate == path else candidate.relative_to(path).as_posix()
            if stat.S_ISLNK(status.st_mode):
                raise MigrationError(f"legacy migration source is a symlink: {candidate}")
            if status.st_uid != os.geteuid():
                raise MigrationError(f"legacy migration source is not user-owned: {candidate}")
            if stat.S_ISDIR(status.st_mode):
                result[relative] = "directory"
            elif stat.S_ISREG(status.st_mode):
                data = _read_secure_bytes(candidate, maximum=STATE_FILE_MAX_BYTES)
                assert data is not None
                result[relative] = hashlib.sha256(data).hexdigest()
            else:
                raise MigrationError(f"legacy migration source is special: {candidate}")
        return result

    @staticmethod
    def _remove_managed_path(path: Path) -> None:
        """Remove one inert XDG migration target without following links."""
        if not os.path.lexists(path):
            return
        _refuse_symlink_components(path)
        status = path.lstat()
        if status.st_uid != os.geteuid():
            raise MigrationError(
                f"stale migration target is not user-owned: {path}"
            )
        if stat.S_ISLNK(status.st_mode):
            raise MigrationError(f"stale migration target is a symlink: {path}")
        if stat.S_ISDIR(status.st_mode):
            for child in sorted(
                path.iterdir(), key=lambda item: item.name, reverse=True
            ):
                PersistenceStore._remove_managed_path(child)
            path.rmdir()
        elif stat.S_ISREG(status.st_mode):
            path.unlink()
        else:
            raise MigrationError(f"stale migration target is special: {path}")
        _fsync_directory(path.parent)

    @staticmethod
    def _prune_directory(source: Path, target: Path) -> None:
        """Make the staged target contain no entries absent from legacy."""
        for child in sorted(target.iterdir(), key=lambda item: item.name):
            source_child = source / child.name
            if not os.path.lexists(source_child):
                PersistenceStore._remove_managed_path(child)
                continue
            source_status = source_child.lstat()
            target_status = child.lstat()
            if stat.S_ISLNK(source_status.st_mode) or stat.S_ISLNK(
                target_status.st_mode
            ):
                raise MigrationError(
                    f"migration directory contains a symlink: {child}"
                )
            if stat.S_ISDIR(source_status.st_mode) and stat.S_ISDIR(
                target_status.st_mode
            ):
                PersistenceStore._prune_directory(source_child, child)

    @staticmethod
    def _copy_file(source: Path, target: Path, *, replace: bool = False) -> str:
        data = _read_secure_bytes(source, maximum=STATE_FILE_MAX_BYTES)
        assert data is not None
        existing = _read_secure_bytes(
            target, maximum=STATE_FILE_MAX_BYTES, missing_ok=True
        )
        if existing is not None:
            if existing != data:
                if not replace:
                    raise MigrationError(
                        f"migration target already has different bytes: {target}"
                    )
                _atomic_write(target, data)
                return "copied"
            return "preserved"
        _atomic_write(target, data)
        return "copied"

    def _copy_item(self, item: CopyItem, *, replace: bool = False) -> str:
        if not os.path.lexists(item.source):
            if replace and os.path.lexists(item.target):
                self._remove_managed_path(item.target)
                return "copied"
            return "skipped"
        before = self._source_snapshot(item.source)
        statuses: list[str] = []
        if item.source.is_file():
            statuses.append(
                self._copy_file(item.source, item.target, replace=replace)
            )
        else:
            _ensure_private_directory(item.target)
            for source in sorted(item.source.rglob("*"), key=lambda path: path.as_posix()):
                relative = source.relative_to(item.source)
                target = item.target / relative
                status = source.lstat()
                if stat.S_ISDIR(status.st_mode):
                    _ensure_private_directory(target)
                elif stat.S_ISREG(status.st_mode):
                    statuses.append(
                        self._copy_file(source, target, replace=replace)
                    )
                else:
                    raise MigrationError(
                        "legacy migration source is not a file/directory: "
                        f"{source}"
                    )
            if replace:
                self._prune_directory(item.source, item.target)
        after = self._source_snapshot(item.source)
        if after != before:
            raise MigrationError(f"legacy migration source changed while copying: {item.source}")
        return "copied" if "copied" in statuses else "preserved"

    def _publish_configuration(
        self, provider_id: str, *, replace: bool = False
    ) -> str:
        revision, values = self._legacy_config(provider_id)
        document = _configuration_document(provider_id, revision, values)
        target = self.layout.xdg_provider_config(provider_id)
        data = _toml_bytes(document)
        existing = _read_secure_bytes(target, maximum=CONFIG_MAX_BYTES, missing_ok=True)
        if existing is not None:
            if existing != data:
                if not replace:
                    raise MigrationError(
                        f"migration target already has different bytes: {target}"
                    )
                _atomic_write(target, data)
                return "copied"
            return "preserved"
        _atomic_write(target, data)
        return "copied"

    def _publish_policy(self, *, replace: bool = False) -> str:
        revision, values = self._legacy_policy()
        data = _toml_bytes({"revision": revision, "schema_version": 1, "values": values})
        existing = _read_secure_bytes(
            self.layout.xdg_policy, maximum=CONFIG_MAX_BYTES, missing_ok=True
        )
        if existing is not None:
            if existing != data:
                if not replace:
                    raise MigrationError(
                        "migration target already has different bytes: "
                        f"{self.layout.xdg_policy}"
                    )
                _atomic_write(self.layout.xdg_policy, data)
                return "copied"
            return "preserved"
        _atomic_write(self.layout.xdg_policy, data)
        return "copied"

    def migrate(
        self, provider_id: str, from_version: str, *, dry_run: bool
    ) -> dict[str, Any]:
        _require_provider(provider_id)
        if (
            not from_version
            or len(from_version) > 64
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in from_version)
        ):
            raise ConfigurationError("invalid migration source version")
        plan = self._operation_plan(provider_id)
        if dry_run:
            if self.authority() != "legacy":
                raise MigrationError("desktop persistence migration is already complete")
            return self._migration_document(
                provider_id,
                from_version,
                dry_run=True,
                state="planned",
                authority="legacy",
                operations=plan,
                recovery_paths=[operation["source"] for operation in plan],
                completed=[],
                generation=0,
            )
        if provider_id in SEPARATE_CONSUMERS:
            raise MigrationError(
                f"{provider_id} is a separate contract consumer, not an "
                "ordered SDK migration member"
            )
        with self._locked():
            record = self._record()
            if record is not None and record["state"] == "completed":
                raise MigrationError("desktop persistence migration is already complete")
            completed = [] if record is None else list(record.get("completed_providers", []))
            if record is not None and record["state"] == "rolled-back":
                completed = []
            expected = (
                MIGRATION_ORDER[len(completed)]
                if len(completed) < len(MIGRATION_ORDER)
                else None
            )
            if provider_id != expected:
                raise MigrationError(
                    f"out-of-order migration: expected {expected or 'none'}, got {provider_id}"
                )
            generation = 1 if record is None else int(record.get("generation", 0)) + 1
            retrying = bool(
                record is not None
                and record.get("state") == "failed"
                and record.get("provider_id") == provider_id
            )
            prior_operations = (
                list(record.get("operations", [])) if record is not None else []
            )
            prior_operations = [
                operation
                for operation in prior_operations
                if not (
                    isinstance(operation, dict)
                    and operation.get("provider_id") == provider_id
                )
            ]
            recovery = (
                list(record.get("recovery_paths", []))
                if record is not None
                else []
            )

            attempts: list[tuple[str, list[dict[str, str]], bool]] = []
            if provider_id == MIGRATION_ORDER[-1]:
                # Earlier XDG copies are deliberately inert. Refresh them from
                # the still-authoritative legacy tree immediately before the
                # sole authority flip so mixed-window writes cannot go stale.
                prior_operations = []
                for staged_provider in completed:
                    attempts.append(
                        (
                            staged_provider,
                            self._operation_plan(
                                staged_provider, phase="final-sync"
                            ),
                            True,
                        )
                    )
            attempts.append((provider_id, plan, retrying))
            attempt_plan = [
                operation
                for _attempt_provider, selected_plan, _replace in attempts
                for operation in selected_plan
            ]
            operations: list[dict[str, Any]] = list(prior_operations)
            completed_attempt_operations = 0
            try:
                for attempt_provider, selected_plan, replace in attempts:
                    config_status = self._publish_configuration(
                        attempt_provider, replace=replace
                    )
                    operations.append(
                        {**selected_plan[0], "status": config_status}
                    )
                    completed_attempt_operations += 1
                    recovery.append(selected_plan[0]["source"])
                    plan_index = 1
                    for item in self._copy_items(attempt_provider):
                        status = self._copy_item(item, replace=replace)
                        operations.append(
                            {**selected_plan[plan_index], "status": status}
                        )
                        completed_attempt_operations += 1
                        if status != "skipped":
                            recovery.append(item.source_label)
                        plan_index += 1
                    if attempt_provider == "kilix-95":
                        policy_status = self._publish_policy(replace=replace)
                        operations.append(
                            {
                                **selected_plan[plan_index],
                                "status": policy_status,
                            }
                        )
                        completed_attempt_operations += 1
                        recovery.append(selected_plan[plan_index]["source"])
            except (OSError, PersistenceError) as error:
                failed = list(operations)
                failed.extend(
                    {**operation, "status": "failed"}
                    for operation in attempt_plan[completed_attempt_operations:]
                )
                try:
                    failure_record = self._migration_document(
                        provider_id,
                        from_version,
                        dry_run=False,
                        state="failed",
                        authority="legacy",
                        operations=failed,
                        recovery_paths=recovery,
                        completed=completed,
                        generation=generation,
                    )
                    _atomic_write(self.layout.migration_record, _json_bytes(failure_record))
                except Exception:
                    pass
                if isinstance(error, MigrationError):
                    raise
                raise MigrationError(f"migration write failed: {error}") from error
            completed.append(provider_id)
            final = completed == list(MIGRATION_ORDER)
            document = self._migration_document(
                provider_id,
                from_version,
                dry_run=False,
                state="completed" if final else "in-progress",
                authority="xdg" if final else "legacy",
                operations=operations,
                recovery_paths=recovery,
                completed=completed,
                generation=generation,
            )
            try:
                _atomic_write(self.layout.migration_record, _json_bytes(document))
            except OSError as error:
                raise MigrationError(
                    f"migration record commit failed: {error}"
                ) from error
            return document

    def rollback(self, from_version: str) -> dict[str, Any]:
        with self._locked():
            record = self._record()
            if record is None:
                raise MigrationError("there is no desktop persistence migration to roll back")
            completed = list(record.get("completed_providers", []))
            operations = [
                {
                    "kind": "state-record",
                    "source": "xdg:migration-v1.json",
                    "status": "preserved",
                    "target": "legacy:authoritative-store",
                }
            ]
            document = self._migration_document(
                "kilix-desktop-sdk",
                from_version,
                dry_run=False,
                state="rolled-back",
                authority="legacy",
                operations=operations,
                recovery_paths=list(record.get("recovery_paths", [])),
                completed=completed,
                generation=int(record.get("generation", 0)) + 1,
            )
            _atomic_write(self.layout.migration_record, _json_bytes(document))
            return document


def emit_json(document: Mapping[str, Any]) -> None:
    """Emit exactly one compact JSON document for a provider endpoint."""
    os.write(1, _json_bytes(document))


def emit_value(value: Any) -> None:
    """Emit one bounded scalar for native runtime bridges."""
    if isinstance(value, str):
        _toml_value(value)
        data = value.encode("utf-8") + b"\n"
    elif isinstance(value, bool):
        data = (b"true\n" if value else b"false\n")
    else:
        data = (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    if len(data) > 65537:
        raise ConfigurationError("configuration value exceeds the bridge limit")
    os.write(1, data)
