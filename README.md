<img width="1672" height="941" alt="ChatGPT Image Jul 26, 2026, 09_04_09 AM" src="https://github.com/user-attachments/assets/051248e7-a443-42b1-bb81-5e6c2d6ac841" />

# claude-c128

**Claude Code, running on a real Commodore 128 — or a C64.**

The Commodore is the terminal — its keyboard is the input, its screen is
the display. Claude Code itself runs on a Linux box behind it. Nothing is
reimplemented and nothing is faked: the actual `claude` binary runs in a PTY,
and what appears on the VDC is its real TUI, translated cell by cell into
PETSCII and shipped over a 6551 ACIA at 38400 baud.

This is the 80-column screen, read verbatim out of the C128's own video RAM
while a session was running:

```
⏺ VIC-IIe (40-column composite) and VDC 8563 (80-column RGBI).

✳ Cooked for 2s

❯ one line: how much ram does a stock c128 have

⏺ 128 KB of main RAM (two 64 KB banks), plus 16 KB of dedicated VDC video RAM
  (64 KB on the C128D/later boards).

✳ Baked for 2s

❯ one line: what bus do commodore disk drives use

⏺ The Commodore serial IEC bus (a serialized IEEE-488 derivative), with the
  C128's fast-serial burst mode on a 1571/1581.

✳ Worked for 2s

────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────
  OPUS·5 (1m context) ❯ C128-DEMO │ CTX ░░░░░░ 8%/1M │ $0.64 ⏱2m RL░░░7% │ +2d…
  ⏸ manual mode on · ← for agents
```

On a directory it has not seen before, Claude Code draws its full welcome box
instead — rounded corners and all (account line removed here):

```
╭─── Claude Code v2.1.220 ─────────────────────────────────────────────────────╮
│                                                    │ Tips for getting        │
│                 Welcome back!                      │ started                 │
│                                                    │ Run /init to create a … │
│                       ▐▛███▜▌                      │ ─────────────────────── │
│                      ▝▜█████▛▘                     │ What's new              │
│                        ▘▘ ▝▝                       │ Bug fixes and reliabil… │
│   Opus 5 (1M context) with xhigh effort · Max      │ Added Claude Opus 5 ('… │
│                   /tmp/c128-demo                   │ /release-notes for more │
╰──────────────────────────────────────────────────────────────────────────────╯
```

The second monitor, on the 40-column VIC-II output, is a live status panel:

```
claude code                 c128 term
----------------------------------------
. claude code

session   5m15s
frames    190
link      67.9 kb
dropped   0   clean

----------------------------------------
HELP repaints / reconnects
RUN-STOP + RESTORE quits
```

The rounded corners, the block-graphic logo, the `❯` prompt, the `⏺` response
bullet — all of it is the C128's own character generator, with the glyphs
PETSCII lacks uploaded into the VDC's character RAM at startup.

```
   C128 keyboard + 80-column monitor
            │
            │  6551 ACIA (SwiftLink) at $DE00, NMI-driven, 38400 baud
            ▼
   Ultimate II+  ── modem emulation ──  TCP :3000
            │
            │  LAN
            ▼
   Linux host : server/bridge.py
       claude in a PTY → pyte → PETSCII → delta frames
```

## Why it is built this way

**The host does all the layout.** The C128 never reflows text or interprets
ANSI; it applies pre-computed cell runs. An 8-bit machine cannot parse truecolor
SGR and Unicode box drawing at speed, and it does not have to.

**Frames are diffed, not repainted.** Claude Code redraws its whole screen
constantly. A full 80×25 repaint is ~2KB, about half a second of wire time. The
differ sends only changed cell runs, so streaming output costs well under 100
bytes a frame and an idle screen costs nothing at all.

**Flow control is receiver-driven.** The C128 is always the slow party and only
it knows when a byte has actually been applied, so it returns a credit every 64
bytes and the host never runs more than 192 bytes ahead. Metering by wall clock
does not work — see [docs/FINDINGS.md](docs/FINDINGS.md).

## What you need

| | |
|---|---|
| A Commodore 128 | The 80-column (RGBI) screen is the terminal; the 40-column screen becomes a status panel. Both are driven at once. |
| An [Ultimate II+](https://ultimate64.com/) cartridge | Firmware 3.11 tested. Provides the SwiftLink-compatible 6551 ACIA and the network link. |
| A Linux host | On the same LAN, with `claude` installed and logged in. |

A real C128 is not required to work on this: the whole stack runs against VICE,
and a virtual client exercises the host side with no 6502 at all.

### Host packages

```sh
# Fedora
sudo dnf install vice cc65 python3-pyte xorg-x11-server-Xvfb
# Debian / Ubuntu
sudo apt install vice cc65 python3-pyte xvfb
```

`vice` supplies the C128 character ROM (the glyph table is verified against it),
the emulator, and `c1541`/`petcat`. `cc65` builds the 6502 client.

## Quick start

```sh
git clone https://github.com/<you>/claude-c128
cd claude-c128
make check                       # unit tests + character coverage, no hardware
```

Against the emulator, no Commodore needed:

```sh
make emu                         # builds the client, runs it in VICE (C128)
make emu64                       # the same, on a C64
```

Against real hardware:

```sh
export CBM_ULTIMATE_HOST=192.168.1.237   # your Ultimate's address
make disk                                # build client + autoboot disk
./run.sh                                 # upload, boot the C128, connect
```

Set the Ultimate's **ACIA (6551) Mode** to `DE00/NMI` under Modem Settings and
save to flash. `server/bootstrap.py` re-asserts this, but the first time is
easier from the Ultimate's own menu.

For unattended use install the service, which brings the C128 up at boot and
reconnects on its own if the link drops:

```sh
cp claude-c128.service ~/.config/systemd/user/
systemctl --user enable --now claude-c128
```

## Using it

Type on the C128. **HELP** forces a full repaint and re-arms the modem, which is
how you reconnect after restarting the host side. **RUN/STOP + RESTORE** quits.
On a C64 the repaint key is **F7**, since it has no HELP key.

On the C128 the 40-column screen shows a status panel: activity, session clock,
frames sent, bytes on the wire, and the count of any dropped bytes.

### On a C64

```sh
./run64.sh                               # build, load, and dial
```

On a real C64, load and run `client/build/claude64.prg` however you like, then
`python3 server/bridge.py --machine c64 --connect $HOST:3000`.

On a **C128 in C64 mode** it is less obvious, which is what `run64.sh` handles.
The Ultimate's `run_prg` resets the machine, and a C128 resets into *C128* mode;
it then accepts a C64 `.prg`, reports no error, and leaves you at a BASIC 7.0
prompt. So the mode switch has to go through the keyboard first — `GO64`,
confirm, `LOAD`, `RUN` — which is `tools/go64.py`. `run64.sh` also stops the
`claude-c128` service while it runs, because that service's bootstrap re-mounts
the C128 boot disk and resets the machine whenever it cannot see a client.

`--machine c64` is not cosmetic: it sets the PTY to 40 columns, so Claude Code
lays *itself* out for the narrower screen rather than having 80 columns cropped.
It also stops the bridge sending panel lines, which on a C64 would be drawn over
the terminal — there is only one screen.

The palettes are not the same, and the client does not pretend otherwise. The
VDC is RGBI — sixteen fixed combinations at two intensities — while the VIC-II
has its own analogue set. The same index means different colours on each, so the
bridge selects a palette per machine; both tables come from VICE's own
`vdc_deft.vpl` and `colodore.vpl`. The Claude logo is drawn in the orange each
palette actually has: `$AA5500` on the VDC, the VIC-II's true orange on a C64.

Three things the VIC-II cannot do that the VDC can, all visible:

- **No underline and no blink.** Colour RAM holds four bits of colour and
  nothing else. Claude Code underlines links; on a C64 they are just text.
- **Reverse video costs a character, not an attribute.** The client folds the
  reverse bit into the screen code, which is how the VIC-II does it.
- **The cursor is drawn in software.** The VDC has a hardware cursor; the VIC-II
  does not, so the client inverts the cell — and checks the cell still holds
  what it wrote before restoring it, so a repaint underneath cannot leave a
  stale character behind.

Forty columns is genuinely narrow. Prose, the welcome box and the logo are fine;
diffs and long file paths get truncated by Claude Code itself. It is a real
terminal, not a comfortable one.

## Layout

| Path | What it is |
|---|---|
| `server/bridge.py` | the daemon: PTY, framing, transport, logging |
| `server/vtscreen.py` | ANSI → an 80×25 grid, via pyte |
| `server/petscii.py` | Unicode → screen codes, truecolor → 16 VDC colours |
| `server/derive.py` | name-driven mapping; covers whole Unicode blocks |
| `server/font.py` | custom VDC glyphs, drawn as editable 8×8 art |
| `server/protocol.py` | wire format and the frame differ |
| `server/keymap.py` | C128 keys → terminal input |
| `server/bootstrap.py` | mount the boot disk and reset, idempotently |
| `client/main.c` | protocol decoder, keyboard, modem answering |
| `client/c128hw.s` | VDC writes and NMI-driven ACIA receive |
| `tools/eval.py` | every check, one verdict |
| `tools/charaudit.py` | Unicode coverage audit |
| `tools/emutest.py` | full stack in VICE, with client diagnostics |
| `tools/vc128.py` | virtual C128, for host-side development |
| `tools/vdcpeek.py` | read the real 80-column screen over the network |
| `tools/mkbootdisk.py` | build the autobooting D64 |
| `tools/glyphmatch.py` | derive the glyph table from the character ROM |

## Testing

```sh
make check      # unit tests, character coverage        (no hardware)
make emu        # the real 6502 client in VICE           (no hardware)
make eval       # all five layers, including hardware if reachable
```

`tools/eval.py` prints one verdict across five layers. Checks that need the
physical machine are **skipped, not passed**, when it is absent, and the summary
names what went unverified.

```
check       result  detail
unit        pass    22/22 passed
coverage    pass    8 must-cover blocks complete
render      pass    101 distinct characters, 0 uncovered
emulator    pass    client rendered the shell prompt, 0 bytes dropped
hardware    pass    client alive, rx=8591, 0 dropped, 0 overruns
```

## Status

Working on real hardware: rendering, the keyboard, autoboot, auto-reconnect, and
survival of a power cycle — all verified against the machine, with zero dropped
bytes and zero ACIA overruns. See [docs/FINDINGS.md](docs/FINDINGS.md) for what
that took, including several bugs that would each have hung the machine.

Known limitations:

- **CJK, emoji and Cyrillic render as `?`.** There is no sensible one-cell Latin
  stand-in. The bridge logs every such character with its codepoint and Unicode
  name, so gaps are visible rather than silent.
- **Only tested on an Ultimate II+, firmware 3.11.** The Ultimate 64 exposes the
  same API and should work, but nobody has tried it.
- **The bell is unverified.** The command arrives and the SID registers are
  written; whether it is audible has not been confirmed.
- **The C64 has no underline or blink**, and 40 columns truncates long lines.
  See the C64 notes above.
- **The C64 client has run on a C128 in C64 mode, not on a physical C64.**
  Claude Code renders correctly on the real machine — welcome box, logo, prompt,
  statusline, and the logo in orange — but C64 mode on a C128 is not quite a C64
  (same VIC-II and 6510-compatible CPU, different board), so a real C64 is still
  untested.

## Documentation

- [docs/HARDWARE.md](docs/HARDWARE.md) — Ultimate settings, first boot, wiring
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — the wire protocol
- [docs/FINDINGS.md](docs/FINDINGS.md) — the non-obvious things, and the bugs
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to work on this

## Licence

MIT — see [LICENSE](LICENSE).
