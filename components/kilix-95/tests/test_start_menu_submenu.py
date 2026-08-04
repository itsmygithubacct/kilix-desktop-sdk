"""An opened submenu survives the pointer leaving the row that opened it.

Win95 keeps a cascaded submenu on screen once it is open. This one used to
close the moment the pointer moved to any other item in the parent — including
a plain entry on the way down to the submenu — so reaching a submenu entry
meant tracing the parent row exactly and then crossing into the child without
drifting. The submenu now closes on a click outside it, or when another
submenu opens in its place.
"""
import harness as H


def _find(items, label):
    for item in items:
        if item.label == label:
            return item
    return None


def _row_center(menu, item):
    for candidate, (x0, y0, x1, y1) in menu.item_rects():
        if candidate is item:
            return (x0 + x1) // 2, (y0 + y1) // 2
    raise AssertionError(f"no row for {item.label!r}")


d = H.make_desk()
d.taskbar.open_start_menu()
root = d.menus.stack[0]
top = root.items

# A parent entry that cascades, and a plain one to drift onto.
parent = next(i for i in top if i.submenu is not None and i.enabled)
plain = next(i for i in top
             if i.submenu is None and i.enabled and i.label != "-")

# Hover the cascading entry: its submenu opens.
H.move(d, *_row_center(root, parent))
assert len(d.menus.stack) == 2, "hovering a cascade entry must open its submenu"
opened = d.menus.stack[-1]

# Drift onto a plain entry. The submenu must still be there.
H.move(d, *_row_center(root, plain))
assert len(d.menus.stack) == 2, "a submenu must not close because the pointer moved away"
assert d.menus.stack[-1] is opened, "the same submenu must still be open"

# Another cascade entry replaces it rather than stacking on top.
others = [i for i in top
          if i.submenu is not None and i.enabled and i is not parent]
if others:
    H.move(d, *_row_center(root, others[0]))
    assert len(d.menus.stack) == 2, "a second submenu replaces the first"
    assert d.menus.stack[-1] is not opened, "the replacement must be a new submenu"

# A click outside every menu closes the lot.
H.click(d, 1022, 766)   # bottom-right of the 1024x768 desk
assert not d.menus.stack, "clicking outside must close the menus"

print("ok test_start_menu_submenu")
