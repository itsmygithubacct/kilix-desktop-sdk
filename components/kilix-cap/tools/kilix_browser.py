#!/usr/bin/env python3
"""Launch one isolated Firefox window for a streamed Kilix app pane."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


PROFILE_PREFS = """\
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.firstrunSkipsHomepage", true);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
"""


def valid_http_url(value: str) -> bool:
    if not value or any(ord(ch) < 33 or ord(ch) > 126 for ch in value):
        return False
    parsed = urlsplit(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def valid_executable(path: str) -> bool:
    try:
        info = os.stat(path, follow_symlinks=True)
    except OSError:
        return False
    return (
        os.path.isabs(path)
        and stat.S_ISREG(info.st_mode)
        and os.access(path, os.X_OK)
    )


def browser_argv(firefox: str, profile: str, url: str) -> list[str]:
    return [
        firefox,
        "--no-remote",
        "--new-instance",
        "--profile",
        profile,
        "--new-window",
        url,
    ]


def write_profile_preferences(profile: str) -> None:
    path = os.path.join(profile, "user.js")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(PROFILE_PREFS)


def remove_ready_log() -> None:
    raw_path = os.environ.get("KILIX_RUN_LOG", "")
    path = Path(raw_path)
    if (
        not path.is_absolute()
        or not path.name.startswith(".web-ready.")
        or path.suffix != ".log"
    ):
        return
    try:
        info = path.lstat()
        if stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid():
            path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def run_browser(firefox: str, url: str) -> int:
    if not valid_executable(firefox):
        print("kilix browser: Firefox ESR is unavailable", file=sys.stderr)
        return 2
    if not valid_http_url(url):
        print("kilix browser: the start page is not a valid http(s) URL",
              file=sys.stderr)
        return 2

    profile = tempfile.mkdtemp(prefix="kilix-cap-firefox-")
    try:
        os.chmod(profile, 0o700)
        write_profile_preferences(profile)
        environment = os.environ.copy()
        environment.pop("WAYLAND_DISPLAY", None)
        environment["MOZ_ENABLE_WAYLAND"] = "0"
        environment["MOZ_NO_REMOTE"] = "1"
        result = subprocess.run(
            browser_argv(firefox, profile, url),
            env=environment,
            check=False,
        )
        return result.returncode
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        remove_ready_log()


def selftest() -> int:
    checks = (
        valid_http_url("https://news.ycombinator.com/"),
        valid_http_url("http://example.org/path?q=1"),
        not valid_http_url("file:///tmp/example"),
        not valid_http_url("https://"),
        not valid_http_url("https://example.org/a b"),
        browser_argv("/usr/bin/firefox-esr", "/tmp/profile", "https://x/") == [
            "/usr/bin/firefox-esr",
            "--no-remote",
            "--new-instance",
            "--profile",
            "/tmp/profile",
            "--new-window",
            "https://x/",
        ],
    )
    if not all(checks):
        print("kilix_browser selftest: FAIL", file=sys.stderr)
        return 1
    print("kilix_browser selftest: ok")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["selftest"]:
        return selftest()
    if len(argv) != 2:
        print("usage: kilix_browser.py FIREFOX URL", file=sys.stderr)
        return 2
    return run_browser(argv[0], argv[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
