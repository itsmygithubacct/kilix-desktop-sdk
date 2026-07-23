#include "kitty_terminal_session.h"

#include <assert.h>
#include <errno.h>
#include <pty.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(void)
{
    kittyts_session session;
    kittyts_options options;
    kittykb_event event;
    struct winsize window = {24, 80, 640, 480};
    int master = -1;
    int slave = -1;

    kittyts_session_init(&session);
    kittyts_options_init(&options);
    assert(!options.keyboard.make_raw);
    assert(!options.keyboard.make_nonblocking);
    assert(options.keyboard.flags == KITTYKB_FLAGS_KEY_STATE);
    assert(kittyts_start(NULL, 0, 1, &options) == -1 && errno == EINVAL);

    assert(openpty(&master, &slave, NULL, NULL, &window) == 0);
    assert(ioctl(slave, TIOCSWINSZ, &window) == 0);
    options.framebuffer.probe_graphics = false;
    options.framebuffer.install_winch_handler = false;
    options.framebuffer.min_width = options.framebuffer.max_width = 320;
    options.framebuffer.min_height = options.framebuffer.max_height = 240;
    options.keyboard.probe_timeout_ms = 0;
    assert(kittyts_start(&session, slave, slave, &options) == 0);
    assert(kittyts_width(&session) == 320);
    assert(kittyts_height(&session) == 240);
    assert(kittyts_start(&session, slave, slave, &options) == -1 &&
           errno == EBUSY);

    assert(write(master, "\x1b[119;1:1u", 10) == 10);
    assert(kittyts_read_input(&session) >= 0);
    assert(kittyts_next_key_event(&session, &event));
    assert(event.key == 'w');
    assert(event.action == KITTYKB_ACTION_PRESS);

    kittyts_stop(&session);
    kittyts_stop(&session);
    assert(kittyts_width(&session) == 0);
    close(slave);
    close(master);
    puts("ok");
    return 0;
}
