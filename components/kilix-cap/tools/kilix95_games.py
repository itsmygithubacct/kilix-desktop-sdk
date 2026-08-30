#!/usr/bin/env python3
"""List and launch the games exposed by a local Kilix 95 checkout.

The list protocol is intentionally tiny and line-oriented so the C host can
consume it without a JSON dependency.  Kilix 95's module is imported with a
temporary storage root: discovering its catalog never creates or modifies the
user's real Kilix 95 configuration.  Registry games are launched through this
helper as well so native projects whose Makefile includes a shared library
before declaring ``all`` are built with an explicit ``make all`` goal.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,62}\Z")
BUILTINS = (
    ("mines", "Minesweeper", "mines"),
    ("sol", "Solitaire", "cards"),
)
ICON_SIDE = 16
ICON_PIXELS = ICON_SIDE * ICON_SIDE
ICON_DIGITS = "0123456789abcdef"
# Index zero is transparent. The remaining entries are Kilix 95's exact
# original 16-color icon palette, in the order used by icons.py.
ICON_PALETTE = (
    (0, 0, 0),
    (255, 255, 255),
    (128, 128, 128),
    (192, 192, 192),
    (255, 0, 0),
    (128, 0, 0),
    (255, 255, 0),
    (128, 128, 0),
    (0, 0, 255),
    (0, 0, 128),
    (0, 255, 255),
    (0, 128, 128),
    (0, 255, 0),
    (0, 128, 0),
)


def clean_field(value: object, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError("invalid Kilix 95 catalog field")
    if any(ord(char) < 32 or char in "\t\r\n" for char in value):
        raise ValueError("control character in Kilix 95 catalog field")
    return value


def clean_id(value: object) -> str:
    value = clean_field(value, 63)
    if ID_RE.fullmatch(value) is None:
        raise ValueError(f"invalid Kilix 95 game id: {value!r}")
    return value


def encode_icon(icon_module: object, name: object) -> str:
    """Encode one exact Kilix 95 16x16 RGBA icon as palette nibbles."""
    icon_name = clean_id(name)
    image = icon_module.get(icon_name, ICON_SIDE).convert("RGBA")
    if image.size != (ICON_SIDE, ICON_SIDE):
        raise ValueError("Kilix 95 icon has an invalid size")
    palette = {rgb: index + 1 for index, rgb in enumerate(ICON_PALETTE)}
    encoded: list[str] = []
    visible = False
    for red, green, blue, alpha in image.getdata():
        if alpha == 0:
            encoded.append("0")
            continue
        if alpha != 255 or (red, green, blue) not in palette:
            raise ValueError(f"Kilix 95 icon {icon_name!r} left its palette")
        visible = True
        encoded.append(ICON_DIGITS[palette[(red, green, blue)]])
    if not visible or len(encoded) != ICON_PIXELS:
        raise ValueError(f"Kilix 95 icon {icon_name!r} is empty")
    return "".join(encoded)


def load_catalog(root: Path) -> tuple[list[Path], list[tuple[str, str, str, str]]]:
    root = root.expanduser().resolve(strict=True)
    games_path = root / "games.py"
    if not games_path.is_file():
        raise FileNotFoundError(f"Kilix 95 games.py not found under {root}")

    old_path = list(sys.path)
    old_cwd = Path.cwd()
    prior_storage = os.environ.get("KILIX95_STORAGE_HOME")
    try:
        with tempfile.TemporaryDirectory(prefix="kilix-cap-catalog-") as tmp:
            os.environ["KILIX95_STORAGE_HOME"] = tmp
            sys.path.insert(0, str(root))
            os.chdir(root)
            import games  # type: ignore[import-not-found]
            import icons as kilix95_icons  # type: ignore[import-not-found]

            registry = games.GAMES
            if not isinstance(registry, dict):
                raise TypeError("Kilix 95 GAMES is not a mapping")
            rows = [
                ("builtin", key, label, encode_icon(kilix95_icons, icon))
                for key, label, icon in BUILTINS
            ]
            for key, metadata in registry.items():
                if not isinstance(metadata, dict):
                    raise TypeError("Kilix 95 game metadata is not a mapping")
                rows.append((
                    "game",
                    clean_id(key),
                    clean_field(metadata.get("label"), 95),
                    encode_icon(kilix95_icons, metadata.get("icon")),
                ))

            watches = [games_path.resolve()]
            icons_path = Path(kilix95_icons.__file__).resolve()
            if icons_path.is_file():
                watches.append(icons_path)
            shared = sys.modules.get("kilix_content")
            shared_file = getattr(shared, "__file__", None)
            if shared_file:
                catalog = Path(shared_file).resolve().parent / "catalog" / "plebian.json"
                if catalog.is_file():
                    watches.append(catalog)
            return watches, rows
    finally:
        sys.path[:] = old_path
        os.chdir(old_cwd)
        if prior_storage is None:
            os.environ.pop("KILIX95_STORAGE_HOME", None)
        else:
            os.environ["KILIX95_STORAGE_HOME"] = prior_storage


def emit(watches: list[Path], rows: list[tuple[str, str, str, str]]) -> None:
    for path in watches:
        text = clean_field(str(path), 4095)
        if not Path(text).is_absolute():
            raise ValueError("watch path is not absolute")
        print(f"watch\t{text}")
    for kind, game_id, label, icon in rows:
        if kind not in ("game", "builtin"):
            raise ValueError("invalid game kind")
        if (len(icon) != ICON_PIXELS or any(ch not in ICON_DIGITS[:15]
                                           for ch in icon)
                or not any(ch != "0" for ch in icon)):
            raise ValueError("invalid Kilix 95 icon payload")
        print(f"{kind}\t{clean_id(game_id)}\t{clean_field(label, 95)}\t{icon}")


def run_builtin(root: Path, app: str) -> None:
    if app not in {game_id for game_id, _label, _icon in BUILTINS}:
        raise ValueError(f"unknown Kilix 95 built-in game: {app!r}")
    root = root.expanduser().resolve(strict=True)
    if not (root / "main.py").is_file():
        raise FileNotFoundError(f"Kilix 95 main.py not found under {root}")
    sys.path.insert(0, str(root))
    os.chdir(root)
    import main as kilix95  # type: ignore[import-not-found]

    desk = kilix95.Desk(term=kilix95.DeskTerm())
    desk.shell.open_app(app)
    desk.run()


def native_build_command(repo: str, binary: str) -> list[str]:
    """Return the explicit native-game build command, or none for a fixture."""
    if os.path.isdir(repo) and os.access(os.path.join(repo, binary), os.X_OK):
        return []
    return ["make", "all"]


def resolve_kilix() -> str | None:
    """The kilix launcher, installed home first, then PATH."""
    candidates = []
    home = os.environ.get("KILIX_HOME")
    if home:
        candidates.append(os.path.join(home, "kilix"))
    source = os.environ.get("GPU_TERMINAL_SOURCE_HOME")
    if source:
        candidates.append(
            os.path.join(os.path.expanduser(source), "kilix", "kilix"))
    found = shutil.which("kilix")
    if found:
        candidates.append(found)
    for candidate in candidates:
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def host_plays_games(kilix: str) -> bool:
    """True when this kilix knows ``games play``.

    Asked without a game id, which every version refuses — the answer is in
    *how* it refuses: a launcher that has the verb names it in its own usage
    line.  Nothing launches either way, so the probe has no side effects.
    (The same detection kilix-land-desktop's games menu uses.)
    """
    try:
        probe = subprocess.run([kilix, "games", "play"],
                               stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    if probe.returncode == 0:
        return True
    message = (probe.stderr or "") + (probe.stdout or "")
    if "usage:" not in message.lower():
        return False
    return "play" in message


def run_game(root: Path, game: str) -> None:
    """Run one Kilix 95 registry game.

    Preferred path: the host owns games.  When this machine's ``kilix``
    knows ``kilix games play GAME``, hand the id over and never touch the
    Kilix 95 checkout — a mansion on a box that installed only Kilix Cap
    has no other desktop's source tree to shell into.

    Fallback path (a kilix that predates the verb): import the checkout's
    games module, preserving its normal installer UI.  The current
    native-game repositories include the shared game-kit Makefile before
    their own ``all`` target.  A bare ``make`` therefore selects a library
    target, exits successfully, and leaves no game executable.  Kilix 95's
    compatibility installer still invokes bare ``make``; replace only that
    compatibility seam with the equivalent pinned installer request and an
    explicit ``all`` goal before entering its normal ``games.main()``.
    """
    game = clean_id(game)
    kilix = resolve_kilix()
    if kilix and host_plays_games(kilix):
        os.execv(kilix, [kilix, "games", "play", game])
    root = root.expanduser().resolve(strict=True)
    games_path = root / "games.py"
    if not games_path.is_file():
        raise FileNotFoundError(f"Kilix 95 games.py not found under {root}")
    sys.path.insert(0, str(root))
    os.chdir(root)
    import games  # type: ignore[import-not-found]

    if game not in games.GAMES:
        raise ValueError(f"unknown Kilix 95 registry game: {game!r}")

    def clone_and_make(repo: str, ref: str, dest: str, binary: str,
                       dep_hint: str, report: object) -> str:
        dest = os.path.abspath(os.path.expanduser(dest))
        spec = games.kilix_content.ContentSpec.from_mapping({
            "id": os.path.basename(dest),
            "label": os.path.basename(dest),
            "source": {"type": "git", "repository": repo, "ref": ref},
            "binary": binary,
            "build": native_build_command(repo, binary),
            "dependency_hint": dep_hint,
        })
        return games.kilix_content.Installer(
            os.path.dirname(dest)).ensure(spec, report)

    games._clone_and_make = clone_and_make
    previous_argv = sys.argv
    try:
        sys.argv = [str(games_path), game]
        games.main()
    finally:
        sys.argv = previous_argv


def fixture() -> None:
    icon = "10" * (ICON_PIXELS // 2)
    emit([Path(__file__).resolve()], [
        ("builtin", "mines", "Minesweeper", icon),
        ("builtin", "sol", "Solitaire", icon),
        ("game", "doom", "Doom", icon),
        ("game", "kilix-pong", "Kilix Pong", icon),
    ])


def selftest() -> None:
    assert clean_id("kilix-pong") == "kilix-pong"
    for rejected in ("", "-doom", "Doom", "doom;id", "x" * 64):
        try:
            clean_id(rejected)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid game id: {rejected!r}")
    assert {(game_id, label) for game_id, label, _icon in BUILTINS} == {
        ("mines", "Minesweeper"), ("sol", "Solitaire")
    }
    assert native_build_command("/definitely/not/a/repository", "game") == [
        "make", "all"
    ]
    with tempfile.TemporaryDirectory(prefix="kilix-cap-build-goal-") as tmp:
        executable = Path(tmp) / "fixture-game"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o700)
        assert native_build_command(tmp, executable.name) == []
    print("kilix95_games: selftest ok")


def usage() -> None:
    print(
        "usage: kilix95_games.py list ROOT | launch ROOT GAME | "
        "builtin ROOT APP | fixture | selftest",
        file=sys.stderr,
    )


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["list"] and len(argv) == 2:
            emit(*load_catalog(Path(argv[1])))
        elif argv[:1] == ["launch"] and len(argv) == 3:
            run_game(Path(argv[1]), clean_id(argv[2]))
        elif argv[:1] == ["builtin"] and len(argv) == 3:
            run_builtin(Path(argv[1]), clean_id(argv[2]))
        elif argv == ["fixture"]:
            fixture()
        elif argv == ["selftest"]:
            selftest()
        else:
            usage()
            return 2
    except Exception as error:
        print(f"kilix95_games: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
