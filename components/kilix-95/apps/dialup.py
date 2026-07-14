"""Dial-Up Networking theater with a real browser hand-off."""

import math
import os
import random
import struct
import time
import wave

import nostalgia
import sounds
import storage
import theme as T
import widgets as W
import wm


DEFAULT_CONNECTION = {"name": "The Internet", "phone": "555-KILIX",
                      "username": "guest"}


def connections():
    values = [value for value in nostalgia.config_list("dial_connections")
              if isinstance(value, dict) and value.get("name")]
    return values or [dict(DEFAULT_CONNECTION)]


def save_connection(value):
    values = [item for item in nostalgia.config_list("dial_connections")
              if isinstance(item, dict) and item.get("name") != value["name"]]
    values.append({key: str(value.get(key) or "")
                   for key in ("name", "phone", "username")})
    nostalgia.set_config_list("dial_connections", values)


def _dial_sound():
    path = storage.data_dir("sounds", "dialup-negotiation.wav")
    if os.path.isfile(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rate, duration = 22050, 2.1
    rng = random.Random(95)
    samples = []
    for index in range(int(rate * duration)):
        t = index / rate
        if t < .45:
            value = .34 * math.sin(2 * math.pi * (350 + (t > .18) * 90) * t)
        elif t < 1.25:
            value = (.20 * math.sin(2 * math.pi * 1200 * t)
                     + .16 * math.sin(2 * math.pi * (1700 + 200 * math.sin(t * 37)) * t)
                     + rng.uniform(-.10, .10))
        else:
            value = (.13 * math.sin(2 * math.pi * 2100 * t)
                     + rng.uniform(-.18, .18)) * max(0, (duration - t) / .85)
        samples.append(max(-32767, min(32767, int(value * 32767))))
    temp = path + ".tmp"
    with wave.open(temp, "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
        output.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    os.replace(temp, path)
    return path


def disconnect(desk):
    state = getattr(desk, "dialup_state", None)
    if not state or not state.get("connected"):
        return False
    state.update({"connected": False, "status": "Disconnected",
                  "disconnected_at": time.time()})
    desk.taskbar.invalidate()
    desk.dirty = True
    return True


class DialUpNetworking(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Dial-Up Networking", 510, 360, icon="dialup")
        cw, ch = self.client_size()
        self.menubar = self.add(W.MenuBar(cw, [
            ("Connections", self._connections_menu), ("Help", self._help_menu)]))
        self.grid = self.add(W.IconGrid(
            2, T.MENU_H + 2, cw - 4, ch - T.MENU_H - 23,
            on_activate=self._activate))
        self.set_focus(self.grid)
        self.refresh()

    def refresh(self):
        items = [{"label": "Make New Connection", "icon": "newconnection",
                  "data": None}]
        for value in connections():
            items.append({"label": value["name"], "icon": "dialup",
                          "data": value})
        self.grid.set_items(items)
        self.invalidate()

    def _activate(self, item):
        if item["data"] is None:
            self._new_connection()
        else:
            self.desk.wm.add(DialConnection(self.desk, item["data"]))

    def _new_connection(self):
        def named(name):
            if not name:
                return
            def numbered(phone):
                if not phone:
                    return
                value = {"name": name, "phone": phone, "username": "guest"}
                save_connection(value)
                self.refresh()
                self.desk.wm.add(DialConnection(self.desk, value))
            wm.inputbox(self.desk, "Make New Connection", "Telephone number:",
                        "555-", cb=numbered, icon="dialup")
        wm.inputbox(self.desk, "Make New Connection", "Connection name:",
                    "My Connection", cb=named, icon="dialup")

    def _connections_menu(self):
        selected = self.grid.selected_items()
        return [W.MenuItem("Connect", enabled=bool(selected),
                           action=lambda: selected and self._activate(selected[0])),
                W.MenuItem("Make New Connection…", icon="newconnection",
                           action=self._new_connection),
                W.sep(), W.MenuItem("Close", action=self.close)]

    def _help_menu(self):
        return [W.MenuItem("About Dial-Up Networking…", icon="dialup",
                           action=lambda: wm.msgbox(
                               self.desk, "Dial-Up Networking",
                               "Recreates the connection ritual, then hands off "
                               "to the real Kilix browser. It does not alter host networking.",
                               icon="dialup"))]

    def on_resize(self):
        cw, ch = self.client_size()
        self.menubar.w = cw
        self.grid.w, self.grid.h = cw - 4, ch - T.MENU_H - 23

    def draw_client(self, d, img):
        cw, ch = self.client_size()
        T.sunken(d, 2, ch - 21, cw - 3, ch - 3, fill=T.FACE)
        d.text((8, ch - 18), f"{len(self.grid.items)} object(s)",
               font=T.FONT, fill=T.TEXT)


class DialConnection(wm.Window):
    STAGES = [(0.0, "Initializing modem…"), (.45, "Dialing…"),
              (1.05, "Verifying user name and password…"),
              (1.65, "Registering your computer on the network…")]

    def __init__(self, desk, value):
        super().__init__(desk, "Connect To " + value["name"], 430, 330,
                         icon="dialup", resizable=False)
        self.value = dict(value)
        cw, ch = self.client_size()
        self.add(W.Label(24, 24, "Telephone number:"))
        self.phone = self.add(W.TextField(166, 18, 220, value.get("phone", "")))
        self.add(W.Label(24, 62, "User name:"))
        self.user = self.add(W.TextField(166, 56, 220, value.get("username", "")))
        self.add(W.Label(24, 100, "Password:"))
        self.password = self.add(W.TextField(166, 94, 220, "", mask=True))
        self.save = self.add(W.Checkbox(166, 128, "Save this user name"))
        self.status = self.add(W.Label(24, 174, "Ready to dial."))
        self.connected_info = self.add(W.Label(24, 198, "", color=T.SHADOW))
        self.connect = self.add(W.Button(cw - 174, ch - 42, 82, 23, "Connect",
                                         default=True, cb=self._connect))
        self.cancel = self.add(W.Button(cw - 84, ch - 42, 72, 23, "Cancel",
                                        cb=self.close))
        self.browser = self.add(W.Button(24, ch - 42, 108, 23, "Open Browser",
                                         icon="browser", cb=self._browser))
        self.browser.enabled = bool(getattr(desk, "dialup_state", {}).get("connected"))
        self.started = None
        self.stage = -1
        self.set_focus(self.phone)

    def _connect(self):
        if getattr(self.desk, "dialup_state", {}).get("connected"):
            disconnect(self.desk)
            self.status.set("Disconnected.")
            self.connect.text = "Connect"
            self.browser.enabled = False
            return
        self.value.update({"phone": self.phone.text,
                           "username": self.user.text})
        save_connection(self.value)
        self.started, self.stage = time.time(), -1
        self.connect.enabled = False
        self.cancel.text = "Cancel"
        self.desk.tick_hooks.append(self._tick)
        self.desk.busy = True
        try:
            sounds.preview(_dial_sound(), volume=50)
        except Exception:
            pass
        self._tick(self.started)

    def _tick(self, now):
        if self.started is None:
            return
        elapsed = now - self.started
        next_stage = sum(1 for at, _ in self.STAGES if elapsed >= at) - 1
        if next_stage != self.stage and 0 <= next_stage < len(self.STAGES):
            self.stage = next_stage
            self.status.set(self.STAGES[next_stage][1])
        if elapsed >= 2.15:
            self._finish()

    def _finish(self):
        if self._tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self._tick)
        now = time.time()
        self.desk.dialup_state = {
            "connected": True, "name": self.value["name"],
            "phone": self.phone.text, "speed": 56000, "connected_at": now,
            "status": "Connected",
        }
        self.started = None
        self.desk.busy = False
        self.status.set("Connected at 56,000 bps.")
        self.connected_info.set("The real browser remains full-speed; only the ritual is simulated.")
        self.connect.text = "Disconnect"
        self.connect.enabled = True
        self.cancel.text = "Close"
        self.browser.enabled = True
        self.desk.taskbar.invalidate()
        self.invalidate()

    def _browser(self):
        if getattr(self.desk, "dialup_state", {}).get("connected"):
            self.desk.shell.open_browser("firefox")

    def close(self):
        if self._tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self._tick)
        self.desk.busy = False
        super().close()
