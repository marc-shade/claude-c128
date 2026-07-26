#!/usr/bin/env python3
"""Type on the real C128 from here, for testing without leaving the keyboard.

Keys go into the KERNAL keyboard buffer, which is the same buffer GETIN reads,
so the client sees them exactly as it sees real keypresses. Deliberately does
not touch $DE00-$DE03: reading the ACIA over DMA steals bytes from the client
and drops the modem to command mode.

  python3 tools/hwtype.py "what is 2+2" --enter
  python3 tools/hwtype.py --key return
"""
import argparse
import os
import sys
import time
import urllib.request

HOST = os.environ.get("CBM_ULTIMATE_HOST", "192.168.1.237")
KBUF, NDX = 0x034A, 0x00D0
CHUNK = 10                      # the C128 keyboard buffer holds ten bytes

NAMED = {
    "return": 0x0D, "enter": 0x0D,
    "esc": 0x1B, "escape": 0x1B,
    "del": 0x14, "backspace": 0x14,
    "tab": 0x09,
    "up": 0x91, "down": 0x11, "left": 0x9D, "right": 0x1D,
    "help": 0x84,               # forces a repaint / re-arms the modem watcher
    "stop": 0x03,               # RUN/STOP -> Ctrl-C
    "home": 0x13,
}


def req(method, path, data=None):
    r = urllib.request.Request(f"http://{HOST}{path}", data=data, method=method)
    with urllib.request.urlopen(r, timeout=20) as resp:
        return resp.read()


def peek(addr, n=1):
    return req("GET", f"/v1/machine:readmem?address={addr:04X}&length={n}")[:n]


def poke(addr, data):
    req("PUT", f"/v1/machine:writemem?address={addr:04X}&data={data.hex().upper()}")


def to_petscii(ch):
    """ASCII -> the code an unshifted C128 key produces.

    Only ASCII: this is emulating physical keypresses, and the C128 keyboard has
    no key for a box-drawing character. To get such characters onto the screen,
    have Claude Code emit them instead of trying to type them.
    """
    o = ord(ch)
    if o > 0x7E:
        raise SystemExit(
            f"cannot type {ch!r} (U+{o:04X}): the C128 keyboard has no such key. "
            f"Ask Claude Code to output it instead.")
    if 0x61 <= o <= 0x7A:       # a-z  -> $41-$5A, which the bridge folds back
        return o - 0x20
    if 0x41 <= o <= 0x5A:       # A-Z  -> shifted
        return o + 0x80
    if o == 0x0A:
        return 0x0D
    return o


def send(codes, settle=0.25, timeout=20.0):
    deadline = time.time() + timeout
    for i in range(0, len(codes), CHUNK):
        chunk = bytes(codes[i:i + CHUNK])
        while peek(NDX, 1)[0] != 0:
            if time.time() > deadline:
                raise TimeoutError("keyboard buffer never drained")
            time.sleep(settle)
        poke(KBUF, chunk)
        poke(NDX, bytes([len(chunk)]))
        time.sleep(settle)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--enter", action="store_true", help="append RETURN")
    ap.add_argument("--key", action="append", default=[],
                    help=f"a named key: {', '.join(sorted(NAMED))}")
    args = ap.parse_args()

    codes = [to_petscii(c) for c in args.text]
    for name in args.key:
        if name.lower() not in NAMED:
            print(f"unknown key {name!r}; known: {', '.join(sorted(NAMED))}",
                  file=sys.stderr)
            return 1
        codes.append(NAMED[name.lower()])
    if args.enter:
        codes.append(0x0D)
    if not codes:
        print("nothing to send", file=sys.stderr)
        return 1
    send(codes)
    print(f"sent {len(codes)} keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
