"""Classic Control Panel namespace and small property-sheet applets."""

import datetime
import os
import platform
import shutil
import subprocess
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import themes
import theme as T
import widgets as W
import wm


CONTROL_ITEMS = [
    ("Display", "display", "displayprops", None),
    ("Themes", "theme", "displayprops", "themes"),
    ("Sounds", "soundcp", "soundcp", None),
    ("Mouse", "mouse", "mouseprops", None),
    ("Keyboard", "keyboard", "keyboardprops", None),
    ("Date/Time", "datetime", "datetime", None),
    ("Fonts", "fonts", "fonts", None),
    ("Printers", "printer", "printers", None),
    ("Network", "network", "networkhood", None),
    ("Dial-Up Networking", "dialup", "dialup", None),
    ("Add New Hardware", "hardware", "hardware", None),
    ("System", "system", "systemprops", None),
    ("PowerToys", "powertoys", "powertoys", None),
]


class ControlPanel(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Control Panel", 560, 430, icon="controlpanel")
        self.min_w, self.min_h = 390, 280
        cw, ch = self.client_size()
        self.menubar = self.add(W.MenuBar(cw, [
            ("File", self._file_menu), ("View", self._view_menu),
            ("Help", self._help_menu)]))
        self.grid = self.add(W.IconGrid(
            2, T.MENU_H + 2, cw - 4, ch - T.MENU_H - 23,
            on_activate=self._activate))
        self.grid.set_items([
            {"label": label, "icon": icon, "data": (app, value)}
            for label, icon, app, value in CONTROL_ITEMS
        ])
        self.set_focus(self.grid)

    def on_resize(self):
        cw, ch = self.client_size()
        self.menubar.w = cw
        self.grid.w, self.grid.h = cw - 4, ch - T.MENU_H - 23

    def draw_client(self, d, img):
        cw, ch = self.client_size()
        T.sunken(d, 2, ch - 21, cw - 3, ch - 3, fill=T.FACE)
        d.text((8, ch - 18), f"{len(self.grid.items)} object(s)",
               font=T.FONT, fill=T.TEXT)

    def _activate(self, item):
        app, value = item["data"]
        self.desk.shell.open_app(app, value)

    def _file_menu(self):
        selected = self.grid.selected_items()
        return [W.MenuItem("Open", enabled=bool(selected),
                           action=lambda: selected and self._activate(selected[0])),
                W.sep(), W.MenuItem("Close", action=self.close)]

    def _view_menu(self):
        return [W.MenuItem("Refresh", action=self.invalidate)]

    def _help_menu(self):
        return [W.MenuItem("About Control Panel…", icon="controlpanel",
                           action=lambda: wm.msgbox(
                               self.desk, "Control Panel",
                               "Use Control Panel to personalize Kilix 95 and "
                               "inspect connected host services.",
                               icon="controlpanel"))]


class _InputProperties(wm.Window):
    KIND = "Mouse"

    def __init__(self, desk, arg=None):
        icon = "mouse" if self.KIND == "Mouse" else "keyboard"
        super().__init__(desk, self.KIND + " Properties", 390, 280,
                         icon=icon, resizable=False)
        cw, ch = self.client_size()
        state = desk.shell.state
        if self.KIND == "Mouse":
            self.add(W.GroupBox(10, 8, cw - 20, 92, "Pointers"))
            self.add(W.Label(24, 38, "Scheme:"))
            values = themes.CURSORS
            current = state.get("cursor_scheme", "Standard")
            self.scheme = self.add(W.Dropdown(
                112, 32, 190, values,
                values.index(current) if current in values else 0))
            self.add(W.GroupBox(10, 108, cw - 20, 70, "Double-click speed"))
            self.add(W.Label(24, 136, "Speed:"))
            speeds = ["Slow", "Medium", "Fast"]
            current_speed = state.get("double_click_speed", "Medium")
            self.speed = self.add(W.Dropdown(
                112, 130, 120, speeds,
                speeds.index(current_speed) if current_speed in speeds else 1))
        else:
            self.add(W.GroupBox(10, 8, cw - 20, 122, "Character repeat"))
            self.add(W.Label(24, 38, "Repeat delay:"))
            delays = ["Long", "Medium", "Short"]
            current = state.get("key_repeat_delay", "Medium")
            self.delay = self.add(W.Dropdown(
                150, 32, 130, delays,
                delays.index(current) if current in delays else 1))
            self.add(W.Label(24, 76, "Repeat rate:"))
            rates = ["Slow", "Medium", "Fast"]
            current = state.get("key_repeat_rate", "Medium")
            self.rate = self.add(W.Dropdown(
                150, 70, 130, rates,
                rates.index(current) if current in rates else 1))
            self.add(W.Label(24, 106,
                             "These preferences are used by Kilix widgets.",
                             font=T.SMALL, color=T.SHADOW))

        def apply(close=False):
            if self.KIND == "Mouse":
                state["cursor_scheme"] = self.scheme.value
                state["double_click_speed"] = self.speed.value
            else:
                state["key_repeat_delay"] = self.delay.value
                state["key_repeat_rate"] = self.rate.value
            desk.shell._save_state()
            desk.dirty = True
            if close:
                self.close()

        self.add(W.Button(cw - 244, ch - 33, 72, 23, "OK", default=True,
                          cb=lambda: apply(True)))
        self.add(W.Button(cw - 164, ch - 33, 72, 23, "Cancel", cb=self.close))
        self.add(W.Button(cw - 84, ch - 33, 72, 23, "Apply", cb=apply))


class MouseProperties(_InputProperties):
    KIND = "Mouse"


class KeyboardProperties(_InputProperties):
    KIND = "Keyboard"


class _Clock(W.Widget):
    def __init__(self, x, y, size=106):
        super().__init__(x, y, size, size)
        self.now_cb = datetime.datetime.now

    def draw(self, d, img):
        now = self.now_cb()
        x0, y0, x1, y1 = self.x, self.y, self.x + self.w - 1, self.y + self.h - 1
        T.sunken(d, x0, y0, x1, y1, fill=T.WINDOW_BG)
        cx, cy, radius = (x0 + x1) // 2, (y0 + y1) // 2, self.w // 2 - 8
        d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                  fill=T.LIGHT, outline=T.TEXT)
        import math
        for hour in range(12):
            angle = math.radians(hour * 30 - 90)
            px = cx + int(math.cos(angle) * (radius - 6))
            py = cy + int(math.sin(angle) * (radius - 6))
            d.ellipse((px - 1, py - 1, px + 1, py + 1), fill=T.TEXT)
        minute = math.radians(now.minute * 6 - 90)
        hour = math.radians((now.hour % 12) * 30 + now.minute * .5 - 90)
        d.line((cx, cy, cx + int(math.cos(hour) * radius * .52),
                cy + int(math.sin(hour) * radius * .52)), fill=T.TEXT, width=2)
        d.line((cx, cy, cx + int(math.cos(minute) * radius * .76),
                cy + int(math.sin(minute) * radius * .76)), fill=T.TEXT)


class DateTimeProperties(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Date/Time Properties", 450, 330,
                         icon="datetime", resizable=False)
        cw, ch = self.client_size()
        self.clock = self.add(_Clock(20, 20))
        self.add(W.Label(150, 30, "Current date:"))
        self.date = self.add(W.Label(250, 30, ""))
        self.add(W.Label(150, 62, "Current time:"))
        self.time_label = self.add(W.Label(250, 62, ""))
        self.add(W.GroupBox(16, 146, cw - 32, 78, "Time zone"))
        zones = ["System default", "UTC", "US/Pacific", "US/Eastern",
                 "Europe/London", "Asia/Tokyo"]
        selected = desk.shell.state.get("display_timezone", "System default")
        self.zone = self.add(W.Dropdown(
            42, 174, 260, zones, zones.index(selected) if selected in zones else 0))
        self.clock.now_cb = self._now
        self.add(W.Label(42, 202,
                         "The host clock is displayed but is never changed.",
                         font=T.SMALL, color=T.SHADOW))
        self._last = ""
        self.desk.tick_hooks.append(self._tick)

        def apply(close=False):
            desk.shell.state["display_timezone"] = self.zone.value
            desk.shell._save_state()
            self._last = ""
            self._tick(time.time())
            if close:
                self.close()

        self.add(W.Button(cw - 164, ch - 33, 72, 23, "OK", default=True,
                          cb=lambda: apply(True)))
        self.add(W.Button(cw - 84, ch - 33, 72, 23, "Cancel", cb=self.close))
        self._tick(time.time())

    def _now(self):
        selected = self.zone.value
        if selected == "System default":
            return datetime.datetime.now().astimezone()
        try:
            return datetime.datetime.now(ZoneInfo(selected))
        except ZoneInfoNotFoundError:
            return datetime.datetime.now().astimezone()

    def _tick(self, now):
        current = self._now()
        stamp = current.strftime("%H:%M:%S")
        if stamp != self._last:
            self._last = stamp
            self.time_label.set(stamp)
            self.date.set(current.strftime("%A, %B %d, %Y"))
            self.clock.invalidate()

    def close(self):
        if self._tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self._tick)
        super().close()


class FontBrowser(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Fonts", 500, 390, icon="fonts")
        self.min_w, self.min_h = 360, 250
        cw, ch = self.client_size()
        self.list = self.add(W.ListBox(
            10, 10, cw - 20, ch - 90, on_select=self._select,
            on_activate=self._select))
        self.preview = self.add(W.Label(18, ch - 66,
                                        "The quick brown fox jumps over the lazy dog."))
        names = []
        try:
            result = subprocess.run(
                ["fc-list", ":", "family"], capture_output=True, text=True,
                timeout=3, check=False)
            if result.returncode == 0:
                names = sorted({part.strip() for line in result.stdout.splitlines()
                                for part in line.split(",") if part.strip()},
                               key=str.lower)
        except (OSError, subprocess.TimeoutExpired):
            pass
        names = names[:500] or ["Kilix system font"]
        self.list.set_items([("fonts", name, name) for name in names])
        if self.list.items:
            self.list.sel = 0

    def _select(self, item):
        if item:
            self.preview.set(f"{item[1]} — The quick brown fox jumps over the lazy dog.")

    def on_resize(self):
        cw, ch = self.client_size()
        self.list.w, self.list.h = cw - 20, ch - 90
        self.preview.y = ch - 66


class SystemProperties(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "System Properties", 480, 360,
                         icon="system", resizable=False)
        cw, ch = self.client_size()
        self.add(W.GroupBox(12, 10, cw - 24, 116, "System"))
        root = shutil.disk_usage("/")
        lines = [
            "Kilix 95 running on " + platform.system(),
            f"Kernel: {platform.release()}",
            f"Machine: {platform.machine() or 'unknown'}",
            f"Python: {platform.python_version()}",
            f"Disk free: {root.free // (1024 ** 2):,} MB",
        ]
        for index, line in enumerate(lines):
            self.add(W.Label(30, 34 + index * 17, line))
        self.add(W.GroupBox(12, 138, cw - 24, 78, "Device management"))
        self.add(W.Button(30, 166, 150, 23, "Device Manager…", icon="hardware",
                          cb=lambda: desk.shell.open_app("devicemanager")))
        self.add(W.Button(196, 166, 150, 23, "Disk Defragmenter…",
                          icon="defrag", cb=lambda: desk.shell.open_app("defrag")))
        self.add(W.Button(cw - 84, ch - 33, 72, 23, "OK", default=True,
                          cb=self.close))
