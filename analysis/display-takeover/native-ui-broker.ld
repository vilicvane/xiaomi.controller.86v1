ENTRY(broker_start)
SECTIONS {
  .prefix 0x3804b108 : { *(.broker.disabled) *(.text.broker.prefix) *(.rodata.broker.prefix) }
  .start 0x3804b2f4 : { *(.broker.entry) }
  .broker 0x3804b2f8 : { *(.text.entry) *(.text*) *(.rodata*) }
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
  ASSERT(SIZEOF(.prefix) <= 0x1ec, "Broker prefix exceeds diagnostic container")
  ASSERT(SIZEOF(.start) == 4 && SIZEOF(.broker) <= 0x9a0, "Broker exceeds factory/showlogo containers")
  ASSERT(broker_start == 0x3804b2f5, "Broker Thumb entry changed")
  ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "Broker needs heap state only")
}
