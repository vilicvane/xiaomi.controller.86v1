#ifndef MI_PANEL_KEY3_GESTURE_H
#define MI_PANEL_KEY3_GESTURE_H

#include <stdint.h>

/* 1.50.10: P3_1 is active-low. Call from a normal thread every 20 ms.
 * Timestamps are monotonic milliseconds modulo 2^32. Gesture windows must
 * not span a half-range of that clock. A tap completes only after release.
 * Times below refer to the onset of the finally debounced raw level.
 */
#define KEY3_GPIO_MASK UINT32_C(0x02000000)
#define KEY3_OTHER_GPIO_MASK UINT32_C(0x0c000000)
#define KEY3_DEBOUNCE_MS UINT32_C(40)
#define KEY3_SHORT_MS UINT32_C(600)
#define KEY3_GAP_MS UINT32_C(500)

struct key3_gesture {
  uint32_t changed_ms;
  uint32_t pressed_ms;
  uint32_t released_ms;
  uint8_t candidate;
  uint8_t stable;
  uint8_t armed;
  uint8_t taps;
  uint8_t blocked;
};

/* A held key at initialization must be released before a gesture can start. */
static inline void key3_gesture_init(struct key3_gesture *s, uint32_t now_ms)
{
  *s = (struct key3_gesture){ .changed_ms = now_ms, .blocked = 1 };
}

/* Returns 1 once on the third completed short tap. No callbacks or I/O.
 * Combination presses cancel the entire sequence and require a quiet
 * debounced release. A long hold does the same. After a toggle, repeated
 * samples of that release cannot retrigger; three fresh taps are required.
 */
static inline int key3_gesture_sample(struct key3_gesture *s, uint32_t now_ms,
                                      int down, int other_down)
{
  down = !!down;
  if (s->candidate != down) {
    s->candidate = (uint8_t)down;
    s->changed_ms = now_ms;
  }

  if (other_down) {
    s->blocked = 1;
    s->armed = s->taps = 0;
    /* Require 40 ms after the last observed combination, even if key3 is up. */
    s->changed_ms = now_ms;
    return 0;
  }

  if (s->blocked) {
    if (!down && (uint32_t)(now_ms - s->changed_ms) >= KEY3_DEBOUNCE_MS) {
      s->blocked = s->stable = s->armed = 0;
    }
    return 0;
  }

  if (s->stable != down &&
      (uint32_t)(now_ms - s->changed_ms) >= KEY3_DEBOUNCE_MS) {
    s->stable = (uint8_t)down;
    if (down) {
      if (s->taps &&
          (uint32_t)(s->changed_ms - s->released_ms) > KEY3_GAP_MS)
        s->taps = 0;
      s->pressed_ms = s->changed_ms;
      s->armed = 1;
    } else if (s->armed) {
      s->armed = 0;
      if ((uint32_t)(s->changed_ms - s->pressed_ms) <= KEY3_SHORT_MS) {
        s->released_ms = s->changed_ms;
        if (++s->taps == 3) {
          s->taps = 0;
          s->blocked = 1;
          return 1;
        }
      } else {
        s->taps = 0;
      }
    }
  }

  /* Do not reject an on-time release while its 40 ms debounce is pending. */
  if (s->armed && down &&
      (uint32_t)(now_ms - s->pressed_ms) > KEY3_SHORT_MS) {
    s->armed = s->taps = 0;
    s->blocked = 1;
  }
  if (s->taps && !s->stable && !down &&
      (uint32_t)(now_ms - s->released_ms) > KEY3_GAP_MS)
    s->taps = 0;
  return 0;
}

static inline int key3_gesture_gpio(struct key3_gesture *s, uint32_t now_ms,
                                    uint32_t gpio_input)
{
  return key3_gesture_sample(s, now_ms, !(gpio_input & KEY3_GPIO_MASK),
    (gpio_input & KEY3_OTHER_GPIO_MASK) != KEY3_OTHER_GPIO_MASK);
}

#endif
