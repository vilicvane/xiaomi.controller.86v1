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

/* Private card stamp kernel, AAPCS arguments r0=pixels, r1=cover, r2=bits,
 * r3=packed x9/y8/scale2/logo1/color2. Preserve r4-r11 and 8-byte SP alignment.
 * The caller supplies scale2/3, white/gray/gold and reviewed in-range x spans.
 * Signed y clipping accepts only rows0..319; cover0 therefore paints nothing.
 */
.section .text.broker.prefix,"ax",%progbits
.balign 4
.global stamp
.type stamp,%function
.thumb_func
stamp:
    push.w {r4-r11,r12,lr}
    mov r6, r2
    ubfx r2, r3, #0, #9
    add.w r4, r0, r2, lsl #2
    ubfx r2, r3, #9, #8
    add r5, r1, r2
    sub.w r5, r5, #320
    ubfx r7, r3, #17, #2
    ubfx r2, r3, #19, #1
    mov.w r8, #5
    cmp r2, #0
    it ne
    movne r8, #24
    lsr r2, r3, #20
    adr r3, stamp_colors
    ldr.w r10, [r3,r2,lsl #2]
    mov r11, r8
1:
    cmp r8, #24
    ite eq
    ldreq.w lr, [r6], #4
    ldrbne.w lr, [r6], #1
    mov r1, r5
2:
    lsrs.w lr, lr, #1
    bcc 4f
    mov r2, r7
    mov r9, r1
3:
    cmp.w r9, #320
    bhs 6f
    movw r0, #1920
    mla r12, r9, r0, r4
    mov r3, r7
5:
    str.w r10, [r12], #4
    subs r3, #1
    bne 5b
6:
    add.w r9, r9, #1
    subs r2, #1
    bne 3b
4:
    add r1, r7
    cmp lr, #0
    bne 2b
    add.w r4, r4, r7, lsl #2
    subs.w r11, r11, #1
    bne 1b
    pop.w {r4-r11,r12,pc}
.balign 4
stamp_colors:
    .word 0xffffffff,0xffa0a0a0,0xffe3b341
.size stamp, .-stamp

.section .text.feedback.paint,"ax",%progbits
/* Card control uses aligned style words and a separate compact glyph stream. */
.balign 4
.global paint
.type paint,%function
.thumb_func
paint:
    push.w {r4-r11,r12,lr}
    str r2, [sp,#32]
    mov r4, r0
    mov r5, r1
    ldr r2, =github_logo
    movw r3, #0x84d8
    movt r3, #0x000c
    bl stamp
    ldr r6, =card_text
    ldr r7, =card_styles
    ldr r11, =card_font
6:
    ldr r0, =card_styles+8
    cmp r7, r0
    bne 9f
    ldr r2, [sp,#32]
    cbz r2, 9f
    mov r0, r4
    mov r1, r5
    bl number
    b 10f
9:
    ldr.w r8, [r7], #4
    ldrb.w r9, [r6], #1
    ubfx r10, r8, #17, #2
    add.w r10, r10, r10, lsl #1
    lsl.w r10, r10, #1
7:
    ldrb.w r0, [r6], #1
    add.w r2, r0, r0, lsl #2
    add r2, r11
    mov r0, r4
    mov r1, r5
    mov r3, r8
    bl stamp
    add r8, r10
    subs.w r9, r9, #1
    bne 7b
    ldr r0, =card_styles+12
    cmp r7, r0
    blo 6b
10:
    pop.w {r4-r11,r12,pc}
.ltorg
.size paint, .-paint

/* Private numeric feedback; reverse has exactly10 bytes for saturatedu32.
 * Save32 bytes and allocate16 bytes separately: SP remains8-aligned at every
 * instruction. Pixels/cover use same private stamp ABI as the static card. */
/* Settled custom page: the caller clears only rows249..269. Reuse the
 * static footer/number loop, preserving the exact full renderer pixels. */
.section .text.feedback.footer,"ax",%progbits
.balign 4
.global paint_footer
.type paint_footer,%function
.thumb_func
paint_footer:
    push.w {r4-r11,r12,lr}
    str r1, [sp,#32]
    mov r4, r0
    movw r5, #320
    ldr r6, =card_text+33
    ldr r7, =card_styles+8
    ldr r11, =card_font
    b.w 6b
.ltorg
.size paint_footer, .-paint_footer

.section .text.feedback.number,"ax",%progbits
.balign 4
.global number
.type number,%function
.thumb_func
number:
    push.w {r4-r10,lr}
    sub sp, #16
    mov r4, sp
    mov r8, r1
    mov r9, r0
    movs r5, #0
    movw r0, #462
    movs r1, #10
11:
    udiv r3, r2, r1
    subs r0, #18
    mls r6, r3, r1, r2
    strb r6, [r4,r5]
    adds r5, #1
    cmp r2, #9
    mov r2, r3
    bhi 11b
    ldr r1, =0x0027f200
    ldr r10, =tap_digits
    orr.w r6, r1, r0, lsr #1
    add.w r2, r10, #50
12:
    mov r0, r9
    mov r1, r8
    mov r3, r6
    bl stamp
    adds r6, #18
    subs r5, #1
    adds r0, r5, #1
    beq 13f
    ldrb r0, [r4,r5]
    add.w r0, r0, r0, lsl #2
    add.w r2, r10, r0
    b 12b
13:
    add sp, #16
    pop.w {r4-r10,pc}
.ltorg
.size number, .-number
