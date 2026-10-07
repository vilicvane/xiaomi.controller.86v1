#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "drawer-gesture.h"
#include "tap-gesture.h"

static int click(struct tap_gesture *s, uint32_t press, uint32_t release,
                 int16_t x, int16_t y)
{
    tap_gesture_press(s,press);
    return tap_gesture_release(s,release,x,y);
}

int main(void)
{
    struct tap_gesture s = {0};
    assert(sizeof(s) == 16);
    assert(!tap_gesture_release(&s,0,100,100));
    assert(!click(&s,10,50,100,100));
    assert(click(&s,300,400,132,100));
    assert(!s.waiting);
    assert(!click(&s,410,450,100,100));
    assert(click(&s,500,550,100,100));
    assert(!s.waiting);

    tap_gesture_cancel(&s);
    assert(!click(&s,10,50,100,100));
    assert(!click(&s,351,401,100,100));
    assert(click(&s,410,450,100,100));

    assert(!click(&s,460,500,100,100));
    assert(!click(&s,510,550,133,100));
    assert(click(&s,560,600,133,100));

    assert(!click(&s,610,650,100,100));
    assert(!click(&s,660,700,132,132));
    assert(click(&s,710,750,132,132));

    assert(!click(&s,760,800,100,100));
    assert(!click(&s,810,1111,100,100));
    assert(!s.waiting && !s.armed);
    assert(!click(&s,1120,1420,100,100));
    tap_gesture_cancel(&s);
    assert(!click(&s,1430,1450,100,100));
    assert(click(&s,1460,1480,100,100));

    tap_gesture_cancel(&s);
    assert(!click(&s,UINT32_MAX-120,50,100,100));
    assert(click(&s,100,150,100,100));

    /* UP coordinates can be invalid: the drawer retains initial contact x/y. */
    struct drawer_gesture d = {0};
    assert(drawer_gesture_sample(&d,1,100,100,320) == DRAWER_CAPTURE);
    assert(drawer_gesture_sample(&d,0,-1,-1,320) & DRAWER_TAP);
    assert(d.x0 == 100 && d.y0 == 100);
    drawer_gesture_sample(&d,1,100,100,320);
    drawer_gesture_sample(&d,1,100,87,320);
    assert(!(drawer_gesture_sample(&d,0,0,0,320) & DRAWER_TAP));
    drawer_gesture_sample(&d,1,100,100,320);
    drawer_gesture_sample(&d,1,150,90,320);
    assert(!(drawer_gesture_sample(&d,0,0,0,320) & DRAWER_TAP));
    puts("Tap timing, location, contact cancellation and drawer release checks passed.");
    return 0;
}
