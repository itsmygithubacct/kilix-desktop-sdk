#include "kitty_terminal_session.h"

#include <errno.h>
#include <string.h>
#include <unistd.h>

void kittyts_options_init(kittyts_options *options)
{
    if (options == NULL) return;
    kittyfb_options_init(&options->framebuffer);
    kittykb_terminal_options_init(&options->keyboard);
    options->keyboard.flags = KITTYKB_FLAGS_KEY_STATE;
    options->keyboard.make_raw = false;
    options->keyboard.make_nonblocking = false;
}

void kittyts_session_init(kittyts_session *session)
{
    if (session == NULL) return;
    (void)memset(session, 0, sizeof *session);
    kittyfb_session_init(&session->framebuffer);
    kittykb_terminal_init(&session->keyboard);
    session->output_fd = -1;
}

int kittyts_start(kittyts_session *session, int input_fd, int output_fd,
                  const kittyts_options *options)
{
    kittyts_options defaults;
    const kittyts_options *selected = options;
    if (session == NULL || input_fd < 0 || output_fd < 0) {
        errno = EINVAL;
        return -1;
    }
    if (session->framebuffer_active || session->keyboard_active) {
        errno = EBUSY;
        return -1;
    }
    if (selected == NULL) {
        kittyts_options_init(&defaults);
        selected = &defaults;
    }
    session->shutdown_claimed = 0;
    session->output_fd = output_fd;
    if (kittyfb_start(&session->framebuffer, input_fd, output_fd,
                      &selected->framebuffer) != 0)
        return -1;
    session->framebuffer_active = true;
    if (kittykb_terminal_start(&session->keyboard, input_fd, output_fd,
                               &selected->keyboard) != 0) {
        int error = errno;
        kittyfb_stop(&session->framebuffer);
        session->framebuffer_active = false;
        session->output_fd = -1;
        errno = error;
        return -1;
    }
    session->keyboard_active = true;
    return 0;
}

static bool claim_shutdown(kittyts_session *session)
{
    if (session == NULL ||
        (!session->framebuffer_active && !session->keyboard_active))
        return false;
    return !__sync_lock_test_and_set(&session->shutdown_claimed, 1);
}

void kittyts_stop(kittyts_session *session)
{
    if (!claim_shutdown(session)) return;
    if (session->keyboard_active) {
        (void)kittykb_terminal_stop(&session->keyboard);
        session->keyboard_active = false;
    }
    if (session->framebuffer_active) {
        kittyfb_stop(&session->framebuffer);
        session->framebuffer_active = false;
    }
    session->output_fd = -1;
}

void kittyts_emergency_restore(kittyts_session *session)
{
    static const char keyboard_pop[] = "\x1b\\\x1b[<u";
    if (!claim_shutdown(session)) return;
    if (session->keyboard_active && session->output_fd >= 0)
        (void)write(session->output_fd, keyboard_pop, sizeof keyboard_pop - 1);
    if (session->framebuffer_active)
        kittyfb_emergency_restore(&session->framebuffer);
}

int kittyts_width(const kittyts_session *session)
{
    return session != NULL && session->framebuffer_active ?
           kittyfb_width(&session->framebuffer) : 0;
}

int kittyts_height(const kittyts_session *session)
{
    return session != NULL && session->framebuffer_active ?
           kittyfb_height(&session->framebuffer) : 0;
}

int kittyts_cell_width(const kittyts_session *session)
{
    return session != NULL && session->framebuffer_active ?
           kittyfb_cell_width(&session->framebuffer) : 0;
}

int kittyts_cell_height(const kittyts_session *session)
{
    return session != NULL && session->framebuffer_active ?
           kittyfb_cell_height(&session->framebuffer) : 0;
}

bool kittyts_check_resize(kittyts_session *session, int *width, int *height)
{
    return session != NULL && session->framebuffer_active &&
           kittyfb_check_resize(&session->framebuffer, width, height);
}

bool kittyts_present(kittyts_session *session, const uint8_t *rgba,
                     int width, int height)
{
    return session != NULL && session->framebuffer_active &&
           kittyfb_present(&session->framebuffer, rgba, width, height);
}

int kittyts_read_input(kittyts_session *session)
{
    if (session == NULL || !session->keyboard_active) {
        errno = EINVAL;
        return -1;
    }
    return kittykb_terminal_read(&session->keyboard);
}

bool kittyts_next_key_event(kittyts_session *session, kittykb_event *event)
{
    return session != NULL && session->keyboard_active &&
           kittykb_input_next(&session->keyboard.input, event);
}

bool kittyts_key_down(const kittyts_session *session, uint32_t key)
{
    return session != NULL && session->keyboard_active &&
           kittykb_input_key_down(&session->keyboard.input, key);
}

bool kittyts_has_release_events(const kittyts_session *session)
{
    return session != NULL && session->keyboard_active &&
           kittykb_input_has_release_events(&session->keyboard.input);
}
