"""Every host catalog app reaches a managed Kilix 95 box."""
import os

import harness as H


def _find(items, label):
    return next((item for item in items if item.label == label), None)


d = H.make_desk()
d.taskbar.open_start_menu()
programs = _find(d.menus.stack[0].items, "Programs")
catalog = _find(programs.submenu, "Kilix Applications")
assert catalog is not None and catalog.submenu
labels = {item.label for item in catalog.submenu}
for expected in ("File Manager", "System Center", "Software Center",
                 "Voice Studio", "Character Map", "Notepad"):
    assert expected in labels, (expected, sorted(labels))

seen = {}
d.shell.open_in_xpane = lambda argv, title, **kwargs: seen.update(
    argv=list(argv), title=title, kwargs=kwargs) or True
entry = _find(catalog.submenu, "System Center")
entry.action()
assert seen["argv"] == [
    os.path.join(H.KILIX_HOME, "kilix"),
    "app", "window", "kilix-system-center",
], seen
assert seen["title"] == "System Center"
assert seen["kwargs"]["app_size"] == (960, 640)
assert seen["kwargs"]["application_id"] == "kilix-system-center"

existing = type("ExistingWindow", (), {
    "kilix_application_id": "kilix-system-center",
})()
d.wm.windows.append(existing)
activated = []
d.wm.activate = activated.append
d.shell.open_in_xpane = lambda *args, **kwargs: (_ for _ in ()).throw(
    AssertionError("a single-instance app opened a duplicate window"))
assert d.shell.open_catalog_application("kilix-system-center")
assert activated == [existing]

print("ok test_catalog_apps_menu")
