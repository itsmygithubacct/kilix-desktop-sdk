/* sound.c — strict asset loading and graceful pcm-mixer integration. */
#include "sound.h"

#include "pcm_mixer.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

enum { SOUND_RATE = 44100, SOUND_MAX_FRAMES = SOUND_RATE };

typedef struct SoundInfo {
    const char *name;
    const char *path;
    float gain;
} SoundInfo;

static const SoundInfo sound_info[SOUND_COUNT] = {
    [SOUND_TOUCH]    = {"touch",    "assets/sfx/touch.wav",    0.75f},
    [SOUND_ERROR]    = {"error",    "assets/sfx/error.wav",    0.55f},
    [SOUND_KEYBOARD] = {"keyboard", "assets/sfx/keyboard.wav", 0.18f},
    [SOUND_SWALLOW]  = {"swallow",  "assets/sfx/swallow.wav",  0.16f},
    [SOUND_CONTAIN]  = {"contain",  "assets/sfx/contain.wav",  0.55f},
    [SOUND_COPY]     = {"copy",     "assets/sfx/copy.wav",     0.18f},
    [SOUND_DOOR]     = {"door",     "assets/sfx/door.wav",     0.20f},
    [SOUND_SWITCH]   = {"switch",   "assets/sfx/switch.wav",   0.25f},
    [SOUND_DISMISS]  = {"dismiss",  "assets/sfx/dismiss.wav",  0.55f},
    [SOUND_MAGIC]    = {"magic",    "assets/sfx/magic.wav",    0.25f},
    [SOUND_RING]     = {"ring",     "assets/sfx/ring.wav",     0.35f},
    [SOUND_NO_MAIL]  = {"no_mail",  "assets/sfx/no_mail.wav",  0.50f},
};

_Static_assert(sizeof sound_info / sizeof sound_info[0] == SOUND_COUNT,
               "sound metadata must cover every cue");

static pcmmix mixer;
static pcmmix_sample samples[SOUND_COUNT];
static int16_t *sample_storage[SOUND_COUNT];
static uint64_t trace_counts[SOUND_COUNT];
static bool logical_enabled = true;
static bool bank_complete;
static bool mixer_started;
static bool mixer_offline;
static bool hard_disabled;
static int ring_voice = -1;

static bool cue_valid(SoundCue cue)
{
    return cue >= SOUND_TOUCH && cue < SOUND_COUNT;
}

static bool string_copy(char *dst, size_t size, const char *src)
{
    if (dst == NULL || size == 0 || src == NULL) return false;
    int n = snprintf(dst, size, "%s", src);
    return n >= 0 && (size_t)n < size;
}

static bool path_join(char *dst, size_t size, const char *left,
                      const char *right)
{
    if (dst == NULL || size == 0 || left == NULL || right == NULL)
        return false;
    size_t nleft = strlen(left);
    int n = snprintf(dst, size, "%s%s%s", left,
                     nleft > 0 && left[nleft - 1] == '/' ? "" : "/", right);
    return n >= 0 && (size_t)n < size;
}

static bool path_dirname(const char *path, char *dst, size_t size)
{
    if (path == NULL || path[0] == '\0') return false;
    const char *slash = strrchr(path, '/');
    if (slash == NULL) return string_copy(dst, size, ".");
    if (slash == path) return string_copy(dst, size, "/");
    size_t length = (size_t)(slash - path);
    if (length + 1 > size) return false;
    memcpy(dst, path, length);
    dst[length] = '\0';
    return true;
}

static bool executable_path(const char *argv0, char *dst, size_t size)
{
    char resolved[PATH_MAX];
#if defined(__linux__)
    {
        ssize_t length = readlink("/proc/self/exe", resolved,
                                  sizeof resolved - 1u);
        if (length > 0 && (size_t)length < sizeof resolved) {
            resolved[length] = '\0';
            return string_copy(dst, size, resolved);
        }
    }
#endif
    if (argv0 != NULL && argv0[0] != '\0' && strchr(argv0, '/') != NULL &&
        realpath(argv0, resolved) != NULL)
        return string_copy(dst, size, resolved);
    return false;
}

static bool bank_readable(const char *root)
{
    char path[PATH_MAX];
    for (int i = 0; i < SOUND_COUNT; i++) {
        const char *name = strrchr(sound_info[i].path, '/');
        name = name != NULL ? name + 1 : sound_info[i].path;
        if (!path_join(path, sizeof path, root, name) ||
            access(path, R_OK) != 0)
            return false;
    }
    return true;
}

static void add_candidate(char candidates[][PATH_MAX], size_t *count,
                          size_t capacity, const char *candidate)
{
    if (*count >= capacity || candidate == NULL || candidate[0] == '\0')
        return;
    for (size_t i = 0; i < *count; i++)
        if (strcmp(candidates[i], candidate) == 0) return;
    if (string_copy(candidates[*count], PATH_MAX, candidate)) (*count)++;
}

static void add_executable_candidates(char candidates[][PATH_MAX],
                                      size_t *count, size_t capacity,
                                      const char *executable)
{
    char directory[PATH_MAX];
    char candidate[PATH_MAX];
    if (!path_dirname(executable, directory, sizeof directory)) return;
    if (path_join(candidate, sizeof candidate, directory, "../assets/sfx"))
        add_candidate(candidates, count, capacity, candidate);
    if (path_join(candidate, sizeof candidate, directory, "assets/sfx"))
        add_candidate(candidates, count, capacity, candidate);
}

static bool resolve_asset_root(const char *argv0, char *dst, size_t size)
{
    const char *override = getenv("KILIX_CAP_ASSET_DIR");
    if (override != NULL && override[0] != '\0')
        return string_copy(dst, size, override);

    char candidates[5][PATH_MAX];
    size_t count = 0;
    char executable[PATH_MAX];
    if (executable_path(argv0, executable, sizeof executable))
        add_executable_candidates(candidates, &count, 5, executable);
    add_candidate(candidates, &count, 5, "assets/sfx");

    for (size_t i = 0; i < count; i++)
        if (bank_readable(candidates[i]))
            return string_copy(dst, size, candidates[i]);

    /* Keep diagnostics deterministic even when the bank is absent. */
    return string_copy(dst, size, count > 0 ? candidates[0] : "assets/sfx");
}

static bool frames_valid(const int16_t *frames, size_t frame_count,
                         const char *path, bool verbose)
{
    if (frame_count == 0 || frame_count > SOUND_MAX_FRAMES) {
        if (verbose)
            fprintf(stderr, "audio: %s has invalid duration (%zu frames)\n",
                    path, frame_count);
        return false;
    }
    bool nonzero = false;
    bool clipped = false;
    for (size_t i = 0; i < frame_count; i++) {
        if (frames[i] != 0) nonzero = true;
        if (frames[i] == INT16_MIN || frames[i] == INT16_MAX) clipped = true;
    }
    if (!nonzero || clipped) {
        if (verbose)
            fprintf(stderr, "audio: %s is %s%s\n", path,
                    nonzero ? "" : "silent",
                    clipped ? (nonzero ? "clipped" : " and clipped") : "");
        return false;
    }
    return true;
}

static bool load_bank(const char *argv0, bool verbose, bool retain)
{
    char root[PATH_MAX];
    int16_t *loaded[SOUND_COUNT] = {0};
    size_t frame_counts[SOUND_COUNT] = {0};
    bool ok = resolve_asset_root(argv0, root, sizeof root);

    if (verbose && ok) printf("audio: validating %s\n", root);
    for (int i = 0; ok && i < SOUND_COUNT; i++) {
        char path[PATH_MAX];
        char error[256];
        const char *name = strrchr(sound_info[i].path, '/');
        name = name != NULL ? name + 1 : sound_info[i].path;
        if (!path_join(path, sizeof path, root, name)) {
            if (verbose) fprintf(stderr, "audio: asset path is too long\n");
            ok = false;
            break;
        }
        loaded[i] = pcmmix_wav_load(path, &frame_counts[i], error,
                                    sizeof error);
        if (loaded[i] == NULL) {
            if (verbose) fprintf(stderr, "audio: %s\n", error);
            ok = false;
            break;
        }
        if (!frames_valid(loaded[i], frame_counts[i], path, verbose)) {
            ok = false;
            break;
        }
        if (verbose)
            printf("audio: %-8s %6zu frames  %.3fs\n", sound_info[i].name,
                   frame_counts[i], (double)frame_counts[i] / SOUND_RATE);
    }

    if (ok && retain) {
        for (int i = 0; i < SOUND_COUNT; i++) {
            sample_storage[i] = loaded[i];
            samples[i].frames = loaded[i];
            samples[i].frame_count = frame_counts[i];
            loaded[i] = NULL;
        }
    }
    for (int i = 0; i < SOUND_COUNT; i++) pcmmix_wav_free(loaded[i]);
    if (verbose)
        printf("audio: %s\n", ok ? "12-cue bank OK" : "bank invalid");
    return ok;
}

static bool environment_disables_audio(void)
{
    const char *no_audio = getenv("KILIX_CAP_NO_AUDIO");
    const char *audio = getenv("KILIX_CAP_AUDIO");
    bool no_audio_false = no_audio != NULL &&
        (strcmp(no_audio, "0") == 0 || strcasecmp(no_audio, "off") == 0 ||
         strcasecmp(no_audio, "false") == 0 ||
         strcasecmp(no_audio, "no") == 0);
    bool audio_false = audio != NULL &&
        (strcmp(audio, "0") == 0 || strcasecmp(audio, "off") == 0 ||
         strcasecmp(audio, "false") == 0 || strcasecmp(audio, "no") == 0);
    return (no_audio != NULL && no_audio[0] != '\0' && !no_audio_false) ||
           audio_false;
}

bool sound_init(const char *argv0, bool offline)
{
    sound_shutdown();
    hard_disabled = !offline && environment_disables_audio();
    if (hard_disabled) logical_enabled = false;
    bank_complete = load_bank(argv0, false, true);
    if (!bank_complete) return false;

    if (hard_disabled) return true;

    pcmmix_options options;
    pcmmix_options_init(&options);
    options.offline = offline;
    mixer_started = pcmmix_start(&mixer, &options);
    mixer_offline = mixer_started && offline;
    if (mixer_started)
        pcmmix_set_enabled(&mixer, logical_enabled);

    /* A live machine without a sink is still a valid installation. */
    return offline ? mixer_started : true;
}

void sound_shutdown(void)
{
    if (mixer_started) pcmmix_stop(&mixer);
    mixer_started = false;
    mixer_offline = false;
    hard_disabled = false;
    ring_voice = -1;
    for (int i = 0; i < SOUND_COUNT; i++) {
        pcmmix_wav_free(sample_storage[i]);
        sample_storage[i] = NULL;
        samples[i] = (pcmmix_sample){0};
    }
    bank_complete = false;
}

void sound_play(SoundCue cue)
{
    if (!cue_valid(cue)) return;
    trace_counts[cue]++;
    if (!logical_enabled || !mixer_started ||
        !pcmmix_is_running(&mixer)) return;

    if (cue == SOUND_RING && ring_voice > 0 &&
        pcmmix_voice_active(&mixer, ring_voice))
        return;
    int voice = pcmmix_play(&mixer, &samples[cue], sound_info[cue].gain, 1.0f);
    if (cue == SOUND_RING) ring_voice = voice;
}

void sound_set_enabled(bool enabled)
{
    logical_enabled = enabled && !hard_disabled;
    if (mixer_started) pcmmix_set_enabled(&mixer, logical_enabled);
    if (!logical_enabled) ring_voice = -1;
}

bool sound_is_enabled(void)
{
    return logical_enabled;
}

bool sound_validate_assets(const char *argv0, bool verbose)
{
    return load_bank(argv0, verbose, false);
}

void sound_reset_trace(void)
{
    memset(trace_counts, 0, sizeof trace_counts);
}

uint64_t sound_trace_count(SoundCue cue)
{
    return cue_valid(cue) ? trace_counts[cue] : 0;
}

const char *sound_cue_name(SoundCue cue)
{
    return cue_valid(cue) ? sound_info[cue].name : "";
}

const char *sound_cue_path(SoundCue cue)
{
    return cue_valid(cue) ? sound_info[cue].path : "";
}

float sound_cue_gain(SoundCue cue)
{
    return cue_valid(cue) ? sound_info[cue].gain : 0.0f;
}

bool sound_mix_offline(int16_t *dst, size_t frames)
{
    if (dst == NULL || frames == 0) return false;
    if (!mixer_started || !mixer_offline) {
        memset(dst, 0, frames * sizeof *dst);
        return false;
    }
    pcmmix_mix_block(&mixer, dst, frames);
    return true;
}

bool sound_bank_complete(void)
{
    return bank_complete;
}

bool sound_mixer_running(void)
{
    return mixer_started && pcmmix_is_running(&mixer);
}
