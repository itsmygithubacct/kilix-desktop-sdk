"""Canonical writable storage for the standalone Kilix 95 project."""

import os


def storage_home():
    base = os.environ.get("GPU_TERMINAL_HOME") or os.path.expanduser(
        "~/.local/gpu_terminal")
    value = os.environ.get("KILIX95_STORAGE_HOME") or os.path.join(
        base, "kilix-95")
    return os.path.abspath(os.path.expanduser(value))


def _owned(env_name, leaf):
    value = os.environ.get(env_name) or os.path.join(storage_home(), leaf)
    return os.path.abspath(os.path.expanduser(value))


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
    """Create a directory and make the final directory user-private."""
    path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(path, mode=0o700, exist_ok=True)
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
