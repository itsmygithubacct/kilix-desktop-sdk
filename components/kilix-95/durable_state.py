"""Structured Kilix 95 records backed by the host's ``kilix-state-py`` SDK.

The envelope gives JSON payloads an application-level schema while the native
record supplies bounds, CRC validation, private permissions, and crash-safe
atomic replacement. Legacy JSON is imported only when no native record exists;
it is deliberately left in place so migration is non-destructive.
"""

import json
import os

from kilix_sdk import state as kilix_state

import storage


SCHEMA_VERSION = 1
StateError = kilix_state.KilixStateError


class JsonState:
    """One dictionary-valued, schema-versioned native state record."""

    def __init__(self, filename, *, legacy_path=None,
                 max_payload=kilix_state.DEFAULT_MAX_PAYLOAD):
        self.legacy_path = (os.path.abspath(os.path.expanduser(legacy_path))
                            if legacy_path else None)
        self.store = kilix_state.Store(
            absolute_path=storage.state_dir(filename),
            max_payload=max_payload)
        self.last_error = None

    @property
    def path(self):
        return self.store.path

    def _decode(self, payload):
        envelope = json.loads(payload.decode("utf-8"))
        if not isinstance(envelope, dict):
            raise ValueError("state envelope must be an object")
        version = envelope.get("schema_version")
        if (not isinstance(version, int) or isinstance(version, bool)
                or version != SCHEMA_VERSION):
            raise ValueError("unsupported state schema")
        value = envelope.get("data")
        if not isinstance(value, dict):
            raise ValueError("state data must be an object")
        return value

    def _legacy_dict(self):
        if not self.legacy_path:
            return None
        try:
            with open(self.legacy_path, encoding="utf-8") as stream:
                value = json.load(stream)
        except (OSError, UnicodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def load_dict(self):
        """Load a dictionary, importing valid legacy JSON when absent.

        Desktop startup remains tolerant of a corrupt or malformed record, as
        it was for the old JSON file. ``last_error`` retains the reason so the
        failure is observable to callers and tests instead of being mistaken
        for an absent record eligible for legacy import.
        """

        self.last_error = None
        try:
            payload = self.store.load()
        except kilix_state.StateNotFoundError:
            legacy = self._legacy_dict()
            if legacy is None:
                return {}
            try:
                self.save_dict(legacy)
            except StateError as error:
                self.last_error = error
            return legacy
        except StateError as error:
            self.last_error = error
            return {}
        try:
            return self._decode(payload)
        except (UnicodeError, ValueError) as error:
            self.last_error = error
            return {}

    def save_dict(self, value):
        if not isinstance(value, dict):
            raise TypeError("state data must be a dictionary")
        envelope = {"schema_version": SCHEMA_VERSION, "data": value}
        payload = json.dumps(
            envelope, sort_keys=True, separators=(",", ":"),
            # ASCII escaping preserves Python's surrogateescape representation
            # of POSIX filenames containing non-UTF-8 bytes.  The previous
            # legacy JSON writer used the same safe representation.
            ensure_ascii=True).encode("utf-8")
        self.store.save(payload)

    def close(self):
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, _kind, _value, _traceback):
        self.close()


__all__ = ["JsonState", "SCHEMA_VERSION", "StateError"]
