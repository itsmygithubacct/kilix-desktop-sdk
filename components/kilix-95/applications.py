"""Installed applications and model-backed launchers, without installing anything.

Discovery checks file sizes, not multi-gigabyte hashes. Providers still enforce
their model integrity, licence and hardware checks when an application runs.
The shell runs this inventory in a background thread, never in its paint loop.
"""
import os
from pathlib import Path
import shutil
import stat
from types import SimpleNamespace

from kilix_sdk import content, paths
from kilix_sdk._content_runtime import apps_root
import model_wizard


def executable(name, prefix=None, candidates=()):
    found = shutil.which(name)
    choices = [found, str(Path(os.environ.get(prefix, "~/.local")).expanduser()
                          / "bin" / name)] if prefix else [found]
    choices += [str(Path("~/.local/bin").expanduser() / name), *map(str, candidates)]
    return next((p for p in choices if p and os.path.isfile(p)
                 and os.access(p, os.X_OK)), None)


def asset_present(spec, installer):
    root = Path(installer.asset_destination(spec))
    if root.is_symlink() or not spec.files:
        return False
    try:
        for item in spec.files:
            path = root / item.path
            # A directory or an unfinished/truncated model is not installed.
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_size != item.bytes:
                return False
        return True
    except OSError:
        return False


def bonsai_assets():
    """Ask the installed Bonsai store about models acquired through its own UI."""
    if not executable("kilix-bonsai", "KILIX_BONSAI_PREFIX"):
        return []
    source = Path(os.environ.get("KILIX_BONSAI_SOURCES",
                                 str(Path(paths.storage_home()) / "sources")))
    package_root = source.expanduser() / "kilix-bonsai/src"
    if not (package_root / "kilix_bonsai").is_dir():
        return []
    try:
        from kilix_sdk._packages import load_pinned_package
        import importlib
        load_pinned_package("kilix_bonsai", (package_root,), "Bonsai is unavailable")
        catalog = importlib.import_module("kilix_bonsai.catalog")
        store = importlib.import_module("kilix_bonsai.store")
        return [(SimpleNamespace(asset_id=model.id, provider="kilix-bonsai"),
                 Path(variant.directory(model.store)))
                for model in catalog.load() for variant in model.variants
                if store.state(model, variant).state == store.PRESENT]
    except (ImportError, OSError, ValueError, RuntimeError):
        return []


def command_record(key, label, icon, argv, **extra):
    return dict(id=key, label=label, icon=icon, kind="command",
                argv=tuple(argv), **extra)


def model_records(assets, decisions, *, local_models=None):
    """Build interfaces only for present models and installed executables."""
    rows = []
    if binary := executable("kilix-bonsai", "KILIX_BONSAI_PREFIX"):
        rows.append(command_record("model-store", "Model Store", "bonsai", [binary]))
    groups = {}
    for asset, directory in assets:
        segment = model_wizard.group(dict(id=asset.asset_id, provider=asset.provider))
        if decisions.get(segment, {}).get("answer") == "no":
            continue
        groups.setdefault(segment, []).append((asset, directory))
    if groups.get("image"):
        if binary := executable("kilix-bonsai-image", "KILIX_BONSAI_PREFIX"):
            rows.append(command_record("bonsai-image", "Bonsai Image Generation",
                                       "paint", [binary]))
    if groups.get("chat"):
        if binary := executable("kilix-bonsai-chat", "KILIX_BONSAI_PREFIX"):
            rows.append(command_record("llm-chat", "LLM Chat", "chat", [binary]))
    if groups.get("dictation"):
        whisper = next(((a, p) for a, p in groups["dictation"]
                        if a.asset_id == "faster-whisper-small-en"), None)
        binary = executable("kilix-whisper-stt", candidates=[
            Path(paths.data_dir()) / "voice/whisper/current/bin/kilix-whisper-stt"])
        if whisper and binary:
            rows.append(command_record(
                "whisper", "Whisper Transcription", "microphone",
                [binary, "transcribe", "--model", str(whisper[1]), "--audio"],
                picker="WAV audio", pattern="*.wav", hold=True))
        if any(a.asset_id == "vibevoice-asr-bitnet" for a, _ in groups["dictation"]):
            if binary := executable("kilix-bonsai-speech", "KILIX_BONSAI_PREFIX"):
                rows.append(command_record("bonsai-speech", "Bonsai Transcription",
                                           "microphone", [binary]))
    # Query only the local installed-model inventory; no pull or inference.
    if local_models is None:
        try:
            import system_llm
            local_models = system_llm.installed()
        except (OSError, ValueError, KeyError, TypeError):
            local_models = {}
    if local_models and decisions.get("system-local-llm", {}).get("answer") != "no":
        model = sorted(local_models)[0]
        if binary := executable("kilix-avatar", "KILIX_AVATAR_PREFIX"):
            rows.append(command_record("avatar", "Kilix Avatar", "avatar",
                                       [binary, "--chat", "--model", model]))
        if not any(row["id"] == "llm-chat" for row in rows):
            if binary := executable("ollama"):
                rows.append(command_record("llm-chat", "LLM Chat", "chat",
                                           [binary, "run", model]))
    return rows, groups


def inventory():
    catalog = content.default_catalog()
    installer = content.Installer(apps_root())
    try:
        decisions = model_wizard.answers()
    except (OSError, ValueError):
        decisions = {}
    assets = [(asset, Path(installer.asset_destination(asset)))
              for asset in catalog.assets if asset_present(asset, installer)]
    assets.extend(bonsai_assets())
    interfaces, groups = model_records(assets, decisions)
    rows = []
    # Group packages so one source verification serves all of their programs.
    packages = {}
    for spec in content.entries(catalog):
        if spec.kind == "app" and spec.source_type in ("git", "archive"):
            packages.setdefault(spec.install_id, []).append(spec)
    for specs in packages.values():
        try:
            ready = installer.ready_provided(specs)
        except (OSError, ValueError, RuntimeError):
            continue
        for spec in specs:
            if not ready.get(spec.content_id):
                continue
            if spec.content_id == "kilix-pdf-conversion" and not groups.get("documents"):
                continue
            if spec.content_id == "kilix-object-detect" and not groups.get("vision"):
                continue
            if spec.content_id == "kilix-needle" and not groups.get("workflows"):
                continue
            rows.append(dict(id=spec.content_id, kind="catalog",
                             label=("Document Parsing" if spec.content_id == "kilix-pdf-conversion"
                                    else spec.label),
                             icon=spec.icon or "app"))
    rows.extend(interfaces)
    return sorted(rows, key=lambda row: (row["label"].casefold(), row["id"]))


def launch(shell, row):
    if row["kind"] == "catalog":
        return shell.open_catalog_application(row["id"])

    def run(selected=None):
        argv = list(row["argv"])
        if selected:
            argv.append(selected)
        if row.get("hold"):
            # Keep transcription output and failures visible after the process
            # exits. Arguments remain positional; filenames are never shell code.
            argv = ["/bin/sh", "-c",
                    '"$@"; status=$?; printf "\\nExit status: %s\\nPress Enter to close. " "$status"; '
                    'read -r reply; exit "$status"', "kilix-tool", *argv]
        return shell._tab(argv, row["label"])

    if row.get("picker"):
        import filedialog
        return filedialog.open_file(
            shell.desk, row["label"], lambda selected: selected and run(selected),
            filters=[(row["picker"], row["pattern"])])
    return run()
