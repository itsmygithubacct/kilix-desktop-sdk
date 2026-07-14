"""Kilix host bootstrap for the external Kilix 95 checkout."""
import os
import sys


def _discover_kilix_home():
    env = os.environ.get("KILIX_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))

    source_home = os.environ.get("GPU_TERMINAL_SOURCE_HOME") or \
        os.path.expanduser("~/gpu_terminal")
    source_home = os.path.abspath(os.path.expanduser(source_home))
    candidates = [
        os.path.join(source_home, "kilix"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "kilix")),
    ]
    for cand in candidates:
        if os.path.exists(os.path.join(cand, "kilix")):
            return cand
    return os.path.join(source_home, "kilix")


def _add_host_config_path():
    kilix_home = _discover_kilix_home()
    config = os.path.join(kilix_home, "config")
    if config not in sys.path:
        sys.path.insert(0, config)
    return kilix_home


def find_kilix_home():
    """Return the Kilix host checkout used for launch/config helpers."""
    fallback = _add_host_config_path()
    try:
        from kilix_sdk import paths
    except ImportError:
        return fallback
    return paths.kilix_home()


def add_kilix_config_path():
    """Put the Kilix host SDK on sys.path and return KILIX_HOME."""
    return find_kilix_home()
