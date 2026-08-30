"""kilix desktop - System Manual browser.

Lists installed manual pages from the local manpath, filters them by name, and
renders the selected page into a read-only text pane.
"""
import os
import re
import subprocess

import theme as T
import widgets as W
import wm

M = 8
TOP = 8
LIST_Y = 38
LIST_W = 190
STATUS_H = 20
COMP_EXTS = ("gz", "bz2", "xz", "lzma", "zst")
DEFAULT_MANPATH = (
    "/usr/local/share/man",
    "/usr/share/man",
    "/usr/local/man",
    "/usr/X11R6/man",
)

_PAGE_RE = re.compile(r"^(.+)\.([0-9][A-Za-z0-9]*)(?:\.([^.]+))?$")
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _man_roots():
    env = os.environ.get("MANPATH")
    if env is not None:
        roots = []
        for part in env.split(":"):
            if part:
                roots.append(os.path.expanduser(part))
            else:
                roots.extend(DEFAULT_MANPATH)
        return roots
    try:
        r = subprocess.run(["manpath", "-q"], capture_output=True, text=True,
                           timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return [os.path.expanduser(p) for p in r.stdout.strip().split(":")
                    if p]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return list(DEFAULT_MANPATH)


def _parse_page_name(filename):
    m = _PAGE_RE.match(filename)
    if not m:
        return None
    name, section, comp = m.groups()
    if comp and comp not in COMP_EXTS:
        return None
    return name, section


def discover_pages(roots=None):
    """Return sorted manual page dicts from manpath roots.

    A page is {'name', 'section', 'label', 'path'}. The first occurrence in
    manpath order wins for duplicate name/section pairs.
    """
    seen = set()
    pages = []
    for root in roots or _man_roots():
        root = os.path.abspath(os.path.expanduser(root))
        if not os.path.isdir(root):
            continue
        for base, _dirs, files in os.walk(root):
            if not os.path.basename(base).startswith("man"):
                continue
            for filename in files:
                parsed = _parse_page_name(filename)
                if not parsed:
                    continue
                name, section = parsed
                key = (name.lower(), section.lower())
                if key in seen:
                    continue
                seen.add(key)
                pages.append({
                    "name": name,
                    "section": section,
                    "label": f"{name} ({section})",
                    "path": os.path.join(base, filename),
                })
    pages.sort(key=lambda p: (p["name"].lower(), p["section"].lower()))
    return pages


def _clean_man_text(text):
    text = _ANSI_RE.sub("", text).replace("\f", "\n")
    out = []
    for ch in text:
        if ch == "\b":
            if out:
                out.pop()
        elif ch != "\r":
            out.append(ch)
    return "".join(out).expandtabs(8).rstrip() + "\n"


def _run_man(page):
    env = dict(os.environ)
    env.update({
        "GROFF_NO_SGR": "1",
        "MANPAGER": "cat",
        "PAGER": "cat",
        "MANWIDTH": "88",
    })
    try:
        r = subprocess.run(
            ["man", page["section"], page["name"]],
            capture_output=True, text=True, errors="replace",
            timeout=15, env=env)
    except FileNotFoundError:
        return "The man command is not installed.\n"
    except subprocess.TimeoutExpired:
        return f"{page['label']}\n\nTimed out while rendering this manual page.\n"
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "No manual output.").strip()
        return f"{page['label']}\n\n{msg}\n"
    return _clean_man_text(r.stdout or "")


class _ReadOnlyTextArea(W.TextArea):
    def on_key(self, ev):
        rows = self._rows()
        if ev.key == "ArrowUp":
            self.sb.pos -= 1
        elif ev.key == "ArrowDown":
            self.sb.pos += 1
        elif ev.key == "PageUp":
            self.sb.pos -= rows
        elif ev.key == "PageDown":
            self.sb.pos += rows
        elif ev.key == "Home":
            self.sb.pos = 0
        elif ev.key == "End":
            self.sb.pos = max(0, len(self.lines) - rows)
        else:
            return False
        self.sb.total, self.sb.page = len(self.lines), rows
        self.sb.clamp()
        self.invalidate()
        return True


class ManualBrowser(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "System Manual", 700, 460, icon="help")
        self.min_w, self.min_h = 520, 320
        self.pages = discover_pages()
        self.rows = []
        self.selected = None
        self.status = ""
        cw, ch = self.client_size()

        self.add(W.Label(M, TOP + 3, "Search:"))
        btn_w = 58
        self.search = self.add(W.TextField(
            58, TOP, cw - 58 - (btn_w * 3 + 32),
            on_enter=lambda *_: self._search_now(),
            on_change=lambda *_: self._search_now(keep_sel=True)))
        self.b_search = self.add(W.Button(cw - 3 * btn_w - 24, TOP, btn_w, 21,
                                          "Search", cb=self._search_now,
                                          default=True))
        self.b_list = self.add(W.Button(cw - 2 * btn_w - 16, TOP, btn_w, 21,
                                        "List", cb=self._show_all))
        self.b_open = self.add(W.Button(cw - btn_w - M, TOP, btn_w, 21,
                                        "Open", cb=self._open_selected))
        self.results = self.add(W.ListBox(
            M, LIST_Y, LIST_W, ch - LIST_Y - STATUS_H - 6,
            on_select=self._select, on_activate=lambda *_: self._open_selected()))
        self.viewer = self.add(_ReadOnlyTextArea(
            LIST_W + 2 * M, LIST_Y, cw - LIST_W - 3 * M,
            ch - LIST_Y - STATUS_H - 6, ""))

        self._show_all()
        if arg == "list":
            self.set_focus(self.results)
        else:
            self.set_focus(self.search)

    def on_resize(self):
        cw, ch = self.client_size()
        btn_w = 58
        self.search.w = cw - 58 - (btn_w * 3 + 32)
        self.b_search.x = cw - 3 * btn_w - 24
        self.b_list.x = cw - 2 * btn_w - 16
        self.b_open.x = cw - btn_w - M
        h = ch - LIST_Y - STATUS_H - 6
        self.results.h = h
        self.viewer.x = LIST_W + 2 * M
        self.viewer.w = cw - LIST_W - 3 * M
        self.viewer.h = h

    def draw_client(self, d, img):
        cw, ch = self.client_size()
        T.sunken(d, 2, ch - STATUS_H, cw - 3, ch - 3, fill=T.FACE)
        d.text((8, ch - STATUS_H + 3), self.status, font=T.FONT, fill=T.TEXT)

    def _filter(self, query):
        q = query.strip().lower()
        if not q:
            return list(self.pages)
        return [p for p in self.pages
                if q in p["name"].lower()
                or q in p["section"].lower()
                or q in p["label"].lower()]

    def _set_rows(self, pages, keep_sel=False):
        self.rows = list(pages)
        self.results.set_items([("doc_text", p["label"], p) for p in self.rows],
                               keep_sel=keep_sel)
        if keep_sel and self.selected in self.rows:
            pass
        else:
            self.selected = None
            self.b_open.enabled = False
        n = len(self.rows)
        self.status = f"{n} manual page{'' if n == 1 else 's'}"
        if not self.pages:
            self.viewer.set_text("No manual pages were found on this system.\n")
        elif n == 0:
            self.viewer.set_text("No matching manual pages.\n")
        self.invalidate()

    def _show_all(self):
        self.search.set("")
        self._set_rows(self.pages)

    def _search_now(self, keep_sel=False):
        self._set_rows(self._filter(self.search.text), keep_sel=keep_sel)

    def _select(self, item):
        self.selected = item[2]
        self.b_open.enabled = True
        self.invalidate()

    def _open_selected(self):
        page = self.selected
        if page is None and 0 <= self.results.sel < len(self.results.items):
            page = self.results.items[self.results.sel][2]
        if page is None:
            return
        self.selected = page
        self.status = f"Opened {page['label']}"
        self.viewer.set_text(_run_man(page))
        self.set_focus(self.viewer)
        self.invalidate()
