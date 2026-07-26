#!/usr/bin/env python3
"""End-to-end test rig: real client binary, emulated C128, real bridge.

Boots the compiled client in VICE with the 6551 ACIA wired to a TCP socket the
bridge is listening on, then reads the emulated VDC's 80-column screen back
through VICE's binary monitor. That exercises the actual 6502 code path — NMI
receive, protocol decode, VDC writes — without touching the real machine.

  python3 tools/emutest.py --command "bash --norc -i" --keys "echo hi\\n"
"""
import argparse
import os
import socket
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
PRG = os.path.join(ROOT, "client", "build", "claude.prg")
LBL = os.path.join(ROOT, "client", "build", "claude.lbl")
MESA_EGL = "/usr/share/glvnd/egl_vendor.d/50_mesa.json"

sys.path.insert(0, os.path.join(ROOT, "server"))
import petscii   # noqa: E402


# --- minimal VICE binary-monitor client ------------------------------------
STX, API = 0x02, 0x02
CMD_MEM_GET, CMD_BANKS, CMD_EXIT, CMD_QUIT = 0x01, 0x82, 0xAA, 0xBB


class Mon:
    def __init__(self, port, timeout=20.0):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.s.settimeout(timeout)
        self.rid = 0

    def _exact(self, n):
        buf = b""
        while len(buf) < n:
            c = self.s.recv(n - len(buf))
            if not c:
                raise EOFError("monitor closed")
            buf += c
        return buf

    def _send(self, cmd, body=b""):
        self.rid += 1
        self.s.sendall(struct.pack("<BBIIB", STX, API, len(body), self.rid, cmd) + body)
        return self.rid

    def _recv(self, want):
        while True:
            stx, _a, blen, _t, err, rid = struct.unpack("<BBIBBI", self._exact(12))
            body = self._exact(blen) if blen else b""
            if rid == want:
                return err, body

    def banks(self):
        err, body = self._recv(self._send(CMD_BANKS))
        out, off = {}, 2
        (count,) = struct.unpack("<H", body[:2])
        for _ in range(count):
            ln = body[off]
            bid = struct.unpack("<H", body[off + 1:off + 3])[0]
            nl = body[off + 3]
            out[body[off + 4:off + 4 + nl].decode("ascii", "replace")] = bid
            off += ln + 1
        return out

    def read(self, start, end, bank=0):
        body = struct.pack("<BHHBH", 0, start, end, 0, bank)
        err, resp = self._recv(self._send(CMD_MEM_GET, body))
        if err:
            raise RuntimeError(f"MEM_GET error {err}")
        (n,) = struct.unpack("<H", resp[:2])
        return resp[2:2 + n]

    def reg_names(self):
        """id -> name, from CMD_REGISTERS_AVAILABLE."""
        err, body = self._recv(self._send(0x83, bytes([0])))
        out, off = {}, 2
        (count,) = struct.unpack("<H", body[:2])
        for _ in range(count):
            ln = body[off]
            rid = body[off + 1]
            nl = body[off + 3]
            out[rid] = body[off + 4:off + 4 + nl].decode("ascii", "replace")
            off += ln + 1
        return out

    def registers(self):
        """name -> value, so we can see where the 6502 actually is."""
        names = self.reg_names()
        err, body = self._recv(self._send(0x31, bytes([0])))
        out, off = {}, 2
        (count,) = struct.unpack("<H", body[:2])
        for _ in range(count):
            ln = body[off]
            rid = body[off + 1]
            val = struct.unpack("<H", body[off + 2:off + 4])[0]
            out[names.get(rid, f"r{rid}")] = val
            off += ln + 1
        return out

    def resume(self):
        self._recv(self._send(CMD_EXIT))

    def quit(self):
        try:
            self._send(CMD_QUIT)
        except OSError:
            pass


INVERSE = petscii.inverse_map()


def render(mem, cols=80, rows=25):
    lines = ["    +" + "-" * cols + "+"]
    for r in range(rows):
        row = mem[r * cols:(r + 1) * cols]
        lines.append(f"{r:3d} |" + "".join(INVERSE.get(b, "?") for b in row) + "|")
    lines.append("    +" + "-" * cols + "+")
    return "\n".join(lines)


def load_labels(path=None):
    """Parse the VICE label file cl65 -Ln produces: 'al 00C0DE .name'."""
    if path is None:
        path = os.path.join(ROOT, "client", "build", "claude.lbl")
    if not os.path.exists(path):
        return {}
    syms = {}
    for line in open(path):
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "al":
            syms[parts[2].lstrip(".")] = int(parts[1], 16)
    return syms


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def free_display():
    for n in range(90, 130):
        if not os.path.exists(f"/tmp/.X11-unix/X{n}"):
            return n
    raise RuntimeError("no free X display")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--command", default="bash --norc -i")
    p.add_argument("--cwd")
    p.add_argument("--settle", type=float, default=12.0)
    p.add_argument("--baud", default="38400")
    p.add_argument("--rate", type=int, default=3840)
    p.add_argument("--bootdisk",
                   help="attach this d64 to drive 8 and let the C128 autoboot "
                        "it, instead of autostarting the .prg directly")
    p.add_argument("--keep", action="store_true", help="leave VICE running")
    p.add_argument("--colours", action="store_true",
                   help="also read the colour plane and report which indices "
                        "are actually on screen")
    p.add_argument("--machine", choices=("c128", "c64"), default="c128",
                   help="c128 runs x128 and reads the 80-column VDC; c64 runs "
                        "x64sc and reads the VIC-II screen at $0400")
    args = p.parse_args()

    if args.machine == "c64":
        emu, cols, rows = "x64sc", 40, 25
        prg = os.path.join(ROOT, "client", "build", "claude64.prg")
        lbl = os.path.join(ROOT, "client", "build", "claude64.lbl")
    else:
        emu, cols, rows = "x128", 80, 25
        prg, lbl = PRG, LBL

    if not os.path.exists(prg):
        print(f"client not built: {prg}\nrun: make -C client", file=sys.stderr)
        return 1

    link_port = free_port()
    mon_port = free_port()
    disp = free_display()
    env = dict(os.environ, __EGL_VENDOR_LIBRARY_FILENAMES=MESA_EGL, DISPLAY=f":{disp}")

    xvfb = subprocess.Popen(["Xvfb", f":{disp}", "-screen", "0", "800x600x24"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=dict(os.environ,
                                     __EGL_VENDOR_LIBRARY_FILENAMES=MESA_EGL))
    for _ in range(50):
        if os.path.exists(f"/tmp/.X11-unix/X{disp}"):
            break
        time.sleep(0.1)

    bridge_cmd = [sys.executable, os.path.join(ROOT, "server", "bridge.py"),
                  "--listen", str(link_port), "--command", args.command,
                  "--rate", str(args.rate), "--machine", args.machine, "-v"]
    if args.cwd:
        bridge_cmd += ["--cwd", args.cwd]
    log_path = os.path.join(ROOT, "bridge.log")
    bridge_log = open(log_path, "w")
    bridge = subprocess.Popen(bridge_cmd, stdout=bridge_log,
                              stderr=subprocess.STDOUT, text=True)
    time.sleep(1.2)

    vice = subprocess.Popen([
        emu, "-default",
        # Swiftlink mode at $DE00 on NMI: the same configuration the real
        # Ultimate II+ presents ("Modem Interface: ACIA / SwiftLink").
        "-acia1", "-acia1base", "0xDE00", "-acia1irq", "1", "-acia1mode", "1",
        "-myaciadev", "0",
        "-rsdev1", f"127.0.0.1:{link_port}", "-rsdev1baud", args.baud,
        "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{mon_port}",
        "-sounddev", "dummy", "-jamaction", "0",
    ] + (["-8", os.path.abspath(args.bootdisk)] if args.bootdisk
         else ["-autostart", prg]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

    rc = 0
    try:
        deadline = time.time() + 25
        mon = None
        while time.time() < deadline:
            try:
                mon = Mon(mon_port)
                break
            except OSError:
                time.sleep(0.3)
        if mon is None:
            print("VICE binary monitor never came up", file=sys.stderr)
            return 1

        banks = mon.banks()
        mon.resume()
        time.sleep(args.settle)

        if args.machine == "c64":
            # Ordinary RAM: the VIC-II reads its text matrix from $0400, so no
            # bank switch and no mirror is needed.
            mem = mon.read(0x0400, 0x0400 + cols * rows - 1)
        else:
            mem = mon.read(0x0000, cols * rows - 1, bank=banks["vdc"])
        mon.resume()
        print(render(mem, cols))

        if args.colours:
            # Read the colour plane the same way the machine does: the VDC keeps
            # attributes in its own RAM at $0800, the VIC-II in colour RAM at
            # $D800. Only the low nibble is colour on either.
            if args.machine == "c64":
                attr = mon.read(0xD800, 0xD800 + cols * rows - 1)
            else:
                attr = mon.read(0x0800, 0x0800 + cols * rows - 1, bank=banks["vdc"])
            mon.resume()
            hist = {}
            for cell, a in zip(mem, attr):
                if cell not in (0x20, 0x00):        # ignore blank cells
                    hist[a & 0x0F] = hist.get(a & 0x0F, 0) + 1
            print("\ncolours in use (index: cells with visible text):")
            for idx in sorted(hist, key=lambda k: -hist[k]):
                print(f"  {idx:2d}  {hist[idx]:5d}")

        # Client-side link diagnostics, read straight out of emulated RAM.
        syms = load_labels(lbl)
        if syms:
            def peek(name, width=1):
                addr = syms.get(name)
                if addr is None:
                    return None
                raw = mon.read(addr, addr + width - 1)
                mon.resume()
                return int.from_bytes(raw[:width], "little")

            print("\nclient link state:")
            for name, width in (("_nmiCount", 2), ("_rxCount", 2),
                                ("_rxOverruns", 1), ("_rxDropped", 1),
                                ("_rxHead", 1), ("_rxTail", 1),
                                ("_loopCount", 2)):
                val = peek(name, width)
                print(f"  {name:<12} {val}")

            regs = mon.registers()
            mon.resume()
            pc = regs.get("PC", 0)
            # Find the nearest preceding symbol so the PC means something.
            near = max(((a, n) for n, a in syms.items() if a <= pc),
                       default=(0, "?"))
            print(f"\ncpu: PC=${pc:04X} (nearest symbol {near[1]} +${pc - near[0]:X})"
                  f"  A=${regs.get('A', 0):02X} SP=${regs.get('SP', 0):02X}")
            print(f"     ACIA status=${mon.read(0xDE01, 0xDE01)[0]:02X} "
                  f"cmd=${mon.read(0xDE02, 0xDE02)[0]:02X} "
                  f"ctrl=${mon.read(0xDE03, 0xDE03)[0]:02X}")
            mon.resume()

        blank = sum(1 for b in mem if b in (0x20, 0x00))
        print(f"\nnon-blank cells: {cols * rows - blank} / {cols * rows}")
        if blank == cols * rows:
            print("SCREEN IS EMPTY - client did not paint", file=sys.stderr)
            rc = 1
    finally:
        bridge.terminate()
        try:
            bridge.wait(timeout=3)
        except subprocess.TimeoutExpired:
            bridge.kill()
        bridge_log.close()
        out = open(log_path).read()
        if not args.keep:
            vice.terminate()
        try:
            vice.wait(timeout=5)
        except subprocess.TimeoutExpired:
            vice.kill()
        xvfb.terminate()
        if out:
            print("--- bridge ---\n" + out, file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
