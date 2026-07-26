# Contributing

Patches welcome. The one rule that matters: **do not claim something works
without having run it.** This project talks to a 40-year-old machine over a
serial link, and almost every bug in its history looked fine in theory.

## You do not need a Commodore 128

Three layers of testing work without hardware, and they catch most things:

```sh
make check      # unit tests + Unicode coverage           (~1s)
make emu        # the real compiled 6502 client, in VICE  (~25s)
```

`make emu` boots the actual client binary in VICE with the ACIA wired to the
bridge, then reads the emulated VDC back through VICE's monitor. It reports the
client's own counters — bytes received, dropped, ACIA overruns, main-loop
liveness — so a failure localises immediately.

For host-side work there is also a virtual client with no 6502 involved:

```sh
python3 server/bridge.py --listen 6400 --command claude &
python3 tools/vc128.py --connect 127.0.0.1:6400 --interactive
```

## Development loop

Work in the emulator, not on hardware. Two of the worst bugs in this project's
history — a boot sector that ran its own string as instructions, and an NMI
handler that unbalanced the stack — would each have hung the real machine on
every power-on, and the emulator caught both for free.

If you do have hardware, `tools/vdcpeek.py` reads the real 80-column screen back
over the network, and `tools/hwtype.py` types into it. Those two make hardware
debugging tractable; without them you are guessing.

## Before opening a PR

```sh
make eval       # all five layers
```

Everything that can run must pass. Checks needing the physical machine will skip
if it is absent, and that is fine — but a skip is not a pass, and the summary
says so.

If you touch character rendering, `make check` includes a sweep of every
must-cover Unicode block. It will fail if anything new falls through to `?`.

## Code style

Match what is there. Specifically:

- **Comments explain why, not what.** The codebase is full of load-bearing
  hardware facts (`$FF33` rather than `RTI`, why the credit window is not reset
  on resync). Those comments are the most valuable thing in the repo; a future
  reader who deletes one will reintroduce the bug.
- **Derive, do not enumerate.** The glyph table is generated from the character
  ROM and re-verified in the test suite; the Unicode mapping is driven by
  Unicode names, not a hand-written table. Adding 100 lines of lookup where a
  rule would do is a regression.
- **Assert on the contract.** A test that passes when the code is broken is
  worse than no test.

Python targets 3.9+ and uses no third-party packages except `pyte`. The 6502
side is `cc65`.

## Reporting a bug

Include:

- what you saw on which screen (80-column terminal, or 40-column panel)
- the output of `make eval`
- the relevant part of the bridge log — run with `--log-file` and `--log-level DEBUG`
- if characters render wrongly, the log lines naming them; the renderer records
  every character it could not draw, with codepoint and Unicode name

If the screen is wrong and you have hardware, `tools/vdcpeek.py` output is worth
more than a description.

## Things that are deliberately the way they are

Before "fixing" these, read [docs/FINDINGS.md](FINDINGS.md):

- the client runs at 1MHz, not 2MHz
- a resync does not restore the credit window
- `CMD_BYE` requires a magic byte
- accent folding is restricted to letters
- the host never reads `$DE00`/`$DE01` while a session is live
