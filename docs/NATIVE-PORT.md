# Running without the host: TLS on the Ultimate II+

`claude-c128` needs a Linux host today because talking to the Claude API means
TLS 1.3, and the C128 has no way to do it. This document records what was
actually measured while investigating whether the Ultimate II+ cartridge could
do the TLS instead, removing the host from the picture.

**Status: blocked on entropy, not on size or CPU.** The code exists, builds, and
fits. It refuses to run. Why is below.

Nothing has been flashed to any device.

## Why the cartridge and not the 8502

The 8502 was measured out of contention first. A P-256 scalar multiplication
needs on the order of 10^6 multiply-accumulate steps. At 1 MHz with no multiply
instruction, a 16x16 multiply costs roughly 200 cycles in software, which puts a
single handshake in the tens of minutes and makes session resumption pointless
because the ticket expires first. Symmetric work (AES-GCM, SHA-384) is fine on
a 6502; it is the asymmetric handshake that is out of reach.

The Ultimate II+ already has what is missing: a Nios II gen2 soft core at
62.5 MHz running FreeRTOS and lwIP, with a working TCP stack and its own
Ethernet. It already terminates connections for FTP, HTTP and telnet. Adding
TLS there is an incremental change, not a new port.

## What was built

Against the GPLv3 `1541ultimate` firmware tree, mbedTLS 3.6.2 wired into the
existing Hayes modem emulation:

| File | Role |
|---|---|
| `software/io/acia/modem_tls.{h,cc}` | `ModemTls` — connect / read / write / close over an lwIP socket |
| `software/io/acia/modem_ca_certs.h` | trust store: one root, GTS Root R4, verified self-signed |
| `software/io/acia/modem_mbedtls_config.h` | trimmed mbedTLS config, TLS 1.3 only |
| `software/io/acia/modem.cc` | `ATDT` gains a TLS modifier; relay reads/writes through TLS when active |

The client verifies: `MBEDTLS_SSL_VERIFY_REQUIRED`, `mbedtls_ssl_set_hostname`
for SNI and name checking, chain verification against the pinned root. Without
those the exercise would be decoration, since anything on the path could
substitute its own key.

A cross toolchain had to be built first — `nios2-elf` GCC 14.2.0, binutils
2.43, newlib 4.4 — because Intel stopped shipping the Nios II GCC. Both libgcc
and newlib must be rebuilt with `-mno-hw-mul -mno-hw-div -mno-hw-mulx`; this
FPGA design reports `ALT_CPU_HARDWARE_MULTIPLY_PRESENT 0`. Missing that on
newlib put 55 hardware multiply instructions into `libc.a`, reaching the final
image inside `strchr`, `gmtime_r` and the stdio refill path.

## Measured size

The flash partition for the application is 1,310,720 bytes.

| Build | `ultimate.app` | vs baseline |
|---|---|---|
| baseline, no TLS | 858,856 | — |
| TLS reachable, trimmed config | 1,095,796 | +231 KB |

Fits with 209 KB spare. Trimming got there from an untrimmed 1,500,504 bytes
(185 KB *over* the partition) by dropping TLS 1.2, RSA, the mbedTLS error
string table, X.509 writing, self-tests, and cutting record buffers from 16 KB
to 4 KB.

Two measurement mistakes are worth recording because both produced
optimistic numbers that looked fine:

- Summing `.text` across object files gave 340 KB for mbedTLS. Linked size is
  what matters; the objects overlap and much is discarded.
- An earlier figure of +161 KB was measured on a build where the TLS code was
  not fully linked, so it was not measuring a working stack (see below).

## The two verification gates

Both are cheap and both caught real defects, so they are worth keeping:

```sh
# 1. no instructions this CPU lacks — must be 0
nios2-elf-objdump -d output/ultimate.out | grep -cE '\s(mul|mulxuu|mulxsu|mulxss|div|divu)\s'

# 2. the TLS code is actually in the image
nios2-elf-nm output/ultimate.out | grep -E 'psa_raw_key_agreement|mbedtls_ecp_mul|modem_ca_pem'
```

Gate 2 is the one that matters. It failed initially, and the cause was not what
it looked like:

**`MBEDTLS_SSL_TLS1_3_KEY_EXCHANGE_MODE_EPHEMERAL_ENABLED` was missing from the
trimmed config.** Without it TLS 1.3 keeps only the PSK key exchange modes,
which cannot talk to a public HTTPS server. Nothing warns you — the build
succeeds, `mbedtls_ssl_handshake` is present, and the ECDHE code is simply
never compiled in. That is what made the earlier +161 KB figure meaningless.
A separate, smaller effect was `--gc-sections` correctly discarding functions
called only from the refusing branch of `Connect()`.

Two absences in gate 2 are expected rather than defects, and were confirmed
rather than assumed: `mbedtls_ecdh_compute_shared` is unused because mbedTLS
3.6 routes TLS 1.3 key agreement through PSA, and `mbedtls_x509_crt_verify` is
a public wrapper the TLS layer bypasses in favour of
`mbedtls_x509_crt_verify_restartable`.

Also required, once the TLS code was genuinely reachable:

- `mbedtls_net_send` / `mbedtls_net_recv` do not exist — `MBEDTLS_NET_C` is off
  in the trimmed config, so `net_sockets.c` compiles to an empty object. The
  BIO callbacks now call lwIP `send`/`recv` directly, which also avoids handing
  mbedTLS an `int*` and relying on it being layout-compatible with
  `mbedtls_net_context`.
- Seven HAL syscall objects (`alt_read`, `alt_write`, `alt_open`, `alt_lseek`,
  `alt_fstat`, `alt_sbrk`, `alt_exit`) must be compiled explicitly. Archive
  ordering alone does not satisfy them, and `--start-group` did not help.
- `memory.cc` defines `__dso_handle`, which GCC 14's `crtbegin.o` also provides.
  The duplicate makes the linker disable relaxation, which inflates the image —
  so this matters for the size measurement, not just for tidiness. Guarded on
  `__GNUC__ < 5` rather than papered over with
  `--allow-multiple-definition`.

## Why it refuses to run

`ModemTls::Connect()` returns `false` before touching mbedTLS, and will keep
doing so until `MODEM_TLS_ENTROPY_REVIEWED` is defined by someone who has
solved this:

**There is no usable entropy source on this hardware.** Checked against the
generated BSP, not assumed: `ALT_TIMESTAMP_CLK` is `none`, the FPGA design
instantiates only memory, `io_bridge`, on-chip memory and a PIO — no TRNG, no
timer peripheral, no ADC — and the finest clock reachable is the ITU
millisecond timer with FreeRTOS ticking at 200 Hz.

TLS derives the ECDHE private key from the RNG. A predictable pool means a
passive eavesdropper can recover the session key and decrypt everything, with
the connection looking perfectly normal at both ends. **Weak entropy here is
worse than no TLS, because it looks secure.** Stirring the millisecond timer
and a call counter — which is what the current pool does — makes values differ
between runs but nowhere near unpredictable: a few bits per sample, and an
attacker who knows roughly when the call was placed can bound most of it.

Ways to fix it properly, in order of preference:

1. **Ring-oscillator TRNG in the FPGA design.** Needs Quartus and a bitstream
   rebuild. The only genuinely defensible option.
2. **Interrupt-arrival jitter** accumulated against a high-resolution counter
   over several seconds, with a measured entropy estimate. This design has no
   such counter, so it needs option 1's tooling anyway.
3. **Seed once from a trusted source, persist a counter in flash.** Survives
   reboots, but a flash image copied between devices repeats its keystream.

Do not define the macro to make it work.

Note that the refusing build is still ~228 KB larger than baseline, because
`ModemTls::Read`/`Write` reference `mbedtls_ssl_read`/`write` unconditionally
and keep the stack linked. If the cartridge were ever shipped without a
solution to entropy, those should be compiled out too so the flash is not spent
on code that refuses to run.

## What remains unverified

- **No handshake has ever run.** Everything above is build-time and
  symbol-level verification. Whether mbedTLS 3.6 completes a TLS 1.3 handshake
  against a real server on this core is unknown, and cannot be known while
  `Connect()` refuses.
- **Handshake latency is unmeasured.** A P-256 ECDHE plus chain verification on
  a 62.5 MHz soft core with no hardware multiply is the open question. Estimates
  were deliberately not put in this document; a QEMU `nios2` run or the real
  device would settle it.
- **RAM headroom during a handshake is unmeasured.** Flash fits; peak heap under
  FreeRTOS with 4 KB record buffers has not been checked.
- **Nothing has been flashed.** No image has been written to any device.
