"""Menu launches must not lean on the terminal's PATH (0.1.7 review, entry 8).

The terminal spawns a tab's child from its own environment, whose PATH does
not reliably include ~/.local/bin. A bare command name it cannot resolve dies
before its first prompt, and the tab is a corpse whose only trace is a resize
warning. So `Shell._tab` resolves argv[0] in the desktop's own environment —
PATH, then ~/.local/bin — and a name found nowhere fails with a message box
instead of a dead tab.
"""
import os
import tempfile
from unittest.mock import patch

import harness as H
import shell as shell_mod
import wm


def _rc_shell(d, spawned):
    d.shell._kitten = lambda: "/usr/bin/true"
    d.shell._popen = lambda argv, cwd=None: spawned.append(list(argv)) or True
    return d.shell


def test_bare_names_resolve_against_the_desktop_environment():
    d = H.make_desk()
    spawned = []
    sh = _rc_shell(d, spawned)
    with patch.dict(os.environ, {"KITTY_LISTEN_ON": "unix:/tmp/kilix-test"}), \
            patch.object(shell_mod.shutil, "which",
                         lambda name: f"/resolved/{name}"):
        assert sh._tab(["kilix-rollout-resume", "status"], "Coding Agents")
    assert len(spawned) == 1
    argv = spawned[0]
    child = argv[argv.index("--") + 1:]
    assert child == ["/resolved/kilix-rollout-resume", "status"]


def test_local_bin_is_reached_when_path_misses_it():
    d = H.make_desk()
    spawned = []
    sh = _rc_shell(d, spawned)
    with tempfile.TemporaryDirectory() as home:
        local = os.path.join(home, ".local", "bin")
        os.makedirs(local)
        tool = os.path.join(local, "kilix-rollout-resume")
        with open(tool, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n")
        os.chmod(tool, 0o755)
        with patch.dict(os.environ, {
                "KITTY_LISTEN_ON": "unix:/tmp/kilix-test", "HOME": home}), \
                patch.object(shell_mod.shutil, "which", lambda name: None):
            assert sh._tab(["kilix-rollout-resume"], "Coding Agents")
    child = spawned[0][spawned[0].index("--") + 1:]
    assert child == [tool]


def test_a_missing_tool_fails_with_words_not_a_dead_tab():
    d = H.make_desk()
    spawned = []
    sh = _rc_shell(d, spawned)
    boxes = []
    with tempfile.TemporaryDirectory() as home, \
            patch.dict(os.environ, {
                "KITTY_LISTEN_ON": "unix:/tmp/kilix-test", "HOME": home}), \
            patch.object(shell_mod.shutil, "which", lambda name: None), \
            patch.object(wm, "msgbox",
                         lambda desk, title, text, **kw: boxes.append(
                             (title, text))):
        assert not sh._tab(["no-such-tool-qq"], "Coding Agents")
    assert spawned == []
    assert len(boxes) == 1
    assert "no-such-tool-qq" in boxes[0][1]
    assert "could not be found" in boxes[0][1]


def test_paths_are_passed_through_when_executable():
    d = H.make_desk()
    spawned = []
    sh = _rc_shell(d, spawned)
    with patch.dict(os.environ, {"KITTY_LISTEN_ON": "unix:/tmp/kilix-test"}):
        assert sh._tab(["/bin/sh", "-c", "true"], "Shell")
    child = spawned[0][spawned[0].index("--") + 1:]
    assert child == ["/bin/sh", "-c", "true"]


test_bare_names_resolve_against_the_desktop_environment()
test_local_bin_is_reached_when_path_misses_it()
test_a_missing_tool_fails_with_words_not_a_dead_tab()
test_paths_are_passed_through_when_executable()
print("ok")
