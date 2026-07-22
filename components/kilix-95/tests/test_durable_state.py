"""Native durable-state records and non-destructive JSON migration."""

import json
import os
import stat
import tempfile

import harness as H  # Initializes the host SDK path before provider imports.
from kilix_sdk import state as kilix_state

import durable_state


def test_round_trip_crc_and_permissions():
    with durable_state.JsonState("contract.state") as record:
        value = {"flavor": "95", "recent": ["README.TXT"]}
        record.save_dict(value)
        assert record.load_dict() == value
        assert open(record.path, "rb").read(4) == b"KST1"
        assert stat.S_IMODE(os.stat(record.path).st_mode) == 0o600


def test_legacy_import_only_when_native_record_is_absent():
    directory = tempfile.mkdtemp(prefix="kilix95-state-legacy-")
    legacy = os.path.join(directory, ".state.json")
    with open(legacy, "w", encoding="utf-8") as stream:
        json.dump({"flavor": "xp"}, stream)
    with durable_state.JsonState(
            "migration.state", legacy_path=legacy) as record:
        assert record.load_dict() == {"flavor": "xp"}
        assert open(record.path, "rb").read(4) == b"KST1"
        with open(legacy, "w", encoding="utf-8") as stream:
            json.dump({"flavor": "stale"}, stream)
        assert record.load_dict() == {"flavor": "xp"}


def test_corruption_does_not_fall_back_to_stale_legacy():
    directory = tempfile.mkdtemp(prefix="kilix95-state-corrupt-")
    legacy = os.path.join(directory, "legacy.json")
    with open(legacy, "w", encoding="utf-8") as stream:
        json.dump({"value": "legacy"}, stream)
    with durable_state.JsonState(
            "corrupt.state", legacy_path=legacy) as record:
        record.save_dict({"value": "current"})
        damaged = bytearray(open(record.path, "rb").read())
        damaged[-1] ^= 0x01
        with open(record.path, "wb") as stream:
            stream.write(damaged)
        assert record.load_dict() == {}
        assert isinstance(record.last_error, kilix_state.CorruptStateError)


def test_valid_record_with_invalid_json_is_observable():
    with durable_state.JsonState("invalid-json.state") as record:
        record.store.save(b"{")
        assert record.load_dict() == {}
        assert isinstance(record.last_error, ValueError)


for _name, _test in sorted(list(globals().items())):
    if _name.startswith("test_") and callable(_test):
        _test()
print("ok")
