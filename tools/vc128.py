#!/usr/bin/env python3
"""Virtual C128: a software stand-in for the real terminal.

Connects to the bridge, decodes the wire protocol, and renders exactly what the
C128 would show — same 80x25 grid, same PETSCII glyphs, same 16 colours. Lets
the whole server be exercised and debugged before any 6502 is involved, and
stays useful afterwards as the reference the hardware client must match.

  python3 tools/vc128.py --connect 127.0.0.1:6400            # snapshot mode
  python3 tools/vc128.py --connect 127.0.0.1:6400 --interactive
"""
import argparse
import os
import select
import socket
import sys
import termios
import tty

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

import protocol                              # noqa: E402
from preview import PreviewSink              # noqa: E402

# ASCII -> PETSCII, the inverse of server/keymap.py, so an interactive session
# sends what the real keyboard would send.
def ascii_to_petscii(byte: int) -> int:
    if 0x61 <= byte <= 0x7A:          # a-z  -> unshifted letter keys
        return byte - 0x20
    if 0x41 <= byte <= 0x5A:          # A-Z  -> shifted letter keys
        return byte + 0x80
    if byte == 0x0A or byte == 0x0D:
        return 0x0D
    if byte == 0x7F or byte == 0x08:
        return 0x14                   # DEL
    if byte == 0x09:
        return 0x09                   # TAB
    if byte == 0x1B:
        return 0x1B                   # ESC
    if byte == 0x03:
        return 0x03                   # STOP
    return byte


class VirtualC128:
    def __init__(self, sock, cols=80, rows=25):
        self.sock = sock
        self.sink = PreviewSink(cols, rows)
        self.buf = b""
        self.panel = {}
        self.glyphs = {}
        self.consumed = 0

    def pump(self, timeout=0.2):
        """Read and apply whatever has arrived. Returns True if a frame landed."""
        r, _, _ = select.select([self.sock], [], [], timeout)
        if self.sock not in r:
            return False
        data = self.sock.recv(65536)
        if not data:
            raise ConnectionError("bridge closed the link")
        self.buf += data
        before = self.sink.frames
        consumed = self._consume()
        self.buf = self.buf[consumed:]

        # Return credit exactly as the real client does. Without this the
        # bridge stops after CREDIT_WINDOW bytes - which the glyph upload
        # alone nearly fills - and the screen never arrives.
        self.consumed += len(data)
        while self.consumed >= protocol.CREDIT_UNIT:
            self.consumed -= protocol.CREDIT_UNIT
            self.sock.sendall(bytes((protocol.CLIENT_ESCAPE,
                                     protocol.CLIENT_CREDIT)))
        return self.sink.frames > before

    def _consume(self):
        """Apply only whole commands; a partial tail waits for more bytes."""
        i, n = 0, len(self.buf)
        data = self.buf
        while i < n:
            start = i
            cmd = data[i]
            i += 1
            try:
                if cmd == protocol.CMD_CLEAR:
                    self.sink.clear(data[i]); i += 1
                elif cmd == protocol.CMD_RUN:
                    row, col, attr, ln = data[i:i + 4]
                    i += 4
                    if i + ln > n:
                        return start
                    self.sink.run(row, col, attr, data[i:i + ln]); i += ln
                elif cmd == protocol.CMD_FILL:
                    row, col, attr, ln, ch = data[i:i + 5]
                    i += 5
                    self.sink.run(row, col, attr, bytes([ch]) * ln)
                elif cmd == protocol.CMD_CURSOR:
                    row, col = data[i], data[i + 1]
                    i += 2
                    self.sink.cursor(None if (row, col) == protocol.CURSOR_HIDDEN
                                     else (row, col))
                elif cmd == protocol.CMD_FRAME:
                    self.sink.frame()
                elif cmd == protocol.CMD_BELL:
                    self.sink.bell()
                elif cmd == protocol.CMD_PANEL:
                    row, color, ln = data[i], data[i + 1], data[i + 2]
                    i += 3
                    if i + ln > n:
                        return start
                    self.panel[row] = bytes(data[i:i + ln]); i += ln
                elif cmd == protocol.CMD_GLYPH:
                    if i + 9 > n:
                        return start
                    # Record the definition so the viewer renders the same
                    # glyph the C128 will, rather than a stand-in.
                    self.glyphs[data[i]] = bytes(data[i + 1:i + 9])
                    i += 9
                elif cmd == protocol.CMD_HELLO:
                    i += 2
                elif cmd == protocol.CMD_BYE:
                    if i >= n:
                        return start
                    magic = data[i]
                    i += 1
                    if magic == protocol.BYE_MAGIC:
                        raise ConnectionError("bridge said goodbye")
                else:
                    raise ValueError(f"bad opcode {cmd:#04x}")
            except IndexError:
                return start          # truncated command, wait for more
        return i

    def render(self):
        return self.sink.render(color=True)

    def render_panel(self):
        if not self.panel:
            return ""
        from preview import code_to_char
        rows = []
        for row in sorted(self.panel):
            rows.append("    |" + "".join(code_to_char(c)
                                          for c in self.panel[row]).ljust(40) + "|")
        return "  40-column companion screen:\n" + "\n".join(rows)

    def send_keys(self, data: bytes):
        self.sock.sendall(bytes(ascii_to_petscii(b) for b in data))

    def request_resync(self):
        """Same announcement the real client makes once its NMI handler is up."""
        self.sock.sendall(bytes((protocol.CLIENT_ESCAPE, protocol.CLIENT_RESYNC)))


def connect(spec):
    host, _, port = spec.rpartition(":")
    sock = socket.create_connection((host, int(port)), timeout=15)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return sock


def run_snapshot(vc, settle, quiet):
    import time
    deadline = time.time() + settle
    while time.time() < deadline:
        try:
            vc.pump(0.2)
        except ConnectionError:
            break
    if not quiet:
        print(vc.render())
        panel = vc.render_panel()
        if panel:
            print(panel)
    return vc


def run_interactive(vc):
    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        sys.stdout.write("\x1b[2J")
        while True:
            r, _, _ = select.select([sys.stdin, vc.sock], [], [], 0.1)
            if vc.sock in r:
                if vc.pump(0):
                    sys.stdout.write("\x1b[H" + vc.render() + "\r\n")
                    sys.stdout.flush()
            if sys.stdin in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if data == b"\x1d":          # Ctrl-] quits the viewer
                    break
                vc.send_keys(data)
    except ConnectionError as exc:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        print("\r\n[vc128] disconnected")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--connect", required=True, metavar="HOST:PORT")
    p.add_argument("--interactive", action="store_true",
                   help="drive it like a terminal (Ctrl-] to quit)")
    p.add_argument("--settle", type=float, default=3.0,
                   help="snapshot mode: seconds to collect before rendering")
    p.add_argument("--keys", help="snapshot mode: send these keys first")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    vc = VirtualC128(connect(args.connect))
    vc.request_resync()
    if args.interactive:
        run_interactive(vc)
        return 0

    if args.keys:
        import time
        deadline = time.time() + 2.0
        while time.time() < deadline:
            vc.pump(0.2)
        vc.send_keys(args.keys.encode())
    run_snapshot(vc, args.settle, args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
