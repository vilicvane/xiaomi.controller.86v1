.syntax unified
.thumb
.section .counter.entry,"ax",%progbits
.balign 4
.global counter_start
.type counter_start,%function
.thumb_func
counter_start:
    b.w counter_main
.size counter_start, .-counter_start
