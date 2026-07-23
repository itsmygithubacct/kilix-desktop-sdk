CC ?= cc
AR ?= ar
KITTY_FRAMEBUFFER_DIR ?= third_party/kitty-framebuffer
KITTY_KEYBOARD_DIR ?= third_party/kitty_keyboard
CPPFLAGS += -D_DEFAULT_SOURCE -D_POSIX_C_SOURCE=200809L -Iinclude \
	-I$(KITTY_FRAMEBUFFER_DIR)/include -I$(KITTY_KEYBOARD_DIR)/include
CFLAGS ?= -O2 -Wall -Wextra -Wpedantic -Werror -std=c11
LDLIBS = -lz -lpthread
BUILD_DIR = build
LIB = $(BUILD_DIR)/libkitty-terminal-session.a
OBJECTS = $(BUILD_DIR)/kitty_terminal_session.o \
	$(BUILD_DIR)/kitty_framebuffer.o $(BUILD_DIR)/kitty_keyboard.o \
	$(BUILD_DIR)/kitty_keyboard_posix.o

all: $(LIB)

$(BUILD_DIR):
	mkdir -p $@

$(BUILD_DIR)/kitty_terminal_session.o: src/kitty_terminal_session.c \
	include/kitty_terminal_session.h | $(BUILD_DIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR)/kitty_framebuffer.o: $(KITTY_FRAMEBUFFER_DIR)/src/kitty_framebuffer.c \
	$(KITTY_FRAMEBUFFER_DIR)/include/kitty_framebuffer.h | $(BUILD_DIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR)/kitty_keyboard.o: $(KITTY_KEYBOARD_DIR)/src/kitty_keyboard.c \
	$(KITTY_KEYBOARD_DIR)/include/kitty_keyboard.h | $(BUILD_DIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR)/kitty_keyboard_posix.o: \
	$(KITTY_KEYBOARD_DIR)/src/kitty_keyboard_posix.c \
	$(KITTY_KEYBOARD_DIR)/include/kitty_keyboard_posix.h | $(BUILD_DIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c -o $@ $<

$(LIB): $(OBJECTS)
	$(AR) rcs $@ $^

$(BUILD_DIR)/test-session: tests/test_session.c $(LIB)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ $< $(LIB) $(LDLIBS) -lutil

test: $(BUILD_DIR)/test-session
	./$(BUILD_DIR)/test-session

sanitize: CFLAGS = -O1 -g -Wall -Wextra -Wpedantic -Werror -std=c11 \
	-fsanitize=address,undefined -fno-omit-frame-pointer
sanitize: clean test

clean:
	rm -rf $(BUILD_DIR)

.PHONY: all test sanitize clean
