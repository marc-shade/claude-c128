#!/usr/bin/env python3
"""claude-c128 bridge: run Claude Code on Linux, display it on a real C128.

Spawns Claude Code in an 80x25 PTY, emulates the terminal, converts each frame
to PETSCII screen codes, and ships only the changed cells over a serial link to
the C128. Keystrokes come back the other way.

Transports:
  --connect HOST:PORT   dial the Ultimate II+ modem listener (real hardware)
  --listen PORT         wait for a client (VICE's -rsdev1 points here)
  --stdio               run the client model locally, for development

Example, against the real machine:
  python3 server/bridge.py --connect 192.168.1.237:3000
"""
import argparse
import errno
import fcntl
import os
import pty
import select
import shlex
import signal
import socket
import struct
import sys
import termios
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import keymap                       # noqa: E402
import petscii                      # noqa: E402
import protocol                     # noqa: E402
from vtscreen import VTScreen       # noqa: E402

COLS, ROWS = 80, 25

# Frames are coalesced for this long before being sent. Claude Code repaints
# far faster than a serial line can carry, and the eye cannot see 30ms anyway.
FRAME_INTERVAL = 0.05

# If this much output is still queued, the link is behind. Drop the backlog and
# force a full repaint rather than displaying an ever-staler screen.
BACKLOG_LIMIT = 32768


class PtyProcess:
    def __init__(self, argv, cols=COLS, rows=ROWS, cwd=None):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLUMNS"] = str(cols)
            os.environ["LINES"] = str(rows)
            # Claude Code suppresses its own TUI when it thinks it is nested.
            os.environ.pop("CLAUDECODE", None)
            os.environ.pop("CLAUDE_CODE_SSE_PORT", None)
            if cwd:
                os.chdir(cwd)
            os.execvp(argv[0], argv)
        self.resize(cols, rows)
        flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        fcntl.fcntl(self.fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def resize(self, cols, rows):
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ,
                    struct.pack("HHHH", rows, cols, 0, 0))

    def read(self, size=65536):
        try:
            return os.read(self.fd, size)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return b""
            return None                     # EIO: the child exited
        return b""

    def write(self, data):
        if data:
            os.write(self.fd, data)

    def alive(self):
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def close(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(self.pid, sig)
                time.sleep(0.2)
                if not self.alive():
                    break
            except ProcessLookupError:
                break
        try:
            os.close(self.fd)
        except OSError:
            pass


class SerialLink:
    """A byte pipe to the C128, with a bounded outgoing queue and pacing.

    Neither VICE's RS232 emulation nor the Ultimate's TCP-backed modem
    rate-limits to the ACIA's nominal baud: both will hand over data as fast as
    the socket delivers it. The C128 receives into a 256-byte ring from NMI, and
    a burst larger than that is simply lost — which shows up as a screen missing
    whole rows, not as an error. So the sender meters itself to the real link
    speed instead of trusting the transport to do it.
    """

    def __init__(self, sock, byte_rate=3840):
        self.sock = sock
        self.sock.setblocking(False)
        self.out = bytearray()
        self.overflowed = False
        self.byte_rate = byte_rate          # 38400 baud 8N1 = 3840 bytes/sec
        self.allowance = float(byte_rate)
        self.last_tick = time.time()
        # Bytes the client has room for. Credits arrive as it consumes.
        self.credits = protocol.CREDIT_WINDOW

    def fileno(self):
        return self.sock.fileno()

    def queue(self, data):
        if len(self.out) + len(data) > BACKLOG_LIMIT:
            self.out.clear()
            self.overflowed = True
            return False
        self.out += data
        return True

    def wants_write(self):
        return bool(self.out)

    def flush(self):
        if not self.out:
            return
        now = time.time()
        self.allowance = min(
            float(self.byte_rate),                      # at most one second of credit
            self.allowance + (now - self.last_tick) * self.byte_rate,
        )
        self.last_tick = now
        budget = min(int(self.allowance), self.credits)
        if budget < 1:
            return
        try:
            sent = self.sock.send(self.out[:budget])
            del self.out[:sent]
            self.allowance -= sent
            self.credits -= sent
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            raise ConnectionError("serial link closed while writing")

    def recv(self):
        try:
            data = self.sock.recv(4096)
        except (BlockingIOError, InterruptedError):
            return b""
        except OSError:
            raise ConnectionError("serial link closed while reading")
        if not data:
            raise ConnectionError("serial link closed by peer")
        return data

    def add_credit(self, units=1):
        self.credits = min(protocol.CREDIT_WINDOW,
                           self.credits + units * protocol.CREDIT_UNIT)

    def reset_credit(self):
        self.credits = protocol.CREDIT_WINDOW

    def take_overflow(self):
        was, self.overflowed = self.overflowed, False
        return was

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def panel_lines(title, status):
    """Content for the 40-column VIC-II companion screen."""
    out = []
    out.append(("claude code / c128", 0))
    out.append(("-" * 40, 1))
    for i, chunk in enumerate([title[i:i + 40] for i in range(0, len(title), 40)][:2]):
        out.append((chunk, 3 + i))
    out.append((status[:40], 6))
    return out


class Bridge:
    def __init__(self, link, argv, cwd=None, panel=True, verbose=False):
        self.link = link
        self.vt = VTScreen(COLS, ROWS)
        self.differ = protocol.ScreenDiffer(COLS, ROWS)
        self.proc = PtyProcess(argv, COLS, ROWS, cwd)
        self.panel_enabled = panel
        self.verbose = verbose
        self.last_frame = 0.0
        self.dirty = False
        self.last_panel = None
        self.bytes_out = 0
        self.frames_sent = 0
        self.pending_escape = False

        # Nothing is sent until the client announces itself. The transport
        # buffers whatever is written before the C128 has opened its ACIA, then
        # delivers it in one burst that overruns the receive ring - which loses
        # whole rows silently. Waiting for the client's resync request makes the
        # first byte on the wire also the first byte it can receive.
        self.client_ready = False

    def _take_control(self, data):
        """Split client control bytes out of the key stream.

        $00 introduces a control byte; everything else is a keystroke. The
        escape may straddle a read, so a trailing $00 is carried over.
        """
        out = bytearray()
        i = 0
        if self.pending_escape and data:
            self._control(data[0])
            i = 1
            self.pending_escape = False
        while i < len(data):
            b = data[i]
            if b == protocol.CLIENT_ESCAPE:
                if i + 1 >= len(data):
                    self.pending_escape = True
                    break
                self._control(data[i + 1])
                i += 2
                continue
            out.append(b)
            i += 1
        return bytes(out)

    def _control(self, code):
        if code == protocol.CLIENT_RESYNC:
            if not self.client_ready:
                self.client_ready = True
                enc = protocol.Encoder()
                enc.hello(COLS, ROWS)
                self.link.queue(enc.take())
                if self.verbose:
                    print("[bridge] client is listening", file=sys.stderr)
            self.link.reset_credit()
            self.differ.reset()
            self.dirty = True
            self.last_panel = None
            if self.verbose:
                print("[bridge] client asked for a resync", file=sys.stderr)
        elif code == protocol.CLIENT_CREDIT:
            self.link.add_credit()
        elif code == protocol.CLIENT_BYE:
            raise ConnectionError("client disconnected")

    def _send_frame(self):
        if self.link.take_overflow():
            # We fell behind; resynchronise from a clean slate.
            self.differ.reset()
            if self.verbose:
                print("[bridge] link backlog exceeded, forcing full repaint",
                      file=sys.stderr)

        frame = self.differ.diff(self.vt.grid(), self.vt.cursor())

        if self.vt.take_bell():
            enc = protocol.Encoder()
            enc.bell()
            frame += enc.take()

        if self.panel_enabled:
            frame += self._panel_frame()

        # A bare FRAME byte means nothing changed; do not spend the link on it.
        if len(frame) > 1:
            self.link.queue(frame)
            self.bytes_out += len(frame)
            self.frames_sent += 1
        self.dirty = False
        self.last_frame = time.time()

    def _panel_frame(self):
        title = self.vt.title() or "claude code"
        status = f"{self.frames_sent} frames  {self.bytes_out // 1024}k sent"
        lines = panel_lines(title, status)
        if lines == self.last_panel:
            return b""
        self.last_panel = lines
        enc = protocol.Encoder()
        for text, row in lines:
            codes = [petscii.to_screen_code(c) for c in text.ljust(40)[:40]]
            enc.panel(row, codes)
        return enc.take()

    def run(self):
        try:
            while True:
                if not self.proc.alive():
                    if self.verbose:
                        print("[bridge] claude exited", file=sys.stderr)
                    break

                rlist = [self.proc.fd, self.link]
                wlist = [self.link] if self.link.wants_write() else []
                if self.link.wants_write():
                    timeout = 0.02          # keep the paced writer moving
                elif self.dirty:
                    timeout = FRAME_INTERVAL
                else:
                    timeout = 0.25
                r, w, _ = select.select(rlist, wlist, [], timeout)

                if self.proc.fd in r:
                    data = self.proc.read()
                    if data is None:
                        break
                    if data:
                        self.vt.feed(data)
                        self.dirty = True

                if self.link in r:
                    keys = self.link.recv()
                    if keys:
                        typed = self._take_control(keys)
                        # Before the client announces itself, anything arriving
                        # is the Ultimate's modem chatter ("Welcome to the Modem
                        # Emulation Layer...", "CONNECT 38400"), not keystrokes.
                        if self.client_ready and typed:
                            out = keymap.translate(typed)
                            if self.verbose:
                                print(f"[bridge] keys from C128: {typed!r} "
                                      f"-> pty {out!r}", file=sys.stderr, flush=True)
                            self.proc.write(out)
                        elif typed and self.verbose:
                            print(f"[bridge] dropped pre-handshake bytes: {typed!r}",
                                  file=sys.stderr, flush=True)

                if (self.client_ready and self.dirty
                        and time.time() - self.last_frame >= FRAME_INTERVAL):
                    self._send_frame()

                if self.link in w or self.link.wants_write():
                    self.link.flush()
        except ConnectionError as exc:
            print(f"[bridge] {exc}", file=sys.stderr)
        except KeyboardInterrupt:
            pass
        finally:
            enc = protocol.Encoder()
            enc.buf += bytes((protocol.CMD_BYE,))
            try:
                self.link.queue(enc.take())
                self.link.flush()
            except (ConnectionError, OSError):
                pass
            self.proc.close()
            self.link.close()
            print(f"[bridge] {self.frames_sent} frames, {self.bytes_out} bytes sent",
                  file=sys.stderr)


def open_transport(args):
    if args.connect:
        host, _, port = args.connect.rpartition(":")
        sock = socket.create_connection((host, int(port)), timeout=15)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"[bridge] connected to {args.connect}", file=sys.stderr)
        return sock
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", args.listen))
    listener.listen(1)
    print(f"[bridge] listening on 127.0.0.1:{args.listen}", file=sys.stderr)
    sock, peer = listener.accept()
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    listener.close()
    print(f"[bridge] client connected from {peer}", file=sys.stderr)
    return sock


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--connect", metavar="HOST:PORT",
                   help="dial the Ultimate II+ modem listener")
    g.add_argument("--listen", type=int, metavar="PORT",
                   help="wait for a client on 127.0.0.1:PORT (VICE)")
    p.add_argument("--command", default="claude",
                   help="what to run in the PTY (default: claude)")
    p.add_argument("--cwd", help="working directory for the child")
    p.add_argument("--no-panel", action="store_true",
                   help="do not drive the 40-column companion screen")
    p.add_argument("--rate", type=int, default=3840,
                   help="link speed in bytes/sec (38400 baud 8N1 = 3840)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    sock = open_transport(args)
    bridge = Bridge(SerialLink(sock, byte_rate=args.rate), shlex.split(args.command),
                    cwd=args.cwd, panel=not args.no_panel, verbose=args.verbose)
    bridge.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
