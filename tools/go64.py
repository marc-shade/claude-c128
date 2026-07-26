#!/usr/bin/env python3
"""Put a C128 into C64 mode and start the C64 client from disk.

Why this is not just `run_prg`: the Ultimate's run_prg resets the machine, and a
C128 resets into C128 mode. A C64 .prg loads at $0801, which is not where BASIC
7.0 keeps a program, so it accepts the file and nothing useful happens - it
returns no error and leaves you at a BASIC 7.0 prompt. Verified on the real
machine: run_prg with a valid C64 .prg left "COMMODORE BASIC V7.0" on screen.

So the mode switch has to happen first, through the keyboard, exactly as a person
would: GO64, answer the confirmation, then LOAD and RUN from the mounted disk.

The two machines keep their keyboard buffer in different places, which is the
detail that makes this fiddly: the C128 uses $034A with the count at $D0, the C64
$0277 with the count at $C6. After GO64 the second pair is the live one.
"""
import argparse
import sys
import time
import urllib.request

C128_KBUF, C128_NDX = 0x034A, 0x00D0
C64_KBUF, C64_NDX = 0x0277, 0x00C6
SCREEN = 0x0400


def req(host, method, path, data=None, timeout=25):
    r = urllib.request.Request(f"http://{host}{path}", data=data, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.read()


def peek(host, addr, n=1):
    return req(host, "GET",
               f"/v1/machine:readmem?address={addr:04X}&length={n}")[:n]


def poke(host, addr, data):
    req(host, "PUT",
        f"/v1/machine:writemem?address={addr:04X}&data={data.hex().upper()}")


def type_line(host, text, kbuf, ndx, settle=0.4):
    """Feed a line through the KERNAL keyboard buffer, ten bytes at a time.

    Ten is the buffer's capacity on both machines; the count byte is written
    last so the KERNAL never sees a partially filled buffer.
    """
    payload = bytes(ord(c.upper()) if c.islower() else ord(c)
                    for c in text) + b"\r"
    for i in range(0, len(payload), 10):
        chunk = payload[i:i + 10]
        for _ in range(80):
            if peek(host, ndx, 1)[0] == 0:
                break
            time.sleep(0.25)
        poke(host, kbuf, chunk)
        poke(host, ndx, bytes([len(chunk)]))
        time.sleep(settle)


def screen_text(host, n=1000):
    return peek(host, SCREEN, n)


def wait_for(host, predicate, what, timeout=40):
    """Poll the screen until it looks right.

    Read errors are expected while the machine is resetting - the Ultimate stops
    answering for a moment - so they are tolerated, but counted and reported. A
    silent except here would turn "the Ultimate is unreachable" into "the C128
    never reached BASIC", which sends you looking in the wrong place.
    """
    deadline = time.time() + timeout
    errors = 0
    last = None
    while time.time() < deadline:
        try:
            if predicate(screen_text(host)):
                return True
        except OSError as exc:
            errors += 1
            last = exc
        time.sleep(1)
    if errors:
        print(f"  timed out waiting for {what} "
              f"({errors} read errors, last: {last})", file=sys.stderr)
    else:
        print(f"  timed out waiting for {what} "
              f"(the machine answered, the screen never matched)",
              file=sys.stderr)
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="192.168.1.237")
    p.add_argument("--image", default="/Usb0/claude64.d64",
                   help="disk image holding the C64 program")
    p.add_argument("--drive", default="a")
    p.add_argument("--program", default="CLAUDE")
    args = p.parse_args()
    host = args.host

    print(f"[go64] mounting {args.image}")
    req(host, "PUT",
        f"/v1/drives/{args.drive}:mount?image={args.image}&type=d64&mode=readwrite")

    print("[go64] resetting to a known state")
    req(host, "PUT", "/v1/machine:reset")
    # BASIC 7.0's banner contains "BASIC"; screen codes put B at 2, A 1, S 19...
    basic = bytes([0x02, 0x01, 0x13, 0x09, 0x03])
    if not wait_for(host, lambda m: basic in m, "the C128 BASIC prompt"):
        return 1
    time.sleep(1.5)

    print("[go64] GO64")
    type_line(host, "GO64", C128_KBUF, C128_NDX)
    time.sleep(1.0)
    # "ARE YOU SURE?" - answering Y is what actually switches mode.
    type_line(host, "Y", C128_KBUF, C128_NDX)

    # The C64 banner says "COMMODORE 64 BASIC"; "64" is screen codes 0x36 0x34.
    if not wait_for(host, lambda m: bytes([0x36, 0x34]) in m, "C64 mode"):
        return 1
    print("[go64] in C64 mode")
    time.sleep(2.0)

    print(f"[go64] LOAD \"{args.program}\",8,1")
    type_line(host, f'LOAD"{args.program}",8,1', C64_KBUF, C64_NDX)
    # "READY." after a load; R=18 E=5 A=1 D=4 Y=25 in screen codes.
    # "READY." appears once after the C64 banner and again when the load
    # finishes, so two occurrences means the drive is done.
    ready = bytes([0x12, 0x05, 0x01, 0x04, 0x19])
    if not wait_for(host, lambda m: m.count(ready) >= 2, "the load to finish",
                    timeout=90):
        return 1
    time.sleep(1.0)

    print("[go64] RUN")
    type_line(host, "RUN", C64_KBUF, C64_NDX)
    time.sleep(3.0)
    print("[go64] started")
    return 0


if __name__ == "__main__":
    sys.exit(main())
