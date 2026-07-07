"""Kilix host discovery for the external Kilix 95 checkout."""
import os
import sys


def find_kilix_home():
    """Return the Kilix host checkout used for launch/config helpers."""
    env = os.environ.get("KILIX_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))

    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "kilix"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "kilix")),
    ]
    for cand in candidates:
        if os.path.exists(os.path.join(cand, "kilix")):
            return cand
    return os.path.join(home, "kilix")


def add_kilix_config_path():
    """Put Kilix host config helpers on sys.path and return KILIX_HOME."""
    kilix_home = find_kilix_home()
    config = os.path.join(kilix_home, "config")
    if config not in sys.path:
        sys.path.insert(0, config)
    return kilix_home
