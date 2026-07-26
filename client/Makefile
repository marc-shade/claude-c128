                                                        # claude-c128 client
CC65    ?= cl65
NAME    := claude
BUILD   := build

# Two machines share main.c; only the hardware layer differs. The C128 renders
# on the 80-column VDC, the C64 on the VIC-II's 40-column screen.
CFLAGS  := -O -Wl -D__STACKSIZE__=0x0400

# The C64 build copies the ROM character set to $3000 so the bridge can upload
# custom glyphs. Nothing may grow into it, so the build checks rather than hopes.
C64_CHARSET := 12288

.PHONY: all clean disk disk64 check64
all: $(BUILD)/$(NAME).prg $(BUILD)/$(NAME)64.prg

$(BUILD):
	@mkdir -p $(BUILD)

# --- C128 -------------------------------------------------------------------
$(BUILD)/main.o: main.c | $(BUILD)
	$(CC65) -t c128 -O -c -o $@ $<

$(BUILD)/c128hw.o: c128hw.s | $(BUILD)
	$(CC65) -t c128 -c -o $@ $<

# -Ln emits a VICE label file so tools/emutest.py can inspect client state
# (ring-buffer indices, parser state) inside the emulator.
$(BUILD)/$(NAME).prg: $(BUILD)/main.o $(BUILD)/c128hw.o
	$(CC65) -t c128 $(CFLAGS) -Ln $(BUILD)/$(NAME).lbl -o $@ $^

# --- C64 --------------------------------------------------------------------
$(BUILD)/main64.o: main.c | $(BUILD)
	$(CC65) -t c64 -O -c -o $@ $<

$(BUILD)/c64hw.o: c64hw.s | $(BUILD)
	$(CC65) -t c64 -c -o $@ $<

$(BUILD)/$(NAME)64.prg: $(BUILD)/main64.o $(BUILD)/c64hw.o
	$(CC65) -t c64 $(CFLAGS) -Ln $(BUILD)/$(NAME)64.lbl \
	        -Wl --mapfile,$(BUILD)/$(NAME)64.map -o $@ $^
	@$(MAKE) --no-print-directory check64

# The character set lives at $3000 in RAM. If code or data reached it the glyphs
# would be overwritten at runtime and the screen would fill with garbage - a
# failure that looks like a protocol fault, so it is caught at build time.
# Uses the linker's segment map, not the label file: the label file also holds
# size constants such as __MAIN_SIZE__, which look like high addresses.
check64: $(BUILD)/$(NAME)64.map
	@top=$$(awk '/^Segment list/{s=1;next} /^$$/{if(s>1)s=0} \
	             s && $$1 ~ /^[A-Z]/ && $$3 ~ /^[0-9A-F]+$$/ { \
	                 s=2; v = strtonum("0x" $$3); if (v > m && v < 53248) m = v } \
	             END { printf "%d", m }' $(BUILD)/$(NAME)64.map); \
	 if [ "$$top" -ge "$(C64_CHARSET)" ]; then \
	   printf 'C64 layout FAILED: top symbol $$%04X reaches the character set at $$%04X\n' \
	          "$$top" "$(C64_CHARSET)" >&2; exit 1; \
	 fi; \
	 printf 'C64 layout ok: top symbol $$%04X, charset at $$%04X, %d bytes clear\n' \
	        "$$top" "$(C64_CHARSET)" "$$(( $(C64_CHARSET) - top ))"

# --- disks ------------------------------------------------------------------
# A D64 sized for drive A of the real machine (a 1541 on bus 8).
disk: $(BUILD)/$(NAME).prg
	@rm -f $(BUILD)/$(NAME).d64
	c1541 -format "claude,c1" d64 $(BUILD)/$(NAME).d64 \
	      -write $(BUILD)/$(NAME).prg claude >/dev/null
	@echo "built $(BUILD)/$(NAME).d64"

disk64: $(BUILD)/$(NAME)64.prg
	@rm -f $(BUILD)/$(NAME)64.d64
	c1541 -format "claude64,c6" d64 $(BUILD)/$(NAME)64.d64 \
	      -write $(BUILD)/$(NAME)64.prg claude >/dev/null
	@echo "built $(BUILD)/$(NAME)64.d64"

clean:
	rm -rf $(BUILD)
