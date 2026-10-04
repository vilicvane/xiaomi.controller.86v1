/* Offline-prepared generic BOOT SRAM caller. No automatic device execution.
 * Host admits exactly bootsetBP/write/erase after independent read verification.
 * Source payload lives at originalSP-1024+256; originalSP/limits never change.
 * Entire image <=256 bytes; HAL stack max232 B in top512 reserved band.
 */
.syntax unified
.thumb
.cpu cortex-m33
.section .text,"ax",%progbits
.global boot_nor_one_call
.type boot_nor_one_call,%function
.thumb_func
boot_nor_one_call:
  adr r4, .Lio
  mrs r5, primask
  str r5, [r4, #20]
  cpsid i
  mrs r5, primask
  str r5, [r4, #24]
  cmp r5, #1
  bne .Lmask_failed
  ldr r7, [r4, #0]
  ldr r0, [r4, #4]
  ldr r1, [r4, #8]
  ldr r2, [r4, #12]
  ldr r3, [r4, #16]
  blx r7
  str r0, [r4, #28]
  ldr r0, =0x43414c4c
  b .Lcomplete
.Lmask_failed:
  ldr r0, =0xbad00001
.Lcomplete:
  str r0, [r4, #32]
  dsb sy
  bkpt #0x61
.Lstopped:
  b .Lstopped
.size boot_nor_one_call, . - boot_nor_one_call
.ltorg
.org 0x7c
.Lguard_before:
  .word 0xc0def00d
.Lio:
  .word 0 /* admitted Thumb function pointer */
  .word 0 /* r0 */
  .word 0 /* r1 */
  .word 0 /* r2 */
  .word 0 /* r3 */
  .word 0 /* original PRIMASK */
  .word 0 /* masked PRIMASK */
  .word 0xdeadc0de /* return */
  .word 0 /* completion */
.Lguard_after:
  .word 0x0df0dec0
.global boot_nor_one_call_io
.set boot_nor_one_call_io, .Lio
.global boot_nor_one_call_guard_before
.set boot_nor_one_call_guard_before, .Lguard_before
.global boot_nor_one_call_guard_after
.set boot_nor_one_call_guard_after, .Lguard_after
.global boot_nor_one_call_end
boot_nor_one_call_end:
