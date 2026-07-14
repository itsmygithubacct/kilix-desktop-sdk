"""Help viewer: selecting topics, direct topics and live links."""
import harness as H
from apps.winhelp import Help, BOOK, BASH_MANUAL, TMUX_MANUAL, TMUX_REPO


def _row_y(win, i):
    gx, gy = win.client_origin()
    return gx, gy + win.topics.y + 2 + i * win.topics.RH + 3


d = H.make_desk()
win = Help(d)
d.wm.add(win)

# opens on the first topic
assert win.topic == BOOK[0][0], win.topic
first_text = win.body.plain()
assert "Welcome to kilix 95" in first_text

# select "Keyboard shortcuts" in the list -> content pane changes
kb = next(i for i, (k, *_ ) in enumerate(BOOK) if k == "keys")
gx, ry = _row_y(win, kb)
H.click(d, gx + 20, ry)
assert win.topic == "keys", win.topic
kb_text = win.body.plain()
assert kb_text != first_text
assert "Alt+F4" in kb_text and "Ctrl+Alt+Q" in kb_text
assert win.b_back.enabled and not win.b_fwd.enabled

# Back returns to the first topic; Forward re-enabled
gx, gy = win.client_origin()
H.click(d, gx + win.b_back.x + 4, gy + win.b_back.y + 4)
assert win.topic == BOOK[0][0], win.topic
assert win.body.plain() == first_text
assert win.b_fwd.enabled

# Forward walks the visited trail again
H.click(d, gx + win.b_fwd.x + 4, gy + win.b_fwd.y + 4)
assert win.topic == "keys", win.topic

# the pane scrolls without error
H.wheel(d, gx + win.body.x + 20, gy + win.body.y + 20, dz=1)
d.dirty = True
d.render()

# Start-menu how-to entries can open directly to a specific topic.
bash = Help(d, "bash")
assert bash.topic == "bash", bash.topic
assert "history" in bash.body.plain()

manual = Help(d, "systemmanual")
assert manual.topic == "systemmanual", manual.topic
assert "Start > Help > System Manual" in manual.body.plain()

kilix = Help(d, "kilix")
assert kilix.topic == "kilix", kilix.topic
kilix_text = kilix.body.plain()
assert "Kitty graphics-protocol app" in kilix_text, kilix_text
assert "page strip" in kilix_text and "clickable pane title bar" in kilix_text
assert "press F11 again" in kilix_text, kilix_text

fallback = Help(d, "nonesuch")
assert fallback.topic == BOOK[0][0], fallback.topic


def _click_body_link(win, label):
    win.body._relayout()
    for i, line in enumerate(win.body._lines):
        font, xoff, text, _bullet, url = line
        if url and label in text:
            rows = win.body._rows()
            if i < win.body.sb.pos:
                win.body.sb.pos = i
            elif i >= win.body.sb.pos + rows:
                win.body.sb.pos = i - rows + 1
            gx, gy = win.client_origin()
            y = gy + win.body.y + win.body.PAD + (
                i - win.body.sb.pos) * win.body.LH + 4
            H.click(d, gx + win.body.x + xoff + 2, y)
            return
    raise AssertionError(f"no link {label!r}")


# Live links in authored how-to pages open through the default browser helper.
seen = []
d.shell.open_default_browser_tab = lambda url, title=None: seen.append(
    (url, title))
tmux = Help(d, "tmux")
d.wm.add(tmux)
_click_body_link(tmux, "tmux project")
_click_body_link(tmux, "tmux manual")
assert seen == [(TMUX_REPO, "tmux project"), (TMUX_MANUAL, "tmux manual")], seen

bash = Help(d, "bash")
d.wm.add(bash)
_click_body_link(bash, "GNU Bash manual")
assert seen[-1] == (BASH_MANUAL, "GNU Bash manual"), seen

print("ok")
