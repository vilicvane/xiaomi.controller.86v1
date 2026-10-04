 .syntax unified
.thumb
.global color_probe
color_probe:
    str r1, [r0]
    ldr r1, [r2]
    orrs r1, r3
    str r1, [r2]
    dsb sy
    bkpt #0x55
1:  b 1b
