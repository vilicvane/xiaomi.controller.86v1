#ifndef MI_PANEL_H
#define MI_PANEL_H

#include <stddef.h>
#include <stdint.h>
#include "drawer-gesture.h"
#include "tap-gesture.h"

typedef unsigned int u32;
typedef unsigned char u8;
typedef unsigned short u16;
typedef signed long long i64;

/* Native addresses and layouts belong to this panel's exact 1.50.10 image. */
#define FN(type, address) ((type)(address))
#define GETFILE FN(int (*)(int, void **), 0x38025679u)
#define ALLOC FN(void *(*)(u32), 0x383d9421u)
#define FREE FN(void (*)(void *), 0x383d93e5u)
#define ZERO FN(void *(*)(void *, int, u32), 0x383d8fa0u)
#define SLEEP FN(int (*)(const void *, void *), 0x38042131u)
#define CLOCK FN(int (*)(int, void *), 0x38004c39u)
#define CREATE FN(int (*)(u32 *, void *, void *(*)(void *), void *), 0x383acc05u)
#define LOCK FN(int (*)(void *, void *), 0x3800da2du)
#define UNLOCK FN(int (*)(void *), 0x3800b0b5u)
#define NLOCK FN(int (*)(void *), 0x3800c1f9u)
#define NUNLOCK FN(int (*)(void *), 0x3800bb3du)
#define ORIGINAL FN(int (*)(int, char **), 0x3818f9fdu)
#define PAN FN(int (*)(void *, const u32 *), 0x383df2dcu)
#define AREA FN(int (*)(void *, void *), 0x383df474u)
#define TOUCH FN(void (*)(void *, u8 *), 0x3806ab75u)
#define TIMER FN(void (*)(void *), 0x3806a93du)
#define SOCKET FN(int (*)(int, int, int), 0x3802b529u)
#define BIND FN(int (*)(int, const void *, u32), 0x381792edu)
#define LISTEN FN(int (*)(int, int), 0x381794fdu)
#define ACCEPT FN(int (*)(int, void *, u32 *), 0x38394355u)
#define RECEIVE FN(int (*)(int, void *, u32, int, void *, u32 *), 0x38179785u)
#define SEND FN(int (*)(int, const void *, u32, int), 0x381798a1u)
#define ERRNO FN(int *(*)(void), 0x38018c5du)
#define CLOSE FN(int (*)(int), 0x38025de1u)
#define IOCTL FN(int (*)(int, int, void *), 0x38025c41u)
#define SNPRINTF FN(int (*)(char *, u32, const char *, ...), 0x3801a419u)
#define WORD(address) (*(volatile u32 *)(address))
#define BYTE(address) (*(volatile u8 *)(address))
#define DEVICE ((void *)0x384ef84cu)
#define PANEL_SCREEN_STATE 0x384ea638u
#define PANEL_PORT 18086u
#define PANEL_WIDTH 480u
#define PANEL_HEIGHT 320u
#define PANEL_IMAGE_BYTES 307200u
#define PREFIX __attribute__((section(".text.broker.prefix")))

#ifndef PANEL_FRONTEND_URL
#define PANEL_FRONTEND_URL ""
#endif
#ifndef PANEL_FRONTEND_ORIGIN
#define PANEL_FRONTEND_ORIGIN "*"
#endif

struct panel_timespec { i64 seconds; int nanoseconds, pad; };
extern const struct panel_timespec pause20;

struct broker {
    u32 mutex[5], tid;
    volatile u32 alive;
    u32 *pixels, *snapshot;
    u32 mode, wanted;
    volatile u32 ready;
    u32 dirty, count, idle;
    u32 drivers[2], released[2], physical;
    u32 overlay, cover, target, shown, background;
    u32 gui_cycles, toggles;
    int last_present, last_x, last_y;
    u32 clock_ms, animation_ms;
    struct tap_gesture taps;
    u32 screen_off; /* 0=awake, 1=off observed, 2=exclude first wake contact from double tap. */
    struct drawer_gesture gesture;
    u32 animation_from, pending, phase;
    u16 *image, *receive;
    volatile u32 image_pending;
    u32 generation, displayed_generation;
    volatile u32 server_state, server_error;
    u32 show_address, ipv4;
    u32 return_after_ms, activity_ms, activity_valid;
};

#if UINTPTR_MAX == UINT32_MAX
_Static_assert(sizeof(struct broker) == 224, "Panel context ABI changed");
_Static_assert(offsetof(struct broker, pixels) == 28, "Glyph pixels ABI changed");
_Static_assert(offsetof(struct broker, cover) == 84, "Glyph cover ABI changed");
_Static_assert(offsetof(struct broker, taps) == 128, "Tap state ABI changed");
_Static_assert(offsetof(struct broker, gesture) == 148, "Gesture state ABI changed");
_Static_assert(offsetof(struct broker, image) == 176, "Image slot ABI changed");
_Static_assert(offsetof(struct broker, image_pending) == 184, "Image publication ABI changed");
_Static_assert(offsetof(struct broker, show_address) == 204, "Address page ABI changed");
_Static_assert(offsetof(struct broker, ipv4) == 208, "IPv4 ABI changed");
_Static_assert(offsetof(struct broker, return_after_ms) == 212, "Return timer ABI changed");
#endif

#define CTX ((struct broker *)WORD(0x384fc864u))
int panel_clock(u32 *output);
int panel_exact(int fd, u8 *data, u32 bytes, u32 start, u32 sending);
void panel_server(struct broker *c);
void glyph(struct broker *c, u32 x, u32 index);

#endif
