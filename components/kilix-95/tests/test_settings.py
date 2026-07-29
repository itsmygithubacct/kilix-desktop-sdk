"""Regression tests for kilix Settings (desktop/apps/settings.py).

Covers F06 (raw kitty.conf tab edits lost on tab switch / stale Apply),
F27 (untouched Apply corrupts non-listed values and appends managed
defaults), and F52 (non-UTF-8 kitty.conf makes Settings unopenable).
"""
import contextlib
import os
import stat
import tempfile

import harness as H
import shell as shell_mod
import theme as T
from apps import settings

# _apply live-reloads the running kilix; make that a no-op under test so we
# never SIGUSR1 a real process or shell out to a kitten.
os.environ.pop("KITTY_LISTEN_ON", None)
os.environ.pop("KITTY_PID", None)

# Each conf() block starts from a shared file that does not exist yet, and
# creating one migrates any exported managed key into it. A developer's own
# kilix.env would otherwise decide what this suite believes the defaults are.
for _key in settings.shared_settings.MANAGED_KEYS:
    os.environ.pop(_key, None)


@contextlib.contextmanager
def conf(text, binary=False):
    """A temp KITTY_CONFIG_DIRECTORY holding a kitty.conf; yields its path."""
    prev = os.environ.get("KITTY_CONFIG_DIRECTORY")
    prev_shared = os.environ.get("GPU_TERMINAL_SETTINGS_FILE")
    d = tempfile.mkdtemp(prefix="kilix95-conf-")
    path = os.path.join(d, "kitty.conf")
    with open(path, "wb") as f:
        f.write(text if binary else text.encode())
    os.environ["KITTY_CONFIG_DIRECTORY"] = d
    os.environ["GPU_TERMINAL_SETTINGS_FILE"] = os.path.join(d, "settings.conf")
    try:
        yield path
    finally:
        if prev is None:
            os.environ.pop("KITTY_CONFIG_DIRECTORY", None)
        else:
            os.environ["KITTY_CONFIG_DIRECTORY"] = prev
        if prev_shared is None:
            os.environ.pop("GPU_TERMINAL_SETTINGS_FILE", None)
        else:
            os.environ["GPU_TERMINAL_SETTINGS_FILE"] = prev_shared


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@contextlib.contextmanager
def storage_conf():
    """Use the canonical Kilix storage path with no config override."""
    old_kitty = os.environ.pop("KITTY_CONFIG_DIRECTORY", None)
    old_storage = os.environ.get("KILIX_STORAGE_HOME")
    old_config = os.environ.pop("KILIX_CONFIG_HOME", None)
    root = tempfile.mkdtemp(prefix="kilix-storage-")
    os.environ["KILIX_STORAGE_HOME"] = root
    try:
        yield root
    finally:
        if old_kitty is not None:
            os.environ["KITTY_CONFIG_DIRECTORY"] = old_kitty
        else:
            os.environ.pop("KITTY_CONFIG_DIRECTORY", None)
        if old_storage is None:
            os.environ.pop("KILIX_STORAGE_HOME", None)
        else:
            os.environ["KILIX_STORAGE_HOME"] = old_storage
        if old_config is None:
            os.environ.pop("KILIX_CONFIG_HOME", None)
        else:
            os.environ["KILIX_CONFIG_HOME"] = old_config


# ── F06: raw editor edits survive a tab roundtrip and reach disk ────────────
with conf("font_size 12\n") as path:
    import apps
    d = H.make_desk()
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    assert win is not None

    win._switch_tab(win.raw_tab)             # go to the raw kitty.conf tab
    win.ta.set_text(win.ta.text() + "map ctrl+j scroll_line_down\n")
    win._switch_tab(0)                       # leave tab 2 …
    win._switch_tab(win.raw_tab)             # … and come back
    assert "map ctrl+j scroll_line_down" in win.ta.text(), \
        "F06: raw edit did not survive a tab roundtrip"

    # and an Apply issued from a form tab must persist the raw edit
    win._switch_tab(0)
    win._apply()
    saved = read(path)
    assert "map ctrl+j scroll_line_down" in saved, \
        "F06: Apply from a form tab wrote a stale buffer"
    assert "font_size" in saved


# ── F27: an untouched Apply is loss-free on odd-but-valid config ────────────
odd = (
    "# hand-tuned kilix config\n"
    "tab_bar_style custom\n"           # valid kitty value the dropdown omits
    "font_size        11.5\n"          # odd whitespace, must be preserved
    "map ctrl+shift+e launch --type=tab\n"
    "enable_audio_bell true\n"         # present as 'true', not 'yes'
    "symbol_map U+E0A0-U+E0A3 PowerlineSymbols\n"
)
with conf(odd) as path:
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")

    # the non-listed value must be shown, not silently reset to options[0]
    kind, wd = win.fields["tab_bar_style"]
    assert wd.value == "custom", \
        f"F27: non-listed tab_bar_style shown as {wd.value!r}, not 'custom'"

    win._apply()                             # user changed nothing
    after = read(path)
    assert after == odd, \
        "F27: untouched Apply mutated the config:\n--- before ---\n" \
        + odd + "\n--- after ---\n" + after
    # specifically: nothing rewritten, no managed defaults appended
    assert "tab_bar_style fade" not in after
    assert "cursor_shape" not in after
    assert "copy_on_select" not in after
    assert settings.MARKER not in after


# ── F27b: a real form change still writes (and only that key) ───────────────
with conf(odd) as path:
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    kind, wd = win.fields["cursor_shape"]
    wd.index = wd.options.index("beam")      # user picks a value
    win._apply()
    after = read(path)
    assert settings.get_key(after, "cursor_shape") == "beam", \
        "F27b: an actual choice change was not written"
    assert "tab_bar_style custom" in after   # untouched keys preserved
    assert settings.get_key(after, "font_size") == "11.5"
    assert "copy_on_select" not in after     # still no unrelated defaults


# ── F52: a non-UTF-8 kitty.conf must not make Settings unopenable ───────────
with conf(b"# note: caf\xe9 sync\nfont_size 13\n", binary=True) as path:
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)           # must not raise UnicodeDecodeError
    win = H.find_window(d, "SettingsWin")
    assert win is not None, "F52: Settings failed to open on a non-UTF-8 config"
    kind, wd = win.fields["font_size"]
    assert wd.text == "13", "F52: config was not parsed after tolerant decode"


# Top-bar widgets, pane-title buttons, and game availability share one file.
with conf("font_size 12\n") as path:
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")

    for key in settings.shared_settings.MANAGED_KEYS:
        assert key in win.fields, f"Kilix 95 Settings is missing {key}"
    _, volume = win.fields["KILIX_CHROME_VOLUME"]
    _, thermal = win.fields["KILIX_CHROME_TEMPERATURE"]
    _, network = win.fields["KILIX_CHROME_NETWORK"]
    _, synchronize = win.fields["KILIX_CHROME_BUTTON_SYNCHRONIZE_INPUT"]
    _, memory_mode = win.fields["KILIX_CHROME_PANE_MEMORY_MODE"]
    _, close = win.fields["KILIX_CHROME_BUTTON_CLOSE"]
    _, doom = win.fields["KILIX_GAME_DOOM"]
    _, lights = win.fields["KILIX_GAME_KILIX_LIGHTS"]
    _, super_kilix = win.fields["KILIX_GAME_SUPER_KILIX"]
    assert not thermal.checked, "thermal widget should be disabled by default"
    assert synchronize.checked, "synchronized-input button should default on"
    assert memory_mode.value == "auto", "pane memory chip should default to auto"
    thermal.checked = True
    volume.checked = False
    network.checked = False
    synchronize.checked = False
    memory_mode.index = memory_mode.options.index("always")
    close.checked = False
    doom.checked = False
    lights.checked = False
    super_kilix.checked = False
    win._apply()

    shared_text = read(win.shared_path)
    assert "KILIX_CHROME_TEMPERATURE=1" in shared_text
    assert "KILIX_CHROME_VOLUME=0" in shared_text
    assert "KILIX_CHROME_NETWORK=0" in shared_text
    assert "KILIX_CHROME_BUTTON_SYNCHRONIZE_INPUT=0" in shared_text
    assert "KILIX_CHROME_PANE_MEMORY_MODE=always" in shared_text
    assert "KILIX_CHROME_BUTTON_CLOSE=0" in shared_text
    assert "KILIX_GAME_DOOM=0" in shared_text
    assert "KILIX_GAME_KILIX_LIGHTS=0" in shared_text
    assert "KILIX_GAME_SUPER_KILIX=0" in shared_text
    assert "KILIX_CHROME_NETWORK" not in read(path)


# ── font-size buttons: same setting as the CLI / kitty shortcut path ───────
with conf("# empty-ish\n") as path:
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    kind, audio = win.fields["enable_audio_bell"]
    assert not audio.checked, "Audio bell should default off"
    kind, wd = win.fields["font_size"]

    win._font_size_adjust(settings.FONT_SIZE_STEP)
    assert wd.text == "13", "font size + button did not start from default 11"
    after = read(path)
    assert settings.get_key(after, "font_size") == "13"
    assert "# empty-ish" in after

    win._font_size_adjust(-settings.FONT_SIZE_STEP)
    assert settings.get_key(read(path), "font_size") == "11"

    wd.set("not-a-number")
    win._font_size_adjust(settings.FONT_SIZE_STEP)
    assert wd.text == "13", "invalid font size should fall back to default"

    win._font_size_reset()
    assert settings.get_key(read(path), "font_size") == "11"


# ── desktop flavor is visible in kilix Settings, not only the Start menu ────
with conf("# empty-ish\n") as path, H.desktop_dir():
    T.apply_flavor("95")
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")

    assert win.flavor_dd is not None, "Settings is missing Desktop flavor"
    assert win.flavor_dd.value == "kilix 95"
    win.flavor_dd._pick(win._flavor_keys.index("xp"))

    assert T.flavor_name() == "xp"
    assert d.shell.state["flavor"] == "xp"
    assert win.flavor_dd.value == "kilix XP"


# The nostalgia layer is a persistent, default-off desktop preference.
with conf("# full experience\n") as path, H.desktop_dir():
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")

    assert win.full_experience.checked is False
    assert not d.shell.full_experience_enabled()
    assert "My Briefcase" not in {item["label"] for item in d.shell.grid.items}

    win.full_experience.checked = True
    win._apply()
    assert d.shell.full_experience_enabled()
    assert "My Briefcase" in {item["label"] for item in d.shell.grid.items}

    d2 = H.make_desk()
    assert d2.shell.full_experience_enabled(), "preference was not persisted"


# The no-override path creates a private project config and leaves tracked host
# defaults untouched. This is the normal launcher path, not only a fallback.
defaults = os.path.join(settings._shell.KILIX_HOME, "config", "kitty.conf")
with open(defaults, "rb") as f:
    defaults_before = f.read()
with storage_conf() as storage_root:
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    expected = os.path.join(storage_root, "config", "kitty.conf")
    assert win.path == expected
    assert not os.path.exists(expected)
    win._apply()
    assert os.path.isfile(expected)
    assert stat.S_IMODE(os.stat(expected).st_mode) == 0o600
    assert "include .kilix-defaults.conf" in read(expected)
with open(defaults, "rb") as f:
    assert f.read() == defaults_before, "Settings modified tracked defaults"


# Atomic replacement must replace a stale link rather than following it and
# rewriting an unrelated file.
with storage_conf() as storage_root:
    directory = os.path.join(storage_root, "config")
    os.makedirs(directory)
    unrelated = os.path.join(storage_root, "unrelated.conf")
    with open(unrelated, "w", encoding="utf-8") as f:
        f.write("keep me\n")
    target = os.path.join(directory, "kitty.conf")
    os.symlink(unrelated, target)
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    win.buffer = "font_size 14\n"
    win._apply()
    assert not os.path.islink(target)
    assert read(target) == "font_size 14\n"
    assert read(unrelated) == "keep me\n"


# Tools exposes the optional tmux-cli `tb` alias installer without writing it
# into kitty.conf or the shared chrome settings document.
with conf("font_size 12\n"):
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    tools_tab = settings.FORM_PAGES.index(settings.TOOLS)
    win._switch_tab(tools_tab)
    assert win.tb_alias_button.visible
    yolo_key = settings.shared_settings.CODING_YOLO_KEY
    yolo = win.fields[yolo_key][1]
    assert yolo.options == ["off", "on"], yolo.options
    assert yolo.value == "off", yolo.value
    assert win.coding_title.y > win.tools_note.y + win.tools_note.h
    assert yolo.y > win.coding_title.y + win.coding_title.h
    assert all(note.y > yolo.y + yolo.h for note in win.coding_notes)
    called = []
    d.shell.install_tb_alias = lambda: called.append(True) or True
    win._install_tb_alias()
    assert called == [True]
    assert "new tab" in win.tb_alias_status.text
    yolo.index = yolo.options.index("on")
    win._apply()
    assert settings.shared_settings.coding_yolo(win.shared_path)
    assert yolo_key not in read(win.path), \
        "shared coding policy reached kitty.conf"


# Session logs edits the same shared document as the kilix CLI and TUI, and
# never writes its controls into kitty.conf.
with conf("font_size 12\n") as target:
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    log_tab = settings.FORM_PAGES.index(settings.SESSION_LOG)
    win._switch_tab(log_tab)

    # Defaults arrive from the shared SDK: recording on, graphics elided.
    assert win.fields["KILIX_TRANSCRIPT"][1].checked
    shared_settings = settings.shared_settings
    graphics = win.fields[shared_settings.TRANSCRIPT_GRAPHICS_KEY][1]
    size = win.fields[shared_settings.TRANSCRIPT_LIMIT_KEY][1]
    assert graphics.value == "elide", graphics.value
    assert size.value == "8M", size.value

    # The directory budgets bound the whole transcript tree, not one pane, so
    # a long-running desktop cannot fill the disk with dead panes' logs.
    total = win.fields[shared_settings.TRANSCRIPT_TOTAL_KEY][1]
    archive = win.fields[shared_settings.TRANSCRIPT_ARCHIVE_KEY][1]
    assert total.value == shared_settings.TRANSCRIPT_TOTAL_DEFAULT, total.value
    assert archive.value == shared_settings.TRANSCRIPT_ARCHIVE_DEFAULT, archive.value
    assert "off" in archive.options, archive.options

    win.fields["KILIX_TRANSCRIPT"][1].checked = False
    graphics.index = graphics.options.index("keep")
    size.index = size.options.index("32M")
    win._apply()

    shared_text = read(win.shared_path)
    assert "KILIX_TRANSCRIPT=0" in shared_text, shared_text
    assert f"{shared_settings.TRANSCRIPT_GRAPHICS_KEY}=keep" in shared_text
    assert f"{shared_settings.TRANSCRIPT_LIMIT_KEY}=32M" in shared_text
    assert "KILIX_TRANSCRIPT" not in read(target)
    assert not shared_settings.transcript_enabled(win.shared_path)
    assert shared_settings.transcript_limit(win.shared_path) == 32 * 1024 * 1024


# Voice sits after Session logs, so every section ahead of it keeps the numeric
# position the CLI and the TUI derive from this same order. Its controls are
# shared settings; none of them belongs in kitty.conf.
with conf("font_size 12\n") as target:
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    shared_settings = settings.shared_settings
    voice_tab = settings.FORM_PAGES.index(settings.VOICE)
    assert win.tabs.tabs[:voice_tab] == [
        "Appearance", "Behavior", "Top bar", "Pane buttons", "Session logs",
    ], win.tabs.tabs
    assert win.tabs.tabs[voice_tab] == "Voice", win.tabs.tabs
    assert win.tabs.tabs[voice_tab + 1] == "Games", win.tabs.tabs
    win._switch_tab(voice_tab)

    for key, _label, _kind, _extra in settings.VOICE:
        assert key in win.shared_keys, \
            f"{key} would be written to kitty.conf, where nothing reads it"

    # Choices and defaults come from the SDK rather than being retyped here: a
    # form that disagrees with the vocabulary the fork reads is a silent bug,
    # since an unrecognised value reads back as the default without saying so.
    for key, (default, choices) in shared_settings.VOICE_CHOICE_SPECS.items():
        _kind, wd = win.fields[key]
        assert wd.options == list(choices), (key, wd.options)
        assert wd.value == default, (key, wd.value)
    for key, (default, _pattern) in shared_settings.VOICE_TOKEN_SPECS.items():
        assert win.fields[key][1].text == default, key
    for key in ("KILIX_CHROME_SPEAK", "KILIX_CHROME_DICTATE",
                shared_settings.VOICE_PUNCTUATION_KEY):
        assert win.fields[key][1].checked, f"{key} should ship enabled"

    engine = win.fields[shared_settings.VOICE_TTS_ENGINE_KEY][1]
    engine.index = engine.options.index("mbrola")
    rate = win.fields[shared_settings.VOICE_TTS_RATE_KEY][1]
    rate.index = rate.options.index("240")
    history = win.fields[shared_settings.VOICE_HISTORY_KEY][1]
    history.index = history.options.index("on")
    win.fields[shared_settings.VOICE_TTS_VOICE_KEY][1].set("mb-us1")
    win.fields["KILIX_CHROME_DICTATE"][1].checked = False
    win._apply()

    shared_text = read(win.shared_path)
    assert f"{shared_settings.VOICE_TTS_ENGINE_KEY}=mbrola" in shared_text
    assert f"{shared_settings.VOICE_TTS_RATE_KEY}=240" in shared_text
    assert f"{shared_settings.VOICE_TTS_VOICE_KEY}=mb-us1" in shared_text
    assert f"{shared_settings.VOICE_HISTORY_KEY}=on" in shared_text
    assert "KILIX_CHROME_DICTATE=0" in shared_text
    assert "KILIX_VOICE" not in read(target), "voice keys reached kitty.conf"
    assert shared_settings.tts_rate(win.shared_path) == 240
    assert shared_settings.voice_history(win.shared_path)


# The submit policy is the safety-relevant control on this tab: dictation that
# presses Enter on its own behalf turns a misrecognition into a command. The
# two values are written out rather than read from the SDK, so that widening
# the vocabulary fails here even if every other assertion still agrees.
with conf("font_size 12\n"):
    d = H.make_desk()
    import apps
    apps.open(d, "settings", None)
    win = H.find_window(d, "SettingsWin")
    _, submit = win.fields[shared_settings.VOICE_STT_SUBMIT_KEY]
    assert submit.options == ["never", "confirm"], submit.options
    assert submit.value == "never", submit.value
    for key, _label, _kind, _extra in settings.VOICE:
        assert "always" not in getattr(win.fields[key][1], "options", ()), key

    submit.index = submit.options.index("confirm")
    win._apply()
    assert shared_settings.stt_submit(win.shared_path) == "confirm"

    # Asking first is the most a settings file can request. A hand-written
    # third policy is not honoured — the accessor validates and falls back.
    with open(win.shared_path, "a", encoding="utf-8") as stream:
        stream.write(f"{shared_settings.VOICE_STT_SUBMIT_KEY}=always\n")
    assert shared_settings.stt_submit(win.shared_path) == "never"


# Start ▸ Programs carries both voice TUIs. Each prefers an installed command
# over the pinned Kilix installer, and an entry that resolves to nothing says
# so: a missing speech engine degrades the feature, it never swallows a click.
with conf("font_size 12\n") as target:
    d = H.make_desk()
    d.taskbar.open_start_menu()
    programs = next(item for item in d.menus.stack[0].items
                    if item.label == "Programs")
    entries = {item.label: item for item in programs.submenu}
    assert entries["Read Aloud"].icon == "speak"
    assert entries["Dictation"].icon == "microphone"

    opened = []
    d.shell._tab = lambda argv, title, cwd=None: opened.append(
        (argv, title, cwd)) or True
    real_which = shell_mod.shutil.which
    shell_mod.shutil.which = lambda name: (
        f"/usr/local/bin/{name}" if name in ("kilix-tts", "kilix-stt")
        else real_which(name))
    try:
        entries["Read Aloud"].action()
        entries["Dictation"].action()
    finally:
        shell_mod.shutil.which = real_which
    home = os.path.expanduser("~")
    assert opened == [
        (["/usr/local/bin/kilix-tts"], "Read Aloud", home),
        (["/usr/local/bin/kilix-stt"], "Dictation", home),
    ], opened

    messages = []
    real_msgbox = shell_mod.wm.msgbox
    real_kilix_home = shell_mod.KILIX_HOME
    shell_mod.wm.msgbox = lambda desk, title, text, **kw: messages.append(
        (title, text, kw))
    shell_mod.KILIX_HOME = os.path.dirname(target)   # holds no kilix launcher
    shell_mod.shutil.which = lambda name: None
    try:
        assert entries["Read Aloud"].action() is False
        assert entries["Dictation"].action() is False
    finally:
        shell_mod.wm.msgbox = real_msgbox
        shell_mod.KILIX_HOME = real_kilix_home
        shell_mod.shutil.which = real_which
    assert [title for title, _text, _kw in messages] == \
        ["Read Aloud", "Dictation"], messages
    assert all(kw.get("icon") == "error" for _t, _m, kw in messages), messages
    assert len(opened) == 2, "an unresolved target still opened a tab"


print("ok")
