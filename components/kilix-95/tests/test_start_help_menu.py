"""Start menu exposes the Help section and routes each Help entry."""
import harness as H
import theme as T


def _find(items, label):
    for it in items:
        if it.label == label:
            return it
    return None


def _labels(items):
    return [it.label for it in items if it.label != "-"]


d = H.make_desk()
d.taskbar.open_start_menu()
top = d.menus.stack[0].items

help_item = _find(top, "Help")
assert help_item is not None and help_item.submenu, _labels(top)
help_sub = help_item.submenu
assert "System Manual" in _labels(help_sub), _labels(help_sub)
assert "List" in _labels(help_sub), _labels(help_sub)
assert "Pleb Recovery Guide" in _labels(help_sub), _labels(help_sub)
assert "Kilix" in _labels(help_sub), _labels(help_sub)
assert "Terminal" in _labels(help_sub), _labels(help_sub)
assert "Help Topics" in _labels(help_sub), _labels(help_sub)

seen = []
d.shell.open_app = lambda name, arg=None: seen.append((name, arg))
d.shell.open_pleb_recovery = lambda: seen.append(("pleb-recovery", None))

_find(help_sub, "System Manual").action()
_find(help_sub, "List").action()
_find(help_sub, "Pleb Recovery Guide").action()
_find(help_sub, "Help Topics").action()
assert seen == [("manual", "search"), ("manual", "list"),
                ("pleb-recovery", None), ("winhelp", None)], seen

seen.clear()
kilix = _find(help_sub, "Kilix").submenu
assert _labels(kilix) == ["Kilix", T.PRODUCT_NAME, "Pleb", "Plebian-OS"]
for it in kilix:
    it.action()
assert seen == [("winhelp", "kilix"), ("winhelp", "kilix95"),
                ("winhelp", "pleb"), ("winhelp", "plebianos")], seen

seen.clear()
terminal = _find(help_sub, "Terminal").submenu
assert _labels(terminal) == ["Terminal", "tmux", "bash"]
for it in terminal:
    it.action()
assert seen == [("winhelp", "terminal"), ("winhelp", "tmux"),
                ("winhelp", "bash")], seen

print("ok")
