#ifndef MI_PANEL_TAP_GESTURE_H
#define MI_PANEL_TAP_GESTURE_H

#include <stdint.h>

#define TAP_HOLD_MS 300u
#define TAP_GAP_MS 350u
#define TAP_DISTANCE 32

/* The drawer recognizer supplies motion-qualified physical contact releases. */
struct tap_gesture {
    uint32_t pressed_ms, released_ms;
    int16_t x, y;
    uint8_t waiting, armed, wake_contact;
};

static inline void tap_gesture_cancel(struct tap_gesture *s)
{
    s->waiting = s->armed = 0;
}

static inline void tap_gesture_press(struct tap_gesture *s, uint32_t now)
{
    s->pressed_ms = now;
    s->armed = 1;
}

/* Times are monotonic milliseconds modulo 2^32. A successful pair is consumed. */
static inline int tap_gesture_release(struct tap_gesture *s, uint32_t now,
                                      int16_t x, int16_t y)
{
    if (!s->armed || (uint32_t)(now - s->pressed_ms) > TAP_HOLD_MS) {
        tap_gesture_cancel(s);
        return 0;
    }
    s->armed = 0;
    int dx = (int)x - s->x, dy = (int)y - s->y;
    if (s->waiting && (uint32_t)(now - s->released_ms) <= TAP_GAP_MS &&
        dx >= -TAP_DISTANCE && dx <= TAP_DISTANCE &&
        dy >= -TAP_DISTANCE && dy <= TAP_DISTANCE &&
        dx*dx + dy*dy <= TAP_DISTANCE*TAP_DISTANCE) {
        s->waiting = 0;
        return 1;
    }
    s->released_ms = now;
    s->x = x; s->y = y; s->waiting = 1;
    return 0;
}

#endif
