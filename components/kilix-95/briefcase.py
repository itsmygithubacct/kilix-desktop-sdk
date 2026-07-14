"""Non-destructive two-folder synchronization for My Briefcase."""

import hashlib
import json
import os
import shutil

import storage


STATE = storage.config_dir("briefcase.json")
MAX_FILES = 5000


def _signature(path):
    stat = os.stat(path, follow_symlinks=False)
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 16), b""):
            digest.update(chunk)
    return {"size": stat.st_size, "sha256": digest.hexdigest()}


def _scan(root):
    root = os.path.abspath(os.path.expanduser(root))
    out = {}
    if not os.path.isdir(root):
        return out
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(current, d))]
        for name in files:
            path = os.path.join(current, name)
            if os.path.islink(path):
                continue
            rel = os.path.relpath(path, root)
            out[rel] = _signature(path)
            if len(out) >= MAX_FILES:
                raise RuntimeError(f"Briefcase is limited to {MAX_FILES} files.")
    return out


def _load():
    try:
        with open(STATE, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(value):
    os.makedirs(os.path.dirname(STATE), mode=0o700, exist_ok=True)
    temp = STATE + ".tmp"
    with open(temp, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temp, STATE)


def validate_roots(left, right):
    left = os.path.abspath(os.path.expanduser(left))
    right = os.path.abspath(os.path.expanduser(right))
    if left == right:
        raise ValueError("Choose two different folders.")
    common = os.path.commonpath([left, right])
    if common in (left, right):
        raise ValueError("One Briefcase folder cannot contain the other.")
    os.makedirs(left, exist_ok=True)
    os.makedirs(right, exist_ok=True)
    return left, right


def plan(left, right):
    left, right = validate_roots(left, right)
    lmap, rmap = _scan(left), _scan(right)
    prior = _load()
    if prior.get("left") != left or prior.get("right") != right:
        previous = {}
    else:
        previous = prior.get("files", {})
    actions = []
    for rel in sorted(set(lmap) | set(rmap), key=str.lower):
        lsig, rsig, old = lmap.get(rel), rmap.get(rel), previous.get(rel)
        if lsig == rsig:
            action = "current"
        elif lsig is None:
            action = "right-to-left"
        elif rsig is None:
            action = "left-to-right"
        elif old == lsig and old != rsig:
            action = "right-to-left"
        elif old == rsig and old != lsig:
            action = "left-to-right"
        else:
            action = "conflict"
        actions.append({"path": rel, "action": action,
                        "left": lsig, "right": rsig})
    return left, right, actions


def synchronize(left, right):
    left, right, actions = plan(left, right)
    copied, conflicts = [], []
    for item in actions:
        rel, action = item["path"], item["action"]
        if action == "current":
            continue
        if action == "conflict":
            conflicts.append(rel)
            continue
        source_root, target_root = ((left, right) if action == "left-to-right"
                                    else (right, left))
        source, target = os.path.join(source_root, rel), os.path.join(target_root, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        copied.append(rel)
    lmap, rmap = _scan(left), _scan(right)
    common = {rel: sig for rel, sig in lmap.items() if rmap.get(rel) == sig}
    _save({"left": left, "right": right, "files": common})
    return {"copied": copied, "conflicts": conflicts,
            "actions": actions}
