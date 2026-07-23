/* panel.c — modal interiors, small utilities, and the on-screen keyboard. */
#include "panel.h"

#include "draw.h"
#include "sound.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

enum {
    PANEL_OBJECT_MAX = 48,
    TEXT_CAP = 45,
    MAIL_TARGET_CAP = 255,
    BOOK_COUNT = 5,

    ACTION_CLOSE = 1,
    ACTION_PRIMARY,
    ACTION_SECONDARY,
    ACTION_TERTIARY,
    ACTION_KEY_BASE = 100,
    ACTION_KEY_BACK = 200,
    ACTION_KEY_SPACE,
    ACTION_KEY_DONE,
    ACTION_KEY_DOT,
    ACTION_KEY_SLASH,
    ACTION_KEY_COLON,
    ACTION_KEY_DASH,
    ACTION_KEY_UNDERSCORE,
    ACTION_KEY_DIGIT_BASE = 300
};

enum KeyboardTarget {
    KEYBOARD_SCRATCH = 0,
    KEYBOARD_MAIL_DRAFT,
    KEYBOARD_NOTE,
    KEYBOARD_MAIL_TARGET
};

/* Compact enough to leave the room legible around an app, while preserving
 * 32px minimum pointer targets and the full text/art hierarchy inside. */
static const UiRect panel_rect = {54, 48, 372, 204};
static Object objects[PANEL_OBJECT_MAX];
static int object_count;
static PanelId current_panel;
static PanelId keyboard_return;
static enum KeyboardTarget keyboard_target;
static int focused_index;
static PanelCommand pending_key_command;

static int clock_hour;
static bool clock_24h;
static int inbox_count;
static bool inbox_checked;
static int outbox_count;
static bool profile_away;
static int date_offset;
static int card_index;
static int file_index;
static bool phone_ringing;
static int paper_sheets;
static int calculator_value;
static int copy_count;
static int tote_items;
static int trash_items;
static int book_index;
static bool web_cached;
static bool web_checked;
static bool mail_target_configured;
static char mail_text[TEXT_CAP + 1];
static char note_text[TEXT_CAP + 1];
static char scratch_text[TEXT_CAP + 1];
static char mail_target_edit[MAIL_TARGET_CAP + 1];
static char key_labels[26][2];
static char phone_unavailable_reason[64];
static char launch_status[64];
static bool launch_status_success;

static const char key_order[] = "qwertyuiopasdfghjklzxcvbnm";
static const char *const contact_names[] = {
    "Mira Chen", "Owen Bell", "Rae Alvarez"
};
static const char *const contact_notes[] = {
    "Workshop - extension 14", "Library - afternoons", "Game Room club"
};
static const char *const file_names[] = {
    "Welcome card", "Room guide", "Audio receipt", "License"
};
static const char *const file_notes[] = {
    "A small place made for a pointer.",
    "Five doors connect useful local rooms.",
    "Twelve original cues; silence is safe.",
    "Source and authored assets: see LICENSE."
};
static const char *const book_titles[BOOK_COUNT] = {
    "First Steps", "Rooms", "Objects", "Sound", "Colophon"
};
static const char *const book_line_a[BOOK_COUNT] = {
    "Touch objects to use them.",
    "Hallway joins five rooms.",
    "Drag shelf items to move.",
    "Cues have visible matches.",
    "Made just for Kilix Cap."
};
static const char *const book_line_b[BOOK_COUNT] = {
    "Tool bar is always ready.",
    "Desk returns home fast.",
    "Tote and Trash hold items.",
    "Controls can mute sound.",
    "Generated art; own code."
};

static void set_button(Object *o, const char *name, const char *label,
                       UiRect visual, int action)
{
    memset(o, 0, sizeof *o);
    o->name = name;
    o->label = label;
    o->kind = OBJ_BUTTON;
    o->icon = ICON_NONE;
    o->visual = visual;
    o->hit = ui_target(visual);
    o->target = action;
    o->container = -1;
    o->visible = true;
}

static void add_button(const char *name, const char *label, UiRect rect,
                       int action)
{
    if (object_count >= PANEL_OBJECT_MAX) return;
    set_button(&objects[object_count++], name, label, rect, action);
}

static void add_bottom_buttons(const char *a, const char *b, const char *d)
{
    int count = (a != NULL) + (b != NULL) + (d != NULL);
    int width = count == 1 ? 132 : 104;
    int gap = 14;
    int total = count * width + (count - 1) * gap;
    int x = (CANVAS_W - total) / 2;
    if (a != NULL) {
        add_button(a, a, ui_rect(x, 210, width, 32), ACTION_PRIMARY);
        x += width + gap;
    }
    if (b != NULL) {
        add_button(b, b, ui_rect(x, 210, width, 32), ACTION_SECONDARY);
        x += width + gap;
    }
    if (d != NULL)
        add_button(d, d, ui_rect(x, 210, width, 32), ACTION_TERTIARY);
}

static void sync_active_buttons(void)
{
    for (int i = 0; i < object_count; i++) {
        Object *o = &objects[i];
        if (current_panel == PANEL_CLOCK && o->target == ACTION_SECONDARY)
            o->active = clock_24h;
        else if (current_panel == PANEL_PROFILE &&
                 o->target == ACTION_PRIMARY)
            o->active = profile_away;
        else if (current_panel == PANEL_PHONE &&
                 o->target == ACTION_PRIMARY)
            o->active = phone_ringing;
        else if (current_panel == PANEL_WEB &&
                 o->target == ACTION_SECONDARY)
            o->active = web_cached;
        else if (current_panel == PANEL_TOOL_HOLDER &&
                 o->target == ACTION_PRIMARY)
            o->active = sound_is_enabled();
    }
}

static void restore_focus(int preferred_action)
{
    focused_index = -1;
    if (current_panel == PANEL_KEYBOARD) return;
    if (preferred_action >= 0) {
        for (int i = 0; i < object_count; i++)
            if (objects[i].target == preferred_action) {
                focused_index = i;
                return;
            }
    }
    for (int i = 0; i < object_count; i++)
        if (objects[i].target != ACTION_CLOSE) {
            focused_index = i;
            return;
        }
    if (object_count > 0) focused_index = 0;
}

static void configure_keyboard(void)
{
    static const int row_starts[3] = {0, 10, 19};
    static const int row_lengths[3] = {10, 9, 7};
    static const int row_x[3] = {70, 87, 121};

    object_count = 0;
    if (keyboard_target == KEYBOARD_MAIL_TARGET) {
        static const int compact_x[3] = {76, 92, 124};
        static const char *const digits[] = {
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"
        };
        int x;
        for (int row = 0; row < 3; row++)
            for (int col = 0; col < row_lengths[row]; col++) {
                int index = row_starts[row] + col;
                add_button("Mail target key", key_labels[index],
                           ui_rect(compact_x[row] + col * 33,
                                   80 + row * 30, 30, 26),
                           ACTION_KEY_BASE + index);
            }
        for (int col = 0; col < 10; col++)
            add_button("Mail target digit", digits[col],
                       ui_rect(76 + col * 33, 170, 30, 26),
                       ACTION_KEY_DIGIT_BASE + col);
        x = 73;
        add_button("Backspace key", "Back", ui_rect(x, 204, 64, 32),
                   ACTION_KEY_BACK);
        x += 70;
        add_button("Dot key", ".", ui_rect(x, 204, 34, 32), ACTION_KEY_DOT);
        x += 40;
        add_button("Slash key", "/", ui_rect(x, 204, 34, 32),
                   ACTION_KEY_SLASH);
        x += 40;
        add_button("Colon key", ":", ui_rect(x, 204, 34, 32),
                   ACTION_KEY_COLON);
        x += 40;
        add_button("Dash key", "-", ui_rect(x, 204, 34, 32),
                   ACTION_KEY_DASH);
        x += 40;
        add_button("Underscore key", "_", ui_rect(x, 204, 34, 32),
                   ACTION_KEY_UNDERSCORE);
        x += 40;
        add_button("Done key", "Done", ui_rect(x, 204, 64, 32),
                   ACTION_KEY_DONE);
        return;
    }
    for (int row = 0; row < 3; row++) {
        for (int col = 0; col < row_lengths[row]; col++) {
            int index = row_starts[row] + col;
            add_button("Keyboard key", key_labels[index],
                       ui_rect(row_x[row] + col * 34, 88 + row * 36, 32, 30),
                       ACTION_KEY_BASE + index);
        }
    }
    add_button("Backspace key", "Back", ui_rect(80, 204, 82, 32),
               ACTION_KEY_BACK);
    add_button("Space key", "Space", ui_rect(171, 204, 138, 32),
               ACTION_KEY_SPACE);
    add_button("Done key", "Done", ui_rect(318, 204, 82, 32),
               ACTION_KEY_DONE);
}

static void configure_panel(void)
{
    int preferred_action = -1;
    if (focused_index >= 0 && focused_index < object_count)
        preferred_action = objects[focused_index].target;
    object_count = 0;
    if (current_panel == PANEL_NONE) return;
    if (current_panel == PANEL_KEYBOARD) {
        configure_keyboard();
        focused_index = -1;
        return;
    }

    add_button("Close window", "X", ui_rect(386, 51, 26, 26), ACTION_CLOSE);
    switch (current_panel) {
    case PANEL_CLOCK:       add_bottom_buttons("Hour +", "12 / 24", "Open app"); break;
    case PANEL_INBOX:       add_bottom_buttons("Check", "Receive", "Open app"); break;
    case PANEL_OUTBOX:
        add_bottom_buttons(outbox_count > 0 ? "Send" : NULL, NULL, "Open app");
        break;
    case PANEL_MAIL:
        if (mail_target_configured)
            add_bottom_buttons("Keyboard", "Queue", "Setup");
        else
            add_bottom_buttons("Register", NULL, NULL);
        break;
    case PANEL_PROFILE:     add_bottom_buttons("Set status", NULL, "Open app"); break;
    case PANEL_NOTES:       add_bottom_buttons("Keyboard", "Clear", "Open app"); break;
    case PANEL_DATES:       add_bottom_buttons("Earlier", "Later", "Open app"); break;
    case PANEL_CARDS:       add_bottom_buttons("Previous", "Next", "Open app"); break;
    case PANEL_FILES:       add_bottom_buttons("Previous", "Next", "Open app"); break;
    case PANEL_PHONE:
        add_bottom_buttons(phone_ringing ? "Stop ring" : "Ring",
                           phone_ringing ? "Answer" : NULL,
                           phone_unavailable_reason[0] != '\0'
                               ? NULL : "Open app");
        break;
    case PANEL_PAPER:       add_bottom_buttons("New sheet", "Copy", "Open app"); break;
    case PANEL_CALCULATOR:  add_bottom_buttons("Add one", "Clear", "Open app"); break;
    case PANEL_WEB:         add_bottom_buttons("Retry", "Cached page", "Open app"); break;
    case PANEL_STAMPER:     add_bottom_buttons("Star", "Leaf", "Label"); break;
    case PANEL_TOTE:
        add_bottom_buttons(tote_items > 0 ? "Put back" : NULL,
                           copy_count > 0 ? "Clear copies" : NULL, NULL);
        break;
    case PANEL_TOOL_HOLDER: add_bottom_buttons("Sound", "Reset", NULL); break;
    case PANEL_TRASH:
        add_bottom_buttons((trash_items > 0 || copy_count > 0) ? "Empty" : NULL,
                           trash_items > 0 ? "Restore" : NULL, NULL);
        break;
    case PANEL_BOOK:        add_bottom_buttons("Previous", "Next", NULL); break;
    default: break;
    }
    sync_active_buttons();
    restore_focus(preferred_action);
}

void panel_init(void)
{
    current_panel = PANEL_NONE;
    keyboard_return = PANEL_NONE;
    keyboard_target = KEYBOARD_SCRATCH;
    focused_index = -1;
    pending_key_command = PANEL_COMMAND_NONE;
    object_count = 0;
    clock_hour = 9;
    clock_24h = false;
    inbox_count = 0;
    inbox_checked = false;
    outbox_count = 1;
    profile_away = false;
    date_offset = 0;
    card_index = 0;
    file_index = 0;
    phone_ringing = false;
    paper_sheets = 1;
    calculator_value = 0;
    copy_count = 0;
    tote_items = 0;
    trash_items = 0;
    book_index = 0;
    web_cached = false;
    web_checked = false;
    snprintf(mail_text, sizeof mail_text, "%s", "Hello from Kilix Cap.");
    snprintf(note_text, sizeof note_text, "%s", "Meet in the Library.");
    scratch_text[0] = '\0';
    launch_status[0] = '\0';
    launch_status_success = true;
    for (int i = 0; i < 26; i++) {
        key_labels[i][0] = key_order[i];
        key_labels[i][1] = '\0';
    }
}

void panel_open(PanelId id)
{
    if (id <= PANEL_NONE || id >= PANEL_COUNT) return;
    if (id == PANEL_KEYBOARD) {
        panel_open_keyboard();
        return;
    }
    current_panel = id;
    keyboard_return = PANEL_NONE;
    keyboard_target = KEYBOARD_SCRATCH;
    focused_index = -1;
    pending_key_command = PANEL_COMMAND_NONE;
    launch_status[0] = '\0';
    if (current_panel == PANEL_MAIL && !mail_target_configured) {
        (void)snprintf(launch_status, sizeof launch_status, "%s",
                       "Register a mail program or mail URL.");
        launch_status_success = false;
    } else if (current_panel == PANEL_PHONE &&
        phone_unavailable_reason[0] != '\0') {
        (void)snprintf(launch_status, sizeof launch_status, "%s",
                       phone_unavailable_reason);
        launch_status_success = false;
    }
    configure_panel();
}

void panel_open_book(int book)
{
    book_index = iclampi(book, 0, BOOK_COUNT - 1);
    panel_open(PANEL_BOOK);
}

static void open_editor_keyboard(void)
{
    keyboard_return = current_panel;
    keyboard_target = current_panel == PANEL_MAIL ? KEYBOARD_MAIL_DRAFT :
                                                    KEYBOARD_NOTE;
    current_panel = PANEL_KEYBOARD;
    focused_index = -1;
    pending_key_command = PANEL_COMMAND_NONE;
    configure_panel();
}

static void open_mail_target_keyboard(void)
{
    keyboard_return = PANEL_MAIL;
    keyboard_target = KEYBOARD_MAIL_TARGET;
    current_panel = PANEL_KEYBOARD;
    focused_index = -1;
    pending_key_command = PANEL_COMMAND_NONE;
    launch_status[0] = '\0';
    configure_panel();
}

void panel_open_keyboard(void)
{
    keyboard_return = PANEL_NONE;
    keyboard_target = KEYBOARD_SCRATCH;
    current_panel = PANEL_KEYBOARD;
    focused_index = -1;
    pending_key_command = PANEL_COMMAND_NONE;
    launch_status[0] = '\0';
    configure_panel();
}

void panel_close(bool audible)
{
    if (current_panel == PANEL_NONE) return;
    current_panel = PANEL_NONE;
    keyboard_return = PANEL_NONE;
    keyboard_target = KEYBOARD_SCRATCH;
    focused_index = -1;
    pending_key_command = PANEL_COMMAND_NONE;
    object_count = 0;
    if (audible) sound_play(SOUND_DISMISS);
}

bool panel_active(void) { return current_panel != PANEL_NONE; }
PanelId panel_current(void) { return current_panel; }

const char *panel_title(void)
{
    static const char *const titles[PANEL_COUNT] = {
        "", "Clock", "In box", "Out box", "New message", "My card",
        "Notepad", "Datebook", "Name cards", "File cabinet", "Telephone",
        "Stationery", "Calculator", "Local web", "Stamper", "Tote bag",
        "Tool holder", "Keyboard", "Trash truck", "Library book"
    };
    return current_panel >= 0 && current_panel < PANEL_COUNT
               ? titles[current_panel] : "";
}

Object *panel_object_at(int x, int y)
{
    if (!panel_active()) return NULL;
    for (int i = object_count - 1; i >= 0; i--)
        if (ui_touchable(&objects[i]) && ui_hit(objects[i].hit, x, y))
            return &objects[i];
    return NULL;
}

bool panel_owns(const Object *o)
{
    for (int i = 0; i < object_count; i++)
        if (o == &objects[i]) return true;
    return false;
}

static char *keyboard_buffer(void)
{
    if (keyboard_target == KEYBOARD_MAIL_DRAFT) return mail_text;
    if (keyboard_target == KEYBOARD_NOTE) return note_text;
    if (keyboard_target == KEYBOARD_MAIL_TARGET) return mail_target_edit;
    return scratch_text;
}

static size_t keyboard_capacity(void)
{
    return keyboard_target == KEYBOARD_MAIL_TARGET ? MAIL_TARGET_CAP :
                                                     TEXT_CAP;
}

static void append_character(char ch)
{
    char *text = keyboard_buffer();
    size_t n = strlen(text);
    if (n < keyboard_capacity()) {
        text[n] = ch;
        text[n + 1] = '\0';
    }
}

static void erase_character(void)
{
    char *text = keyboard_buffer();
    size_t n = strlen(text);
    if (n > 0) text[n - 1] = '\0';
}

static void leave_keyboard(void)
{
    current_panel = keyboard_return;
    keyboard_return = PANEL_NONE;
    keyboard_target = KEYBOARD_SCRATCH;
    focused_index = -1;
    if (current_panel == PANEL_NONE) object_count = 0;
    else configure_panel();
}

PanelCommand panel_activate(Object *o)
{
    int action;
    if (!panel_owns(o)) return PANEL_COMMAND_NONE;
    action = o->target;

    if (current_panel == PANEL_KEYBOARD) {
        if (action >= ACTION_KEY_BASE && action < ACTION_KEY_BASE + 26)
            append_character(key_order[action - ACTION_KEY_BASE]);
        else if (action >= ACTION_KEY_DIGIT_BASE &&
                 action < ACTION_KEY_DIGIT_BASE + 10)
            append_character((char)('0' + action - ACTION_KEY_DIGIT_BASE));
        else if (action == ACTION_KEY_BACK)
            erase_character();
        else if (action == ACTION_KEY_SPACE)
            append_character(' ');
        else if (action == ACTION_KEY_DOT)
            append_character('.');
        else if (action == ACTION_KEY_SLASH)
            append_character('/');
        else if (action == ACTION_KEY_COLON)
            append_character(':');
        else if (action == ACTION_KEY_DASH)
            append_character('-');
        else if (action == ACTION_KEY_UNDERSCORE)
            append_character('_');
        else if (action == ACTION_KEY_DONE) {
            bool save_mail_target = keyboard_target == KEYBOARD_MAIL_TARGET;
            leave_keyboard();
            sound_play(SOUND_DISMISS);
            return save_mail_target ? PANEL_COMMAND_SAVE_MAIL_TARGET :
                                      PANEL_COMMAND_NONE;
        }
        return PANEL_COMMAND_NONE;
    }

    if (action == ACTION_CLOSE) {
        panel_close(true);
        return PANEL_COMMAND_NONE;
    }

    if (current_panel >= PANEL_CLOCK && current_panel <= PANEL_WEB &&
        action == ACTION_TERTIARY && current_panel != PANEL_MAIL)
        return PANEL_COMMAND_LAUNCH_APP;

    switch (current_panel) {
    case PANEL_CLOCK:
        if (action == ACTION_PRIMARY) clock_hour = (clock_hour + 1) % 24;
        else if (action == ACTION_SECONDARY) {
            clock_24h = !clock_24h;
            sound_play(SOUND_SWITCH);
            configure_panel();
        }
        break;
    case PANEL_INBOX:
        if (action == ACTION_PRIMARY) {
            inbox_checked = true;
            if (inbox_count == 0) sound_play(SOUND_NO_MAIL);
            else inbox_count--;
        } else if (action == ACTION_SECONDARY) {
            if (inbox_count < 999) inbox_count++;
            inbox_checked = false;
            sound_play(SOUND_MAGIC);
        }
        break;
    case PANEL_OUTBOX:
        if (action == ACTION_PRIMARY) {
            outbox_count = 0;
            configure_panel();
        }
        break;
    case PANEL_MAIL:
        if (action == ACTION_PRIMARY) {
            if (mail_target_configured) open_editor_keyboard();
            else open_mail_target_keyboard();
        } else if (action == ACTION_SECONDARY) {
            if (mail_text[0] != '\0') {
                if (outbox_count < 999) outbox_count++;
                sound_play(SOUND_CONTAIN);
            }
        } else if (action == ACTION_TERTIARY)
            open_mail_target_keyboard();
        break;
    case PANEL_PROFILE:
        if (action == ACTION_PRIMARY) {
            profile_away = !profile_away;
            sound_play(SOUND_SWITCH);
            configure_panel();
        }
        break;
    case PANEL_NOTES:
        if (action == ACTION_PRIMARY) open_editor_keyboard();
        else if (action == ACTION_SECONDARY) note_text[0] = '\0';
        break;
    case PANEL_DATES:
        if (action == ACTION_PRIMARY && date_offset > -120) date_offset--;
        else if (action == ACTION_SECONDARY && date_offset < 120) date_offset++;
        break;
    case PANEL_CARDS:
        if (action == ACTION_PRIMARY) card_index = (card_index + 2) % 3;
        else if (action == ACTION_SECONDARY) card_index = (card_index + 1) % 3;
        break;
    case PANEL_FILES:
        if (action == ACTION_PRIMARY) file_index = (file_index + 3) % 4;
        else if (action == ACTION_SECONDARY) file_index = (file_index + 1) % 4;
        break;
    case PANEL_PHONE:
        if (action == ACTION_PRIMARY) {
            phone_ringing = !phone_ringing;
            if (phone_ringing) sound_play(SOUND_RING);
            configure_panel();
        } else if (action == ACTION_SECONDARY) {
            phone_ringing = false;
            configure_panel();
        }
        break;
    case PANEL_PAPER:
        if (action == ACTION_PRIMARY && paper_sheets < 999) paper_sheets++;
        else if (action == ACTION_SECONDARY) {
            if (copy_count < 999) copy_count++;
            sound_play(SOUND_COPY);
        }
        break;
    case PANEL_CALCULATOR:
        if (action == ACTION_PRIMARY && calculator_value < 999999)
            calculator_value++;
        else if (action == ACTION_SECONDARY) calculator_value = 0;
        break;
    case PANEL_WEB:
        if (action == ACTION_PRIMARY) {
            web_checked = true;
            sound_play(SOUND_NO_MAIL);
        }
        else if (action == ACTION_SECONDARY) {
            web_cached = !web_cached;
            configure_panel();
        }
        break;
    case PANEL_STAMPER:
        if (action == ACTION_PRIMARY || action == ACTION_SECONDARY ||
            action == ACTION_TERTIARY) {
            if (copy_count < 999) copy_count++;
            sound_play(SOUND_COPY);
        }
        break;
    case PANEL_TOTE:
        if (action == ACTION_PRIMARY) return PANEL_COMMAND_RETURN_TOTE_ITEM;
        if (action == ACTION_SECONDARY) {
            copy_count = 0;
            configure_panel();
        }
        break;
    case PANEL_TOOL_HOLDER:
        if (action == ACTION_PRIMARY) {
            bool enabling = !sound_is_enabled();
            if (enabling) sound_set_enabled(true);
            sound_play(SOUND_SWITCH);
            if (!enabling) sound_set_enabled(false);
            configure_panel();
        } else if (action == ACTION_SECONDARY) {
            return PANEL_COMMAND_RESET_WORKSPACE;
        }
        break;
    case PANEL_TRASH:
        if (action == ACTION_PRIMARY) {
            copy_count = 0;
            return PANEL_COMMAND_EMPTY_TRASH;
        }
        if (action == ACTION_SECONDARY)
            return PANEL_COMMAND_RESTORE_TRASH_ITEM;
        break;
    case PANEL_BOOK:
        if (action == ACTION_PRIMARY)
            book_index = (book_index + BOOK_COUNT - 1) % BOOK_COUNT;
        else if (action == ACTION_SECONDARY)
            book_index = (book_index + 1) % BOOK_COUNT;
        break;
    default:
        break;
    }
    return PANEL_COMMAND_NONE;
}

static void move_focus(int direction)
{
    if (object_count <= 0 || current_panel == PANEL_KEYBOARD) return;
    if (focused_index < 0 || focused_index >= object_count)
        focused_index = direction < 0 ? object_count - 1 : 0;
    else
        focused_index = (focused_index + direction + object_count) %
                        object_count;
}

static void activate_focused(void)
{
    if (focused_index < 0 || focused_index >= object_count) return;
    sound_play(SOUND_TOUCH);
    pending_key_command = panel_activate(&objects[focused_index]);
}

bool panel_handle_key(const input_event *ev)
{
    if (ev == NULL || !panel_active() ||
        (ev->kind != IN_KEY_DOWN && ev->kind != IN_KEY_REPEAT))
        return false;

    if (ev->key == KEY_ESCAPE) {
        if (ev->kind == IN_KEY_DOWN) {
            if (current_panel == PANEL_KEYBOARD) {
                leave_keyboard();
                sound_play(SOUND_DISMISS);
            }
            else panel_close(true);
        }
        return true;
    }
    if (ev->key == KEY_TAB) {
        if (ev->kind == IN_KEY_DOWN)
            move_focus((ev->mods & MOD_SHIFT) != 0 ? -1 : 1);
        return true;
    }
    if (current_panel == PANEL_KEYBOARD || current_panel == PANEL_NOTES ||
        (current_panel == PANEL_MAIL && mail_target_configured)) {
        if (current_panel != PANEL_KEYBOARD) {
            keyboard_target = current_panel == PANEL_MAIL
                                  ? KEYBOARD_MAIL_DRAFT : KEYBOARD_NOTE;
        }
        if (ev->key == KEY_BACKSPACE) {
            erase_character();
            sound_play(SOUND_KEYBOARD);
            return true;
        }
        if (ev->key == KEY_ENTER && current_panel == PANEL_KEYBOARD) {
            if (ev->kind == IN_KEY_DOWN) {
                bool save_mail_target =
                    keyboard_target == KEYBOARD_MAIL_TARGET;
                sound_play(SOUND_KEYBOARD);
                leave_keyboard();
                if (save_mail_target)
                    pending_key_command = PANEL_COMMAND_SAVE_MAIL_TARGET;
                sound_play(SOUND_DISMISS);
            }
            return true;
        }
        if (ev->key >= 32 && ev->key <= 126 &&
            (ev->mods & (MOD_CTRL | MOD_ALT)) == 0) {
            char ch = (char)ev->key;
            if ((ev->mods & MOD_SHIFT) != 0)
                ch = (char)toupper((unsigned char)ch);
            append_character(ch);
            sound_play(SOUND_KEYBOARD);
            return true;
        }
    }
    if (current_panel != PANEL_KEYBOARD &&
        (ev->key == KEY_ENTER || ev->key == ' ')) {
        if (ev->kind == IN_KEY_DOWN) activate_focused();
        return true;
    }
    return true; /* a modal consumes other keys instead of quitting the app */
}

PanelCommand panel_take_command(void)
{
    PanelCommand command = pending_key_command;
    pending_key_command = PANEL_COMMAND_NONE;
    return command;
}

static uint32_t mix_color(uint32_t a, uint32_t b, unsigned b_weight)
{
    unsigned a_weight = 256u - b_weight;
    unsigned ar = (a >> 16) & 0xffu, ag = (a >> 8) & 0xffu, ab = a & 0xffu;
    unsigned br = (b >> 16) & 0xffu, bg = (b >> 8) & 0xffu, bb = b & 0xffu;
    return (((ar * a_weight + br * b_weight) >> 8) << 16) |
           (((ag * a_weight + bg * b_weight) >> 8) << 8) |
           ((ab * a_weight + bb * b_weight) >> 8);
}

static uint32_t panel_accent(void)
{
    static const uint32_t accents[PANEL_COUNT] = {
        UI_TEAL,   UI_GOLD,   UI_BLUE,   UI_ORANGE, UI_CORAL,
        UI_PURPLE, UI_GREEN,  UI_CORAL,  UI_TEAL,   UI_WOOD,
        0x31786fu, UI_BLUE,   UI_NAVY_LIGHT, 0x3f79b7u, UI_CORAL,
        UI_ORANGE, UI_SLATE,  UI_TEAL,   UI_CORAL,  UI_WOOD
    };
    if (current_panel <= PANEL_NONE || current_panel >= PANEL_COUNT)
        return UI_TEAL;
    return accents[current_panel];
}

static IconId panel_icon(void)
{
    static const IconId icons[PANEL_COUNT] = {
        ICON_NONE,       ICON_CLOCK,      ICON_INBOX,      ICON_OUTBOX,
        ICON_POSTCARD,   ICON_NAMECARD,   ICON_NOTEBOOK,   ICON_DATEBOOK,
        ICON_CARDFILE,   ICON_CABINET,    ICON_PHONE,      ICON_STATIONERY,
        ICON_TOOLBOX,    ICON_GLOBE,      ICON_POSTCARD,   ICON_BOX,
        ICON_TOOLBOX,    ICON_KEYBOARD,   ICON_CRATE,      ICON_NOTEBOOK
    };
    if (current_panel <= PANEL_NONE || current_panel >= PANEL_COUNT)
        return ICON_NONE;
    return icons[current_panel];
}

static void fit_text(char *out, size_t out_size, const char *text,
                     size_t max_chars)
{
    size_t length;
    if (out_size == 0) return;
    if (text == NULL) text = "";
    length = strlen(text);
    if (length <= max_chars || max_chars < 4) {
        (void)snprintf(out, out_size, "%.*s", (int)max_chars, text);
        return;
    }
    (void)snprintf(out, out_size, "%.*s...", (int)(max_chars - 3), text);
}

static void fit_text_pixels(char *out, size_t out_size, const char *text,
                            int max_width)
{
    size_t keep;
    if (out_size == 0) return;
    if (text == NULL) text = "";
    if (draw_text_width(text) <= max_width) {
        (void)snprintf(out, out_size, "%s", text);
        return;
    }
    keep = strlen(text);
    while (keep > 3) {
        (void)snprintf(out, out_size, "%.*s...", (int)(keep - 3), text);
        if (draw_text_width(out) <= max_width) return;
        keep--;
    }
    out[0] = '\0';
}

static void draw_body_card(Canvas *c, uint32_t accent, int height)
{
    const int x = panel_rect.x + 14;
    const int y = 84;
    const int w = panel_rect.w - 28;
    draw_shadow(c, x, y, w, height);
    draw_round_rect(c, x, y, w, height, 8, MC_WHITE);
    draw_frame(c, x, y, w, height, 1,
               mix_color(accent, UI_NAVY, 118u));
    draw_rect(c, x, y + 8, 5, height - 16, accent);
}

static void draw_body_heading(Canvas *c, const char *text, uint32_t accent)
{
    draw_text(c, panel_rect.x + 28, 94, text,
              mix_color(accent, UI_NAVY, 148u));
}

static void draw_body_text(Canvas *c, int x, int y, const char *text,
                           uint32_t color)
{
    draw_text(c, panel_rect.x + x, y, text, color);
}

static void draw_badge(Canvas *c, int x, int y, int w, const char *text,
                       uint32_t accent)
{
    draw_round_rect(c, x, y, w, 24, 12,
                    mix_color(accent, MC_WHITE, 194u));
    draw_frame(c, x, y, w, 24, 1, accent);
    draw_text_center(c, x + w / 2, y + 5, text,
                     mix_color(accent, UI_NAVY, 128u));
}

static void draw_envelope(Canvas *c, int x, int y, int w, int h,
                          uint32_t accent, bool incoming)
{
    draw_shadow(c, x, y, w, h);
    draw_rect(c, x, y, w, h, 0xfffbf4u);
    draw_frame(c, x, y, w, h, 2, mix_color(accent, UI_NAVY, 120u));
    draw_line_hard(c, x + 2, y + 2, x + w / 2, y + h / 2, accent);
    draw_line_hard(c, x + w - 3, y + 2, x + w / 2, y + h / 2,
                   accent);
    draw_line_hard(c, x + 2, y + h - 3, x + w / 2, y + h / 2,
                   mix_color(accent, UI_NAVY, 80u));
    draw_line_hard(c, x + w - 3, y + h - 3, x + w / 2, y + h / 2,
                   mix_color(accent, UI_NAVY, 80u));
    if (incoming) {
        draw_disc(c, x + w - 3, y + 2, 9, UI_CORAL);
        draw_text_center(c, x + w - 3, y - 5, "!", MC_WHITE);
    }
}

static void draw_calendar_art(Canvas *c, int x, int y, int offset,
                              uint32_t accent)
{
    char month[16];
    draw_shadow(c, x, y, 88, 83);
    draw_round_rect(c, x, y, 88, 83, 5, MC_WHITE);
    draw_rect(c, x, y, 88, 24, accent);
    draw_frame(c, x, y, 88, 83, 1, mix_color(accent, UI_NAVY, 128u));
    snprintf(month, sizeof month, "%+d MONTH", offset);
    draw_text_center(c, x + 44, y + 5, offset == 0 ? "THIS MONTH" : month,
                     MC_WHITE);
    for (int row = 0; row < 3; row++) {
        for (int col = 0; col < 5; col++) {
            uint32_t fill = row == 1 && col == 2
                                ? UI_GOLD
                                : mix_color(accent, MC_WHITE, 224u);
            draw_round_rect(c, x + 8 + col * 15, y + 31 + row * 15,
                            10, 10, 2, fill);
        }
    }
}

static void draw_phone_art(Canvas *c, int x, int y, uint32_t accent,
                           bool ringing)
{
    static const int dial_x[8] = {0, 7, 10, 7, 0, -7, -10, -7};
    static const int dial_y[8] = {-10, -7, 0, 7, 10, 7, 0, -7};
    uint32_t dark = mix_color(accent, UI_NAVY, 126u);
    if (ringing) {
        draw_ring_hard(c, x + 39, y + 37, 44, 42, UI_GOLD);
        draw_ring_hard(c, x + 39, y + 37, 38, 36, UI_ORANGE);
    }
    draw_shadow(c, x + 7, y + 28, 66, 47);
    draw_round_rect(c, x + 7, y + 28, 66, 47, 10, accent);
    draw_frame(c, x + 7, y + 28, 66, 47, 2, dark);
    draw_round_rect(c, x + 11, y + 5, 58, 17, 8, dark);
    draw_disc(c, x + 14, y + 13, 9, dark);
    draw_disc(c, x + 66, y + 13, 9, dark);
    draw_rect(c, x + 15, y + 10, 50, 9, dark);
    draw_disc(c, x + 40, y + 52, 18, dark);
    draw_disc(c, x + 40, y + 52, 13, MC_WHITE);
    draw_disc(c, x + 40, y + 52, 5, accent);
    for (int i = 0; i < 8; i++)
        draw_disc(c, x + 40 + dial_x[i], y + 52 + dial_y[i], 2, dark);
    draw_rect(c, x + 17, y + 69, 46, 3, dark);
}

static void draw_notepaper(Canvas *c, int x, int y, uint32_t accent,
                           const char *text)
{
    char short_text[18];
    draw_shadow(c, x, y, 91, 84);
    draw_rect(c, x, y, 91, 84, 0xfff8d9u);
    draw_frame(c, x, y, 91, 84, 1, accent);
    draw_rect(c, x + 12, y, 2, 84, UI_CORAL);
    for (int i = 0; i < 4; i++)
        draw_rect(c, x + 8, y + 22 + i * 14, 74, 1,
                  mix_color(UI_BLUE, MC_WHITE, 130u));
    fit_text(short_text, sizeof short_text, text, 10);
    draw_text(c, x + 19, y + 7, short_text, UI_NAVY);
    for (int i = 0; i < 5; i++)
        draw_disc(c, x + 10 + i * 17, y, 3, UI_SLATE);
}

static void draw_calculator_art(Canvas *c, int x, int y, int value,
                                uint32_t accent)
{
    char display[16];
    uint32_t dark = mix_color(accent, UI_NAVY, 105u);
    draw_shadow(c, x, y, 90, 88);
    draw_round_rect(c, x, y, 90, 88, 7, dark);
    draw_frame(c, x, y, 90, 88, 2, UI_NAVY);
    draw_round_rect(c, x + 9, y + 9, 72, 23, 3, 0xcde3c1u);
    snprintf(display, sizeof display, "%d", value);
    draw_text(c, x + 75 - draw_text_width(display), y + 14, display,
              UI_NAVY);
    for (int row = 0; row < 3; row++) {
        for (int col = 0; col < 4; col++) {
            uint32_t fill = col == 3 ? UI_ORANGE : MC_WHITE;
            draw_round_rect(c, x + 10 + col * 18, y + 40 + row * 14,
                            13, 10, 2, fill);
        }
    }
}

static void draw_browser_art(Canvas *c, int x, int y, int w, int h,
                             uint32_t accent, bool cached)
{
    draw_shadow(c, x, y, w, h);
    draw_round_rect(c, x, y, w, h, 6, MC_WHITE);
    draw_frame(c, x, y, w, h, 1, UI_NAVY);
    draw_rect(c, x, y, w, 20, mix_color(accent, UI_NAVY, 80u));
    draw_disc(c, x + 11, y + 10, 3, UI_CORAL);
    draw_disc(c, x + 21, y + 10, 3, UI_GOLD);
    draw_disc(c, x + 31, y + 10, 3, UI_GREEN);
    draw_round_rect(c, x + 44, y + 5, w - 53, 11, 5, MC_WHITE);
    draw_text(c, x + 15, y + 30, cached ? "ROOM GUIDE / LOCAL COPY" :
                                            "OFFLINE / LOCAL ONLY",
              UI_NAVY);
    draw_rect(c, x + 15, y + h - 18, w - 80, 3,
              mix_color(accent, MC_WHITE, 120u));
    draw_rect(c, x + 15, y + h - 8, w - 120, 3,
              mix_color(accent, MC_WHITE, 160u));
}

static void draw_bag_art(Canvas *c, int x, int y, uint32_t accent)
{
    uint32_t dark = mix_color(accent, UI_WOOD_DARK, 110u);
    draw_ring_hard(c, x + 40, y + 23, 26, 22, dark);
    draw_shadow(c, x + 4, y + 22, 72, 61);
    draw_round_rect(c, x + 4, y + 22, 72, 61, 10, accent);
    draw_frame(c, x + 4, y + 22, 72, 61, 2, dark);
    draw_rect(c, x + 13, y + 39, 54, 3, UI_GOLD);
    draw_text_center(c, x + 40, y + 52, "TOTE", MC_WHITE);
}

static void draw_truck_art(Canvas *c, int x, int y, uint32_t accent)
{
    uint32_t dark = mix_color(accent, UI_NAVY, 118u);
    draw_shadow(c, x + 2, y + 24, 80, 49);
    draw_round_rect(c, x + 2, y + 24, 53, 43, 5, accent);
    draw_rect(c, x + 55, y + 37, 28, 30, dark);
    draw_rect(c, x + 62, y + 42, 14, 10, UI_BLUE);
    draw_disc(c, x + 18, y + 69, 9, UI_NAVY);
    draw_disc(c, x + 67, y + 69, 9, UI_NAVY);
    draw_disc(c, x + 18, y + 69, 4, UI_GOLD);
    draw_disc(c, x + 67, y + 69, 4, UI_GOLD);
    draw_line_hard(c, x + 13, y + 34, x + 44, y + 57, MC_WHITE);
    draw_line_hard(c, x + 44, y + 34, x + 13, y + 57, MC_WHITE);
}

static void draw_book_art(Canvas *c, int x, int y, uint32_t accent)
{
    draw_shadow(c, x, y + 4, 106, 76);
    draw_round_rect(c, x, y, 52, 76, 5, 0xfff9e8u);
    draw_round_rect(c, x + 54, y, 52, 76, 5, 0xfff9e8u);
    draw_frame(c, x, y, 106, 76, 1, accent);
    draw_rect(c, x + 52, y + 3, 3, 70, UI_WOOD_DARK);
    for (int i = 0; i < 4; i++) {
        draw_rect(c, x + 9, y + 16 + i * 12, 34, 2,
                  mix_color(accent, MC_WHITE, 120u));
        draw_rect(c, x + 64, y + 16 + i * 12, 33, 2,
                  mix_color(accent, MC_WHITE, 120u));
    }
}

static void draw_body(Canvas *c)
{
    uint32_t accent = panel_accent();
    char line[96];
    char short_text[40];

    if (current_panel == PANEL_KEYBOARD) {
        draw_shadow(c, 62, 84, 356, 158);
        draw_round_rect(c, 62, 84, 356, 158, 8,
                        mix_color(UI_NAVY, MC_WHITE, 36u));
        draw_frame(c, 62, 84, 356, 158, 1, UI_GOLD);
        return;
    }

    draw_body_card(c, accent,
                   current_panel >= PANEL_CLOCK && current_panel <= PANEL_WEB
                       ? 108 : 116);
    switch (current_panel) {
    case PANEL_CLOCK: {
        int shown = clock_hour;
        const char *suffix = "";
        if (!clock_24h) {
            suffix = clock_hour < 12 ? " AM" : " PM";
            shown %= 12;
            if (shown == 0) shown = 12;
        }
        draw_body_heading(c, "LOCAL DESK TIME", accent);
        snprintf(line, sizeof line, "%02d:41%s", shown, suffix);
        draw_body_text(c, 28, 121, line, UI_NAVY);
        draw_badge(c, 82, 148, 112, clock_24h ? "24-HOUR" : "12-HOUR",
                   accent);
        draw_body_text(c, 28, 174, "Quiet, local, dependable.", MC_DARK);
        draw_disc(c, 374, 139, 36, mix_color(accent, UI_NAVY, 112u));
        draw_disc(c, 371, 136, 33, MC_WHITE);
        draw_ring_hard(c, 371, 136, 33, 29, accent);
        for (int i = -1; i <= 1; i++) {
            draw_rect(c, 369 + i, 107, 2, 7, UI_NAVY);
            draw_rect(c, 369 + i, 158, 2, 7, UI_NAVY);
        }
        draw_rect(c, 340, 134, 7, 2, UI_NAVY);
        draw_rect(c, 395, 134, 7, 2, UI_NAVY);
        draw_line_hard(c, 371, 136, 371, 116, UI_NAVY);
        draw_line_hard(c, 371, 136, 389, 141, UI_CORAL);
        draw_disc(c, 371, 136, 3, UI_GOLD);
        break;
    }
    case PANEL_INBOX:
        draw_body_heading(c, "INCOMING MAIL", accent);
        snprintf(line, sizeof line, "%d waiting", inbox_count);
        draw_body_text(c, 28, 121, line, UI_NAVY);
        draw_badge(c, 82, 148, 128,
                   inbox_checked ? "CHECKED" : "NOT CHECKED", accent);
        draw_body_text(c, 28, 174,
                       inbox_count ? "Local courier delivery." :
                                     "The tray is clear.", MC_DARK);
        draw_envelope(c, 337, 111, 70, 52, accent, inbox_count > 0);
        break;
    case PANEL_OUTBOX:
        draw_body_heading(c, "DELIVERY QUEUE", accent);
        snprintf(line, sizeof line, "%d message%s ready", outbox_count,
                 outbox_count == 1 ? "" : "s");
        draw_body_text(c, 28, 121, line, UI_NAVY);
        draw_badge(c, 82, 148, 104,
                   outbox_count > 0 ? "QUEUED" : "SENT", accent);
        draw_body_text(c, 28, 174, "Send clears the local queue.", MC_DARK);
        draw_envelope(c, 337, 111, 70, 52, accent, false);
        draw_line_hard(c, 348, 172, 397, 172, accent);
        draw_line_hard(c, 397, 172, 389, 166, accent);
        draw_line_hard(c, 397, 172, 389, 178, accent);
        break;
    case PANEL_MAIL:
        if (!mail_target_configured) {
            draw_body_heading(c, "MAIL SETUP", accent);
            draw_body_text(c, 28, 121, "No mail target is registered.",
                           UI_NAVY);
            draw_badge(c, 82, 148, 128, "SETUP NEEDED", accent);
            draw_body_text(c, 28, 174, "Add a program or webmail URL.",
                           MC_DARK);
        } else {
            draw_body_heading(c, "MESSAGE DRAFT", accent);
            fit_text_pixels(short_text, sizeof short_text,
                            mail_text[0] ? mail_text : "(empty)", 196);
            draw_round_rect(c, 82, 118, 224, 30, 5, 0xfff8edu);
            draw_frame(c, 82, 118, 224, 30, 1, accent);
            draw_text(c, 91, 126, short_text, UI_NAVY);
            draw_rect(c, 93 + draw_text_width(short_text), 123, 2, 18,
                      accent);
            snprintf(line, sizeof line, "Out box: %d", outbox_count);
            draw_body_text(c, 28, 155, line, MC_DARK);
            draw_body_text(c, 28, 174, "Click Mail to open its target.",
                           MC_DARK);
        }
        draw_envelope(c, 337, 112, 70, 50, accent, false);
        break;
    case PANEL_PROFILE:
        draw_body_heading(c, "LOCAL IDENTITY", accent);
        draw_body_text(c, 28, 121, "Kilix Cap Guest", UI_NAVY);
        draw_badge(c, 82, 148, 128,
                   profile_away ? "AWAY" : "AVAILABLE", accent);
        draw_body_text(c, 28, 174, "Shared only inside Kilix Cap.", MC_DARK);
        draw_disc(c, 372, 126, 31, mix_color(accent, MC_WHITE, 145u));
        draw_disc(c, 372, 117, 12, accent);
        draw_round_rect(c, 346, 132, 52, 34, 16, accent);
        draw_disc(c, 401, 164, 8,
                  profile_away ? UI_ORANGE : UI_GREEN);
        break;
    case PANEL_NOTES:
        draw_body_heading(c, "NOTEPAD / PAGE 1", accent);
        fit_text_pixels(short_text, sizeof short_text,
                        note_text[0] ? note_text : "(blank page)", 190);
        draw_round_rect(c, 82, 116, 218, 30, 5, 0xfff8edu);
        draw_frame(c, 82, 116, 218, 30, 1, accent);
        draw_text(c, 91, 124, short_text, UI_NAVY);
        draw_rect(c, 93 + draw_text_width(short_text), 121, 2, 18, accent);
        draw_body_text(c, 28, 151, "Printable keys edit directly.", MC_DARK);
        draw_badge(c, 82, 166, 88, note_text[0] ? "SAVED" : "BLANK",
                   accent);
        draw_notepaper(c, 320, 96, accent,
                       note_text[0] ? note_text : "blank");
        break;
    case PANEL_DATES:
        draw_body_heading(c, "DATEBOOK", accent);
        snprintf(line, sizeof line, "Month offset: %+d", date_offset);
        draw_body_text(c, 28, 121, line, UI_NAVY);
        draw_body_text(c, 28, 148, "Tue 10:00  Library", MC_DARK);
        draw_body_text(c, 28, 171, "Thu 15:30  Game Room", MC_DARK);
        draw_calendar_art(c, 320, 96, date_offset, accent);
        break;
    case PANEL_CARDS:
        draw_body_heading(c, "NAME CARD FILE", accent);
        draw_body_text(c, 28, 121, contact_names[card_index], UI_NAVY);
        draw_body_text(c, 28, 148, contact_notes[card_index], MC_DARK);
        snprintf(line, sizeof line, "CARD %d / 3", card_index + 1);
        draw_badge(c, 82, 166, 96, line, accent);
        draw_shadow(c, 313, 105, 98, 65);
        draw_round_rect(c, 313, 105, 98, 65, 5, MC_WHITE);
        draw_frame(c, 313, 105, 98, 65, 2, accent);
        draw_disc(c, 336, 130, 11, accent);
        draw_round_rect(c, 324, 141, 24, 17, 8, accent);
        draw_rect(c, 356, 120, 43, 3, UI_NAVY);
        draw_rect(c, 356, 133, 35, 2, MC_DARK);
        draw_rect(c, 356, 145, 39, 2, MC_DARK);
        break;
    case PANEL_FILES:
        draw_body_heading(c, "FILE CABINET", accent);
        draw_body_text(c, 28, 121, file_names[file_index], UI_NAVY);
        fit_text(short_text, sizeof short_text, file_notes[file_index], 29);
        draw_body_text(c, 28, 148, short_text, MC_DARK);
        snprintf(line, sizeof line, "FILE %d / 4", file_index + 1);
        draw_badge(c, 82, 166, 96, line, accent);
        draw_shadow(c, 342, 99, 60, 80);
        draw_gradient_v(c, 342, 99, 60, 80, 0xb77745u, UI_WOOD);
        draw_frame(c, 342, 99, 60, 80, 2, UI_WOOD_DARK);
        for (int i = 0; i < 3; i++) {
            draw_frame(c, 349, 107 + i * 23, 46, 18, 1, UI_WOOD_DARK);
            draw_rect(c, 365, 113 + i * 23, 14, 3, UI_GOLD);
        }
        break;
    case PANEL_PHONE:
        draw_body_heading(c, "LOCAL TELEPHONE", accent);
        if (phone_unavailable_reason[0] != '\0') {
            draw_body_text(c, 28, 121, "No external calling service.",
                           UI_NAVY);
            draw_badge(c, 82, 148, 112,
                       phone_ringing ? "RINGING" : "LOCAL ONLY", accent);
            draw_body_text(c, 28, 174, "Ring is a local sound demo.",
                           MC_DARK);
        } else {
            draw_body_text(c, 28, 121,
                           phone_ringing ? "Incoming local call..." :
                                           "Telephone is idle.", UI_NAVY);
            draw_badge(c, 82, 148, 112,
                       phone_ringing ? "RINGING" : "READY", accent);
            draw_body_text(c, 28, 174, "Sound always has a visual cue.",
                           MC_DARK);
        }
        draw_phone_art(c, 328, 99, accent, phone_ringing);
        break;
    case PANEL_PAPER:
        draw_body_heading(c, "STATIONERY DESK", accent);
        snprintf(line, sizeof line, "Blank sheets: %d", paper_sheets);
        draw_body_text(c, 28, 121, line, UI_NAVY);
        snprintf(line, sizeof line, "Copies in Tote: %d", copy_count);
        draw_body_text(c, 28, 148, line, MC_DARK);
        draw_badge(c, 82, 166, 96, "A4 / CREAM", accent);
        for (int i = 3; i >= 0; i--) {
            draw_shadow(c, 331 + i * 4, 105 + i * 4, 65, 61);
            draw_rect(c, 331 + i * 4, 105 + i * 4, 65, 61,
                      i == 0 ? 0xfff6e4u : MC_WHITE);
            draw_frame(c, 331 + i * 4, 105 + i * 4, 65, 61, 1, accent);
        }
        draw_rect(c, 341, 119, 43, 3, accent);
        draw_rect(c, 341, 130, 35, 2, MC_DARK);
        draw_rect(c, 341, 141, 41, 2, MC_DARK);
        break;
    case PANEL_CALCULATOR:
        draw_body_heading(c, "DESK CALCULATOR", accent);
        snprintf(line, sizeof line, "Display: %d", calculator_value);
        draw_body_text(c, 28, 121, line, UI_NAVY);
        draw_badge(c, 82, 148, 112, "LOCAL MATH", accent);
        draw_body_text(c, 28, 174, "A small, dependable counter.", MC_DARK);
        draw_calculator_art(c, 320, 96, calculator_value, accent);
        break;
    case PANEL_WEB:
        draw_body_heading(c, "LOCAL WEB", accent);
        draw_browser_art(c, 82, 113, 316, 54, accent, web_cached);
        draw_disc(c, 92, 181, 5, web_checked ? UI_ORANGE : UI_GREEN);
        draw_body_text(c, 48, 174,
                       web_checked ? "Retry complete: safely offline" :
                                     "No external service contacted", MC_DARK);
        break;
    case PANEL_STAMPER:
        draw_body_heading(c, "COPY STUDIO", accent);
        snprintf(line, sizeof line, "Copies in Tote: %d", copy_count);
        draw_body_text(c, 28, 122, line, UI_NAVY);
        draw_body_text(c, 28, 151, "Choose a mark below.", MC_DARK);
        draw_badge(c, 82, 169, 112, "INK READY", accent);
        draw_disc(c, 346, 123, 22, UI_GOLD);
        draw_line_hard(c, 346, 103, 346, 143, UI_CORAL);
        draw_line_hard(c, 326, 123, 366, 123, UI_CORAL);
        draw_line_hard(c, 332, 109, 360, 137, UI_CORAL);
        draw_line_hard(c, 360, 109, 332, 137, UI_CORAL);
        draw_disc(c, 390, 151, 20, UI_GREEN);
        draw_line_hard(c, 380, 161, 400, 141, MC_WHITE);
        break;
    case PANEL_TOTE:
        draw_body_heading(c, "TOTE INVENTORY", accent);
        snprintf(line, sizeof line, "Room items: %d", tote_items);
        draw_body_text(c, 28, 122, line, UI_NAVY);
        snprintf(line, sizeof line, "Paper and stamps: %d", copy_count);
        draw_body_text(c, 28, 149, line, MC_DARK);
        draw_body_text(c, 28, 174,
                       tote_items > 0 ? "Put back returns one item." :
                                        "Tote is empty; drop items here.",
                       MC_DARK);
        draw_bag_art(c, 328, 99, accent);
        break;
    case PANEL_TOOL_HOLDER:
        draw_body_heading(c, "WORKSPACE TOOLS", accent);
        draw_body_text(c, 28, 122,
                       sound_is_enabled() ? "Sound cues: ON" :
                                            "Sound cues: MUTED", UI_NAVY);
        draw_round_rect(c, 227, 116, 68, 24, 12, MC_LIGHT);
        draw_disc(c, sound_is_enabled() ? 282 : 240, 128, 9,
                  sound_is_enabled() ? UI_GREEN : MC_DARK);
        draw_body_text(c, 28, 151, "Every cue has a visual match.", MC_DARK);
        draw_body_text(c, 28, 174, "Reset restores the workspace.", MC_DARK);
        draw_shadow(c, 348, 107, 52, 72);
        draw_round_rect(c, 348, 107, 52, 72, 6, UI_SLATE);
        draw_rect(c, 357, 118, 7, 48, UI_CORAL);
        draw_rect(c, 370, 112, 7, 54, UI_GOLD);
        draw_rect(c, 383, 124, 7, 42, UI_TEAL);
        break;
    case PANEL_TRASH:
        draw_body_heading(c, "RECOVERY TRUCK", accent);
        snprintf(line, sizeof line, "Room items: %d", trash_items);
        draw_body_text(c, 28, 122, line, UI_NAVY);
        snprintf(line, sizeof line, "Disposable copies: %d", copy_count);
        draw_body_text(c, 28, 149, line, MC_DARK);
        draw_body_text(c, 28, 174,
                       trash_items > 0 ? "Restore first, then empty." :
                                         "Trash is empty.", MC_DARK);
        draw_truck_art(c, 326, 101, accent);
        break;
    case PANEL_BOOK:
        draw_body_heading(c, book_titles[book_index], accent);
        fit_text(short_text, sizeof short_text, book_line_a[book_index], 26);
        draw_body_text(c, 28, 122, short_text, UI_NAVY);
        fit_text(short_text, sizeof short_text, book_line_b[book_index], 26);
        draw_body_text(c, 28, 149, short_text, MC_DARK);
        snprintf(line, sizeof line, "VOLUME %d / %d", book_index + 1,
                 BOOK_COUNT);
        draw_badge(c, 82, 169, 112, line, accent);
        draw_book_art(c, 305, 101, accent);
        break;
    case PANEL_NONE:
    case PANEL_COUNT:
    default:
        break;
    }
}

static void draw_panel_button(Canvas *c, const Object *o, uint32_t accent)
{
    int x = o->visual.x;
    int y = o->visual.y;
    int w = o->visual.w;
    int h = o->visual.h;
    uint32_t dark = mix_color(accent, UI_NAVY, 132u);
    uint32_t fill = MC_WHITE;
    uint32_t ink = UI_NAVY;
    uint32_t border = dark;

    bool focused = focused_index >= 0 && focused_index < object_count &&
                   o == &objects[focused_index];
    bool equal_group = current_panel == PANEL_DATES ||
                       current_panel == PANEL_CARDS ||
                       current_panel == PANEL_FILES ||
                       current_panel == PANEL_STAMPER ||
                       current_panel == PANEL_BOOK;
    bool destructive = o->label != NULL &&
                       (strcmp(o->label, "Clear") == 0 ||
                        strcmp(o->label, "Clear copies") == 0 ||
                        strcmp(o->label, "Empty") == 0 ||
                        strcmp(o->label, "Reset") == 0);

    if (o->pressed) y += 2;
    if (o->target == ACTION_CLOSE) {
        fill = mix_color(UI_CORAL, UI_NAVY, 72u);
        ink = MC_WHITE;
        border = mix_color(UI_CORAL, UI_NAVY, 130u);
    } else if (current_panel == PANEL_KEYBOARD) {
        if (o->target == ACTION_KEY_DONE) {
            fill = dark;
            ink = MC_WHITE;
        } else if (o->target == ACTION_KEY_BACK) {
            fill = mix_color(UI_CORAL, MC_WHITE, 158u);
            border = UI_CORAL;
        } else if (o->target == ACTION_KEY_SPACE) {
            fill = mix_color(accent, MC_WHITE, 220u);
        }
    } else if (destructive) {
        fill = mix_color(UI_CORAL, MC_WHITE, 202u);
        border = mix_color(UI_CORAL, UI_NAVY, 70u);
        ink = UI_NAVY;
    } else if (equal_group) {
        fill = mix_color(accent, MC_WHITE, 226u);
        border = accent;
        ink = dark;
    } else if (o->active) {
        fill = dark;
        border = UI_GOLD;
        ink = MC_WHITE;
    } else if (o->target == ACTION_PRIMARY ||
               o->target == ACTION_TERTIARY) {
        fill = o->target == ACTION_TERTIARY ? UI_NAVY : dark;
        ink = MC_WHITE;
    } else if (o->target == ACTION_SECONDARY) {
        fill = mix_color(accent, MC_WHITE, 224u);
        border = accent;
    }

    if (o->pressed) {
        fill = mix_color(fill, UI_NAVY, 72u);
        border = MC_WHITE;
    } else {
        draw_shadow(c, x, y, w, h);
    }
    draw_round_rect(c, x, y, w, h, o->target == ACTION_CLOSE ? 16 : 7,
                    fill);
    draw_frame(c, x, y, w, h, 1, border);
    if (focused) {
        draw_frame(c, x - 2, y - 2, w + 4, h + 4, 2, UI_GOLD);
        draw_frame(c, x, y, w, h, 1, MC_WHITE);
    }
    if (current_panel == PANEL_KEYBOARD &&
        o->target >= ACTION_KEY_BASE &&
        o->target < ACTION_KEY_BASE + 26)
        draw_rect(c, x + 4, y + 4, w - 8, 2,
                  mix_color(accent, MC_WHITE, 90u));
    draw_text_center(c, x + w / 2,
                     y + (h - draw_text_height()) / 2,
                     o->label != NULL ? o->label : "", ink);
}

void panel_draw(Canvas *c)
{
    uint32_t accent;
    uint32_t header_dark;
    IconId title_icon;
    int shell_height;

    if (c == NULL || !panel_active()) return;
    accent = panel_accent();
    header_dark = mix_color(accent, UI_NAVY, 196u);
    title_icon = panel_icon();
    shell_height = (current_panel == PANEL_TOTE ||
                    current_panel == PANEL_TRASH) && object_count <= 1
                       ? 160 : panel_rect.h;
    draw_blend_rect(c, 0, CONTENT_Y, CANVAS_W, CONTENT_H, UI_NAVY, 96u);
    draw_shadow(c, panel_rect.x, panel_rect.y, panel_rect.w, shell_height);
    draw_round_rect(c, panel_rect.x, panel_rect.y, panel_rect.w, shell_height,
                    11, 0xf6efe5u);
    draw_frame(c, panel_rect.x, panel_rect.y, panel_rect.w, shell_height,
               DRAW_BORDER, header_dark);
    if (shell_height == panel_rect.h) {
        draw_gradient_v(c, panel_rect.x + 2, 204,
                        panel_rect.w - 4,
                        panel_rect.y + shell_height - 206,
                        0xeee4d6u, 0xddd0bfu);
        draw_rect(c, panel_rect.x + 2, 203, panel_rect.w - 4, 1,
                  mix_color(accent, MC_WHITE, 155u));
    }
    draw_gradient_v(c, panel_rect.x + 2, panel_rect.y + 2,
                    panel_rect.w - 4, 30,
                    mix_color(accent, UI_NAVY, 132u), header_dark);
    draw_rect(c, panel_rect.x + 2, panel_rect.y + 30, panel_rect.w - 4, 2,
              UI_GOLD);
    draw_round_rect(c, panel_rect.x + 12, panel_rect.y + 6, 24, 24, 6,
                    MC_WHITE);
    if (title_icon != ICON_NONE)
        icon_draw(c, title_icon, panel_rect.x + 14, panel_rect.y + 8, 20, 20);
    draw_text(c, panel_rect.x + 46, panel_rect.y + 8, panel_title(), MC_WHITE);
    if (current_panel == PANEL_KEYBOARD) {
        char line[40];
        const char *prefix =
            keyboard_target == KEYBOARD_MAIL_DRAFT ? "Mail: " :
            keyboard_target == KEYBOARD_NOTE ? "Note: " :
            keyboard_target == KEYBOARD_MAIL_TARGET ? "Target: " :
                                                       "Scratch: ";
        const char *text = keyboard_buffer()[0] ? keyboard_buffer() : "(empty)";
        size_t length = strlen(text);
        if (length > 13)
            snprintf(line, sizeof line, "%s<%.13s", prefix,
                     text + length - 13);
        else
            snprintf(line, sizeof line, "%s%s", prefix, text);
        draw_round_rect(c, 170, panel_rect.y + 6, 218, 24, 6, MC_WHITE);
        draw_text(c, 180, panel_rect.y + 11, line, UI_NAVY);
        draw_rect(c, 182 + draw_text_width(line), panel_rect.y + 10,
                  2, 16, accent);
    }
    draw_body(c);
    if (current_panel >= PANEL_CLOCK && current_panel <= PANEL_WEB &&
        launch_status[0] != '\0') {
        const char *status = launch_status;
        char fitted[48];
        uint32_t status_accent = launch_status_success ? UI_GREEN : UI_CORAL;
        fit_text(fitted, sizeof fitted, status, 43);
        draw_shadow(c, panel_rect.x + 14, 255, panel_rect.w - 28, 22);
        draw_round_rect(c, panel_rect.x + 14, 255, panel_rect.w - 28, 22,
                        7, mix_color(status_accent, MC_WHITE, 218u));
        draw_frame(c, panel_rect.x + 14, 255, panel_rect.w - 28, 22,
                   1, status_accent);
        draw_disc(c, panel_rect.x + 25, 266, 5, status_accent);
        if (!launch_status_success)
            draw_text_center(c, panel_rect.x + 25, 259, "!", MC_WHITE);
        draw_text(c, panel_rect.x + 36, 259, fitted, UI_NAVY);
    }
    for (int i = 0; i < object_count; i++)
        draw_panel_button(c, &objects[i], accent);
}

void panel_set_storage_counts(int tote, int trash)
{
    tote_items = imaxi(tote, 0);
    trash_items = imaxi(trash, 0);
    if (current_panel == PANEL_TOTE || current_panel == PANEL_TRASH)
        configure_panel();
}

void panel_set_mail_target(const char *target)
{
    if (target == NULL || target[0] == '\0') {
        mail_target_edit[0] = '\0';
        mail_target_configured = false;
    } else {
        (void)snprintf(mail_target_edit, sizeof mail_target_edit, "%s",
                       target);
        mail_target_configured = true;
    }
    if (current_panel == PANEL_MAIL) {
        if (mail_target_configured) {
            launch_status[0] = '\0';
            launch_status_success = true;
        } else {
            (void)snprintf(launch_status, sizeof launch_status, "%s",
                           "Register a mail program or mail URL.");
            launch_status_success = false;
        }
        configure_panel();
    }
}

bool panel_mail_target_configured(void) { return mail_target_configured; }
const char *panel_mail_target_edit(void) { return mail_target_edit; }

void panel_set_phone_unavailable(const char *reason)
{
    if (reason == NULL) phone_unavailable_reason[0] = '\0';
    else
        (void)snprintf(phone_unavailable_reason,
                       sizeof phone_unavailable_reason, "%s", reason);
    if (current_panel == PANEL_PHONE) {
        if (phone_unavailable_reason[0] == '\0') {
            launch_status[0] = '\0';
            launch_status_success = true;
        } else {
            (void)snprintf(launch_status, sizeof launch_status, "%s",
                           phone_unavailable_reason);
            launch_status_success = false;
        }
        configure_panel();
    }
}

void panel_set_launch_status(const char *status, bool success)
{
    if (status == NULL) launch_status[0] = '\0';
    else (void)snprintf(launch_status, sizeof launch_status, "%s", status);
    launch_status_success = success;
}

int panel_copy_count(void) { return copy_count; }
int panel_object_count(void) { return object_count; }

const Object *panel_object(int index)
{
    if (index < 0 || index >= object_count) return NULL;
    return &objects[index];
}

const char *panel_status_text(void) { return launch_status; }
bool panel_status_success(void) { return launch_status_success; }

static uint32_t hash_value(uint32_t h, uint32_t value)
{
    h ^= value;
    return h * 16777619u;
}

static uint32_t hash_text(uint32_t h, const char *text)
{
    while (*text != '\0') h = hash_value(h, (unsigned char)*text++);
    return h;
}

uint32_t panel_digest(void)
{
    uint32_t h = 2166136261u;
    h = hash_value(h, (uint32_t)current_panel);
    h = hash_value(h, (uint32_t)keyboard_return);
    h = hash_value(h, (uint32_t)keyboard_target);
    h = hash_value(h, (uint32_t)clock_hour);
    h = hash_value(h, clock_24h ? 1u : 0u);
    h = hash_value(h, (uint32_t)inbox_count);
    h = hash_value(h, inbox_checked ? 1u : 0u);
    h = hash_value(h, (uint32_t)outbox_count);
    h = hash_value(h, profile_away ? 1u : 0u);
    h = hash_value(h, (uint32_t)(date_offset + 1000));
    h = hash_value(h, (uint32_t)card_index);
    h = hash_value(h, (uint32_t)file_index);
    h = hash_value(h, phone_ringing ? 1u : 0u);
    h = hash_value(h, web_cached ? 1u : 0u);
    h = hash_value(h, web_checked ? 1u : 0u);
    h = hash_value(h, mail_target_configured ? 1u : 0u);
    h = hash_value(h, (uint32_t)paper_sheets);
    h = hash_value(h, (uint32_t)calculator_value);
    h = hash_value(h, (uint32_t)copy_count);
    h = hash_value(h, (uint32_t)book_index);
    h = hash_value(h, (uint32_t)(focused_index + 1));
    h = hash_value(h, launch_status_success ? 1u : 0u);
    h = hash_text(h, mail_text);
    h = hash_text(h, note_text);
    h = hash_text(h, scratch_text);
    h = hash_text(h, mail_target_edit);
    return hash_text(h, launch_status);
}
