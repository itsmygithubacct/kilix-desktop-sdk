"""kilix desktop — built-in apps.

apps.open(desk, name, arg) is the only entry point the shell uses; each app
is a wm.Window subclass in its own module. Settings is a singleton (opening
it again focuses the existing window); everything else opens fresh.
"""

import wm


FULL_EXPERIENCE_APPS = frozenset({
    "briefcase", "defrag", "devicemanager", "dialup", "hardware",
    "networkhood", "powertoys", "printers",
})
GAME_APPS = {"mines": "minesweeper", "sol": "solitaire"}


def open(desk, name, arg=None):
    game_id = GAME_APPS.get(name)
    if game_id is not None:
        from kilix_sdk import settings as shared_settings
        if not shared_settings.game_enabled(game_id):
            wm.msgbox(
                desk, "Games",
                "This game is disabled. Re-enable it in "
                "kilix Settings → Games.",
                icon="info")
            return
    if name in FULL_EXPERIENCE_APPS \
            and not desk.shell.full_experience_enabled():
        wm.msgbox(
            desk, "Full experience",
            "This classic extra is disabled.\n\n"
            "Open kilix Settings → Behavior and select\n"
            "Activate full experience to make it available.",
            icon="info")
        return
    if name == "filemgr":
        from . import filemgr
        desk.wm.add(filemgr.FileWindow(desk, arg or "~"))
    elif name == "notepad":
        from . import notepad
        desk.wm.add(notepad.Notepad(desk, arg))
    elif name == "viewer":
        from . import viewer
        desk.wm.add(viewer.Viewer(desk, arg))
    elif name == "amp":
        from . import amp
        amp.open_amp(desk, arg)
    elif name == "settings":
        from . import settings
        for w in desk.wm.windows:
            if isinstance(w, settings.SettingsWin):
                desk.wm.activate(w)
                return
        desk.wm.add(settings.SettingsWin(desk))
    elif name == "soundcp":
        from . import soundcp
        soundcp.open(desk)
    elif name == "calc":
        from . import calc
        desk.wm.add(calc.Calc(desk, arg))
    elif name == "mines":
        from . import mines
        desk.wm.add(mines.Mines(desk, arg))
    elif name == "sol":
        from . import sol
        desk.wm.add(sol.Solitaire(desk, arg))
    elif name == "paint":
        from . import paint
        desk.wm.add(paint.Paint(desk, arg))
    elif name == "wordpad":
        from . import wordpad
        desk.wm.add(wordpad.WordPad(desk, arg))
    elif name == "charmap":
        from . import charmap
        desk.wm.add(charmap.CharMap(desk, arg))
    elif name == "winhelp":
        from . import winhelp
        desk.wm.add(winhelp.Help(desk, arg))
    elif name == "manual":
        from . import manual
        desk.wm.add(manual.ManualBrowser(desk, arg))
    elif name == "mycomp":
        from . import mycomp
        desk.wm.add(mycomp.MyComputer(desk, arg))
    elif name == "recyclebin":
        from . import recyclebin
        for w in desk.wm.windows:
            if isinstance(w, recyclebin.RecycleBin):
                desk.wm.activate(w)
                return
        desk.wm.add(recyclebin.RecycleBin(desk))
    elif name == "findfiles":
        from . import findfiles
        desk.wm.add(findfiles.FindFiles(desk, arg))
    elif name == "taskmgr":
        from . import taskmgr
        for w in desk.wm.windows:
            if isinstance(w, taskmgr.TaskManager):
                desk.wm.activate(w)
                return
        desk.wm.add(taskmgr.TaskManager(desk))
    elif name == "controlpanel":
        from . import controlpanel
        for win in desk.wm.windows:
            if isinstance(win, controlpanel.ControlPanel):
                desk.wm.activate(win)
                return
        desk.wm.add(controlpanel.ControlPanel(desk, arg))
    elif name == "displayprops":
        from . import displayprops
        for win in desk.wm.windows:
            if isinstance(win, displayprops.DisplayProperties):
                if arg == "themes":
                    win._switch(4)
                elif arg == "settings":
                    win._switch(3)
                desk.wm.activate(win)
                return
        desk.wm.add(displayprops.DisplayProperties(desk, arg))
    elif name in ("mouseprops", "keyboardprops", "datetime", "fonts",
                  "systemprops"):
        from . import controlpanel
        classes = {
            "mouseprops": controlpanel.MouseProperties,
            "keyboardprops": controlpanel.KeyboardProperties,
            "datetime": controlpanel.DateTimeProperties,
            "fonts": controlpanel.FontBrowser,
            "systemprops": controlpanel.SystemProperties,
        }
        desk.wm.add(classes[name](desk, arg))
    elif name == "networkhood":
        from . import networkhood
        desk.wm.add(networkhood.NetworkNeighborhood(desk, arg))
    elif name == "dialup":
        from . import dialup
        desk.wm.add(dialup.DialUpNetworking(desk, arg))
    elif name == "printers":
        from . import printers
        desk.wm.add(printers.Printers(desk, arg))
    elif name in ("hardware", "devicemanager"):
        from . import hardware
        cls = hardware.HardwareWizard if name == "hardware" \
            else hardware.DeviceManager
        desk.wm.add(cls(desk, arg))
    elif name == "briefcase":
        from . import briefcase
        desk.wm.add(briefcase.BriefcaseWindow(desk, arg))
    elif name == "powertoys":
        from . import powertoys
        desk.wm.add(powertoys.PowerToys(desk, arg))
    elif name == "defrag":
        from . import defrag
        desk.wm.add(defrag.Defragmenter(desk, arg))
    else:
        raise ValueError(f"unknown app {name!r}")
