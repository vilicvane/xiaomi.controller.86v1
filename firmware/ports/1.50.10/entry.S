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

/* Private 3x5 IP digit stamp, fixed scale3; r0=context,r1=x,r2=glyph.
 * Y is shifted by drawer cover. Source digits use bit0 as top-left.
 * Both top clipping and bottom bound are checked for each output row. */
.section .text,"ax",%progbits
.balign 4
.global glyph
.type glyph,%function
.thumb_func
glyph:
    push {r0,r4-r7,lr}
    ldr r4,[r0,#28]
    ldr r5,[r0,#84]
    subs r5,#170
    add.w r4,r4,r1,lsl #2
    adds r7,r4,#36
    ldr r0,=digits
    ldrh.w r6,[r0,r2,lsl #1]
1:
    lsrs r6,#1
    bcc 4f
    movs r2,#3
    mov r3,r5
2:
    cmp.w r3,#320
    bhs 3f
    movw r0,#1920
    mla r0,r3,r0,r4
    mov.w r1,#0xffffffff
    str r1,[r0]
    str r1,[r0,#4]
    str r1,[r0,#8]
3:
    adds r3,#1
    subs r2,#1
    bne 2b
4:
    adds r4,#12
    cmp r4,r7
    bne 5f
    subs r4,#36
    adds r5,#3
5:
    cmp r6,#0
    bne 1b
    pop {r0,r4-r7,pc}
.ltorg
.size glyph,.-glyph
