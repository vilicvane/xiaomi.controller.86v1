#include "panel.h"

const struct panel_timespec pause20
    __attribute__((section(".rodata"))) = {0,20000000,0};

static void timer(void *handle);
static void begin(struct broker *c)
{
    c->animation_from = c->shown <= 320 ? c->shown : c->cover;
    c->cover = c->animation_from; c->pending = 1; c->phase = 0;
}
__attribute__((section(".text.broker.prefix")))
int panel_clock(u32 *output)
{
    struct { i64 seconds; int nanoseconds; int pad; } time;
    int result = CLOCK(1,&time);
    if (!result) *output = (u32)time.seconds*1000u+(u32)time.nanoseconds/1000000u;
    return result;
}
#define clock_ms(c) panel_clock(&(c)->clock_ms)
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

PREFIX __attribute__((noinline))
static void tap(struct broker *c, int down, int started, unsigned event)
{
    u32 now;
    if (!c->mode || c->overlay || c->screen_off || WORD(PANEL_SCREEN_STATE) != 1) {
        tap_gesture_cancel(&c->taps);
    } else if (started && down) {
        if (panel_clock(&now)) tap_gesture_cancel(&c->taps);
        else tap_gesture_press(&c->taps,now);
    } else if (event & DRAWER_RELEASE) {
        if (!(event & DRAWER_TAP) || panel_clock(&now)) tap_gesture_cancel(&c->taps);
        else if (tap_gesture_release(&c->taps,now,c->gesture.x0,c->gesture.y0)) {
            c->show_address ^= 1; c->dirty = 1;
        }
    }
}

static void touch(void *driver, u8 *data)
{
    struct broker *c = CTX;
    TOUCH(driver,data);
    if (LOCK(c->mutex,0)) { data[0x12] = 0; return; }
    unsigned i = (u32)driver == c->drivers[0] ? 0 : 1;
    int down = data[0x12] != 0;
    c->released[i] = !down && !data[0x13];
    /* Exclude the first wake contact from double tap, including contacts
     * swallowed during animation. Drawer swipes remain active. */
    if (i == c->physical && c->screen_off) {
        tap_gesture_cancel(&c->taps);
        if (down) c->taps.wake_contact = 1;
        else if (c->taps.wake_contact && WORD(PANEL_SCREEN_STATE) == 1) {
            c->taps.wake_contact = 0; c->screen_off = 0;
        }
    }
    if (i == c->physical && !(c->overlay && !c->gesture.active) &&
        (data[0x13] || !down)) {
        int x = (int)WORD((u32)data), y = (int)WORD((u32)data+4u);
        c->last_x = x; c->last_y = y;
        /* Do not truncate an already delivered virtual DOWN/UP pair. */
        if (!c->mode && !c->gesture.active && !c->released[i^1u]) y = 21;
        int started = !c->gesture.active;
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
        tap(c,down,started,event);
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
                if (result >= 0) {
                    c->mode = c->wanted; c->overlay = 0; c->dirty = 0;
                    tap_gesture_cancel(&c->taps);
                }
            }
    }
    if (upper[1] != upper[0]) NUNLOCK((void *)(upper[1]+4u));
    NUNLOCK((void *)(upper[0]+4u));
    return result;
}

PREFIX __attribute__((noinline))
static void compose(struct broker *c)
{
    u32 limit = c->cover*480u, image = c->generation && !c->show_address;
    u32 *output = c->pixels, *background = c->snapshot;
    u16 *source = c->image+(320u-c->cover)*480u;
    for (u32 i = 0; i < limit; ++i) {
        u32 v = image ? source[i] : 0x1082u;
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
    if (!c->generation || c->show_address) address_text(c);
    u32 plane[7]; ZERO(plane,0,sizeof(plane)); plane[6] = (u32)c->pixels;
    int result = PAN(DEVICE,plane);
    if (result >= 0) {
        c->shown = c->cover; c->dirty = 0;
        if (!c->show_address && c->cover) c->displayed_generation = c->generation;
    }
    return result;
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
        /* panel_apps owns backlight and wake. Only prepare the custom owner. */
        u32 screen_state = WORD(PANEL_SCREEN_STATE);
        if (!screen_state) {
            c->screen_off = 1;
            tap_gesture_cancel(&c->taps);
            if (!c->wanted) {
                c->wanted = 1; ++c->toggles;
                if (c->overlay) { c->target = 320; begin(c); }
            }
        } else if (screen_state == 1 && c->screen_off == 1) c->screen_off = 2;
        int released = c->released[0] && c->released[1] && BYTE(0x384f50a1u) != 1;
        if (!released) c->idle = 0;
        else if (c->idle < 2) ++c->idle;
        /* No delivered DOWN is pending on either GUI consumer at this point.
         * Queued, not-yet-delivered contacts are suppressed in full until the
         * publisher-locked final gate. No owner is committed at animation start. */
        if (!c->overlay && c->mode != c->wanted && c->idle == 2) {
            tap_gesture_cancel(&c->taps);
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

static void *bootstrap(void *argument)
{
    struct broker *c = argument;
    while (c->alive && !c->ready) { arm_timer(c); SLEEP(&pause20,0); }
    if (c->alive) panel_server(c);
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
