"""Safe host-facing helpers for Kilix 95's nostalgic shell features.

The UI modules deliberately keep discovery read-only.  The only persistent
writes here are Kilix 95 configuration and the managed virtual CD tree, all
under the project's canonical storage root.
"""

import json
import os
import re
import shutil
import subprocess

import storage


CONFIG = storage.config_dir("nostalgia.json")


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(value):
    os.makedirs(os.path.dirname(CONFIG), mode=0o700, exist_ok=True)
    temp = CONFIG + ".tmp"
    with open(temp, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temp, CONFIG)


def config_list(key):
    value = load_config().get(key, [])
    return value if isinstance(value, list) else []


def set_config_list(key, values):
    value = load_config()
    value[key] = list(values)
    save_config(value)


def _run(argv, timeout=2):
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _flatten_devices(nodes):
    out = []
    for node in nodes or []:
        if isinstance(node, dict):
            out.append(node)
            out.extend(_flatten_devices(node.get("children")))
    return out


def block_devices():
    """Return normalized block-device facts from lsblk, without mounting."""
    raw = _run([
        "lsblk", "--json", "--bytes", "--output",
        "NAME,LABEL,TYPE,SIZE,MOUNTPOINT,RM,RO,MODEL,FSTYPE",
    ])
    try:
        nodes = _flatten_devices(json.loads(raw).get("blockdevices", []))
    except (ValueError, AttributeError):
        nodes = []
    out = []
    for node in nodes:
        kind = str(node.get("type") or "")
        if kind not in ("disk", "part", "rom", "loop"):
            continue
        name = str(node.get("name") or "")
        if not name:
            continue
        out.append({
            "id": name,
            "name": name,
            "label": str(node.get("label") or ""),
            "type": kind,
            "size": int(node.get("size") or 0),
            "mount": str(node.get("mountpoint") or ""),
            "removable": bool(node.get("rm")),
            "readonly": bool(node.get("ro")),
            "model": str(node.get("model") or "").strip(),
            "fstype": str(node.get("fstype") or ""),
        })
    return out


def block_device_signature():
    """Cheap signature used by the live new-hardware notification monitor."""
    try:
        return tuple(sorted(os.listdir("/sys/class/block")))
    except OSError:
        return ()


def mounted_drives():
    """Mounted removable/optical devices suitable for My Computer."""
    seen, out = set(), []
    for dev in block_devices():
        mount = dev["mount"]
        if not mount or mount in seen:
            continue
        if not (dev["removable"] or dev["type"] == "rom"
                or mount.startswith(("/media/", "/run/media/", "/mnt/"))):
            continue
        seen.add(mount)
        label = dev["label"] or dev["model"] or os.path.basename(mount)
        out.append({**dev, "label": label or dev["name"]})
    return out


def ssh_hosts():
    """Configured concrete SSH aliases; wildcard patterns are not shown."""
    path = os.path.expanduser("~/.ssh/config")
    out, seen = [], set()
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            lines = stream
            for line in lines:
                match = re.match(r"\s*Host\s+(.+?)\s*$", line,
                                 flags=re.IGNORECASE)
                if not match:
                    continue
                for host in match.group(1).split():
                    if any(c in host for c in "*?!") or host in seen:
                        continue
                    seen.add(host)
                    out.append({"name": host, "kind": "ssh",
                                "target": host})
    except OSError:
        pass
    for item in config_list("network_hosts"):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append({"name": name,
                        "kind": str(item.get("kind") or "ssh"),
                        "target": str(item.get("target") or name),
                        "path": str(item.get("path") or "")})
    return out


def add_network_host(name, target=None, kind="ssh", path=""):
    name = str(name or "").strip()
    if not name:
        raise ValueError("Enter a computer name.")
    items = [item for item in config_list("network_hosts")
             if isinstance(item, dict) and item.get("name") != name]
    items.append({"name": name, "target": str(target or name),
                  "kind": kind, "path": str(path or "")})
    set_config_list("network_hosts", items)


def printers():
    """Detected CUPS queues plus Kilix virtual printer definitions."""
    found, seen = [], set()
    for line in _run(["lpstat", "-p"], timeout=3).splitlines():
        match = re.match(r"printer\s+(\S+)\s+(.*)", line)
        if match:
            name, status = match.groups()
            seen.add(name)
            found.append({"name": name, "kind": "cups",
                          "status": status.strip() or "Ready"})
    virtual = config_list("printers")
    if not virtual:
        virtual = [{"name": "Print to File", "kind": "file",
                    "path": storage.data_dir("printed-documents")}]
    for item in virtual:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name and name not in seen:
            found.append({"name": name,
                          "kind": str(item.get("kind") or "file"),
                          "path": str(item.get("path") or ""),
                          "status": "Ready"})
    return found


def add_virtual_printer(name, path):
    name = str(name or "").strip()
    path = os.path.abspath(os.path.expanduser(path or ""))
    if not name or not path:
        raise ValueError("Enter a printer name and output folder.")
    os.makedirs(path, exist_ok=True)
    items = [item for item in config_list("printers")
             if isinstance(item, dict) and item.get("name") != name]
    items.append({"name": name, "kind": "file", "path": path})
    set_config_list("printers", items)


def virtual_cd_path():
    return storage.data_dir("virtual-cd")


def ensure_virtual_cd():
    """Create the original-content Kilix 95 CD and return its mount folder."""
    root = virtual_cd_path()
    # Restore owner write permission for an in-place content refresh.
    if os.path.isdir(root):
        for current, dirs, files in os.walk(root):
            try:
                os.chmod(current, 0o755)
            except OSError:
                pass
            for name in files:
                try:
                    os.chmod(os.path.join(current, name), 0o644)
                except OSError:
                    pass
    os.makedirs(os.path.join(root, "Fun Stuff"), exist_ok=True)
    os.makedirs(os.path.join(root, "Projects"), exist_ok=True)
    docs = {
        "README.TXT": (
            "KILIX 95 CD-ROM\n\n"
            "Welcome to the original Kilix 95 multimedia sampler.\n"
            "Open Fun Stuff for demos and Projects for local project links.\n"
            "This managed disc is regenerated by Kilix 95 and is read-only.\n"),
        os.path.join("Fun Stuff", "WELCOME.TXT"): (
            "FUN STUFF\n\nTry Paint, Amp, the animated screensavers, "
            "Kilix Fishtank, Chess Bash, Joustix, and the other Games-menu "
            "installers. All artwork and sounds in Kilix 95 are original.\n"),
        os.path.join("Fun Stuff", "DID YOU KNOW.TXT"): (
            "Did you know? Right-click the desktop for Display Properties, "
            "open Network Neighborhood for SSH hosts, or use My Briefcase "
            "to synchronize two folders.\n"),
    }
    project_root = os.path.dirname(os.path.abspath(__file__))
    for name, path in (
            ("Kilix 95", project_root),
            ("Kilix", os.path.abspath(os.path.join(project_root, "..", "kilix"))),
            ("Pleb", os.path.abspath(os.path.join(project_root, "..", "pleb"))),
            ("Plebian-OS", os.path.abspath(os.path.join(project_root, "..", "plebian-os")))):
        docs[os.path.join("Projects", name + ".TXT")] = (
            f"{name}\n\nLocal checkout: {path}\n"
            + ("Available on this machine.\n" if os.path.exists(path)
               else "Not currently installed at this location.\n"))
    for relative, text in docs.items():
        path = os.path.join(root, relative)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(text)
    # The File Manager can browse it, while ordinary writes fail like a CD.
    for current, dirs, files in os.walk(root, topdown=False):
        for name in files:
            try:
                os.chmod(os.path.join(current, name), 0o444)
            except OSError:
                pass
        try:
            os.chmod(current, 0o555)
        except OSError:
            pass
    return root


def human_size(size):
    value = float(max(0, size))
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return (f"{int(value)} {unit}" if unit == "bytes"
                    else f"{value:.1f} {unit}")
        value /= 1024
    return f"{value:.1f} TB"


def send_to_destinations(shell):
    briefcase = storage.data_dir("briefcase")
    os.makedirs(briefcase, exist_ok=True)
    out = [("Desktop", shell.dir), ("My Briefcase", briefcase)]
    for item in config_list("send_to"):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            path = os.path.abspath(os.path.expanduser(
                str(item.get("path") or "")))
            if name and os.path.isdir(path):
                out.append((name, path))
    return out


def send_paths(paths, destination):
    """Copy paths to a configured destination without overwriting anything."""
    destination = os.path.abspath(os.path.expanduser(destination))
    if not os.path.isdir(destination):
        raise OSError(f"Destination does not exist: {destination}")
    copied = []
    for source in paths:
        source = os.path.abspath(os.path.expanduser(source))
        if not os.path.lexists(source):
            continue
        target = os.path.join(destination,
                              os.path.basename(source.rstrip(os.sep)))
        base, ext = os.path.splitext(target)
        number = 2
        while os.path.lexists(target):
            target = f"{base} ({number}){ext}"
            number += 1
        if os.path.isdir(source) and not os.path.islink(source):
            shutil.copytree(source, target, symlinks=True)
        else:
            shutil.copy2(source, target, follow_symlinks=False)
        copied.append(target)
    return copied
