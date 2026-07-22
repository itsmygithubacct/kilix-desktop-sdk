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
import theme as T
from apps import settings

# _apply live-reloads the running kilix; make that a no-op under test so we
# never SIGUSR1 a real process or shell out to a kitten.
os.environ.pop("KITTY_LISTEN_ON", None)
os.environ.pop("KITTY_PID", None)


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
    _, network = win.fields["KILIX_CHROME_NETWORK"]
    _, close = win.fields["KILIX_CHROME_BUTTON_CLOSE"]
    _, doom = win.fields["KILIX_GAME_DOOM"]
    network.checked = False
    close.checked = False
    doom.checked = False
    win._apply()

    shared_text = read(win.shared_path)
    assert "KILIX_CHROME_NETWORK=0" in shared_text
    assert "KILIX_CHROME_BUTTON_CLOSE=0" in shared_text
    assert "KILIX_GAME_DOOM=0" in shared_text
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


print("ok")
