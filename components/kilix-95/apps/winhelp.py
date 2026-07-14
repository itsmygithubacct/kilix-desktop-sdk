"""kilix desktop — Help. A two-pane topic viewer over a book of articles.

Left: a ListBox of topics. Right: a scrollable rich-text pane (wrapped
paragraphs, bold headings, bullet lists). Back/Forward walk visited topics.
"""
import theme as T
import widgets as W
import wm

TB_Y = 2                             # toolbar row
TB_H = 26
LIST_W = 158
LINK = (0, 0, 170)

KILIX_REPO = "https://github.com/itsmygithubacct/kilix"
KILIX95_REPO = "https://github.com/itsmygithubacct/kilix-95"
PLEB_REPO = "https://github.com/itsmygithubacct/pleb"
PLEBIAN_OS_REPO = "https://github.com/itsmygithubacct/plebian-os"
BASH_MANUAL = "https://www.gnu.org/software/bash/manual/bash.html"
BASH_REPO = "https://git.savannah.gnu.org/cgit/bash.git"
TMUX_REPO = "https://github.com/tmux/tmux"
TMUX_MANUAL = "https://man.openbsd.org/tmux.1"
LINUX_MANPAGES = "https://www.kernel.org/doc/man-pages/"

# ── the book: key -> (title, [blocks]); block = (kind, text) ─────────────────
# kind: "h" heading, "p" paragraph, "b" bullet item, "l" live link.
def build_book():
    product = T.PRODUCT_NAME
    return [
        ("welcome", f"Welcome to {product}", [
            ("h", f"Welcome to {product}"),
            ("p", f"{product} is a pixel desktop in the {T.STYLE_NAME} classic: "
                  "wallpaper, icons you double-click, draggable windows, and a "
                  "Start button in the corner."),
            ("p", "Pick a topic on the left to learn your way around. Use Back "
                  "and Forward to retrace the topics you have read."),
            ("b", "Desktop basics — icons, selection, the taskbar."),
            ("b", "Using the Start menu — launch programs and games."),
            ("b", "Managing windows — move, size, minimize, close."),
            ("b", "Keyboard shortcuts — do it all from the keys."),
            ("b", "F11 — use content-only fullscreen for `kilix run` and "
                  "Kitty graphics-protocol apps. Kilix hides its page tabs and "
                  "clickable pane chrome until F11 restores them."),
            ("b", "Control Panel and Themes — make the desktop your own."),
            ("b", "My Computer, Network Neighborhood, and My Briefcase."),
            ("p", "Did you know? Right-click almost anywhere for Properties, "
                  "or choose MS-DOS Prompt to start the managed DOSBox prompt."),
        ]),
        ("desktop", "Desktop basics", [
            ("h", "Desktop basics"),
            ("p", "The desktop is the surface behind every window. It holds "
                  "shortcut icons; double-click one to open it."),
            ("b", "Single-click selects an icon; double-click opens it."),
            ("b", "Right-click the desktop for New, Refresh and other commands."),
            ("b", "Drag a rubber-band box to select several icons at once."),
            ("p", "The taskbar along the bottom shows a button for every open "
                  "window. Click a button to raise that window or to restore it "
                  "if it has been minimized."),
        ]),
        ("startmenu", "Using the Start menu", [
            ("h", "Using the Start menu"),
            ("p", "Click Start, or press Ctrl+Esc, to open the Start menu — the "
                  "one place that reaches everything on the system."),
            ("b", "Programs holds the accessories and a Games submenu."),
            ("b", "Programs also holds PowerToys, special folders, networking, "
                  "and the MS-DOS Prompt caller."),
            ("b", "Documents lists files you opened recently."),
            ("b", "Settings adjusts the desktop's look and behaviour."),
            ("b", "Help opens this guide, project how-tos, and the System "
                  "Manual browser for installed man pages."),
            ("b", "Live links in Help open with the system default browser in a "
                  "new tab, not with the Kilix browser renderer."),
            ("b", "Run launches a command; Shut Down ends the session."),
        ]),
        ("windows", "Managing windows", [
            ("h", "Managing windows"),
            ("p", "Every program runs in a window framed by a title bar and a "
                  "raised border."),
            ("b", "Drag the title bar to move a window."),
            ("b", "Drag an edge or corner to resize it."),
            ("b", "The title-bar buttons minimize, maximize and close."),
            ("b", "Double-click the title bar to maximize or restore."),
            ("p", "The active window has a highlighted title bar; click any "
                  "window to bring it to the front and make it active."),
        ]),
        ("keys", "Keyboard shortcuts", [
            ("h", "Keyboard shortcuts"),
            ("p", "These work anywhere on the desktop:"),
            ("b", "Ctrl+Esc — open the Start menu."),
            ("b", "Alt+Tab — switch between open windows."),
            ("b", "Alt+F4 — close the active window."),
            ("b", f"Ctrl+Alt+Q — quit the {product} desktop."),
            ("p", "Inside a window:"),
            ("b", "Tab and Shift+Tab — move between controls."),
            ("b", "Enter — activate the default button or selected item."),
            ("b", "Escape — cancel a dialog or close a menu."),
        ]),
        ("accessories", "The accessories", [
            ("h", "The accessories"),
            ("p", f"{product} ships a set of small programs, found under Start, "
                  "then Programs, then Accessories."),
            ("b", "Calculator — a standard arithmetic calculator with memory."),
            ("b", "Paint — a bitmap editor for original pixel art."),
            ("b", "Minesweeper — clear the field without hitting a mine."),
            ("b", "Solitaire — the classic patience card game."),
            ("b", "Character Map — browse and copy special characters."),
            ("p", "Open any of them and press F1, or read this Help book, to "
                  "learn more."),
        ]),
        ("controlpanel", "Control Panel and Themes", [
            ("h", "Control Panel and Themes"),
            ("p", "Control Panel gathers Display, Themes, Sounds, input, "
                  "Date/Time, Fonts, Printers, Network, hardware, System, and "
                  "PowerToys in one classic icon view."),
            ("b", "Display Properties changes wallpaper, patterns, appearance, "
                  "pointer scheme, screen saver, and compatibility era."),
            ("b", "The Windows 95, Kilix Space, Terminal Green, Dangerous "
                  "Creatures, Inside Your Computer, Plebian, and Kilix XP "
                  "themes use original generated art and sounds."),
            ("b", "Screen savers include Mystify, Starfield, Matrix, Pipes, "
                  "Maze, Marquee, Flying Kilix, and Blank."),
            ("b", "A screen-saver password is stored as a salted verifier; "
                  "Kilix 95 never changes the host login password."),
        ]),
        ("mycomputer", "My Computer and special folders", [
            ("h", "My Computer and special folders"),
            ("p", "My Computer collects the host filesystem, Home, Desktop, "
                  "mounted removable media, system folders, and a managed "
                  "read-only Kilix 95 CD-ROM."),
            ("b", "The floppy icon gives the authentic not-ready response until "
                  "a removable disk is mounted by the host."),
            ("b", "Printers discovers CUPS queues read-only and can add a safe "
                  "print-to-folder destination."),
            ("b", "Device Manager and Add New Hardware inspect devices without "
                  "loading drivers, mounting disks, or changing the host."),
        ]),
        ("network", "Network and Dial-Up Networking", [
            ("h", "Network and Dial-Up Networking"),
            ("p", "Network Neighborhood shows concrete SSH aliases and local "
                  "shares that you explicitly add."),
            ("b", "Opening an SSH computer starts the real ssh command in a "
                  "Kilix tab; opening a local share starts File Manager."),
            ("b", "Dial-Up Networking recreates the modem ritual and sound, "
                  "then hands off to the normal full-speed browser."),
            ("b", "The dial-up feature is presentation only and never changes "
                  "the machine's network configuration."),
        ]),
        ("briefcase", "Using My Briefcase", [
            ("h", "Using My Briefcase"),
            ("p", "My Briefcase safely synchronizes two folders. Preview shows "
                  "the proposed direction for every file before copying."),
            ("b", "It never propagates a deletion."),
            ("b", "It never overwrites a file changed on both sides; conflicts "
                  "are left untouched for you to resolve."),
            ("b", "Right-click a desktop or File Manager item and use Send To "
                  "for a simple non-overwriting copy to My Briefcase."),
        ]),
        ("powertoys", "PowerToys and classic polish", [
            ("h", "PowerToys and classic polish"),
            ("p", "PowerToys provides Command Prompt Here, Explore From Here, "
                  "QuickRes, DeskMenu, Send To, TweakUI, Round Clock, and the "
                  "safe Disk Defragmenter display."),
            ("b", "TweakUI can hide desktop icons, Quick Launch, or live window "
                  "contents during dragging."),
            ("b", "Outline dragging, minimize animation, busy pointers, menu "
                  "accelerators, and property sheets complete the period feel."),
            ("b", "Disk Defragmenter visualizes real usage but never moves host "
                  "data."),
        ]),
        ("systemmanual", "Using System Manual", [
            ("h", "Using System Manual"),
            ("p", "System Manual searches the man pages installed on this "
                  "machine. It is the quickest way to read command, library, "
                  "configuration-file, and administrator references without "
                  "leaving the desktop."),
            ("b", "Start > Help > System Manual opens a searchable manual-page "
                  "browser."),
            ("b", "Start > Help > List opens the same browser with the full "
                  "installed page list visible."),
            ("b", "Type part of a command name, such as `bash`, `ssh`, or "
                  "`tmux`, then press Enter or click Search."),
            ("b", "Select a result and click Open, or double-click the result, "
                  "to render the page in the text pane."),
            ("b", "Use the mouse wheel, Page Up, Page Down, Home, and End to "
                  "read long pages."),
            ("l", "Linux man-pages project", LINUX_MANPAGES),
        ]),
        ("kilix", "Using Kilix", [
            ("h", "Using Kilix"),
            ("p", "Kilix is the host terminal and app runner behind this "
                  "desktop. It opens terminal tabs, runs graphical programs "
                  "inside terminal panes, and provides desktop services."),
            ("b", "Use Start > Programs > Terminal for a normal shell tab."),
            ("b", "Use Start > Programs > Mux Terminal for a persistent mux "
                  "session."),
            ("b", "Use Start > Programs > Web Browser for the Kilix browser "
                  "path."),
            ("b", "`kilix run COMMAND` runs an X11 program in a contained "
                  "pane."),
            ("b", "Press F11 in a `kilix run` or Kitty graphics-protocol app "
                  "for content-only fullscreen. The Kilix page strip and "
                  "clickable pane title bar disappear; press F11 again to "
                  "restore the normal chrome and window geometry."),
            ("b", "`kilix browse URL` opens a URL through Kilix's browser "
                  "launcher."),
            ("b", "`kilix serve` starts the mux terminal service used by Mux "
                  "Terminal."),
            ("b", "Help-topic links use the system default browser through "
                  "`xdg-open`/`sensible-browser`, so repository links open like "
                  "normal web links."),
            ("l", "Kilix repository", KILIX_REPO),
        ]),
        ("kilix95", f"Using {product}", [
            ("h", f"Using {product}"),
            ("p", f"{product} is the desktop shell running inside Kilix. It "
                  "draws windows, menus, icons, and built-in apps as pixels in "
                  "the terminal."),
            ("b", "Start launches programs, settings, help, and shutdown "
                  "actions."),
            ("b", "Desktop icons are real files and launchers in the desktop "
                  "folder."),
            ("b", "Settings changes Kilix/Kitty appearance and desktop flavor."),
            ("b", "System Manual searches installed man pages."),
            ("b", "Help Topics is a two-pane guide: choose topics on the left "
                  "and follow blue underlined links from the right pane."),
            ("b", "Use Shut Down to leave the desktop cleanly."),
            ("l", f"{product} repository", KILIX95_REPO),
        ]),
        ("pleb", "Using Pleb", [
            ("h", "Using Pleb"),
            ("p", "Pleb owns the installed user session around Kilix: display "
                  "manager wiring, session startup, autologin/kiosk behavior, "
                  "and updates of the user-facing Kilix stack."),
            ("b", "`pleb install` installs or refreshes the session pieces."),
            ("b", "`pleb update` updates the session stack when available."),
            ("b", "On a Plebian-OS system, Start > System exposes Pleb update "
                  "actions when the helper is installed."),
            ("b", "If a session change does not appear immediately, restart "
                  "the desktop or session."),
            ("b", "Use Pleb when the login/session wiring is wrong; use Kilix "
                  "when the terminal/app runtime itself needs attention."),
            ("l", "Pleb repository", PLEB_REPO),
        ]),
        ("plebianos", "Using Plebian-OS", [
            ("h", "Using Plebian-OS"),
            ("p", "Plebian-OS is the Debian-based system image and installer "
                  "layer that provisions Kilix, Pleb, and this desktop."),
            ("b", "Use the system update entry under Start > System when it is "
                  "present."),
            ("b", "Use Reinstall dependencies only when the installed desktop "
                  "stack is missing required system packages."),
            ("b", "Use the shutdown/restart entries from Start so the desktop "
                  "can play its shutdown flow and restore the terminal."),
            ("b", "For disk, USB, dependency, or update work, verify the target "
                  "device or command before running it."),
            ("b", "If the desktop opens but external apps fail, check the "
                  "system dependencies for Xvfb, ffmpeg, browser packages, "
                  "audio, and Python modules."),
            ("l", "Plebian-OS repository", PLEBIAN_OS_REPO),
        ]),
        ("terminal", "Terminal basics", [
            ("h", "Terminal basics"),
            ("p", "A terminal runs command-line programs in a shell. Commands "
                  "usually read from standard input, write to standard output, "
                  "and report errors on standard error."),
            ("b", "`pwd` prints the current directory."),
            ("b", "`ls` lists files; `ls -la` includes hidden files and "
                  "details."),
            ("b", "`cd DIR` changes directory."),
            ("b", "Tab completes file and command names in many shells."),
            ("b", "Ctrl+C interrupts the foreground program; Ctrl+D sends end "
                  "of input."),
            ("b", "`command --help` often prints a quick usage summary."),
            ("b", "`man COMMAND` opens the terminal manual page; Start > Help "
                  "> System Manual opens the same kind of reference in a "
                  "desktop window."),
            ("b", "Use pipes like `producer | consumer` to send output from "
                  "one command into another."),
            ("l", "Linux man-pages project", LINUX_MANPAGES),
        ]),
        ("tmux", "Using tmux", [
            ("h", "Using tmux"),
            ("p", "tmux keeps terminal sessions alive and lets one terminal "
                  "hold multiple windows and panes."),
            ("b", "`tmux new -s NAME` starts a named session."),
            ("b", "`tmux attach -t NAME` reconnects to a session."),
            ("b", "`tmux ls` lists sessions; `tmux kill-session -t NAME` stops "
                  "one."),
            ("b", "The default prefix is Ctrl+B."),
            ("b", "Ctrl+B then C creates a window; Ctrl+B then N moves to the "
                  "next one."),
            ("b", "Ctrl+B then % splits vertically; Ctrl+B then \" splits "
                  "horizontally."),
            ("b", "Ctrl+B then D detaches without stopping the session."),
            ("l", "tmux project", TMUX_REPO),
            ("l", "tmux manual", TMUX_MANUAL),
        ]),
        ("bash", "Using bash", [
            ("h", "Using bash"),
            ("p", "bash is the default command shell on many Linux systems. It "
                  "runs commands, expands variables, keeps history, and "
                  "combines commands with pipes and redirection."),
            ("b", "`echo $NAME` prints an environment or shell variable."),
            ("b", "`export NAME=value` makes a variable available to child "
                  "processes."),
            ("b", "`history` shows recent commands; Ctrl+R searches them."),
            ("b", "`alias ll='ls -la'` creates a shortcut for the current "
                  "shell; put lasting aliases in `~/.bashrc`."),
            ("b", "`>` writes output to a file; `>>` appends."),
            ("b", "`2>` redirects error output."),
            ("b", "`set -euo pipefail` is useful in scripts when failures "
                  "should stop the script early."),
            ("b", "Quote paths with spaces, for example `cd \"My Folder\"`."),
            ("l", "GNU Bash manual", BASH_MANUAL),
            ("l", "Bash source repository", BASH_REPO),
        ]),
        ("tips", "Tips", [
            ("h", "Tips of the day"),
            ("b", "Right-click almost anything for a menu of what you can do."),
            ("b", "You can drag files onto the desktop to make shortcuts."),
            ("b", "Minimized windows are not closed — their taskbar button "
                  "brings them right back."),
            ("b", "Hold Ctrl while clicking icons to select several at once."),
            ("b", "The address bar in the File Manager accepts a typed path."),
        ]),
    ]


BOOK = build_book()


class _RichText(W.Widget):
    """Scrollable formatted-text pane: bold headings, wrapped paragraphs,
    bullets and live links with a hanging indent. Content blocks are
    (kind, text) or (kind, text, url) for links."""
    focusable = True
    LH = 15
    PAD = 6

    def __init__(self, x, y, w, h):
        super().__init__(x, y, w, h)
        self.blocks = []
        self.sb = W.VScroll()
        self._lines = []              # (font, x_indent, text, bullet, url)
        self._key = None              # (id(blocks), width) cache guard

    def set_blocks(self, blocks):
        self.blocks = blocks
        self.sb.pos = 0
        self._key = None
        self.invalidate()

    def plain(self):
        """The rendered text as one string (for tests / simple search)."""
        return "\n".join(b[1] for b in self.blocks)

    def _avail(self):
        return self.w - 2 * self.PAD - T.SCROLL_W - 2

    def _wrap(self, font, text, maxw):
        out, cur = [], ""
        for word in text.split():
            trial = word if not cur else cur + " " + word
            if T.text_w(font, trial) <= maxw:
                cur = trial
            else:
                if cur:
                    out.append(cur)
                cur = word
        if cur:
            out.append(cur)
        return out or [""]

    def _relayout(self):
        avail = self._avail()
        lines = []
        for block in self.blocks:
            kind, text = block[0], block[1]
            url = block[2] if kind == "l" and len(block) > 2 else None
            if kind == "h":
                for ln in self._wrap(T.BOLD, text, avail):
                    lines.append((T.BOLD, self.PAD, ln, False, None))
                lines.append((T.FONT, self.PAD, "", False, None))
            elif kind == "b":
                wrapped = self._wrap(T.FONT, text, avail - 14)
                for i, ln in enumerate(wrapped):
                    lines.append((T.FONT, self.PAD + 14, ln, i == 0, None))
                lines.append((T.FONT, self.PAD, "", False, None))
            elif kind == "l":
                wrapped = self._wrap(T.FONT, text, avail - 14)
                for ln in wrapped:
                    lines.append((T.FONT, self.PAD + 14, ln, False, url))
                lines.append((T.FONT, self.PAD, "", False, None))
            else:
                for ln in self._wrap(T.FONT, text, avail):
                    lines.append((T.FONT, self.PAD, ln, False, None))
                lines.append((T.FONT, self.PAD, "", False, None))
        self._lines = lines

    def _rows(self):
        return max(1, (self.h - 2 * self.PAD) // self.LH)

    def draw(self, d, img):
        key = (id(self.blocks), self.w)
        if key != self._key:
            self._relayout()
            self._key = key
        x0, y0 = self.x, self.y
        x1, y1 = x0 + self.w - 1, y0 + self.h - 1
        T.sunken(d, x0, y0, x1, y1)
        self.sb.total, self.sb.page = len(self._lines), self._rows()
        self.sb.clamp()
        self.sb.place(x1 - T.SCROLL_W - 1, y0 + 2, self.h - 4)
        avail = self._avail()
        for i in range(self._rows()):
            idx = self.sb.pos + i
            if idx >= len(self._lines):
                break
            font, xoff, text, bullet, url = self._lines[idx]
            yy = y0 + self.PAD + i * self.LH
            if bullet:
                d.rectangle([x0 + self.PAD + 3, yy + 4,
                             x0 + self.PAD + 7, yy + 8], fill=T.TEXT)
            if url:
                d.text((x0 + self.PAD + 3, yy), ">", font=T.FONT, fill=LINK)
            if text:
                shown = T.ellipsize(font, text, avail)
                fill = LINK if url else T.TEXT
                d.text((x0 + xoff, yy), shown, font=font, fill=fill)
                if url:
                    tw = min(T.text_w(font, shown), avail)
                    d.line([(x0 + xoff, yy + 13), (x0 + xoff + tw, yy + 13)],
                           fill=fill)
        if self.sb.total > self.sb.page:
            self.sb.draw(d)

    def _link_at(self, px, py):
        if not self._lines:
            self._relayout()
        rel_y = py - self.y - self.PAD
        if rel_y < 0:
            return None
        row = rel_y // self.LH
        if not (0 <= row < self._rows()):
            return None
        idx = self.sb.pos + row
        if not (0 <= idx < len(self._lines)):
            return None
        font, xoff, text, _bullet, url = self._lines[idx]
        if not url:
            return None
        x0 = self.x + xoff
        x1 = x0 + min(T.text_w(font, text), self._avail())
        if x0 <= px <= x1:
            return text, url
        return None

    def on_mouse(self, ev):
        if (self.sb.total > self.sb.page
                and (self.sb.hit(ev.x, ev.y) or self.sb.drag is not None)):
            if self.sb.on_mouse(ev):
                self.invalidate()
            return True
        if ev.wheel:
            self.sb.pos += ev.wheel * 3
            self.sb.clamp()
            self.invalidate()
            return True
        if ev.press and ev.btn == 1:
            hit = self._link_at(ev.x, ev.y)
            if hit and self.desk:
                label, url = hit
                self.desk.shell.open_default_browser_tab(url, label)
                return True
        return True

    def on_key(self, ev):
        step = {"ArrowUp": -1, "ArrowDown": 1,
                "PageUp": -self._rows(), "PageDown": self._rows()}.get(ev.key)
        if step is None:
            return False
        self.sb.pos += step
        self.sb.clamp()
        self.invalidate()
        return True


class Help(wm.Window):
    def __init__(self, desk, arg=None):
        self.book = build_book()
        self.blocks = {k: b for k, _, b in self.book}
        super().__init__(desk, f"Help Topics - {T.PRODUCT_NAME}", 560, 400,
                         icon="help")
        self.min_w, self.min_h = 380, 240
        self.hist, self.hist_i = [], -1
        cw, ch = self.client_size()
        self.b_back = self.add(W.Button(4, TB_Y + 2, 66, 22, "Back",
                                        icon="back", cb=lambda: self._go(-1)))
        self.b_fwd = self.add(W.Button(72, TB_Y + 2, 82, 22, "Forward",
                                       icon="forward", cb=lambda: self._go(+1)))
        gy = TB_Y + TB_H + 2
        gh = ch - gy - 4
        self.topics = self.add(W.ListBox(2, gy, LIST_W, gh,
                                         on_select=self._pick,
                                         on_activate=self._pick))
        self.body = self.add(_RichText(LIST_W + 6, gy, cw - LIST_W - 8, gh))
        self.topics.set_items([(None, title, key)
                               for key, title, _ in self.book])
        self.set_focus(self.topics)
        start = arg if arg in self.blocks else self.book[0][0]
        self._navigate(start)

    def on_resize(self):
        cw, ch = self.client_size()
        gy = TB_Y + TB_H + 2
        gh = ch - gy - 4
        self.topics.h = gh
        self.body.w, self.body.h = cw - LIST_W - 8, gh
        self.body._key = None

    def draw_client(self, d, img):
        cw, _ = self.client_size()
        T.raised_thin(d, 0, TB_Y, cw - 1, TB_Y + TB_H - 1)

    # ── navigation ──────────────────────────────────────────────────────────
    def _pick(self, item):
        if item[2] != self.topic:
            self._navigate(item[2])

    def _navigate(self, key):
        self.hist = self.hist[:self.hist_i + 1] + [key]
        self.hist_i = len(self.hist) - 1
        self._show(key)

    def _go(self, step):
        i = self.hist_i + step
        if 0 <= i < len(self.hist):
            self.hist_i = i
            self._show(self.hist[i])

    def _show(self, key):
        self.topic = key
        self.body.set_blocks(self.blocks[key])
        for i, it in enumerate(self.topics.items):
            if it[2] == key:
                self.topics.sel = i
                break
        self.b_back.enabled = self.hist_i > 0
        self.b_fwd.enabled = self.hist_i < len(self.hist) - 1
        self.invalidate()
