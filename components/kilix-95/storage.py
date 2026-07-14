"""Canonical writable storage for the standalone Kilix 95 project."""

import os
import stat


def _normalized(path):
    return os.path.abspath(os.path.expanduser(path))


def storage_home():
    base = os.environ.get("GPU_TERMINAL_HOME") or os.path.expanduser(
        "~/.local/gpu_terminal")
    value = os.environ.get("KILIX95_STORAGE_HOME") or os.path.join(
        base, "kilix-95")
    return _normalized(value)


def _private_storage_home():
    """Create/repair the dedicated Kilix 95 root without broad chmods."""
    path = storage_home()
    base = _normalized(os.environ.get("GPU_TERMINAL_HOME") or
                       "~/.local/gpu_terminal")
    home = _normalized("~")
    if path in (os.path.abspath(os.sep), home, base):
        raise ValueError(
            "KILIX95_STORAGE_HOME must be a dedicated component directory")
    return private_dir(path)


def _is_within(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _owned(env_name, leaf):
    root = _private_storage_home()
    value = os.environ.get(env_name) or os.path.join(root, leaf)
    path = _normalized(value)
    # Paths inside the dedicated component root are Kilix 95-owned and must
    # stay private.  An explicit out-of-tree category override remains
    # authoritative; callers that need a private leaf (session/AMP) secure
    # that leaf without chmodding an operator-managed parent directory.
    return private_dir(path) if _is_within(path, root) else path


def config_dir(*parts):
    return os.path.join(_owned("KILIX95_CONFIG_HOME", "config"), *parts)


def state_dir(*parts):
    return os.path.join(_owned("KILIX95_STATE_HOME", "state"), *parts)


def cache_dir(*parts):
    return os.path.join(_owned("KILIX95_CACHE_HOME", "cache"), *parts)


def data_dir(*parts):
    return os.path.join(_owned("KILIX95_DATA_HOME", "data"), *parts)


def session_dir(*parts):
    return os.path.join(_owned("KILIX95_SESSION_HOME", "session"), *parts)


def private_dir(path):
    """Create an app-owned directory and make it user-private.

    Refuse a final symlink or foreign-owned directory instead of following it
    with chmod.  This helper deliberately changes only the directory boundary,
    never its descendants.
    """
    path = _normalized(path)
    os.makedirs(path, mode=0o700, exist_ok=True)
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise OSError(f"private storage path is not a real directory: {path}")
    if info.st_uid != os.geteuid():
        raise PermissionError(f"private storage path is not owned by this user: {path}")
    os.chmod(path, 0o700)
    return path


def private_session_dir(*parts):
    """Create and return a user-private runtime/session directory.

    ``os.makedirs(path, mode=...)`` applies its mode only to the final path,
    so create and tighten the session root explicitly before any child.  This
    keeps installer output and raw framebuffer files unreadable to other local
    users even with a conventional 022 umask.
    """
    root = private_dir(session_dir())
    path = os.path.join(root, *parts)
    if parts:
        private_dir(path)
    return path
