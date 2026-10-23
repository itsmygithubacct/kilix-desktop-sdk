"""Presence, removal, model policy and desktop/menu activation share one inventory."""
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
from unittest.mock import patch

import harness as H
import applications as A
import xdgapps


def model(key, provider="kilix-bonsai"):
    return NS(asset_id=key, provider=provider)


def interfaces_require_models_and_respect_declines():
    assets = [(model("bonsai-image-4b-ternary-gemlite"), Path("/models/image")),
              (model("bonsai-8b"), Path("/models/chat")),
              (model("faster-whisper-small-en", "kilix-voice"), Path("/models/whisper"))]
    with patch.object(A, "executable", side_effect=lambda name, *a, **kw: "/bin/" + name):
        empty, _ = A.model_records([], {}, local_models={})
        assert [r["id"] for r in empty] == ["model-store"]
        rows, _ = A.model_records(assets, {}, local_models={"sample:1b": {}})
        by_id = {r["id"]: r for r in rows}
        assert {"bonsai-image", "llm-chat", "avatar", "whisper"} <= by_id.keys()
        assert by_id["whisper"]["argv"][-1] == "--audio"
        assert by_id["avatar"]["argv"][-2:] == ("--model", "sample:1b")
        rows, _ = A.model_records(assets, {"image": {"answer": "no"},
                                           "system-local-llm": {"answer": "no"}},
                                 local_models={"sample:1b": {}})
        assert not {"bonsai-image", "avatar"} & {r["id"] for r in rows}
    with patch.object(A, "executable", return_value=None):
        assert not A.model_records(assets, {}, local_models={"sample:1b": {}})[0]


def partial_and_removed_files_are_not_models():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        spec = NS(files=[NS(path="weights.bin", bytes=4)])
        installer = NS(asset_destination=lambda _: root)
        assert not A.asset_present(spec, installer)
        (root / "weights.bin").write_bytes(b"123")
        assert not A.asset_present(spec, installer)
        (root / "weights.bin").write_bytes(b"1234")
        assert A.asset_present(spec, installer)
        (root / "weights.bin").unlink()
        assert not A.asset_present(spec, installer)


def desktop_and_menu_launch_same_app_and_refresh_removes_it():
    desk = H.make_desk()
    row = A.command_record("test-chat", "Sample Chat", "chat", ["/bin/true"])
    desk.shell.installed_applications = [row]
    desk.shell.refresh()
    item = next(i for i in desk.shell.grid.items if i["label"] == "Sample Chat")
    seen = []
    desk.shell._tab = lambda argv, label: seen.append((argv, label))
    desk.shell._activate(item)
    desk.shell.installed_application_menu_items()[0].action()
    assert seen == [(["/bin/true"], "Sample Chat")] * 2
    desk.shell.installed_applications = []
    desk.shell.refresh()
    assert not any(i["label"] == "Sample Chat" for i in desk.shell.grid.items)
    assert not desk.shell.installed_application_menu_items()


def installed_desktop_entry_is_discovered_on_desktop():
    desk = H.make_desk()
    entry = dict(id="sample.desktop", name="Sample Installed App", exec="/bin/true",
                 categories=["Office"], terminal=False, path="/apps/sample.desktop")
    with patch.object(xdgapps, "scan", return_value=[entry]):
        desk.shell.refresh()
    item = next(i for i in desk.shell.grid.items if i["label"] == entry["name"])
    with patch.object(xdgapps, "launch") as launch:
        desk.shell._activate(item)
        launch.assert_called_once_with(desk.shell, entry)

def empty_inventory_does_not_install_models_or_programs():
    with patch("system_llm.installed", return_value={}), \
            patch.object(A, "executable", return_value=None), \
            patch.object(A.content.Installer, "ensure") as install:
        assert A.inventory() == []
    install.assert_not_called()


interfaces_require_models_and_respect_declines()
partial_and_removed_files_are_not_models()
desktop_and_menu_launch_same_app_and_refresh_removes_it()
installed_desktop_entry_is_discovered_on_desktop()
empty_inventory_does_not_install_models_or_programs()
print("ok")
