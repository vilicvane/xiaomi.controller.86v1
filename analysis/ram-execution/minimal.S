.syntax unified
.thumb
.global ram_probe
ram_probe:
    movs r1, #42
    movs r2, #23
    adds r1, r1, r2
    str r1, [r0]
    eors r1, r2
    str r1, [r0, #4]
    bkpt #0x55
1:  b 1b
