"""Worker errors through all real completion handlers and socket publication.

Only the accessibility helper launch/close boundary is stubbed. Workers run
in the real executor, and rendering, message boxes, publication and the
framed socket peer use their ordinary implementations.
"""
import copy
import json
import socket
import time
import unicodedata

import harness as H
import pty_fake as F
from accessibility import Controller, Tree
from accessibility_protocol import Channel
from apps import ptysessions as P


def settle(win):
    deadline = time.monotonic() + 8
    while win.futures and time.monotonic() < deadline:
        win._tick(time.time())
        time.sleep(.001)
    assert not win.futures, "private worker did not settle"


def publish(desk):
    left, right = socket.socketpair()
    controller = Controller.__new__(Controller)
    controller.desk, controller.tree = desk, Tree(desk)
    controller.channel, receiver = Channel(left), Channel(right)
    controller.closed, controller.last, controller._geometry = False, None, None
    closed = []
    controller.close = lambda: closed.append(True)
    try:
        controller.publish()
        assert not closed, "worker error closed accessibility publication"
        messages = []
        deadline = time.monotonic() + 2
        while not messages and time.monotonic() < deadline:
            controller.channel.flush()
            messages.extend(receiver.receive())
            if not messages:
                time.sleep(.001)
        assert messages and messages[-1]["type"] == "snapshot", "no snapshot reached the peer"
        return messages[-1]
    finally:
        left.close()
        right.close()


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for part in value.values():
            yield from strings(part)
    elif isinstance(value, list):
        for part in value:
            yield from strings(part)


BIDI = "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
JOINERS = "می\u200cروم 👩\u200d💻"
cases = [(chr(code), f"\\u{code:04x}", f"\\u{code:04x}")
         for code in (0xd800, 0xdbff, 0xdc80, 0xdfff)]
cases += [(char, " ", "?") for char in BIDI + "\x00\x1b\x7f\x85\x9f"]
cases += [("\n", " ", "\n"), ("\t", " ", "\t"), ("\r\n", "  ", "\n")]
cases += [(sample, sample, sample) for sample in
          ("می\u200cروم", "👩\u200d💻", "क्\u200dष", JOINERS + " 😀\U0010ffff e\u0301\ufe0f")]
failures = []


def check(condition, label):
    if not condition:
        failures.append(label)


def safe(text, multiline=True):
    allowed = "\n\t" if multiline else ""
    return all(unicodedata.category(c) != "Cs" and c not in BIDI
               and (unicodedata.category(c) != "Cc" or c in allowed) for c in text)


for kind in ("list", "journals", "preview", "journal_view", "kill"):
    for error_type in (P.PtyError, RuntimeError):
        live = F.doc(F.DETACHED, command=JOINERS, cwd=JOINERS, cwd_now=JOINERS)
        journal = F.doc(F.JOURNALS["journals"][0], path="/private/" + JOINERS)
        recorded = F.doc(F.RECORDED_UNREACHABLE, recorded={
            "argv": ["echo", "raw\udfff 👩\u200d💻"], "truncated": False})
        sources = copy.deepcopy((live, journal, recorded))
        fake = F.FakeKilix([
            F.response(["pty", "list"], F.doc(F.LIST, sessions=[live], unreachable=[recorded])),
            F.response(["pty", "journals", "list"], F.doc(F.JOURNALS, journals=[journal])),
        ])
        P.kilix_launcher = lambda: fake.path
        desk = H.make_desk()
        win = P.PtySessions(desk)
        desk.wm.add(win)
        try:
            settle(win)
            win.list.sel = 0
            win._select_session(win.list.items[0])
            win._switch(1)
            settle(win)
            win.jlist.sel = 0
            win._select_journal(win.jlist.items[0])
            win._switch(1 if kind in ("journals", "journal_view") else 0)
            assert win.details.wait(8) and win.details.complete
            assert win.jdetails.wait(8) and win.jdetails.complete
            for sample, single, multi in cases:
                raw_error = "left" + sample + "right"
                error = error_type(raw_error)
                prefix = "Unexpected failure: " if error_type is RuntimeError else ""
                single_error, multi_error = prefix + "left" + single + "right", prefix + "left" + multi + "right"
                sid = journal["id"] if kind == "journal_view" else live["id"]
                context = {"id": sid, "raw": sample, "started_millis": live["started_millis"]}
                original_context = copy.deepcopy(context)
                calls = fake.calls()
                old_sessions, old_journals = win.list.items, win.jlist.items
                listed_at, summary, jsummary = win.listed_at, win.session_summary, win.journal_summary
                win.last_refresh = time.time()

                def fail():
                    raise error

                assert win._submit(kind, fail, ctx=context)
                future, submitted_context = win.futures[kind]
                assert submitted_context is context
                settle(win)
                assert future.exception() is error and error.args == (raw_error,)
                assert context == original_context, "display changed structured job context"
                label = f"{kind}/{error_type.__name__}/{ascii(sample)}"
                dialog = None
                if kind == "list":
                    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(listed_at / 1000))
                    expected = f"Could not list sessions: {single_error} Showing the list from {stamp}."
                    displayed = win.session_status
                    assert win.list.items is old_sessions and win.listed_at == listed_at
                elif kind == "journals":
                    expected = f"Could not list journals: {single_error}"
                    displayed = win.journal_status
                    assert win.jlist.items is old_journals and win.journals_loaded
                else:
                    dialogs = [w for w in desk.wm.windows if w is not win]
                    assert len(dialogs) == 1
                    dialog = dialogs[0]
                    if kind == "preview":
                        expected = f"Could not read session {sid}:\n{multi_error}"
                        assert dialog.title == "Preview" and win.session_status == summary
                        assert win.b_preview.enabled
                    elif kind == "journal_view":
                        expected = f"Could not read the journal of {sid}:\n{multi_error}"
                        assert dialog.title == "View Journal" and win.journal_status == jsummary
                        assert win.b_jview.enabled
                    else:
                        expected = (f"No receipt for session {sid}.\n\n{single_error}\n"
                                    "The session may or may not have ended. Refresh the list to find out.")
                        assert dialog.title == "End Session" and win.b_end.enabled
                    displayed = next(w.text for w in dialog.widgets
                                     if getattr(w, "text", "").startswith(expected.split("\n", 1)[0]))
                check(displayed == expected, f"{label}: completed display text")
                check(safe(displayed, multiline=kind not in ("list", "journals")),
                      f"{label}: unsafe display text")
                desk.render()
                snapshot = publish(desk)
                if dialog is not None:
                    # Existing Label names omit tab-separated accelerator text.
                    expected_name = expected.split("\t", 1)[0]
                    check(any(node["role"] == "label" and node["name"] == expected_name
                              for node in snapshot["nodes"]), f"{label}: socket dialog name")
                check(all(safe(text) for text in strings(snapshot)), f"{label}: unsafe socket snapshot")
                try:
                    json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
                except UnicodeEncodeError:
                    check(False, f"{label}: socket snapshot is not strict UTF-8")
                assert any(JOINERS in text for text in strings(snapshot))
                assert [item[2]["session"] for item in win.list.items] == [live, recorded]
                assert win.jlist.items[0][2]["journal"] == journal
                assert (live, journal, recorded) == sources
                if kind == "kill":
                    assert fake.calls() == calls + [["pty", "list", "--json"]], "kill failure must refresh only"
                else:
                    assert fake.calls() == calls, "injected failure launched an extra CLI action"
                if dialog is not None:
                    dialog.close()
                print(json.dumps({"kind": kind, "exception": error_type.__name__,
                                  "sample": sample, "display": displayed, "socket_received": True}), flush=True)
        finally:
            win.close()

assert not failures, "worker-error display failures:\n" + "\n".join(failures)
print(f"{len(cases)} Unicode samples x 2 exception classes x 5 completion handlers: "
      "display boundaries and socket snapshots safe; raw context, exceptions, objects and behavior preserved")
