# Hardware setup

## What is required

- A **Commodore 128** (or 128D). The 80-column VDC output is the terminal, so a
  C64 will not work — it has no VDC.
- An **Ultimate II+** cartridge, firmware 3.11 or later, on the network. It
  provides both the 6551 ACIA the client talks to and the TCP link the host
  dials into. An Ultimate 64 exposes the same API and should work; untested.
- A **monitor on the VDC output** (RGBI, or the composite/greyscale pin). A
  second monitor on the 40-column VIC-II output is optional but recommended —
  it becomes a live status panel, and both screens are driven simultaneously.
- A **Linux host** on the same LAN with `claude` installed and authenticated.

No cable modification, soldering or extra hardware is needed. The Ultimate's
network port carries everything.

## Ultimate II+ settings

In the Ultimate menu, under **Modem Settings**:

| Setting | Value | Why |
|---|---|---|
| Modem Interface | `ACIA / SwiftLink` | the only option; this is what the client drives |
| **ACIA (6551) Mode** | **`DE00/NMI`** | maps the ACIA at `$DE00` and drives NMI. Required. |
| Listening Port | `3000` | the host dials this |

Then **save the configuration to flash**. Verified: the setting survives a full
power cycle once flashed. It does *not* survive if you only set it in the menu
without saving — that produced a confusing failure where the modem listener
answers `Modem Software is currently not running...`.

`server/bootstrap.py` re-asserts and re-flashes this on every cold bring-up, so
a machine that loses it recovers on its own.

Nothing else needs changing. Drive A stays a 1541 on bus 8, which is what the
boot disk is built for.

## First boot

```sh
export CBM_ULTIMATE_HOST=<your Ultimate's IP>
make disk          # builds client/build/claude.prg and claude-boot.d64
./run.sh           # uploads over FTP, mounts, resets, connects
```

`run.sh` puts the boot disk on the Ultimate's own storage at
`/Usb0/claude-boot.d64` over **FTP** (anonymous login). The REST file-upload
endpoint is unimplemented in firmware 3.11, so FTP is the way in.

You should see, on the 80-column screen, the Claude Code welcome box. On the
40-column screen, a status panel.

## Autoboot

The disk carries a C128 boot sector, so a **reset** starts the terminal with no
typing. The Ultimate keeps drive A mounted across a power cycle once the image
is on its own storage, so nothing needs re-uploading.

A **cold power-on does not autoboot**, though: the C128 reads the boot sector
before the Ultimate's drive emulation is ready and never retries. That is why
the host side issues a reset once the Ultimate is up — which the systemd service
does automatically:

```sh
cp claude-c128.service ~/.config/systemd/user/
systemctl --user enable --now claude-c128
loginctl enable-linger $USER      # so it runs without you logged in
```

The service is safe to restart at any time: its pre-start step does nothing if a
client is already running, so it will not reset a machine you are using.

## Speed

38400 baud, 8N1, which is control register `$1F` on a SwiftLink (the doubled
crystal shifts every 6551 baud code). The binding constraint is not the wire but
how fast the C128 can apply a frame at 1MHz, which is why flow control is
receiver-driven — see [FINDINGS.md](FINDINGS.md).

The client deliberately stays at 1MHz rather than calling `fast()`: 2MHz doubles
VDC throughput but blanks the VIC-II, which is the 40-column status panel.

## Troubleshooting

**`Modem Software is currently not running...`** — the Ultimate's modem layer
only starts once a program configures the ACIA. Either the client is not running,
or ACIA mode is not `DE00/NMI`. Run `python3 server/bootstrap.py --force`.

**Nothing on the 80-column screen** — check you are looking at the VDC output,
not the VIC-II. The 40-column screen shows the status panel, not the terminal.

**Garbled or missing rows** — should not happen; the client counts dropped bytes
and the status panel shows them. If `dropped` is non-zero, file a bug with the
count.

**Screen wrong but you cannot tell what the machine sees** — `tools/vdcpeek.py`
reads the real 80-column screen back over the network. That is the only way to
see the VDC from the host, since its RAM is not on the cartridge bus.

**Do not poll the ACIA from the host while a session is live.** Reading `$DE00`
pops a byte off the 6551's receive register and reading `$DE01` clears its
interrupt flag, so either steals data from the client. Use the client's own
counters instead (`tools/eval.py` reads them safely).
