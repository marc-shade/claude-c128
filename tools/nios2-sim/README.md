# nios2sim

A Nios II R1 instruction-set simulator, written because a number needed checking
and there was nothing to check it with. QEMU removed its nios2 target, so on a
current machine there is no way to run Nios II code at all.

It earned its keep immediately: it showed that a figure derived from static
disassembly was wrong by 3.5×, and that a predicted 59× speedup was really 5.1×.
Both errors were in the optimistic direction. See `docs/NATIVE-PORT.md`.

## What it is

- Nios II R1, 32 registers, flat 64 MB of memory, little-endian ELF loader
- Bare-metal user code only: no MMU, no interrupt controller, no peripherals
- Three MMIO addresses stand in for I/O:

  | address | direction | meaning |
  |---|---|---|
  | `0x10000000` | store byte | write to stdout |
  | `0x10000004` | store word | halt, value is the exit code |
  | `0x10000008` | load word | instructions executed so far |

  The last one lets a benchmark bracket its own phases instead of the host
  guessing where they start.

- Roughly 265 M simulated instructions per second, so a 5-billion-instruction
  P-256 run finishes in about 20 seconds.

**Any opcode it does not implement aborts.** A simulator that silently skipped
instructions would still print a number, and the number would be wrong.

## Trusting it

Instruction encodings are not hand-transcribed. `nios2_opcodes.h` is generated
from binutils' own `nios2r1.h` tables via `gen_opcodes.c` — 105 of the 106 R1
mnemonics resolve, the exception being `movia`, which is an assembler macro.
Pseudo-instructions that share an encoding with a real one (`movui`/`ori`,
`cmplei`/`cmplti`, `ble`/`bge`) are emitted as aliases rather than one being
picked arbitrarily.

Semantics are hand-written, so they are checked two ways:

    make check     # 45 cases: the same C compiled for host and target must agree
    make bench     # P-256 shared secret must match the host byte for byte

`make check` covers signed and unsigned arithmetic at the wrap boundaries,
variable and constant shifts, arithmetic vs logical right shift, 64-bit
multiply/divide/shift through the libgcc helpers, sign and zero extension,
mixed-sign comparisons, and byte/halfword/word memory traffic.

`make bench` is the stronger check. A P-256 ECDH shared secret depends on every
carry in roughly 585 million instructions; if one of them were wrong the answer
would differ. It matches, and so does the reverse agreement, an ECDSA verify, and
an ECDSA *rejection* of a tampered digest. The hardware-multiply build produces
the same secret, which validates `mul`/`mulxuu` as well.

What that does **not** establish: this is not a cycle-accurate model. It counts
instructions. Cycles-per-instruction for the Nios II/e is an input you supply,
not something measured here.

## Usage

    make
    ./nios2sim [--histogram] [--sp ADDR] program.elf

Programs link against `rt/` — `start.S` sets up sp/fp/gp and zeroes bss,
`syscalls.c` provides the handful of calls newlib needs for `printf` and
`malloc`, and `link.ld` lays out flat memory with `_gp` defined (nios2 addresses
small data gp-relative, and the link fails without it).

Building target code needs a `nios2-elf` toolchain, which Intel no longer ships;
GCC 14 can still be built for it with `--enable-obsolete`, and GCC 15 dropped the
target entirely. Both libgcc and newlib must be compiled with
`-mno-hw-mul -mno-hw-div -mno-hw-mulx` for a core that lacks the multiplier, or
`libc.a` itself carries instructions the CPU cannot execute.

    make check CROSS=/path/to/bin/nios2-elf-
    make bench CROSS=/path/to/bin/nios2-elf- MBEDTLS_DIR=/path/to/mbedtls

## Scope

Written for one measurement, so it stops where that stopped. Not implemented:
custom instructions, shadow register sets (`rdprs`/`wrprs`), the trap
instruction, and exception or interrupt delivery. Caches are absent rather than
modelled, which is accurate for the Nios II/e — it has none — and wrong for the
/f. All of these abort rather than pretending.
