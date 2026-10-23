"""A fake `kilix pty` for the PTY Sessions tests.

The fixtures are the documents of the `kilix.pty/v1` contract (the examples in
the Kilix README's "JSON contracts" section), with every path under /srv. The
fake launcher is a real executable: the app runs it exactly as it runs
`kilix`, so argv, exit statuses and stdout/stderr are exercised end to end.
Each call is appended to a log the tests read back.

Not a test itself (run.py only runs test_*.py).
"""
import copy
import json
import os
import stat
import sys
import tempfile

RUNTIME = "/run/user/1000/kilix-pty-broker"
HEADER = {"schema": "kilix.pty/v1", "runtime": RUNTIME, "timeout_seconds": 2.0}

# SESSION example from the contract: detached, started in /srv/work.
DETACHED = {
    "id": "3fa9c2d41b7e6a05", "broker_pid": 1574870, "child_pid": 1574871,
    "foreground_pgrp": 1574871, "started_millis": 1791337517862,
    "journal_bytes": 28, "journal_epoch": 0, "attached": False,
    "replay_complete": True, "rows": 24, "columns": 80, "cwd": "/srv/work",
    "cwd_now": "/srv/work/build",
    "command": "sh -c echo \"build ok\"; sleep 300",
    "boot_id": "86ed1b01-26cc-46f2-9e7d-fa55e8c27217",
    "start_ticks": 11186224, "reachable": True,
}
# The same shape with a client attached (what a pane that is open looks like).
ATTACHED = dict(DETACHED, id="a1b2c3d4e5f60718", broker_pid=1574880,
                child_pid=1574881, foreground_pgrp=1574881,
                started_millis=1791337517964, attached=True, rows=40,
                columns=132, cwd="/srv/home", cwd_now=None,
                command="bash", start_ticks=11186300)
# `unreachable` example from the contract's list envelope.
UNREACHABLE = {"id": "0123456789abcdef", "reachable": False,
               "error": "timeout"}
RECORDED_UNREACHABLE = dict(UNREACHABLE, recorded={
    "argv": ["python3", "-c", "print('build ok')"], "cwd": "/srv/work",
    "started_millis": 1791337517862, "truncated": False})

LIST = dict(HEADER, timeout_seconds=1.0, sessions=[DETACHED, ATTACHED],
            unreachable=[UNREACHABLE])

NOT_FOUND = dict(HEADER, result="not_found", id="0000000000000000")

OBSERVE = dict(HEADER, id=DETACHED["id"], journal_epoch=0, cursor="0:28",
               total_bytes=28, truncated=False, untrusted=True,
               text="build ok\ntests: 42 passed\n")

JOURNALS = dict(HEADER, journals=[{
    "id": "90d1e57a2c4b8f36", "started_millis": 1791337517964,
    "reaped_millis": 1791337520392, "archived_millis": 1791337520000,
    "broker_pid": 1574875, "child_pid": 1574877, "raw_bytes": 8,
    "compressed_bytes": 21,
    "path": "/srv/kilix/state/pty-journals/"
            "90d1e57a2c4b8f36.1791337517964.journal.zst"}])

JOURNAL_VIEW = dict(HEADER, id="90d1e57a2c4b8f36",
                    started_millis=1791337517964, journal_epoch=None,
                    cursor=None, total_bytes=8, truncated=False,
                    untrusted=True, text="old out\n")


def receipt(result, sid=DETACHED["id"], reason=None, request_sent=True,
            message="", **extra):
    """A kill receipt with exactly the fields the real `kilix pty kill` prints
    for that case (captured from the real launcher in the B1 review): only
    receipts that polled for absence carry started_millis and waited_ms."""
    return dict(HEADER, result=result, id=sid, request_sent=request_sent,
                reason=reason, message=message, **extra)


# The three receipts below are real documents printed by `kilix pty kill` on
# real brokers (kilix's captures/kill-verified_absent.json,
# kill-refused-started_mismatch.json, kill-refused-cannot_bind.json), copied
# byte for byte as JSON. Their ID is "target"; kill_response() / doc() put
# the ID of the session under test into a copy where a flow needs it.
VERIFIED = json.loads('''
{
  "schema": "kilix.pty/v1",
  "runtime": "/run/user/1000/kilix-pty-broker",
  "timeout_seconds": 2.0,
  "result": "verified_absent",
  "id": "target",
  "request_sent": true,
  "reason": null,
  "message": "the session is gone",
  "started_millis": 1791370099423,
  "waited_ms": 151
}
''')
# request sent, the session was still listed after the grace period
UNCERTAIN = receipt("uncertain", reason="still_listed",
                    message="still listed after the grace period",
                    started_millis=DETACHED["started_millis"], waited_ms=3500)
# the lookup failed, so nothing was sent
UNCERTAIN_UNSENT = receipt(
    "uncertain", reason="status_failed", request_sent=False,
    message="could not look the session up; nothing was sent: "
            "kitty-pty-broker: query session: timed out")
REFUSED_OWN = receipt(
    "refused", reason="own_session", request_sent=False,
    message="that is this pane's own session; ending it would end this "
            "program. Run the kill from another pane")
REFUSED_MISMATCH = json.loads('''
{
  "schema": "kilix.pty/v1",
  "runtime": "/run/user/1000/kilix-pty-broker",
  "timeout_seconds": 2.0,
  "result": "refused",
  "id": "target",
  "request_sent": false,
  "reason": "started_mismatch",
  "message": "started_millis is 1791370099243, not the expected 1791370099242: another session now has this ID",
  "started_millis": 1791370099243,
  "expected_started_millis": 1791370099242,
  "hint": "read it again with `kilix pty status target --json`; kill only if the ID still names the session you meant"
}
''')
REFUSED_CANNOT_BIND = json.loads('''
{
  "schema": "kilix.pty/v1",
  "runtime": "/run/user/1000/kilix-pty-broker",
  "timeout_seconds": 2.0,
  "result": "refused",
  "id": "target",
  "request_sent": false,
  "reason": "cannot_bind",
  "message": "this session's broker is an older build that cannot check its identity, so nothing was done; a person can end it with `kilix pty kill target --yes` (without --expect-started)",
  "started_millis": 1791370102798,
  "hint": "a person can run: kilix pty kill target --yes   (an agent stops here and reports)"
}
''')
# Spec-shaped, NOT captured from a real run (kilix has not captured it): a kill
# with no identifiable caller, off a terminal.
REFUSED_CALLER_UNIDENTIFIED = receipt(
    "refused", reason="caller_unidentified", request_sent=False,
    message="cannot tell which pane asked; pass --no-caller-check to end it "
            "anyway")
NOT_FOUND_RECEIPT = receipt("not_found", request_sent=False,
                            message="no such session")

# exit statuses of the contract's table
EXIT = {"verified_absent": 0, "uncertain": 1, "refused": 3, "not_found": 4}


def response(match, stdout=None, code=0, stderr="", sleep=0):
    """One scripted answer: used when `match` is a prefix of the argv."""
    if stdout is not None and not isinstance(stdout, str):
        stdout = json.dumps(stdout)
    return {"match": list(match), "stdout": stdout or "", "code": code,
            "stderr": stderr, "sleep": sleep}


def kill_response(doc, sid=DETACHED["id"], sleep=0):
    """The scripted answer to `kill SID`: `doc` with its ID set to SID (the
    captures name their session "target")."""
    return response(["pty", "kill", sid], dict(doc, id=sid),
                    EXIT[doc["result"]], sleep=sleep)


_SCRIPT = '''#!{python}
import json, os, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_PTY_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
with open(os.environ["FAKE_PTY_STATE"]) as handle:
    state = json.load(handle)
for item in state["responses"]:
    if args[:len(item["match"])] == item["match"]:
        time.sleep(item["sleep"])
        sys.stdout.write(item["stdout"])
        sys.stderr.write(item["stderr"])
        sys.exit(item["code"])
sys.stderr.write("kilix pty: the fake has no answer for " + " ".join(args) + "\\n")
sys.exit(2)
'''


class FakeKilix:
    """A temp dir holding an executable `kilix` plus its script and call log."""

    def __init__(self, responses=()):
        self.dir = tempfile.mkdtemp(prefix="kilix95-fakepty-")
        self.path = os.path.join(self.dir, "kilix")
        self.state = os.path.join(self.dir, "state.json")
        self.log = os.path.join(self.dir, "calls.log")
        with open(self.path, "w") as handle:
            handle.write(_SCRIPT.format(python=sys.executable))
        os.chmod(self.path, os.stat(self.path).st_mode | stat.S_IXUSR)
        open(self.log, "w").close()
        os.environ["FAKE_PTY_STATE"] = self.state
        os.environ["FAKE_PTY_LOG"] = self.log
        self.set(responses)

    def set(self, responses):
        with open(self.state, "w") as handle:
            json.dump({"responses": list(responses)}, handle)

    def calls(self):
        with open(self.log) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def clear(self):
        open(self.log, "w").close()


def standard_responses():
    """list, status-free: what a desktop with three sessions sees."""
    return [
        response(["pty", "list", "--json"], LIST),
        response(["pty", "observe", DETACHED["id"], "--once"], OBSERVE),
        response(["pty", "journals", "list", "--json"], JOURNALS),
        response(["pty", "journals", "show"], JOURNAL_VIEW),
        kill_response(VERIFIED),
    ]


def doc(base, **changes):
    out = copy.deepcopy(base)
    out.update(changes)
    return out
