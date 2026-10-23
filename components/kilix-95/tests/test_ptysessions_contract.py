"""PTY Sessions' kilix pty client: contract parsing, bounds, receipts.

Runs the app's backend against a fake `kilix pty` executable that prints the
documents of the kilix.pty/v1 contract. No broker, no Kilix store, no desktop.
"""
import shlex
import sys
import unicodedata

import harness as H  # noqa: F401  (puts the desktop dir on sys.path)
import pty_fake as F
from apps import ptysessions as P


def raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except P.PtyError as error:
        return str(error)
    raise AssertionError("expected PtyError")


fake = F.FakeKilix(F.standard_responses())
L = fake.path

# ── list: sessions and unreachable are separate, nothing is dropped ─────────
data = P.load_sessions(L)
assert data["runtime"] == F.RUNTIME
assert [s["id"] for s in data["sessions"]] == [
    F.DETACHED["id"], F.ATTACHED["id"]]
assert [s["id"] for s in data["unreachable"]] == [F.UNREACHABLE["id"]]
assert data["unreachable"][0]["reachable"] is False
assert fake.calls() == [["pty", "list", "--json"]], fake.calls()

# unknown fields are ignored, not fatal (the contract may grow within v1)
fake.set([F.response(["pty", "list"], F.doc(F.LIST, future_field=[1, 2]))])
assert len(P.load_sessions(L)["sessions"]) == 2

# a different schema, non-JSON, an array, a missing list and a failed exit
# are all errors that say so — never an empty listing
fake.set([F.response(["pty", "list"], F.doc(F.LIST, schema="kilix.pty/v2"))])
assert "schema" in raises(P.load_sessions, L)
fake.set([F.response(["pty", "list"], "not json at all")])
assert "not JSON" in raises(P.load_sessions, L)
fake.set([F.response(["pty", "list"], "[]")])
assert raises(P.load_sessions, L)
bad = F.doc(F.LIST)
del bad["unreachable"]
fake.set([F.response(["pty", "list"], bad)])
assert "malformed" in raises(P.load_sessions, L)
fake.set([F.response(["pty", "list"], None, 1,
                     "kilix pty: broker runtime is gone\n")])
assert raises(P.load_sessions, L) == "kilix pty: broker runtime is gone"
fake.set([F.response(["pty", "list"], F.LIST, 1)])
assert "exit status 1" in raises(P.load_sessions, L)

# a call that does not return within its bound is an error, not a hang
fake.set([F.response(["pty", "list"], F.LIST, sleep=5)])
assert "did not answer" in raises(P.run_pty, ["list", "--json"], L, 1)

# a missing launcher is explained
try:
    P.run_pty(["list"], "/nonexistent/kilix")
except P.PtyError as error:
    assert "Could not start" in str(error), error
else:
    raise AssertionError("a missing launcher was accepted")

# ── rows and states ─────────────────────────────────────────────────────────
assert P.session_state(F.DETACHED) == "detached"
assert P.session_state(F.ATTACHED) == "attached"
assert P.session_state(F.UNREACHABLE) == "unreachable"
now = F.DETACHED["started_millis"] + 5 * 60 * 1000 + 7
assert P.format_age(F.DETACHED["started_millis"], now) == "5m"
assert P.format_age(1000, 1000 + 7 * 3600 * 1000 + 120000) == "7h 02m"
assert P.format_age(1000, 1000 + 3 * 86400 * 1000) == "3d 0h"
assert P.format_age(None, now) == "?"
icon, label, row = P.session_row(F.DETACHED, now)
assert row["cells"] == ("3fa9c2d41b7e6a05", "detached", "5m", "80x24",
                        'sh -c echo "build ok"; sleep 300',
                        "/srv/work/build"), row["cells"]
assert "detached" in label and "/srv/work/build" in label
icon, label, row = P.session_row(F.UNREACHABLE, now)
assert icon == "warn" and row["state"] == "unreachable"
assert "UNREACHABLE" in label and F.UNREACHABLE["id"] in label
assert row["cells"][1] == "UNREACHABLE" and "timeout" in row["cells"][4]

# Startup facts are preserved by the client and identified in both the drawn
# command cell and its accessible name. They never enable a session action.
recording = F.RECORDED_UNREACHABLE["recorded"]
for recorded in (None, dict(argv=None, cwd=None, started_millis=None,
                            truncated=False), recording,
                 dict(recording, truncated=True),
                 dict(argv=[], cwd=None, started_millis=None, truncated=True),
                 dict(recording, argv="not an array"),
                 dict(recording, argv=["sh", None])):
    fixture = F.doc(F.UNREACHABLE, recorded=recorded)
    fake.set([F.response(["pty", "list"], F.doc(F.LIST, unreachable=[fixture]))])
    loaded = P.load_sessions(L)["unreachable"][0]
    assert loaded == fixture, (loaded, fixture)
    icon, label, row = P.session_row(loaded, now)
    details = P.session_details(row, F.RUNTIME, None, now)
    assert icon == "warn" and row["state"] == "unreachable"
    assert row["cells"][:4] == (fixture["id"], "UNREACHABLE", "?", "?")
    assert "timeout" in row["cells"][4]
    assert not P.can_end(loaded)[0]
    if recorded is None:
        assert "recorded at start" not in row["cells"][4] + label + details
    else:
        for text in (row["cells"][4], label, details):
            assert "recorded at start:" in text, text
            assert ("(truncated)" in text) == recorded["truncated"], text
        argv = recorded["argv"]
        if isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv):
            command = label.split("recorded at start: ", 1)[1].removesuffix(" (truncated)")
            assert shlex.split(command) == argv, command
        else:
            assert "(unknown)" in label, label

hostile = F.doc(F.RECORDED_UNREACHABLE)
hostile["recorded"]["argv"] = ["sh", "-c", "$(id)\n\x1b[2J\u202eecho café"]
icon, label, row = P.session_row(hostile, now)
details = P.session_details(row, F.RUNTIME, None, now)
for text in (label, row["cells"][4], details):
    assert "$(id)" in text and "echo café" in text
    assert "\x1b" not in text and "\u202e" not in text
assert "\n" not in label + row["cells"][4]

# The reviewer's reproducer contains all twelve Bidi_Control characters.
bidi_controls = ("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
                 "\u2066\u2067\u2068\u2069")
fixture = F.doc(F.UNREACHABLE, recorded={
    "argv": ["sh", "-c", "echo " + bidi_controls + "hello"],
    "truncated": False})
_, label, row = P.session_row(fixture, now)
details = P.session_details(row, F.RUNTIME, None, now)
for surface, text in (("cell", row["cells"][4]), ("accessible", label),
                      ("details", details)):
    remaining = [f"U+{ord(c):04X}" for c in bidi_controls if c in text]
    assert not remaining, (surface, "Bidi_Control survives", remaining)
    assert "recorded at start: sh -c 'echo " in text and "hello'" in text

# Recorded commands visibly escape benign Cf characters, while live/output
# text preserves them. Bidi controls and C0/C1 controls remain neutralised.
# Sweep each separately so command length bounds cannot hide a survivor.
format_controls = [chr(n) for n in range(sys.maxunicode + 1)
                   if unicodedata.category(chr(n)) == "Cf"]
controls = [chr(n) for n in range(0xa0)
            if unicodedata.category(chr(n)) == "Cc"]
assert "\u061c" in format_controls and "\U000e007f" in format_controls
for control in format_controls + controls:
    code = ord(control)
    visible = (" " if control in bidi_controls or control in controls else
               f"\\u{code:04x}" if code <= 0xffff else f"\\U{code:08x}")
    argv = ["sh", "-c", f"echo left{control}right café"]
    fixture = F.doc(F.UNREACHABLE, recorded={"argv": argv, "truncated": False})
    before = F.doc(fixture)
    _, label, row = P.session_row(fixture, now)
    details = P.session_details(row, F.RUNTIME, None, now)
    for surface, text in (("cell", row["cells"][4]), ("accessible", label),
                          ("details", details)):
        assert f"recorded at start: sh -c 'echo left{visible}right café'" in text, \
            (surface, f"U+{ord(control):04X}", repr(text))
        assert not any(unicodedata.category(c) == "Cf" for c in text), \
            (surface, f"U+{ord(control):04X}", repr(text))
    assert fixture == before, "display sanitization changed the recorded facts"
    assert "\n" not in label + row["cells"][4]
    # Multiline snapshots retain benign formatting and the established
    # tab/newline layout and CR-to-LF normalization.
    expected = ("\n" if control == "\r" else control
                if control in "\n\t" or control in format_controls
                and control not in bidi_controls else "?")
    assert P.clean_text(f"left{control}right café", multiline=True) == \
        f"left{expected}right café", f"U+{ord(control):04X}"
assert P.clean_text("café 界 e\u0301") == "café 界 e\u0301"
assert P.clean_text("a\t b\r\nc\rd\ne", multiline=True) == "a\t b\nc\nd\ne"

# Every surrogate must be visible data, never a raw UTF-8 encoding failure.
# Actual non-BMP Unicode remains intact, including JSON surrogate-pair input.
for code in range(0xd800, 0xe000):
    arg = f"left{chr(code)}right 😀"
    fixture = F.doc(F.UNREACHABLE, recorded={"argv": ["echo", arg]})
    before = F.doc(fixture)
    _, label, row = P.session_row(fixture, now)
    details = P.session_details(row, F.RUNTIME, None, now)
    visible = f"left\\u{code:04x}right 😀"
    for text in (label, row["cells"][4], details):
        assert visible in text, f"U+{code:04X} not visibly escaped"
        assert not any(unicodedata.category(c) == "Cs" for c in text)
        text.encode("utf-8")
    assert fixture == before
    assert P.clean_text(arg, multiline=True) == visible
assert P.clean_text("👩\u200d💻 😀") == "👩\u200d💻 😀"
print(f"Recorded display: 12 Bidi_Control and {len(controls)} C0/C1 controls "
      f"neutralised; {len(format_controls) - 12} benign Cf and 2048 Cs visibly "
      "escaped on all three surfaces; output preserves benign Cf")

# Remaining formatter callers: JSON runtime/identity/error/receipt fields,
# plus details' interpolated metadata. Preserve joiners and escape Cs there
# too; malformed values in otherwise numeric fields cannot reach UTF-8 raw.
sample = "می\u200cروم 👩\u200d💻 क्\u200dष"
raw, visible = sample + "\ud800", sample + "\\ud800"
audit_live = F.doc(F.DETACHED, id=raw, command=raw, cwd=raw, cwd_now=raw,
                   boot_id=raw, broker_pid=raw, child_pid=raw,
                   foreground_pgrp=raw, journal_epoch=raw, start_ticks=raw)
audit_unreachable = F.doc(F.UNREACHABLE, id=raw, error=raw)
audit_journal = F.doc(F.JOURNALS["journals"][0], id=raw, path=raw,
                      broker_pid=raw, child_pid=raw)
fake.set([
    F.response(["pty", "list"], F.doc(F.LIST, runtime=raw, sessions=[audit_live],
                                     unreachable=[audit_unreachable])),
    F.response(["pty", "journals", "list"], F.doc(
        F.JOURNALS, runtime=raw, journals=[audit_journal])),
])
loaded = P.load_sessions(L)
assert loaded["runtime"] == visible and loaded["sessions"] == [audit_live]
assert loaded["unreachable"] == [audit_unreachable]
for source in (audit_live, audit_unreachable):
    _, label, row = P.session_row(source, now)
    details = P.session_details(row, raw, None, now)
    assert visible in label and all(visible in c for c in (row["cells"][0], row["cells"][4]))
    assert visible in details and "\ud800" not in label + details
    details.encode("utf-8")
loaded = P.load_journals(L)
assert loaded["runtime"] == visible and loaded["journals"] == [audit_journal]
_, label, row = P.journal_row(audit_journal)
details = P.journal_details(row, raw)
assert visible in label and visible in details and "\ud800" not in label + details
details.encode("utf-8")
receipt = F.doc(F.UNCERTAIN, message=raw, reason=raw)
fake.set([F.kill_response(receipt)])
got = P.end_session(F.DETACHED["id"], F.DETACHED["started_millis"], L)
assert got["message"] == visible and got["reason"] == raw
assert visible in P.receipt_message(got)[1]
assert visible in P.receipt_message(F.doc(receipt, id=raw))[1]
fake.set([F.response(["pty", "list"], None, 1, sample + "\u061c\x1b")])
assert P.run_pty(["list"], L)[2] == sample + "  "
print("Formatter caller audit: runtime, identity, errors, receipts and metadata pass")

# A recording on a reachable row never replaces its live command or fields.
live = F.doc(F.DETACHED, recorded=recording)
_, live_label, live_row = P.session_row(live, now)
_, live_label_before, live_row_before = P.session_row(F.DETACHED, now)
assert live_label == live_label_before and live_row["cells"] == live_row_before["cells"]
assert P.session_details(P.session_row(live, now)[2], F.RUNTIME, None, now) == \
    P.session_details(P.session_row(F.DETACHED, now)[2], F.RUNTIME, None, now)

# ── ids and untrusted text ──────────────────────────────────────────────────
for ok in ("3fa9c2d41b7e6a05", "a.b_c-9", "x" * 64):
    assert P.valid_id(ok), ok
for bad in ("", ".", "..", "x" * 65, "a b", "a/b", "a;b", "$(id)", "é", None,
            "a\n", "-x"[:0]):
    assert not P.valid_id(bad), repr(bad)
assert P.clean_text("a\x1b[31mred\x07\x00") == "a [31mred  "
assert P.clean_text("a\x1b[31m\x9b\u202etxt\u202c\r\nb", multiline=True) \
    == "a?[31m??txt?\nb"
assert "\x1b" not in P.clean_text("\x1b]0;title\x07", multiline=True)

# ── a pane snapshot is bounded and sanitised ────────────────────────────────
fake.set(F.standard_responses())
text = P.fetch_pane_text(F.DETACHED["id"], L)
assert text == {"text": "build ok\ntests: 42 passed\n", "truncated": False,
                "total_bytes": 28}, text
last = [c for c in fake.calls() if c[:2] == ["pty", "observe"]][-1]
assert last == ["pty", "observe", F.DETACHED["id"], "--once", "--lines", "200",
                "--text", "--json"], last
hostile = "\n".join(f"line {i}\x1b[2J\x1b]52;c;ZXZpbA==\x07" for i in range(500))
fake.set([F.response(["pty", "observe"], F.doc(
    F.OBSERVE, text=hostile, truncated=False))])
out = P.fetch_pane_text(F.DETACHED["id"], L)
assert out["truncated"] is True
assert len(out["text"].split("\n")) <= P.VIEW_LINES + 1
assert "\x1b" not in out["text"] and "\x07" not in out["text"]
assert out["text"].splitlines()[-1].startswith("line 499")
fake.set([F.response(["pty", "observe"], F.doc(
    F.OBSERVE, text="x" * (P.VIEW_CHARS * 3)))])
assert len(P.fetch_pane_text(F.DETACHED["id"], L)["text"]) == P.VIEW_CHARS
fake.set([F.response(["pty", "observe"], F.doc(F.OBSERVE, id="ffffffffffffffff"))])
assert "different session" in raises(P.fetch_pane_text, F.DETACHED["id"], L)
fake.set([F.response(["pty", "observe"], F.doc(F.OBSERVE, text=None))])
assert "without text" in raises(P.fetch_pane_text, F.DETACHED["id"], L)
fake.set([F.response(["pty", "observe"], None, 1, "kilix pty: gone\n")])
assert raises(P.fetch_pane_text, F.DETACHED["id"], L) == "kilix pty: gone"
fake.clear()
raises(P.fetch_pane_text, "bad id;", L)
assert fake.calls() == [], "an unusable id reached kilix"

# ── journals ────────────────────────────────────────────────────────────────
fake.set(F.standard_responses())
journals = P.load_journals(L)["journals"]
assert [j["id"] for j in journals] == ["90d1e57a2c4b8f36"]
view = P.fetch_journal_text("90d1e57a2c4b8f36", 1791337517964, L)
assert view["text"] == "old out\n"
assert fake.calls()[-1] == ["pty", "journals", "show",
                            "90d1e57a2c4b8f36.1791337517964", "--text",
                            "--json", "--lines", "200"], fake.calls()[-1]

# ── end_session: exactly the contract's receipts, truthfully ────────────────
sid, started = F.DETACHED["id"], F.DETACHED["started_millis"]
for doc in (F.VERIFIED, F.UNCERTAIN, F.UNCERTAIN_UNSENT, F.REFUSED_OWN,
            F.REFUSED_MISMATCH, F.REFUSED_CANNOT_BIND,
            F.REFUSED_CALLER_UNIDENTIFIED, F.NOT_FOUND_RECEIPT):
    fake.set([F.kill_response(doc)])
    fake.clear()
    got = P.end_session(sid, started, L)
    assert got["result"] == doc["result"], (doc["result"], got)
    assert fake.calls() == [["pty", "kill", sid, "--yes", "--expect-started",
                             str(started), "--json"]], fake.calls()

# a receipt that lies about its exit status is not believed
fake.set([F.response(["pty", "kill"], F.VERIFIED, 1)])
got = P.end_session(sid, started, L)
assert got["result"] == "no_receipt", got
fake.set([F.response(["pty", "kill"], F.UNCERTAIN, 0)])
assert P.end_session(sid, started, L)["result"] == "no_receipt"
# a receipt for another session, an unknown result, no JSON: no receipt
fake.set([F.response(["pty", "kill"], F.doc(F.VERIFIED, id="ffffffffffffffff"), 0)])
assert P.end_session(sid, started, L)["result"] == "no_receipt"
fake.set([F.response(["pty", "kill"], F.doc(F.VERIFIED, result="gone"), 0)])
assert P.end_session(sid, started, L)["result"] == "no_receipt"
fake.set([F.response(["pty", "kill"], None, 2, "kilix pty: kill needs --yes\n")])
got = P.end_session(sid, started, L)
assert got["result"] == "no_receipt" and "needs --yes" in got["message"], got
# a kill that never returns: no receipt, never success
fake.set([F.response(["pty", "kill"], F.VERIFIED, 0, sleep=5)])
orig = P.KILL_TIMEOUT
P.KILL_TIMEOUT = 1
try:
    got = P.end_session(sid, started, L)
finally:
    P.KILL_TIMEOUT = orig
assert got["result"] == "no_receipt" and "did not answer" in got["message"], got
assert P.receipt_message(got)[0] == "error"

# the desktop's own session is refused locally: kilix is never even called
fake.set([F.kill_response(F.VERIFIED)])
fake.clear()
got = P.end_session(sid, started, L, own=sid)
assert got["result"] == "refused" and got["reason"] == "own_session", got
assert got["request_sent"] is False
assert fake.calls() == [], "an own-session end reached kilix"
# an unnameable session is not sent either
got = P.end_session(sid, None, L)
assert got["result"] == "no_receipt" and fake.calls() == []
got = P.end_session("bad id", started, L)
assert got["result"] == "no_receipt" and fake.calls() == []

# can_end: the one place that decides
assert P.can_end(F.DETACHED) == (True, "")
assert P.can_end(F.ATTACHED)[0] is True          # an attached session may end
assert not P.can_end(F.UNREACHABLE)[0]
# even if a future contract adds a start time to an unreachable entry
assert not P.can_end(F.doc(F.UNREACHABLE, started_millis=1791337517862))[0]
assert not P.can_end(F.DETACHED, own=sid)[0]
assert P.can_end(F.DETACHED, own="ffffffffffffffff")[0]
assert not P.can_end(F.doc(F.DETACHED, started_millis=None))[0]
assert not P.can_end(F.doc(F.DETACHED, id="a b"))[0]

# receipts read truthfully
text = {r: P.receipt_message(F.doc(d, result=d["result"]))
        for r, d in (("verified_absent", F.VERIFIED), ("uncertain", F.UNCERTAIN),
                     ("refused", F.REFUSED_OWN), ("not_found", F.NOT_FOUND_RECEIPT))}
assert text["verified_absent"][0] == "info"
assert "has ended" in text["verified_absent"][1]
assert "verified_absent" in text["verified_absent"][1]
assert text["uncertain"][0] == "warn" and "uncertain" in text["uncertain"][1]
assert "WAS sent" in text["uncertain"][1] and "Refresh" in text["uncertain"][1]
assert "has ended" not in text["uncertain"][1]
unsent = P.receipt_message(F.UNCERTAIN_UNSENT)[1]
assert "status_failed" in unsent and "Nothing was sent" in unsent, unsent
assert "WAS sent" not in unsent and "has ended" not in unsent
assert "Nothing was sent" in P.receipt_message(F.doc(
    F.UNCERTAIN_UNSENT, reason="status_timeout"))[1]
# the real receipts omit started_millis / waited_ms when nothing was polled
for bare in (F.UNCERTAIN_UNSENT, F.REFUSED_OWN, F.NOT_FOUND_RECEIPT):
    assert "started_millis" not in bare and "waited_ms" not in bare, bare
assert "waited_ms" not in F.REFUSED_MISMATCH
assert F.VERIFIED["waited_ms"] and F.VERIFIED["started_millis"]
assert P.receipt_message(F.VERIFIED)[0] == "info"
assert "own_session" in text["refused"][1] and "Nothing was ended" in text["refused"][1]
for bound in (F.REFUSED_CANNOT_BIND, F.REFUSED_CALLER_UNIDENTIFIED):
    icon, said = P.receipt_message(bound)
    assert icon == "warn" and "refused" in said and bound["reason"] in said
    assert "Nothing was ended" in said and "has ended" not in said, said
    assert bound["request_sent"] is False
# the real captured cannot_bind receipt: its own message is shown, after ours
real = P.receipt_message(F.doc(F.REFUSED_CANNOT_BIND, id=sid))[1]
assert "without --expect-started" in real and "older build" in real, real
assert "Nothing was ended" in real and "kilix pty kill " + sid in real, real
# a real receipt names the session it was printed for ("target"): another
# session's receipt is not believed
fake.set([F.response(["pty", "kill"], F.VERIFIED, 0)])
assert P.end_session(sid, started, L)["result"] == "no_receipt"
fake.set([F.kill_response(F.VERIFIED)])
assert P.end_session(sid, started, L)["result"] == "verified_absent"
assert "not_found" in text["not_found"][1]
assert "has ended" not in text["refused"][1] + text["not_found"][1]

print("ok")
