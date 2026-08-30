"""Useful Windows 95 PowerToys-inspired shell helpers."""

import os

import nostalgia
import theme as T
import widgets as W
import wm


TOOLS = [
    ("Command Prompt Here", "terminal", "terminal"),
    ("Explore From Here", "folder_open", "explore"),
    ("QuickRes", "display", "quickres"),
    ("DeskMenu", "desktop", "deskmenu"),
    ("Send To", "sendto", "sendto"),
    ("TweakUI", "powertoys", "tweakui"),
    ("Round Clock", "datetime", "clock"),
    ("Disk Defragmenter", "defrag", "defrag"),
]


class PowerToys(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "PowerToys", 520, 380, icon="powertoys")
        cw, ch = self.client_size()
        self.grid = self.add(W.IconGrid(
            2, 2, cw - 4, ch - 28, on_activate=self._activate))
        self.grid.set_items([{"label": label, "icon": icon, "data": action}
                             for label, icon, action in TOOLS])
        self.set_focus(self.grid)

    def draw_client(self, d, img):
        cw, ch = self.client_size()
        T.sunken(d, 2, ch - 24, cw - 3, ch - 3, fill=T.FACE)
        d.text((8, ch - 21), "Shell tools from the Kilix 95 workshop",
               font=T.FONT, fill=T.TEXT)

    def on_resize(self):
        cw, ch = self.client_size()
        self.grid.w, self.grid.h = cw - 4, ch - 28

    def _activate(self, item):
        action = item["data"]
        if action == "terminal":
            self._path_prompt("Command Prompt Here", self.desk.shell.open_terminal)
        elif action == "explore":
            self._path_prompt("Explore From Here",
                              lambda path: self.desk.shell.open_app("filemgr", path))
        elif action == "quickres":
            self.desk.shell.open_app("displayprops", "settings")
        elif action == "deskmenu":
            self.desk.shell.open_app("filemgr", self.desk.shell.dir)
        elif action == "sendto":
            self.desk.wm.add(SendToSettings(self.desk))
        elif action == "tweakui":
            self.desk.wm.add(TweakUI(self.desk))
        elif action == "clock":
            self.desk.shell.open_app("datetime")
        elif action == "defrag":
            self.desk.shell.open_app("defrag")

    def _path_prompt(self, title, callback):
        def chosen(path):
            path = os.path.abspath(os.path.expanduser(path or ""))
            if os.path.isdir(path):
                callback(path)
            else:
                wm.msgbox(self.desk, title, "That folder does not exist.",
                          icon="error")
        wm.inputbox(self.desk, title, "Folder:", os.path.expanduser("~"),
                    cb=chosen, icon="folder")


class TweakUI(wm.Window):
    def __init__(self, desk):
        super().__init__(desk, "TweakUI", 450, 370, icon="powertoys",
                         resizable=False)
        cw, ch = self.client_size()
        state = desk.shell.state
        self.add(W.GroupBox(12, 10, cw - 24, 180, "Desktop"))
        self.home = self.add(W.Checkbox(30, 40, "Show Home icon",
                                        checked=state.get("show_home", True)))
        self.settings = self.add(W.Checkbox(
            30, 70, "Show kilix Settings icon",
            checked=state.get("show_settings", True)))
        self.terminal = self.add(W.Checkbox(
            30, 100, "Show Terminal icons",
            checked=state.get("show_terminals", True)))
        self.quick = self.add(W.Checkbox(
            30, 130, "Show Quick Launch toolbar",
            checked=state.get("show_quick_launch", True)))
        self.auto = self.add(W.Checkbox(
            30, 160, "Auto Arrange desktop icons", checked=True))
        self.auto.enabled = False  # the current icon grid is intentionally arranged
        self.add(W.GroupBox(12, 204, cw - 24, 72, "Window movement"))
        self.drag = self.add(W.Checkbox(
            30, 234, "Show window contents while dragging",
            checked=state.get("full_window_drag", True)))

        def apply(close=False):
            state.update({"show_home": self.home.checked,
                          "show_settings": self.settings.checked,
                          "show_terminals": self.terminal.checked,
                          "show_quick_launch": self.quick.checked,
                          "full_window_drag": self.drag.checked})
            desk.shell._save_state()
            desk.shell.refresh()
            desk.taskbar.invalidate()
            if close:
                self.close()

        self.add(W.Button(cw - 244, ch - 33, 72, 23, "OK", default=True,
                          cb=lambda: apply(True)))
        self.add(W.Button(cw - 164, ch - 33, 72, 23, "Cancel", cb=self.close))
        self.add(W.Button(cw - 84, ch - 33, 72, 23, "Apply", cb=apply))


class SendToSettings(wm.Window):
    def __init__(self, desk):
        super().__init__(desk, "Send To", 500, 350, icon="sendto")
        cw, ch = self.client_size()
        self.list = self.add(W.ListBox(12, 36, cw - 24, ch - 100))
        self.add(W.Label(12, 12, "Configured destinations:"))
        self.add(W.Button(12, ch - 50, 92, 23, "Add…", cb=self._add))
        self.add(W.Button(112, ch - 50, 92, 23, "Remove", cb=self._remove))
        self.add(W.Button(cw - 84, ch - 50, 72, 23, "Close", cb=self.close))
        self.refresh()
    def refresh(self):
        self.list.set_items([
            ("folder", f"{item.get('name')} — {item.get('path')}", item)
            for item in nostalgia.config_list("send_to") if isinstance(item, dict)
        ] or [(None, "(Desktop and My Briefcase are always available)", None)])

    def _add(self):
        def named(name):
            if not name:
                return
            def pathed(path):
                path = os.path.abspath(os.path.expanduser(path or ""))
                if not os.path.isdir(path):
                    wm.msgbox(self.desk, "Send To", "That folder does not exist.",
                              icon="error")
                    return
                values = [item for item in nostalgia.config_list("send_to")
                          if isinstance(item, dict) and item.get("name") != name]
                values.append({"name": name, "path": path})
                nostalgia.set_config_list("send_to", values)
                self.refresh()
            wm.inputbox(self.desk, "Send To", "Destination folder:",
                        os.path.expanduser("~"), cb=pathed, icon="folder")
        wm.inputbox(self.desk, "Send To", "Destination name:", cb=named,
                    icon="sendto")

    def _remove(self):
        if not (0 <= self.list.sel < len(self.list.items)):
            return
        item = self.list.items[self.list.sel][2]
        if not item:
            return
        values = [value for value in nostalgia.config_list("send_to")
                  if value != item]
        nostalgia.set_config_list("send_to", values)
        self.refresh()
