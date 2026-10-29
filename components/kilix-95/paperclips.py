"""Optional focus-gated paperclip desktop, with bounded background sampling."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import threading
import time

from PIL import Image


ASSETS = Path(__file__).parent / 'assets' / 'wallpapers'
BASE = ASSETS / 'kilix-firekitten-dusk.png'
LEVELS = (0, 5, 10, 20, 30, 60, 90, 100)
INTERVALS = (60, 300, 600, 1800)


def interval(value):
    return value if type(value) is int and value in INTERVALS else 300


def scene_level(percent):
    return max(level for level in LEVELS if level <= max(0, min(100, percent)))


def counters(root=Path('/proc')):
    """Read local kernel counters; guest time is already included in user time."""
    with (root / 'stat').open() as stream:
        fields = stream.readline().split()
    if fields[0] != 'cpu' or len(fields) < 5:
        raise ValueError('No aggregate CPU counters')
    cpu = [int(value) for value in fields[1:9]]
    total, idle = sum(cpu), cpu[3] + (cpu[4] if len(cpu) > 4 else 0)
    memory = {}
    for line in (root / 'meminfo').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('SwapTotal', 'SwapFree'):
            memory[key] = int(value.split()[0]) * 1024
    pages = sum(int(line.split()[1]) for line in
                (root / 'vmstat').read_text().splitlines()
                if line.startswith(('pswpin ', 'pswpout ')))
    return total, idle, memory.get('SwapTotal', 0), memory.get('SwapFree', 0), pages


def measure(cancel, root=Path('/proc'), clock=time.monotonic):
    """One one-second sample, on a worker. Nothing polls between scheduled samples."""
    try:
        if cancel.is_set():
            return None
        first, started = counters(root), clock()
        if cancel.wait(1):
            return None
        last, elapsed = counters(root), clock() - started
        delta = last[0] - first[0]
        if delta <= 0 or elapsed <= 0:
            return None
        busy = max(0, min(100, 100 * (1 - (last[1] - first[1]) / delta)))
        used = max(0, last[2] - last[3])
        traffic = max(0, last[4] - first[4]) * os.sysconf('SC_PAGE_SIZE') / elapsed
        hot = (used >= 256 * 1024**2 and last[2] > 0 and used >= last[2] / 2
               or traffic >= 8 * 1024**2)
        return busy, bool(hot)
    except (OSError, ValueError, IndexError, ZeroDivisionError):
        return None


class Controller:
    def __init__(self, shell, *, sampler=measure, clock=time.monotonic):
        self.shell, self.desk = shell, shell.desk
        self.sampler, self.clock = sampler, clock
        self.level, self.hot, self.frame = 0, False, 0
        self.next_sample = self.next_frame = 0
        self.future = self.executor = None
        self.cancel = None
        self.frames = None
        self.offsets = []
        self.frame_size = None
        self.closed = False
        self.active = False
        self.settings = None

    def enabled(self):
        return (self.shell.state.get('paperclips_enabled', True) is True
                and not self.shell.state.get('wall_custom', False))

    def focused(self):
        return (self.desk.frontend_focused and not self.desk.saving
                and not self.desk.bsod)

    def wallpaper(self):
        if not self.enabled():
            return None
        return str(BASE if self.level == 0 else ASSETS / f'kilix-paperclips-{self.level}.png')

    def tick(self, _now=None):
        if self.closed:
            return
        now = self.clock()
        config = (self.enabled(), self.shell.state.get('paperclips_animate', True) is True,
                  interval(self.shell.state.get('paperclips_interval', 300)))
        if config != self.settings:
            self.settings = config
            # Changed settings apply immediately; an in-flight result is discarded.
            self.next_sample = now
            self.active = False
            if self.cancel is not None:
                self.cancel.set()
            self.shell._wall = None
            self.shell.invalidate()
        visible = config[0] and self.focused()
        if not visible:
            self.active = False
            if self.cancel is not None:
                self.cancel.set()
            if self.future is not None and self.future.done():
                self.future = None
            return
        if self.future is not None and self.future.done():
            result = self.future.result()
            self.future = None
            if result is not None and self.active and not self.cancel.is_set():
                level, hot = scene_level(result[0]), result[1]
                if (level, hot) != (self.level, self.hot):
                    self.level, self.hot = level, hot
                    self.shell._wall = None
                    self.shell.invalidate()
        self.active = True
        if self.future is None and now >= self.next_sample:
            self.next_sample = now + config[2]
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='paperclip-load')
            self.cancel = threading.Event()
            self.future = self.executor.submit(self.sampler, self.cancel)
        if config[1] and now >= self.next_frame:
            self.next_frame = now + 2
            self.frame = 1 - self.frame
            self.shell.invalidate()

    def draw(self, image):
        if not self.enabled():
            return
        # A distant machine on the back-left hill, clear of the foreground.
        size = max(32, min(112, int(image.width * .065)))
        if self.frame_size != size:
            self.frame_size = size
            self.frames = []
            self.offsets = []
            try:
                with Image.open(ASSETS / 'paperclip-optimizer.png') as sheet:
                    sheet = sheet.convert('RGBA')
                    w, h = sheet.width // 2, sheet.height // 2
                    anchors = []
                    for row in range(2):
                        for col in range(2):
                            frame = sheet.crop((col*w, row*h, (col+1)*w, (row+1)*h))
                            # Align the solid feet, not the moving crank or steam.
                            floor = int(h * .76)
                            feet = frame.getchannel('A').point(lambda a: 255 if a >= 64 else 0)
                            box = feet.crop((0, floor, w, h)).getbbox()
                            anchors.append(((box[0]+box[2])/2, floor+box[3]) if box else (w/2, h))
                            self.frames.append(frame.resize((size, size), Image.Resampling.LANCZOS))
                    self.offsets = [(round((anchors[0][0]-x)*size/w),
                                     round((anchors[0][1]-y)*size/h)) for x, y in anchors]
            except OSError:
                self.frames = []
        if self.frames:
            index = 2 * int(self.hot) + self.frame
            sprite = self.frames[index]
            dx, dy = self.offsets[index]
            import theme
            wall_height = image.height - theme.TASKBAR_H
            image.paste(sprite, (int(image.width * .125) + dx,
                                int(wall_height * .53) - size + dy), sprite)

    def close(self):
        self.closed = True
        if self.cancel is not None:
            self.cancel.set()
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)
