"""Network Neighborhood backed by configured SSH hosts and local shares."""

import os
import shutil

import nostalgia
import theme as T
import widgets as W
import wm


class NetworkNeighborhood(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Network Neighborhood", 530, 390, icon="network")
        self.min_w, self.min_h = 360, 250
        cw, ch = self.client_size()
        self.menubar = self.add(W.MenuBar(cw, [
            ("File", self._file_menu), ("Tools", self._tools_menu),
            ("Help", self._help_menu)]))
        self.grid = self.add(W.IconGrid(
            2, T.MENU_H + 2, cw - 4, ch - T.MENU_H - 23,
            on_activate=self._activate, on_context=self._context))
        self.set_focus(self.grid)
        self.refresh()

    def refresh(self):
        items = [{"label": "Entire Network", "icon": "network",
                  "data": {"kind": "entire"}}]
        for host in nostalgia.ssh_hosts():
            items.append({"label": host["name"], "icon": "computer",
                          "data": host})
        self.grid.set_items(items)
        self.invalidate()

    def on_resize(self):
        cw, ch = self.client_size()
        self.menubar.w = cw
        self.grid.w, self.grid.h = cw - 4, ch - T.MENU_H - 23

    def draw_client(self, d, img):
        cw, ch = self.client_size()
        T.sunken(d, 2, ch - 21, cw - 3, ch - 3, fill=T.FACE)
        hosts = max(0, len(self.grid.items) - 1)
        d.text((8, ch - 18), f"Workgroup: KILIX   {hosts} computer(s)",
               font=T.FONT, fill=T.TEXT)

    def _activate(self, item):
        value = item["data"]
        kind = value.get("kind")
        if kind == "entire":
            wm.msgbox(self.desk, "Entire Network",
                      "Kilix 95 lists concrete SSH aliases and explicitly "
                      "configured local shares. Wildcard SSH entries are hidden.",
                      icon="network")
        elif kind == "local" and os.path.isdir(value.get("path", "")):
            self.desk.shell.open_app("filemgr", value["path"])
        else:
            target = value.get("target") or value.get("name")
            if not shutil.which("ssh"):
                wm.msgbox(self.desk, "Network Neighborhood",
                          "The ssh command is not installed.", icon="error")
                return
            self.desk.shell._tab(["ssh", target], f"Network: {value['name']}")

    def _selected(self):
        values = self.grid.selected_items()
        return values[0] if values else None

    def _file_menu(self):
        item = self._selected()
        return [W.MenuItem("Open", enabled=item is not None,
                           action=lambda: item and self._activate(item)),
                W.MenuItem("Properties…", enabled=item is not None,
                           action=lambda: item and self._properties(item)),
                W.sep(), W.MenuItem("Close", action=self.close)]

    def _tools_menu(self):
        return [W.MenuItem("Find Computer…", icon="find",
                           action=self._find),
                W.MenuItem("Add Computer…", icon="computer",
                           action=self._add_ssh),
                W.MenuItem("Add Shared Folder…", icon="folder_open",
                           action=self._add_share),
                W.sep(), W.MenuItem("Refresh", action=self.refresh)]

    def _help_menu(self):
        return [W.MenuItem("About Network Neighborhood…", icon="network",
                           action=lambda: wm.msgbox(
                               self.desk, "Network Neighborhood",
                               "Double-click an SSH computer to connect in a "
                               "Kilix tab, or a shared folder to browse it.",
                               icon="network"))]

    def _context(self, item, event):
        gx, gy = self.client_origin()
        items = [W.MenuItem("Open", action=lambda: self._activate(item)),
                 W.MenuItem("Properties…", action=lambda: self._properties(item))]
        self.desk.menus.open(items, gx + event.x, gy + event.y)

    def _properties(self, item):
        value = item["data"]
        wm.msgbox(self.desk, item["label"] + " Properties",
                  f"Type: {value.get('kind', 'ssh').upper()} resource\n"
                  f"Target: {value.get('target') or value.get('path') or '-'}\n"
                  "Status: Available on demand",
                  icon=item.get("icon", "computer"))

    def _find(self):
        def search(text):
            if text is None:
                return
            match = next((item for item in self.grid.items
                          if text.lower() in item["label"].lower()), None)
            if match:
                self.grid.sel = {self.grid.items.index(match)}
                self.grid.invalidate()
            else:
                wm.msgbox(self.desk, "Find Computer",
                          f"No configured computer matches '{text}'.",
                          icon="info")
        wm.inputbox(self.desk, "Find Computer", "Computer name:", cb=search,
                    icon="find")

    def _add_ssh(self):
        def named(name):
            if not name:
                return
            def targeted(target):
                if target:
                    try:
                        nostalgia.add_network_host(name, target, "ssh")
                        self.refresh()
                    except ValueError as error:
                        wm.msgbox(self.desk, "Add Computer", str(error), icon="error")
            wm.inputbox(self.desk, "Add Computer", "SSH host or address:",
                        name, cb=targeted, icon="computer")
        wm.inputbox(self.desk, "Add Computer", "Display name:", cb=named,
                    icon="computer")

    def _add_share(self):
        def named(name):
            if not name:
                return
            def pathed(path):
                path = os.path.abspath(os.path.expanduser(path or ""))
                if not os.path.isdir(path):
                    wm.msgbox(self.desk, "Add Shared Folder",
                              "That folder does not exist.", icon="error")
                    return
                nostalgia.add_network_host(name, kind="local", path=path)
                self.refresh()
            wm.inputbox(self.desk, "Add Shared Folder", "Local folder:",
                        os.path.expanduser("~"), cb=pathed, icon="folder")
        wm.inputbox(self.desk, "Add Shared Folder", "Share name:", cb=named,
                    icon="folder")
