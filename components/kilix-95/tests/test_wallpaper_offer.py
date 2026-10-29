"""The startup wallpaper choice is explicit, durable, and precedes model setup."""
import os
from unittest import mock

import harness as H
from apps import modelwizard
from apps.wallpaperoffer import open_window
import paperclips


for choice in (False, True):
    with H.desktop_dir(), mock.patch.dict(os.environ, {'KILIX_MODEL_WIZARD_OFFER': '1'}), \
            mock.patch.object(modelwizard, 'open_window') as models:
        desk = H.make_desk(size=(640, 480))
        assert not desk.paperclips.enabled()
        assert desk.shell.state['wall_image'] == str(paperclips.REGULAR)
        modelwizard.startup(desk)
        offer = H.find_window(desk, 'WallpaperOffer')
        assert offer and models.call_count == 0
        modelwizard.startup(desk)
        assert sum(type(w).__name__ == 'WallpaperOffer' for w in desk.wm.windows) == 1
        assert all(w.x >= 0 and w.y >= 0 and w.x+w.w <= offer.client_size()[0]
                   and w.y+w.h <= offer.client_size()[1] for w in offer.widgets)
        offer.choose(choice)
        assert models.call_count == 1 and offer not in desk.wm.windows
        state = desk.shell.state_store.load_dict()
        assert state['wallpaper_offer_answered'] and state['paperclips_enabled'] is choice
        assert desk.paperclips.enabled() is choice
        later = H.make_desk(size=(640, 480))
        assert later.paperclips.enabled() is choice
        assert later.shell.state['wall_image'] == str(paperclips.BASE if choice else paperclips.REGULAR)
        modelwizard.startup(later)
        assert H.find_window(later, 'WallpaperOffer') is None and models.call_count == 2

with H.desktop_dir():
    desk = H.make_desk()
    continuation = mock.Mock()
    offer = open_window(desk, continuation)
    with mock.patch.object(desk.shell.state_store, 'save_dict', side_effect=OSError('full')):
        offer.choose(True)
    assert offer in desk.wm.windows and not desk.paperclips.enabled()
    assert not desk.shell.state.get('wallpaper_offer_answered')
    continuation.assert_not_called()
    offer.close()
    offer.close()
    continuation.assert_called_once()
    assert not desk.shell.state.get('wallpaper_offer_answered')
    # An unanswered offer never silently overwrites an existing custom wallpaper.
    desk.shell.state.update(wall_custom=True, wall_image='/custom/landscape.png')
    offer = open_window(desk, mock.Mock())
    assert desk.shell.state['wall_image'] == '/custom/landscape.png'
    offer.close()
    continuation.reset_mock()
    offer = open_window(desk, continuation)
    desk.running = False
    offer.close()
    continuation.assert_not_called()
print('ok')
