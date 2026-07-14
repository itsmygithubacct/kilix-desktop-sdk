"""Printers folder: CUPS queue discovery plus safe virtual printers."""

import os
import subprocess

import nostalgia
import storage
import theme as T
import widgets as W
import wm


class Printers(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Printers", 520, 380, icon="printer")
        self.min_w, self.min_h = 360, 250
        cw, ch = self.client_size()
        self.menubar = self.add(W.MenuBar(cw, [
            ("File", self._file_menu), ("Help", self._help_menu)]))
        self.grid = self.add(W.IconGrid(
            2, T.MENU_H + 2, cw - 4, ch - T.MENU_H - 23,
            on_activate=self._activate))
        self.set_focus(self.grid)
        self.refresh()

    def refresh(self):
        items = [{"label": "Add Printer", "icon": "addprinter", "data": None}]
        items += [{"label": item["name"], "icon": "printer", "data": item}
                  for item in nostalgia.printers()]
        self.grid.set_items(items)
        self.invalidate()

    def _activate(self, item):
        if item["data"] is None:
            self._add()
        else:
            self.desk.wm.add(PrintQueue(self.desk, item["data"]))

    def _add(self):
        def named(name):
            if not name:
                return
            default = storage.data_dir("printed-documents")
            def pathed(path):
                try:
                    nostalgia.add_virtual_printer(name, path)
                    self.refresh()
                    wm.msgbox(self.desk, "Add Printer Wizard",
                              f"'{name}' is ready. Jobs are written to:\n"
                              f"{os.path.abspath(os.path.expanduser(path))}",
                              icon="printer")
                except (OSError, ValueError) as error:
                    wm.msgbox(self.desk, "Add Printer Wizard", str(error),
                              icon="error")
            wm.inputbox(self.desk, "Add Printer Wizard", "Output folder:",
                        default, cb=pathed, icon="printer")
        wm.inputbox(self.desk, "Add Printer Wizard", "Printer name:",
                    "My Printer", cb=named, icon="printer")

    def _file_menu(self):
        selected = self.grid.selected_items()
        return [W.MenuItem("Open", enabled=bool(selected),
                           action=lambda: selected and self._activate(selected[0])),
                W.MenuItem("Add Printer…", icon="addprinter", action=self._add),
                W.sep(), W.MenuItem("Close", action=self.close)]

    def _help_menu(self):
        return [W.MenuItem("About Printers…", icon="printer",
                           action=lambda: wm.msgbox(
                               self.desk, "Printers",
                               "CUPS queues are discovered read-only. Add Printer "
                               "creates a safe print-to-folder destination.",
                               icon="printer"))]

    def on_resize(self):
        cw, ch = self.client_size()
        self.menubar.w = cw
        self.grid.w, self.grid.h = cw - 4, ch - T.MENU_H - 23

    def draw_client(self, d, img):
        cw, ch = self.client_size()
        T.sunken(d, 2, ch - 21, cw - 3, ch - 3, fill=T.FACE)
        d.text((8, ch - 18), f"{len(self.grid.items) - 1} printer(s)",
               font=T.FONT, fill=T.TEXT)


class PrintQueue(wm.Window):
    def __init__(self, desk, printer):
        super().__init__(desk, printer["name"], 560, 330, icon="printer")
        self.printer = printer
        cw, ch = self.client_size()
        self.add(W.Label(12, 12, f"Printer: {printer['name']}", bold=True))
        self.add(W.Label(12, 32,
                         f"Status: {printer.get('status', 'Ready')}"))
        self.jobs = self.add(W.ListBox(10, 58, cw - 20, ch - 108))
        self.add(W.Button(cw - 94, ch - 38, 82, 23, "Refresh", cb=self.refresh))
        self.refresh()

    def refresh(self):
        rows = []
        if self.printer.get("kind") == "cups":
            try:
                result = subprocess.run(
                    ["lpstat", "-o", self.printer["name"]],
                    capture_output=True, text=True, timeout=3, check=False)
                rows = [("doc", line, line) for line in result.stdout.splitlines()]
            except (OSError, subprocess.TimeoutExpired):
                rows = []
        else:
            path = self.printer.get("path", "")
            try:
                rows = [("doc", name, os.path.join(path, name))
                        for name in sorted(os.listdir(path), key=str.lower)]
            except OSError:
                rows = []
        self.jobs.set_items(rows or [(None, "(No documents)", None)])
