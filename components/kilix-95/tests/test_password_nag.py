"""Default-password nag: the security-check module degrades gracefully with no
helper, the tray shows a persistent 'password' icon while nagging, clicking it
opens a masked change-password dialog that validates + clears the nag on
success, and the notification balloon is a chromeless taskbar popup."""
import harness as H
import security
import widgets as W


# ── security module: no helper on the test box → never nags spuriously ──────
assert not security.available(), "test box unexpectedly has the passwd helper"
assert security.is_default_password() is False
ok, msg = security.change_password("whatever")
assert ok is False and "not available" in msg


# ── the tray icon appears only while the nag is armed ───────────────────────
d = H.make_desk()
tb = d.taskbar
assert not any(t[0] == "password" for t in tb._tray_icons())   # off by default

d.password_nag = True
assert "password" in [t[0] for t in tb._tray_icons()]


# ── clicking the password tray icon opens the change-password dialog ────────
pw = [t for t in tb._tray_icons() if t[0] == "password"][0]
px = (pw[2] + pw[3]) // 2
py = (tb.rect()[1] + tb.rect()[3]) // 2
H.click(d, px, py)
dlg = next((w for w in d.wm.windows if getattr(w, "title", "") == "Change Password"), None)
assert dlg is not None, "change-password dialog did not open"

# two MASKED password fields
fields = [w for w in dlg.widgets if isinstance(w, W.TextField)]
assert len(fields) == 2 and all(f.mask for f in fields), fields
new, conf = fields
assert new._disp() == "" and (new.__setattr__("text", "hi") or new._disp() == "••")


# ── validation keeps the dialog open on bad input ───────────────────────────
def submit(a, b):
    new.text, conf.text = a, b
    conf.on_enter()                    # bound to the dialog's OK handler

submit("", "")                         # empty
assert dlg in d.wm.windows
submit("abc", "abd")                   # mismatch
assert dlg in d.wm.windows
submit("plebian", "plebian")           # refuse the default
assert dlg in d.wm.windows


# ── success path: dialog closes and the tray nag clears ─────────────────────
security.change_password = lambda p: (True, "changed")
security.is_default_password = lambda: False        # recheck now sees it changed
submit("s3cret-new", "s3cret-new")
assert dlg not in d.wm.windows, "dialog stayed open after a successful change"
assert d.password_nag is False, "tray nag did not clear"
assert not any(t[0] == "password" for t in tb._tray_icons())


# ── a masked field must NOT leak its plaintext to the (shared/host) clipboard ─
import types as _types


def _ctrl_c(field, text):
    field.window = _types.SimpleNamespace(desk=d, focus=None, invalidate=lambda: None)
    field.text, field.anchor, field.cur = text, 0, len(text)   # select all
    field.on_key(W.Ev(kind="key", key="c", ctrl=True, text=""))


d.set_clipboard("")                                   # known baseline
_ctrl_c(W.TextField(0, 0, 100, mask=True), "hunter2")
assert d.clipboard == "", "masked field copied the plaintext secret to the clipboard"
_ctrl_c(W.TextField(0, 0, 100), "public")             # ordinary field still copies
assert d.clipboard == "public", d.clipboard


# ── the notification balloon is a chromeless popup above the tray ───────────
d.password_nag = True
tb.show_password_balloon()
bal = tb._popup
assert bal is not None and type(bal).__name__ == "_PasswordBalloon"
assert bal in d.wm.windows and getattr(bal, "_no_taskbar", False)
# dismissing the bubble (Later) closes it but the tray icon persists
bal._dismiss()
assert tb._popup is None and bal not in d.wm.windows
assert "password" in [t[0] for t in tb._tray_icons()], "icon vanished with the bubble"

print("ok")
