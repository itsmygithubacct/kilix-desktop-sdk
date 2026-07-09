"""System Manual: discover pages, filter them, and render a selected page."""
import os
import tempfile

import harness as H
from apps import manual


root = tempfile.mkdtemp(prefix="kilix95-man-")
man1 = os.path.join(root, "man1")
man8 = os.path.join(root, "man8")
os.makedirs(man1, exist_ok=True)
os.makedirs(man8, exist_ok=True)
open(os.path.join(man1, "bash.1.gz"), "w").close()
open(os.path.join(man1, "printf.1posix.gz"), "w").close()
open(os.path.join(man8, "shutdown.8"), "w").close()
open(os.path.join(man1, "not-a-page.txt"), "w").close()

pages = manual.discover_pages([root])
assert [p["label"] for p in pages] == [
    "bash (1)", "printf (1posix)", "shutdown (8)"
]

assert manual._clean_man_text("A\bA _\bB \x1b[1mC\x1b[0m") == "A B C\n"

real_discover = manual.discover_pages
real_run_man = manual._run_man
try:
    manual.discover_pages = lambda roots=None: pages
    manual._run_man = lambda page: (
        f"{page['name'].upper()}({page['section']})\nmanual body\n")

    d = H.make_desk()
    win = manual.ManualBrowser(d, "list")
    d.wm.add(win)

    assert len(win.results.items) == 3, win.results.items
    assert win.status == "3 manual pages"

    win.search.set("bash")
    win._search_now()
    assert [it[1] for it in win.results.items] == ["bash (1)"]

    win._select(win.results.items[0])
    win._open_selected()
    assert "BASH(1)" in win.viewer.text()
    assert "manual body" in win.viewer.text()
    assert win.status == "Opened bash (1)"

    win.search.set("missing")
    win._search_now()
    assert win.results.items == []
    assert "No matching manual pages" in win.viewer.text()
finally:
    manual.discover_pages = real_discover
    manual._run_man = real_run_man

print("ok")
