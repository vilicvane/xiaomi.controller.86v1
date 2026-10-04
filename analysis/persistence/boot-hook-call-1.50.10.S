/* The four bytes at NOR 0x150056: BL 0x0c824400. */
.syntax unified
.thumb
.cpu cortex-m33
.section .text,"ax",%progbits
.global boot_hook_call
.type boot_hook_call,%function
.thumb_func
boot_hook_call:
  bl . + 0x6d43aa
.size boot_hook_call, . - boot_hook_call
