#include <stdio.h>
#include "opcode/nios2r1.h"
int main(void){
#ifdef MATCH_R1_ADD
  printf("%s %08lx %08lx\n", "add", (unsigned long)MATCH_R1_ADD, (unsigned long)MASK_R1_ADD);
#endif
#ifdef MATCH_R1_ADDI
  printf("%s %08lx %08lx\n", "addi", (unsigned long)MATCH_R1_ADDI, (unsigned long)MASK_R1_ADDI);
#endif
#ifdef MATCH_R1_AND
  printf("%s %08lx %08lx\n", "and", (unsigned long)MATCH_R1_AND, (unsigned long)MASK_R1_AND);
#endif
#ifdef MATCH_R1_ANDHI
  printf("%s %08lx %08lx\n", "andhi", (unsigned long)MATCH_R1_ANDHI, (unsigned long)MASK_R1_ANDHI);
#endif
#ifdef MATCH_R1_ANDI
  printf("%s %08lx %08lx\n", "andi", (unsigned long)MATCH_R1_ANDI, (unsigned long)MASK_R1_ANDI);
#endif
#ifdef MATCH_R1_BEQ
  printf("%s %08lx %08lx\n", "beq", (unsigned long)MATCH_R1_BEQ, (unsigned long)MASK_R1_BEQ);
#endif
#ifdef MATCH_R1_BGE
  printf("%s %08lx %08lx\n", "bge", (unsigned long)MATCH_R1_BGE, (unsigned long)MASK_R1_BGE);
#endif
#ifdef MATCH_R1_BGEU
  printf("%s %08lx %08lx\n", "bgeu", (unsigned long)MATCH_R1_BGEU, (unsigned long)MASK_R1_BGEU);
#endif
#ifdef MATCH_R1_BGT
  printf("%s %08lx %08lx\n", "bgt", (unsigned long)MATCH_R1_BGT, (unsigned long)MASK_R1_BGT);
#endif
#ifdef MATCH_R1_BGTU
  printf("%s %08lx %08lx\n", "bgtu", (unsigned long)MATCH_R1_BGTU, (unsigned long)MASK_R1_BGTU);
#endif
#ifdef MATCH_R1_BLE
  printf("%s %08lx %08lx\n", "ble", (unsigned long)MATCH_R1_BLE, (unsigned long)MASK_R1_BLE);
#endif
#ifdef MATCH_R1_BLEU
  printf("%s %08lx %08lx\n", "bleu", (unsigned long)MATCH_R1_BLEU, (unsigned long)MASK_R1_BLEU);
#endif
#ifdef MATCH_R1_BLT
  printf("%s %08lx %08lx\n", "blt", (unsigned long)MATCH_R1_BLT, (unsigned long)MASK_R1_BLT);
#endif
#ifdef MATCH_R1_BLTU
  printf("%s %08lx %08lx\n", "bltu", (unsigned long)MATCH_R1_BLTU, (unsigned long)MASK_R1_BLTU);
#endif
#ifdef MATCH_R1_BNE
  printf("%s %08lx %08lx\n", "bne", (unsigned long)MATCH_R1_BNE, (unsigned long)MASK_R1_BNE);
#endif
#ifdef MATCH_R1_BR
  printf("%s %08lx %08lx\n", "br", (unsigned long)MATCH_R1_BR, (unsigned long)MASK_R1_BR);
#endif
#ifdef MATCH_R1_BREAK
  printf("%s %08lx %08lx\n", "break", (unsigned long)MATCH_R1_BREAK, (unsigned long)MASK_R1_BREAK);
#endif
#ifdef MATCH_R1_BRET
  printf("%s %08lx %08lx\n", "bret", (unsigned long)MATCH_R1_BRET, (unsigned long)MASK_R1_BRET);
#endif
#ifdef MATCH_R1_CALL
  printf("%s %08lx %08lx\n", "call", (unsigned long)MATCH_R1_CALL, (unsigned long)MASK_R1_CALL);
#endif
#ifdef MATCH_R1_CALLR
  printf("%s %08lx %08lx\n", "callr", (unsigned long)MATCH_R1_CALLR, (unsigned long)MASK_R1_CALLR);
#endif
#ifdef MATCH_R1_CMPEQ
  printf("%s %08lx %08lx\n", "cmpeq", (unsigned long)MATCH_R1_CMPEQ, (unsigned long)MASK_R1_CMPEQ);
#endif
#ifdef MATCH_R1_CMPEQI
  printf("%s %08lx %08lx\n", "cmpeqi", (unsigned long)MATCH_R1_CMPEQI, (unsigned long)MASK_R1_CMPEQI);
#endif
#ifdef MATCH_R1_CMPGE
  printf("%s %08lx %08lx\n", "cmpge", (unsigned long)MATCH_R1_CMPGE, (unsigned long)MASK_R1_CMPGE);
#endif
#ifdef MATCH_R1_CMPGEI
  printf("%s %08lx %08lx\n", "cmpgei", (unsigned long)MATCH_R1_CMPGEI, (unsigned long)MASK_R1_CMPGEI);
#endif
#ifdef MATCH_R1_CMPGEU
  printf("%s %08lx %08lx\n", "cmpgeu", (unsigned long)MATCH_R1_CMPGEU, (unsigned long)MASK_R1_CMPGEU);
#endif
#ifdef MATCH_R1_CMPGEUI
  printf("%s %08lx %08lx\n", "cmpgeui", (unsigned long)MATCH_R1_CMPGEUI, (unsigned long)MASK_R1_CMPGEUI);
#endif
#ifdef MATCH_R1_CMPGT
  printf("%s %08lx %08lx\n", "cmpgt", (unsigned long)MATCH_R1_CMPGT, (unsigned long)MASK_R1_CMPGT);
#endif
#ifdef MATCH_R1_CMPGTI
  printf("%s %08lx %08lx\n", "cmpgti", (unsigned long)MATCH_R1_CMPGTI, (unsigned long)MASK_R1_CMPGTI);
#endif
#ifdef MATCH_R1_CMPGTU
  printf("%s %08lx %08lx\n", "cmpgtu", (unsigned long)MATCH_R1_CMPGTU, (unsigned long)MASK_R1_CMPGTU);
#endif
#ifdef MATCH_R1_CMPGTUI
  printf("%s %08lx %08lx\n", "cmpgtui", (unsigned long)MATCH_R1_CMPGTUI, (unsigned long)MASK_R1_CMPGTUI);
#endif
#ifdef MATCH_R1_CMPLE
  printf("%s %08lx %08lx\n", "cmple", (unsigned long)MATCH_R1_CMPLE, (unsigned long)MASK_R1_CMPLE);
#endif
#ifdef MATCH_R1_CMPLEI
  printf("%s %08lx %08lx\n", "cmplei", (unsigned long)MATCH_R1_CMPLEI, (unsigned long)MASK_R1_CMPLEI);
#endif
#ifdef MATCH_R1_CMPLEU
  printf("%s %08lx %08lx\n", "cmpleu", (unsigned long)MATCH_R1_CMPLEU, (unsigned long)MASK_R1_CMPLEU);
#endif
#ifdef MATCH_R1_CMPLEUI
  printf("%s %08lx %08lx\n", "cmpleui", (unsigned long)MATCH_R1_CMPLEUI, (unsigned long)MASK_R1_CMPLEUI);
#endif
#ifdef MATCH_R1_CMPLT
  printf("%s %08lx %08lx\n", "cmplt", (unsigned long)MATCH_R1_CMPLT, (unsigned long)MASK_R1_CMPLT);
#endif
#ifdef MATCH_R1_CMPLTI
  printf("%s %08lx %08lx\n", "cmplti", (unsigned long)MATCH_R1_CMPLTI, (unsigned long)MASK_R1_CMPLTI);
#endif
#ifdef MATCH_R1_CMPLTU
  printf("%s %08lx %08lx\n", "cmpltu", (unsigned long)MATCH_R1_CMPLTU, (unsigned long)MASK_R1_CMPLTU);
#endif
#ifdef MATCH_R1_CMPLTUI
  printf("%s %08lx %08lx\n", "cmpltui", (unsigned long)MATCH_R1_CMPLTUI, (unsigned long)MASK_R1_CMPLTUI);
#endif
#ifdef MATCH_R1_CMPNE
  printf("%s %08lx %08lx\n", "cmpne", (unsigned long)MATCH_R1_CMPNE, (unsigned long)MASK_R1_CMPNE);
#endif
#ifdef MATCH_R1_CMPNEI
  printf("%s %08lx %08lx\n", "cmpnei", (unsigned long)MATCH_R1_CMPNEI, (unsigned long)MASK_R1_CMPNEI);
#endif
#ifdef MATCH_R1_CUSTOM
  printf("%s %08lx %08lx\n", "custom", (unsigned long)MATCH_R1_CUSTOM, (unsigned long)MASK_R1_CUSTOM);
#endif
#ifdef MATCH_R1_DIV
  printf("%s %08lx %08lx\n", "div", (unsigned long)MATCH_R1_DIV, (unsigned long)MASK_R1_DIV);
#endif
#ifdef MATCH_R1_DIVU
  printf("%s %08lx %08lx\n", "divu", (unsigned long)MATCH_R1_DIVU, (unsigned long)MASK_R1_DIVU);
#endif
#ifdef MATCH_R1_ERET
  printf("%s %08lx %08lx\n", "eret", (unsigned long)MATCH_R1_ERET, (unsigned long)MASK_R1_ERET);
#endif
#ifdef MATCH_R1_FLUSHD
  printf("%s %08lx %08lx\n", "flushd", (unsigned long)MATCH_R1_FLUSHD, (unsigned long)MASK_R1_FLUSHD);
#endif
#ifdef MATCH_R1_FLUSHDA
  printf("%s %08lx %08lx\n", "flushda", (unsigned long)MATCH_R1_FLUSHDA, (unsigned long)MASK_R1_FLUSHDA);
#endif
#ifdef MATCH_R1_FLUSHI
  printf("%s %08lx %08lx\n", "flushi", (unsigned long)MATCH_R1_FLUSHI, (unsigned long)MASK_R1_FLUSHI);
#endif
#ifdef MATCH_R1_FLUSHP
  printf("%s %08lx %08lx\n", "flushp", (unsigned long)MATCH_R1_FLUSHP, (unsigned long)MASK_R1_FLUSHP);
#endif
#ifdef MATCH_R1_INITD
  printf("%s %08lx %08lx\n", "initd", (unsigned long)MATCH_R1_INITD, (unsigned long)MASK_R1_INITD);
#endif
#ifdef MATCH_R1_INITDA
  printf("%s %08lx %08lx\n", "initda", (unsigned long)MATCH_R1_INITDA, (unsigned long)MASK_R1_INITDA);
#endif
#ifdef MATCH_R1_INITI
  printf("%s %08lx %08lx\n", "initi", (unsigned long)MATCH_R1_INITI, (unsigned long)MASK_R1_INITI);
#endif
#ifdef MATCH_R1_JMP
  printf("%s %08lx %08lx\n", "jmp", (unsigned long)MATCH_R1_JMP, (unsigned long)MASK_R1_JMP);
#endif
#ifdef MATCH_R1_JMPI
  printf("%s %08lx %08lx\n", "jmpi", (unsigned long)MATCH_R1_JMPI, (unsigned long)MASK_R1_JMPI);
#endif
#ifdef MATCH_R1_LDB
  printf("%s %08lx %08lx\n", "ldb", (unsigned long)MATCH_R1_LDB, (unsigned long)MASK_R1_LDB);
#endif
#ifdef MATCH_R1_LDBIO
  printf("%s %08lx %08lx\n", "ldbio", (unsigned long)MATCH_R1_LDBIO, (unsigned long)MASK_R1_LDBIO);
#endif
#ifdef MATCH_R1_LDBU
  printf("%s %08lx %08lx\n", "ldbu", (unsigned long)MATCH_R1_LDBU, (unsigned long)MASK_R1_LDBU);
#endif
#ifdef MATCH_R1_LDBUIO
  printf("%s %08lx %08lx\n", "ldbuio", (unsigned long)MATCH_R1_LDBUIO, (unsigned long)MASK_R1_LDBUIO);
#endif
#ifdef MATCH_R1_LDH
  printf("%s %08lx %08lx\n", "ldh", (unsigned long)MATCH_R1_LDH, (unsigned long)MASK_R1_LDH);
#endif
#ifdef MATCH_R1_LDHIO
  printf("%s %08lx %08lx\n", "ldhio", (unsigned long)MATCH_R1_LDHIO, (unsigned long)MASK_R1_LDHIO);
#endif
#ifdef MATCH_R1_LDHU
  printf("%s %08lx %08lx\n", "ldhu", (unsigned long)MATCH_R1_LDHU, (unsigned long)MASK_R1_LDHU);
#endif
#ifdef MATCH_R1_LDHUIO
  printf("%s %08lx %08lx\n", "ldhuio", (unsigned long)MATCH_R1_LDHUIO, (unsigned long)MASK_R1_LDHUIO);
#endif
#ifdef MATCH_R1_LDW
  printf("%s %08lx %08lx\n", "ldw", (unsigned long)MATCH_R1_LDW, (unsigned long)MASK_R1_LDW);
#endif
#ifdef MATCH_R1_LDWIO
  printf("%s %08lx %08lx\n", "ldwio", (unsigned long)MATCH_R1_LDWIO, (unsigned long)MASK_R1_LDWIO);
#endif
#ifdef MATCH_R1_MOV
  printf("%s %08lx %08lx\n", "mov", (unsigned long)MATCH_R1_MOV, (unsigned long)MASK_R1_MOV);
#endif
#ifdef MATCH_R1_MOVHI
  printf("%s %08lx %08lx\n", "movhi", (unsigned long)MATCH_R1_MOVHI, (unsigned long)MASK_R1_MOVHI);
#endif
#ifdef MATCH_R1_MOVI
  printf("%s %08lx %08lx\n", "movi", (unsigned long)MATCH_R1_MOVI, (unsigned long)MASK_R1_MOVI);
#endif
#ifdef MATCH_R1_MOVIA
  printf("%s %08lx %08lx\n", "movia", (unsigned long)MATCH_R1_MOVIA, (unsigned long)MASK_R1_MOVIA);
#endif
#ifdef MATCH_R1_MOVUI
  printf("%s %08lx %08lx\n", "movui", (unsigned long)MATCH_R1_MOVUI, (unsigned long)MASK_R1_MOVUI);
#endif
#ifdef MATCH_R1_MUL
  printf("%s %08lx %08lx\n", "mul", (unsigned long)MATCH_R1_MUL, (unsigned long)MASK_R1_MUL);
#endif
#ifdef MATCH_R1_MULI
  printf("%s %08lx %08lx\n", "muli", (unsigned long)MATCH_R1_MULI, (unsigned long)MASK_R1_MULI);
#endif
#ifdef MATCH_R1_MULXSS
  printf("%s %08lx %08lx\n", "mulxss", (unsigned long)MATCH_R1_MULXSS, (unsigned long)MASK_R1_MULXSS);
#endif
#ifdef MATCH_R1_MULXSU
  printf("%s %08lx %08lx\n", "mulxsu", (unsigned long)MATCH_R1_MULXSU, (unsigned long)MASK_R1_MULXSU);
#endif
#ifdef MATCH_R1_MULXUU
  printf("%s %08lx %08lx\n", "mulxuu", (unsigned long)MATCH_R1_MULXUU, (unsigned long)MASK_R1_MULXUU);
#endif
#ifdef MATCH_R1_NEXTPC
  printf("%s %08lx %08lx\n", "nextpc", (unsigned long)MATCH_R1_NEXTPC, (unsigned long)MASK_R1_NEXTPC);
#endif
#ifdef MATCH_R1_NOP
  printf("%s %08lx %08lx\n", "nop", (unsigned long)MATCH_R1_NOP, (unsigned long)MASK_R1_NOP);
#endif
#ifdef MATCH_R1_NOR
  printf("%s %08lx %08lx\n", "nor", (unsigned long)MATCH_R1_NOR, (unsigned long)MASK_R1_NOR);
#endif
#ifdef MATCH_R1_OR
  printf("%s %08lx %08lx\n", "or", (unsigned long)MATCH_R1_OR, (unsigned long)MASK_R1_OR);
#endif
#ifdef MATCH_R1_ORHI
  printf("%s %08lx %08lx\n", "orhi", (unsigned long)MATCH_R1_ORHI, (unsigned long)MASK_R1_ORHI);
#endif
#ifdef MATCH_R1_ORI
  printf("%s %08lx %08lx\n", "ori", (unsigned long)MATCH_R1_ORI, (unsigned long)MASK_R1_ORI);
#endif
#ifdef MATCH_R1_RDCTL
  printf("%s %08lx %08lx\n", "rdctl", (unsigned long)MATCH_R1_RDCTL, (unsigned long)MASK_R1_RDCTL);
#endif
#ifdef MATCH_R1_RDPRS
  printf("%s %08lx %08lx\n", "rdprs", (unsigned long)MATCH_R1_RDPRS, (unsigned long)MASK_R1_RDPRS);
#endif
#ifdef MATCH_R1_RET
  printf("%s %08lx %08lx\n", "ret", (unsigned long)MATCH_R1_RET, (unsigned long)MASK_R1_RET);
#endif
#ifdef MATCH_R1_ROL
  printf("%s %08lx %08lx\n", "rol", (unsigned long)MATCH_R1_ROL, (unsigned long)MASK_R1_ROL);
#endif
#ifdef MATCH_R1_ROLI
  printf("%s %08lx %08lx\n", "roli", (unsigned long)MATCH_R1_ROLI, (unsigned long)MASK_R1_ROLI);
#endif
#ifdef MATCH_R1_ROR
  printf("%s %08lx %08lx\n", "ror", (unsigned long)MATCH_R1_ROR, (unsigned long)MASK_R1_ROR);
#endif
#ifdef MATCH_R1_SLL
  printf("%s %08lx %08lx\n", "sll", (unsigned long)MATCH_R1_SLL, (unsigned long)MASK_R1_SLL);
#endif
#ifdef MATCH_R1_SLLI
  printf("%s %08lx %08lx\n", "slli", (unsigned long)MATCH_R1_SLLI, (unsigned long)MASK_R1_SLLI);
#endif
#ifdef MATCH_R1_SRA
  printf("%s %08lx %08lx\n", "sra", (unsigned long)MATCH_R1_SRA, (unsigned long)MASK_R1_SRA);
#endif
#ifdef MATCH_R1_SRAI
  printf("%s %08lx %08lx\n", "srai", (unsigned long)MATCH_R1_SRAI, (unsigned long)MASK_R1_SRAI);
#endif
#ifdef MATCH_R1_SRL
  printf("%s %08lx %08lx\n", "srl", (unsigned long)MATCH_R1_SRL, (unsigned long)MASK_R1_SRL);
#endif
#ifdef MATCH_R1_SRLI
  printf("%s %08lx %08lx\n", "srli", (unsigned long)MATCH_R1_SRLI, (unsigned long)MASK_R1_SRLI);
#endif
#ifdef MATCH_R1_STB
  printf("%s %08lx %08lx\n", "stb", (unsigned long)MATCH_R1_STB, (unsigned long)MASK_R1_STB);
#endif
#ifdef MATCH_R1_STBIO
  printf("%s %08lx %08lx\n", "stbio", (unsigned long)MATCH_R1_STBIO, (unsigned long)MASK_R1_STBIO);
#endif
#ifdef MATCH_R1_STH
  printf("%s %08lx %08lx\n", "sth", (unsigned long)MATCH_R1_STH, (unsigned long)MASK_R1_STH);
#endif
#ifdef MATCH_R1_STHIO
  printf("%s %08lx %08lx\n", "sthio", (unsigned long)MATCH_R1_STHIO, (unsigned long)MASK_R1_STHIO);
#endif
#ifdef MATCH_R1_STW
  printf("%s %08lx %08lx\n", "stw", (unsigned long)MATCH_R1_STW, (unsigned long)MASK_R1_STW);
#endif
#ifdef MATCH_R1_STWIO
  printf("%s %08lx %08lx\n", "stwio", (unsigned long)MATCH_R1_STWIO, (unsigned long)MASK_R1_STWIO);
#endif
#ifdef MATCH_R1_SUB
  printf("%s %08lx %08lx\n", "sub", (unsigned long)MATCH_R1_SUB, (unsigned long)MASK_R1_SUB);
#endif
#ifdef MATCH_R1_SUBI
  printf("%s %08lx %08lx\n", "subi", (unsigned long)MATCH_R1_SUBI, (unsigned long)MASK_R1_SUBI);
#endif
#ifdef MATCH_R1_SYNC
  printf("%s %08lx %08lx\n", "sync", (unsigned long)MATCH_R1_SYNC, (unsigned long)MASK_R1_SYNC);
#endif
#ifdef MATCH_R1_TRAP
  printf("%s %08lx %08lx\n", "trap", (unsigned long)MATCH_R1_TRAP, (unsigned long)MASK_R1_TRAP);
#endif
#ifdef MATCH_R1_WRCTL
  printf("%s %08lx %08lx\n", "wrctl", (unsigned long)MATCH_R1_WRCTL, (unsigned long)MASK_R1_WRCTL);
#endif
#ifdef MATCH_R1_WRPRS
  printf("%s %08lx %08lx\n", "wrprs", (unsigned long)MATCH_R1_WRPRS, (unsigned long)MASK_R1_WRPRS);
#endif
#ifdef MATCH_R1_XOR
  printf("%s %08lx %08lx\n", "xor", (unsigned long)MATCH_R1_XOR, (unsigned long)MASK_R1_XOR);
#endif
#ifdef MATCH_R1_XORHI
  printf("%s %08lx %08lx\n", "xorhi", (unsigned long)MATCH_R1_XORHI, (unsigned long)MASK_R1_XORHI);
#endif
#ifdef MATCH_R1_XORI
  printf("%s %08lx %08lx\n", "xori", (unsigned long)MATCH_R1_XORI, (unsigned long)MASK_R1_XORI);
#endif
  return 0; }
