.syntax unified
.thumb
.section .broker.disabled,"ax",%progbits
.balign 4
.global broker_ntpcstatus_disabled
.type broker_ntpcstatus_disabled,%function
.thumb_func
broker_ntpcstatus_disabled:
    movs r0, #38
    rsbs r0, r0, #0
    bx lr
.size broker_ntpcstatus_disabled, .-broker_ntpcstatus_disabled
.balign 4
.global broker_showlogo_disabled
.type broker_showlogo_disabled,%function
.thumb_func
broker_showlogo_disabled:
    movs r0, #0
    bx lr
.size broker_showlogo_disabled, .-broker_showlogo_disabled
.section .broker.entry,"ax",%progbits
.balign 4
.global broker_start
.type broker_start,%function
.thumb_func
broker_start:
    b.w broker_main
.size broker_start, .-broker_start
