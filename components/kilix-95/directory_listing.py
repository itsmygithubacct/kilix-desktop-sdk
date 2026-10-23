"""Filesystem snapshots shared by manual and background directory refreshes."""
import configparser
from dataclasses import dataclass
import os
import stat


def _identity(path, info):
    return (os.path.abspath(path), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def _version(info):
    return (info.st_ctime_ns, info.st_mtime_ns, info.st_size, info.st_mode)


def parse_launcher(path):
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    try:
        # Directory refresh must never wait for a FIFO/device called .desktop.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 256 * 1024:
                return {}
            text = stream.read(256 * 1024 + 1)
        if len(text) > 256 * 1024:
            return {}
        cp.read_string(text.decode('utf-8'))
        return dict(cp['Desktop Entry']) if cp.has_section('Desktop Entry') else {}
    except (OSError, ValueError, configparser.Error):
        return {}


@dataclass(frozen=True)
class Entry:
    name: str
    path: str
    isdir: bool
    identity: tuple
    version: tuple
    launcher: dict | None

    def tag(self, item):
        return dict(item, _entry_key=self.identity, _entry_version=self.version)


@dataclass(frozen=True)
class Listing:
    path: str
    entries: tuple
    error: int | None = None


def scan(path):
    path = os.path.abspath(os.path.expanduser(path))
    entries = []
    try:
        with os.scandir(path) as names:
            for entry in names:
                try:
                    info = entry.stat(follow_symlinks=False)
                    isdir = entry.is_dir()
                    version = _version(info)
                    if stat.S_ISLNK(info.st_mode):
                        # Also notice changes to the target's type/launcher data.
                        try: version += _version(entry.stat())
                        except OSError: pass
                    spec = parse_launcher(entry.path) if entry.name.endswith('.desktop') and not isdir else None
                    entries.append(Entry(entry.name, entry.path, isdir, _identity(entry.path, info), version, spec))
                except OSError:
                    continue  # Entry disappeared during this non-atomic listing.
        return Listing(path, tuple(entries))
    except OSError as error:
        return Listing(path, (), error.errno)


def current(item):
    """Never redirect an old file/launcher action to a replacement entry."""
    key = item.get('_entry_key')
    if key is None:
        return True  # Synthetic/builtin items retain their existing behavior.
    try:
        info = os.lstat(key[0])
        if key != _identity(key[0], info):
            return False
        version = _version(info)
        if stat.S_ISLNK(info.st_mode):
            try: version += _version(os.stat(key[0]))
            except OSError: pass
        return item.get('_entry_version') == version
    except OSError:
        return False
