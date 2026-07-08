"""VirtualBox integration tests without launching VirtualBox."""
import os
import tempfile

import harness as H
from apps import filemgr
import vbox


def _menu_item(desk, label):
    for it in desk.menus.stack[-1].items:
        if it.label == label:
            return it
    raise AssertionError(f"no {label!r} item")


def _write_vm(path):
    with open(path, "w") as f:
        f.write("""<?xml version="1.0"?>
<VirtualBox xmlns="http://www.virtualbox.org/" version="1.19-linux">
  <Machine uuid="{12345678-1234-1234-1234-123456789abc}"
           name="sample vm" OSType="Linux"/>
</VirtualBox>
""")


def vbox_xml_parses_vm_identity():
    tmp = tempfile.mkdtemp(prefix="kilix95-vbox-")
    path = os.path.join(tmp, "sample.vbox")
    _write_vm(path)
    assert vbox.is_vm_file(path)
    assert vbox.vm_title(path) == "sample vm"
    assert vbox.vm_argv(path) == [
        "VirtualBoxVM", "--startvm",
        "{12345678-1234-1234-1234-123456789abc}",
    ]
    assert vbox.vm_argv(path, fullscreen=True)[-1] == "--fullscreen"


def shell_opens_vbox_file_in_kilix_run_tab():
    d = H.make_desk(size=(1280, 720))
    path = os.path.join(d.shell.dir, "sample.vbox")
    _write_vm(path)

    seen = {}
    d.shell._tab = lambda argv, title, cwd=None: seen.update(
        argv=argv, title=title, cwd=cwd) or True

    d.shell.open_path(path)
    assert os.path.basename(seen["argv"][0]) == "kilix", seen
    assert seen["argv"][1:] == [
        "run", "VirtualBoxVM", "--startvm",
        "{12345678-1234-1234-1234-123456789abc}",
    ], seen
    assert seen["title"] == "sample vm"
    assert path in d.shell.state["recent"]

    seen.clear()
    d.shell.open_virtualbox_vm(path, fullscreen=True)
    assert seen["argv"][1:] == [
        "run", "--size", "1280x720", "--fill",
        "VirtualBoxVM", "--startvm",
        "{12345678-1234-1234-1234-123456789abc}",
        "--fullscreen",
    ], seen


def vbox_file_contexts_offer_fullscreen():
    d = H.make_desk(size=(800, 600))
    path = os.path.join(d.shell.dir, "sample.vbox")
    _write_vm(path)
    d.shell.refresh()
    seen = {}
    d.shell._tab = lambda argv, title, cwd=None: seen.update(
        argv=argv, title=title, cwd=cwd) or True

    desktop_item = next(i for i in d.shell.grid.items
                        if i["label"] == "sample.vbox")
    d.shell._context(desktop_item, H.ev("mouse", x=20, y=20))
    _menu_item(d, "Open fullscreen").action()
    assert "--fill" in seen["argv"], seen
    assert "--fullscreen" in seen["argv"], seen

    d.menus.close_all()
    win = filemgr.FileWindow(d, d.shell.dir)
    file_item = next(i for i in win.grid.items if i["label"] == "sample.vbox")
    win._context(file_item, H.ev("mouse", x=20, y=20))
    assert _menu_item(d, "Open fullscreen").action


vbox_xml_parses_vm_identity()
shell_opens_vbox_file_in_kilix_run_tab()
vbox_file_contexts_offer_fullscreen()
print("ok")
