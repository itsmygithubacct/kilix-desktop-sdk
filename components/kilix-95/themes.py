"""Original Kilix 95 Plus!-style theme packs."""

import os
import random

from PIL import Image, ImageDraw

import storage


THEMES = {
    "Windows 95": {
        "flavor": "95", "color": (0, 128, 128), "pattern": "None",
        "sound": "kilix 95", "cursor": "Standard", "saver": "Mystify",
    },
    "Kilix Space": {
        "flavor": "95", "color": (0, 0, 40), "pattern": "Stars",
        "sound": "kilix 95", "cursor": "Inverted", "saver": "Starfield",
    },
    "Terminal Green": {
        "flavor": "95", "color": (0, 32, 0), "pattern": "Circuit",
        "sound": "No Sounds", "cursor": "Black", "saver": "Matrix",
    },
    "Dangerous Creatures": {
        "flavor": "95", "color": (40, 20, 0), "pattern": "Scales",
        "sound": "kilix 95", "cursor": "Dinosaur", "saver": "Pipes",
    },
    "Inside Your Computer": {
        "flavor": "95", "color": (32, 32, 48), "pattern": "Circuit",
        "sound": "kilix 95", "cursor": "Standard", "saver": "Maze",
    },
    "Plebian": {
        "flavor": "95", "color": (72, 0, 72), "pattern": "Plaid",
        "sound": "kilix 95", "cursor": "Dinosaur",
        "saver": "Flying Kilix",
    },
    "Kilix XP": {
        "flavor": "xp", "color": (58, 110, 165), "pattern": "None",
        "sound": "kilix XP", "cursor": "Standard", "saver": "Starfield",
    },
}

PATTERNS = ["None", "Bricks", "Circuit", "Plaid", "Scales", "Stars"]
CURSORS = ["Standard", "Black", "Inverted", "Dinosaur"]


def _pattern(draw, name, size, fg):
    w, h = size
    if name == "Bricks":
        for y in range(0, h, 16):
            draw.line((0, y, w, y), fill=fg)
            off = 0 if (y // 16) % 2 else 12
            for x in range(off, w, 24):
                draw.line((x, y, x, min(h, y + 16)), fill=fg)
    elif name == "Circuit":
        for y in range(8, h, 24):
            draw.line((0, y, w, y), fill=fg)
            for x in range((y // 3) % 19, w, 38):
                draw.line((x, y, x, min(h, y + 10)), fill=fg)
                draw.rectangle((x - 1, y + 9, x + 2, y + 12), fill=fg)
    elif name == "Plaid":
        for x in range(0, w, 16):
            draw.line((x, 0, x, h), fill=fg)
        for y in range(0, h, 16):
            draw.line((0, y, w, y), fill=fg)
    elif name == "Scales":
        for y in range(0, h, 12):
            for x in range((-6 if (y // 12) % 2 else 0), w, 12):
                draw.arc((x, y - 6, x + 12, y + 6), 0, 180, fill=fg)
    elif name == "Stars":
        rng = random.Random(95)
        for _ in range(max(50, w * h // 900)):
            x, y = rng.randrange(w), rng.randrange(h)
            draw.point((x, y), fill=fg)
            if rng.random() < 0.15:
                draw.point((min(w - 1, x + 1), y), fill=fg)


def wallpaper(name, color, pattern):
    """Generate/cache an original tiled wallpaper for a theme selection."""
    safe = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    root = storage.data_dir("themes")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, safe + ".png")
    image = Image.new("RGB", (320, 240), tuple(color))
    draw = ImageDraw.Draw(image)
    fg = tuple(min(255, c + 48) for c in color)
    _pattern(draw, pattern, image.size, fg)
    image.save(path)
    return path


def apply(shell, name):
    if name not in THEMES:
        raise ValueError(f"Unknown theme: {name}")
    spec = THEMES[name]
    import sounds
    shell.set_flavor(spec["flavor"])
    state = shell.state
    state["theme"] = name
    state["wall_color"] = list(spec["color"])
    state["wall_pattern"] = spec["pattern"]
    state["wall_image"] = wallpaper(
        name, spec["color"], spec["pattern"]) if spec["pattern"] != "None" \
        else None
    state["wall_mode"] = "tile" if state["wall_image"] else "stretch"
    state["wall_custom"] = True
    state["cursor_scheme"] = spec["cursor"]
    state["saver_name"] = spec["saver"]
    state["sound_scheme"] = spec["sound"]
    state["era_profile"] = ("Kilix XP" if name == "Kilix XP" else
                            "Windows 95 RTM" if name == "Windows 95" else
                            "Windows 95 Plus!")
    state["show_quick_launch"] = name == "Kilix XP"
    state["full_window_drag"] = name != "Windows 95"
    sounds.load_scheme(spec["sound"])
    shell._wall = None
    shell._save_state()
    shell.invalidate()
    return dict(spec)
