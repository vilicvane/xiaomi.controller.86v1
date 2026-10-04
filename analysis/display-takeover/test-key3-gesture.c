#include "key3-gesture.h"
#include <assert.h>
#include <stdio.h>

struct fixture {
  struct key3_gesture s;
  uint32_t now;
  unsigned toggles;
};

static void sample(struct fixture *f, int down, int other)
{
  f->toggles += key3_gesture_sample(&f->s, f->now, down, other);
  f->now += 20;
}

static void level(struct fixture *f, int down, int other, unsigned ms)
{
  assert(ms % 20 == 0);
  while (ms) { sample(f, down, other); ms -= 20; }
}

static struct fixture fresh(uint32_t start)
{
  struct fixture f = { .now = start };
  key3_gesture_init(&f.s, f.now);
  level(&f, 0, 0, 60);
  return f;
}

static void tap(struct fixture *f, unsigned duration)
{
  level(f, 1, 0, duration);
  level(f, 0, 0, 80);
}

int main(void)
{
  struct fixture f;

  f = fresh(1000);
  tap(&f, 100); tap(&f, 100); tap(&f, 100);
  assert(f.toggles == 1);
  level(&f, 0, 0, 2000);
  assert(f.toggles == 1); /* No duplicate event on repeated release samples. */
  tap(&f, 100); tap(&f, 100);
  assert(f.toggles == 1);
  tap(&f, 100);
  assert(f.toggles == 2); /* Three fresh taps, not the old third release. */

  f = fresh(0);
  sample(&f, 1, 0); sample(&f, 0, 0); sample(&f, 1, 0);
  sample(&f, 0, 0); level(&f, 0, 0, 100);
  assert(f.s.taps == 0 && f.toggles == 0); /* Sub-40 ms bounce is not a tap. */
  level(&f, 1, 0, 60); sample(&f, 0, 0); sample(&f, 1, 0);
  level(&f, 0, 0, 80); /* Release bounce resolves to one completed tap. */
  assert(f.s.taps == 1);
  tap(&f, 100); tap(&f, 100);
  assert(f.toggles == 1);

  f = fresh(0);
  tap(&f, 100); tap(&f, 100); level(&f, 0, 0, 520);
  tap(&f, 100);
  assert(f.toggles == 0 && f.s.taps == 1); /* Expired sequence restarts. */

  f = fresh(0);
  tap(&f, 100); level(&f, 0, 0, 420);
  tap(&f, 100); level(&f, 0, 0, 420); tap(&f, 100);
  assert(f.toggles == 1); /* Exactly 500 ms raw release-to-press gap. */
  f = fresh(0);
  tap(&f, 100); level(&f, 0, 0, 440);
  tap(&f, 100); tap(&f, 100);
  assert(f.toggles == 0 && f.s.taps == 2); /* 520 ms starts a new sequence. */

  f = fresh(0);
  tap(&f, 600); tap(&f, 600); tap(&f, 600);
  assert(f.toggles == 1); /* Exact short-duration boundary, including debounce. */
  f = fresh(0);
  tap(&f, 100); tap(&f, 100); tap(&f, 620);
  assert(f.toggles == 0 && f.s.taps == 0);
  tap(&f, 100); tap(&f, 100); tap(&f, 100);
  assert(f.toggles == 1);

  f = fresh(0);
  tap(&f, 100); tap(&f, 100);
  level(&f, 1, 0, 60);
  f.now += 640; /* Native calls/scheduling delayed the next sample. */
  sample(&f, 1, 0); level(&f, 0, 0, 80);
  assert(f.toggles == 0 && f.s.taps == 0);

  f = fresh(0);
  tap(&f, 100); tap(&f, 100);
  level(&f, 1, 1, 100); level(&f, 1, 0, 100); level(&f, 0, 0, 80);
  assert(f.toggles == 0 && f.s.taps == 0); /* Combo and lingering key3 cancel. */
  tap(&f, 100); tap(&f, 100); tap(&f, 100);
  assert(f.toggles == 1);

  f = fresh(0);
  tap(&f, 100); tap(&f, 100);
  level(&f, 0, 1, 100); sample(&f, 1, 0); level(&f, 1, 0, 100);
  level(&f, 0, 0, 80);
  assert(f.toggles == 0); /* Other-key release cannot immediately arm key3. */

  f = (struct fixture){ .now = 0 };
  key3_gesture_init(&f.s, 0);
  level(&f, 1, 0, 1000); level(&f, 0, 0, 80);
  tap(&f, 100); tap(&f, 100);
  assert(f.toggles == 0); /* Boot-held key is never a first tap. */
  tap(&f, 100); assert(f.toggles == 1);

  f = fresh(UINT32_MAX - 200);
  tap(&f, 100); tap(&f, 100); tap(&f, 100);
  assert(f.toggles == 1); /* Monotonic clock rollover. */

  f = fresh(0);
  assert(!key3_gesture_gpio(&f.s, f.now, UINT32_C(0x0e000000)));
  assert(!key3_gesture_gpio(&f.s, f.now + 20, UINT32_C(0x0c000000)));
  assert(!key3_gesture_gpio(&f.s, f.now + 60, UINT32_C(0x08000000)));
  assert(f.s.blocked && f.s.taps == 0); /* GPIO adapter detects other key low. */

  puts("key3 gesture: all host scenarios passed");
  return 0;
}
