#ifndef KITTY_TERMINAL_SESSION_H
#define KITTY_TERMINAL_SESSION_H

#include "kitty_framebuffer.h"
#include "kitty_keyboard_posix.h"

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define KITTYTS_VERSION_MAJOR 0
#define KITTYTS_VERSION_MINOR 1
#define KITTYTS_VERSION_PATCH 0

typedef struct kittyts_options {
    kittyfb_options framebuffer;
    kittykb_terminal_options keyboard;
} kittyts_options;

typedef struct kittyts_session {
    kittyfb_session framebuffer;
    kittykb_terminal keyboard;
    int output_fd;
    bool framebuffer_active;
    bool keyboard_active;
    volatile int shutdown_claimed;
} kittyts_session;

void kittyts_options_init(kittyts_options *options);
void kittyts_session_init(kittyts_session *session);

int kittyts_start(kittyts_session *session, int input_fd, int output_fd,
                  const kittyts_options *options);
void kittyts_stop(kittyts_session *session);
void kittyts_emergency_restore(kittyts_session *session);

int kittyts_width(const kittyts_session *session);
int kittyts_height(const kittyts_session *session);
int kittyts_cell_width(const kittyts_session *session);
int kittyts_cell_height(const kittyts_session *session);
bool kittyts_check_resize(kittyts_session *session, int *width, int *height);
bool kittyts_present(kittyts_session *session, const uint8_t *rgba,
                     int width, int height);

int kittyts_read_input(kittyts_session *session);
bool kittyts_next_key_event(kittyts_session *session, kittykb_event *event);
bool kittyts_key_down(const kittyts_session *session, uint32_t key);
bool kittyts_has_release_events(const kittyts_session *session);

#ifdef __cplusplus
}
#endif

#endif
