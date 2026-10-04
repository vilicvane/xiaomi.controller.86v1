/* 1.50.10 only. GUI-owned drawer; the bootstrap exits after hook installation. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef signed long long i64;
#include "key3-gesture.h"
#include "drawer-gesture.h"
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
#define WORD(address) (*(volatile u32 *)(address))
#define BYTE(address) (*(volatile u8 *)(address))
#define DEVICE ((void *)0x384ef84cu)
#define PREFIX __attribute__((section(".rodata.broker.prefix")))

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
    struct key3_gesture keys;
    struct drawer_gesture gesture;
};
#define CTX ((struct broker *)WORD(0x384fc864u))
static void timer(void *handle);
static const char alphabet[] PREFIX = "vilcane+0123456789";
static const char prefix[] PREFIX = "vilicvane +";
static const u8 font[][7] PREFIX = {
    {0,0,17,17,17,10,4}, {4,0,12,4,4,4,14}, {12,4,4,4,4,4,14},
    {0,0,15,16,16,16,15}, {0,0,14,1,15,17,15}, {0,0,30,17,17,17,17},
    {0,0,14,17,31,16,15}, {0,4,4,31,4,4,0},
    {14,17,19,21,25,17,14}, {4,12,4,4,4,4,14}, {14,17,1,2,4,8,31},
    {30,1,1,14,1,1,30}, {2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
    {14,16,16,30,17,17,14}, {31,1,2,4,8,8,8}, {14,17,17,14,17,17,14},
    {14,17,17,15,1,1,14}
};

__attribute__((section(".text.broker.prefix"),noinline))
static void paint(u32 *pixels, u32 count, int cover)
{
    char text[22], reverse[10];
    unsigned length = 0, digits = 0;
    while (prefix[length]) { text[length] = prefix[length]; ++length; }
    do { reverse[digits++] = (char)('0'+count%10); count /= 10; } while (count);
    while (digits) text[length++] = reverse[--digits];
    unsigned left = (480-length*18)/2;
    for (unsigned c = 0; c < length; ++c) {
        if (text[c] == ' ') continue;
        unsigned glyph = 0;
        while (alphabet[glyph] && alphabet[glyph] != text[c]) ++glyph;
        if (!alphabet[glyph]) continue;
        for (unsigned y = 0; y < 21; ++y) {
            int row = 145+(int)y+cover-320;
            if (row < 0) continue;
            for (unsigned x = 0; x < 15; ++x)
                if (font[glyph][y/3] & (16u >> (x/3)))
                    pixels[row*480+left+c*18+x] = 0xffffffffu;
        }
    }
}

static int pan(void *device, const u32 *plane)
{
    struct broker *c = CTX;
    if (LOCK(c->mutex,0)) return -1;
    int result = plane[6] == 0xffffffffu ? -1 :
                 (c->mode || c->overlay) ? 0 : PAN(device,plane);
    UNLOCK(c->mutex);
    return result;
}

static int area(void *device, void *rectangle)
{
    struct broker *c = CTX;
    if (LOCK(c->mutex,0)) return -1;
    int result = (c->mode || c->overlay) ? 0 : AREA(device,rectangle);
    UNLOCK(c->mutex);
    return result;
}

static void touch(void *driver, u8 *data)
{
    struct broker *c = CTX;
    TOUCH(driver,data);
    if (LOCK(c->mutex,0)) { data[0x12] = 0; return; }
    unsigned i = (u32)driver == c->drivers[0] ? 0 : 1;
    int down = data[0x12] != 0;
    c->released[i] = !down && !data[0x13];
    if (i == c->physical && !(c->overlay && !c->gesture.active) &&
        (data[0x13] || !down)) {
        int x = (int)WORD((u32)data), y = (int)WORD((u32)data+4u);
        c->last_x = x; c->last_y = y;
        /* Do not truncate an already delivered virtual DOWN/UP pair. */
        if (!c->mode && !c->gesture.active && !c->released[i^1u]) y = 21;
        unsigned event = drawer_gesture_sample(&c->gesture,down,x,y,c->mode*320u);
        if (event & DRAWER_CAPTURE) {
            c->cover = c->gesture.cover;
            if (!c->overlay && (!c->mode || c->cover != 320)) {
                c->overlay = 1; c->background = 0; c->idle = 0;
                c->target = c->mode*320u;
            }
            if (event & DRAWER_RELEASE) {
                c->target = c->gesture.target;
                c->wanted = c->target == 320;
                if (c->wanted != c->mode) ++c->toggles;
            }
            if (event & DRAWER_TAP) { ++c->count; c->dirty = 1; }
        }
    }
    if (c->mode || c->overlay) data[0x12] = 0;
    UNLOCK(c->mutex);
}

static void arm_timer(struct broker *c)
{
    if (c->alive && BYTE(0x384fce30u) == 13 && !(WORD(0x384fce54u)&3u) &&
        (int)WORD(0x384fce20u) >= 0)
        __sync_bool_compare_and_swap((u32 *)0x384fce58u,0x3806a93du,(u32)timer);
}

static int channels(struct broker *c, u32 *upper, u32 *subscriber)
{
    for (unsigned i = 0; i < 2; ++i) {
        void *file = 0;
        if (GETFILE((int)WORD(WORD(c->drivers[i]+0xcu)),&file) < 0 || !file) return -1;
        u32 inode = WORD((u32)file+0x10u);
        if (WORD(inode+0x10u) != 0x384b621cu) return -1;
        upper[i] = WORD(inode+0x18u);
        subscriber[i] = WORD((u32)file+0x14u);
    }
    return 0;
}

/* Publisher-locked finalization; source memory remains allocated. */
__attribute__((noinline)) static int handoff(struct broker *c)
{
    u32 upper[2], subscriber[2];
    if (channels(c,upper,subscriber) < 0) return -1;
    if (NLOCK((void *)(upper[0]+4u))) return -1;
    if (upper[1] != upper[0] && NLOCK((void *)(upper[1]+4u))) {
        NUNLOCK((void *)(upper[0]+4u)); return -1;
    }
    int result = -1;
    int empty = c->released[0] && c->released[1] &&
                BYTE(0x384f50a1u) != 1 && !WORD(0x384ef93cu);
    for (unsigned i = 0; i < 2; ++i)
        if (WORD(subscriber[i]+8u) != WORD(subscriber[i]+0xcu)) empty = 0;
    if (empty) {
        u32 plane[7]; ZERO(plane,0,sizeof(plane));
        plane[6] = c->wanted ? (u32)c->pixels : 0;
        result = PAN(DEVICE,plane);
        if (result >= 0) { c->mode = c->wanted; c->overlay = 0; c->dirty = 0; }
    }
    if (upper[1] != upper[0]) NUNLOCK((void *)(upper[1]+4u));
    NUNLOCK((void *)(upper[0]+4u));
    return result;
}

static int draw(struct broker *c)
{
    for (unsigned i = 0; i < 480u*320u; ++i)
        c->pixels[i] = i < c->cover*480u ? 0xff101010u : c->snapshot[i];
    paint(c->pixels,c->count,c->cover);
    u32 plane[7]; ZERO(plane,0,sizeof(plane)); plane[6] = (u32)c->pixels;
    int result = PAN(DEVICE,plane);
    if (result >= 0) { c->shown = c->cover; c->dirty = 0; }
    return result;
}

__attribute__((noinline)) static int keys(struct broker *c, u32 now)
{
    return key3_gesture_gpio(&c->keys,now,WORD(0x40081050u));
}

static void timer(void *handle)
{
    struct broker *c = CTX;
    if ((u32)handle != 0x384fce28u) { TIMER(handle); return; }
    ++c->gui_cycles;
    /* Complete GUI nodes are published here, in their owning thread. */
    if (!c->ready && c->alive && !LOCK(c->mutex,0)) {
        u32 node = WORD(0x384fcbdcu), display = WORD(0x384fcc4cu);
        if (node && display) {
            u32 first = WORD(node), next = WORD(node+0x84u);
            u32 second = next ? WORD(next) : 0;
            u32 board = WORD(display)-0x1cu;
            if (first && second && !WORD(next+0x84u) &&
                WORD(first+4u) == 0x3806ab75u && WORD(second+4u) == 0x3806ab75u &&
                !BYTE(board+0x2d0u) && WORD(board+0x2a4u) == WORD(0x384ef8a0u) &&
                WORD(0x384ef8a0u) == 0x50000000u && WORD(0x384ef8a4u) == 614400u &&
                WORD(0x384ef898u) == 0x01e0000du &&
                (WORD(0x384ef89cu)&0xffffu) == 320u &&
                (WORD(0x384ef8a8u)&0xff00ffffu) == 0x20000780u &&
                WORD(0x384ef87cu) == 0x383df2dcu && WORD(0x384ef854u) == 0x383df474u) {
                u32 upper[2], subscriber[2];
                c->drivers[0] = first; c->drivers[1] = second;
                if (!channels(c,upper,subscriber) &&
                    ((upper[0] == WORD(0x384f50b0u)) != (upper[1] == WORD(0x384f50b0u)))) {
                    c->physical = upper[0] == WORD(0x384f50b0u) ? 0 : 1;
                    c->gesture.active = BYTE(WORD(c->drivers[c->physical]+0xcu)+4u) != 0;
                    WORD(first+4u) = (u32)touch; WORD(second+4u) = (u32)touch;
                    WORD(0x384ef87cu) = (u32)pan; WORD(0x384ef854u) = (u32)area;
                    c->ready = 1;
                }
            }
        }
        UNLOCK(c->mutex);
    }
    TIMER(handle); /* Always outside broker mutex: stock UI/JS continues. */
    if (c->alive && c->ready && !LOCK(c->mutex,0)) {
        struct { i64 seconds; int nanoseconds; int pad; } time;
        u32 step = 0;
        if (!CLOCK(1,&time)) {
            u32 now = (u32)time.seconds*1000u+(u32)time.nanoseconds/1000000u;
            c->clock_ms = now;
            u32 elapsed = now-c->animation_ms;
            step = (elapsed < 50 ? elapsed : 50)*2u;
            c->animation_ms = now;
            if (keys(c,now) && !c->gesture.active) {
                c->wanted ^= 1; ++c->toggles;
                if (c->overlay) c->target = c->wanted*320u;
            }
        } else key3_gesture_init(&c->keys,0);
        int released = c->released[0] && c->released[1] && BYTE(0x384f50a1u) != 1;
        if (!released) c->idle = 0;
        else if (c->idle < 2) ++c->idle;
        /* No delivered DOWN is pending on either GUI consumer at this point.
         * Queued, not-yet-delivered contacts are suppressed in full until the
         * publisher-locked final gate. No owner is committed at animation start. */
        if (!c->overlay && c->mode != c->wanted && c->idle == 2) {
            c->overlay = 1; c->target = c->wanted*320u; c->background = 0;
        }
        if (!WORD(0x384ef93cu)) {
            if (c->overlay) {
                if (!c->background) {
                    for (unsigned i = 0; i < 480u*320u; ++i)
                        c->snapshot[i] = WORD(0x50000000u+i*4u);
                    c->background = 1; c->shown = 0xffffffffu;
                }
                if (!c->gesture.active) {
                    if (c->cover < c->target) c->cover += step < c->target-c->cover ? step : c->target-c->cover;
                    else c->cover -= step < c->cover-c->target ? step : c->cover-c->target;
                }
                if (c->cover != c->shown || c->dirty) c->last_present = draw(c);
                else if (!c->gesture.active && c->cover == c->target && c->idle == 2)
                    c->last_present = handoff(c);
            } else if (c->mode && c->dirty) c->last_present = draw(c);
        }
        UNLOCK(c->mutex);
    }
    arm_timer(c);
}

static void *bootstrap(void *argument)
{
    struct broker *c = argument;
    struct { i64 seconds; int nanoseconds; int pad; } pause = {0,20000000,0};
    while (c->alive && !c->ready) { arm_timer(c); SLEEP(&pause,0); }
    return 0;
}

__attribute__((section(".text.entry")))
int broker_main(int argc, char **argv)
{
    struct broker *c = ALLOC(sizeof(*c));
    if (!c) return ORIGINAL(argc,argv);
    ZERO(c,0,sizeof(*c));
    c->pixels = ALLOC(1228800);
    if (!c->pixels) { FREE(c); return ORIGINAL(argc,argv); }
    c->snapshot = c->pixels+480u*320u;
    c->mutex[0] = 1; c->mutex[3] = 0xffffffffu;
    c->alive = 1; c->wanted = 1; c->shown = 0xffffffffu;
    key3_gesture_init(&c->keys,0);
    WORD(0x384fc864u) = (u32)c;
    __sync_synchronize();
    if (CREATE(&c->tid,0,bootstrap,c)) {
        FREE(c->pixels); FREE(c); WORD(0x384fc864u) = 0;
        return ORIGINAL(argc,argv);
    }
    int result = ORIGINAL(argc,argv);
    c->alive = 0;
    if (!LOCK(c->mutex,0)) {
        if (c->ready) {
            WORD(0x384ef87cu) = 0x383df2dcu; WORD(0x384ef854u) = 0x383df474u;
        }
        UNLOCK(c->mutex);
    }
    return result;
}
