"""Journal display boundaries through real handlers and a socket peer.

The fake executable supplies ASCII JSON to the normal loader. Only the
accessibility helper launch/close boundary is stubbed; rendering, publication
and framed transport use their real implementations.
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
        time.sleep(.01)
    assert not win.futures, "private fake launcher did not settle"


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
        assert not closed, "journal display closed accessibility publication"
        deadline = time.monotonic() + 2
        messages = []
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


def scalar_and_control_safe(text):
    return all(unicodedata.category(c) != "Cs"
               and c not in "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
               and (unicodedata.category(c) != "Cc" or c in "\n\t") for c in text)


# Independent expected strings, including the different single/multiline
# policies. Valid scalars and meaningful joiners must survive both boundaries.
cases = [(chr(code), f"\\u{code:04x}", f"\\u{code:04x}")
         for code in (0xd800, 0xdbff, 0xdc80, 0xdfff)]
cases += [(c, " ", "?") for c in "\u061c\u202e\x00\x1b\x7f\x85\x9f"]
cases += [("\n", " ", "\n"), ("\t", " ", "\t"), ("\r\n", "  ", "\n")]
cases += [(sample, sample, sample) for sample in
          ("می\u200cروم", "👩\u200d💻", "क्\u200dष", "می\u200cروم 👩\u200d💻 😀\U0010ffff")]
failures = []


def check(condition, label):
    if not condition:
        failures.append(label)


def check_dialog(desk, win, expected, label):
    dialogs = [dialog for dialog in desk.wm.windows if dialog is not win]
    assert len(dialogs) == 1 and dialogs[0].title == "View Journal"
    bodies = [widget.text for widget in dialogs[0].widgets if hasattr(widget, "text")
              and widget.text.startswith("Could not read the journal")]
    assert len(bodies) == 1, "real message-box body was not found"
    body = bodies[0]
    check(body == expected, f"{label}: completed error dialog")
    check(scalar_and_control_safe(body), f"{label}: unsafe dialog body")
    desk.render()
    snapshot = publish(desk)
    # Label accessible names already omit tab-separated accelerator text.
    # The message body still retains the established multiline tab policy.
    expected_name = expected.split("\t", 1)[0]
    check(any(node["role"] == "label" and node["name"] == expected_name
              for node in snapshot["nodes"]), f"{label}: peer dialog accessible name")
    check(all(scalar_and_control_safe(text) for text in strings(snapshot)),
          f"{label}: unsafe socket-received snapshot")
    try:
        json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        check(False, f"{label}: socket-received snapshot is not strict UTF-8")
    return body


for sample, pending_sample, dialog_sample in cases:
    raw_id = "archive" + sample + "tail"
    journal = F.doc(F.JOURNALS["journals"][0], id=raw_id)
    original = copy.deepcopy(journal)
    fake = F.FakeKilix([
        F.response(["pty", "list"], F.doc(F.LIST, sessions=[], unreachable=[])),
        F.response(["pty", "journals", "list"], F.doc(F.JOURNALS, journals=[journal])),
    ])
    P.kilix_launcher = lambda: fake.path
    desk = H.make_desk()
    win = P.PtySessions(desk)
    desk.wm.add(win)
    try:
        settle(win)
        win._switch(1)
        settle(win)
        item = win.jlist.items[0]
        win.set_focus(win.jlist)
        win.jlist.sel = 0
        win._select_journal(item)
        assert win.jdetails.wait(8) and win.jdetails.complete
        assert item[2]["journal"] == original and win.b_jview.enabled
        desk.render()
        publish(desk)
        calls = fake.calls()
        win._view_journal()
        pending = win.journal_status
        label = ascii(sample)
        check(pending == f"Reading the journal of archive{pending_sample}tail…",
              f"{label}: loading status")
        check(scalar_and_control_safe(pending), f"{label}: unsafe loading status")
        # Display formatting must not change the context ID, selected object
        # or request validation. The real fetch rejects these IDs locally.
        assert win.futures["journal_view"][1]["id"] == raw_id
        assert item[2]["journal"] == original and journal == original
        desk.render()
        settle(win)
        body = check_dialog(desk, win,
                            f"Could not read the journal of archive{dialog_sample}tail:\n"
                            "That journal ID is not usable.", label)
        assert fake.calls() == calls, "an invalid ID reached the CLI"
        assert calls and all(call[:2] == ["pty", "list"]
                             or call[:3] == ["pty", "journals", "list"] for call in calls)
        assert item[2]["journal"] == original and journal == original
        assert win.journal_status == win.journal_summary and win.b_jview.enabled
        print(json.dumps({"input": sample, "loading_status": pending,
                          "dialog_body": body, "socket_received": True}), flush=True)
    finally:
        win.close()


# Check the complete message boundary as well as the ID. An error raised by
# a worker goes through the ordinary Future/_finish/message-box path.
desk = H.make_desk()
win = P.PtySessions(desk)
desk.wm.add(win)
try:
    settle(win)
    raw_error = "read\udfff\u061c\u202e\x1b\x85\r\nمی\u200cروم 👩\u200d💻"

    def fail():
        raise P.PtyError(raw_error)

    assert win._submit("journal_view", fail, ctx={"id": F.JOURNAL_VIEW["id"]})
    settle(win)
    check_dialog(desk, win,
                 f"Could not read the journal of {F.JOURNAL_VIEW['id']}:\n"
                 "read\\udfff????\nمی\u200cروم 👩\u200d💻", "worker failure text")
finally:
    win.close()

assert not failures, "journal display boundary failures:\n" + "\n".join(failures)
print(f"{len(cases)} journal-ID cases plus worker failure: loading status, "
      "dialog body and socket-received accessible names safe; raw data preserved")
