/* Exact 1.50.10 ABI prototype. Not an installer; original main runs once. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef signed long long i64;
#include "key3-gesture.h"
#define FN(type, address) ((type)(address))
#define OPEN FN(int (*)(const char *, int), 0x3802c901u)
#define IOCTL FN(int (*)(int, int, void *), 0x38025c41u)
#define GETFILE FN(int (*)(int, void **), 0x38025679u)
#define READ FN(int (*)(void *, void *, u32), 0x3802954du)
#define CLOSE FN(int (*)(int), 0x38025d21u)
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
    u32 *pixels;
    void *input_file;
    u32 mode, wanted, ready, dirty, count, idle, pressed;
    u32 drivers[2], released[2];
    u32 gpio, clock_ms, worker_cycles, gui_cycles, toggles;
    int last_present;
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

__attribute__((section(".text.broker.prefix")))
static void paint(u32 *pixels, u32 count)
{
    char text[22], reverse[10];
    unsigned length = 0, digits = 0;
    while (prefix[length]) { text[length] = prefix[length]; ++length; }
    do { reverse[digits++] = (char)('0'+count%10); count /= 10; } while (count);
    while (digits) text[length++] = reverse[--digits];
    for (unsigned y = 140; y < 172; ++y)
        for (unsigned x = 0; x < 480; ++x) pixels[y*480+x] = 0xff101010u;
    unsigned left = (480-length*18)/2;
    for (unsigned c = 0; c < length; ++c) {
        if (text[c] == ' ') continue;
        unsigned glyph = 0;
        while (alphabet[glyph] && alphabet[glyph] != text[c]) ++glyph;
        if (!alphabet[glyph]) continue;
        for (unsigned y = 0; y < 21; ++y)
            for (unsigned x = 0; x < 15; ++x)
                if (font[glyph][y/3] & (16u >> (x/3)))
                    pixels[(145+y)*480+left+c*18+x] = 0xffffffffu;
    }
}

/* Both submission routes are guarded. Do not allow fbmem relocation. */
static int pan(void *device, const u32 *plane)
{
    struct broker *c = CTX;
    if (LOCK(c->mutex,0)) return -1;
    int result = plane[6] == 0xffffffffu ? -1 :
                 c->mode ? 0 : PAN(device,plane);
    UNLOCK(c->mutex);
    return result;
}

static int area(void *device, void *rectangle)
{
    struct broker *c = CTX;
    if (LOCK(c->mutex,0)) return -1;
    int result = c->mode ? 0 : AREA(device,rectangle);
    UNLOCK(c->mutex);
    return result;
}

static void touch(void *driver, u8 *data)
{
    struct broker *c = CTX;
    TOUCH(driver,data); /* Always drain the original subscriber. */
    if (LOCK(c->mutex,0)) { data[0x12] = 0; return; }
    unsigned i = (u32)driver == c->drivers[0] ? 0 : 1;
    c->released[i] = !data[0x12] && !data[0x13];
    if (c->mode) data[0x12] = 0;
    UNLOCK(c->mutex);
}

static void arm_timer(struct broker *c)
{
    if (c->alive && BYTE(0x384fce30u) == 13 && !(WORD(0x384fce54u)&3u) &&
        (int)WORD(0x384fce20u) >= 0)
        __sync_bool_compare_and_swap((u32 *)0x384fce58u,0x3806a93du,(u32)timer);
}

/* Freeze publishers while choosing the new owner; all three rings must be empty.
 * READ uses subscriber locks; publishers instead hold the device upper mutex.
 * The GUI thread is the sole consumer of its two descriptors. */
static int present(struct broker *c, u32 source)
{
    void *files[3];
    u32 upper[3], subscriber[3];
    files[2] = c->input_file;
    for (unsigned i = 0; i < 3; ++i) {
        if (i < 2 && GETFILE((int)WORD(WORD(c->drivers[i]+0xcu)),&files[i]) < 0) return -1;
        if (!files[i]) return -1;
        u32 inode = WORD((u32)files[i]+0x10u);
        if (WORD(inode+0x10u) != 0x384b621cu) return -1;
        upper[i] = WORD(inode+0x18u);
        subscriber[i] = WORD((u32)files[i]+0x14u);
    }
    if (upper[2] != upper[0] && upper[2] != upper[1]) return -1;
    if (NLOCK((void *)(upper[0]+4u))) return -1;
    if (upper[1] != upper[0] && NLOCK((void *)(upper[1]+4u))) {
        NUNLOCK((void *)(upper[0]+4u)); return -1;
    }
    int result = -1;
    int empty = !c->pressed && BYTE(0x384f50a1u) != 1 && !WORD(0x384ef93cu);
    for (unsigned i = 0; i < 3; ++i)
        if (WORD(subscriber[i]+8u) != WORD(subscriber[i]+0xcu)) empty = 0;
    if (empty) {
        u32 plane[7]; ZERO(plane,0,sizeof(plane)); plane[6] = source;
        result = PAN(DEVICE,plane);
        if (result >= 0) c->mode = c->wanted;
    }
    if (upper[1] != upper[0]) NUNLOCK((void *)(upper[1]+4u));
    NUNLOCK((void *)(upper[0]+4u));
    return result;
}

static void timer(void *handle)
{
    struct broker *c = CTX;
    if ((u32)handle != 0x384fce28u) { TIMER(handle); return; }
    ++c->gui_cycles;
    /* Installation executes in the GUI thread, never across a half-made list. */
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
                c->drivers[0] = first; c->drivers[1] = second;
                WORD(first+4u) = (u32)touch; WORD(second+4u) = (u32)touch;
                WORD(0x384ef87cu) = (u32)pan; WORD(0x384ef854u) = (u32)area;
                c->ready = 1;
            }
        }
        UNLOCK(c->mutex);
    }
    TIMER(handle); /* Original UI/JS timers continue; it re-registers itself. */
    if (c->alive && c->ready && !LOCK(c->mutex,0)) {
        int released = c->released[0] && c->released[1] && !c->pressed &&
                       BYTE(0x384f50a1u) != 1;
        if (c->mode != c->wanted) {
            /* Two complete GUI scans after release, with the old frame drained. */
            if (!released) c->idle = 0;
            else if (c->idle < 2) ++c->idle;
            else if (!WORD(0x384ef93cu)) {
                c->last_present = present(c,c->wanted ? (u32)c->pixels : 0);
                if (c->last_present >= 0) {
                    c->dirty = 0; c->idle = 0;
                }
            }
        } else if (c->mode && c->dirty && !WORD(0x384ef93cu)) {
            u32 plane[7]; ZERO(plane,0,sizeof(plane)); plane[6] = (u32)c->pixels;
            c->last_present = PAN(DEVICE,plane);
            if (c->last_present >= 0) c->dirty = 0;
        }
        UNLOCK(c->mutex);
    }
    arm_timer(c);
}

static void *worker(void *argument)
{
    struct broker *c = argument;
    struct { i64 seconds; int nanoseconds; int pad; } pause = {0,20000000,0};
    struct key3_gesture keys;
    struct { i64 seconds; int nanoseconds; int pad; } time;
    key3_gesture_init(&keys,0);
    u32 sample[8];
    void *input_file = 0;
    int input = OPEN("/dev/input0",0x41);
    if (input < 0 || GETFILE(input,&input_file) < 0) goto done;
    c->input_file = input_file;
    for (unsigned i = 0; i < 480u*320u; ++i) c->pixels[i] = 0xff101010u;
    paint(c->pixels,0);
    while (c->alive) {
        int toggle = 0;
        if (!CLOCK(1,&time)) {
            u32 now = (u32)time.seconds*1000u+(u32)time.nanoseconds/1000000u;
            c->clock_ms = now; c->gpio = WORD(0x40081050u);
            toggle = key3_gesture_gpio(&keys,now,c->gpio);
        } else key3_gesture_init(&keys,0);
        ++c->worker_cycles;
        if (!LOCK(c->mutex,0)) {
            if (toggle && c->ready) { c->wanted ^= 1; c->idle = 0; ++c->toggles; }
            for (unsigned n = 0; n < 16 && READ(input_file,sample,32) == 32; ++n) {
                if (sample[0] != 1) continue;
                u8 flags = ((u8 *)sample)[9];
                if (flags & 4) c->pressed = 0;
                else if ((flags & 3) && !c->pressed) {
                    c->pressed = 1;
                    if (c->mode && c->wanted) { paint(c->pixels,++c->count); c->dirty = 1; }
                }
            }
            UNLOCK(c->mutex);
        }
        arm_timer(c);
        SLEEP(&pause,0);
    }
done:
    if (input >= 0) CLOSE(input);
    return 0;
}

__attribute__((section(".text.entry")))
int broker_main(int argc, char **argv)
{
    struct broker *c = ALLOC(sizeof(*c));
    if (!c) return ORIGINAL(argc,argv);
    ZERO(c,0,sizeof(*c));
    c->pixels = ALLOC(614400);
    if (!c->pixels) { FREE(c); return ORIGINAL(argc,argv); }
    c->mutex[0] = 1; c->mutex[3] = 0xffffffffu;
    c->alive = 1; c->wanted = 1;
    c->pressed = BYTE(0x384f50a1u) == 1;
    WORD(0x384fc864u) = (u32)c;
    __sync_synchronize();
    if (CREATE(&c->tid,0,worker,c)) {
        FREE(c->pixels); FREE(c); WORD(0x384fc864u) = 0;
        return ORIGINAL(argc,argv);
    }
    int result = ORIGINAL(argc,argv);
    c->alive = 0;
    /* No stop/restart/signals, no freed input-node access, no canvas free. */
    if (!LOCK(c->mutex,0)) {
        if (c->ready) {
            WORD(0x384ef87cu) = 0x383df2dcu; WORD(0x384ef854u) = 0x383df474u;
        }
        UNLOCK(c->mutex);
    }
    return result;
}
