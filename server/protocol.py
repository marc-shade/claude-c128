"""Wire protocol between the Linux bridge and the C128 client.

The C128 is on the far end of a 6551 ACIA, so bandwidth is the binding
constraint: a full 80x25 repaint is ~2KB, which is about half a second at
38400 baud. Claude Code repaints its whole screen constantly, so the bridge
diffs frames and sends only changed cell runs. Typical streaming output touches
one or two lines, i.e. under 100 bytes per frame.

An attribute byte is a VDC attribute directly: bits 0-3 colour, bit 5
underline, bit 6 reverse. The client writes it straight into VDC attribute RAM.
"""
import struct

CMD_CLEAR = 0x01     # attr
CMD_RUN = 0x02       # row, col, attr, len, <len screen codes>
CMD_FILL = 0x03      # row, col, attr, len, char
CMD_CURSOR = 0x04    # row, col   (0xFF,0xFF hides it)
CMD_FRAME = 0x05     # end of frame
CMD_BELL = 0x06
CMD_PANEL = 0x07     # row, len, <len screen codes>  -> 40-col VIC-II panel
CMD_HELLO = 0x08     # cols, rows
CMD_BYE = 0x09
CMD_GLYPH = 0x0A     # code, 8 bitmap bytes -> redefine a VDC character

ATTR_UNDERLINE = 0x20
ATTR_REVERSE = 0x40
ATTR_COLOR_MASK = 0x0F

# Client -> server. A keystroke is never $00, so $00 introduces a control byte.
# The client cannot rely on catching the start of the stream: the link is open
# before the C128 has finished loading, and on real hardware the operator
# starts the client whenever they like. So the client announces itself and asks
# for a full repaint rather than assuming it saw frame one.
CLIENT_ESCAPE = 0x00
CLIENT_RESYNC = 0x01     # "repaint everything, I may have missed bytes"
CLIENT_BYE = 0x02
CLIENT_CREDIT = 0x03     # "I have consumed CREDIT_UNIT more bytes"

# Receiver-driven flow control. The C128 is always the slow party and only it
# knows when it has actually applied a byte, so the server never sends more
# than CREDIT_WINDOW bytes beyond what the client has acknowledged. This is
# transport-independent: neither VICE's RS232 emulation nor the Ultimate's
# TCP-backed modem honours the ACIA's nominal baud, so metering by time cannot
# be made safe, and a burst larger than the client's 256-byte receive ring is
# lost silently as missing rows.
CREDIT_UNIT = 64
CREDIT_WINDOW = 192      # < the client's 255-byte usable ring

MAX_RUN = 255
CURSOR_HIDDEN = (0xFF, 0xFF)


class Encoder:
    """Builds a frame of protocol bytes."""

    def __init__(self):
        self.buf = bytearray()

    def clear(self, attr=0x0E):
        self.buf += bytes((CMD_CLEAR, attr))

    def run(self, row, col, attr, codes):
        while codes:
            chunk, codes = codes[:MAX_RUN], codes[MAX_RUN:]
            self.buf += bytes((CMD_RUN, row, col, attr, len(chunk)))
            self.buf += bytes(chunk)
            col += len(chunk)

    def fill(self, row, col, attr, char, count):
        while count > 0:
            n = min(count, MAX_RUN)
            self.buf += bytes((CMD_FILL, row, col, attr, n, char))
            col += n
            count -= n

    def cursor(self, row, col):
        self.buf += bytes((CMD_CURSOR, row & 0xFF, col & 0xFF))

    def hide_cursor(self):
        self.buf += bytes((CMD_CURSOR, 0xFF, 0xFF))

    def panel(self, row, codes):
        codes = codes[:40]
        self.buf += bytes((CMD_PANEL, row, len(codes))) + bytes(codes)

    def bell(self):
        self.buf += bytes((CMD_BELL,))

    def glyph(self, code, bitmap):
        self.buf += bytes((CMD_GLYPH, code)) + bytes(bitmap)

    def hello(self, cols, rows):
        self.buf += bytes((CMD_HELLO, cols, rows))

    def frame(self):
        self.buf += bytes((CMD_FRAME,))

    def take(self):
        out = bytes(self.buf)
        self.buf = bytearray()
        return out

    def __len__(self):
        return len(self.buf)


# A run shorter than this is not worth splitting off from its neighbour: the
# 5-byte header costs more than just resending the unchanged cells between.
RUN_HEADER = 5
GAP_TOLERANCE = RUN_HEADER


class ScreenDiffer:
    """Tracks what the client is displaying and emits minimal updates."""

    def __init__(self, cols=80, rows=25, blank_attr=0x0E):
        self.cols, self.rows = cols, rows
        self.blank_attr = blank_attr
        self.blank_cell = (0x20, blank_attr)
        self.prev = None
        self.prev_cursor = None

    def reset(self):
        """Forget client state so the next diff is a full repaint."""
        self.prev = None
        self.prev_cursor = None

    def diff(self, grid, cursor):
        """grid: rows x cols list of (screen_code, attr). Returns frame bytes."""
        enc = Encoder()
        full = self.prev is None
        if full:
            enc.clear(self.blank_attr)
            self.prev = [[self.blank_cell] * self.cols for _ in range(self.rows)]

        for r in range(self.rows):
            new_row, old_row = grid[r], self.prev[r]
            for start, end in self._changed_spans(new_row, old_row):
                self._emit_span(enc, r, new_row, start, end)
            self.prev[r] = list(new_row)

        if cursor != self.prev_cursor:
            if cursor is None:
                enc.hide_cursor()
            else:
                enc.cursor(cursor[0], cursor[1])
            self.prev_cursor = cursor

        enc.frame()
        return enc.take()

    def _changed_spans(self, new_row, old_row):
        """Changed column spans, merging ones separated by a tiny clean gap.

        Spans are closed on the last genuinely changed cell, so a run never
        loses its final character to the trailing clean gap.
        """
        spans = []
        col = 0
        while col < self.cols:
            if new_row[col] == old_row[col]:
                col += 1
                continue
            start = last_diff = col
            gap = 0
            while col < self.cols:
                if new_row[col] == old_row[col]:
                    gap += 1
                    if gap > GAP_TOLERANCE:
                        break
                else:
                    gap = 0
                    last_diff = col
                col += 1
            spans.append((start, last_diff + 1))
            col = last_diff + 1 + gap
        return spans

    def _emit_span(self, enc, row, new_row, start, end):
        """Split a span on attribute changes, using FILL for repeated chars."""
        col = start
        while col < end:
            attr = new_row[col][1]
            run_end = col
            while run_end < end and new_row[run_end][1] == attr:
                run_end += 1
            codes = [new_row[c][0] for c in range(col, run_end)]

            # A long stretch of one character is cheaper as a FILL.
            if len(codes) >= 8 and len(set(codes)) == 1:
                enc.fill(row, col, attr, codes[0], len(codes))
            else:
                enc.run(row, col, attr, codes)
            col = run_end


def decode(data, sink):
    """Decode a protocol stream, driving `sink`. Used by the preview renderer
    and by the protocol tests to prove encoder and client agree."""
    i, n = 0, len(data)
    while i < n:
        cmd = data[i]
        i += 1
        if cmd == CMD_CLEAR:
            sink.clear(data[i]); i += 1
        elif cmd == CMD_RUN:
            row, col, attr, ln = data[i:i + 4]
            i += 4
            sink.run(row, col, attr, data[i:i + ln]); i += ln
        elif cmd == CMD_FILL:
            row, col, attr, ln, ch = data[i:i + 5]
            i += 5
            sink.run(row, col, attr, bytes([ch]) * ln)
        elif cmd == CMD_CURSOR:
            row, col = data[i], data[i + 1]
            i += 2
            sink.cursor(None if (row, col) == CURSOR_HIDDEN else (row, col))
        elif cmd == CMD_FRAME:
            sink.frame()
        elif cmd == CMD_BELL:
            sink.bell()
        elif cmd == CMD_PANEL:
            row, ln = data[i], data[i + 1]
            i += 2
            sink.panel(row, data[i:i + ln]); i += ln
        elif cmd == CMD_GLYPH:
            i += 9
        elif cmd == CMD_HELLO:
            i += 2
        elif cmd == CMD_BYE:
            break
        else:
            raise ValueError(f"bad opcode {cmd:#04x} at offset {i - 1}")
    return i
