"""Windows 95 nostalgia namespaces, themes, shell polish, and safe services."""

import os
import tempfile
import time

import harness as H
import apps
import briefcase
import icons
import nostalgia
import screensaver
import storage
import themes
import widgets as W
from apps import controlpanel, dialup, displayprops, mycomp


def test_00_extras_are_opt_in():
    with H.desktop_dir():
        d = H.make_desk()
        assert not d.shell.full_experience_enabled()
        desktop = {item["label"] for item in d.shell.grid.items}
        assert not {"Network Neighborhood", "My Briefcase"} & desktop

        win = mycomp.MyComputer(d)
        d.wm.add(win)
        labels = {item["label"] for item in win.grid.items}
        assert not {"3½ Floppy (A:)", "Kilix 95 CD-ROM (K:)",
                    "Printers", "Dial-Up Networking", "Network Neighborhood",
                    "My Briefcase"} & labels

        props = controlpanel.SystemProperties(d)
        d.wm.add(props)
        assert not any(widget.visible for widget in props.device_widgets)

        d.shell.set_full_experience(True)
        desktop = {item["label"] for item in d.shell.grid.items}
        assert {"Network Neighborhood", "My Briefcase"} <= desktop
        labels = {item["label"] for item in win.grid.items}
        assert {"3½ Floppy (A:)", "Kilix 95 CD-ROM (K:)",
                "Printers", "Dial-Up Networking", "Network Neighborhood",
                "My Briefcase"} <= labels
        assert all(widget.visible for widget in props.device_widgets)

        d.shell.set_full_experience(False)
        assert not any(widget.visible for widget in props.device_widgets)
        assert props.focus is props.ok
        d.shell.set_full_experience(True)
        assert all(widget.visible for widget in props.device_widgets)


def test_storage_and_theme_pack():
    d = H.make_desk()
    root = storage.storage_home()
    assert root.endswith("kilix-95")
    assert all(os.path.commonpath([root, path]) == root for path in (
        storage.config_dir(), storage.state_dir(), storage.cache_dir(),
        storage.data_dir(), storage.session_dir()))
    spec = themes.apply(d.shell, "Dangerous Creatures")
    assert spec["cursor"] == "Dinosaur"
    assert d.shell.state["saver_name"] == "Pipes"
    assert d.shell.state["era_profile"] == "Windows 95 Plus!"
    assert os.path.isfile(d.shell.state["wall_image"])
    assert d.shell.state["wall_image"].startswith(storage.data_dir())


def test_control_panel_and_namespaces_render():
    d = H.make_desk((800, 600))
    d.shell.set_full_experience(True)
    for name, class_name in (
            ("controlpanel", "ControlPanel"),
            ("displayprops", "DisplayProperties"),
            ("networkhood", "NetworkNeighborhood"),
            ("dialup", "DialUpNetworking"),
            ("printers", "Printers"),
            ("devicemanager", "DeviceManager"),
            ("briefcase", "BriefcaseWindow"),
            ("powertoys", "PowerToys"),
            ("defrag", "Defragmenter")):
        apps.open(d, name)
        assert H.find_window(d, class_name) is not None
    d.render()
    required = {"Themes", "Add New Hardware", "PowerToys", "Printers"}
    panel = H.find_window(d, "ControlPanel")
    assert required <= {item["label"] for item in panel.grid.items}


def test_my_computer_special_folders():
    d = H.make_desk()
    win = mycomp.MyComputer(d)
    labels = {item["label"] for item in win.grid.items}
    assert {"3½ Floppy (A:)", "Kilix 95 CD-ROM (K:)", "Control Panel",
            "Printers", "Dial-Up Networking", "Network Neighborhood",
            "My Briefcase"} <= labels


def test_virtual_cd_and_send_to():
    d = H.make_desk()
    root = nostalgia.ensure_virtual_cd()
    assert root.startswith(storage.data_dir())
    assert os.path.isfile(os.path.join(root, "README.TXT"))
    assert os.path.isfile(os.path.join(root, "Fun Stuff", "DID YOU KNOW.TXT"))
    assert not os.stat(root).st_mode & 0o222
    source_dir = tempfile.mkdtemp(prefix="kilix95-send-source-")
    source = os.path.join(source_dir, "hello.txt")
    with open(source, "w", encoding="utf-8") as stream:
        stream.write("hello")
    copied = nostalgia.send_paths([source], d.shell.dir)
    assert len(copied) == 1 and open(copied[0], encoding="utf-8").read() == "hello"
    # Leave the runner able to remove its otherwise read-only sandbox.
    for current, _dirs, files in os.walk(root):
        os.chmod(current, 0o755)
        for name in files:
            os.chmod(os.path.join(current, name), 0o644)


def test_briefcase_non_destructive_sync():
    parent = tempfile.mkdtemp(prefix="kilix95-briefcase-")
    left, right = os.path.join(parent, "left"), os.path.join(parent, "right")
    os.makedirs(left); os.makedirs(right)
    with open(os.path.join(left, "one.txt"), "w", encoding="utf-8") as stream:
        stream.write("one")
    result = briefcase.synchronize(left, right)
    assert result["copied"] == ["one.txt"]
    assert open(os.path.join(right, "one.txt"), encoding="utf-8").read() == "one"
    assert open(briefcase.STATE, "rb").read(4) == b"KST1"
    assert not os.path.exists(briefcase.LEGACY_STATE)
    with open(os.path.join(left, "one.txt"), "w", encoding="utf-8") as stream:
        stream.write("left")
    with open(os.path.join(right, "one.txt"), "w", encoding="utf-8") as stream:
        stream.write("right")
    result = briefcase.synchronize(left, right)
    assert result["conflicts"] == ["one.txt"]
    assert open(os.path.join(left, "one.txt"), encoding="utf-8").read() == "left"
    assert open(os.path.join(right, "one.txt"), encoding="utf-8").read() == "right"


def test_savers_password_and_dialup_tray():
    d = H.make_desk()
    assert {"Pipes", "Maze", "Marquee", "Flying Kilix", "Blank"} <= \
        set(screensaver.names())
    d.shell.state.update({
        "saver_name": "Maze", "saver_lock": True,
        "saver_password": displayprops._password_record("secret")})
    d._start_saver()
    assert type(d.saver).__name__ == "Maze"
    d._wake_saver()
    unlock = next(win for win in d.wm.windows if win.title == "Unlock Kilix 95")
    assert unlock.modal
    unlock.close = lambda: None

    connection = dialup.DialConnection(d, dialup.DEFAULT_CONNECTION)
    connection._finish()
    assert d.dialup_state["connected"]
    assert "network" in [name for name, _tip in d.taskbar._tray_defs()]
    assert dialup.disconnect(d)


def test_start_menu_dos_caller_and_polish():
    d = H.make_desk()
    d.taskbar.open_start_menu()
    start = d.menus.stack[0]
    programs = next(item for item in start.items if item.label == "Programs")
    labels = {item.label for item in programs.submenu}
    assert {"MS-DOS Prompt", "PowerToys", "Network Neighborhood",
            "Dial-Up Networking", "My Briefcase", "Printers"} <= labels
    settings = next(item for item in start.items if item.label == "Settings")
    assert any(item.label == "Control Panel" for item in settings.submenu)
    d.menus.close_all()

    called = []
    d.shell._tab = lambda argv, title, cwd=None, env=None: called.append(
        (argv, title, cwd)) or True
    assert d.shell.open_dos_prompt()
    assert called[0][1] == "MS-DOS Prompt"
    assert os.path.basename(called[0][0][-2]) == "games.py"
    assert called[0][0][-1] == "dosbox"

    apps.open(d, "notepad")
    win = d.wm.active
    d.shell.state["full_window_drag"] = False
    original = (win.x, win.y)
    d.wm.begin_drag(win, "move", win.x, win.y)
    d.wm.drag_motion(W.Ev(kind="mouse", x=win.x + 40, y=win.y + 30,
                          move=True, btn=1))
    assert (win.x, win.y) == original and d.drag_outline is not None
    d.wm.end_drag()
    assert (win.x, win.y) == (original[0] + 40, original[1] + 30)
    menubar = next(widget for widget in win.widgets if isinstance(widget, W.MenuBar))
    assert menubar.activate_accelerator("f")
    assert d.menus.active


def test_new_hardware_notification():
    d = H.make_desk()
    original = nostalgia.block_device_signature
    try:
        d.hardware_signature = ("sda",)
        d._hardware_checked = 0
        nostalgia.block_device_signature = lambda: ("sda", "sdb")
        d._hardware_tick(time.time())
        assert d.new_hardware
        assert "hardware" in [name for name, _tip in d.taskbar._tray_defs()]
    finally:
        nostalgia.block_device_signature = original


def test_nostalgia_icons_exist():
    for name in ("controlpanel", "theme", "network", "dialup", "printer",
                 "briefcase", "cdrom", "floppy", "hardware", "powertoys",
                 "sendto", "defrag"):
        assert icons.get(name, 32).size == (32, 32)


for _name, _test in sorted(list(globals().items())):
    if _name.startswith("test_") and callable(_test):
        _test()
print("ok")
