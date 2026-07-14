"""Windows 95-style Display Properties, themes, and screen-saver settings."""

import hashlib
import os
import secrets

from PIL import Image

import filedialog
import screensaver
import shell as shell_mod
import themes
import theme as T
import widgets as W
import wm


TIMEOUTS = [("1 minute", 60), ("3 minutes", 180), ("5 minutes", 300),
            ("10 minutes", 600), ("15 minutes", 900), ("Never", 0)]
ERAS = ["Windows 95 RTM", "Windows 95 Plus!", "Late Win9x", "Kilix XP"]


def _password_record(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 120000)
    return {"salt": salt, "digest": digest.hex()}


def verify_password(record, password):
    try:
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            bytes.fromhex(record["salt"]), 120000).hex()
        return secrets.compare_digest(check, record["digest"])
    except (KeyError, TypeError, ValueError):
        return False


def show_unlock(desk):
    """Show an unclosable local saver-password prompt."""
    record = desk.shell.state.get("saver_password")
    if not record:
        return None
    win = wm.Window(desk, "Unlock Kilix 95", 360, 180, icon="key",
                    resizable=False, modal=True)
    cw, _ = win.client_size()
    win.add(W.Label(16, 16, "Enter the screen saver password:"))
    field = win.add(W.TextField(16, 42, cw - 32, mask=True))
    status = win.add(W.Label(16, 72, "", color=(128, 0, 0)))

    def unlock(_text=None):
        if verify_password(record, field.text):
            win.close()
            desk.dirty = True
        else:
            field.set("")
            status.set("The password is not correct.")

    field.on_enter = unlock
    win.add(W.Button(cw - 92, 104, 76, 23, "Unlock", default=True,
                     cb=unlock))
    win.request_close = lambda: None
    win.set_focus(field)
    desk.wm.add(win)
    return win


class _SaverPreview(W.Widget):
    def __init__(self, x, y, w, h, name):
        super().__init__(x, y, w, h)
        self.name = name
        self.saver = screensaver.pick((max(1, w - 12), max(1, h - 18)), name)

    def set_name(self, name):
        self.name = name
        self.saver = screensaver.pick(
            (max(1, self.w - 12), max(1, self.h - 18)), name)
        self.invalidate()

    def draw(self, d, img):
        T.raised(d, self.x, self.y, self.x + self.w - 1, self.y + self.h - 1,
                 fill=T.DKSHADOW)
        x0, y0 = self.x + 6, self.y + 5
        frame = self.saver.step(.08)
        img.paste(frame, (x0, y0))
        d.rectangle((x0, y0, x0 + frame.width - 1, y0 + frame.height - 1),
                    outline=T.TEXT)
        d.rectangle((self.x + self.w // 2 - 18, self.y + self.h - 11,
                     self.x + self.w // 2 + 18, self.y + self.h - 8),
                    fill=T.SHADOW)


class _DesktopPreview(W.Widget):
    def __init__(self, x, y, w, h, color, pattern):
        super().__init__(x, y, w, h)
        self.color, self.pattern = tuple(color), pattern

    def set(self, color, pattern):
        self.color, self.pattern = tuple(color), pattern
        self.invalidate()

    def draw(self, d, img):
        T.raised(d, self.x, self.y, self.x + self.w - 1, self.y + self.h - 1,
                 fill=T.DKSHADOW)
        interior = Image.new("RGB", (self.w - 12, self.h - 18), self.color)
        if self.pattern != "None":
            from PIL import ImageDraw
            draw = ImageDraw.Draw(interior)
            fg = tuple(min(255, c + 48) for c in self.color)
            themes._pattern(draw, self.pattern, interior.size, fg)
        img.paste(interior, (self.x + 6, self.y + 5))
        d.rectangle((self.x + self.w // 2 - 18, self.y + self.h - 11,
                     self.x + self.w // 2 + 18, self.y + self.h - 8),
                    fill=T.SHADOW)


class DisplayProperties(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Display Properties", 570, 455, icon="display",
                         resizable=False)
        self.state = desk.shell.state
        cw, ch = self.client_size()
        self.tabs = self.add(W.TabBar(
            8, 7, cw - 16,
            ["Background", "Screen Saver", "Appearance", "Settings", "Themes"],
            cb=self._switch))
        self.panels = [[] for _ in range(5)]
        self._build_background(cw)
        self._build_saver(cw)
        self._build_appearance(cw)
        self._build_settings(cw)
        self._build_themes(cw)
        self.status = self.add(W.Label(12, ch - 29, "", font=T.SMALL,
                                       color=T.SHADOW))
        self.ok = self.add(W.Button(cw - 244, ch - 33, 72, 23, "OK",
                                    default=True, cb=lambda: self._apply(True)))
        self.cancel = self.add(W.Button(cw - 164, ch - 33, 72, 23, "Cancel",
                                        cb=self.close))
        self.apply = self.add(W.Button(cw - 84, ch - 33, 72, 23, "Apply",
                                       cb=self._apply))
        initial = 4 if arg == "themes" else 3 if arg == "settings" else 0
        self._switch(initial)
        self.tabs.active = initial

    def _add(self, panel, widget):
        self.panels[panel].append(self.add(widget))
        return widget

    def _build_background(self, cw):
        p = 0
        color_names = [name for name, _ in shell_mod.WALL_COLORS]
        current = tuple(self.state.get("wall_color", T.DESKTOP))
        color_i = next((i for i, (_, value) in enumerate(shell_mod.WALL_COLORS)
                        if tuple(value) == current), 0)
        self.bg_preview = self._add(
            p, _DesktopPreview(22, 46, 164, 126, current,
                               self.state.get("wall_pattern", "None")))
        self._add(p, W.Label(212, 48, "Color:"))
        self.bg_color = self._add(p, W.Dropdown(
            292, 42, 220, color_names, color_i, cb=lambda _v: self._preview_bg()))
        self._add(p, W.Label(212, 82, "Pattern:"))
        pattern = self.state.get("wall_pattern", "None")
        self.bg_pattern = self._add(p, W.Dropdown(
            292, 76, 220, themes.PATTERNS,
            themes.PATTERNS.index(pattern) if pattern in themes.PATTERNS else 0,
            cb=lambda _v: self._preview_bg()))
        self._add(p, W.Label(22, 196, "Wallpaper:"))
        self.bg_image = self._add(p, W.TextField(
            102, 190, cw - 226, self.state.get("wall_image") or ""))
        self._add(p, W.Button(cw - 112, 189, 78, 23, "Browse…", cb=self._browse))
        self._add(p, W.Label(22, 234, "Display:"))
        modes = ["stretch", "tile", "center"]
        mode = self.state.get("wall_mode", "stretch")
        self.bg_mode = self._add(p, W.Dropdown(
            102, 228, 140, modes, modes.index(mode) if mode in modes else 0))
        self._add(p, W.Label(
            22, 276,
            "Patterns and theme artwork are generated under Kilix 95 user data.",
            font=T.SMALL, color=T.SHADOW))

    def _build_saver(self, cw):
        p = 1
        names = screensaver.names()
        current = self.state.get("saver_name", "Mystify")
        self.saver_preview = self._add(p, _SaverPreview(
            22, 46, 194, 142, current))
        self._add(p, W.Label(244, 54, "Screen saver:"))
        self.saver_dd = self._add(p, W.Dropdown(
            244, 76, 250, names,
            names.index(current) if current in names else 0,
            cb=self.saver_preview.set_name))
        self._add(p, W.Button(244, 112, 88, 23, "Preview", cb=self._test_saver))
        self._add(p, W.Label(22, 218, "Wait:"))
        seconds = int(self.state.get("saver_idle", 180))
        timeout_i = min(range(len(TIMEOUTS)), key=lambda i: abs(TIMEOUTS[i][1] - seconds))
        self.timeout_dd = self._add(p, W.Dropdown(
            82, 212, 140, [label for label, _ in TIMEOUTS], timeout_i))
        self.lock = self._add(p, W.Checkbox(
            22, 254, "Password protected",
            checked=bool(self.state.get("saver_lock", False))))
        self._add(p, W.Button(244, 250, 132, 23, "Set Password…",
                              cb=self._set_password))
        self._add(p, W.Label(
            22, 294,
            "Any input exits Preview; password protection uses a local "
            "salted verifier.", font=T.SMALL, color=T.SHADOW))

    def _build_appearance(self, cw):
        p = 2
        self._add(p, W.GroupBox(18, 44, cw - 36, 112, "Scheme"))
        self._add(p, W.Label(38, 76, "Desktop flavor:"))
        flavors = [label for _, label in T.flavor_options()]
        active_flavor = T.flavor_label()
        self.flavor = self._add(p, W.Dropdown(
            180, 70, 210, flavors,
            flavors.index(active_flavor) if active_flavor in flavors else 0))
        self._add(p, W.Label(38, 114, "Pointer scheme:"))
        cursor = self.state.get("cursor_scheme", "Standard")
        self.cursor = self._add(p, W.Dropdown(
            180, 108, 210, themes.CURSORS,
            themes.CURSORS.index(cursor) if cursor in themes.CURSORS else 0))
        self._add(p, W.GroupBox(18, 176, cw - 36, 104, "Preview"))
        self._add(p, W.Label(42, 206,
                             "Active window     Selected item     Button"))
        self._add(p, W.Label(42, 236,
                             "Original 16-color artwork remains crisp at 1x and 2x.",
                             font=T.SMALL, color=T.SHADOW))

    def _build_settings(self, cw):
        p = 3
        self._add(p, W.GroupBox(18, 44, cw - 36, 96, "Desktop area"))
        w, h = self.desk.size()
        self._add(p, W.Label(38, 76, f"Current framebuffer: {w} by {h} pixels"))
        self._add(p, W.Label(38, 102,
                             "Resize the Kilix pane to change the desktop area.",
                             font=T.SMALL, color=T.SHADOW))
        self._add(p, W.GroupBox(18, 158, cw - 36, 132, "Compatibility"))
        era = self.state.get("era_profile", "Windows 95 Plus!")
        self._add(p, W.Label(38, 190, "Era profile:"))
        self.era = self._add(p, W.Dropdown(
            150, 184, 220, ERAS, ERAS.index(era) if era in ERAS else 1,
            cb=self._era_changed))
        self.full_drag = self._add(p, W.Checkbox(
            38, 226, "Show window contents while dragging",
            checked=bool(self.state.get("full_window_drag", True))))
        self.quick_launch = self._add(p, W.Checkbox(
            38, 256, "Show Quick Launch toolbar",
            checked=bool(self.state.get("show_quick_launch", True))))

    def _era_changed(self, era):
        """Seed the interaction defaults associated with each Win95 era."""
        classic = era in ("Windows 95 RTM", "Windows 95 Plus!")
        self.quick_launch.checked = not classic
        self.full_drag.checked = era != "Windows 95 RTM"
        self.invalidate()

    def _build_themes(self, cw):
        p = 4
        self._add(p, W.GroupBox(18, 44, cw - 36, 104, "Desktop theme"))
        names = list(themes.THEMES)
        active = self.state.get("theme", "Windows 95")
        self.theme_dd = self._add(p, W.Dropdown(
            38, 76, 280, names, names.index(active) if active in names else 0,
            cb=lambda _v: self._theme_info()))
        self._add(p, W.Button(336, 75, 154, 23, "Apply Theme", cb=self._apply_theme))
        self.theme_info = self._add(p, W.Label(38, 114, ""))
        self._add(p, W.GroupBox(18, 168, cw - 36, 118, "Theme includes"))
        self._add(p, W.Label(
            38, 198,
            "Wallpaper and pattern • desktop flavor • sound scheme"))
        self._add(p, W.Label(
            38, 224,
            "Pointer scheme • screen saver • era-appropriate presentation"))
        self._add(p, W.Label(
            38, 252, "All bundled themes use original Kilix artwork and sounds.",
            font=T.SMALL, color=T.SHADOW))
        self._theme_info()

    def _switch(self, index):
        self.tabs.active = index
        for panel_index, panel in enumerate(self.panels):
            for widget in panel:
                widget.visible = panel_index == index
        focus = [widget for widget in self.panels[index]
                 if widget.focusable and widget.visible and widget.enabled]
        self.set_focus(focus[0] if focus else None)
        self.invalidate()

    def _preview_bg(self):
        color = shell_mod.WALL_COLORS[self.bg_color.index][1]
        self.bg_preview.set(color, self.bg_pattern.value)

    def _browse(self):
        filedialog.open_file(
            self.desk, "Choose Wallpaper",
            lambda path: path and self.bg_image.set(path),
            start=os.path.dirname(self.bg_image.text)
            if self.bg_image.text.strip() else None,
            filters=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"),
                     ("All Files", "*.*")])

    def _test_saver(self):
        self._apply(False)
        self.desk._start_saver(self.saver_dd.value)

    def _set_password(self):
        def first(value):
            if value is None:
                return
            if not value:
                self.state.pop("saver_password", None)
                self.lock.checked = False
                self.status.set("Screen saver password cleared.")
                return

            def confirm(again):
                if again is None:
                    return
                if value != again:
                    wm.msgbox(self.desk, "Screen Saver Password",
                              "The passwords do not match.", icon="error")
                    return
                self.state["saver_password"] = _password_record(value)
                self.lock.checked = True
                self.desk.shell._save_state()
                self.status.set("Screen saver password set.")

            box = wm.inputbox(self.desk, "Screen Saver Password",
                              "Confirm password:", cb=confirm, icon="key")
            field = next(widget for widget in box.widgets
                         if isinstance(widget, W.TextField))
            field.mask = True

        box = wm.inputbox(self.desk, "Screen Saver Password",
                          "New password (blank clears):", cb=first, icon="key")
        field = next(widget for widget in box.widgets
                     if isinstance(widget, W.TextField))
        field.mask = True

    def _theme_info(self):
        spec = themes.THEMES[self.theme_dd.value]
        self.theme_info.set(
            f"{spec['pattern']} background, {spec['cursor']} pointer, "
            f"{spec['saver']} saver")

    def _apply_theme(self):
        themes.apply(self.desk.shell, self.theme_dd.value)
        self.status.set(f"{self.theme_dd.value} applied.")
        self.desk.taskbar.invalidate()
        self.desk.dirty = True

    def _apply(self, close=False):
        state = self.state
        color = shell_mod.WALL_COLORS[self.bg_color.index][1]
        pattern = self.bg_pattern.value
        image = self.bg_image.text.strip() or None
        if not image and pattern != "None":
            image = themes.wallpaper("Custom " + pattern, color, pattern)
        state.update({
            "wall_color": list(color), "wall_pattern": pattern,
            "wall_image": image, "wall_mode": self.bg_mode.value,
            "wall_custom": True, "saver_name": self.saver_dd.value,
            "saver_idle": TIMEOUTS[self.timeout_dd.index][1],
            "saver_lock": bool(self.lock.checked and state.get("saver_password")),
            "cursor_scheme": self.cursor.value,
            "era_profile": self.era.value,
            "full_window_drag": self.full_drag.checked,
            "show_quick_launch": self.quick_launch.checked,
        })
        flavor_keys = [key for key, _ in T.flavor_options()]
        self.desk.shell.set_flavor(flavor_keys[self.flavor.index])
        self.desk.saver_idle = float(state["saver_idle"])
        self.desk.shell._wall = None
        self.desk.shell._save_state()
        self.desk.shell.invalidate()
        self.desk.taskbar.invalidate()
        self.status.set("Display settings applied.")
        if close:
            self.close()
