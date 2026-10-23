"""Unsaved-document checkpoints, so a crash does not take the user's typing with it.

A window opts in by defining ``recovery_app`` (a name ``apps.open`` accepts),
``recovery_snapshot()`` (a JSON-serialisable dict) and ``recovery_restore(snap)``.
While such a window is ``modified`` its snapshot is written, at most once per
``INTERVAL`` seconds and only when it changed, to its own crash-safe record under
``state/document-recovery/``.  A save, a new or opened document (which clear
``modified``) or a deliberate close removes the record; a window closed because
it failed, or a desktop that dies, leaves it in place.  The next desktop start
offers every remaining record for restore, and names any it cannot restore.
"""

import json
import os
import time
import uuid

import durable_state
import storage

INTERVAL = 1.0                      # seconds between checkpoint passes
MAX_DOCUMENT = 8 * 1024 * 1024      # larger snapshots keep only a name-only marker
_DIRNAME = "document-recovery"
_MAX_PAYLOAD = 16 * 1024 * 1024


def _dir():
    path = storage.state_dir(_DIRNAME)
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def _store(token):
    return durable_state.JsonState(os.path.join(_DIRNAME, token),
                                   max_payload=_MAX_PAYLOAD)


def _start_ticks(pid):
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(") ", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _boot_id():
    try:
        with open("/proc/sys/kernel/random/boot_id") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _owner():
    pid = os.getpid()
    return {"pid": pid, "start": _start_ticks(pid), "boot": _boot_id()}


def _owned_by_another_live_desktop(record):
    """A second running desktop must neither offer nor discard the documents
    another live desktop is still editing."""
    owner = record.get("owner")
    if not isinstance(owner, dict) or owner.get("pid") == os.getpid():
        return False
    pid = owner.get("pid")
    if not isinstance(pid, int) or owner.get("boot") != _boot_id() or owner.get("boot") is None:
        return False
    start = _start_ticks(pid)
    return start is not None and start == owner.get("start")


def _token(win):
    token = getattr(win, "_recovery_token", None)
    if token is None:
        token = win._recovery_token = uuid.uuid4().hex
    return token


def _recoverable(win):
    return callable(getattr(win, "recovery_snapshot", None)) and getattr(
        win, "recovery_app", None)


def _name(win):
    path = getattr(win, "path", None)
    return os.path.basename(path) if path else "Untitled"


def write(win):
    """Checkpoint ``win`` now if its snapshot changed. Returns True when a record
    for its current unsaved state exists afterwards."""
    if not _recoverable(win) or not getattr(win, "modified", False):
        return False
    try:
        snap = win.recovery_snapshot()
        body = json.dumps(snap, sort_keys=True, ensure_ascii=True)
    except Exception:
        return False
    if body == getattr(win, "_recovery_written", None):
        return True
    record = {"app": win.recovery_app, "name": _name(win),
              "path": getattr(win, "path", None), "saved_at": time.time(),
              "owner": _owner()}
    if len(body) > MAX_DOCUMENT:
        record["too_large"] = True
    else:
        record["snapshot"] = snap
    _dir()
    try:
        with _store(_token(win)) as store:
            store.save_dict(record)
    except (durable_state.StateError, OSError):
        return False
    win._recovery_written = body
    return not record.get("too_large", False)


def clear(win):
    """Remove ``win``'s checkpoint (saved, replaced or deliberately discarded)."""
    token = getattr(win, "_recovery_token", None)
    win._recovery_written = None
    if token is None:
        return
    for name in os.listdir(_dir()):
        if name == token or name.startswith(token + "."):
            try:
                os.unlink(os.path.join(_dir(), name))
            except OSError:
                pass


def tick(desk, now):
    """Desk tick hook: checkpoint modified windows, drop records of clean ones."""
    # A clock that steps backwards must not stop checkpointing for good.
    if 0 <= now - getattr(desk, "_recovery_last", 0.0) < INTERVAL:
        return
    desk._recovery_last = now
    for win in list(desk.wm.windows):
        if not _recoverable(win):
            continue
        if getattr(win, "modified", False):
            write(win)
        elif getattr(win, "_recovery_written", None) is not None:
            clear(win)


def closed(win):
    """A window closed on purpose: its unsaved state was saved or discarded."""
    if _recoverable(win) and not getattr(win, "_recovery_fault", False):
        clear(win)


def pending():
    """[(token, record)] for every checkpoint left by an earlier failure."""
    out = []
    try:
        names = sorted(os.listdir(_dir()))
    except OSError:
        return out
    for token in names:
        if "." in token:             # the store's temporary/lock siblings
            continue
        with _store(token) as store:
            record = store.load_dict()
        if record.get("app") and not _owned_by_another_live_desktop(record):
            out.append((token, record))
    return out


def _forget(token):
    for name in os.listdir(_dir()):
        if name == token or name.startswith(token + "."):
            try:
                os.unlink(os.path.join(_dir(), name))
            except OSError:
                pass


def _saved_since(record):
    """Whether the document's file was saved after this checkpoint was taken."""
    path, saved = record.get("path"), record.get("saved_at")
    try:
        return bool(path) and isinstance(saved, (int, float)) and \
            os.path.getmtime(path) > saved
    except OSError:
        return False


def restore(desk, token, record):
    """Reopen one checkpoint as an unsaved document; True on success.

    If the file was saved since, the checkpoint reopens as an untitled copy, so
    saving it cannot silently replace the newer work."""
    import apps
    if record.get("too_large") or "snapshot" not in record:
        return False
    if _saved_since(record):
        record = dict(record, path=None)
    before = list(desk.wm.windows)
    apps.open(desk, record["app"], None)
    new = [w for w in desk.wm.windows if w not in before]
    if not new or not callable(getattr(new[-1], "recovery_restore", None)):
        return False
    win = new[-1]
    win.recovery_restore(record)
    # The reopened window owns the record now: write it under its own token
    # before forgetting the old one, so a second failure still keeps the text.
    write(win)
    _forget(token)
    return True


_APP_LABELS = {"notepad": "Notepad", "wordpad": "WordPad", "paint": "Paint"}


def app_label(app):
    """The program's own name as the user sees it in its title bar."""
    return _APP_LABELS.get(app, app.title())


def describe(record):
    """One line naming a pending document, when it was unsaved, and any risk."""
    label = f"{record.get('name', 'Untitled')} ({app_label(record['app'])})"
    saved = record.get("saved_at")
    if isinstance(saved, (int, float)):
        label += time.strftime(", unsaved at %H:%M", time.localtime(saved))
    if _saved_since(record):
        label += " - the file was saved since; it reopens as an untitled copy"
    if record.get("too_large"):
        label += " - too large to keep, changes lost"
    return label


def offer(desk, items=None, reason=None):
    """Ask the user about pending checkpoints; nothing happens without an answer."""
    import wm
    items = pending() if items is None else items
    if not items:
        return
    names = ["  " + describe(record) for _token_, record in items]
    restorable = [(t, r) for t, r in items if not r.get("too_large")]
    lost_only = not restorable
    text = (reason or "These documents had unsaved changes when they "
            "were last open:") + "\n\n" + "\n".join(names)
    if lost_only:
        wm.msgbox(desk, "Document Recovery", text, icon="warn",
                  cb=lambda _ans: [_forget(t) for t, _r in items])
        return

    def answer(ans):
        if ans == "Restore":
            for token, record in items:
                if record.get("too_large"):
                    _forget(token)
                elif not restore(desk, token, record):
                    pass             # stays pending for the next start
        elif ans == "Discard":
            for token, _record in items:
                _forget(token)
    wm.msgbox(desk, "Document Recovery", text + "\n\nRestore them now?",
              icon="warn", buttons=("Restore", "Later", "Discard"), cb=answer)
