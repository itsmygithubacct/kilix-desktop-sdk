"""Shell.open_in_xpane: an app opens as a desktop window via XPane, and an
XPane/Xvfb failure shows an error dialog instead of crashing the desktop."""
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import harness as H
import shell as shell_mod
import wm
from apps import xpane


class FakePane(wm.Window):
    """A real window that captures the argv/title it was built with, so wm.add
    genuinely succeeds (a bare stub would raise in wm.add and mask the real path
    with the error-dialog fallback)."""
    made = []

    def __init__(self, desk, argv, title, icon="exe", cwd=None, fill=False,
                 app_size=None, cleanup=None):
        FakePane.made.append((argv, title, icon, cwd, fill))
        super().__init__(desk, title, 400, 300, icon=icon)


def _with_pane(cls, fn):
    orig = xpane.XPane
    xpane.XPane = cls
    try:
        fn()
    finally:
        xpane.XPane = orig


# ── a real argv opens as a window on the desktop ─────────────────────────────
def opens_window():
    FakePane.made = []
    d = H.make_desk()
    n0 = len(d.wm.windows)

    def go():
        d.shell.open_in_xpane(["xterm", "-e", "top"], "xterm", icon="terminal")
    _with_pane(FakePane, go)
    assert len(d.wm.windows) == n0 + 1, "no window added"
    assert isinstance(d.wm.windows[-1], FakePane), \
        "the added window must be the pane itself, not an error dialog"
    argv, title, icon, cwd, fill = FakePane.made[-1]
    assert argv == ["xterm", "-e", "top"], argv
    assert title == "xterm" and icon == "terminal"
    assert cwd, "cwd must default to the home directory"
    assert fill is True, "open_in_xpane must maximize the app to fill the window"


# ── a raising XPane (Xvfb unavailable) shows an error box, no crash ──────────
def failure_shows_msgbox():
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("Xvfb: not found")

    d = H.make_desk()

    def go():
        d.shell.open_in_xpane(["true"], "Broken App")
    _with_pane(Boom, go)             # pre-fix: exception escapes, desk dies
    box = H.find_window(d, "Window")
    assert box is not None and box.modal, "no error dialog"
    assert not any(type(w).__name__ == "XPane" for w in d.wm.windows)


def pdf_viewer_chooser_uses_the_shared_window_plan():
    d = H.make_desk()
    seen = {}
    d.shell.open_in_xpane = lambda argv, title, **kwargs: seen.update(
        argv=list(argv), title=title, kwargs=kwargs) or True

    with tempfile.TemporaryDirectory() as directory:
        document = str(Path(directory) / "report.pdf")
        with patch("filedialog.open_file",
                   side_effect=lambda _desk, _title, cb, **_kwargs:
                   cb(document) or True):
            assert d.shell.open_kilix_pdf()
    assert seen["argv"] == [
        os.path.join(H.KILIX_HOME, "kilix"), "app", "window",
        "kilix-pdf", "--action", "open", "--", document,
    ], seen
    assert seen["title"] == "PDF Viewer"
    assert seen["kwargs"]["icon"] == "doc_text"
    assert seen["kwargs"]["app_size"] == (960, 700)


def pdf_file_association_uses_the_viewer():
    d = H.make_desk()
    seen = {}
    d.shell.open_catalog_application = lambda content_id, **kwargs: seen.update(
        content_id=content_id, kwargs=kwargs) or True
    with tempfile.TemporaryDirectory() as directory:
        document = Path(directory) / "manual.PDF"
        document.write_bytes(b"%PDF-1.4\n")
        d.shell.open_path(str(document))
    assert seen == {
        "content_id": "kilix-pdf",
        "kwargs": {"action": "open", "arguments": (str(document),)},
    }


def firefox_defaults_to_filled_run_tab():
    d = H.make_desk()
    seen = {}
    d.shell._first_on_path = lambda cands: "/usr/bin/firefox-esr"
    d.shell._tab = lambda argv, title, cwd=None, **kw: seen.update(
        argv=argv, title=title, cwd=cwd, kw=kw) or True

    d.shell.open_browser("firefox")

    assert os.path.basename(seen["argv"][0]) == "kilix", seen
    assert seen["argv"][1:] == [
        "run", "--fill", "/usr/bin/firefox-esr", "--no-remote",
        d.shell.BROWSER_HOME,
    ], seen
    assert seen["title"] == "Firefox"
    assert seen["kw"]["env"]["KILIX_IN_OVERLAY"] == "1"


def default_browser_links_use_the_real_browser_dispatch():
    d = H.make_desk()
    seen = {}
    d.shell._first_on_path = lambda cands: "/usr/bin/chromium"
    d.shell._tab = lambda argv, title, cwd=None, **kw: seen.update(
        argv=argv, title=title, cwd=cwd, kw=kw) or True
    assert d.shell.open_default_browser_tab(
        "https://example.invalid/manual", "Manual") is True

    assert os.path.basename(seen["argv"][0]) == "kilix", seen
    assert seen["argv"][1:] == [
        "run", "--fill", "/usr/bin/chromium",
        "https://example.invalid/manual"], seen
    assert seen["title"] == "Manual"
    assert seen["kw"]["env"]["KILIX_IN_OVERLAY"] == "1"


def url_launchers_use_the_real_browser_dispatch():
    d = H.make_desk()
    seen = {}
    d.shell._first_on_path = lambda cands: "/usr/bin/firefox-esr"
    d.shell._tab = lambda argv, title, cwd=None, **kw: seen.update(
        argv=argv, title=title, cwd=cwd, kw=kw) or True

    d.shell.open_url("https://example.invalid/launcher")

    assert os.path.basename(seen["argv"][0]) == "kilix", seen
    assert seen["argv"][1:] == [
        "run", "--fill", "/usr/bin/firefox-esr", "--no-remote",
        "https://example.invalid/launcher"], seen
    assert seen["kw"]["env"]["KILIX_IN_OVERLAY"] == "1"


def chromium_defaults_to_filled_run_tab():
    d = H.make_desk()
    seen = {}
    d.shell._first_on_path = lambda cands: "/usr/bin/chromium"
    d.shell._tab = lambda argv, title, cwd=None, **kw: seen.update(
        argv=argv, title=title, cwd=cwd, kw=kw) or True

    d.shell.open_browser("chromium")

    assert os.path.basename(seen["argv"][0]) == "kilix", seen
    assert seen["argv"][1:] == [
        "run", "--fill", "/usr/bin/chromium",
        d.shell.BROWSER_HOME], seen
    assert seen["title"] == "Chromium"
    assert seen["kw"]["env"]["KILIX_IN_OVERLAY"] == "1"


def chromium_window_mode_uses_a_private_profile():
    d = H.make_desk()
    seen = {}
    d.shell._first_on_path = lambda cands: "/usr/bin/chromium"
    d.shell.open_in_xpane = lambda argv, title, **kw: seen.update(
        argv=argv, title=title, kw=kw) or True

    d.shell.open_browser("chromium", "window")

    profile_arg = next(
        arg for arg in seen["argv"] if arg.startswith("--user-data-dir="))
    profile = profile_arg.split("=", 1)[1]
    assert os.path.isdir(profile)
    seen["kw"]["cleanup"]()
    assert not os.path.exists(profile)


def browser_fallback_stays_in_its_existing_tab():
    d = H.make_desk()
    seen = {}
    d.shell._first_on_path = lambda cands: None
    d.shell._tab = lambda argv, title, cwd=None, **kw: seen.update(
        argv=argv, title=title, cwd=cwd, kw=kw) or True

    assert d.shell.open_default_browser_tab("https://example.invalid") is True
    assert seen["argv"][1:] == ["open-url", "https://example.invalid"], seen
    assert seen["kw"]["env"]["KILIX_IN_OVERLAY"] == "1"


def copied_gui_launcher_defaults_to_run_and_strips_field_codes():
    d = H.make_desk()
    seen = {}
    d.shell.open_x11_tab = lambda argv, title, cwd=None, **kw: seen.update(
        argv=argv, title=title, cwd=cwd, kw=kw) or True

    d.shell.launch({
        "Type": "Application", "Name": "Chromium",
        "Exec": "/usr/bin/chromium %U",
    })

    assert seen["argv"] == ["/usr/bin/chromium"], seen
    assert seen["title"] == "Chromium"


def copied_terminal_launchers_strip_field_codes_before_shell_execution():
    for mode in ("tab", "window"):
        d = H.make_desk()
        seen = {}
        d.shell._spawn_kitty_launch = (
            lambda opts, cmd, title, cwd=None: seen.update(
                opts=opts, cmd=cmd, title=title, cwd=cwd) or True)

        d.shell.launch({
            "Type": "Application", "Name": "Terminal tool",
            "Exec": "terminal-tool %U --label 'two words'",
            "Terminal": "true", "X-Kilix-Open": mode,
        })

        assert seen["cmd"] == "terminal-tool --label 'two words'", seen
        expected = "--type=tab" if mode == "tab" else "--type=os-window"
        assert seen["opts"] == [expected], seen


def copied_launcher_expands_field_codes_without_argument_debris():
    d = H.make_desk()
    seen = {}
    d.shell.open_x11_tab = lambda argv, title, cwd=None, **kw: seen.update(
        argv=argv, title=title, cwd=cwd, kw=kw) or True
    desktop_path = "/tmp/example.desktop"

    d.shell.launch({
        "Type": "Application", "Name": "Demo Name", "Icon": "demo-icon",
        "Exec": 'demo "%U" --arg=%U pre%Upost %% %c %k %i',
    }, desktop_path)

    assert seen["argv"] == [
        "demo", "%", "Demo Name", desktop_path, "--icon", "demo-icon",
    ], seen


def malformed_copied_launcher_is_rejected():
    d = H.make_desk()
    d.shell.open_x11_tab = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("malformed launcher was executed"))
    d.shell.launch({
        "Type": "Application", "Name": "Broken", "Exec": "demo 'unterminated",
    })
    box = H.find_window(d, "Window")
    assert box is not None and box.modal


opens_window()
failure_shows_msgbox()
pdf_viewer_chooser_uses_the_shared_window_plan()
pdf_file_association_uses_the_viewer()
firefox_defaults_to_filled_run_tab()
chromium_defaults_to_filled_run_tab()
chromium_window_mode_uses_a_private_profile()
default_browser_links_use_the_real_browser_dispatch()
url_launchers_use_the_real_browser_dispatch()
browser_fallback_stays_in_its_existing_tab()
copied_gui_launcher_defaults_to_run_and_strips_field_codes()
copied_terminal_launchers_strip_field_codes_before_shell_execution()
copied_launcher_expands_field_codes_without_argument_debris()
malformed_copied_launcher_is_rejected()
print("ok")
