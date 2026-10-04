/* Offline review artifact only; not executed or programmed. */
.syntax unified
.thumb
.cpu cortex-m33
.section .text,"ax",%progbits
.global boot_hook
.type boot_hook,%function
.thumb_func
boot_hook:
  push {r0, r1}
  ldr r0, marker_register
  ldr r1, marker_value
  str r1, [r0]
  dsb sy
  pop {r0, r1}
  /* At mapped 0x0c82440e, branch to original 0x0c5d6538. */
  b.w . - 0x24ded6
  .hword 0xbf00
marker_register:
  .word 0xe000edf8
marker_value:
  .word 0x4b4f4f48
  .word 0xffffffff
.size boot_hook, . - boot_hook
