/* sound.h — the twelve system cues and their failure-safe mixer wrapper.
 *
 * Audio is feedback only.  Every valid sound_play() request is traced even
 * when audio is muted, not initialized, or has no live output device; this
 * lets headless tests prove trigger coverage without making sound part of
 * interaction semantics.
 */
#ifndef KILIX_CAP_SOUND_H
#define KILIX_CAP_SOUND_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum SoundCue {
    SOUND_TOUCH = 0,
    SOUND_ERROR,
    SOUND_KEYBOARD,
    SOUND_SWALLOW,
    SOUND_CONTAIN,
    SOUND_COPY,
    SOUND_DOOR,
    SOUND_SWITCH,
    SOUND_DISMISS,
    SOUND_MAGIC,
    SOUND_RING,
    SOUND_NO_MAIL,
    SOUND_COUNT
} SoundCue;

/* Load the complete bank and start pcm-mixer.  `offline` starts no process or
 * thread and is intended for deterministic tests.  The return value reports
 * whether all twelve assets are valid; a complete bank with no live audio
 * sink still returns true and runs silently. */
bool sound_init(const char *argv0, bool offline);
void sound_shutdown(void);

/* Playback is always optional.  Invalid cue values are ignored. */
void sound_play(SoundCue cue);
void sound_set_enabled(bool enabled);
bool sound_is_enabled(void);

/* Non-mutating bank check using the same executable-relative lookup as
 * sound_init().  Verbose mode prints one line per validated cue. */
bool sound_validate_assets(const char *argv0, bool verbose);

/* Headless trigger accounting. */
void     sound_reset_trace(void);
uint64_t sound_trace_count(SoundCue cue);

/* Stable metadata used by diagnostics and manifest tests. */
const char *sound_cue_name(SoundCue cue);
const char *sound_cue_path(SoundCue cue);
float       sound_cue_gain(SoundCue cue);

/* Test-facing state.  sound_mix_offline() returns false and fills silence if
 * no offline mixer is running; it must never be called on a live mixer. */
bool sound_mix_offline(int16_t *dst, size_t frames);
bool sound_bank_complete(void);
bool sound_mixer_running(void);

#endif /* KILIX_CAP_SOUND_H */
