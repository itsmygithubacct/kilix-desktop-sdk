"""kilix desktop — Backup and Restore: settings and desktop documents.

A front for the host's ``kilix backup``: Back Up Now writes a private
archive; Restore checks an archive, says what it will change, restores it
(keeping a safety copy of the replaced files) and restarts the desktop so the
restored settings are loaded instead of overwritten.
"""
import os

import filedialog
import theme as T
import widgets as W
import wm

_FILTERS = [("Kilix backups", "*.tar.gz"), ("All Files", "*.*")]
_SESSION_FILE = "kilix/kilix.env"     # read once per Kilix session, not per desktop
_SHOWN_CHANGES = 6
_SHOWN_FLAGGED = 8      # keeps the box on screen; the rest are counted, not hidden


def _backend():
    try:
        from kilix_sdk import backup
    except ImportError:
        return None
    return backup


class BackupWin(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Backup and Restore", 420, 230, icon="floppy",
                         resizable=False)
        self.backend = _backend()
        lines = (
            "Saves your settings, the desktop's layout and choices,",
            "and the documents on your desktop to one private file.",
            "Restoring replaces only the files the backup holds and",
            "keeps a copy of everything it replaces.",
        )
        for i, text in enumerate(lines):
            self.add(W.Label(14, 14 + i * 16, text))
        self.b_backup = self.add(W.Button(14, 96, 130, 24, "Back Up Now",
                                          cb=self.back_up))
        self.b_restore = self.add(W.Button(154, 96, 130, 24, "Restore…",
                                           cb=self.choose_restore))
        self.status = self.add(W.Label(14, 136, "", font=T.SMALL, color=T.SHADOW))
        if self.backend is None:
            self.b_backup.enabled = self.b_restore.enabled = False
            self.status.text = "This Kilix host does not provide backups yet."

    def back_up(self):
        skipped = []
        try:
            path = self.backend.create(skipped=skipped)
        except (OSError, self.backend.BackupError) as error:
            wm.msgbox(self.desk, "Backup", f"The backup failed:\n{error}", icon="error")
            return
        self.status.text = "Saved " + os.path.basename(path)
        self.invalidate()
        text = f"Backup saved to\n{path}"
        if skipped:
            text += (f"\n\nLeft out {len(skipped)} file(s) whose names a backup cannot "
                     "hold, such as " + os.path.basename(skipped[0]))
        wm.msgbox(self.desk, "Backup", text, icon="warn" if skipped else "info")

    def choose_restore(self):
        os.makedirs(self.backend.default_directory(), mode=0o700, exist_ok=True)
        filedialog.open_file(self.desk, "Restore a Backup",
                             lambda p: p and self.confirm_restore(p),
                             start=self.backend.default_directory(),
                             filters=_FILTERS)

    def confirm_restore(self, archive):
        try:
            rows = self.backend.plan(archive)
        except (OSError, self.backend.BackupError) as error:
            wm.msgbox(self.desk, "Restore", f"This backup cannot be restored:\n{error}",
                      icon="error")
            return
        new = sum(1 for _n, _d, action in rows if action == "create")
        changed = sum(1 for _n, _d, action in rows if action == "replace")
        if not new and not changed:
            wm.msgbox(self.desk, "Restore", "Everything in this backup is already current.",
                      icon="info")
            return

        def answer(ans):
            if ans == "Restore":
                self.restore(archive)
        text = (f"Restore {new} new and {changed} changed file(s)?\n"
                "Your current files are backed up first, and the desktop "
                "restarts to load the restored settings.")
        text += self._describe_changes(archive)
        if any(name == _SESSION_FILE and action != "same" for name, _d, action in rows):
            text += ("\n\nkilix.env changes take effect only after you log out "
                     "and back in.")
        wm.msgbox(self.desk, "Restore", text,
                  icon="warn", buttons=("Restore", "Cancel"), cb=answer, default=1)

    def _describe_changes(self, archive):
        """The settings this restore changes, with launch-deciding keys flagged:
        a backup file may come from somewhere else."""
        if not hasattr(self.backend, "changes"):
            return ""
        try:
            rows = self.backend.changes(archive)
        except (OSError, self.backend.BackupError):
            return ""
        if not rows:
            return ""
        launch_key = getattr(self.backend, "launch_key", lambda key: True)
        flagged = [r for r in rows if r[0] == _SESSION_FILE and launch_key(r[1])]
        other = [r for r in rows if r not in flagged]
        # Changes that can alter what runs come first, so padding a backup with
        # ordinary settings cannot push one out of view. Past a screenful they
        # are counted in their own line rather than folded into the others.
        shown_flagged = flagged[:_SHOWN_FLAGGED]
        shown = shown_flagged + other[:max(0, _SHOWN_CHANGES - len(shown_flagged))]
        lines = []
        for name, key, _old, new in shown:
            mark = " (can change what runs!)" if (name, key, _old, new) in flagged else ""
            lines.append(f"{os.path.basename(name)}: {key} = {new or '(removed)'}{mark}")
        hidden_flagged = len(flagged) - len(shown_flagged)
        if hidden_flagged:
            lines.append(f"... and {hidden_flagged} more that can change what runs: "
                         "check them with 'kilix backup list' before restoring")
        hidden = len(rows) - len(shown) - hidden_flagged
        if hidden:
            lines.append(f"... and {hidden} more setting(s)")
        return "\n\nSettings it changes:\n" + "\n".join(lines)

    def restore(self, archive):
        try:
            result = self.backend.restore(archive)
        except (OSError, self.backend.BackupError) as error:
            wm.msgbox(self.desk, "Restore", f"The restore failed:\n{error}", icon="error")
            return
        message = f"Restored {result['written']} file(s)."
        if result.get("safety"):
            message += f"\nPrevious files: {os.path.basename(result['safety'])}"
        else:
            message += "\nNo existing file was replaced."
        if _SESSION_FILE in result.get("names", ()):
            message += ("\nkilix.env was restored too: log out and back in for it "
                        "to take effect.")
        self.desk.restart_after_restore(message)
