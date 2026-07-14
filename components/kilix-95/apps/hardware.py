"""Read-only Device Manager and Add New Hardware wizard."""

import os
import platform

import nostalgia
import theme as T
import widgets as W
import wm


def inventory():
    values = [{"name": platform.processor() or platform.machine() or "CPU",
               "kind": "Processor", "detail": platform.platform()},
              {"name": "Kilix graphics framebuffer", "kind": "Display",
               "detail": "Kitty graphics protocol display adapter"}]
    for dev in nostalgia.block_devices():
        values.append({"name": dev["label"] or dev["model"] or dev["name"],
                       "kind": "Disk drives" if dev["type"] != "rom"
                       else "CD-ROM",
                       "detail": (f"/dev/{dev['name']}  "
                                  f"{nostalgia.human_size(dev['size'])}  "
                                  f"{dev['fstype'] or 'unformatted'}")})
    try:
        for name in sorted(os.listdir("/sys/class/net")):
            values.append({"name": name, "kind": "Network adapters",
                           "detail": f"Network interface {name}"})
    except OSError:
        pass
    return values


class DeviceManager(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Device Manager", 570, 420, icon="hardware")
        self.min_w, self.min_h = 390, 270
        cw, ch = self.client_size()
        self.list = self.add(W.ListBox(
            10, 38, cw - 20, ch - 90, on_activate=self._properties,
            on_select=self._selection))
        self.add(W.Label(12, 12, "View devices by type:"))
        self.status = self.add(W.Label(12, ch - 40, ""))
        self.add(W.Button(cw - 220, ch - 44, 98, 23, "Properties…",
                          cb=self._selected_properties))
        self.add(W.Button(cw - 114, ch - 44, 102, 23, "Scan Hardware",
                          cb=self.scan))
        self.scan()

    def scan(self):
        self.devices = inventory()
        rows = []
        for value in self.devices:
            icon = "drive" if value["kind"] in ("Disk drives", "CD-ROM") \
                else "network" if value["kind"] == "Network adapters" \
                else "hardware"
            rows.append((icon, f"{value['kind']} — {value['name']}", value))
        self.list.set_items(rows)
        self.desk.new_hardware = False
        self.desk.hardware_signature = nostalgia.block_device_signature()
        self.desk.taskbar.invalidate()
        self.status.set(f"{len(rows)} device(s) found. No drivers were changed.")

    def _selection(self, item):
        if item:
            self.status.set(item[2]["detail"])

    def _selected_properties(self):
        if 0 <= self.list.sel < len(self.list.items):
            self._properties(self.list.items[self.list.sel])

    def _properties(self, item):
        if not item:
            return
        value = item[2]
        wm.msgbox(self.desk, value["name"] + " Properties",
                  f"Device type: {value['kind']}\n"
                  f"Device status: This device is working properly.\n\n"
                  f"{value['detail']}", icon=item[0] or "hardware")

    def on_resize(self):
        cw, ch = self.client_size()
        self.list.w, self.list.h = cw - 20, ch - 90
        self.status.y = ch - 40


class HardwareWizard(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Add New Hardware Wizard", 500, 330,
                         icon="hardware", resizable=False, modal=True)
        cw, ch = self.client_size()
        self.add(W.Label(28, 28, "Kilix 95 will search for newly attached hardware.",
                         bold=True))
        self.add(W.Label(28, 58,
                         "Detection is read-only; no drivers or mounts are changed."))
        self.results = self.add(W.ListBox(28, 92, cw - 56, 128))
        self.status = self.add(W.Label(28, 232, "Click Next to scan."))
        self.next = self.add(W.Button(cw - 174, ch - 38, 82, 23, "Next >",
                                      default=True, cb=self._scan))
        self.add(W.Button(cw - 84, ch - 38, 72, 23, "Cancel", cb=self.close))

    def _scan(self):
        values = inventory()
        self.results.set_items([
            ("hardware", f"{value['kind']}: {value['name']}", value)
            for value in values])
        self.status.set(f"Windows found {len(values)} device(s).")
        self.next.text = "Finish"
        self.next.cb = self._finish
        self.desk.new_hardware = False
        self.desk.hardware_signature = nostalgia.block_device_signature()
        self.desk.taskbar.invalidate()

    def _finish(self):
        self.close()
        self.desk.shell.open_app("systemprops")
