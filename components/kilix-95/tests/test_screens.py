"""Startup/shutdown system screens."""

import harness as H
import theme as T


d = H.make_desk(size=(1280, 720))
before = d.fb.copy()

d._show_system_screen("startup", 0)

assert d.fb.size == (1280, 720)
assert d.fb.tobytes() != before.tobytes(), "startup screen did not update fb"
assert d.fb.getpixel((d.w // 2, d.h // 2)) != T.DESKTOP
assert d.dirty is True, "desktop should render after startup screen delay"

shutdown = d._system_screen("shutdown")
assert shutdown.size == (1280, 720)
assert shutdown.getpixel((d.w // 2, d.h // 2)) != T.DESKTOP


class FakeTerm:
    cols = 80
    rows = 25
    cell_w = 12
    cell_h = 20

    def __init__(self):
        self.writes = 0

    def write(self, data):
        self.writes += 1


term = FakeTerm()
live = H.desk_main.Desk(term=term)
live._show_system_screen("startup", 0.01)
assert term.writes >= 2, "startup screen should re-blit while it is visible"
live.cleanup_shm()

print("ok")
