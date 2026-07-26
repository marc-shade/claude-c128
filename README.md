# claude-c128

Claude Code, displayed on a real Commodore 128.

Claude Code runs on the Linux box. The C128 is the terminal: its keyboard is the
input, its 80-column screen is the display. Nothing is reimplemented — the
actual `claude` binary runs in a PTY, and what you see on the VDC is its real
TUI, translated cell by cell into PETSCII.

```
   C128 keyboard + 80-col monitor
            |
            |  6551 ACIA (SwiftLink) at $DE00, NMI-driven
            v
   Ultimate II+  ── modem emulation ──  TCP :3000
            |
            |  LAN
            v
   fedora.local : server/bridge.py
       claude in a PTY  ->  pyte  ->  PETSCII  ->  delta frames
```

## Why it is built this way

**The bridge does all the layout.** The C128 never reflows text or interprets
ANSI; it applies pre-computed cell runs. An 8-bit machine at 2MHz cannot parse
truecolor SGR and Unicode box drawing at speed, and it does not have to.

**Frames are diffed, not repainted.** Claude Code redraws its entire screen
constantly. A full 80x25 repaint is about 2KB, roughly half a second of wire
time. The differ sends only changed cell runs, so streaming output costs well
under 100 bytes a frame.

**The client asks for the picture.** The serial link is open before the C128 has
finished loading, so the first repaint is always lost. The client announces
itself once its interrupt handler is live and asks for a full repaint. The same
path is the recovery route from any corruption — press **HELP**.

## Running it

Against the real machine (the bridge dials the Ultimate's modem listener):

```sh
./run.sh [working-directory]            # build, load the client, dial in
```

As a `systemd --user` service, so it survives reboots and reconnects on its own
if the link drops (`claude-c128.service`, install with `systemctl --user
enable --now`). The bridge exits 0 when Claude Code quits on its own — nothing
is left to serve, so the service stays down — and exits 1 on a link failure, so
`Restart=on-failure` respawns it and the C128 dials back in. Verified: a clean
`true` command exits 0, an abrupt socket close while the session is still
running exits 1.

or by hand:

```sh
make -C client disk                     # build client/build/claude.d64
cbm --target c128 deploy client/build/claude.prg --name claude
python3 server/bridge.py --connect 192.168.1.237:3000
```

On the C128, **HELP** forces a full repaint and re-arms the modem watcher, which
is how you reconnect after restarting the bridge.

The Ultimate's **ACIA (6551) Mode** must be set to `DE00/NMI` (Modem Settings).
The modem layer only starts once a program configures the ACIA, which the client
does at startup.

Against the emulator, which needs no hardware at all:

```sh
python3 tools/emutest.py --command claude --cwd /tmp/demo
```

Without any 6502 in the loop, using the virtual client:

```sh
python3 server/bridge.py --listen 6400 --command claude &
python3 tools/vc128.py --connect 127.0.0.1:6400 --interactive
```

## Layout

| Path | What it is |
|---|---|
| `server/bridge.py` | the daemon: PTY, framing, transport |
| `server/vtscreen.py` | ANSI to an 80x25 grid, via pyte |
| `server/petscii.py` | Unicode to screen codes, truecolor to 16 VDC colours |
| `server/protocol.py` | wire format and the frame differ |
| `server/keymap.py` | C128 keys to terminal input |
| `server/test_bridge.py` | the test suite |
| `client/main.c` | protocol decoder, keyboard, modem answering |
| `client/c128hw.s` | VDC writes and the NMI-driven ACIA receive |
| `tools/vc128.py` | virtual C128, for development |
| `tools/emutest.py` | full stack in VICE, with client diagnostics |
| `tools/preview.py` | render a captured ANSI stream as the C128 would |
| `tools/glyphmatch.py` | derives the glyph table from the character ROM |
| `server/font.py` | custom VDC glyphs, drawn as editable 8x8 art |
| `tools/vdcpeek.py` | read the real 80-column screen back over the network |
| `tools/hwrun.py` | bring-up and verification against the real machine |
| `tools/mkbootdisk.py` | build the autobooting D64 |
| `tools/hwtype.py` | type on the real C128 from the host, for testing |
| `server/bootstrap.py` | mount the boot disk and reset, idempotently |
| `server/derive.py` | name-driven character mapping, covers whole blocks |
| `tools/charaudit.py` | Unicode coverage audit |
| `tools/eval.py` | every check, one verdict |
| `tools/hwtype.py` | type on the real C128 from the host |

## Things that were not obvious

**The glyph table is derived, not remembered.** `tools/glyphmatch.py` renders
every screen code from the C128 character ROM and matches it against synthesized
bitmaps for the Unicode glyphs Claude Code emits. All 18 block elements match
exactly, and `petscii.verify_against_rom()` re-checks it in the test suite so it
cannot drift. This matters because Claude Code's logo and rules are drawn with
block and quadrant glyphs, which is precisely what PETSCII is good at.

**The C128 NMI entry is not the C64's.** The ROM stub at `$FF05` pushes A, X, Y
*and* the MMU configuration register before dispatching through `$0318`. A
handler that saves its own registers and exits with a bare `RTI` unbalances the
stack and returns to a garbage address — it ran twice and then crashed to
`$032C`. The correct exit is `JMP $FF33`, the KERNAL's matching unwind.

**Charset 2 keeps what matters.** The C128 shows either uppercase+graphics or
lowercase+uppercase. Readable text needs the lowercase set, which costs codes
`$41-$5A` (they become A-Z) but keeps the horizontal rule, the cross, every box
corner, the centred vertical bar at `$5D`, and all the block elements. The only
casualties are the rounded corners, which fold onto the sharp ones.

**cc65 hands you PETSCII, not ASCII.** String literals are translated for CBM
targets, so `main.c` folds PETSCII to screen codes rather than treating text as
ASCII. Getting this wrong renders text as graphics glyphs.

**The Ultimate's modem is in the way, benignly.** On an incoming connection it
sends `\rRING\r` and waits for `ATA`. Its replies are printable ASCII plus CR,
and protocol opcodes are `$01-$09`, so the two streams cannot collide: every
byte goes to both the modem watcher and the protocol decoder, and each ignores
the other's traffic.

**Dial-out is blocked here, not broken.** `ATD<host>:<port>` would let the C128
initiate, but `192.168.1.237` is not in this node's firewalld trusted zone, so
the inbound connection never lands. The bridge dialling the Ultimate avoids
needing a firewall change.

## Status

**Display path: working on the real C128.** Verified with hard counters read out
of the machine's own RAM while it ran: 2773 bytes delivered, `_rxDropped 0`,
`_rxOverruns 0`. The 40-column companion panel shows text that originated on the
Linux side, which proves the whole chain — PTY, pyte, PETSCII, differ, TCP,
Ultimate modem, ACIA, NMI, 6502 decoder, screen RAM. When nothing changes on
screen the link goes completely idle, as designed.

**Verified in VICE with the same client binary:** Claude Code's full trust dialog
renders on the emulated VDC at 38400 baud with zero drops and zero overruns.

**Keyboard path: working on the real C128.** Confirmed from the bridge's own
log, which records what it receives and what it writes to the PTY:

```
[bridge] keys from C128: b'\r' -> pty b'\r'
[bridge] keys from C128: b'H'  -> pty b'h'
[bridge] keys from C128: b'I'  -> pty b'i'
```

The cause of the earlier failure was `kbhit()`/`cgetc()` from cc65's conio never
returning keys placed in the C128's keyboard buffer, so nothing was transmitted
while the receive direction worked perfectly. The client now calls the KERNAL's
GETIN at `$FFE4`, which is the documented non-blocking read.

Two things made this look worse than it was while diagnosing. Letters and `/`
sent to Claude Code's trust dialog legitimately do nothing — the only key that
dialog answers to is RETURN — so early tests read as "no response" when the
dialog was simply ignoring the input. And a small byte count coming back is the
differ working, not a failure: typing one character changes a couple of cells,
so the update is a handful of bytes, not a repaint.

**Two measurement caveats that invalidated earlier attempts, worth not
repeating:** the bridge is killed when a tool call returns unless it is started
under tmux, and several keyboard tests were run against an already-dead link.
Keys were also injected by poking the KERNAL buffer over the network rather than
pressed on the real keyboard; that is the same buffer `cgetc()` reads, but it is
not the identical path.

**The 80-column screen can now be read remotely.** The VDC's RAM is not on the
cartridge bus, but the C128 itself can reach it, so the client copies a VDC
plane into ordinary memory on request (`mirrorReq`) and `tools/vdcpeek.py`
reads it back. Confirmed against the real machine: the Claude Code welcome box,
logo and input prompt all render, and typing `abc` shows `> abc` on row 21.

**The VDC attribute byte is not the protocol attribute.** It is
`bit7 alternate charset | bit6 reverse | bit5 underline | bit4 blink |
bits3-0 colour`, and the client translates into it (`attrToVdc`) rather than
writing the wire value through:

* **Bit 7 must be set.** The C128 keeps 512 character definitions at the base in
  R28 — the first 256 the uppercase/graphics set, the second 256 the lowercase
  set. Everything the bridge encodes is lowercase-set screen codes, so without
  this bit the VDC draws them from the wrong half and text comes out as graphics
  symbols.
* **Underline is discarded.** Claude Code underlines links, but the VDC rules a
  line under every cell of a run including the blanks, which made the whole
  screen unreadable.

**pyte mishandles private-prefix CSI, and it shows up as pixels.** Claude Code
emits `ESC[<u` / `ESC[>1u` (Kitty keyboard protocol) and `ESC[>4;2m`
(modifyOtherKeys). pyte does not recognise the `<`, `>` or `=` prefix, so it
printed the literal `u` at the cursor — a stray character in the top-left corner
— and applied `ESC[>4;2m` as plain SGR 4, switching underline on for the whole
screen. One cause, two symptoms that looked unrelated. `sanitize()` strips them
and `test_private_prefix_csi_is_stripped` pins the behaviour.

**Redefining a VDC character is address arithmetic that must not be fused.**
Definitions live in VDC RAM at `R28_base + $1000 + code*16` for the lowercase
bank. Multiplying the code by 16 *into* the register already holding the base
shifts the base too, so every glyph lands somewhere arbitrary — in practice in
the attribute area, corrupting colours and leaving the real glyphs untouched.
Compute `code*16` separately, then add the base. `tools/vdcpeek.py` can read
the definitions back out of VDC RAM, which is the only way to check this
without staring at the monitor.

**Flow control must not be handed back on a resync.** A resync means the client
lost its place, not that its receive ring is empty. Restoring the full credit
window on top of bytes it has not read yet is precisely how the ring overruns -
which produces more stray bytes, more resync requests, and a repaint storm that
never converges. Credit is returned only as the client actually consumes.

For the same reason a stray byte asks for a repaint at most once per cooldown:
each request costs a full 2KB repaint, so reacting to every unrecognised byte
turns one desync into a feedback loop.

**A bare opcode should not be able to end the session.** `CMD_BYE` takes a magic
second byte, because one corrupted byte was enough to shut the terminal down.

**Autoboot is a C128 KERNAL feature, and the Ultimate cannot replace it.** On
every reset the C128 reads track 1 sector 0 of device 8 and, if it starts with
`CBM`, prints `BOOTING <message>` and JSRs the code that follows. The boot code
here stuffs `RUN"C"` into the keyboard buffer and returns, so BASIC starts the
client — the same mechanism the network deploy path uses. The program on the
boot disk is named `c` because the keyboard buffer holds ten characters and
`RUN"CLAUDE"` needs twelve.

Two things about writing that sector by hand, both of which the emulator caught
and either of which would have hung the machine on every power-on:

* **Put the `rts` before the data, not after.** With the string after the code
  but the `rts` after the string, execution fell through `RUN"C"` and ran the
  text as instructions — the emulator stopped with `PC=$0B2C`, inside the
  string, and every client counter reading uninitialised garbage.
* **Compute the branch displacement, don't write it.** A hand-written `bpl -8`
  was one byte short of the loop start and would have branched into the middle
  of an instruction. `mkbootdisk.py` derives it and range-checks it.

**The Ultimate has no "mount an image at startup" setting** — every config
category was checked. So a cold power-on leaves drive A empty and nothing
autoboots, and the always-on Linux side has to do the bring-up:
`server/bootstrap.py` mounts the boot disk and resets. It decides whether a
client is already running by looking for the client's name on the 40-column
screen at `$0400`, **not** by reading the ACIA — probing `$DE00-$DE03` would
pop bytes off the 6551 and corrupt a live session. That makes it idempotent, so
the service can re-run it on every restart without ever disturbing a session in
use.

The boot disk lives on the Ultimate's own storage at `/Usb0/claude-boot.d64`,
uploaded over **FTP** (anonymous login works); the REST file-upload endpoint is
unimplemented in firmware 3.11.

**Glyph aliases beat glyph slots.** Claude Code picks its response bullet and
spinner from a family — `⏺ ● ○ ◉` and `✳ ✻ ✴ ✶`, depending on state — and the
substitute table folded the whole circle family to the letter `o` and the
asterisks to `*`, so a real answer rendered as `o AUTOBOOT OK`. `font.ALIASES`
points the siblings at an already-drawn slot: 38 characters covered by 21
slots. A viewer must label a shared slot with the glyph it was *drawn* for,
otherwise an alias wins the name and the prompt chevron gets reported as `›`.

**Accented letters fold, they do not fall back.** Claude Code says things like
"Sautéed for 3s", and `Saut?ed` reads as corruption rather than as a missing
accent. NFD-decomposing and dropping the combining marks handles the whole
range without a table; the handful that are not base-plus-mark (`ø æ œ ß ł þ`)
get one-cell substitutes so columns stay aligned.

## Character coverage

The terminal shows whatever Claude Code shows — file contents, source, command
output — so coverage cannot be argued from the chrome it happens to draw, and
anything missed reaches the screen as a question mark that is indistinguishable
from a real one. Three layers handle that.

**Derivation, not enumeration.** `server/derive.py` reads the structure in the
Unicode *name*. "BOX DRAWINGS HEAVY DOWN AND LEFT" names its own arms, so the
light-line glyph with the same arms is the answer without anyone listing all 128
box characters. The same trick covers partial blocks, geometric shapes, arrows,
Greek, superscripts and most punctuation. Box Drawing went from 27/128 covered
to 128/128 this way.

**An audit that can fail the build.** `tools/charaudit.py` sweeps the blocks a
terminal realistically meets and reports how every character renders;
`--strict` exits non-zero if a must-cover block has a gap, and the same sweep
is pinned as a test. It reports through `petscii.render_path`, which
distinguishes a deliberate stand-in from a failure — mapping `¿` to `?` is
correct and falling through to `?` is a bug, and the screen code is identical
either way, so the code alone cannot tell them apart.

**Runtime logging for the rest.** No block list covers everything, so the
renderer records what it could not draw and the bridge logs it with codepoint
and Unicode name:

```
WARNING unmapped character U+1F600 GRINNING FACE x1 -> rendered as '?'
```

Four bugs this found, none of which a spot check would have:

* `┈` rendered as `┴`, because **"QUADRUPLE" contains the substring "UP"**. Arm
  matching is now on whole words.
* `≠` rendered as `=`. NFD-decomposing accented letters is right, but the same
  decomposition drops a combining slash and **inverts the meaning** — worse than
  any fallback. Folding is now restricted to letters, and every negated relation
  maps to `#`.
* `√` rendered as a shaded block, having matched "SQUARE" in "SQUARE ROOT".
* `±` rendered as `-`, because "MINUS" matched before "PLUS-MINUS".

Verified on the real machine by having Claude Code emit the characters — it
cannot be typed, since the C128 keyboard has no key for a box-drawing glyph:
`U+2501`→`─`, `U+2550`→`─`, `U+00B1`→`+`, `U+2260`→`#`, `U+221E`→`8`,
`U+00E9`→`e`, `U+00B5`→`u`, `U+00B0`→`*`.

## Logging and evals

The bridge logs to stderr and, with `--log-file`, to a file; `--log-level`
takes the usual names. `tools/eval.py` runs every check and prints one verdict:

```
check       result  detail
unit        pass    22/22 passed
coverage    pass    8 must-cover blocks complete
render      pass    70 distinct characters, 0 uncovered
emulator    pass    client rendered the shell prompt, 0 bytes dropped
hardware    pass    client alive, rx=22459, 0 dropped, 0 overruns
```

Checks needing the physical machine are **skipped, not passed**, when it is not
reachable, and the summary lists what went unverified — a skip must never read
as a pass.

## Two traps that cost the most time

**Reading the ACIA over DMA destroys the link.** `readmem $DE00` pops a byte off
the 6551's receive register and `readmem $DE01` clears its interrupt flag, so
any host-side probe of `$DE00-$DE03` steals data from the client and can drop
the modem back to command mode. Diagnose with the client's own counters
(`_rxCount`, `_rxDropped`, `_kbCount`) and `tools/vdcpeek.py`, never by peeking
at the ACIA while a session is live.

**The bridge inherits whatever namespace launched it.** Started from a sandboxed
shell it gets a read-only `~/.claude`, and Claude Code's SessionStart hook then
fails once per attempt with `EROFS`, filling the screen with errors and pushing
the welcome banner off the top — which looks exactly like a rendering bug and is
not one. Launch it from a normal shell (or over the loopback SSH channel).

## Design decisions that were forced by measurement

**Flow control is receiver-driven, not timed.** Metering the sender by wall
clock does nothing: at 38400 and at 1200 bytes/sec the client dropped exactly
the same 74 bytes, because neither VICE nor the Ultimate paces to the ACIA's
nominal baud. Only the C128 knows when it has applied a byte, so it returns a
credit every 64 bytes and the server never runs more than 192 bytes ahead. That
took drops from 484 to zero.

**The client stays at 1MHz.** `fast()` doubles VDC throughput but blanks the
VIC-II, which is the companion panel on the second monitor. Exposing that choice
also exposed the ring-overflow bug that 2MHz had been masking.

**Screen clearing uses the VDC block fill.** Writing 2000 cells individually
takes ~80ms at 1MHz — long enough for a burst to lap a 256-byte receive ring.
