/* 1.50.10 only. GUI-owned image drawer; independent network worker. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef unsigned short u16;
typedef signed long long i64;
#include "../display-takeover/key3-gesture.h"
#include "../display-takeover/drawer-gesture.h"
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
#define PREFIX __attribute__((section(".text.broker.prefix")))
#define SOCKET FN(int (*)(int,int,int),0x3802b529u)
#define BIND FN(int (*)(int,const void *,u32),0x381792edu)
#define LISTEN FN(int (*)(int,int),0x381794fdu)
#define ACCEPT FN(int (*)(int,void *,u32 *),0x38394355u)
#define RECEIVE FN(int (*)(int,void *,u32,int,void *,u32 *),0x38179785u)
#define SEND FN(int (*)(int,const void *,u32,int),0x381798a1u)
#define ERRNO FN(int *(*)(void),0x38018c5du)
#define CLOSE FN(int (*)(int),0x38025de1u)
#define IOCTL FN(int (*)(int,int,void *),0x38025c41u)
#define SNPRINTF FN(int (*)(char *,u32,const char *,...),0x3801a419u)


static const struct { i64 seconds; int nanoseconds,pad; } pause20
    __attribute__((section(".rodata"))) = {0,20000000,0};

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
    u32 animation_from, pending, phase;
    u16 *image, *receive;
    volatile u32 image_pending;
    u32 generation, displayed_generation;
    volatile u32 server_state, server_error, received;
    u32 ipv4;

};
#define CTX ((struct broker *)WORD(0x384fc864u))
static void timer(void *handle);
static void begin(struct broker *c)
{
    c->animation_from = c->shown <= 320 ? c->shown : c->cover;
    c->cover = c->animation_from; c->pending = 1; c->phase = 0;
}
__attribute__((section(".text.broker.prefix")))
static int clock_value(u32 *output)
{
    struct { i64 seconds; int nanoseconds; int pad; } time;
    int result = CLOCK(1,&time);
    if (!result) *output = (u32)time.seconds*1000u+(u32)time.nanoseconds/1000000u;
    return result;
}
#define clock_ms(c) clock_value(&(c)->clock_ms)
__attribute__((noinline))
static int submit(void *device,void *argument,int is_area)
{
    struct broker *c = CTX;
    if (LOCK(c->mutex,0)) return -1;
    int result = (!is_area && ((u32 *)argument)[6] == 0xffffffffu) ? -1 :
                 (c->mode || c->overlay) ? 0 :
                 (is_area ? AREA(device,argument) : PAN(device,argument));
    UNLOCK(c->mutex);
    return result;
}
static int pan(void *device,const u32 *plane) { return submit(device,(void *)plane,0); }
static int area(void *device,void *rectangle) { return submit(device,rectangle,1); }

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
                if (c->overlay) begin(c);
                if (c->wanted != c->mode) ++c->toggles;
            }
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

/* Original two-publisher owner transaction; no network waits while locked. */
__attribute__((section(".text.feedback.handoff"),noinline)) static int handoff(struct broker *c)
{
    u32 upper[2], subscriber[2];
    if (channels(c,upper,subscriber) < 0) return -1;
    if (NLOCK((void *)(upper[0]+4u))) return -1;
    if (upper[1] != upper[0] && NLOCK((void *)(upper[1]+4u))) {
        NUNLOCK((void *)(upper[0]+4u)); return -1;
    }
    int result = -1;
    int empty = c->released[0] && c->released[1] &&
                BYTE(0x384f50a1u) != 1 && !c->gesture.active;
    for (unsigned i = 0; i < 2; ++i)
        if (WORD(subscriber[i]+8u) != WORD(subscriber[i]+0xcu)) empty = 0;
    if (empty) {
            if (!WORD(0x384ef93cu)) {
                u32 plane[7]; ZERO(plane,0,sizeof(plane));
                plane[6] = c->wanted ? (u32)c->pixels : 0;
                result = PAN(DEVICE,plane);
                if (result >= 0) { c->mode = c->wanted; c->overlay = 0; c->dirty = 0; }
            }
    }
    if (upper[1] != upper[0]) NUNLOCK((void *)(upper[1]+4u));
    NUNLOCK((void *)(upper[0]+4u));
    return result;
}

PREFIX __attribute__((noinline))
static void compose(struct broker *c)
{
    u32 limit = c->cover*480u, generation = c->generation;
    u32 *output = c->pixels, *background = c->snapshot;
    u16 *source = c->image+(320u-c->cover)*480u;
    for (u32 i = 0; i < limit; ++i) {
        u32 v = generation ? source[i] : 0x1082u;
        u32 r = (v >> 11)&31u, g = (v >> 5)&63u, b = v&31u;
        output[i] = 0xff000000u | ((r<<3)|(r>>2))<<16 |
                      ((g<<2)|(g>>4))<<8 | (b<<3)|(b>>2);
    }
    for (u32 i = limit; i < 480u*320u; ++i) output[i] = background[i];
}
const u16 digits[12] = {0x7b6f,0x2492,0x73e7,0x79e7,0x49ed,0x79cf,
                              0x7bcf,0x4927,0x7bef,0x79ef,0x2000,0x0410};
extern void glyph(struct broker *,u32,u32);
static void address_text(struct broker *c)
{
    char text[24];
    const u8 *ip = (const u8 *)&c->ipv4;
    int size = SNPRINTF(text,sizeof(text),"%u.%u.%u.%u:18086",ip[0],ip[1],ip[2],ip[3]);
    if ((u32)size >= sizeof(text)) return;
    for (u32 i = 0; text[i]; ++i)
        glyph(c,114+i*12,text[i] == '.' ? 10u : text[i] == ':' ? 11u : (u32)(text[i]-'0'));
}
static int draw(struct broker *c)
{
    compose(c);
    if (!c->generation) address_text(c);
    u32 plane[7]; ZERO(plane,0,sizeof(plane)); plane[6] = (u32)c->pixels;
    int result = PAN(DEVICE,plane);
    if (result >= 0) {
        c->shown = c->cover; c->dirty = 0;
        c->displayed_generation = c->generation;
    }
    return result;
}

PREFIX __attribute__((noinline)) static int keys(struct broker *c, u32 now)
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
        int clock_valid = !clock_ms(c);
        if (clock_valid) {
            u32 now = c->clock_ms;
            if (keys(c,now) && !c->gesture.active) {
                c->wanted ^= 1; ++c->toggles;
                if (c->overlay) {
                    c->target = c->wanted*320u;
                    begin(c);
                }
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
            begin(c);
        }
        if (!WORD(0x384ef93cu)) {
            if (c->image_pending && !c->overlay && !c->gesture.active) {
                u16 *old = c->image; c->image = c->receive; c->receive = old;
                ++c->generation; c->dirty = 1; c->image_pending = 0;
            }
            if (c->overlay) {
                if (!c->background) {
                    for (unsigned i = 0; i < 480u*320u; ++i)
                        c->snapshot[i] = WORD(0x50000000u+i*4u);
                    c->background = 1; c->shown = 0xffffffffu;
                }
                if (c->gesture.active) {
                    if (c->cover != c->shown || c->dirty) c->last_present = draw(c);
                } else if (clock_valid) {
                    if (c->phase >= 150 && c->dirty) c->last_present = draw(c);
                    else if (c->pending || c->phase < 150) {
                        u32 phase = c->phase;
                        if (!c->pending) {
                            u32 elapsed = c->clock_ms-c->animation_ms;
                            phase += elapsed < 30 ? elapsed : 30;
                            if (phase > 150) phase = 150;
                        }
                        int delta = (int)c->target-(int)c->animation_from;
                        /* Smoothstep: maximum product 320*150^3 fits int32.
                         * Admit even rounded identical poses so phase cannot stall. */
                        c->cover = c->animation_from+delta*(int)phase*(int)phase*(450-2*(int)phase)/3375000;
                        u32 proposed_ms = c->clock_ms;
                        c->last_present = draw(c);
                        if (c->last_present >= 0 && !clock_ms(c)) {
                            c->phase = phase;
                            c->animation_ms = c->pending ? c->clock_ms : proposed_ms;
                            c->pending = 0;
                        }
                    } else if (c->idle == 2) c->last_present = handoff(c);
                }
            } else if (c->mode && c->dirty) c->last_present = draw(c);
        }
        UNLOCK(c->mutex);
    }
    arm_timer(c);
}

/* Fixed binary transport: little-endian VIMG,width16,height16,length32,FNV1a32.
 * All accepted socket I/O happens on this worker, never the GUI callback. */
__attribute__((section(".text.feedback.exact"),noinline))
static int exact(int fd, u8 *data, u32 bytes, u32 start, u32 sending)
{
    u32 last;
    if (clock_value(&last)) return -1;
    while (bytes) {
        u32 now;
        if (clock_value(&now) || now-start >= 30000u || now-last >= 5000u) return -1;
        int n = sending ? SEND(fd,data,bytes,0x40) : RECEIVE(fd,data,bytes,0x40,0,0);
        if (n > 0 && (u32)n <= bytes) { data += n; bytes -= (u32)n; last = now; }
        else if (n < 0 && (*ERRNO() == 11 || *ERRNO() == 4)) SLEEP(&pause20,0);
        else return -1;
    }
    return 0;
}
static void server(struct broker *c)
{
    struct { u16 family,port; u32 address; u8 zero[8]; } addr = {2,0xa646,0,{0}};
    int listener = SOCKET(2,0x801,0);
    if (listener < 0) { c->server_error = 1; return; }
    if (BIND(listener,&addr,16) || LISTEN(listener,1)) {
        c->server_error = 2; CLOSE(listener); return;
    }
    c->server_state = 1;
    while (c->alive) {
        if (c->image_pending) { SLEEP(&pause20,0); continue; }
        if (!c->ipv4) {
            u32 request[10]; ZERO(request,0,sizeof(request)); request[0] = 0x6e616c77u; request[1] = 0x30u;
            if (!IOCTL(listener,0x701,request) && (request[5]&0xffffu) == 2u && request[6] && !LOCK(c->mutex,0)) {
                c->ipv4 = request[6]; c->dirty = 1; UNLOCK(c->mutex);
            }
        }
        int fd = ACCEPT(listener,0,0);
        if (fd < 0) {
            int error = *ERRNO(); if (error != 11 && error != 4) c->server_error = 3;
            SLEEP(&pause20,0); continue;
        }
        u32 status = 1, header[4], reply[2] = {0x4b434156u,1}, start;
        c->server_state = 2;
        if (!clock_value(&start) && !exact(fd,(u8 *)header,16,start,0) && header[0] == 0x474d4956u &&
            header[1] == 0x014001e0u && header[2] == 307200u) {
            u8 *destination = 0;
            if (!LOCK(c->mutex,0)) { destination = (u8 *)c->receive; UNLOCK(c->mutex); }
            if (destination && !exact(fd,destination,307200u,start,0)) {
                u32 checksum = 2166136261u;
                for (u32 i = 0; i < 307200u; ++i) checksum = (checksum^destination[i])*16777619u;
                status = 2;
                if (checksum == header[3] && !LOCK(c->mutex,0)) {
                    if (c->alive) { c->image_pending = 1; status = 0; }
                    UNLOCK(c->mutex);
                }
            }
        }
        reply[1] = status;
        if (!clock_value(&start)) exact(fd,(u8 *)reply,8,start,1);
        CLOSE(fd);
        c->server_error = status; c->server_state = 1;
    }
    CLOSE(listener); c->server_state = 0;
}
static void *bootstrap(void *argument)
{
    struct broker *c = argument;
    while (c->alive && !c->ready) { arm_timer(c); SLEEP(&pause20,0); }
    if (c->alive) server(c);
    return 0;
}

__attribute__((section(".text.entry")))
int broker_main(int argc, char **argv)
{
    struct broker *c = ALLOC(sizeof(*c));
    if (!c) return ORIGINAL(argc,argv);
    ZERO(c,0,sizeof(*c));
    c->pixels = ALLOC(1843200);
    if (!c->pixels) { FREE(c); return ORIGINAL(argc,argv); }
    c->snapshot = c->pixels+480u*320u;
    c->image = (u16 *)(c->pixels+2u*480u*320u);
    c->receive = c->image+480u*320u;
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
