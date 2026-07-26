#!/usr/bin/env python3
"""Derive the Unicode -> C128 screen-code map from the real character ROM.

Rather than trusting a remembered PETSCII table, this renders every screen code
from the C128 character ROM as an 8x8 bitmap and matches it against bitmaps we
synthesize for the Unicode glyphs Claude Code actually emits. Exact matches are
facts about the ROM; anything unmatched is reported so it gets a deliberate
substitute instead of a silent wrong glyph.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "server"))
import petscii   # noqa: E402

ROM = petscii.ROM_PATH or ""
SET_OFFSET = 0x0000          # C128 mode, uppercase/graphics set
NCHARS = 256


def load_rom(path=ROM, offset=SET_OFFSET):
    data = open(path, "rb").read()
    return [tuple(data[offset + c * 8: offset + c * 8 + 8]) for c in range(NCHARS)]


def rows(*vals):
    """Build an 8-row bitmap from 8 byte values."""
    assert len(vals) == 8
    return tuple(vals)


def solid(top, bottom):
    """Top 4 rows = top pattern, bottom 4 rows = bottom pattern."""
    return tuple([top] * 4 + [bottom] * 4)


def hline(row):
    return tuple(0xFF if r == row else 0x00 for r in range(8))


def vline(bit):
    return tuple(bit for _ in range(8))


L, R, F, E = 0xF0, 0x0F, 0xFF, 0x00

# Block elements are geometrically unambiguous, so these bitmaps are exact.
BLOCKS = {
    "█": solid(F, F),      # FULL BLOCK
    "▌": vline(L),         # LEFT HALF
    "▐": vline(R),         # RIGHT HALF
    "▀": solid(F, E),      # UPPER HALF
    "▄": solid(E, F),      # LOWER HALF
    "▘": solid(L, E),      # QUADRANT UPPER LEFT
    "▝": solid(R, E),      # QUADRANT UPPER RIGHT
    "▖": solid(E, L),      # QUADRANT LOWER LEFT
    "▗": solid(E, R),      # QUADRANT LOWER RIGHT
    "▛": solid(F, L),      # UPPER LEFT + UPPER RIGHT + LOWER LEFT
    "▜": solid(F, R),      # UPPER LEFT + UPPER RIGHT + LOWER RIGHT
    "▙": solid(L, F),      # UPPER LEFT + LOWER LEFT + LOWER RIGHT
    "▟": solid(R, F),      # UPPER RIGHT + LOWER LEFT + LOWER RIGHT
    "▚": solid(L, R),      # QUADRANT UL + LR
    "▞": solid(R, L),      # QUADRANT UR + LL
    "▎": vline(0xC0),      # LEFT ONE QUARTER BLOCK
    "▏": vline(0x80),      # LEFT ONE EIGHTH BLOCK
    "▕": vline(0x01),      # RIGHT ONE EIGHTH BLOCK
    "▔": rows(F, 0, 0, 0, 0, 0, 0, 0),   # UPPER ONE EIGHTH
    "▁": rows(0, 0, 0, 0, 0, 0, 0, F),   # LOWER ONE EIGHTH
}

# Line-drawing: PETSCII may center on row/col 3 or 4, so try both and let the
# ROM decide which is real.
LINES = {
    "─": [hline(3), hline(4)],                    # HORIZONTAL
    "│": [vline(0x10), vline(0x08)],              # VERTICAL
}


def fmt(bitmap):
    return "\n".join(
        "".join("#" if b & (1 << (7 - x)) else "." for x in range(8)) for b in bitmap
    )


def main():
    chars = load_rom()

    # Sanity check: codes 0x80-0xFF should be the bitwise inverse of 0x00-0x7F.
    inverted = sum(
        1 for c in range(128)
        if chars[c + 128] == tuple(b ^ 0xFF for b in chars[c])
    )
    print(f"reverse-video check: {inverted}/128 of codes $80-$FF are exact inverses")

    lookup = {}
    for code, bits in enumerate(chars):
        lookup.setdefault(bits, code)

    print("\n=== block elements (exact bitmap match) ===")
    resolved, missing = {}, []
    for ch, bmp in BLOCKS.items():
        code = lookup.get(bmp)
        if code is None:
            missing.append(ch)
            print(f"  U+{ord(ch):04X} {ch}   NO EXACT MATCH")
        else:
            resolved[ch] = code
            print(f"  U+{ord(ch):04X} {ch}   screen code ${code:02X} ({code})")

    print("\n=== line drawing ===")
    for ch, candidates in LINES.items():
        for bmp in candidates:
            code = lookup.get(bmp)
            if code is not None:
                resolved[ch] = code
                print(f"  U+{ord(ch):04X} {ch}   screen code ${code:02X} ({code})")
                break
        else:
            missing.append(ch)
            print(f"  U+{ord(ch):04X} {ch}   NO EXACT MATCH")

    # Corners/tees: find them by shape rather than by guessing codes. A corner
    # has exactly one horizontal arm and one vertical arm meeting at center.
    print("\n=== corner / tee candidates discovered in ROM ===")
    for code, bits in enumerate(chars[:128]):
        on = [(x, y) for y in range(8) for x in range(8) if bits[y] & (1 << (7 - x))]
        if not (6 <= len(on) <= 14):
            continue
        xs = {x for x, _ in on}
        ys = {y for _, y in on}
        # a single full row or column arm pattern
        rowcount = sum(1 for y in range(8) if bits[y])
        if rowcount == 1 or len(xs) == 1:
            continue
        # centered cross-ish shapes only
        if 3 in ys and (3 in xs or 4 in xs) and len(on) <= 12:
            print(f"  ${code:02X} ({code:3d}):")
            for line in fmt(bits).split("\n"):
                print(f"      {line}")

    print(f"\nresolved {len(resolved)} glyphs, {len(missing)} unmatched")
    return resolved


if __name__ == "__main__":
    main()
