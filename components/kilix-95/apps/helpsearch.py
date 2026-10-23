"""Search the shipped Kilix help corpus and display original cited passages."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil
import subprocess

import theme as T
import widgets as W
import wm

from apps.manual import _ReadOnlyTextArea

M = 8
TOP = 8
LIST_Y = 38
LIST_W = 210
STATUS_H = 20


class HelpSearchError(ValueError):
    pass


def kilix_launcher():
    """Use the same installed Kilix launcher reached from the desktop menu."""
    from shell import KILIX_HOME

    candidate = os.path.join(KILIX_HOME, "kilix")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    return shutil.which("kilix")


def lookup(question, launcher=None):
    question = question.strip()
    if not 1 <= len(question) <= 2000:
        raise HelpSearchError("Enter a help question of 1–2000 characters.")
    launcher = launcher or kilix_launcher()
    if launcher is None:
        raise HelpSearchError("The Kilix launcher is unavailable.")
    try:
        result = subprocess.run(
            [launcher, "help-search", "-k", "5", "--json", "--", question],
            capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired as error:
        raise HelpSearchError("Help search timed out; try again.") from error
    except OSError as error:
        raise HelpSearchError(f"Could not start Kilix help search: {error}") from error
    if result.returncode:
        reason = (result.stderr or result.stdout).strip()[:400]
        raise HelpSearchError(reason or "Kilix help search failed.")
    try:
        rows = json.loads(result.stdout)
    except ValueError as error:
        raise HelpSearchError("Kilix help search returned invalid results.") from error
    if not isinstance(rows, list) or len(rows) > 5:
        raise HelpSearchError("Kilix help search returned invalid results.")
    for row in rows:
        if not isinstance(row, dict) or any(
                not isinstance(row.get(key), str)
                for key in ("id", "source", "repo", "path", "heading", "text", "commit")):
            raise HelpSearchError("Kilix help search returned invalid results.")
    return rows


class HelpSearch(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Help Search", 720, 470, icon="help")
        self.min_w, self.min_h = 530, 320
        self.rows = []
        self.future = None
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.status = "Ask about Kilix, kitty, Pleb, or Plebian-OS."
        cw, ch = self.client_size()
        self.add(W.Label(M, TOP + 3, "Question:"))
        self.search = self.add(W.TextField(
            72, TOP, cw - 72 - 84,
            on_enter=lambda *_: self._search_now()))
        self.b_search = self.add(W.Button(cw - 76, TOP, 68, 21,
                                          "Search", cb=self._search_now,
                                          default=True))
        self.results = self.add(W.ListBox(
            M, LIST_Y, LIST_W, ch - LIST_Y - STATUS_H - 6,
            on_select=self._select, on_activate=self._select))
        self.viewer = self.add(_ReadOnlyTextArea(
            LIST_W + 2 * M, LIST_Y, cw - LIST_W - 3 * M,
            ch - LIST_Y - STATUS_H - 6, ""))
        self.viewer_source = ""
        self._show_text("Results are original documentation excerpts, not generated answers.\n")
        self.set_focus(self.search)
        self.desk.tick_hooks.append(self.refresh)
        self.on_close = self.cleanup
        if isinstance(arg, str) and arg.strip():
            self.search.set(arg)
            self._search_now()

    def on_resize(self):
        cw, ch = self.client_size()
        self.search.w = cw - 72 - 84
        self.b_search.x = cw - 76
        height = ch - LIST_Y - STATUS_H - 6
        self.results.h = height
        self.viewer.x = LIST_W + 2 * M
        self.viewer.w = cw - LIST_W - 3 * M
        self.viewer.h = height
        self._show_text(self.viewer_source)

    def _show_text(self, source):
        """Wrap display lines to the viewer width without losing source characters."""
        self.viewer_source = source
        width = max(1, self.viewer.w - T.SCROLL_W - 10)
        lines = []
        for original in source.expandtabs(4).split("\n"):
            line = original
            while line and T.text_w(self.viewer.font, line) > width:
                low, high = 1, len(line)
                while low < high:
                    middle = (low + high + 1) // 2
                    if T.text_w(self.viewer.font, line[:middle]) <= width:
                        low = middle
                    else:
                        high = middle - 1
                cut = max(1, low)
                lines.append(line[:cut])
                line = line[cut:]
            lines.append(line)
        self.viewer.set_text("\n".join(lines))

    def draw_client(self, d, img):
        cw, ch = self.client_size()
        T.sunken(d, 2, ch - STATUS_H, cw - 3, ch - 3, fill=T.FACE)
        d.text((8, ch - STATUS_H + 3), self.status[:110], font=T.FONT, fill=T.TEXT)

    def _search_now(self):
        if self.future is not None:
            return
        question = self.search.text.strip()
        if not 1 <= len(question) <= 2000:
            self.status = "Enter a help question of 1–2000 characters."
            self.invalidate()
            return
        self.status = "Searching documentation…"
        self.b_search.enabled = False
        self.future = self.pool.submit(lookup, question)
        self.invalidate()

    def refresh(self, _now):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.b_search.enabled = True
        try:
            self.rows = future.result()
        except HelpSearchError as error:
            self.rows = []
            self.status = "Search failed."
            self.results.set_items([])
            self._show_text(str(error) + "\n")
        except Exception:
            self.rows = []
            self.status = "Search failed."
            self.results.set_items([])
            self._show_text("Help search failed unexpectedly; try again.\n")
        else:
            self.results.set_items([
                ("doc_text", f"{row['source']}: {row['heading'].split(' > ')[-1]}", row)
                for row in self.rows])
            self.status = f"{len(self.rows)} cited passage{'s' if len(self.rows) != 1 else ''}."
            if self.rows:
                self.results.sel = 0
                self._select(self.results.items[0])
            else:
                self._show_text("No matching documentation passages.\n")
        self.invalidate()

    def _select(self, item):
        row = item[2]
        self._show_text(
            f"{row['heading']}\n\n"
            f"Collection: {row['source']}\n"
            f"Corpus repository: {row['repo']}\n"
            f"Corpus path: {row['path']}\n"
            f"Corpus commit: {row['commit']}\n"
            f"Passage: {row['id']}\n\n{row['text']}\n")
        self.invalidate()

    def cleanup(self):
        if self.refresh in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self.refresh)
        self.pool.shutdown(wait=False, cancel_futures=True)
