# kilix-cap — an original room-metaphor interface for kitty-protocol
# terminals. Dependencies are stdlib + POSIX + pthreads + zlib + libm only;
# everything else is vendored under third_party/ and built from source here.

CC      ?= cc
CFLAGS  ?= -O2 -Wall -Wextra -Wpedantic -std=c11
LDLIBS  ?= -lz -lm -pthread

O       := obj
BINDIR  := bin
BIN     := $(BINDIR)/kilix-cap

KTS := third_party/kitty-terminal-session
KFB := $(KTS)/third_party/kitty-framebuffer
KKB := $(KTS)/third_party/kitty_keyboard
SR  := third_party/soft-raster
PCM := third_party/pcm-mixer

# -I$(KFB)/src is deliberate: term.c calls kittyfb_derive_geometry() from the
# framebuffer's internal header to mirror image placement into the mouse map.
# Generated header dependencies are load-bearing, not a nicety: without them a
# change to a struct in src/*.h rebuilds only the .c files that also changed,
# and the resulting mix of stale and fresh objects disagrees about layout.
# That failure mode is silent at link time and surfaces as garbage field
# values at runtime. Keep the flags out of CPPFLAGS so syntax-only header
# checks do not leak a-*.d files into the repository root.
override CPPFLAGS += -Isrc -I$(KTS)/include -I$(KFB)/include -I$(KFB)/src \
                     -I$(KKB)/include -I$(SR)/include -I$(PCM)/include \
                     -D_DEFAULT_SOURCE -D_POSIX_C_SOURCE=200809L
DEPFLAGS := -MMD -MP

SRC := $(sort $(wildcard src/*.c))
OBJ := $(SRC:src/%.c=$(O)/%.o)

VENDOR_OBJ := \
  $(O)/vendor_kitty_terminal_session.o \
  $(O)/vendor_kitty_framebuffer.o \
  $(O)/vendor_kitty_keyboard.o \
  $(O)/vendor_kitty_keyboard_posix.o \
  $(O)/vendor_soft_raster.o \
  $(O)/vendor_pcm_mixer.o \
  $(O)/vendor_pcm_wav.o

DEP := $(OBJ:.o=.d) $(VENDOR_OBJ:.o=.d)

.PHONY: all clean test test-code test-render validate-audio validate-visual check-headers \
        forbidden-check sanitize release-check run

all: $(BIN)

$(BIN): $(OBJ) $(VENDOR_OBJ) | $(BINDIR)
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

$(O) $(BINDIR):
	mkdir -p $@

$(O)/%.o: src/%.c | $(O)
	$(CC) $(CPPFLAGS) $(DEPFLAGS) $(CFLAGS) -c -o $@ $<

# Explicit per-object vendor rules with their header dependencies listed.
$(O)/vendor_kitty_terminal_session.o: $(KTS)/src/kitty_terminal_session.c \
    $(KTS)/include/kitty_terminal_session.h $(KFB)/include/kitty_framebuffer.h \
    $(KKB)/include/kitty_keyboard_posix.h | $(O)
	$(CC) $(CPPFLAGS) $(DEPFLAGS) $(CFLAGS) -c -o $@ $<

$(O)/vendor_kitty_framebuffer.o: $(KFB)/src/kitty_framebuffer.c \
    $(KFB)/include/kitty_framebuffer.h $(KFB)/src/kitty_framebuffer_internal.h | $(O)
	$(CC) $(CPPFLAGS) $(DEPFLAGS) $(CFLAGS) -c -o $@ $<

$(O)/vendor_kitty_keyboard.o: $(KKB)/src/kitty_keyboard.c \
    $(KKB)/include/kitty_keyboard.h | $(O)
	$(CC) $(CPPFLAGS) $(DEPFLAGS) $(CFLAGS) -c -o $@ $<

$(O)/vendor_kitty_keyboard_posix.o: $(KKB)/src/kitty_keyboard_posix.c \
    $(KKB)/include/kitty_keyboard_posix.h $(KKB)/include/kitty_keyboard.h | $(O)
	$(CC) $(CPPFLAGS) $(DEPFLAGS) $(CFLAGS) -c -o $@ $<

$(O)/vendor_soft_raster.o: $(SR)/src/soft_raster.c \
    $(SR)/include/soft_raster.h $(SR)/src/font8x16.h | $(O)
	$(CC) $(CPPFLAGS) $(DEPFLAGS) $(CFLAGS) -c -o $@ $<

$(O)/vendor_pcm_mixer.o: $(PCM)/src/pcm_mixer.c \
    $(PCM)/include/pcm_mixer.h | $(O)
	$(CC) $(CPPFLAGS) $(DEPFLAGS) $(CFLAGS) -c -o $@ $<

$(O)/vendor_pcm_wav.o: $(PCM)/src/pcm_wav.c \
    $(PCM)/include/pcm_mixer.h | $(O)
	$(CC) $(CPPFLAGS) $(DEPFLAGS) $(CFLAGS) -c -o $@ $<

run: $(BIN)
	./$(BIN)

# Every src/*.h must compile standalone: frozen contracts have to be
# self-contained or they are not contracts.
check-headers:
	@set -e; for h in src/*.h; do \
	  $(CC) $(CPPFLAGS) $(CFLAGS) -fsyntax-only -x c $$h || exit 1; \
	done; echo "check-headers: ok"

# The no-asset subset: builds and proves the logic without needing a
# terminal or any generated asset.
test-code: $(BIN)
	./$(BIN) --version
	python3 tests/cli_smoke.py --binary ./$(BIN)
	./$(BIN) --targets-test
	./$(BIN) --input-test
	./$(BIN) --scene-test
	./$(BIN) --interaction-test
	./$(BIN) --audio-trigger-test
	./$(BIN) --font-test
	./$(BIN) --launcher-test
	./$(BIN) --laptop-test
	python3 tools/kilix_browser.py selftest
	python3 tools/mansion_tui.py selftest
	python3 tools/kilix95_games.py selftest
	./$(BIN) --game-catalog-test
	@set -e; \
	a=$$(./$(BIN) --selftest 1337 400); \
	b=$$(./$(BIN) --selftest 1337 400); \
	e1='selftest: seed=1337 steps=400 digest=1f57e554 scene=Grand Gallery'; \
	e2='selftest: seed=42 steps=900 digest=8e35d73f scene=Server Room'; \
	e3='selftest: seed=90210 steps=1500 digest=adb3e8e0 scene=Study'; \
	[ "$$a" = "$$b" ] || { echo "FAIL selftest is not deterministic"; \
	  echo "  run 1: $$a"; echo "  run 2: $$b"; exit 1; }; \
	[ "$$a" = "$$e1" ] || { echo "FAIL selftest 1337 regression"; \
	  echo "  expected: $$e1"; echo "  actual:   $$a"; exit 1; }; \
	b=$$(./$(BIN) --selftest 42 900); \
	[ "$$b" = "$$e2" ] || { echo "FAIL selftest 42 regression"; \
	  echo "  expected: $$e2"; echo "  actual:   $$b"; exit 1; }; \
	c=$$(./$(BIN) --selftest 90210 1500); \
	[ "$$c" = "$$e3" ] || { echo "FAIL selftest 90210 regression"; \
	  echo "  expected: $$e3"; echo "  actual:   $$c"; exit 1; }; \
	echo "$$a"; echo "$$b"; echo "$$c"; \
	echo "determinism + golden digests: ok"

# Asset validation and exact RGB render structure join the logic gates.
test: test-code check-headers forbidden-check validate-audio validate-visual test-render

test-render: $(BIN)
	@set -e; \
	d=$$(mktemp -d); \
	r=$$(mktemp -d); \
	trap 'rm -rf "$$d" "$$r"' EXIT; \
	./$(BIN) --render-test "$$d"; \
	python3 tools/check_render.py "$$d" --expected \
	  base-desk.ppm base-hallway.ppm base-storeroom.ppm \
	  base-server-room.ppm base-game-room.ppm base-library.ppm \
	  base-cleaning-room.ppm base-balcony.ppm state-desk-hover.ppm \
	  state-desk-web-boot.ppm state-desk-web-zoom.ppm \
	  state-server-hover.ppm state-cleaning-hover.ppm \
	  state-game-hover.ppm state-store-moved.ppm; \
	./$(BIN) --render-review "$$r"; \
	python3 tools/check_render.py "$$r" --expected-count 30

validate-audio: $(BIN)
	python3 tools/validate_audio.py
	./$(BIN) --audio-test

validate-visual: $(BIN)
	python3 tools/validate_visual.py
	./$(BIN) --visual-test

# Makes "we never ingested the original" a testable claim rather than a
# promise (asset contract §7.8). Checks the compiled binary, not the source:
# research notes may name these; shipped strings may not.
forbidden-check: $(BIN)
	python3 tools/forbidden_input_scan.py --binary $(BIN) --assets assets

# A recovering UBSan prints and continues, which lets real UB pass as green.
sanitize:
	$(MAKE) clean
	$(MAKE) O=obj-san BINDIR=bin-san \
	  CFLAGS="-O1 -g -Wall -Wextra -Wpedantic -std=c11 -Werror \
	          -fsanitize=address,undefined -fno-sanitize-recover=undefined \
	          -fno-omit-frame-pointer" \
	  test

release-check:
	$(MAKE) clean
	$(MAKE) all
	$(MAKE) test
	$(MAKE) sanitize
	$(MAKE) clean
	$(MAKE) all
	python3 tests/pty_smoke.py --binary ./$(BIN)

clean:
	rm -rf $(O) $(BINDIR) obj-san bin-san
	rm -f a-*.d

-include $(DEP)
