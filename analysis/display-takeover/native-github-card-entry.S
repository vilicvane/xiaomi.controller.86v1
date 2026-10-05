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
    ubfx lr, r3, #19, #1
    movs r0, #7
    cmp lr, #0
    it ne
    movne r0, #24
    mul r9, r0, r7
    it eq
    subeq r0, #2
    mul r8, r0, r7
    lsr r2, r3, #20
    adr r3, stamp_colors
    ldr.w r10, [r3,r2,lsl #2]
    mov.w r11, #0
1:
    add.w r1, r5, r11
    cmp.w r1, #320
    bhs 4f
    movw r2, #1920
    mla r12, r1, r2, r4
    movs r0, #0
2:
    udiv r2, r0, r7
    udiv r3, r11, r7
    cmp lr, #0
    ite eq
    ldrbeq r2, [r6,r2]
    ldrne.w r2, [r6,r2,lsl #2]
    lsr.w r3, r2, r3
    tst r3, #1
    it ne
    strne.w r10, [r12,r0,lsl #2]
    adds r0, #1
    cmp r0, r8
    blo 2b
4:
    add.w r11, r11, #1
    cmp r11, r9
    blo 1b
    pop.w {r4-r11,r12,pc}
.balign 4
stamp_colors:
    .word 0xffffffff,0xffa0a0a0,0xffe3b341
.size stamp, .-stamp

/* Card control uses aligned style words and a separate compact glyph stream. */
.balign 4
.global paint
.type paint,%function
.thumb_func
paint:
    push.w {r4-r11,r12,lr}
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
    pop.w {r4-r11,r12,pc}
.ltorg
.size paint, .-paint
