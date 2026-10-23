"""Backup and Restore applet: back up, restore, and restart without saving over it."""
import os
from unittest import mock

import harness as H
import wm as wm_mod_for_test
import widgets as W
from apps import controlpanel
from apps.backup import BackupWin


def box(desk, title):
    for win in reversed(desk.wm.windows):
        if win.title == title:
            return win
    return None


def press(win, label):
    for wdg in win.widgets:
        if isinstance(wdg, W.Button) and wdg.text == label:
            wdg.cb()
            return
    raise AssertionError(f"no {label!r} in {win.title!r}")


assert ("Backup", "floppy", "backup", None) in controlpanel.CONTROL_ITEMS

d = H.make_desk()
import apps                                                   # noqa: E402
apps.open(d, "backup")
win = H.find_window(d, "BackupWin")
assert win is not None and win.backend is not None, "the host provides kilix_sdk.backup"

# Back Up Now writes a private archive holding the desktop documents.
desktop = d.shell.dir
with open(os.path.join(desktop, "letter.txt"), "w") as fh:
    fh.write("original\n")
win.back_up()
press(box(d, "Backup"), "OK")
archives = sorted(os.listdir(win.backend.default_directory()))
assert len(archives) == 1 and archives[0].endswith(".tar.gz"), archives
archive = os.path.join(win.backend.default_directory(), archives[0])

# Restore says what it will change, restores, and restarts under the supervisor
# without waiting for anyone to click OK; the restarted desktop shows the notice.
with open(os.path.join(desktop, "letter.txt"), "w") as fh:
    fh.write("edited after the backup\n")
win.confirm_restore(archive)
d.running = True
with mock.patch.dict(os.environ, {"KILIX_DESKTOP_SUPERVISED": "1"}):
    press(box(d, "Restore"), "Restore")
with open(os.path.join(desktop, "letter.txt")) as fh:
    assert fh.read() == "original\n", "the document came back"
assert d.exit_status == d.RESTART_STATUS == 75 and not d.running
assert d.shell.state_frozen, "the replaced state is never saved over the restore"
saves = []
d.shell.state_store.save_dict = lambda value: saves.append(value)
d.shell._save_state()
assert saves == [], "a frozen shell writes nothing"
import storage                                                # noqa: E402
notice = storage.state_dir(d.RESTORE_NOTICE)
assert os.path.exists(notice)
after = H.make_desk()
shown_notice = []
real_box = wm_mod_for_test.msgbox
with mock.patch.object(wm_mod_for_test, "msgbox",
                       lambda desk, title, text, **kw: shown_notice.append(text) or real_box(desk, title, text, **kw)):
    after._start_document_recovery()              # the restarted desktop's startup
assert box(after, "Restore") is not None and not os.path.exists(notice)
assert any("are loaded" in text for text in shown_notice), shown_notice

# Without a supervisor it relaunches itself the old way instead of exiting 75 ...
os.environ.pop("KILIX_DESKTOP_SUPERVISED", None)
d2 = H.make_desk()
calls = []
d2.shell._restart_desktop = lambda: calls.append("relaunch") or True
d2.restart_after_restore("Restored 1 file(s).")
assert calls == ["relaunch"] and getattr(d2, "exit_status", 0) == 0
assert d2.shell.state_frozen
# ... and if that relaunch fails it keeps saving settings and says so.
d3 = H.make_desk()
d3.shell._restart_desktop = lambda: False
d3.restart_after_restore("Restored 1 file(s).")
assert not d3.shell.state_frozen, "a desktop that cannot restart must keep saving"
assert box(d3, "Restore") is not None and not os.path.exists(storage.state_dir(d3.RESTORE_NOTICE))
failed_text = []
d3b = H.make_desk()
d3b.shell._restart_desktop = lambda: False
apps.open(d3b, "backup")
w3b = H.find_window(d3b, "BackupWin")
with open(os.path.join(desktop, "letter.txt"), "w") as fh:
    fh.write("edited again\n")
with mock.patch.object(wm_mod_for_test, "msgbox",
                       lambda desk, title, text, **kw: failed_text.append(text)):
    w3b.restore(archive)                          # the applet's own message
assert "Restored 1 file(s)" in failed_text[-1], failed_text
assert "could not restart itself" in failed_text[-1], failed_text
assert "are loaded" not in failed_text[-1], "a desktop that did not restart has not loaded them"

# A requested restart is not reported as a crash.
import doc_recovery                                           # noqa: E402
seen = []
with mock.patch.object(doc_recovery, "offer", lambda desk, reason=None: seen.append(reason)), \
        mock.patch.dict(os.environ, {"KILIX_DESKTOP_RESTARTED": "1",
                                     "KILIX_DESKTOP_LAST_STATUS": "75"}):
    H.make_desk()._start_document_recovery()
with mock.patch.object(doc_recovery, "offer", lambda desk, reason=None: seen.append(reason)), \
        mock.patch.dict(os.environ, {"KILIX_DESKTOP_RESTARTED": "1",
                                     "KILIX_DESKTOP_LAST_STATUS": "1"}):
    H.make_desk()._start_document_recovery()
assert seen[0] is None and "stopped unexpectedly" in seen[1], seen

# A corrupt archive is refused with a message, and nothing restarts.
bad = os.path.join(win.backend.default_directory(), "bad.tar.gz")
with open(bad, "wb") as fh:
    fh.write(b"not a backup")
d4 = H.make_desk()
apps.open(d4, "backup")
w4 = H.find_window(d4, "BackupWin")
w4.confirm_restore(bad)
assert box(d4, "Restore") is not None and not getattr(d4.shell, "state_frozen", False)

# A restore that only re-creates deleted files replaces nothing, keeps no safety
# copy, and still restarts with an honest message (it used to crash on None).
import wm                                                     # noqa: E402
os.environ["KILIX_DESKTOP_SUPERVISED"] = "1"
d5 = H.make_desk()
apps.open(d5, "backup")
w5 = H.find_window(d5, "BackupWin")
gone = os.path.join(d5.shell.dir, "gone.txt")
with open(gone, "w") as fh:
    fh.write("deleted later\n")
only_new = w5.backend.create()
os.unlink(gone)
said = []
d5.restart_after_restore = said.append
w5.restore(only_new)
assert said and "No existing file was replaced" in said[0], said
assert "log out" not in said[0], "nothing session-wide was restored"
with open(gone) as fh:
    assert fh.read() == "deleted later\n"

# The confirmation lists the settings a restore changes and flags the ones that
# decide what the desktop runs; kilix.env needs a new session, and says so.
kilix_env = os.path.join(os.environ["KILIX_CONFIG_HOME"], "kilix.env")
os.makedirs(os.path.dirname(kilix_env), exist_ok=True)
with open(kilix_env, "w") as fh:
    fh.write("KILIX95_DIR=/opt/elsewhere\n")
from_elsewhere = w5.backend.create()
assert "kilix/kilix.env" in w5.backend.read(from_elsewhere)[1]
with open(kilix_env, "w") as fh:
    fh.write("KILIX95_DIR=/opt/mine\n")
texts = []
real_msgbox = wm.msgbox
with mock.patch.object(wm, "msgbox", lambda desk, title, text, **kw: texts.append(text)):
    w5.confirm_restore(from_elsewhere)
assert "Settings it changes" in texts[-1], texts
assert "KILIX95_DIR = /opt/elsewhere (can change what runs!)" in texts[-1], texts[-1]
assert "log out and back in" in texts[-1], texts[-1]
said.clear()
w5.restore(from_elsewhere)
assert "Previous files:" in said[0] and "kilix.env was restored too" in said[0], said

# Padding a backup with ordinary settings cannot push a flagged one out of view.
settings_file = os.environ["GPU_TERMINAL_SETTINGS_FILE"]
with open(settings_file, "w") as fh:
    fh.write("".join(f"key{i}=theirs\n" for i in range(9)))
with open(kilix_env, "w") as fh:
    fh.write("KILIX_OBJECT_DETECTOR=sh /tmp/x.txt\nKILIX_CHROME_CLOCK=1\n")
padded = w5.backend.create()
with open(settings_file, "w") as fh:
    fh.write("".join(f"key{i}=mine\n" for i in range(9)))
with open(kilix_env, "w") as fh:
    fh.write("KILIX_CHROME_CLOCK=0\n")
texts.clear()
with mock.patch.object(wm, "msgbox", lambda desk, title, text, **kw: texts.append(text)):
    w5.confirm_restore(padded)
assert "KILIX_OBJECT_DETECTOR = sh /tmp/x.txt (can change what runs!)" in texts[-1], texts[-1]
assert texts[-1].index("KILIX_OBJECT_DETECTOR") < texts[-1].index("key0"), texts[-1]
assert "... and 5 more setting(s)" in texts[-1], texts[-1]

# A display setting is shown unflagged when there is room for it.
with open(settings_file, "w") as fh:
    fh.write("".join(f"key{i}=theirs\n" for i in range(9)))
with open(kilix_env, "w") as fh:
    fh.write("KILIX_CHROME_CLOCK=1\n")
display_only = w5.backend.create()
with open(kilix_env, "w") as fh:
    fh.write("KILIX_CHROME_CLOCK=0\n")
texts.clear()
with mock.patch.object(wm, "msgbox", lambda desk, title, text, **kw: texts.append(text)):
    w5.confirm_restore(display_only)
assert "kilix.env: KILIX_CHROME_CLOCK = 1\n" in texts[-1] + "\n", texts[-1]
assert "can change what runs" not in texts[-1], texts[-1]

# Many flagged changes stay on screen: eight are listed and the rest counted
# on their own line, never folded into the ordinary settings.
with open(kilix_env, "w") as fh:
    fh.write("".join(f"KILIX_FAKE_{i:02d}=x\n" for i in range(12)))
flood = w5.backend.create()
with open(kilix_env, "w") as fh:
    fh.write("")
texts.clear()
with mock.patch.object(wm, "msgbox", lambda desk, title, text, **kw: texts.append(text)):
    w5.confirm_restore(flood)
assert texts[-1].count("(can change what runs!)") == 8, texts[-1]
assert "... and 4 more that can change what runs" in texts[-1], texts[-1]

# Back Up Now names the files a backup cannot hold instead of writing an
# archive its own restore would refuse.
odd = os.path.join(w5.desk.shell.dir, "C:\\Users\\me\\report.txt")
with open(odd, "w") as fh:
    fh.write("from a zip\n")
texts.clear()
with mock.patch.object(wm, "msgbox", lambda desk, title, text, **kw: texts.append(text)):
    w5.back_up()
assert "Left out 1 file(s)" in texts[-1] and "report.txt" in texts[-1], texts[-1]
os.unlink(odd)
os.environ.pop("KILIX_DESKTOP_SUPERVISED", None)

print("ok")
