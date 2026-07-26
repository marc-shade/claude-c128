#!/usr/bin/env python3
"""Read the real C128's 80-column VDC screen over the network.

The VDC keeps its screen in private RAM that the Ultimate's DMA cannot reach,
so the host cannot see the 80-column display directly. This asks the running
client to copy a VDC plane into ordinary C128 memory, then reads it back — the
C128 does the part only it can do.

  python3 tools/vdcpeek.py            # text
  python3 tools/vdcpeek.py --color    # text with the VDC colours
"""
import argparse
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
HOST = os.environ.get("CBM_ULTIMATE_HOST", "192.168.1.237")

sys.path.insert(0, os.path.join(ROOT, "server"))
import petscii   # noqa: E402

COLS, ROWS = 80, 25


def syms():
    out = {}
    for line in open(os.path.join(ROOT, "client", "build", "claude.lbl")):
        p = line.split()
        if len(p) >= 3 and p[0] == "al":
            out[p[2].lstrip(".")] = int(p[1], 16)
    return out


def req(method, path, data=None):
    r = urllib.request.Request(f"http://{HOST}{path}", data=data, method=method)
    with urllib.request.urlopen(r, timeout=20) as resp:
        return resp.read()


def peek(addr, n):
    return req("GET", f"/v1/machine:readmem?address={addr:04X}&length={n}")[:n]


def poke(addr, data):
    req("PUT", f"/v1/machine:writemem?address={addr:04X}&data={data.hex().upper()}")


def grab(plane, s):
    """plane 1 = characters, 2 = attributes."""
    poke(s["_mirrorReq"], bytes([plane]))
    for _ in range(60):
        if peek(s["_mirrorReq"], 1)[0] == 0:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("client never serviced the mirror request "
                           "(is it running?)")
    buf = bytearray()
    base = s["_mirrorBuf"]
    while len(buf) < COLS * ROWS:
        n = min(256, COLS * ROWS - len(buf))
        buf += peek(base + len(buf), n)
    return bytes(buf)


INVERSE = {}
for _ch, _code in petscii.GLYPHS.items():
    INVERSE.setdefault(_code, _ch)
for _c in range(0x20, 0x40):
    INVERSE.setdefault(_c, chr(_c))
for _i in range(26):
    INVERSE.setdefault(0x01 + _i, chr(ord("a") + _i))
    INVERSE.setdefault(0x41 + _i, chr(ord("A") + _i))
INVERSE.setdefault(0x00, "@")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--color", action="store_true",
                    help="also fetch attributes and colour the output")
    args = ap.parse_args()

    s = syms()
    chars = grab(1, s)
    attrs = grab(2, s) if args.color else None

    print("    +" + "-" * COLS + "+")
    for r in range(ROWS):
        row = chars[r * COLS:(r + 1) * COLS]
        if attrs is None:
            body = "".join(INVERSE.get(b, "?") for b in row)
        else:
            arow = attrs[r * COLS:(r + 1) * COLS]
            out, last = [], None
            for code, attr in zip(row, arow):
                if attr != last:
                    rgb = petscii.VDC_PALETTE[attr & 0x0F]
                    out.append(f"\x1b[0m\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m")
                    if attr & 0x40:
                        out.append("\x1b[7m")
                    last = attr
                out.append(INVERSE.get(code, "?"))
            body = "".join(out) + "\x1b[0m"
        print(f"{r:3d} |{body}|")
    print("    +" + "-" * COLS + "+")

    used = sum(1 for b in chars if b not in (0x20, 0x00))
    print(f"\n{used} non-blank cells of {COLS * ROWS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
