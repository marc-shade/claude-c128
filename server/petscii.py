"""Unicode -> C128 screen code, and truecolor -> VDC color.

Every screen code in GLYPHS was derived from the real C128 character ROM by
matching 8x8 bitmaps (see tools/glyphmatch.py), not from a remembered PETSCII
table. `verify_against_rom()` re-derives the check at test time so the table
cannot silently drift.

The C128 runs the lowercase/uppercase charset (charset 2) so that ordinary text
is readable. That set keeps the box-drawing and block glyphs at $40, $5B-$5D,
$6B-$73, $7B-$7F and $A0+, and gives up only codes $41-$5A, which become A-Z.
"""

import os
import unicodedata

import derive
import font

# The C128 character ROM, shipped with VICE. Distributions put it in different
# places and the file has several revisions, so candidates are searched rather
# than assumed; CBM_CHARGEN overrides.
ROM_CANDIDATES = (
    "/usr/share/vice/C128/chargen-390059-01.bin",
    "/usr/share/vice/C128/chargen-315079-01.bin",
    "/usr/local/share/vice/C128/chargen-390059-01.bin",
    "/opt/homebrew/share/vice/C128/chargen-390059-01.bin",
    "/usr/lib/vice/C128/chargen-390059-01.bin",
)


def find_rom():
    """Path to a C128 character ROM, or None if VICE is not installed."""
    override = os.environ.get("CBM_CHARGEN")
    if override:
        return override if os.path.exists(override) else None
    for path in ROM_CANDIDATES:
        if os.path.exists(path):
            return path
    # Any chargen in a VICE C128 directory will do for the glyphs we check.
    for base in ("/usr/share/vice", "/usr/local/share/vice",
                 "/opt/homebrew/share/vice", "/usr/lib/vice"):
        d = os.path.join(base, "C128")
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if name.startswith("chargen") and name.endswith(".bin"):
                    return os.path.join(d, name)
    return None


ROM_PATH = find_rom()
CHARSET2_OFFSET = 0x0800          # lowercase/uppercase set, C128 mode

# ---------------------------------------------------------------------------
# Glyphs. Codes verified against the character ROM.
# ---------------------------------------------------------------------------
GLYPHS = {
    # Box drawing, sharp corners
    "─": 0x40,   # ─ HORIZONTAL
    "│": 0x5D,   # │ VERTICAL
    "┼": 0x5B,   # ┼ CROSS
    "┌": 0x70,   # ┌ DOWN AND RIGHT
    "┐": 0x6E,   # ┐ DOWN AND LEFT
    "└": 0x6D,   # └ UP AND RIGHT
    "┘": 0x7D,   # ┘ UP AND LEFT
    "├": 0x6B,   # ├ VERTICAL AND RIGHT
    "┤": 0x73,   # ┤ VERTICAL AND LEFT
    "┬": 0x72,   # ┬ DOWN AND HORIZONTAL
    "┴": 0x71,   # ┴ UP AND HORIZONTAL

    # Rounded corners map onto the sharp ones: the ROM's rounded set lives at
    # $49/$4A/$4B/$55, which charset 2 reassigns to I/J/K/U.
    "╭": 0x70,   # ╭
    "╮": 0x6E,   # ╮
    "╰": 0x6D,   # ╰
    "╯": 0x7D,   # ╯

    # Heavy/double box drawing degrades to the light set
    "━": 0x40, "┃": 0x5D, "┏": 0x70, "┓": 0x6E,
    "┗": 0x6D, "┛": 0x7D, "═": 0x40, "║": 0x5D,
    "╔": 0x70, "╗": 0x6E, "╚": 0x6D, "╝": 0x7D,

    # Block elements — these carry the Claude Code logo
    "█": 0xA0,   # █ FULL BLOCK
    "▌": 0x61,   # ▌ LEFT HALF
    "▐": 0xE1,   # ▐ RIGHT HALF
    "▀": 0xE2,   # ▀ UPPER HALF
    "▄": 0x62,   # ▄ LOWER HALF
    "▘": 0x7E,   # ▘ QUADRANT UPPER LEFT
    "▝": 0x7C,   # ▝ QUADRANT UPPER RIGHT
    "▖": 0x7B,   # ▖ QUADRANT LOWER LEFT
    "▗": 0x6C,   # ▗ QUADRANT LOWER RIGHT
    "▛": 0xEC,   # ▛ UL+UR+LL
    "▜": 0xFB,   # ▜ UL+UR+LR
    "▙": 0xFC,   # ▙ UL+LL+LR
    "▟": 0xFE,   # ▟ UR+LL+LR
    "▚": 0x7F,   # ▚ UL+LR
    "▞": 0xFF,   # ▞ UR+LL
    "▎": 0x65,   # ▎ LEFT ONE QUARTER
    "▔": 0x63,   # ▔ UPPER ONE EIGHTH
    "▁": 0x64,   # ▁ LOWER ONE EIGHTH

    # Shades have no exact PETSCII equivalent; the checkerboard reads closest.
    "░": 0x66,   # ░ LIGHT SHADE
    "▒": 0x66,   # ▒ MEDIUM SHADE
    "▓": 0xA0,   # ▓ DARK SHADE -> solid
}

# Glyphs with no geometric equivalent get a deliberate ASCII stand-in. Each is
# one cell wide so column alignment survives.
SUBSTITUTES = {
    "❯": ">",    # ❯ prompt chevron
    "›": ">",    # ›
    "‣": ">",    # ‣
    "⎿": "└",   # ⎿ tool-result elbow -> └
    "⏸": "|",    # ⏸ pause
    "⚠": "!",    # ⚠ warning
    "✳": "*",    # ✳ Claude asterisk
    "✴": "*",    # ✴
    "✻": "*",    # ✻
    "◉": "o",    # ◉ fisheye
    "●": "o",    # ● black circle
    "⏺": "o",    # ⏺ record (tool-use bullet)
    "○": "o",    # ○
    "•": "*",    # • bullet
    "·": ".",    # · middle dot
    "…": ".",    # … ellipsis (one cell, keeps alignment)
    "—": "-",    # — em dash
    "–": "-",    # – en dash
    "‘": "'", "’": "'", "“": '"', "”": '"',
    " ": " ",    # NBSP
    "✓": "y",    # ✓ check
    "✗": "x",    # ✗
    "→": ">",    # →
    "←": "<",    # ←
    # Latin letters that are not a base plus a combining mark, so NFD cannot
    # fold them. One cell each, to keep column alignment.
    "ø": "o", "Ø": "O", "æ": "a", "Æ": "A", "œ": "o", "Œ": "O",
    "ß": "s", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
    "þ": "t", "Þ": "T", "ð": "d", "Ð": "D", "ı": "i", "ŋ": "n",
    "↳": ">",    # ↳
    "": " ", "": "|",   # powerline separators
}

# Braille spinner frames (U+2800 block) -> a rotating ASCII stand-in.
SPINNER = "|/-\\"


# How a character reached the screen. Returned by render_path so callers can
# tell a deliberate stand-in from a failure: mapping the inverted question mark
# to "?" is correct, while falling through to "?" is a coverage gap, and the
# resulting screen code is identical.
# Characters that reached the screen as a question mark, with how many times.
# The block sweep in tools/charaudit.py cannot cover everything a terminal might
# show - CJK, emoji, symbols nobody thought of - so the renderer records its own
# misses and the bridge logs them. Real usage is what closes the last gaps.
UNMAPPED_SEEN = {}


def take_unmapped():
    """New misses since the last call, as {char: count}. Clears the record."""
    seen = dict(UNMAPPED_SEEN)
    UNMAPPED_SEEN.clear()
    return seen


EXACT = "exact"           # a drawn glyph or a real PETSCII shape
STAND_IN = "stand-in"     # a deliberate one-cell approximation
UNMAPPED = "unmapped"     # nothing applied; rendered as a question mark


def _accent_base(ch):
    """The base letter of an accented letter, or None.

    Restricted to letters on purpose. Many mathematical symbols decompose to a
    base plus a combining slash - dropping it turns "not equal" into "equal",
    which is worse than any fallback because it inverts the meaning.
    """
    folded = "".join(c for c in unicodedata.normalize("NFD", ch)
                     if not unicodedata.combining(c))
    if not folded or folded[0] == ch:
        return None
    if not unicodedata.category(folded[0]).startswith("L"):
        return None
    return folded[0]


def render_path(ch: str):
    """(kind, code, via) for one character. The single source of truth for
    both the coverage audit and the bridge's runtime logging."""
    code = font.CODES.get(ch)
    if code is not None:
        return EXACT, code, "glyph"
    if ch in GLYPHS:
        return EXACT, GLYPHS[ch], "petscii"
    if ch in SUBSTITUTES:
        return STAND_IN, to_screen_code(ch), "substitute"

    o = ord(ch)
    if 0x2800 <= o <= 0x28FF:
        return STAND_IN, to_screen_code(ch), "braille"
    if o < 0x20:
        return STAND_IN, 0x20, "control"
    if 0x20 <= o <= 0x7E:
        return EXACT, to_screen_code(ch), "ascii"

    if _accent_base(ch):
        return STAND_IN, to_screen_code(ch), "accent-fold"

    if derive.derive(ch) is not None:
        return STAND_IN, to_screen_code(ch), "derived"

    return UNMAPPED, 0x3F, "none"


def to_screen_code(ch: str) -> int:
    """Map one character to a C128 screen code in the lowercase charset.

    Characters the client has a custom VDC glyph for win over both the PETSCII
    table and the ASCII stand-ins, so they render exactly rather than being
    approximated.
    """
    code = font.CODES.get(ch)
    if code is not None:
        return code
    if ch in GLYPHS:
        return GLYPHS[ch]

    sub = SUBSTITUTES.get(ch)
    if sub is not None:
        ch = sub
        if ch in GLYPHS:
            return GLYPHS[ch]

    o = ord(ch)
    if 0x2800 <= o <= 0x28FF:                       # braille spinner frames
        return ord(SPINNER[o % len(SPINNER)])
    if ch == "@":
        return 0x00
    if "a" <= ch <= "z":
        return o - 0x60                             # a-z -> $01-$1A
    if "A" <= ch <= "Z":
        return o                                    # A-Z -> $41-$5A
    if 0x20 <= o <= 0x3F:
        return o                                    # space..? -> same
    if ch == "[":
        return 0x1B
    if ch == "]":
        return 0x1D
    if ch == "\\":
        return 0x4D
    if ch == "_":
        return 0x64
    if ch == "^":
        return 0x1E
    if ch == "`":
        return 0x27
    if ch in "{}":
        return 0x5B
    if ch == "|":
        return 0x5D
    if ch == "~":
        return 0x40
    if o < 0x20:
        return 0x20                                 # control chars -> space

    # Accented Latin letters fold to their base letter. Claude Code reaches for
    # words like "Sautéed" and "Café", and a '?' in the middle of one reads as
    # corruption rather than as a missing accent. Decomposing and dropping the
    # combining marks handles the whole range without a lookup table.
    base = _accent_base(ch)
    if base:
        return to_screen_code(base)

    # Last resort before giving up: derive a stand-in from the Unicode name.
    # This is what covers whole blocks - box drawing, partial blocks, arrows,
    # geometric shapes, Greek - by their structure rather than by enumeration.
    stand_in = derive.derive(ch)
    if stand_in is not None:
        if stand_in == "":
            return 0x20                             # zero-width -> blank cell
        if stand_in != ch:
            return to_screen_code(stand_in)

    if ch != "?":
        UNMAPPED_SEEN[ch] = UNMAPPED_SEEN.get(ch, 0) + 1
    return 0x3F                                     # genuinely unknown -> '?'


# ---------------------------------------------------------------------------
# Color. The VDC attribute nibble is intensity-red-green-blue.
# ---------------------------------------------------------------------------
VDC_PALETTE = [
    (0x00, 0x00, 0x00),   # 0  black
    (0x55, 0x55, 0x55),   # 1  dark grey
    (0x00, 0x00, 0xAA),   # 2  blue
    (0x55, 0x55, 0xFF),   # 3  light blue
    (0x00, 0xAA, 0x00),   # 4  green
    (0x55, 0xFF, 0x55),   # 5  light green
    (0x00, 0xAA, 0xAA),   # 6  cyan
    (0x55, 0xFF, 0xFF),   # 7  light cyan
    (0xAA, 0x00, 0x00),   # 8  red
    (0xFF, 0x55, 0x55),   # 9  light red
    (0xAA, 0x00, 0xAA),   # 10 purple
    (0xFF, 0x55, 0xFF),   # 11 light purple
    (0xAA, 0x55, 0x00),   # 12 brown / dark yellow
    (0xFF, 0xFF, 0x55),   # 13 yellow
    (0xAA, 0xAA, 0xAA),   # 14 light grey
    (0xFF, 0xFF, 0xFF),   # 15 white
]

BLACK, WHITE, LIGHT_GREY, DARK_GREY = 0, 15, 14, 1

# The colour the Claude Code logo is drawn in. Its real shade is a salmon that
# nearest-match sends to grey, indistinguishable from body text, so it is
# chosen deliberately rather than derived. Any VDC index works:
#   0 black  1 dk grey  2 blue   3 lt blue  4 green   5 lt green  6 cyan
#   7 lt cyan 8 red     9 lt red 10 purple 11 lt purple 12 brown 13 yellow
#   14 lt grey 15 white
LOGO_COLOR = 11           # light purple - reads as pink on RGBI

# Claude Code's palette, pinned by hand so its identity colors land on the
# right VDC entries instead of drifting to whatever nearest-RGB picks.
EXACT = {
    (0xD7, 0x87, 0x87): LOGO_COLOR,   # logo, as actually emitted
    (0xD7, 0x77, 0x57): LOGO_COLOR,   # logo, older shade
    (0xCC, 0x78, 0x5C): LOGO_COLOR,   # logo, banner variant
    (0xFF, 0xC1, 0x07): 13,   # amber warning             -> yellow
    (0x99, 0x99, 0x99): 14,   # dim text                  -> light grey
    (0x88, 0x88, 0x88): 1,    # rules and borders         -> dark grey
    (0xB1, 0xB9, 0xF9): 3,    # lavender prompt           -> light blue
    (0x00, 0x00, 0x00): 0,
    (0xFF, 0xFF, 0xFF): 15,
}

# xterm 256-color cube, needed because Claude Code mixes 38;5;N with truecolor.
_STEPS = (0, 95, 135, 175, 215, 255)
_ANSI16 = [
    (0, 0, 0), (170, 0, 0), (0, 170, 0), (170, 85, 0),
    (0, 0, 170), (170, 0, 170), (0, 170, 170), (170, 170, 170),
    (85, 85, 85), (255, 85, 85), (85, 255, 85), (255, 255, 85),
    (85, 85, 255), (255, 85, 255), (85, 255, 255), (255, 255, 255),
]


def xterm256_to_rgb(n: int):
    if n < 16:
        return _ANSI16[n]
    if n < 232:
        n -= 16
        return (_STEPS[n // 36 % 6], _STEPS[n // 6 % 6], _STEPS[n % 6])
    v = 8 + (n - 232) * 10
    return (v, v, v)


def rgb_to_vdc(r: int, g: int, b: int) -> int:
    """Nearest VDC color, with Claude Code's identity colors pinned."""
    hit = EXACT.get((r, g, b))
    if hit is not None:
        return hit
    best, best_d = WHITE, None
    for idx, (pr, pg, pb) in enumerate(VDC_PALETTE):
        # Weighted for perceived luminance so greys don't collapse to blue.
        d = 2 * (r - pr) ** 2 + 4 * (g - pg) ** 2 + 3 * (b - pb) ** 2
        if best_d is None or d < best_d:
            best, best_d = idx, d
    return best


def parse_color(spec, default: int) -> int:
    """pyte reports a color as 'default', a name, or a 6-digit hex string."""
    if spec in (None, "default"):
        return default
    if isinstance(spec, str) and len(spec) == 6 and all(
        c in "0123456789abcdefABCDEF" for c in spec
    ):
        return rgb_to_vdc(int(spec[0:2], 16), int(spec[2:4], 16),
                          int(spec[4:6], 16))
    return {
        "black": 0, "red": 8, "green": 4, "brown": 12, "blue": 2,
        "magenta": 10, "cyan": 6, "white": 14,
        "brightblack": 1, "brightred": 9, "brightgreen": 5,
        "brightbrown": 13, "brightyellow": 13, "brightblue": 3,
        "brightmagenta": 11, "brightcyan": 7, "brightwhite": 15,
    }.get(spec, default)


BRIGHTEN = {0: 1, 1: 14, 2: 3, 4: 5, 6: 7, 8: 9, 10: 11, 12: 13, 14: 15}
DIM = {v: k for k, v in BRIGHTEN.items()}


def apply_intensity(color: int, bold: bool, dim: bool) -> int:
    if bold and not dim:
        return BRIGHTEN.get(color, color)
    if dim and not bold:
        return DIM.get(color, color)
    return color


def inverse_map():
    """screen code -> a character to display it as, for host-side viewers.

    Custom VDC glyphs take priority: on the C128 they are the real thing, so a
    viewer that showed them as '?' would misreport a screen that is correct.
    """
    inv = {}
    # The glyph a slot was drawn for wins its label. Aliases share slots, so
    # without this an alias could name the slot and a viewer would report the
    # prompt chevron as a single guillemet.
    for ch in font.GLYPH_ART:
        inv[font.CODES[ch]] = ch
    for ch, code in font.CODES.items():
        inv.setdefault(code, ch)
    for ch, code in GLYPHS.items():
        inv.setdefault(code, ch)
    for c in range(0x20, 0x40):
        inv.setdefault(c, chr(c))
    for i in range(26):
        inv.setdefault(0x01 + i, chr(ord("a") + i))
        inv.setdefault(0x41 + i, chr(ord("A") + i))
    inv.setdefault(0x00, "@")
    inv.setdefault(0x1B, "[")
    inv.setdefault(0x1D, "]")
    inv.setdefault(0x4D, "\\")
    inv.setdefault(0x66, "\u2591")
    return inv


# ---------------------------------------------------------------------------
def verify_against_rom(rom_path: str = None):
    """Re-derive every GLYPHS entry from the ROM bitmap. Returns (ok, errors)."""
    rom_path = rom_path or ROM_PATH
    if not rom_path or not os.path.exists(rom_path):
        return False, ["character ROM not found; install VICE or set CBM_CHARGEN"]
    data = open(rom_path, "rb").read()
    chars = [
        tuple(data[CHARSET2_OFFSET + c * 8: CHARSET2_OFFSET + c * 8 + 8])
        for c in range(256)
    ]

    L, R, F, E = 0xF0, 0x0F, 0xFF, 0x00

    def solid(t, b):
        return tuple([t] * 4 + [b] * 4)

    expected = {
        "█": solid(F, F), "▌": tuple([L] * 8), "▐": tuple([R] * 8),
        "▀": solid(F, E), "▄": solid(E, F),
        "▘": solid(L, E), "▝": solid(R, E),
        "▖": solid(E, L), "▗": solid(E, R),
        "▛": solid(F, L), "▜": solid(F, R),
        "▙": solid(L, F), "▟": solid(R, F),
        "▚": solid(L, R), "▞": solid(R, L),
        "▎": tuple([0xC0] * 8),
        "▔": (F, 0, 0, 0, 0, 0, 0, 0),
        "▁": (0, 0, 0, 0, 0, 0, 0, F),
    }

    errors = []
    for ch, bmp in expected.items():
        code = GLYPHS[ch]
        if chars[code] != bmp:
            errors.append(
                f"U+{ord(ch):04X} maps to ${code:02X} but the ROM bitmap differs"
            )

    # Structural checks for the line-drawing set. PETSCII centres lines on the
    # two middle rows/columns, and corners carry only half-arms, so test for
    # arms extending from a filled centre rather than for full bands.
    CENTRE = 0x18                       # columns 3 and 4

    def centre_filled(bits):
        return bits[3] & CENTRE == CENTRE and bits[4] & CENTRE == CENTRE

    def arm_left(bits):
        return bool(bits[3] & 0xE0)     # columns 0-2

    def arm_right(bits):
        return bool(bits[3] & 0x07)     # columns 5-7

    def arm_up(bits):
        return all(bits[y] & CENTRE == CENTRE for y in (0, 1, 2))

    def arm_down(bits):
        return all(bits[y] & CENTRE == CENTRE for y in (5, 6, 7))

    # (glyph, expected arms) — exactly the shape each box character must have.
    SHAPES = {
        "─": (True, True, False, False),
        "│": (False, False, True, True),
        "┼": (True, True, True, True),
        "┌": (False, True, False, True),
        "┐": (True, False, False, True),
        "└": (False, True, True, False),
        "┘": (True, False, True, False),
        "├": (False, True, True, True),
        "┤": (True, False, True, True),
        "┬": (True, True, False, True),
        "┴": (True, True, True, False),
    }
    for ch, want in SHAPES.items():
        bits = chars[GLYPHS[ch]]
        if not centre_filled(bits):
            errors.append(f"U+{ord(ch):04X} (${GLYPHS[ch]:02X}) has no filled centre")
            continue
        got = (arm_left(bits), arm_right(bits), arm_up(bits), arm_down(bits))
        if got != want:
            names = ("left", "right", "up", "down")
            errors.append(
                f"U+{ord(ch):04X} (${GLYPHS[ch]:02X}) arms "
                f"{[n for n, g in zip(names, got) if g]} != "
                f"expected {[n for n, w in zip(names, want) if w]}"
            )

    return (not errors), errors


if __name__ == "__main__":
    ok, errs = verify_against_rom()
    print("ROM verification:", "PASS" if ok else "FAIL")
    for e in errs:
        print("  ", e)
    raise SystemExit(0 if ok else 1)
