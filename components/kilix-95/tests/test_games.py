"""games.py: a broken games.conf must not crash a *_ready() check (F33),
and an installer error that isn't RuntimeError/OSError must be shown, not
leaked out of main() with the tab (F36). No network: conf files + stubs only."""
import builtins
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile

import harness as H       # noqa: F401  (sets up sys.path for `import games`)
import games

tmp = tempfile.mkdtemp(prefix="games-test-")
games.CONF = os.path.join(tmp, "games.conf")
games.GAMES_DIR = os.path.join(tmp, "games")   # isolate the vendored-binary scan


def write(text):
    with open(games.CONF, "w") as f:
        f.write(text)


# F33a: a syntactically bad conf (missing '=') reads as empty, not a crash.
# Pre-fix load() let configparser.ParsingError escape doom_ready().
write("[doom]\ndosbox /usr/bin/dosbox\n")
assert games.doom_ready() is None
assert games.bashed_ready() is None
cp = games.load()
assert not cp.has_section("doom"), "malformed conf should load as empty"

# F33b: a '%' in a stored path is literal, not an interpolation token.
# Pre-fix cp.get() raised InterpolationSyntaxError from BasicInterpolation.
write("[doom]\ndosbox = /opt/games/%stuff/dosbox\ndir = /nonexistent\n")
assert games.doom_ready() is None
cp = games.load()
assert cp.get("doom", "dosbox") == "/opt/games/%stuff/dosbox"

# a well-formed conf still round-trips
write("[doom]\ndosbox = /nonexistent/dosbox\ndir = /nonexistent\n")
cp = games.load()
assert cp.get("doom", "dir") == "/nonexistent"
assert games.doom_ready() is None            # path doesn't exist -> not ready


# DOSBox is a first-class Games entry, launchable on its own; game_ready
# dispatches to dosbox_ready, which finds a dosbox on $PATH without installing.
assert "dosbox" in games.GAMES and games.GAMES["dosbox"]["icon"] == "dosbox"
import shutil as _sh
_which = _sh.which
_sh.which = lambda n: "/usr/bin/dosbox" if n == "dosbox" else None
try:
    write("")                                    # empty conf, no [dosbox]
    assert games.dosbox_ready(games.load()) == "/usr/bin/dosbox"
    assert games.game_ready("dosbox") == "/usr/bin/dosbox"
    _sh.which = lambda n: None                    # nothing on PATH, none vendored
    assert games.dosbox_ready(games.load()) is None
    assert games.game_ready("nonesuch") is None
finally:
    _sh.which = _which

# Terminal Lander is a first-class Games entry, built from source like Bashed
# Earth; game_ready dispatches to lander_ready (None until it's cloned+built).
assert "terminal-lander" in games.GAMES
assert games.GAMES["terminal-lander"]["icon"] == "lander"
write("")                                        # empty conf, no [terminal-lander]
assert games.lander_ready(games.load()) is None
assert games.game_ready("terminal-lander") is None

# Joustix is installed from a pinned source checkout and launches natively in
# its Kilix tab, just like the other Kitty-graphics games.
assert "joustix" in games.GAMES
assert games.GAMES["joustix"]["icon"] == "joustix"
write("")                                        # empty conf, no [joustix]
assert games.joustix_ready(games.load()) is None
assert games.game_ready("joustix") is None

# Kitty Brokeout is a first-class Games entry, built from source the same way.
assert "kitty-brokeout" in games.GAMES
assert games.GAMES["kitty-brokeout"]["icon"] == "brokeout"
write("")                                        # empty conf, no [kitty-brokeout]
assert games.brokeout_ready(games.load()) is None
assert games.game_ready("kitty-brokeout") is None


# Tarball extraction must reject members that escape the destination. Python
# 3.11's tarfile.extractall() does not filter these by default.
root = tempfile.mkdtemp(prefix="games-tar-test-")
bad_tar = os.path.join(root, "bad.tar")
out_dir = os.path.join(root, "out")
os.mkdir(out_dir)
with tarfile.open(bad_tar, "w") as t:
    data = b"escape"
    ti = tarfile.TarInfo("../escape.txt")
    ti.size = len(data)
    t.addfile(ti, io.BytesIO(data))
with tarfile.open(bad_tar, "r") as t:
    try:
        games._safe_extract_tar(t, out_dir)
        assert False, "unsafe tar member was extracted"
    except RuntimeError as e:
        assert "unsafe path" in str(e)
assert not os.path.exists(os.path.join(root, "escape.txt"))

# ZIP extraction has the same traversal guarantee as tar extraction.
bad_zip = os.path.join(root, "bad.zip")
with zipfile.ZipFile(bad_zip, "w") as archive:
    archive.writestr("../zip-escape.txt", b"escape")
with zipfile.ZipFile(bad_zip) as archive:
    try:
        games._safe_extract_zip(archive, out_dir)
        assert False, "unsafe ZIP member was extracted"
    except RuntimeError as error:
        assert "unsafe path" in str(error)
assert not os.path.exists(os.path.join(root, "zip-escape.txt"))

for ref in (games.BASHED_REF, games.JOUSTIX_REF, games.LANDER_REF,
            games.BROKEOUT_REF,
            games.AMP_REF):
    assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref)


# Managed native-game caches are installed atomically and remain pinned on
# every ready check. A different configured directory is explicitly trusted.
source_repo = os.path.join(root, "native-source")
os.mkdir(source_repo)
source_binary = os.path.join(source_repo, "bashed-earth")
with open(source_binary, "w") as f:
    f.write("#!/bin/sh\nexit 0\n")
os.chmod(source_binary, 0o755)
for command in (
        ["git", "init", "--quiet", source_repo],
        ["git", "-C", source_repo, "config", "user.name", "Kilix Test"],
        ["git", "-C", source_repo, "config", "user.email", "test@example.invalid"],
        ["git", "-C", source_repo, "add", "bashed-earth"],
        ["git", "-C", source_repo, "commit", "--quiet", "-m", "fixture"]):
    subprocess.run(command, check=True, capture_output=True, text=True)
pinned_ref = subprocess.run(
    ["git", "-C", source_repo, "rev-parse", "HEAD"], check=True,
    capture_output=True, text=True).stdout.strip()

managed = os.path.join(games.GAMES_DIR, "bashed-earth")
old_repo, old_ref = games.BASHED_REPO, games.BASHED_REF
games.BASHED_REPO, games.BASHED_REF = source_repo, pinned_ref
try:
    try:
        games._clone_and_make(
            source_repo, "0" * 40, managed, "bashed-earth", "fixture deps",
            lambda _message: None)
        assert False, "a missing ref unexpectedly installed"
    except RuntimeError as error:
        assert "source setup failed" in str(error)
    assert not os.path.exists(managed), "failed fetch left a partial cache"
    assert not any(name.startswith(".bashed-earth.install-")
                   for name in os.listdir(games.GAMES_DIR)), \
        "failed fetch left its staging directory"

    executable = games._clone_and_make(
        source_repo, pinned_ref, managed, "bashed-earth", "fixture deps",
        lambda _message: None)
    assert executable == os.path.join(managed, "bashed-earth")
    write(f"[bashed-earth]\ndir = {managed}\n")
    cp = games.load()
    assert games.bashed_ready(cp) == executable

    subprocess.run(
        ["git", "-C", managed, "remote", "set-url", "origin",
         source_repo + "-wrong"], check=True)
    assert games.bashed_ready(cp) is None, "wrong origin was trusted"
    subprocess.run(
        ["git", "-C", managed, "remote", "set-url", "origin", source_repo],
        check=True)

    with open(executable, "a") as f:
        f.write("# tracked modification\n")
    assert games.bashed_ready(cp) is None, "dirty managed source was trusted"
    subprocess.run(
        ["git", "-C", managed, "checkout", "--", "bashed-earth"],
        check=True, capture_output=True, text=True)

    subprocess.run(
        ["git", "-C", managed, "config", "user.name", "Kilix Test"],
        check=True)
    subprocess.run(
        ["git", "-C", managed, "config", "user.email", "test@example.invalid"],
        check=True)
    subprocess.run(
        ["git", "-C", managed, "commit", "--quiet", "--allow-empty",
         "-m", "wrong head"], check=True)
    assert games.bashed_ready(cp) is None, "unpinned managed HEAD was trusted"
    subprocess.run(
        ["git", "-C", managed, "checkout", "--quiet", "--detach", pinned_ref],
        check=True)

    external = os.path.join(root, "user-managed")
    os.mkdir(external)
    external_exe = os.path.join(external, "bashed-earth")
    with open(external_exe, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(external_exe, 0o755)
    write(f"[bashed-earth]\ndir = {external}\n")
    assert games.bashed_ready(games.load()) == external_exe, \
        "explicit user-managed executable was rejected"
finally:
    games.BASHED_REPO, games.BASHED_REF = old_repo, old_ref


# Downloads must fail closed when the pinned checksum does not match.
fetch_dir = tempfile.mkdtemp(prefix="games-fetch-test-")
src = os.path.join(fetch_dir, "src.bin")
dst = os.path.join(fetch_dir, "dst.bin")
with open(src, "wb") as f:
    f.write(b"not the expected artifact")
try:
    games._fetch("file://" + src, dst, lambda _msg: None,
                 sha256="0" * 64)
    assert False, "checksum mismatch was accepted"
except RuntimeError as e:
    assert "sha256 mismatch" in str(e)
assert not os.path.exists(dst), "bad artifact must be removed"


# F36: main() catches installer errors that don't subclass RuntimeError/OSError
# (BadZipFile from a mirror serving HTML, TarError, configparser.Error) and
# exits cleanly with the [Enter to close] path instead of dumping a traceback
# into a tab that then vanishes.
def boom(game, report=print):
    raise zipfile.BadZipFile("mirror returned an HTML error page")


games.ensure = boom
builtins.input = lambda *a: (_ for _ in ()).throw(EOFError())
sys.argv = ["games.py", "doom"]
try:
    games.main()
    assert False, "main() should have exited"
except SystemExit as e:
    assert e.code == 1, e.code
except zipfile.BadZipFile:
    assert False, "BadZipFile leaked past main()'s handler"

print("ok")
