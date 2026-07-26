# Wire protocol

A byte stream in both directions over the ACIA. Deliberately small: the C128
decodes it with a resumable state machine in about 200 bytes of C, because bytes
arrive from an NMI ring buffer in arbitrary chunks and any command can be split
across two reads.

All multi-byte values are single bytes; there is no endianness to get wrong.

## Host → client

| Opcode | Name | Payload |
|---|---|---|
| `$01` | `CLEAR` | `attr` — blank the screen in this attribute |
| `$02` | `RUN` | `row, col, attr, len`, then `len` screen codes |
| `$03` | `FILL` | `row, col, attr, len, char` — one character repeated |
| `$04` | `CURSOR` | `row, col`; `$FF $FF` hides it |
| `$05` | `FRAME` | end of frame, no payload |
| `$06` | `BELL` | no payload |
| `$07` | `PANEL` | `row, colour, len`, then `len` screen codes → 40-column panel |
| `$08` | `HELLO` | `cols, rows` |
| `$09` | `BYE` | `magic` — must be `$5A` to act |
| `$0A` | `GLYPH` | `code`, then 8 bitmap bytes → redefine a VDC character |

`BYE` takes a magic byte because a bare opcode is one bit-flip away from ending
the session, and that happened.

An unrecognised opcode makes the client request a repaint, at most once per
cooldown. Reacting to every stray byte turns one desync into a repaint storm,
since each request costs a full 2KB frame.

### Attributes

The `attr` byte is close to a VDC attribute but not identical, so the client
translates:

```
bit 6  reverse
bit 5  underline
bits 3-0  colour (VDC palette index)
```

The client adds bit 7 (alternate character set) unconditionally, because the
C128 keeps 512 glyph definitions and everything here is encoded against the
lowercase half. Without it, text renders as graphics symbols.

## Client → host

Keystrokes are sent raw as PETSCII, one byte each — translation to terminal
input happens on the host, so the key map can change without reflashing a disk.

`$00` is never a keystroke, so it introduces a control byte:

| Sequence | Meaning |
|---|---|
| `$00 $01` | `RESYNC` — "repaint everything, I may have missed bytes" |
| `$00 $02` | `BYE` — client is shutting down |
| `$00 $03` | `CREDIT` — "I have consumed 64 more bytes" |

## Flow control

The host sends nothing until the client announces itself with `RESYNC`. The link
is open before the C128 has finished loading, and on real hardware the operator
starts the client whenever they like, so the first frame would otherwise be lost
into a machine that is not listening.

After that the host stays within a **192-byte window** of what the client has
acknowledged, and the client returns a credit every 64 bytes it consumes.

This is receiver-driven for a specific reason: neither VICE's RS232 emulation nor
the Ultimate's TCP-backed modem paces to the ACIA's nominal baud. Metering the
sender by wall clock does nothing at all — at 38400 and at 1200 bytes/sec the
client dropped *exactly* the same bytes. Only the C128 knows when a byte has
actually been applied.

**A resync must not restore the credit window.** A resync means the client lost
its place, not that its ring is empty; handing back a full window on top of
unread bytes is how the ring overruns, which produces more stray bytes and more
resync requests. Removing one line that did this took drops from 164 to 0.

## Framing and the differ

The host runs a full terminal emulator (pyte), so it always has a complete 80×25
grid of `(screen code, attr)`. Each frame it diffs against what the client is
known to be showing and emits only changed cell runs.

Runs are split on attribute changes, and a stretch of 8 or more identical
characters becomes a `FILL`. Changed spans separated by a gap smaller than the
5-byte run header are merged, since resending a few clean cells is cheaper than
a second header.

An unchanged screen emits a bare `FRAME` byte, which the host suppresses — so an
idle terminal costs nothing.

## Sizes

| | |
|---|---|
| Full repaint | ~2KB, about 0.5s at 38400 baud |
| Typical streaming frame | under 100 bytes |
| Glyph upload at startup | 21 glyphs × 10 bytes |
| Status panel, idle | ~82 bytes/sec, 2.1% of the link |
| Idle terminal | 0 bytes |
