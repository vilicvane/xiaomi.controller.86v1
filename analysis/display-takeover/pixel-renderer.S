.syntax unified
.cpu cortex-m33
.thumb
.section .text.pixel_renderer,"ax",%progbits
.global pixel_renderer
.type pixel_renderer,%function
.thumb_func
// Entry (privileged, halted debug setup, interrupt masking active):
// r0 = exact current PSRAMUHS noncacheable scanout base
// r1 = pixel count (10240 for 32 physical rows of 320 pixels)
// r2 = packed opaque RGB32 color (candidate 0xffff00ff)
// r3 = original secure MPU region 5 RBAR (0x38000007)
// r4 = secure MPU RBAR register (0xe000ed9c), RNR remains 5
// Host temporarily grants privileged RW by RBAR=0x38000001.
// Only r0/r1, arithmetic flags, and PC are changed by this routine.
pixel_renderer:
    dsb sy
    isb sy
    cbz r1, .Lrestore
.Lfill:
    str r2, [r0]
    adds r0, #4
    subs r1, #1
    bne .Lfill
.Lrestore:
    dsb sy
    str r3, [r4]
    dsb sy
    isb sy
    bkpt #0x55
.Lstop:
    b .Lstop
.size pixel_renderer, .-pixel_renderer
