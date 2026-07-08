"""VirtualBox launch helpers for Kilix-95.

VirtualBox windows need to stay inside `kilix run`; launching them as normal
host/XPane windows can leave an unmanaged square over the desktop.
"""
import os
import shlex
import xml.etree.ElementTree as ET


VM_EXTS = (".vbox",)
_COMMANDS = {"virtualbox", "virtualboxvm", "vbox"}


def is_vm_file(path):
    return str(path).lower().endswith(VM_EXTS)


def is_virtualbox_argv(argv):
    if not argv:
        return False
    return os.path.basename(argv[0]).lower() in _COMMANDS


def is_virtualbox_exec(exec_str):
    try:
        return is_virtualbox_argv(shlex.split(exec_str or ""))
    except ValueError:
        return False


def is_virtualbox_entry(entry):
    entry_id = (entry.get("id") or "").lower()
    icon = (entry.get("icon") or "").lower()
    name = (entry.get("name") or "").lower()
    return (is_virtualbox_exec(entry.get("exec", ""))
            or entry_id.startswith("virtualbox")
            or icon == "virtualbox"
            or "virtualbox" in name)


def read_vm(path):
    """Return {'uuid': ..., 'name': ...} from a .vbox file when readable."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] == "Machine":
            return {"uuid": elem.get("uuid"), "name": elem.get("name")}
    return {}


def vm_title(path):
    meta = read_vm(path)
    return meta.get("name") or os.path.splitext(os.path.basename(path))[0] \
        or "VirtualBox VM"


def vm_argv(path, fullscreen=False):
    meta = read_vm(path)
    ident = meta.get("uuid") or meta.get("name") or path
    argv = ["VirtualBoxVM", "--startvm", ident]
    if fullscreen:
        argv.append("--fullscreen")
    return argv


def entry_argv(entry, fullscreen=False):
    try:
        argv = shlex.split(entry.get("exec", ""))
    except ValueError:
        return []
    if fullscreen and argv and os.path.basename(argv[0]).lower() == "virtualboxvm" \
            and "--fullscreen" not in argv:
        argv.append("--fullscreen")
    return argv
