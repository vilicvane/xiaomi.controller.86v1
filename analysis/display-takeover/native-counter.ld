ENTRY(counter_start)
SECTIONS {
  .start 0x3804b2f4 : { *(.counter.entry) }
  .counter 0x3804b2f8 : { *(.text.entry) *(.text*) *(.rodata*) }
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
  ASSERT(SIZEOF(.start) == 4 && SIZEOF(.counter) <= 0x584, "Counter exceeds the proved factory-task function container")
  ASSERT(ADDR(.start) == 0x3804b2f4 && ADDR(.counter) == 0x3804b2f8, "Counter binary load address changed")
  ASSERT(counter_start == 0x3804b2f5, "Counter Thumb entry changed")
  ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "Counter must have no additional RW/BSS storage")
}
