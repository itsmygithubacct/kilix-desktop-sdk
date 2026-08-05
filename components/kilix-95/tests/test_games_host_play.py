"""games.py delegates install-and-boot to the host's `kilix games play`.

The host verb is the one install-and-boot implementation (backed by the same
pinned content catalog), so a Start-menu launch and every other desktop's
launch stay on one build. Delegation is probed, never assumed: on a host that
predates the verb this checkout still boots games by itself. No network:
stub launchers only.
"""
import os
import stat
import sys
import tempfile

import harness as H       # noqa: F401  (sets up sys.path for `import games`)
import games

tmp = tempfile.mkdtemp(prefix="games-host-play-")


def fake_kilix(games_help_stdout, rc=0):
    """A stub host launcher whose `games help` prints what we say."""
    home = tempfile.mkdtemp(prefix="kilix-home-", dir=tmp)
    path = os.path.join(home, "kilix")
    with open(path, "w") as f:
        f.write("#!/bin/sh\n"
                "if [ \"$1\" = games ] && [ \"$2\" = help ]; then\n"
                f"  printf '%s\\n' \"{games_help_stdout}\"\n"
                f"  exit {rc}\n"
                "fi\n"
                "exit 0\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return home


# A host advertising the verb is delegated to, with the exact play argv.
games.KILIX_HOME = fake_kilix("usage: kilix games play GAME [--setup-only]")
argv = games.host_play_argv("chess-bash")
assert argv is not None, "a host advertising play must be used"
assert argv[1:] == ["games", "play", "chess-bash"], argv
assert argv[0] == os.path.join(games.KILIX_HOME, "kilix"), argv

# --setup-only rides along, so a pre-install stays a pre-install.
argv = games.host_play_argv("chess-bash", setup_only=True)
assert argv[-1] == "--setup-only", argv

# A host that predates the verb is left alone: its help has no play action.
games.KILIX_HOME = fake_kilix(
    "usage: kilix games [list|settings|enable GAME...|disable GAME...]")
assert games.host_play_argv("chess-bash") is None, \
    "an old host must fall back to the local installer"

# A missing or non-executable host is not an error, just no delegation.
games.KILIX_HOME = os.path.join(tmp, "nowhere")
assert games.host_play_argv("chess-bash") is None

# A probe that fails outright degrades the same way.
games.KILIX_HOME = fake_kilix("broken", rc=3)
assert games.host_play_argv("chess-bash") is None

# The host's own install report answers "is it ready" once delegation owns
# installs — otherwise a game the host installed would prompt forever.
home = tempfile.mkdtemp(prefix="kilix-home-", dir=tmp)
path = os.path.join(home, "kilix")
with open(path, "w") as f:
    f.write("#!/bin/sh\n"
            "if [ \"$1\" = install ] && [ \"$2\" = --json ]; then\n"
            "  printf '%s' '[{\"id\": \"chess-bash\", \"installed\": true},"
            " {\"id\": \"joustix\", \"installed\": false}]'\n"
            "  exit 0\n"
            "fi\nexit 0\n")
os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
games.KILIX_HOME = home
assert games.host_game_ready("chess-bash") is True
assert games.host_game_ready("joustix") is False
assert games.host_game_ready("doom") is False
games.KILIX_HOME = os.path.join(tmp, "nowhere")
assert games.host_game_ready("chess-bash") is False

# A working local install is never delegated away: offline boxes and
# pre-verb installs keep booting exactly what they already have.
games.KILIX_HOME = fake_kilix("usage: kilix games play GAME [--setup-only]")
local_boots = []
real_game_ready = games.game_ready
real_ensure = games.ensure
real_launch_native = games._launch_native
games.game_ready = lambda g, cp=None: "/somewhere/chess-bash"
games.ensure = lambda g, report=print: "/somewhere/chess-bash"
games._launch_native = lambda exe: local_boots.append(exe)
sys.argv = ["games.py", "chess-bash"]
games.main()
assert local_boots == ["/somewhere/chess-bash"], local_boots
games.game_ready = real_game_ready
games.ensure = real_ensure
games._launch_native = real_launch_native

# main() execs the host argv when it is offered — before any local ensure.
games.KILIX_HOME = fake_kilix("usage: kilix games play GAME [--setup-only]")
executed = []


def fake_execv(path, argv):
    executed.append((path, list(argv)))
    raise SystemExit(0)          # stand in for the process being replaced


def must_not_install(game, report=print):
    raise AssertionError("local ensure must not run when the host plays")


games.ensure = must_not_install
os.execv, real_execv = fake_execv, os.execv
sys.argv = ["games.py", "chess-bash"]
try:
    games.main()
    assert False, "main() should have handed off"
except SystemExit as e:
    assert e.code == 0, e.code
finally:
    os.execv = real_execv
assert executed and executed[0][1][1:] == ["games", "play", "chess-bash"], \
    executed

print("ok")
