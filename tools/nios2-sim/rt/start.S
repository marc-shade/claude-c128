/* Bare-metal entry for nios2sim. The simulator sets sp/fp and jumps here. */
    .section .text.startup, "ax"
    .global _start
    .type _start, @function
_start:
    movhi   r2, %hi(_stack_top)
    ori     r2, r2, %lo(_stack_top)
    mov     sp, r2
    mov     fp, r2
    /* gp, for small-data relative addressing */
    movhi   r2, %hi(_gp)
    ori     r2, r2, %lo(_gp)
    mov     gp, r2
    /* zero .bss */
    movhi   r4, %hi(__bss_start)
    ori     r4, r4, %lo(__bss_start)
    movhi   r5, %hi(__bss_end)
    ori     r5, r5, %lo(__bss_end)
1:  bgeu    r4, r5, 2f
    stw     r0, 0(r4)
    addi    r4, r4, 4
    br      1b
    movhi   r4, %hi(__sbss_start)
    ori     r4, r4, %lo(__sbss_start)
    movhi   r5, %hi(__sbss_end)
    ori     r5, r5, %lo(__sbss_end)
4:  bgeu    r4, r5, 2f
    stw     r0, 0(r4)
    addi    r4, r4, 4
    br      4b
2:  call    main
    /* store the return value to the halt port */
    movhi   r3, 0x1000          /* 0x10000000 */
    stw     r2, 4(r3)           /* MMIO_HALT  */
3:  br      3b
    .size _start, .-_start
