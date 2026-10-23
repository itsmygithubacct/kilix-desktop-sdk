"""kilix desktop — freedesktop application discovery.

The scanner itself lives in the host SDK (`kilix_sdk.xdgapps`, SDK 1.8) so
every desktop and the launcher catalog share one implementation. This module
keeps the desktop-side half: icon mapping and `launch(shell, entry)`, which
hands a discovered entry to Shell.launch. Everything is driven by
$XDG_DATA_HOME / $XDG_DATA_DIRS (spec defaults when unset); nothing about the
host machine is hardcoded.
"""
import shlex
from pathlib import Path
import icons

import host as kilix_host

kilix_host.add_kilix_config_path()

import vbox
import widgets as W
import wm

from kilix_sdk import xdgapps as _shared

# Discovery is the SDK's; these names stay importable here so the desktop's
# menus and tests keep one vocabulary.
BUCKET_ORDER = _shared.BUCKET_ORDER
app_dirs = _shared.app_dirs
scan = _shared.scan
bucket = _shared.bucket
grouped = _shared.grouped

# bucket → an existing kilix icon name (generic "app" fallback)
_BUCKET_ICONS = {
    "Accessories": "app",
    "Development": "terminal",
    "Education": "doc_text",
    "Games": "exe",
    "Graphics": "paint",
    "Internet": "browser",
    "Multimedia": "amp",
    "Office": "doc_text",
    "System": "settings",
    "Other": "app",
}


def icon_for(entry):
    name = entry.get("icon", "")
    if name in icons.ICONS:
        return name
    if name and Path(name).is_absolute() and Path(name).is_file():
        return name
    if name and "/" not in name:
        # Prefer the application's own raster artwork when the icon theme
        # supplies it; category icons remain the fallback for SVG-only themes.
        for apps in app_dirs():
            base = Path(apps).parent
            for size in ("32x32", "48x48", "64x64", "16x16", "128x128"):
                path = base / "icons/hicolor" / size / "apps" / (name + ".png")
                if path.is_file():
                    return str(path)
            for suffix in ("", ".png", ".xpm"):
                path = base / "pixmaps" / (name + suffix)
                if path.is_file():
                    return str(path)
    return _BUCKET_ICONS.get(bucket(entry), "app")


# ── launching ────────────────────────────────────────────────────────────────

def launch(shell, entry, mode="tab"):
    """Open a discovered app. mode "tab" (default) synthesizes a launcher spec
    and runs it in a kilix tab; "window" streams it into a Win95 desktop window
    via XPane (the way the media player runs); "fullscreen" is the same, sized
    to the whole screen."""
    name = entry.get("name") or "app"
    if vbox.is_virtualbox_entry(entry):
        argv = vbox.entry_argv(entry, fullscreen=(mode == "fullscreen"))
        if not argv:
            wm.msgbox(shell.desk, name, "Launcher has no Exec line.",
                      icon="error")
            return
        shell.open_x11_tab(argv, name, cwd=entry.get("workdir") or None,
                           fill=(mode == "fullscreen"),
                           size=shell.desk.size() if mode == "fullscreen"
                           else None,
                           refit_windows=True)
        return
    if mode in ("window", "fullscreen"):
        try:                               # malformed Exec must not kill the desktop
            argv = shlex.split(entry.get("exec", ""))
        except ValueError:
            argv = []
        if not argv:                       # discovered entries always have one
            wm.msgbox(shell.desk, name, "Launcher has no Exec line.",
                      icon="error")
            return
        size = shell.desk.size() if mode == "fullscreen" else None
        shell.open_in_xpane(argv, name, icon=icon_for(entry),
                            cwd=entry.get("workdir") or None, app_size=size)
        return
    spec = {
        "Name": name,
        "Exec": entry.get("exec", ""),
        "Path": entry.get("workdir") or "~",
        "X-Kilix-Open": "tab" if entry.get("terminal") else "run",
    }
    shell.launch(spec)


def app_context(shell, entry):
    """Right-click menu: run the app in a kilix tab or a desktop window."""
    MI = W.MenuItem
    items = [MI("Open in tab", action=lambda: launch(shell, entry, "tab"))]
    if vbox.is_virtualbox_entry(entry):
        items.append(
            MI("Open fullscreen", action=lambda: launch(shell, entry, "fullscreen")))
        return items
    if not entry.get("terminal"):          # no tty on Xvfb → dead window
        items.append(
            MI("Open in window", action=lambda: launch(shell, entry, "window")))
        items.append(
            MI("Open fullscreen", action=lambda: launch(shell, entry, "fullscreen")))
    return items
