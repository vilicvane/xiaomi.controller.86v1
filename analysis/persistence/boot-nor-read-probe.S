/* BOOT only, position-independent SRAM caller.  No program/erase/status write.
 * Host preserves all core registers, DCRDR and the borrowed 1024-byte RAM range.
 * Place code/output entirely below original SP-512.  Keep original SP and limits.
 * HAL maximum internal stack for this caller is 64 bytes.  It stops with IRQ
 * still masked; host restores borrowed RAM/core before resuming original boot.
 */
.syntax unified
.thumb
.cpu cortex-m33
.section .text,"ax",%progbits
.global boot_nor_read_probe
.type boot_nor_read_probe,%function
.thumb_func
boot_nor_read_probe:
  adr r4, .Loutput
  mrs r5, primask
  str r5, [r4, #0]
  cpsid i
  mrs r5, primask
  str r5, [r4, #4]
  cmp r5, #1
  bne .Lmask_failed

  movs r0, #0
  add.w r1, r4, #32
  movs r2, #3
  ldr r7, =0x00201cf9
  blx r7
  str r0, [r4, #8]

  movs r0, #0
  ldr r7, =0x002018a9
  blx r7
  str r0, [r4, #12]

  movs r0, #0
  movs r1, #0x05
  add.w r2, r4, #35
  movs r3, #1
  ldr r7, =0x00201901
  blx r7
  str r0, [r4, #16]

  movs r0, #0
  movs r1, #0x35
  add.w r2, r4, #36
  movs r3, #1
  ldr r7, =0x00201901
  blx r7
  str r0, [r4, #20]

  movs r0, #0
  ldr r7, =0x002018f9
  blx r7
  str r0, [r4, #24]
  ldr r0, =0x52454144
  b .Lcomplete

.Lmask_failed:
  ldr r0, =0xbad00001
.Lcomplete:
  str r0, [r4, #28]
  dsb sy
  bkpt #0
.Lstopped:
  b .Lstopped
.size boot_nor_read_probe, . - boot_nor_read_probe
.ltorg
.p2align 2
.Lguard_before:
  .word 0xc0def00d
.Loutput:
  .space 40, 0
.Lguard_after:
  .word 0x0df0dec0
.global boot_nor_read_probe_output
.set boot_nor_read_probe_output, .Loutput
.global boot_nor_read_probe_guard_before
.set boot_nor_read_probe_guard_before, .Lguard_before
.global boot_nor_read_probe_guard_after
.set boot_nor_read_probe_guard_after, .Lguard_after
.global boot_nor_read_probe_end
boot_nor_read_probe_end:
