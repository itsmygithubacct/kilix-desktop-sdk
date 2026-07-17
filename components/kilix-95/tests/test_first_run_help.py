"""The opt-in full experience opens its Welcome book once."""
import harness as H

# The lean default does not interrupt a fresh desktop with Welcome.
d = H.make_desk()
assert not d.shell.state.get("help_shown")
n0 = len(d.wm.windows)
d._first_run_help()
assert not d.shell.state.get("help_shown")
assert len(d.wm.windows) == n0, "lean default opened Welcome"

# Once the full experience is active, Welcome opens and records its marker.
d.shell.set_full_experience(True)
d._first_run_help()
assert d.shell.state.get("help_shown") is True, "marker not persisted"
assert len(d.wm.windows) == n0 + 1, "Help did not open on first run"
help_win = H.find_window(d, "Help")
assert help_win is not None, "the opened window is not Help"
welcome = help_win.body.plain()
assert "F11" in welcome and "content-only fullscreen" in welcome, welcome
assert "page tabs" in welcome and "clickable pane chrome" in welcome, welcome

# A second call is a no-op — Help pops exactly once.
d._first_run_help()
assert len(d.wm.windows) == n0 + 1, "Help opened a second time"

# a desktop whose state already carries the marker never opens Help
d2 = H.make_desk()
d2.shell.state["help_shown"] = True
m0 = len(d2.wm.windows)
d2._first_run_help()
assert len(d2.wm.windows) == m0, "Help opened despite the marker"

print("ok")
