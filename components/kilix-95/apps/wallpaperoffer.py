"""The startup wizard offers the animated desktop without opting users in."""
from PIL import Image

import paperclips
import theme as T
import widgets as W
import wm


class Preview(W.Widget):
    def __init__(self, x, y, path):
        super().__init__(x, y, 268, 151)
        with Image.open(path) as image:
            self.image = image.convert('RGB').resize((self.w, self.h), Image.Resampling.LANCZOS)

    def draw(self, draw, image):
        image.paste(self.image, (self.x, self.y))
        draw.rectangle((self.x, self.y, self.x+self.w-1, self.y+self.h-1), outline=T.SHADOW)


class WallpaperOffer(wm.Window):
    def __init__(self, desk, continuation):
        super().__init__(desk, 'Plebian-OS setup — Desktop', 620, 370,
                         icon='display', resizable=False)
        self.add(W.Label(18, 14, 'Choose your desktop wallpaper'))
        self.add(Preview(18, 44, paperclips.REGULAR))
        self.add(Preview(318, 44, paperclips.ASSETS / 'kilix-paperclips-30.png'))
        self.add(W.Label(18, 207, 'Regular Plebian-OS wallpaper'))
        self.add(W.Label(318, 207, 'Firekitten and paperclip optimizer'))
        self.add(W.Label(18, 234, 'The optional scene samples load every five minutes while this desktop is focused.', font=T.SMALL))
        self.add(W.Label(18, 251, 'You can change or disable it later in Display Properties → Background.', font=T.SMALL))
        self.regular_button = self.add(W.Button(18, 278, 268, 26, 'Keep Plebian-OS',
                                               default=True, cb=lambda: self.choose(False)))
        self.paperclip_button = self.add(W.Button(318, 278, 268, 26, 'Use paperclips',
                                                 cb=lambda: self.choose(True)))
        self.status = self.add(W.Label(18, 317, '', color=T.SHADOW, font=T.SMALL))
        self.add(W.Button(496, 312, 90, 23, 'Later', cb=self.close))
        self.continuation = continuation
        self.continued = False
        self.set_focus(self.regular_button)

    def close(self):
        if self not in self.desk.wm.windows:
            return
        super().close()
        if not self.continued and self.desk.running:
            self.continued = True
            self.continuation()

    def choose(self, enabled):
        shell = self.desk.shell
        state = dict(shell.state, wallpaper_offer_answered=True,
                     paperclips_enabled=enabled, wall_custom=False, wall_mode='stretch',
                     wall_image=str(paperclips.BASE if enabled else paperclips.REGULAR))
        try:
            shell.state_store.save_dict(state)
        except Exception as error:
            self.status.set(('Could not save wallpaper choice: ' + str(error))[:77])
            return
        shell.state.update(state)
        shell._wall = None
        shell.invalidate()
        self.close()


def open_window(desk, continuation):
    for window in desk.wm.windows:
        if isinstance(window, WallpaperOffer):
            desk.wm.activate(window)
            return window
    window = WallpaperOffer(desk, continuation)
    desk.wm.add(window)
    return window
