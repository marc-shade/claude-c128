/* nios2sim - a Nios II R1 instruction-set simulator, built to turn computed
 * instruction counts into measured ones.
 *
 * Why this exists: the cost of a TLS handshake on the Ultimate II+'s Nios II/e
 * was worked out by hand - static disassembly of __muldi3/__mulsi3 plus an
 * assumption about how many times the shift-add loop iterates. That is a
 * derivation, not a measurement, and QEMU dropped the nios2 target so there was
 * nothing to check it against. This runs the real code and counts.
 *
 * Scope: bare-metal user code only. No MMU, no interrupts beyond the registers
 * needed to link, no peripherals. Two magic addresses stand in for I/O.
 *
 * Every instruction encoding comes from nios2_opcodes.h, which is generated
 * from binutils' own tables - see gen_opcodes in the build script. Semantics
 * are hand-written, which is why validate.sh checks the simulator against
 * host-computed crypto results rather than trusting it.
 *
 * Any opcode this does not implement aborts. A simulator that silently skips
 * instructions would produce a plausible, wrong number.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdarg.h>

#include "nios2_opcodes.h"

/* ------------------------------------------------------------------ memory */

#define MEM_SIZE   (64u * 1024 * 1024)
#define MMIO_PUTC  0x10000000u      /* store a byte here -> stdout          */
#define MMIO_HALT  0x10000004u      /* store here -> stop, value = exit code */
#define MMIO_ICNT  0x10000008u      /* load here -> instructions so far      */

static uint8_t  *mem;
static uint32_t  reg[32];
static uint32_t  pc;
static uint32_t  ctl[32];
static int       halted, exit_code;

static uint64_t  icount;
static uint64_t  icount_by_op[64];      /* indexed by OP field   */
static uint64_t  icount_by_opx[64];     /* indexed by OPX field  */

/* Counters that can be sampled by the guest through MMIO_ICNT, so a benchmark
 * can bracket a region of interest without the host guessing where it is. */

static void fatal(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "\nnios2sim: ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n  pc=0x%08x icount=%" PRIu64 "\n", pc, icount);
    va_end(ap);
    exit(2);
}

static inline uint32_t ld32(uint32_t a)
{
    if (a == MMIO_ICNT) return (uint32_t) icount;
    if (a + 4 > MEM_SIZE) fatal("load32 out of range at 0x%08x", a);
    uint32_t v;
    memcpy(&v, mem + a, 4);
    return v;
}
static inline uint16_t ld16(uint32_t a)
{
    if (a + 2 > MEM_SIZE) fatal("load16 out of range at 0x%08x", a);
    uint16_t v;
    memcpy(&v, mem + a, 2);
    return v;
}
static inline uint8_t ld8(uint32_t a)
{
    if (a >= MEM_SIZE) fatal("load8 out of range at 0x%08x", a);
    return mem[a];
}

static inline void st32(uint32_t a, uint32_t v)
{
    if (a == MMIO_HALT) { halted = 1; exit_code = (int) v; return; }
    if (a == MMIO_PUTC) { fputc((int)(v & 0xff), stdout); return; }
    if (a + 4 > MEM_SIZE) fatal("store32 out of range at 0x%08x", a);
    memcpy(mem + a, &v, 4);
}
static inline void st16(uint32_t a, uint16_t v)
{
    if (a + 2 > MEM_SIZE) fatal("store16 out of range at 0x%08x", a);
    memcpy(mem + a, &v, 2);
}
static inline void st8(uint32_t a, uint8_t v)
{
    if (a == MMIO_PUTC) { fputc(v, stdout); return; }
    if (a >= MEM_SIZE) fatal("store8 out of range at 0x%08x", a);
    mem[a] = v;
}

/* --------------------------------------------------------------- ELF loader */

static uint32_t load_elf(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(2); }

    uint8_t eh[52];
    if (fread(eh, 1, sizeof eh, f) != sizeof eh) fatal("short ELF header");
    if (memcmp(eh, "\177ELF", 4) != 0)           fatal("not an ELF file");
    if (eh[4] != 1)                              fatal("not ELF32");
    if (eh[5] != 1)                              fatal("not little-endian");

    uint16_t machine;  memcpy(&machine, eh + 18, 2);
    /* EM_ALTERA_NIOS2 == 113 */
    if (machine != 113) fatal("wrong e_machine %u (expected 113, nios2)", machine);

    uint32_t entry, phoff;
    uint16_t phentsize, phnum;
    memcpy(&entry,     eh + 24, 4);
    memcpy(&phoff,     eh + 28, 4);
    memcpy(&phentsize, eh + 42, 2);
    memcpy(&phnum,     eh + 44, 2);

    for (uint16_t i = 0; i < phnum; i++) {
        uint8_t ph[32];
        if (fseek(f, (long)(phoff + (uint32_t)i * phentsize), SEEK_SET) != 0)
            fatal("seek to program header %u failed", i);
        if (fread(ph, 1, sizeof ph, f) != sizeof ph) fatal("short program header");

        uint32_t type, off, vaddr, filesz, memsz;
        memcpy(&type,   ph +  0, 4);
        memcpy(&off,    ph +  4, 4);
        memcpy(&vaddr,  ph +  8, 4);
        memcpy(&filesz, ph + 16, 4);
        memcpy(&memsz,  ph + 20, 4);
        if (type != 1) continue;                       /* PT_LOAD only */

        if ((uint64_t) vaddr + memsz > MEM_SIZE)
            fatal("segment at 0x%08x size %u exceeds %u MB of simulated RAM",
                  vaddr, memsz, MEM_SIZE >> 20);

        if (fseek(f, (long) off, SEEK_SET) != 0) fatal("seek to segment failed");
        if (filesz && fread(mem + vaddr, 1, filesz, f) != filesz)
            fatal("short read on segment at 0x%08x", vaddr);
        if (memsz > filesz) memset(mem + vaddr + filesz, 0, memsz - filesz);
    }
    fclose(f);
    return entry;
}

/* ------------------------------------------------------------------ execute */

#define RA   ((iw >> 27) & 0x1f)
#define RB   ((iw >> 22) & 0x1f)
#define RC   ((iw >> 17) & 0x1f)
#define OPX  ((iw >> 11) & 0x3f)
#define IMM5 ((iw >> 6)  & 0x1f)
#define IMM16 ((uint32_t)((iw >> 6) & 0xffff))
#define SIMM16 ((int32_t)(int16_t)IMM16)
#define IMM26 ((iw >> 6) & 0x3ffffff)

static inline void wr(unsigned r, uint32_t v) { if (r) reg[r] = v; }

static void run(void)
{
    while (!halted) {
        if (pc & 3) fatal("misaligned pc");
        uint32_t iw = ld32(pc);
        uint32_t next = pc + 4;
        unsigned op = iw & 0x3f;

        icount++;
        icount_by_op[op]++;

        switch (op) {

        /* ---- I-type arithmetic / logic ---- */
        case OP_ADDI:    wr(RB, reg[RA] + (uint32_t) SIMM16); break;
        case OP_MULI:    wr(RB, (uint32_t)((int32_t) reg[RA] * SIMM16)); break;
        case OP_ANDI:    wr(RB, reg[RA] & IMM16); break;
        case OP_ORI:     wr(RB, reg[RA] | IMM16); break;
        case OP_XORI:    wr(RB, reg[RA] ^ IMM16); break;
        case OP_ANDHI:   wr(RB, reg[RA] & (IMM16 << 16)); break;
        case OP_ORHI:    wr(RB, reg[RA] | (IMM16 << 16)); break;
        case OP_XORHI:   wr(RB, reg[RA] ^ (IMM16 << 16)); break;

        /* Signed immediate compares. */
        case OP_CMPGEI:  wr(RB, (int32_t) reg[RA] >= SIMM16); break;
        case OP_CMPLTI:  wr(RB, (int32_t) reg[RA] <  SIMM16); break;
        case OP_CMPNEI:  wr(RB, reg[RA] != (uint32_t) SIMM16); break;
        case OP_CMPEQI:  wr(RB, reg[RA] == (uint32_t) SIMM16); break;
        /* Unsigned immediate compares: the immediate is zero-extended. */
        case OP_CMPGEUI: wr(RB, reg[RA] >= IMM16); break;
        case OP_CMPLTUI: wr(RB, reg[RA] <  IMM16); break;

        /* ---- loads and stores (the io variants behave identically here) ---- */
        case OP_LDW: case OP_LDWIO:
            wr(RB, ld32(reg[RA] + (uint32_t) SIMM16)); break;
        case OP_LDH: case OP_LDHIO:
            wr(RB, (uint32_t)(int32_t)(int16_t) ld16(reg[RA] + (uint32_t) SIMM16)); break;
        case OP_LDHU: case OP_LDHUIO:
            wr(RB, ld16(reg[RA] + (uint32_t) SIMM16)); break;
        case OP_LDB: case OP_LDBIO:
            wr(RB, (uint32_t)(int32_t)(int8_t) ld8(reg[RA] + (uint32_t) SIMM16)); break;
        case OP_LDBU: case OP_LDBUIO:
            wr(RB, ld8(reg[RA] + (uint32_t) SIMM16)); break;
        case OP_STW: case OP_STWIO:
            st32(reg[RA] + (uint32_t) SIMM16, reg[RB]); break;
        case OP_STH: case OP_STHIO:
            st16(reg[RA] + (uint32_t) SIMM16, (uint16_t) reg[RB]); break;
        case OP_STB: case OP_STBIO:
            st8(reg[RA] + (uint32_t) SIMM16, (uint8_t) reg[RB]); break;

        /* ---- branches: offset is relative to the following instruction ---- */
        case OP_BR:                                   next = pc + 4 + SIMM16; break;
        case OP_BEQ:  if (reg[RA] == reg[RB])         next = pc + 4 + SIMM16; break;
        case OP_BNE:  if (reg[RA] != reg[RB])         next = pc + 4 + SIMM16; break;
        case OP_BGE:
            if ((int32_t) reg[RA] >= (int32_t) reg[RB]) next = pc + 4 + SIMM16;
            break;
        case OP_BLT:
            if ((int32_t) reg[RA] < (int32_t) reg[RB]) next = pc + 4 + SIMM16;
            break;
        case OP_BGEU: if (reg[RA] >= reg[RB])         next = pc + 4 + SIMM16; break;
        case OP_BLTU: if (reg[RA] <  reg[RB])         next = pc + 4 + SIMM16; break;

        /* ---- J-type: target is within the current 256 MB region ---- */
        case OP_CALL:
            reg[31] = pc + 4;
            next = ((pc + 4) & 0xf0000000u) | (IMM26 << 2);
            break;
        case OP_JMPI:
            next = ((pc + 4) & 0xf0000000u) | (IMM26 << 2);
            break;

        /* ---- cache and prefetch hints: no cache here, so no-ops ---- */
        case OP_FLUSHD: case OP_FLUSHDA: case OP_INITD: case OP_INITDA:
            break;

        case OP_CUSTOM:
            fatal("custom instruction 0x%08x - this design has none", iw);
            break;

        case OP_RDPRS:
            fatal("rdprs: shadow register sets are not modelled");
            break;

        /* ---- R-type ---- */
        case OP_RTYPE: {
            unsigned opx = OPX;
            icount_by_opx[opx]++;
            switch (opx) {
            case OPX_ADD:  wr(RC, reg[RA] + reg[RB]); break;
            case OPX_SUB:  wr(RC, reg[RA] - reg[RB]); break;
            case OPX_MUL:  wr(RC, (uint32_t)(reg[RA] * reg[RB])); break;
            case OPX_MULXUU:
                wr(RC, (uint32_t)(((uint64_t) reg[RA] * (uint64_t) reg[RB]) >> 32));
                break;
            case OPX_MULXSS:
                wr(RC, (uint32_t)(((int64_t)(int32_t) reg[RA] *
                                   (int64_t)(int32_t) reg[RB]) >> 32));
                break;
            case OPX_MULXSU:
                wr(RC, (uint32_t)(((int64_t)(int32_t) reg[RA] *
                                   (int64_t)(uint64_t) reg[RB]) >> 32));
                break;
            case OPX_DIV:
                if (reg[RB] == 0) fatal("integer divide by zero");
                wr(RC, (uint32_t)((int32_t) reg[RA] / (int32_t) reg[RB]));
                break;
            case OPX_DIVU:
                if (reg[RB] == 0) fatal("integer divide by zero");
                wr(RC, reg[RA] / reg[RB]);
                break;

            case OPX_AND:  wr(RC, reg[RA] & reg[RB]); break;
            case OPX_OR:   wr(RC, reg[RA] | reg[RB]); break;
            case OPX_XOR:  wr(RC, reg[RA] ^ reg[RB]); break;
            case OPX_NOR:  wr(RC, ~(reg[RA] | reg[RB])); break;

            case OPX_SLL:  wr(RC, reg[RA] << (reg[RB] & 31)); break;
            case OPX_SRL:  wr(RC, reg[RA] >> (reg[RB] & 31)); break;
            case OPX_SRA:  wr(RC, (uint32_t)((int32_t) reg[RA] >> (reg[RB] & 31))); break;
            case OPX_SLLI: wr(RC, reg[RA] << IMM5); break;
            case OPX_SRLI: wr(RC, reg[RA] >> IMM5); break;
            case OPX_SRAI: wr(RC, (uint32_t)((int32_t) reg[RA] >> IMM5)); break;
            case OPX_ROL:  { unsigned s = reg[RB] & 31;
                             wr(RC, s ? (reg[RA] << s) | (reg[RA] >> (32 - s)) : reg[RA]); }
                           break;
            case OPX_ROLI: { unsigned s = IMM5;
                             wr(RC, s ? (reg[RA] << s) | (reg[RA] >> (32 - s)) : reg[RA]); }
                           break;
            case OPX_ROR:  { unsigned s = reg[RB] & 31;
                             wr(RC, s ? (reg[RA] >> s) | (reg[RA] << (32 - s)) : reg[RA]); }
                           break;

            case OPX_CMPEQ:  wr(RC, reg[RA] == reg[RB]); break;
            case OPX_CMPNE:  wr(RC, reg[RA] != reg[RB]); break;
            case OPX_CMPGE:  wr(RC, (int32_t) reg[RA] >= (int32_t) reg[RB]); break;
            case OPX_CMPLT:  wr(RC, (int32_t) reg[RA] <  (int32_t) reg[RB]); break;
            case OPX_CMPGEU: wr(RC, reg[RA] >= reg[RB]); break;
            case OPX_CMPLTU: wr(RC, reg[RA] <  reg[RB]); break;

            case OPX_JMP:    next = reg[RA]; break;
            case OPX_CALLR:  reg[31] = pc + 4; next = reg[RA]; break;
            case OPX_RET:    next = reg[31]; break;
            case OPX_NEXTPC: wr(RC, pc + 4); break;

            case OPX_ERET:   ctl[0] = ctl[1]; next = reg[29]; break;
            case OPX_BRET:   ctl[0] = ctl[2]; next = reg[30]; break;

            case OPX_RDCTL:  wr(RC, ctl[IMM5 & 31]); break;
            case OPX_WRCTL:  ctl[IMM5 & 31] = reg[RA]; break;

            /* No caches, no pipeline to flush, no shadow registers. */
            case OPX_FLUSHI: case OPX_INITI: case OPX_FLUSHP: case OPX_SYNC:
                break;
            case OPX_WRPRS:
                fatal("wrprs: shadow register sets are not modelled");
                break;

            case OPX_TRAP:
                fatal("trap instruction - no exception handler is modelled");
                break;
            case OPX_BREAK:
                fprintf(stderr, "\nnios2sim: break at pc=0x%08x\n", pc);
                halted = 1; exit_code = 3;
                break;

            default:
                fatal("unimplemented R-type opx 0x%02x (iw=0x%08x)", opx, iw);
            }
            break;
        }

        default:
            fatal("unimplemented op 0x%02x (iw=0x%08x)", op, iw);
        }

        pc = next;
    }
}

/* --------------------------------------------------------------------- main */

int main(int argc, char **argv)
{
    const char *elf = NULL;
    uint32_t sp = MEM_SIZE - 16;
    int histogram = 0;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--histogram")) histogram = 1;
        else if (!strcmp(argv[i], "--sp") && i + 1 < argc) sp = strtoul(argv[++i], NULL, 0);
        else if (argv[i][0] == '-') { fprintf(stderr, "unknown option %s\n", argv[i]); return 2; }
        else elf = argv[i];
    }
    if (!elf) {
        fprintf(stderr,
            "usage: nios2sim [--histogram] [--sp ADDR] program.elf\n"
            "  writes to 0x%08x go to stdout; a store to 0x%08x halts with that exit code\n"
            "  a load from 0x%08x yields the instruction count so far\n",
            MMIO_PUTC, MMIO_HALT, MMIO_ICNT);
        return 2;
    }

    mem = calloc(MEM_SIZE, 1);
    if (!mem) { fprintf(stderr, "cannot allocate %u MB\n", MEM_SIZE >> 20); return 2; }

    pc = load_elf(elf);
    reg[27] = sp;                 /* sp */
    reg[28] = sp;                 /* fp */

    run();

    fflush(stdout);
    fprintf(stderr, "\n[nios2sim] instructions executed: %" PRIu64 "\n", icount);

    if (histogram) {
        fprintf(stderr, "[nios2sim] top OP fields:\n");
        for (int pass = 0; pass < 12; pass++) {
            int best = -1; uint64_t bv = 0;
            for (int i = 0; i < 64; i++)
                if (icount_by_op[i] > bv) { bv = icount_by_op[i]; best = i; }
            if (best < 0) break;
            fprintf(stderr, "    op 0x%02x  %12" PRIu64 "  %5.1f%%\n",
                    best, bv, 100.0 * (double) bv / (double) icount);
            icount_by_op[best] = 0;
        }
        fprintf(stderr, "[nios2sim] top OPX fields (R-type):\n");
        for (int pass = 0; pass < 12; pass++) {
            int best = -1; uint64_t bv = 0;
            for (int i = 0; i < 64; i++)
                if (icount_by_opx[i] > bv) { bv = icount_by_opx[i]; best = i; }
            if (best < 0) break;
            fprintf(stderr, "    opx 0x%02x %12" PRIu64 "  %5.1f%%\n",
                    best, bv, 100.0 * (double) bv / (double) icount);
            icount_by_opx[best] = 0;
        }
    }
    return exit_code;
}
