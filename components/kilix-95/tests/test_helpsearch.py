"""Help Search uses the RC5 CLI lookup and shows source-bound passages."""
import json
from types import SimpleNamespace
from unittest import mock

import harness as H
from apps import helpsearch


row = {
    "id": "kilix:docs/kilix/help/panes.md#1",
    "source": "kilix",
    "repo": "kilix-help-llm",
    "path": "docs/kilix/help/panes.md",
    "heading": "Kilix > Panes",
    "text": "Use Ctrl+Alt+R to split right.",
    "commit": "a" * 40,
}
finished = SimpleNamespace(returncode=0, stdout=json.dumps([row]), stderr="")

with mock.patch.object(helpsearch.subprocess, "run", return_value=finished) as run:
    assert helpsearch.lookup("  --iso in a VM?  ", "/opt/kilix/kilix") == [row]
    assert run.call_args.args[0] == [
        "/opt/kilix/kilix", "help-search", "-k", "5", "--json", "--",
        "--iso in a VM?"]
    assert run.call_args.kwargs["timeout"] == 120

with mock.patch.object(helpsearch.subprocess, "run", return_value=SimpleNamespace(
        returncode=0, stdout="not json", stderr="")):
    try:
        helpsearch.lookup("pane", "/opt/kilix/kilix")
    except helpsearch.HelpSearchError:
        pass
    else:
        raise AssertionError("invalid output was accepted")

with mock.patch.object(helpsearch, "lookup", return_value=[row]):
    desk = H.make_desk()
    window = helpsearch.HelpSearch(desk)
    desk.wm.add(window)
    window.search.set("split right")
    window._search_now()
    assert window.status == "Searching documentation…"
    window.future.result(timeout=2)
    window.refresh(0)
    assert window.status == "1 cited passage."
    assert len(window.results.items) == 1
    assert "Ctrl+Alt+R" in window.viewer.text()
    assert row["path"] in window.viewer.text()
    assert row["commit"] in window.viewer.text()
    assert "Corpus repository: kilix-help-llm" in window.viewer_source
    assert all(helpsearch.T.text_w(window.viewer.font, line)
               <= window.viewer.w - helpsearch.T.SCROLL_W - 10
               for line in window.viewer.lines)
    long_source = "W" * 200
    window._show_text(long_source)
    assert window.viewer_source == long_source
    assert "".join(window.viewer.lines) == long_source
    assert all(helpsearch.T.text_w(window.viewer.font, line)
               <= window.viewer.w - helpsearch.T.SCROLL_W - 10
               for line in window.viewer.lines)
    window.close()
    assert window.refresh not in desk.tick_hooks

print("ok")
