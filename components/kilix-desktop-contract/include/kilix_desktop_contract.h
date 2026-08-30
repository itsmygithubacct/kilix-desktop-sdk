#ifndef KILIX_DESKTOP_CONTRACT_H
#define KILIX_DESKTOP_CONTRACT_H

#include <stddef.h>
#include <string.h>

#define KILIX_DESKTOP_CONTRACT_VERSION 1
#define KILIX_DESKTOP_ACTION_MAX_BYTES 4096u

enum kilix_desktop_exit_status {
    KILIX_DESKTOP_EXIT_OK = 0,
    KILIX_DESKTOP_EXIT_USAGE = 2,
    KILIX_DESKTOP_EXIT_INVALID_REQUEST = 3,
    KILIX_DESKTOP_EXIT_UNAVAILABLE = 4,
    KILIX_DESKTOP_EXIT_INCOMPATIBLE_CONTRACT = 5,
    KILIX_DESKTOP_EXIT_MIGRATION_FAILED = 6,
    KILIX_DESKTOP_EXIT_INTERNAL_ERROR = 70
};

enum kilix_desktop_action_verb {
    KILIX_DESKTOP_ACTION_APP_OPEN,
    KILIX_DESKTOP_ACTION_DESKTOP_LAUNCH,
    KILIX_DESKTOP_ACTION_DESKTOP_MAKE_DEFAULT,
    KILIX_DESKTOP_ACTION_DOCUMENT_OPEN,
    KILIX_DESKTOP_ACTION_GAME_PLAY,
    KILIX_DESKTOP_ACTION_POWER_REQUEST,
    KILIX_DESKTOP_ACTION_SESSION_OPEN,
    KILIX_DESKTOP_ACTION_SETTINGS_OPEN,
    KILIX_DESKTOP_ACTION_URL_OPEN
};

enum kilix_desktop_parse_status {
    KILIX_DESKTOP_PARSE_OK = 0,
    KILIX_DESKTOP_PARSE_NULL,
    KILIX_DESKTOP_PARSE_TOO_LONG,
    KILIX_DESKTOP_PARSE_MISSING_SEPARATOR,
    KILIX_DESKTOP_PARSE_EMPTY_PAYLOAD,
    KILIX_DESKTOP_PARSE_CONTROL,
    KILIX_DESKTOP_PARSE_UNKNOWN_VERB,
    KILIX_DESKTOP_PARSE_INVALID_PAYLOAD
};

struct kilix_desktop_action {
    enum kilix_desktop_action_verb verb;
    const char *payload;
    size_t payload_length;
};

static inline int
kilix_desktop_contract_slice_eq(const char *value, size_t length,
                                const char *literal)
{
    size_t literal_length = strlen(literal);
    return length == literal_length && memcmp(value, literal, length) == 0;
}

static inline int
kilix_desktop_contract_identifier(const char *value, size_t length)
{
    size_t index;
    int separator = 0;
    if (length == 0u)
        return 0;
    for (index = 0u; index < length; ++index) {
        unsigned char character = (unsigned char)value[index];
        int alpha_numeric = (character >= (unsigned char)'a' &&
                             character <= (unsigned char)'z') ||
                            (character >= (unsigned char)'0' &&
                             character <= (unsigned char)'9');
        int is_separator = character == (unsigned char)'.' ||
                           character == (unsigned char)'_' ||
                           character == (unsigned char)'-' ||
                           character == (unsigned char)'/';
        if (alpha_numeric) {
            separator = 0;
        } else if (is_separator && index != 0u && !separator) {
            separator = 1;
        } else {
            return 0;
        }
    }
    return !separator;
}

static inline enum kilix_desktop_parse_status
kilix_desktop_action_parse(const char *raw, struct kilix_desktop_action *action)
{
    const char *separator;
    const char *payload;
    size_t raw_length;
    size_t verb_length;
    size_t payload_length;
    size_t index;
    int identifier_payload = 0;

    if (raw == NULL || action == NULL)
        return KILIX_DESKTOP_PARSE_NULL;
    raw_length = strlen(raw);
    if (raw_length > KILIX_DESKTOP_ACTION_MAX_BYTES)
        return KILIX_DESKTOP_PARSE_TOO_LONG;
    separator = strchr(raw, ':');
    if (separator == NULL || separator == raw)
        return KILIX_DESKTOP_PARSE_MISSING_SEPARATOR;
    payload = separator + 1;
    payload_length = raw_length - (size_t)(payload - raw);
    if (payload_length == 0u)
        return KILIX_DESKTOP_PARSE_EMPTY_PAYLOAD;
    for (index = 0u; index < raw_length; ++index) {
        unsigned char character = (unsigned char)raw[index];
        if (character < 0x20u || character == 0x7fu)
            return KILIX_DESKTOP_PARSE_CONTROL;
    }

    verb_length = (size_t)(separator - raw);
    if (kilix_desktop_contract_slice_eq(raw, verb_length, "app.open")) {
        action->verb = KILIX_DESKTOP_ACTION_APP_OPEN;
        identifier_payload = 1;
    } else if (kilix_desktop_contract_slice_eq(raw, verb_length,
                                               "desktop.launch")) {
        action->verb = KILIX_DESKTOP_ACTION_DESKTOP_LAUNCH;
        identifier_payload = 1;
    } else if (kilix_desktop_contract_slice_eq(raw, verb_length,
                                               "desktop.make-default")) {
        action->verb = KILIX_DESKTOP_ACTION_DESKTOP_MAKE_DEFAULT;
        identifier_payload = 1;
    } else if (kilix_desktop_contract_slice_eq(raw, verb_length,
                                               "document.open")) {
        action->verb = KILIX_DESKTOP_ACTION_DOCUMENT_OPEN;
    } else if (kilix_desktop_contract_slice_eq(raw, verb_length,
                                               "game.play")) {
        action->verb = KILIX_DESKTOP_ACTION_GAME_PLAY;
        identifier_payload = 1;
    } else if (kilix_desktop_contract_slice_eq(raw, verb_length,
                                               "power.request")) {
        action->verb = KILIX_DESKTOP_ACTION_POWER_REQUEST;
        if (!kilix_desktop_contract_slice_eq(payload, payload_length, "logout") &&
            !kilix_desktop_contract_slice_eq(payload, payload_length, "reboot") &&
            !kilix_desktop_contract_slice_eq(payload, payload_length, "shutdown") &&
            !kilix_desktop_contract_slice_eq(payload, payload_length, "suspend"))
            return KILIX_DESKTOP_PARSE_INVALID_PAYLOAD;
    } else if (kilix_desktop_contract_slice_eq(raw, verb_length,
                                               "session.open")) {
        action->verb = KILIX_DESKTOP_ACTION_SESSION_OPEN;
        identifier_payload = 1;
    } else if (kilix_desktop_contract_slice_eq(raw, verb_length,
                                               "settings.open")) {
        action->verb = KILIX_DESKTOP_ACTION_SETTINGS_OPEN;
        identifier_payload = 1;
    } else if (kilix_desktop_contract_slice_eq(raw, verb_length, "url.open")) {
        action->verb = KILIX_DESKTOP_ACTION_URL_OPEN;
        if (payload_length < 9u || memcmp(payload, "https://", 8u) != 0)
            return KILIX_DESKTOP_PARSE_INVALID_PAYLOAD;
    } else {
        return KILIX_DESKTOP_PARSE_UNKNOWN_VERB;
    }
    if (identifier_payload &&
        !kilix_desktop_contract_identifier(payload, payload_length))
        return KILIX_DESKTOP_PARSE_INVALID_PAYLOAD;

    action->payload = payload;
    action->payload_length = payload_length;
    return KILIX_DESKTOP_PARSE_OK;
}

#endif
