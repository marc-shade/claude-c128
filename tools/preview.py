#!/usr/bin/env python3
"""Render what the C128 would display, in this terminal.

Closes the loop without hardware: real Claude Code bytes -> pyte -> PETSCII
screen codes -> wire protocol -> decode -> back to glyphs. What you see here is
what the C128 renders, in the C128's 16 colours, one cell per cell.

  python3 tools/preview.py capture.raw
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

import petscii            # noqa: E402
import protocol           # noqa: E402
from vtscreen import VTScreen   # noqa: E402

# One shared inverse map, so the preview shows exactly what the C128 shows.
INVERSE = petscii.inverse_map()


def code_to_char(code):
    return INVERSE.get(code, "?")


def ansi_for(attr):
    """True-colour escape reproducing the VDC colour, so the preview shows the
    16-colour result rather than the original palette."""
    color = attr & 0x0F
    r, g, b = petscii.VDC_PALETTE[color]
    seq = f"\x1b[38;2;{r};{g};{b}m"
    if attr & protocol.ATTR_REVERSE:
        seq += "\x1b[7m"
    if attr & protocol.ATTR_UNDERLINE:
        seq += "\x1b[4m"
    return seq


class PreviewSink:
    """Applies a decoded protocol stream to a virtual C128 screen."""

    def __init__(self, cols=80, rows=25):
        self.cols, self.rows = cols, rows
        self.cells = [[(0x20, 0x0E)] * cols for _ in range(rows)]
        self.cur = None
        self.frames = 0
        self.bells = 0
        self.panel = {}

    def clear(self, attr):
        self.cells = [[(0x20, attr)] * self.cols for _ in range(self.rows)]

    def run(self, row, col, attr, codes):
        if row >= self.rows:
            return
        for i, code in enumerate(codes):
            if col + i < self.cols:
                self.cells[row][col + i] = (code, attr)

    def cursor(self, pos):
        self.cur = pos

    def frame(self):
        self.frames += 1

    def bell(self):
        self.bells += 1

    def panel(self, row, codes):     # noqa: F811 - protocol sink method
        self.panel[row] = bytes(codes)

    def render(self, color=True, border=True):
        lines = []
        if border:
            lines.append("    +" + "-" * self.cols + "+")
        for r, row in enumerate(self.cells):
            out = []
            last = None
            for code, attr in row:
                if color and attr != last:
                    out.append("\x1b[0m" + ansi_for(attr))
                    last = attr
                out.append(code_to_char(code))
            body = "".join(out) + ("\x1b[0m" if color else "")
            lines.append(f"{r:3d} |{body}|" if border else body)
        if border:
            lines.append("    +" + "-" * self.cols + "+")
        return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    raw = open(sys.argv[1], "rb").read()

    vt = VTScreen(80, 25)
    vt.feed(raw)

    differ = protocol.ScreenDiffer(80, 25)
    frame = differ.diff(vt.grid(), vt.cursor())

    sink = PreviewSink(80, 25)
    protocol.decode(frame, sink)

    print(sink.render(color=sys.stdout.isatty() or "--color" in sys.argv))
    print(f"\ninput {len(raw)} bytes of ANSI -> {len(frame)} bytes on the wire "
          f"(first frame is a full repaint)")
    if vt.title():
        print(f"terminal title: {vt.title()!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
