#!/usr/bin/env python3
"""Live system consoles launched from Kilix Cap's mansion rooms.

The monitor modes are read-only.  Housekeeping actions are deliberately
bounded, previewed, and require an explicit confirmation inside this TUI.
Privileged package/journal cleanup is delegated to pkexec so the desktop owns
the authentication prompt and policy decision.
"""

from __future__ import annotations

import argparse
import curses
from dataclasses import dataclass
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import time
from typing import Callable, Iterable


REFRESH_SECONDS = 2.0
MAX_CAPTURE = 32_768
MAX_SCAN_ENTRIES = 50_000
TEMP_AGE_SECONDS = 7 * 24 * 60 * 60


def command_lines(argv: list[str], limit: int, timeout: float = 2.0) -> list[str]:
    """Run one fixed argv without a shell and return a bounded line snapshot."""

    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return result.stdout[:MAX_CAPTURE].splitlines()[-limit:]


def tail_text(path: Path, limit: int) -> list[str]:
    try:
        if path.is_symlink() or not path.is_file():
            return []
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - MAX_CAPTURE), os.SEEK_SET)
            data = handle.read(MAX_CAPTURE)
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()[-limit:]


def system_logs(limit: int) -> list[str]:
    journalctl = shutil.which("journalctl")
    if journalctl:
        lines = command_lines(
            [journalctl, "--no-pager", "-n", str(limit), "-o", "short-monotonic"],
            limit,
        )
        if lines:
            return lines
    for candidate in (Path("/var/log/syslog"), Path("/var/log/messages")):
        lines = tail_text(candidate, limit)
        if lines:
            return lines
    return ["No readable journal or system log was found."]


def system_alerts(limit: int) -> list[str]:
    journalctl = shutil.which("journalctl")
    if journalctl:
        lines = command_lines(
            [
                journalctl,
                "--no-pager",
                "-p",
                "warning..alert",
                "-n",
                str(limit),
                "-o",
                "short-monotonic",
            ],
            limit,
        )
        if lines:
            return lines
    return ["No current warning-or-higher journal entries."]


def system_mail(limit: int) -> list[str]:
    user = pwd.getpwuid(os.getuid()).pw_name
    for candidate in (Path("/var/mail") / user, Path("/var/spool/mail") / user):
        lines = tail_text(candidate, limit)
        if lines:
            return lines
    mail_command = shutil.which("mail")
    if mail_command:
        lines = command_lines([mail_command, "-H"], limit)
        if lines:
            return lines
    return [f"No local system mail for {user}."]


def process_rows(limit: int) -> list[str]:
    rows: list[tuple[int, str]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            status: dict[str, str] = {}
            for line in (entry / "status").read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    status[key] = value.strip()
            uid_text = status.get("Uid", "").split()
            if uid_text and int(uid_text[0]) != os.getuid():
                continue
            rss_text = status.get("VmRSS", "0 kB").split()
            rss_kib = int(rss_text[0]) if rss_text else 0
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
            shown = command.decode("utf-8", "replace").strip()
            if not shown:
                shown = status.get("Name", "?")
            state = status.get("State", "?").split()[0]
            rows.append(
                (
                    rss_kib,
                    f"{entry.name:>6} {state:<2} {rss_kib / 1024:>7.1f}M  {shown}",
                )
            )
        except (OSError, ValueError):
            continue
    rows.sort(key=lambda row: row[0], reverse=True)
    return [row[1] for row in rows[:limit]] or ["No user processes are visible."]


def network_rows(limit: int) -> list[str]:
    ss = shutil.which("ss")
    if ss:
        lines = command_lines([ss, "-tunap"], limit + 1)
        if lines:
            return lines[: limit + 1]
    netstat = shutil.which("netstat")
    if netstat:
        lines = command_lines([netstat, "-tun"], limit + 1)
        if lines:
            return lines[: limit + 1]
    return ["Neither ss nor netstat is installed."]


def clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    clean = "".join(ch if ch.isprintable() else " " for ch in text)
    return clean if len(clean) <= width else clean[: max(0, width - 1)] + "…"


def put(
    screen: curses.window,
    y: int,
    x: int,
    text: str,
    width: int,
    style: int = 0,
) -> None:
    height, screen_width = screen.getmaxyx()
    if y < 0 or y >= height or x < 0 or x >= screen_width or width <= 0:
        return
    try:
        screen.addnstr(y, x, clip(text, min(width, screen_width - x)), width, style)
    except curses.error:
        pass


def initialize_colors() -> dict[str, int]:
    # The one Kilix palette: blue carries structure and selection, red warns,
    # white speaks, and grey supports.
    colors = {
        "text": curses.A_NORMAL,
        "title": curses.A_BOLD,
        "accent": curses.A_BOLD,
        "alert": curses.A_BOLD,
        "muted": curses.A_DIM,
        "selected": curses.A_REVERSE,
    }
    if not curses.has_colors():
        return colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_BLUE, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
    colors.update(
        text=curses.color_pair(1),
        title=curses.color_pair(1) | curses.A_BOLD,
        accent=curses.color_pair(2),
        alert=curses.color_pair(3) | curses.A_BOLD,
        muted=curses.color_pair(1) | curses.A_DIM,
        selected=curses.color_pair(4) | curses.A_BOLD,
    )
    return colors


def draw_frame(
    screen: curses.window, title: str, colors: dict[str, int], _now: float
) -> tuple[int, int]:
    screen.erase()
    height, width = screen.getmaxyx()
    if height <= 0 or width <= 0:
        return height, width
    left = 1 if width > 2 else 0
    put(screen, 0, left, "KILIX TUI", max(0, width - left),
        colors["title"])
    strap = f"Kilix Cap · {title.title()}"
    if width - len(strap) - 1 > left + len("KILIX TUI"):
        put(screen, 0, width - len(strap) - 1, strap, len(strap),
            colors["muted"])
    put(screen, 1, left, "▶1 Overview ", max(0, width - left),
        colors["selected"])
    put(screen, 2, 0, "─" * max(0, width - 1), width, colors["muted"])
    put(
        screen,
        3,
        left,
        time.strftime("%Y-%m-%d %H:%M:%S") + " · live system console",
        max(0, width - left),
        colors["muted"],
    )
    put(screen, height - 1, left, "r refresh · q close",
        max(0, width - left), colors["muted"])
    return height, width


def draw_section(
    screen: curses.window,
    y: int,
    x: int,
    height: int,
    width: int,
    title: str,
    lines: Iterable[str],
    colors: dict[str, int],
    *,
    warning: bool = False,
) -> None:
    if height < 2 or width < 4:
        return
    style = colors["alert"] if warning else colors["accent"]
    put(screen, y, x, title.upper(), width, style)
    for index, line in enumerate(lines):
        if index >= height - 1:
            break
        put(screen, y + 1 + index, x, line, width, colors["text"])


def monitor_loop(
    screen: curses.window,
    title: str,
    painter: Callable[[curses.window, int, int, dict[str, int]], None],
) -> None:
    colors = initialize_colors()
    curses.curs_set(0)
    screen.nodelay(True)
    screen.timeout(100)
    next_refresh = 0.0
    while True:
        now = time.monotonic()
        if now >= next_refresh:
            height, width = draw_frame(screen, title, colors, now)
            painter(screen, height, width, colors)
            screen.refresh()
            next_refresh = now + REFRESH_SECONDS
        key = screen.getch()
        if key in (ord("q"), ord("Q"), 27):
            return
        if key in (ord("r"), ord("R"), curses.KEY_RESIZE):
            next_refresh = 0.0


def logs_painter(
    screen: curses.window, height: int, width: int, colors: dict[str, int]
) -> None:
    if height < 8 or width < 48:
        return
    body_height = height - 5
    left_width = max(24, width * 2 // 3)
    right_width = width - left_width
    alert_height = max(4, body_height // 3)
    log_height = body_height - alert_height
    draw_section(
        screen,
        4,
        0,
        log_height,
        left_width,
        "SYSTEM LOG STREAM",
        system_logs(max(1, log_height - 1)),
        colors,
    )
    draw_section(
        screen,
        4 + log_height,
        0,
        alert_height,
        left_width,
        "ALERTS / WARNINGS",
        system_alerts(max(1, alert_height - 1)),
        colors,
        warning=True,
    )
    draw_section(
        screen,
        4,
        left_width,
        body_height,
        right_width,
        "SYSTEM MAIL",
        system_mail(max(1, body_height - 1)),
        colors,
    )


def activity_painter(
    screen: curses.window, height: int, width: int, colors: dict[str, int]
) -> None:
    if height < 8 or width < 48:
        return
    body_height = height - 5
    left_width = max(28, width * 3 // 5)
    draw_section(
        screen,
        4,
        0,
        body_height,
        left_width,
        "ACTIVE PROCESSES  PID ST RSS COMMAND",
        process_rows(max(1, body_height - 1)),
        colors,
    )
    draw_section(
        screen,
        4,
        left_width,
        body_height,
        width - left_width,
        "ACTIVE NETWORK CONNECTIONS",
        network_rows(max(1, body_height - 1)),
        colors,
    )


def path_size(path: Path) -> tuple[int, int, bool]:
    total = 0
    entries = 0
    truncated = False
    try:
        if path.is_symlink():
            return path.lstat().st_size, 1, False
        if path.is_file():
            return path.stat().st_size, 1, False
        for root, directories, files in os.walk(path, followlinks=False):
            directories[:] = [
                name for name in directories if not (Path(root) / name).is_symlink()
            ]
            for name in files:
                entries += 1
                if entries > MAX_SCAN_ENTRIES:
                    truncated = True
                    return total, entries, truncated
                try:
                    total += (Path(root) / name).lstat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total, entries, truncated


def human_size(value: int) -> str:
    amount = float(value)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024.0 or suffix == "TiB":
            return f"{amount:.1f} {suffix}"
        amount /= 1024.0
    return f"{amount:.1f} TiB"


def safe_children(path: Path) -> list[Path]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_dir() or resolved == Path("/"):
            return []
        return list(resolved.iterdir())
    except OSError:
        return []


def remove_entry(path: Path) -> bool:
    try:
        details = path.lstat()
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
            path.unlink()
        else:
            shutil.rmtree(path)
        return True
    except OSError:
        return False


def old_owned_temp_entries() -> list[Path]:
    cutoff = time.time() - TEMP_AGE_SECONDS
    result: list[Path] = []
    try:
        for entry in Path("/tmp").iterdir():
            details = entry.lstat()
            if details.st_uid == os.getuid() and details.st_mtime < cutoff:
                result.append(entry)
    except OSError:
        pass
    return result


def temp_summary() -> tuple[str, list[Path]]:
    entries = old_owned_temp_entries()
    total = 0
    for entry in entries:
        total += path_size(entry)[0]
    return f"{len(entries)} owned entries older than 7 days · {human_size(total)}", entries


def directory_summary(path: Path) -> str:
    total, entries, truncated = path_size(path)
    marker = "+" if truncated else ""
    return f"{human_size(total)} · {entries}{marker} files · {path}"


def journal_summary() -> str:
    journalctl = shutil.which("journalctl")
    if not journalctl:
        return "journalctl is not installed"
    lines = command_lines([journalctl, "--disk-usage"], 1)
    return lines[-1] if lines else "journal size unavailable"


@dataclass(frozen=True)
class CleanupAction:
    key: str
    title: str
    summary: Callable[[], str]
    execute: Callable[[], str]


def clean_temp() -> str:
    _, entries = temp_summary()
    removed = sum(remove_entry(entry) for entry in entries)
    return f"Removed {removed} of {len(entries)} old owned /tmp entries."


def clean_directory_children(path: Path, label: str) -> str:
    children = safe_children(path)
    removed = sum(remove_entry(entry) for entry in children)
    return f"Removed {removed} of {len(children)} entries from {label}."


def privileged(argv: list[str], label: str) -> str:
    pkexec = shutil.which("pkexec")
    executable = shutil.which(argv[0])
    if not pkexec or not executable:
        return f"{label} needs pkexec and {argv[0]}."
    try:
        result = subprocess.run([pkexec, executable, *argv[1:]], check=False)
    except OSError as exc:
        return f"{label} could not start: {exc}."
    return (
        f"{label} completed."
        if result.returncode == 0
        else f"{label} exited with status {result.returncode}."
    )


def clean_apt() -> str:
    return privileged(["apt-get", "clean"], "APT package-cache cleaning")


def vacuum_journal() -> str:
    return privileged(
        ["journalctl", "--vacuum-time=14d"], "System journal vacuum"
    )


def empty_trash() -> str:
    gio = shutil.which("gio")
    if gio:
        try:
            result = subprocess.run([gio, "trash", "--empty"], check=False)
            if result.returncode == 0:
                return "Desktop trash emptied."
        except OSError:
            pass
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return clean_directory_children(data_home / "Trash/files", "desktop trash")


def cleanup_actions() -> list[CleanupAction]:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    thumbnails = cache_home / "thumbnails"
    apt_cache = Path("/var/cache/apt/archives")
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    trash = data_home / "Trash/files"
    return [
        CleanupAction("1", "Old owned temporary files", lambda: temp_summary()[0], clean_temp),
        CleanupAction(
            "2",
            "Thumbnail cache",
            lambda: directory_summary(thumbnails),
            lambda: clean_directory_children(thumbnails, "thumbnail cache"),
        ),
        CleanupAction(
            "3",
            "APT package cache",
            lambda: directory_summary(apt_cache),
            clean_apt,
        ),
        CleanupAction("4", "Journals older than 14 days", journal_summary, vacuum_journal),
        CleanupAction(
            "5",
            "Desktop trash",
            lambda: directory_summary(trash),
            empty_trash,
        ),
    ]


def cleanup_loop(screen: curses.window, focus: str) -> None:
    colors = initialize_colors()
    curses.curs_set(0)
    screen.timeout(150)
    actions = cleanup_actions()
    pending: CleanupAction | None = None
    status = "Nothing is removed until you choose a station and confirm with y."
    while True:
        now = time.monotonic()
        height, width = draw_frame(screen, "HOUSEKEEPING CONSOLE", colors, now)
        put(
            screen,
            4,
            2,
            "Bounded cleanup stations · privileged jobs use the desktop auth prompt",
            width - 4,
            colors["accent"],
        )
        if focus != "all":
            put(
                screen,
                5,
                2,
                f"Room station selected: {focus.upper()}",
                width - 4,
                colors["title"],
            )
        start = 7
        for index, action in enumerate(actions):
            selected = pending == action
            style = colors["selected"] if selected else colors["text"]
            put(
                screen,
                start + index * 2,
                3,
                f"{'▶' if selected else ' '} [{action.key}] {action.title}",
                max(1, width // 3),
                style,
            )
            put(
                screen,
                start + index * 2,
                max(28, width // 3),
                action.summary(),
                width - max(30, width // 3),
                colors["muted"],
            )
        footer_y = min(height - 3, start + len(actions) * 2 + 1)
        if pending:
            message = (
                f"Confirm {pending.title}?  [y] yes  [n] cancel. "
                "Only the described target is affected."
            )
            put(screen, footer_y, 2, message, width - 4, colors["alert"])
        else:
            put(screen, footer_y, 2, status, width - 4, colors["accent"])
        screen.refresh()
        key = screen.getch()
        if key in (ord("q"), ord("Q"), 27):
            return
        if pending and key in (ord("y"), ord("Y")):
            curses.def_prog_mode()
            curses.endwin()
            status = pending.execute()
            try:
                input(f"\n{status}\nPress Enter to return to Housekeeping…")
            except EOFError:
                pass
            curses.reset_prog_mode()
            curses.curs_set(0)
            pending = None
            continue
        if pending and key in (ord("n"), ord("N")):
            status = "Cleanup cancelled; nothing was removed."
            pending = None
            continue
        for action in actions:
            if key == ord(action.key):
                pending = action
                break


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kilix Cap mansion system console")
    parser.add_argument("mode", choices=("logs", "activity", "cleanup", "selftest"))
    parser.add_argument(
        "focus",
        nargs="?",
        default="all",
        choices=("all", "temp", "cache", "packages", "trash"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "selftest":
        class TestScreen:
            def __init__(self) -> None:
                self.lines = [" " * 100 for _ in range(24)]

            def erase(self) -> None:
                self.lines = [" " * 100 for _ in range(24)]

            def getmaxyx(self) -> tuple[int, int]:
                return 24, 100

            def addnstr(
                self, row: int, column: int, text: str, count: int, style: int
            ) -> None:
                del style
                clipped = text[:count][:100 - column]
                line = self.lines[row]
                self.lines[row] = (
                    line[:column] + clipped + line[column + len(clipped):]
                )

        actions = cleanup_actions()
        screen = TestScreen()
        test_colors = {
            name: 0 for name in
            ("text", "title", "accent", "alert", "muted", "selected")
        }
        draw_frame(screen, "ACTIVITY", test_colors, 0.0)
        if (
            [action.key for action in actions] != ["1", "2", "3", "4", "5"]
            or any(not action.title or not action.summary() for action in actions)
            or not process_rows(3)
            or not network_rows(3)
            or not system_logs(3)
            or not system_alerts(3)
            or not system_mail(3)
            or "KILIX TUI" not in screen.lines[0]
            or "Kilix Cap · Activity" not in screen.lines[0]
            or "▶1 Overview" not in screen.lines[1]
            or not screen.lines[2].startswith("─")
            or " // " in "\n".join(screen.lines)
        ):
            print("mansion_tui: selftest failed")
            return 1
        print("mansion_tui: selftest ok (read-only monitors, bounded cleanup previews)")
    elif args.mode == "logs":
        curses.wrapper(
            monitor_loop,
            "LOGS · ALERTS · SYSTEM MAIL",
            logs_painter,
        )
    elif args.mode == "activity":
        curses.wrapper(
            monitor_loop,
            "PROCESSES · NETWORK CONNECTIONS",
            activity_painter,
        )
    else:
        curses.wrapper(cleanup_loop, args.focus)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
