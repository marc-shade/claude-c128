/* Flat memory, matching nios2sim's 64 MB. Text starts above zero so a null
 * dereference lands outside any mapped section.
 *
 * _gp must exist because nios2 addresses small data gp-relative (+/-32 KB);
 * without it the linker fails on .sdata relocations. start.S loads it into r26. */
ENTRY(_start)
MEMORY { ram : ORIGIN = 0x00001000, LENGTH = 0x03FFF000 }
SECTIONS
{
  .text   : { *(.text.startup) *(.text .text.*) } > ram
  .rodata : { *(.rodata .rodata.*) } > ram
  .data   : { *(.data .data.*) } > ram

  . = ALIGN(16);
  _gp = . + 0x8000;
  PROVIDE(gp = _gp);

  .sdata  : { *(.sdata .sdata.*) } > ram
  .sbss (NOLOAD) : { __sbss_start = .; *(.sbss .sbss.*) . = ALIGN(4); __sbss_end = .; } > ram
  .bss (NOLOAD)  : { __bss_start = .; *(.bss .bss.* COMMON) . = ALIGN(4); __bss_end = .; } > ram

  . = ALIGN(16);
  __heap_start = .;
  _stack_top = 0x03FF0000;
}
