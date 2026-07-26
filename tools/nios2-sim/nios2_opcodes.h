/* Generated from binutils-2.43 include/opcode/nios2r1.h -- do not hand-edit.
   Every encoding here came from the assembler's own tables. Assembler
   pseudo-instructions share an encoding with the real instruction they
   expand to (movui/ori, cmplei/cmplti, ble/bge...), so all names are
   emitted as aliases rather than picking one arbitrarily. */
#ifndef NIOS2_OPCODES_H
#define NIOS2_OPCODES_H

/* OP field (bits 5:0), non-R-type */
#define OP_CALL 0x00
#define OP_JMPI 0x01
#define OP_LDBU 0x03
#define OP_ADDI 0x04
#define OP_MOVI 0x04
#define OP_SUBI 0x04
#define OP_STB 0x05
#define OP_BR 0x06
#define OP_LDB 0x07
#define OP_CMPGEI 0x08
#define OP_CMPGTI 0x08
#define OP_LDHU 0x0b
#define OP_ANDI 0x0c
#define OP_STH 0x0d
#define OP_BGE 0x0e
#define OP_BLE 0x0e
#define OP_LDH 0x0f
#define OP_CMPLEI 0x10
#define OP_CMPLTI 0x10
#define OP_INITDA 0x13
#define OP_MOVUI 0x14
#define OP_ORI 0x14
#define OP_STW 0x15
#define OP_BGT 0x16
#define OP_BLT 0x16
#define OP_LDW 0x17
#define OP_CMPNEI 0x18
#define OP_FLUSHDA 0x1b
#define OP_XORI 0x1c
#define OP_BNE 0x1e
#define OP_CMPEQI 0x20
#define OP_LDBUIO 0x23
#define OP_MULI 0x24
#define OP_STBIO 0x25
#define OP_BEQ 0x26
#define OP_LDBIO 0x27
#define OP_CMPGEUI 0x28
#define OP_CMPGTUI 0x28
#define OP_LDHUIO 0x2b
#define OP_ANDHI 0x2c
#define OP_STHIO 0x2d
#define OP_BGEU 0x2e
#define OP_BLEU 0x2e
#define OP_LDHIO 0x2f
#define OP_CMPLEUI 0x30
#define OP_CMPLTUI 0x30
#define OP_CUSTOM 0x32
#define OP_INITD 0x33
#define OP_MOVHI 0x34
#define OP_ORHI 0x34
#define OP_STWIO 0x35
#define OP_BGTU 0x36
#define OP_BLTU 0x36
#define OP_LDWIO 0x37
#define OP_RDPRS 0x38
#define OP_FLUSHD 0x3b
#define OP_XORHI 0x3c

/* OPX field (bits 16:11), when OP == 0x3a */
#define OPX_ERET 0x01
#define OPX_ROLI 0x02
#define OPX_ROL 0x03
#define OPX_FLUSHP 0x04
#define OPX_RET 0x05
#define OPX_NOR 0x06
#define OPX_MULXUU 0x07
#define OPX_CMPGE 0x08
#define OPX_CMPLE 0x08
#define OPX_BRET 0x09
#define OPX_ROR 0x0b
#define OPX_FLUSHI 0x0c
#define OPX_JMP 0x0d
#define OPX_AND 0x0e
#define OPX_CMPGT 0x10
#define OPX_CMPLT 0x10
#define OPX_SLLI 0x12
#define OPX_SLL 0x13
#define OPX_WRPRS 0x14
#define OPX_OR 0x16
#define OPX_MULXSU 0x17
#define OPX_CMPNE 0x18
#define OPX_SRLI 0x1a
#define OPX_SRL 0x1b
#define OPX_NEXTPC 0x1c
#define OPX_CALLR 0x1d
#define OPX_XOR 0x1e
#define OPX_MULXSS 0x1f
#define OPX_CMPEQ 0x20
#define OPX_DIVU 0x24
#define OPX_DIV 0x25
#define OPX_RDCTL 0x26
#define OPX_MUL 0x27
#define OPX_CMPGEU 0x28
#define OPX_CMPLEU 0x28
#define OPX_INITI 0x29
#define OPX_TRAP 0x2d
#define OPX_WRCTL 0x2e
#define OPX_CMPGTU 0x30
#define OPX_CMPLTU 0x30
#define OPX_ADD 0x31
#define OPX_MOV 0x31
#define OPX_NOP 0x31
#define OPX_BREAK 0x34
#define OPX_SYNC 0x36
#define OPX_SUB 0x39
#define OPX_SRAI 0x3a
#define OPX_SRA 0x3b

#define OP_RTYPE 0x3a
#endif
