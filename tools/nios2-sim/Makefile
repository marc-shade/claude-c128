# nios2sim - a Nios II R1 instruction-set simulator.
#
#   make            build the simulator
#   make check      validate it against the host compiler (needs the cross toolchain)
#   make bench      measure the P-256 handshake cost (needs MBEDTLS_DIR too)
#
# The cross toolchain is not on PATH by default; point CROSS at it:
#   make check CROSS=$HOME/code/nios2-toolchain/install/bin/nios2-elf-

CC      ?= gcc
CFLAGS  ?= -O2 -Wall -Wextra
CROSS   ?= nios2-elf-
MBEDTLS_DIR ?=

# newlib and libgcc for this target must be built without hardware multiply,
# or libc itself carries instructions the Nios II/e cannot execute.
NOHW  := -mno-hw-mul -mno-hw-div -mno-hw-mulx
HW    := -mhw-mul -mhw-mulx -mno-hw-div
# -G0 disables small-data addressing. The crypto build outgrows the +/-32 KB gp
# window otherwise, and both builds must use the same setting to be comparable.
TFLAGS := -O2 -G0 -ffreestanding -nostartfiles -T rt/link.ld -I rt -I tests
TRT    := rt/start.S rt/syscalls.c

MB_SRCS := bignum.c bignum_core.c ecp.c ecp_curves.c ecdh.c ecdsa.c \
           asn1parse.c asn1write.c sha256.c md.c platform.c platform_util.c \
           constant_time.c

.PHONY: all check bench clean opcodes

all: nios2sim

nios2sim: nios2sim.c nios2_opcodes.h
	$(CC) $(CFLAGS) -o $@ $<

# Regenerate the decode constants from binutils' own opcode tables. Requires a
# binutils source tree; the checked-in header is the output of this.
opcodes: gen_opcodes.c
	@test -n "$(BINUTILS_SRC)" || { echo "set BINUTILS_SRC=/path/to/binutils-x.y"; exit 1; }
	$(CC) -I $(BINUTILS_SRC)/include -o /tmp/gen_opcodes $<
	/tmp/gen_opcodes > /tmp/r1_table.txt
	@echo "resolved $$(wc -l < /tmp/r1_table.txt) encodings; regenerate the header from this"

# Compile the same C for host and target, run both, and diff. A mismatch means
# the simulator and a real compiler disagree about what the C means.
check: nios2sim
	@$(CC) -O2 -o /tmp/isa_host tests/isa_test.c
	@$(CROSS)gcc $(TFLAGS) $(NOHW) $(TRT) tests/isa_test.c -o /tmp/isa.elf -lc -lgcc 2>/dev/null
	@/tmp/isa_host > /tmp/isa_host.txt
	@./nios2sim /tmp/isa.elf 2>/dev/null > /tmp/isa_sim.txt
	@if diff -u /tmp/isa_host.txt /tmp/isa_sim.txt; then \
	   echo "PASS  $$(wc -l < /tmp/isa_host.txt) cases match the host compiler"; \
	 else echo "FAIL  simulator semantics differ from the host"; exit 1; fi

# Measure the public-key cost of a handshake, with and without hardware
# multiply. Validation is built in: both builds must produce the same P-256
# shared secret as the host, or the numbers mean nothing.
bench: nios2sim
	@test -n "$(MBEDTLS_DIR)" || { echo "set MBEDTLS_DIR=/path/to/mbedtls"; exit 1; }
	@$(eval LIB := $(addprefix $(MBEDTLS_DIR)/library/,$(MB_SRCS)))
	@$(CC) -O2 -w -DMBEDTLS_CONFIG_FILE='"bench_config.h"' \
	   -I $(MBEDTLS_DIR)/include -I tests tests/crypto_bench.c $(LIB) -o /tmp/cb_host
	@/tmp/cb_host | grep -v '^$$' > /tmp/cb_host.txt
	@for v in nohw hw; do \
	   if [ $$v = nohw ]; then M="$(NOHW)"; else M="$(HW)"; fi; \
	   $(CROSS)gcc $(TFLAGS) $$M -DNIOS2_SIM \
	     -DMBEDTLS_CONFIG_FILE='"bench_config.h"' -I $(MBEDTLS_DIR)/include \
	     $(TRT) tests/crypto_bench.c $(LIB) -o /tmp/cb_$$v.elf -lc -lgcc 2>/dev/null; \
	   echo "=== $$v ==="; \
	   ./nios2sim /tmp/cb_$$v.elf 2>&1 | grep -E '^#|instructions executed'; \
	   ./nios2sim /tmp/cb_$$v.elf 2>/dev/null | grep -vE '^#' | grep -v '^$$' > /tmp/cb_$$v.txt; \
	   if diff -q /tmp/cb_host.txt /tmp/cb_$$v.txt >/dev/null; then \
	     echo "    results match the host - counts are trustworthy"; \
	   else echo "    RESULTS DIFFER FROM HOST - do not trust these counts"; exit 1; fi; \
	 done

clean:
	rm -f nios2sim
