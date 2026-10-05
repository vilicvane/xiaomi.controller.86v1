ENTRY(broker_start)
SECTIONS {
  .prefix 0x3804b108 : { *(.broker.disabled) *(.text.broker.prefix) *(.rodata.broker.prefix) }
  .start 0x3804b2f4 : { *(.broker.entry) }
  .broker 0x3804b2f8 : { *(.text.entry) *(.text) *(.rodata) *(.rodata.str*) *(.rodata.cst*) }
  .feedback 0x3807a764 : { *(.text.feedback*) *(.rodata.feedback*) }
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
  ASSERT(SIZEOF(.prefix) <= 0x1ec, "Broker prefix exceeds diagnostic container")
  ASSERT(SIZEOF(.start) == 4 && SIZEOF(.broker) <= 0xb78, "Drawer exceeds reviewed diagnostic containers")
  ASSERT(ADDR(.feedback) == 0x3807a764 && SIZEOF(.feedback) <= 0x1bc, "Feedback exceeds bounded former faclvgl socketworker slot")
  ASSERT(ADDR(.broker)+SIZEOF(.broker) <= 0x3804be70, "Shared helper at be70 must remain intact")
  ASSERT(broker_start == 0x3804b2f5, "Broker Thumb entry changed")
  ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "Broker needs heap state only")
}
