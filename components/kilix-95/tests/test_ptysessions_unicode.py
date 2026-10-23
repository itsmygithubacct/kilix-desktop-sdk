"""Unicode regressions through fake CLI, real windows and publication.

Only the accessibility helper's launch/close boundary is stubbed. Snapshots,
Controller.publish and the framed socket transport are the real implementation.
"""
import json
import os
import socket
import time
import unicodedata

import harness as H
import pty_fake as F
from accessibility import Controller, Tree
from accessibility_protocol import Channel
from apps import ptysessions as P

os.environ.pop("KITTY_PTY_BROKER_SESSION", None)
samples = ["می\u200cروم", "👩\u200d💻", "क्\u200dष", "می\u200cروم 👩\u200d💻"]
live = [F.doc(F.DETACHED, id=f"{i + 1:016x}", command=sample,
              cwd=sample, cwd_now=sample) for i, sample in enumerate(samples)]
codes = [0xd800, 0xdbff, 0xdc80, 0xdfff]
recorded = [F.doc(F.UNREACHABLE, id=f"{i + 256:016x}", recorded={
    "argv": ["echo", f"left{chr(code)}right 😀"], "truncated": False})
    for i, code in enumerate(codes)]
journals = [F.doc(F.JOURNALS["journals"][0], id=f"{i + 512:016x}",
                  path=f"/private/{sample}.zst") for i, sample in enumerate(samples)]
responses = [
    F.response(["pty", "list"], F.doc(F.LIST, sessions=live, unreachable=recorded)),
    F.response(["pty", "journals", "list"], F.doc(F.JOURNALS, journals=journals)),
]
for session, journal, sample in zip(live, journals, samples):
    responses += [
        F.response(["pty", "observe", session["id"]],
                   F.doc(F.OBSERVE, id=session["id"], text=sample + "\n")),
        F.response(["pty", "journals", "show", f"{journal['id']}.{journal['started_millis']}"],
                   F.doc(F.JOURNAL_VIEW, id=journal["id"], text=sample + "\n")),
    ]
fake = F.FakeKilix(responses)
P.kilix_launcher = lambda: fake.path
desk = H.make_desk()
win = P.PtySessions(desk)
desk.wm.add(win)


def settle():
    deadline = time.monotonic() + 8
    while win.futures and time.monotonic() < deadline:
        win._tick(time.time())
        time.sleep(.01)
    assert not win.futures, "private fake launcher did not settle"


def select(item, journal=False):
    listing = win.jlist if journal else win.list
    win.set_focus(listing)
    listing.sel = listing.items.index(item)
    (win._select_journal if journal else win._select_session)(item)
    view = win.jdetails if journal else win.details
    assert view.wait(8) and view.complete, "details layout failed"


left, right = socket.socketpair()
controller = Controller.__new__(Controller)
controller.desk, controller.tree = desk, Tree(desk)
controller.channel, receiver = Channel(left), Channel(right)
controller.closed, controller.last, controller._geometry = False, None, None
closed = []
controller.close = lambda: closed.append(True)


def publish():
    controller.publish()
    assert not closed, "malformed PTY text closed accessibility publication"
    assert controller.last is not None, "no accessibility snapshot was queued"
    # Also require Unicode scalar strings even though the transport's JSON
    # uses ASCII escapes. This catches the strict UTF-8 hashing failure.
    json.dumps(controller.last, ensure_ascii=False).encode("utf-8")
    messages = []
    deadline = time.monotonic() + 2
    while not messages and time.monotonic() < deadline:
        controller.channel.flush()
        messages.extend(receiver.receive())
        if not messages:
            time.sleep(.001)
    assert messages and messages[-1]["type"] == "snapshot", "publication did not reach the peer"
    return messages[-1]


def displayed_texts(snapshot):
    return [node["text"] for node in snapshot["nodes"] if node["role"] == "text"]


try:
    settle()
    # The fake executable emits ASCII JSON, including escaped high/low
    # surrogates, and the app uses its ordinary JSON decoder and row loader.
    for source, code in zip(recorded, codes):
        assert json.loads(json.dumps(source)) == source
        item = next(i for i in win.list.items if i[2]["session"]["id"] == source["id"])
        select(item)
        desk.render()
        snapshot = publish()
        expected = f"left\\u{code:04x}right 😀"
        assert item[2]["session"] == source, "display changed the recorded object"
        for text in (item[1], item[2]["cells"][4], win.details.source, win.details.text()):
            assert expected in text, (f"U+{code:04X}", ascii(text))
            assert not any(unicodedata.category(c) == "Cs" for c in text)
        assert any(node["role"] == "list item" and node["name"] == item[1]
                   for node in snapshot["nodes"])
        assert any(expected in text for text in displayed_texts(snapshot))
        assert all(not b.enabled for b in (win.b_observe, win.b_preview, win.b_attach, win.b_end))
        calls = fake.calls()
        win._observe(); win._preview(); win._attach(); win._end()
        assert fake.calls() == calls and not win.futures

    # The review's seven paths use real live rows and real observe/journal
    # fetches. End Session adds an eighth path, through its actual handler.
    for session, journal, sample in zip(live, journals, samples):
        win._switch(0)
        item = next(i for i in win.list.items if i[2]["session"]["id"] == session["id"])
        select(item)
        assert item[2]["session"] == session
        for text in (item[2]["cells"][4], item[2]["cells"][5], item[1], win.details.source):
            assert sample in text, (ascii(sample), ascii(text))
        snapshot = publish()
        assert any(node["name"] == item[1] for node in snapshot["nodes"])
        assert any(sample in text for text in displayed_texts(snapshot))

        win._preview()
        settle()
        output = H.find_window(desk, "OutputWindow")
        assert output is not None and output.view.wait(8) and output.view.complete
        assert output.view.source == sample + "\n"
        desk.render()
        snapshot = publish()
        assert any(node["role"] == "text" and node["name"] == output.view.accessibility_name
                   and sample in node["text"] for node in snapshot["nodes"])
        output.close()

        win._switch(1)
        settle()
        item = next(i for i in win.jlist.items if i[2]["journal"]["id"] == journal["id"])
        select(item, journal=True)
        assert item[2]["journal"] == journal
        assert f"/private/{sample}.zst" in win.jdetails.source
        win._view_journal()
        settle()
        output = H.find_window(desk, "OutputWindow")
        assert output is not None and output.view.wait(8) and output.view.complete
        assert output.view.source == sample + "\n"
        desk.render()
        snapshot = publish()
        assert any(f"/private/{sample}.zst" in text for text in displayed_texts(snapshot))
        assert any(node["role"] == "text" and node["name"] == output.view.accessibility_name
                   and sample in node["text"] for node in snapshot["nodes"])
        output.close()

        win._switch(0)
        item = next(i for i in win.list.items if i[2]["session"]["id"] == session["id"])
        select(item)
        win._end()
        confirm = H.find_window(desk, "ConfirmEnd")
        assert confirm is not None and confirm.view.wait(8) and confirm.view.complete
        assert confirm.command == sample and sample in confirm.view.text()
        snapshot = publish()
        assert any(node["role"] == "text" and node["name"] == confirm.view.accessibility_name
                   and sample in node["text"] for node in snapshot["nodes"])
        confirm.close()

    assert not any(call[:2] == ["pty", "kill"] for call in fake.calls())
    assert len([call for call in fake.calls() if call[:2] == ["pty", "observe"]]) == len(samples)
    assert len([call for call in fake.calls() if call[:3] == ["pty", "journals", "show"]]) == len(samples)
    # JSON's valid UTF-16 surrogate pair is a scalar after decoding.
    assert json.loads('"\\ud83d\\udc69"') == "👩"
    assert P.clean_text(json.loads('"\\ud83d\\udc69"')) == "👩"
    print("4 high/low surrogate windows publish intact; 4 joiner samples preserved "
          "on all seven paths and End Session; real socket snapshots delivered")
finally:
    win.close()
    left.close()
    right.close()
