ENTRY(broker_start)
SECTIONS {
  .codec 0x38047098 : { *image-codec.o(.text* .rodata*) *(.text.codec.http) }
  .prefix 0x3804b108 : { *(.broker.disabled) *(.text.broker.prefix) *(.rodata.broker.prefix) }
  .start 0x3804b2f4 : { *(.broker.entry) }
  .broker 0x3804b2f8 : {
    *ui.o(.text.entry) *entry.o(.text)
    *ui.o(.text .rodata .rodata.str* .rodata.cst*)
    *(.text.broker.settings)
  }
  .network 0x3804d000 : {
    *http.o(.text .text.panel* .text.body .text.reply .rodata*)
    *http-parser.o(.text* .rodata*) *settings.o(.text* .rodata*)
  }
  .storage 0x38052000 : { *image-store.o(.text* .rodata*) *(.text.storage.http) }
  .feedback 0x3807a764 : { *(.text.feedback*) *(.rodata.feedback*) *(.feedback.settings) }
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
  ASSERT(SIZEOF(.prefix) <= 0x1ec, "Prefix exceeds reviewed diagnostic container")
  ASSERT(SIZEOF(.start) == 4 && SIZEOF(.broker) <= 0xb78, "UI exceeds reviewed diagnostic containers")
  ASSERT(ADDR(.feedback) == 0x3807a764 && SIZEOF(.feedback) <= 0x1bc, "Auxiliary code exceeds former factory socket worker")
  ASSERT(ADDR(.broker)+SIZEOF(.broker) <= 0x3804be70, "Shared helper at be70 must remain intact")
  ASSERT(ADDR(.network) == 0x3804d000 && SIZEOF(.network) <= 0xff0, "Network exceeds diagnostic test container")
  ASSERT(ADDR(.codec) == 0x38047098 && SIZEOF(.codec) <= 0xd14, "Image codecs exceed reviewed fill diagnostic container")
  ASSERT(ADDR(.storage) == 0x38052000 && SIZEOF(.storage) <= 0xbf0, "Image storage exceeds reviewed monkey diagnostic tail")
  ASSERT(broker_start == 0x3804b2f5, "Thumb entry changed")
  ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "State must be owned heap memory")
}
