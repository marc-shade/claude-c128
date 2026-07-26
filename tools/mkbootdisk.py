#!/usr/bin/env python3
"""Build a D64 that autoboots the claude-c128 client.

The C128 KERNAL reads track 1 sector 0 of device 8 on every reset and, if it
begins with "CBM", treats it as a boot sector: it prints "BOOTING <message>",
optionally loads a named file, then JSRs the machine code that follows. That
makes the terminal come up on power-on with no typing.

Boot sector layout (C128 Programmer's Reference Guide):

    +0  'C' 'B' 'M'
    +3  load address lo/hi for any additional sectors
    +5  bank
    +6  number of additional sectors to load
    +7  null-terminated message, printed after "BOOTING "
        null-terminated filename, loaded if non-empty
        machine code, JSRed in place

The sector is read to $0B00, so absolute references in the code are resolved
against that. Rather than have the boot loader load the client itself — which
would then need BASIC's RUN entry poked by hand to start a cc65 program with a
BASIC stub — the code stuffs RUN"<name>" into the keyboard buffer and returns.
BASIC comes up, consumes the buffer, and runs it: the same mechanism the
network deploy path uses, which is already proven on this hardware.

The buffer holds ten characters, so the program on the boot disk is named "c":
RUN"C" plus a carriage return is seven bytes and fits with room to spare.
"""
import argparse
import os
import subprocess
import sys
import tempfile

BOOT_ORIGIN = 0x0B00        # where the KERNAL reads the boot sector to
KBUF = 0x034A               # C128 keyboard buffer
NDX = 0x00D0                # number of characters waiting in it
D64_SECTOR = 256

# Track 1 sector 0 sits at the very start of a .d64 image.
BOOT_OFFSET = 0


def petscii(s):
    """Uppercase ASCII is what an unshifted C128 shows as capitals."""
    return s.upper().encode("ascii")


def build_boot_sector(message, program):
    cmd = petscii(f'run"{program}"') + b"\x0d"
    if len(cmd) > 10:
        raise SystemExit(
            f'RUN"{program.upper()}" is {len(cmd)} bytes; the C128 keyboard '
            f"buffer holds 10. Use a shorter program name."
        )

    header = bytearray(b"CBM")
    header += bytes((0x00, 0x0B))     # load address for extra sectors (unused)
    header += bytes((0x00,))          # bank
    header += bytes((0x00,))          # no additional sectors
    header += petscii(message) + b"\x00"
    header += b"\x00"                 # empty filename: nothing for it to load

    # Assemble with computed offsets. The branch displacement in particular is
    # derived, not written by hand: getting it wrong by one byte lands in the
    # middle of an instruction, which is silent and fatal.
    code_base = len(header)                  # offset of the code within the sector

    prologue = bytes((0xA2, len(cmd) - 1))   # ldx #len-1
    loop_off = code_base + len(prologue)     # 'lda cmd,x' starts here

    # cmd_addr depends on the total code length, which depends on nothing that
    # follows, so the body can be laid out with a placeholder and patched.
    body_len = 3 + 3 + 1 + 2                 # lda,abs,x | sta,abs,x | dex | bpl
    tail_len = 2 + 2 + 1                     # lda #len | sta $D0 | rts
    # The rts is part of the code, so the data starts after it. Putting the
    # data before the rts would let execution fall through the string and run
    # it as instructions - which hangs the machine on every boot.
    cmd_addr = BOOT_ORIGIN + code_base + len(prologue) + body_len + tail_len

    # bpl is relative to the address after its operand.
    after_branch = loop_off + body_len
    disp = loop_off - after_branch
    if not -128 <= disp <= 127:
        raise SystemExit(f"branch out of range: {disp}")

    code = prologue + bytes((
        0xBD, cmd_addr & 0xFF, cmd_addr >> 8,     # lda cmd,x
        0x9D, KBUF & 0xFF, KBUF >> 8,             # sta $034A,x
        0xCA,                                     # dex
        0x10, disp & 0xFF,                        # bpl loop
        0xA9, len(cmd),                           # lda #len
        0x85, NDX,                                # sta $D0
        0x60,                                     # rts - before the data
    ))

    sector = bytearray(header + code + cmd)
    if len(sector) > D64_SECTOR:
        raise SystemExit(f"boot sector is {len(sector)} bytes, max {D64_SECTOR}")
    sector += b"\x00" * (D64_SECTOR - len(sector))
    return bytes(sector)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prg", help="the client .prg to put on the disk")
    ap.add_argument("-o", "--output", default="claude-boot.d64")
    ap.add_argument("--name", default="c",
                    help='program name on disk (default "c", keeps RUN short)')
    ap.add_argument("--message", default="claude code terminal",
                    help='shown as "BOOTING <message>"')
    ap.add_argument("--disk-name", default="claude boot")
    args = ap.parse_args()

    if not os.path.exists(args.prg):
        raise SystemExit(f"no such file: {args.prg}")

    out = os.path.abspath(args.output)
    if os.path.exists(out):
        os.remove(out)

    # c1541 builds the filesystem; the boot sector is written in afterwards
    # because it lives outside the directory structure.
    r = subprocess.run(
        ["c1541", "-format", f"{args.disk_name[:16]},cb", "d64", out,
         "-write", args.prg, args.name],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        raise SystemExit(f"c1541 failed: {r.stderr.strip() or r.stdout.strip()}")

    sector = build_boot_sector(args.message, args.name)
    with open(out, "r+b") as fh:
        fh.seek(BOOT_OFFSET)
        fh.write(sector)

    print(f"built {out}")
    print(f'  boots with: BOOTING {args.message.upper()}')
    print(f'  then types: RUN"{args.name.upper()}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
