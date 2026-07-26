# Running without the host: TLS on the Ultimate II+

`claude-c128` needs a Linux host today because talking to the Claude API means
TLS 1.3, and the C128 has no way to do it. This document records what was
actually measured while investigating whether the Ultimate II+ cartridge could
do the TLS instead, removing the host from the picture.

**Status: it fits, and it is far too slow to be worth flashing.** The code
builds, fits in flash with 209 KB spare, and needs about 10 KB of RAM. It refuses
to run for lack of an entropy source. And a handshake costs **3.5 billion
instructions** — measured, not estimated — which is around five and a half
minutes on this core, or a minute even with a hardware multiplier added.

An earlier version of this document put that figure at 96 seconds and claimed a
hardware multiplier would cut it to 1.6 s. Both were wrong, and wrong in the
flattering direction. They came from static disassembly plus an assumption that
one hot function dominated; it does not. Building an instruction-set simulator
(`tools/nios2-sim`) and running the real code settled it. The corrected numbers
are below, along with what the mistake was.

Nothing has been flashed to any device.

**Where the code is.** Every path below is relative to a local clone of the
GPLv3 [`1541ultimate`](https://github.com/GideonZ/1541ultimate) firmware tree,
which is **not part of this repository** — it is a separate project under a
different licence, and the changes described here have not been submitted
upstream. This document is the record of what was measured; it is not a patch
you can apply from here.

## Why the cartridge and not the 8502

The 8502 was ruled out first, on the grounds that a P-256 handshake needs on the
order of 10^6 multiply-accumulate steps. That was an estimate at the time; the
instrumented count below puts it at **999,646**, so the premise held. At 1 MHz
with no multiply instruction and a software 16×16 multiply costing on the order
of 200 cycles, a single handshake lands in the tens of minutes, which also makes
session resumption pointless because the ticket expires first. Symmetric work
(AES-GCM, SHA-384) is fine on a 6502; it is the asymmetric handshake that is out
of reach.

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
worse than no TLS, because it looks secure.**

### What the clock situation actually is

Worth stating precisely, because the first version of this document was vague
about it and the code was wrong about it. From `fpga/io/itu/vhdl_source/itu.vhd`:

- `ms_timer` increments on `tick_1ms` and runs freely. This is the **only**
  free-running clock software can read: 1 ms resolution.
- `ITU_TIMER` is finer — `tick_1us` with `c_timer_div = 5`, so 5 µs per tick —
  but line 102 only decrements it when non-zero, so it is a reloadable one-shot
  that **halts at zero**, and other code already reloads it for delays. It reads
  0 most of the time and cannot serve as a sampling clock.

### The accumulator that is there now

`StirEntropy()` samples inter-arrival times, at 1 ms resolution, of events this
board does not schedule: characters typed on the C128 (`modem.cc`, the ACIA TX
buffer path) and packets arriving from the network (the relay's `recv`). Samples
go into a 64-entry ring; `mbedtls_hardware_poll()` absorbs the ring with SHA-256
and squeezes output from it. SHA-256 is already linked for the handshake, so this
costs no extra flash.

It is **metered and fails closed**: each sample credits a deliberately
pessimistic 2 bits, a delta identical to the previous one credits nothing (that
is what a machine-paced or idle source looks like), and a draw that would exceed
the collected budget returns `MBEDTLS_ERR_ENTROPY_SOURCE_FAILED` rather than
stretching what it has. Drawing debits the budget, so a second seeding cannot
reuse the same entropy.

Three defects in the first attempt are recorded here because none of them
announced itself, and any one would have produced a "working" TLS stack with
predictable keys:

- it mixed in `(uint32_t)ITU_TIMER` — an **address** macro, not a register read,
  so the timer's contribution was a compile-time constant
- `StirEntropy()` was never called from any event path, only from inside the
  poll callback, so nothing ever accumulated over time
- there was no entropy accounting at all, so there was nothing to fail on

### It is still not sufficient

`MODEM_TLS_ENTROPY_REVIEWED` stays undefined. 1 ms resolution over human
keystrokes is a few bits per event at best; an attacker who knows roughly when
the call was placed can bound much of it. Most importantly **the 2-bits-per-sample
credit is an assumption that has never been measured on this hardware** — the
accounting is only as good as that number.

Ways to finish it, in order of preference:

1. **Ring-oscillator TRNG in the FPGA design.** Needs Quartus and a bitstream
   rebuild. The only option that is defensible without an entropy measurement
   campaign.
2. **Keep this accumulator but justify the credit** — sample against a
   free-running high-resolution counter and measure the distribution on real
   hardware. Adding such a counter needs Quartus too.
3. **Seed once from a trusted source, persist a counter in flash.** Survives
   reboots, but a flash image copied between devices repeats its keystream.

Do not define the macro to make it work.

### Testing the accounting

The accounting is the security-bearing part, and it is testable off-hardware.
`software/io/acia/hosttest/run.sh` compiles the **real** `modem_tls.cc` for the
host against a fake millisecond clock — not a copy of the logic — and drives
arrival patterns deliberately: 15 checks covering refusal when empty, no credit
for evenly-spaced or zero-delta events, accumulation to threshold, exact
debiting, and refusal of oversized requests. Stubs for the TLS calls `abort()`
rather than returning plausible values, so a test that strays into the handshake
path fails loudly instead of quietly passing.

It was mutation-tested, which is the only reason to believe it. Four deliberate
breakages: crediting every sample, removing the fail-closed gate, dropping the
budget debit, and ignoring the ring contents. The first three were caught
immediately. **The fourth was not** — with the ring ignored, successive draws
still differed, because the event counter alone was feeding the hash. A draw
that is a pure function of how many events have occurred is predictable, so this
mattered. The fix was a check that compares two draws with the *same* event
count and different timings, in separate processes so the counter matches; it
now catches that mutation.

Two of those mutations are also a reminder that a mutation can be a no-op:
the first attempt at disabling the fail-closed gate inserted `false &&` into a
condition joined by `||`, and precedence left the second clause still guarding
it. The test passing there said nothing until the mutation was corrected.

Note that the refusing build is still ~229 KB larger than baseline, because
`ModemTls::Read`/`Write` reference `mbedtls_ssl_read`/`write` unconditionally
and keep the stack linked. If the cartridge were ever shipped without a
solution to entropy, those should be compiled out too so the flash is not spent
on code that refuses to run.

## Handshake cost

This was the open question. It is now measured rather than derived, and the
measurement contradicted the derivation badly enough to change the conclusion.

The CPU is the **Nios II/e economy core** — `ALT_CPU_CPU_IMPLEMENTATION "tiny"`
in the generated BSP. No caches, no barrel shifter, no multiplier. Because
mbedTLS ships no nios2 assembly, its bignum code falls back to generic C and GCC
lowers each limb-wise multiply-accumulate to a `__muldi3` call, which calls
`__mulsi3` six times, each a 7-instruction shift-add loop.

### What the simulator says

There is no way to run Nios II code on a current machine — QEMU removed the
target — so `tools/nios2-sim` was written for this. It counts instructions and
validates itself by computing a P-256 shared secret that must match the host byte
for byte; a single wrong carry in 585 million instructions would change it.

Measured, for the public-key work of one ECDHE-ECDSA P-256 handshake
(ephemeral keygen + ECDH + two ECDSA verifications for a leaf and an
intermediate), at 62.5 MHz:

| core | ECP config | instructions | @1 CPI | @6 CPI |
|---|---|---|---|---|
| no multiplier | as shipped here (w=2, no fixed-point) | 3,505 M | 56 s | **336 s** |
| no multiplier | untrimmed (w=4, fixed-point) | 1,962 M | 31 s | 188 s |
| hardware multiply | as shipped here | 688 M | 11 s | 66 s |
| hardware multiply | untrimmed | 388 M | **6.2 s** | 37 s |

1 CPI is a floor no multi-cycle core can reach, so it bounds the best case; the
6 CPI figure usually quoted for the Nios II/e could not be verified from a local
source and is an assumption, which is why both columns are given.

Per-phase, without a multiplier: keygen 584.6 M, ECDH 584.7 M, one ECDSA verify
1,168.1 M. Verify costs almost exactly two scalar multiplications, which is what
it should — `u1·G + u2·Q` — and that internal consistency is a small check on
the numbers.

### What was wrong before, and why

An earlier version of this document reported **998.6 M** instructions without a
multiplier and **17.0 M** with one, for a 59× speedup. Measured: **3,505 M** and
**688 M**, a **5.1×** speedup. So the baseline was optimistic by 3.5×, the
hardware-multiply figure by 40×, and the headline speedup by 11×.

The error was methodological, not arithmetic. Those figures came from counting
limb multiply-accumulates and multiplying by the instruction cost of one, taken
from disassembly. Both inputs were about right. The mistake was assuming that
one function's cost *was* the total: the surrounding work — modular reduction,
constant-time conditional copies, `mbedtls_mpi` grow/copy/free, Montgomery
setup, and the modular inversion inside ECDSA verify — is the majority of the
instructions. Scaling one component by its own speedup and calling it the whole
is Amdahl's law, and it was ignored.

The lesson is not subtle: a derived number that has never been executed should
be labelled as such and treated as provisional. It was labelled, but it was also
put in the summary line, which is where it did the damage.

### So what would it take

- **Flash**: fits, 209 KB spare. Solved in software.
- **RAM**: peak mbedTLS heap during the public-key work is **2.2 KB**, plus the
  two 4 KB record buffers — about 10.2 KB before FreeRTOS task stacks. Never a
  concern.
- **Entropy**: needs a TRNG in the FPGA design.
- **Speed**: a hardware multiplier is worth 5.1×, and restoring the ECP settings
  that were trimmed to fit flash is worth another 1.8×. Together they take 336 s
  down to 37 s — still unusable. Getting to the 6.2 s figure needs ~1 CPI, which
  means replacing the "tiny" core with the pipelined Nios II/f and its caches.

That is a real FPGA redesign — new core, new peripheral, more logic — not a
recompile, and whether the Cyclone IV on this board has the room for it is
unknown here. Even then the result is a handshake measured in seconds, tolerable
only because TLS session resumption would let subsequent connections skip it.

The honest recommendation is that the host-based design this repository actually
ships is the right one, and that the cartridge port is interesting rather than
practical.

## What remains unverified

- **No handshake has ever run.** Everything above is build-time, symbol-level,
  and operation-count verification. Whether mbedTLS 3.6 completes a TLS 1.3
  handshake against a real server on this core is unknown, and cannot be known
  while `Connect()` refuses.
- **Instruction counts are measured; cycle counts are not.** `tools/nios2-sim`
  executes the real code and counts instructions, and validates itself against
  host-computed P-256 results. It is not cycle-accurate: cycles-per-instruction
  is an input, which is why every table gives both a 1-CPI floor and 6 CPI.
- **The simulator models the Nios II/e's absence of caches by having none.** That
  is right for this core and wrong for the /f, so the 1-CPI column is a bound
  rather than a prediction of what an /f would do — cache misses on a real
  pipelined core would push it above 1 CPI.
- **The hardware-multiply figures assume nothing else changes.** Only the
  compiler flag differs; a real Qsys change might also alter clock frequency or
  memory latency, in either direction.
- **Entropy quality is unverified**, and cannot be verified off-hardware. Only
  the accounting is tested.
- **Nothing has been flashed.** No image has been written to any device.
