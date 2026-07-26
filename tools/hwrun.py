#!/usr/bin/env python3
"""Bring up claude-c128 on the real C128 and verify it from this side.

Order matters. The Ultimate's modem layer only starts once a program configures
the ACIA, and the client must be listening before the bridge dials in, so the
client is started first and the bridge second.

The 80-column VDC cannot be read back over the cartridge bus, so verification
uses what can be read: the client's own counters in C128 RAM, and the
40-column companion panel, whose content comes from the bridge — if the panel
shows bridge-provided text, the whole chain is working.
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
HOST = os.environ.get("CBM_ULTIMATE_HOST", "192.168.1.237")

sys.path.insert(0, os.path.join(ROOT, "server"))
import petscii   # noqa: E402

KBUF, NDX = 0x034A, 0x00D0      # C128 keyboard buffer and pending count
VIC_SCREEN = 0x0400


def req(method, path, data=None):
    r = urllib.request.Request(f"http://{HOST}{path}", data=data, method=method)
    with urllib.request.urlopen(r, timeout=20) as resp:
        return resp.read()


def peek(addr, n=1):
    return req("GET", f"/v1/machine:readmem?address={addr:04X}&length={n}")[:n]


def poke(addr, data):
    req("PUT", f"/v1/machine:writemem?address={addr:04X}&data={data.hex().upper()}")


def word(addr):
    b = peek(addr, 2)
    return b[0] | (b[1] << 8)


def type_line(text):
    """Feed a command through the KERNAL keyboard buffer, 10 bytes at a time."""
    payload = bytes(ord(c.upper()) if c.islower() else ord(c) for c in text) + b"\r"
    for i in range(0, len(payload), 10):
        chunk = payload[i:i + 10]
        for _ in range(80):
            if peek(NDX, 1)[0] == 0:
                break
            time.sleep(0.25)
        poke(KBUF, chunk)
        poke(NDX, bytes([len(chunk)]))
        time.sleep(0.3)


INVERSE = {}
for _ch, _code in petscii.GLYPHS.items():
    INVERSE.setdefault(_code, _ch)
for _c in range(0x20, 0x40):
    INVERSE.setdefault(_c, chr(_c))
for _i in range(26):
    INVERSE.setdefault(0x01 + _i, chr(ord("a") + _i))
    INVERSE.setdefault(0x41 + _i, chr(ord("A") + _i))


def show_panel():
    mem = peek(VIC_SCREEN, 1000)
    print("    +" + "-" * 40 + "+")
    for r in range(10):
        row = mem[r * 40:(r + 1) * 40]
        print(f"{r:3d} |" + "".join(INVERSE.get(b, "?") for b in row) + "|")
    print("    +" + "-" * 40 + "+")


def load_labels():
    path = os.path.join(ROOT, "client", "build", "claude.lbl")
    syms = {}
    for line in open(path):
        p = line.split()
        if len(p) >= 3 and p[0] == "al":
            syms[p[2].lstrip(".")] = int(p[1], 16)
    return syms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--command", default="claude")
    ap.add_argument("--cwd", default="/tmp/c128demo")
    ap.add_argument("--settle", type=float, default=30.0)
    ap.add_argument("--keep", action="store_true",
                    help="leave the bridge running so the C128 stays usable")
    ap.add_argument("--skip-run", action="store_true",
                    help="client is already running on the C128")
    args = ap.parse_args()

    syms = load_labels()

    if not args.skip_run:
        print('typing RUN"CLAUDE" on the C128 ...')
        type_line('run"claude"')
        print("waiting for the client to configure the ACIA ...")
        for _ in range(60):
            regs = peek(0xDE00, 4)
            if regs[3] == 0x1F and regs[2] == 0x09:
                print(f"   ACIA configured by the client: "
                      f"ctrl=${regs[3]:02X} cmd=${regs[2]:02X}")
                break
            time.sleep(1)
        else:
            print("   client never configured the ACIA", file=sys.stderr)
            print("   40-column screen:")
            show_panel()
            return 1

    print(f"dialling the C128 from the bridge ...")
    log = open(os.path.join(ROOT, "hwbridge.log"), "w")
    bridge = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "server", "bridge.py"),
         "--connect", f"{HOST}:3000", "--command", args.command,
         "--cwd", args.cwd, "-v"],
        stdout=log, stderr=subprocess.STDOUT, text=True)

    try:
        time.sleep(args.settle)
        print("\n40-column companion panel (content comes from the bridge):")
        show_panel()
        print("\nclient counters, read out of C128 RAM:")
        for name, width in (("_nmiCount", 2), ("_rxCount", 2),
                            ("_rxOverruns", 1), ("_rxDropped", 1),
                            ("_loopCount", 2)):
            a = syms[name]
            v = word(a) if width == 2 else peek(a, 1)[0]
            print(f"  {name:<12} {v}")
    finally:
        if args.keep:
            print(f"\nbridge left running as pid {bridge.pid}; "
                  f"look at the 80-column monitor.")
            print(f"stop it with:  kill {bridge.pid}")
        else:
            bridge.terminate()
            try:
                bridge.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bridge.kill()
        log.close()
        print("\n--- bridge log ---")
        print(open(os.path.join(ROOT, "hwbridge.log")).read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
