                                                        # claude-c128 client
CC65    ?= cl65
TARGET  := c128
NAME    := claude
BUILD   := build

SOURCES := main.c c128hw.s
OBJS    := $(addprefix $(BUILD)/,$(SOURCES:.c=.o))
OBJS    := $(OBJS:.s=.o)

# -Ln emits a VICE label file so tools/emutest.py can inspect client state
# (ring-buffer indices, parser state) inside the emulator.
CFLAGS  := -t $(TARGET) -O -Wl -D__STACKSIZE__=0x0400 -Ln $(BUILD)/$(NAME).lbl

.PHONY: all clean disk run
all: $(BUILD)/$(NAME).prg

$(BUILD):
	@mkdir -p $(BUILD)

$(BUILD)/%.o: %.c | $(BUILD)
	$(CC65) -t $(TARGET) -O -c -o $@ $<

$(BUILD)/%.o: %.s | $(BUILD)
	$(CC65) -t $(TARGET) -c -o $@ $<

$(BUILD)/$(NAME).prg: $(OBJS)
	$(CC65) $(CFLAGS) -o $@ $(OBJS)

# A D64 sized for drive A of the real machine (a 1541 on bus 8).
disk: $(BUILD)/$(NAME).prg
	@rm -f $(BUILD)/$(NAME).d64
	c1541 -format "claude,c1" d64 $(BUILD)/$(NAME).d64 \
	      -write $(BUILD)/$(NAME).prg claude >/dev/null
	@echo "built $(BUILD)/$(NAME).d64"

clean:
	rm -rf $(BUILD)
