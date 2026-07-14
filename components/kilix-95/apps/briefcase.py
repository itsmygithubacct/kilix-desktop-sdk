"""My Briefcase UI for non-destructive two-folder synchronization."""

import os

import briefcase as sync_mod
import storage
import theme as T
import widgets as W
import wm


ACTION_LABELS = {
    "current": "Up to date",
    "left-to-right": "Copy left → right",
    "right-to-left": "Copy right → left",
    "conflict": "Conflict — left untouched",
}


class BriefcaseWindow(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "My Briefcase", 650, 460, icon="briefcase")
        self.min_w, self.min_h = 480, 330
        cw, ch = self.client_size()
        state = desk.shell.state
        self.add(W.Label(12, 15, "Folder at home:"))
        self.left = self.add(W.TextField(
            118, 9, cw - 240, state.get("briefcase_left", desk.shell.dir)))
        self.add(W.Button(cw - 112, 8, 98, 23, "Open", icon="folder_open",
                          cb=lambda: self._open(self.left.text)))
        self.add(W.Label(12, 49, "Portable copy:"))
        default_right = storage.data_dir("briefcase")
        self.right = self.add(W.TextField(
            118, 43, cw - 240, state.get("briefcase_right", default_right)))
        self.add(W.Button(cw - 112, 42, 98, 23, "Open", icon="folder_open",
                          cb=lambda: self._open(self.right.text)))
        self.results = self.add(W.ListBox(
            10, 82, cw - 20, ch - 142, on_activate=self._detail))
        self.status = self.add(W.Label(12, ch - 48,
                                       "Preview compares both folders without changing them."))
        self.add(W.Button(cw - 206, ch - 44, 92, 23, "Preview",
                          cb=self.preview))
        self.add(W.Button(cw - 106, ch - 44, 92, 23, "Synchronize",
                          default=True, cb=self.synchronize))
        self.actions = []

    def on_resize(self):
        cw, ch = self.client_size()
        self.left.w = self.right.w = cw - 240
        self.results.w, self.results.h = cw - 20, ch - 142
        self.status.y = ch - 48

    def _open(self, path):
        path = os.path.abspath(os.path.expanduser(path or ""))
        if not os.path.isdir(path):
            wm.msgbox(self.desk, "My Briefcase",
                      f"The folder does not exist:\n{path}", icon="error")
            return
        self.desk.shell.open_app("filemgr", path)

    def _paths(self):
        left, right = sync_mod.validate_roots(self.left.text, self.right.text)
        self.left.set(left); self.right.set(right)
        self.desk.shell.state["briefcase_left"] = left
        self.desk.shell.state["briefcase_right"] = right
        self.desk.shell._save_state()
        return left, right

    def preview(self):
        try:
            left, right = self._paths()
            _left, _right, self.actions = sync_mod.plan(left, right)
        except (OSError, ValueError, RuntimeError) as error:
            wm.msgbox(self.desk, "My Briefcase", str(error), icon="error")
            return
        rows = []
        for item in self.actions:
            action = item["action"]
            icon = "warn" if action == "conflict" else \
                "info" if action == "current" else "doc"
            rows.append((icon, f"{item['path']} — {ACTION_LABELS[action]}", item))
        self.results.set_items(rows or [(None, "(Both folders are empty)", None)])
        changes = sum(item["action"] not in ("current", "conflict")
                      for item in self.actions)
        conflicts = sum(item["action"] == "conflict" for item in self.actions)
        self.status.set(f"{changes} update(s), {conflicts} conflict(s), "
                        f"{len(self.actions)} file(s) compared.")

    def synchronize(self):
        self.desk.busy = True
        try:
            left, right = self._paths()
            result = sync_mod.synchronize(left, right)
        except (OSError, ValueError, RuntimeError) as error:
            wm.msgbox(self.desk, "My Briefcase", str(error), icon="error")
            return
        finally:
            self.desk.busy = False
        self.preview()
        message = f"Copied {len(result['copied'])} file(s)."
        if result["conflicts"]:
            message += (f"\n\n{len(result['conflicts'])} conflict(s) were left "
                        "unchanged for you to resolve.")
        wm.msgbox(self.desk, "Briefcase Updated", message,
                  icon="warn" if result["conflicts"] else "info")

    def _detail(self, item):
        if not item or not item[2]:
            return
        value = item[2]
        wm.msgbox(self.desk, "Briefcase File",
                  f"Name: {value['path']}\n"
                  f"Action: {ACTION_LABELS[value['action']]}\n\n"
                  "Briefcase never propagates deletions and never overwrites "
                  "a two-sided conflict.",
                  icon=item[0] or "briefcase")
