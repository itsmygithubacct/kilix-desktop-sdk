"""kilix desktop — idle screensavers.

A few classic full-framebuffer savers. Each is a small object with a
``step(dt) -> PIL RGB frame`` at the size it was built for; the Desk blits
the frame straight to the terminal while idle, and any input wakes it.
No animation loop of their own — the main loop drives the cadence.
"""
import random
import math

from PIL import Image, ImageDraw

import icons
import theme as T
import widgets as W


class _Saver:
    name = "saver"

    def __init__(self, size):
        self.w, self.h = size
        self.buf = Image.new("RGB", size, (0, 0, 0))

    def step(self, dt):               # pragma: no cover - overridden
        return self.buf


def _fade(shift):
    """LUT that decays a channel toward black (for motion trails)."""
    return lambda p: (p * shift) >> 8


class Mystify(_Saver):
    """Bouncing polylines leaving a fading trail (the Win95 'Mystify')."""
    name = "mystify"
    COLORS = [(255, 0, 255), (0, 255, 255), (255, 255, 0), (64, 160, 255)]

    def __init__(self, size, lines=2, verts=4):
        super().__init__(size)
        self.shapes = []
        for i in range(lines):
            pts = [[random.uniform(0, self.w), random.uniform(0, self.h),
                    random.uniform(-70, 70), random.uniform(-70, 70)]
                   for _ in range(verts)]
            self.shapes.append((pts, self.COLORS[i % len(self.COLORS)]))
        self._lut = _fade(205)        # ~0.80 per step

    def step(self, dt):
        self.buf = self.buf.point(self._lut)
        d = W.drawer(self.buf)
        for pts, color in self.shapes:
            for v in pts:
                v[0] += v[2] * dt
                v[1] += v[3] * dt
                if v[0] < 0 or v[0] > self.w:
                    v[2] = -v[2]
                    v[0] = min(max(v[0], 0), self.w)
                if v[1] < 0 or v[1] > self.h:
                    v[3] = -v[3]
                    v[1] = min(max(v[1], 0), self.h)
            poly = [(v[0], v[1]) for v in pts]
            d.line(poly + poly[:1], fill=color)
        return self.buf


class Starfield(_Saver):
    """A warp-speed starfield, stars streaming out from the centre."""
    name = "starfield"

    def __init__(self, size, n=200):
        super().__init__(size)
        self.cx, self.cy = self.w / 2, self.h / 2
        self.stars = [self._spawn() for _ in range(n)]

    def _spawn(self):
        return [random.uniform(-self.w, self.w),
                random.uniform(-self.h, self.h),
                random.uniform(0.1, 1.0)]

    def step(self, dt):
        buf = Image.new("RGB", (self.w, self.h), (0, 0, 0))
        d = W.drawer(buf)
        for s in self.stars:
            s[2] -= dt * 0.45
            if s[2] <= 0.03:
                s[:] = self._spawn()
                s[2] = random.uniform(0.6, 1.0)
            sx = self.cx + s[0] / s[2]
            sy = self.cy + s[1] / s[2]
            if 0 <= sx < self.w and 0 <= sy < self.h:
                b = min(255, int(50 + (1 - s[2]) * 240))
                r = 0 if s[2] > 0.5 else 1
                d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(b, b, b))
        self.buf = buf
        return buf


class Matrix(_Saver):
    """Falling green code rain."""
    name = "matrix"
    GLYPHS = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ<>*+-=/\\|"

    def __init__(self, size):
        super().__init__(size)
        self.cw, self.lh = 9, 14
        self.cols = max(1, self.w // self.cw)
        self.drops = [random.randint(-self.h // self.lh, 0)
                      for _ in range(self.cols)]
        self.speed = [random.uniform(6, 18) for _ in range(self.cols)]
        self._acc = [0.0] * self.cols
        self._lut = _fade(150)        # ~0.59: long fading tails

    def step(self, dt):
        self.buf = self.buf.point(self._lut)
        d = W.drawer(self.buf)
        for c in range(self.cols):
            self._acc[c] += self.speed[c] * dt
            if self._acc[c] < 1.0:
                continue
            self._acc[c] -= int(self._acc[c])
            self.drops[c] += 1
            if self.drops[c] * self.lh > self.h and random.random() < 0.08:
                self.drops[c] = 0
            x = c * self.cw
            y = self.drops[c] * self.lh
            d.text((x, y), random.choice(self.GLYPHS), font=T.FONT,
                   fill=(190, 255, 190))
            d.text((x, y - self.lh), random.choice(self.GLYPHS), font=T.FONT,
                   fill=(0, 150, 0))
        return self.buf


class Pipes(_Saver):
    """Colorful orthogonal pipes grown a segment at a time."""
    name = "pipes"
    COLORS = [(0, 220, 80), (40, 160, 255), (255, 196, 0),
              (230, 60, 220), (255, 80, 60)]

    def __init__(self, size):
        super().__init__(size)
        self.buf = Image.new("RGB", size, (4, 4, 12))
        self.x, self.y = self.w // 2, self.h // 2
        self.dx, self.dy = 1, 0
        self.color = random.choice(self.COLORS)
        self.acc = 0.0

    def step(self, dt):
        self.acc += max(0.02, dt) * 24
        d = ImageDraw.Draw(self.buf)
        while self.acc >= 1:
            self.acc -= 1
            old = self.x, self.y
            self.x += self.dx * 8
            self.y += self.dy * 8
            if not (8 <= self.x < self.w - 8 and 8 <= self.y < self.h - 8):
                self.x, self.y = random.randrange(8, max(9, self.w - 8)), \
                    random.randrange(8, max(9, self.h - 8))
                old = self.x, self.y
                self.color = random.choice(self.COLORS)
            d.line([old, (self.x, self.y)], fill=self.color, width=5)
            d.ellipse([self.x - 3, self.y - 3, self.x + 3, self.y + 3],
                      fill=self.color, outline=(255, 255, 255))
            if random.random() < 0.35:
                self.dx, self.dy = random.choice(
                    [(self.dy, -self.dx), (-self.dy, self.dx)])
        return self.buf


class Maze(_Saver):
    """Overhead maze with a wandering yellow explorer."""
    name = "maze"

    def __init__(self, size):
        super().__init__(size)
        self.cell = 16
        self.cols = max(4, self.w // self.cell)
        self.rows = max(4, self.h // self.cell)
        self.grid = [[15 for _ in range(self.cols)] for _ in range(self.rows)]
        self._carve()
        self.x = self.y = 0
        self.acc = 0.0

    def _carve(self):
        # wall bits N/E/S/W; recursive-backtracker without recursion.
        stack, seen = [(0, 0)], {(0, 0)}
        dirs = [(0, -1, 1, 4), (1, 0, 2, 8),
                (0, 1, 4, 1), (-1, 0, 8, 2)]
        while stack:
            x, y = stack[-1]
            choices = [(dx, dy, bit, opposite) for dx, dy, bit, opposite in dirs
                       if 0 <= x + dx < self.cols and 0 <= y + dy < self.rows
                       and (x + dx, y + dy) not in seen]
            if not choices:
                stack.pop()
                continue
            dx, dy, bit, opposite = random.choice(choices)
            nx, ny = x + dx, y + dy
            self.grid[y][x] &= ~bit
            self.grid[ny][nx] &= ~opposite
            seen.add((nx, ny))
            stack.append((nx, ny))

    def _moves(self):
        walls = self.grid[self.y][self.x]
        values = []
        if not walls & 1: values.append((0, -1))
        if not walls & 2: values.append((1, 0))
        if not walls & 4: values.append((0, 1))
        if not walls & 8: values.append((-1, 0))
        return values

    def step(self, dt):
        self.acc += max(0.02, dt) * 4
        while self.acc >= 1:
            self.acc -= 1
            dx, dy = random.choice(self._moves())
            self.x, self.y = self.x + dx, self.y + dy
        image = Image.new("RGB", (self.w, self.h), (0, 0, 0))
        d = ImageDraw.Draw(image)
        c = self.cell
        for y, row in enumerate(self.grid):
            for x, walls in enumerate(row):
                x0, y0 = x * c, y * c
                if walls & 1: d.line((x0, y0, x0 + c, y0), fill=(0, 90, 255))
                if walls & 2: d.line((x0 + c, y0, x0 + c, y0 + c), fill=(0, 90, 255))
                if walls & 4: d.line((x0, y0 + c, x0 + c, y0 + c), fill=(0, 90, 255))
                if walls & 8: d.line((x0, y0, x0, y0 + c), fill=(0, 90, 255))
        cx, cy = self.x * c + c // 2, self.y * c + c // 2
        d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(255, 255, 0))
        self.buf = image
        return image


class Marquee(_Saver):
    name = "marquee"

    def __init__(self, size):
        super().__init__(size)
        self.x = float(self.w)
        self.phase = 0.0

    def step(self, dt):
        self.x -= max(0.02, dt) * 90
        self.phase += max(0.02, dt) * 2
        text = "Kilix 95 — where do you want to go today?"
        width = T.text_w(T.BOLD, text)
        if self.x < -width:
            self.x = float(self.w)
        image = Image.new("RGB", (self.w, self.h), (0, 0, 0))
        d = ImageDraw.Draw(image)
        y = int(self.h / 2 + math.sin(self.phase) * max(8, self.h / 5))
        d.text((int(self.x) + 2, y + 2), text, font=T.BOLD, fill=(0, 0, 128))
        d.text((int(self.x), y), text, font=T.BOLD, fill=(255, 255, 0))
        self.buf = image
        return image


class FlyingKilix(_Saver):
    name = "flying kilix"

    def __init__(self, size):
        super().__init__(size)
        self.sprites = [[random.randrange(max(1, self.w - 32)),
                         random.randrange(max(1, self.h - 32)),
                         random.choice((-55, -40, 40, 55)),
                         random.choice((-45, -32, 32, 45))]
                        for _ in range(9)]
        self.logo = icons.get("flame", 32)

    def step(self, dt):
        dt = max(0.02, dt)
        image = Image.new("RGB", (self.w, self.h), (0, 0, 0))
        for sprite in self.sprites:
            sprite[0] += sprite[2] * dt
            sprite[1] += sprite[3] * dt
            if sprite[0] < 0 or sprite[0] > self.w - 32:
                sprite[2] *= -1
                sprite[0] = max(0, min(self.w - 32, sprite[0]))
            if sprite[1] < 0 or sprite[1] > self.h - 32:
                sprite[3] *= -1
                sprite[1] = max(0, min(self.h - 32, sprite[1]))
            image.paste(self.logo, (int(sprite[0]), int(sprite[1])), self.logo)
        self.buf = image
        return image


class Blank(_Saver):
    name = "blank"


SAVERS = [Mystify, Starfield, Matrix, Pipes, Maze, Marquee, FlyingKilix, Blank]

DISPLAY_NAMES = {
    "mystify": "Mystify", "starfield": "Starfield", "matrix": "Matrix",
    "pipes": "Pipes", "maze": "Maze", "marquee": "Marquee",
    "flying kilix": "Flying Kilix", "blank": "Blank",
}


def names():
    return [DISPLAY_NAMES[cls.name] for cls in SAVERS]


def pick(size, name=None):
    """Return the named saver, or a random saver when no name is selected."""
    wanted = str(name or "").strip().lower()
    for cls in SAVERS:
        if wanted in (cls.name, DISPLAY_NAMES[cls.name].lower()):
            return cls(size)
    return random.choice(SAVERS)(size)
