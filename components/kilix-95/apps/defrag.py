"""Safe Windows 95-style disk map driven by real disk usage statistics."""

import random
import shutil
import time

import theme as T
import widgets as W
import wm


class _DiskMap(W.Widget):
    COLORS = [(0, 0, 160), (0, 160, 0), (180, 0, 0), (220, 220, 0),
              (255, 255, 255)]

    def __init__(self, x, y, w, h):
        super().__init__(x, y, w, h)
        self.blocks = []
        self.progress = 0
        self.analyze()

    def analyze(self):
        usage = shutil.disk_usage("/")
        used = usage.used / max(1, usage.total)
        count = max(1, (self.w - 8) // 8) * max(1, (self.h - 8) // 8)
        occupied = int(count * used)
        rng = random.Random(int(used * 100000) + 95)
        self.blocks = ([rng.choice(self.COLORS[:4]) for _ in range(occupied)]
                       + [self.COLORS[4]] * (count - occupied))
        rng.shuffle(self.blocks)
        self.progress = 0
        self.invalidate()

    def optimize_step(self, progress):
        self.progress = progress
        if progress:
            used = [color for color in self.blocks if color != self.COLORS[4]]
            free = [color for color in self.blocks if color == self.COLORS[4]]
            ordered = used + free
            amount = int(len(self.blocks) * progress / 100)
            self.blocks[:amount] = ordered[:amount]
        self.invalidate()

    def draw(self, d, img):
        T.sunken(d, self.x, self.y, self.x + self.w - 1, self.y + self.h - 1,
                 fill=T.WINDOW_BG)
        cols = max(1, (self.w - 8) // 8)
        for index, color in enumerate(self.blocks):
            row, col = divmod(index, cols)
            x, y = self.x + 4 + col * 8, self.y + 4 + row * 8
            if y + 6 >= self.y + self.h - 3:
                break
            d.rectangle((x, y, x + 6, y + 6), fill=color)


class Defragmenter(wm.Window):
    def __init__(self, desk, arg=None):
        super().__init__(desk, "Disk Defragmenter", 590, 410, icon="defrag")
        self.min_w, self.min_h = 440, 300
        cw, ch = self.client_size()
        self.add(W.Label(14, 12, "Drive C:  (host filesystem /)"))
        self.map = self.add(_DiskMap(12, 38, cw - 24, ch - 130))
        self.status = self.add(W.Label(14, ch - 76,
                                       "Analysis complete. No disk changes are made."))
        self.button = self.add(W.Button(cw - 202, ch - 46, 92, 23,
                                        "Analyze", cb=self._analyze))
        self.start = self.add(W.Button(cw - 102, ch - 46, 90, 23,
                                       "Defragment", default=True,
                                       cb=self._start))
        self.started = None

    def _analyze(self):
        self.map.analyze()
        usage = shutil.disk_usage("/")
        percent = usage.used * 100 / max(1, usage.total)
        self.status.set(f"Drive is {percent:.1f}% used. Visualization refreshed.")

    def _start(self):
        if self.started is not None:
            return
        self.started = time.time()
        self.start.enabled = self.button.enabled = False
        self.desk.tick_hooks.append(self._tick)
        self.desk.busy = True
        self.status.set("Rearranging the visualization… (host disk is untouched)")

    def _tick(self, now):
        progress = min(100, int((now - self.started) * 34))
        self.map.optimize_step(progress)
        self.status.set(f"{progress}% complete — host disk remains untouched.")
        if progress >= 100:
            self.started = None
            if self._tick in self.desk.tick_hooks:
                self.desk.tick_hooks.remove(self._tick)
            self.start.enabled = self.button.enabled = True
            self.desk.busy = False
            self.status.set("Defragmentation display complete. No disk changes were made.")

    def close(self):
        if self._tick in self.desk.tick_hooks:
            self.desk.tick_hooks.remove(self._tick)
        self.desk.busy = False
        super().close()

    def on_resize(self):
        cw, ch = self.client_size()
        self.map.w, self.map.h = cw - 24, ch - 130
        self.status.y = ch - 76
        self.button.x, self.button.y = cw - 202, ch - 46
        self.start.x, self.start.y = cw - 102, ch - 46
