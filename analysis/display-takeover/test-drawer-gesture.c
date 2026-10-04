#include "drawer-gesture.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>

static unsigned sample(struct drawer_gesture *s, int down, int x, int y,
                       unsigned cover)
{
  return drawer_gesture_sample(s, down, (int16_t)x, (int16_t)y, cover);
}

static void stock_top_contact(void)
{
  struct drawer_gesture s = {0};
  assert(sample(&s, 1, 140, 20, 0) == DRAWER_CAPTURE);
  assert(s.cover == 0);
  assert(sample(&s, 1, 140, 100, 0) == DRAWER_CAPTURE);
  assert(s.cover == 80);
  assert(sample(&s, 0, 0, 0, 0) == (DRAWER_CAPTURE | DRAWER_RELEASE));
  assert(s.target == DRAWER_HEIGHT); /* Inclusive 80px release threshold. */
  assert(!sample(&s, 0, 0, 0, 0)); /* Repeated UP cannot trigger twice. */
}

static void stock_short_contact(void)
{
  struct drawer_gesture s = {0};
  sample(&s, 1, 140, 0, 0);
  sample(&s, 1, 140, 79, 0);
  assert(s.cover == 79);
  assert(sample(&s, 0, 140, 320, 0) == (DRAWER_CAPTURE | DRAWER_RELEASE));
  assert(!s.target); /* UP's stale/zero coordinates never change the result. */
}

static void stock_outside_contact(void)
{
  struct drawer_gesture s = {0};
  assert(!sample(&s, 1, 140, 21, 0));
  assert(!sample(&s, 1, 140, 0, 0));
  assert(!sample(&s, 1, 140, 300, 0));
  assert(!sample(&s, 0, 140, 300, 0));
  assert(!s.active); /* Stock receives the complete contact without capture. */
  assert(sample(&s, 1, 140, 0, 0) == DRAWER_CAPTURE);
}

static void horizontal_cancel(void)
{
  struct drawer_gesture s = {0};
  sample(&s, 1, 100, 0, 0);
  sample(&s, 1, 101, 40, 0);
  assert(s.cover == 40);
  assert(sample(&s, 1, 170, 50, 0) == DRAWER_CAPTURE);
  assert(s.cancelled && !s.cover);
  assert(sample(&s, 1, 100, 200, 0) == DRAWER_CAPTURE);
  assert(!s.cover); /* Returning to a vertical route cannot uncancel. */
  assert(sample(&s, 0, 100, 200, 0) == (DRAWER_CAPTURE | DRAWER_RELEASE));
  assert(!s.target);
}

static void custom_close(void)
{
  struct drawer_gesture s = {0};
  assert(sample(&s, 1, 100, 300, DRAWER_HEIGHT) == DRAWER_CAPTURE);
  sample(&s, 1, 105, 220, DRAWER_HEIGHT);
  assert(s.cover == 240);
  assert(sample(&s, 0, 0, 0, DRAWER_HEIGHT) ==
         (DRAWER_CAPTURE | DRAWER_RELEASE));
  assert(!s.target); /* Inclusive 80px upward motion closes. */
}

static void custom_short_close(void)
{
  struct drawer_gesture s = {0};
  sample(&s, 1, 100, 300, DRAWER_HEIGHT);
  sample(&s, 1, 100, 221, DRAWER_HEIGHT);
  assert(s.cover == 241);
  assert(sample(&s, 0, 0, 0, DRAWER_HEIGHT) ==
         (DRAWER_CAPTURE | DRAWER_RELEASE));
  assert(s.target == DRAWER_HEIGHT);
}

static void custom_tap_once(void)
{
  struct drawer_gesture s = {0};
  unsigned taps = 0, i, event;
  sample(&s, 1, 200, 100, DRAWER_HEIGHT);
  for (i = 0; i < 100; ++i)
    assert(sample(&s, 1, 200, 100, DRAWER_HEIGHT) == DRAWER_CAPTURE);
  /* An arbitrarily held contact counts once on release, not on repeated DOWN. */
  event = sample(&s, 0, 0, 0, DRAWER_HEIGHT);
  taps += !!(event & DRAWER_TAP);
  assert(event == (DRAWER_CAPTURE | DRAWER_RELEASE | DRAWER_TAP));
  assert(!sample(&s, 0, 0, 0, DRAWER_HEIGHT));
  sample(&s, 1, 200, 100, DRAWER_HEIGHT);
  taps += !!(sample(&s, 0, 0, 0, DRAWER_HEIGHT) & DRAWER_TAP);
  assert(taps == 2);
}

static void custom_tap_slop(void)
{
  struct drawer_gesture s = {0};
  sample(&s, 1, 200, 100, DRAWER_HEIGHT);
  sample(&s, 1, 212, 112, DRAWER_HEIGHT);
  assert(sample(&s, 0, 0, 0, DRAWER_HEIGHT) & DRAWER_TAP);
  sample(&s, 1, 200, 100, DRAWER_HEIGHT);
  sample(&s, 1, 200, 113, DRAWER_HEIGHT);
  sample(&s, 1, 200, 100, DRAWER_HEIGHT);
  assert(!(sample(&s, 0, 0, 0, DRAWER_HEIGHT) & DRAWER_TAP));
  assert(s.target == DRAWER_HEIGHT); /* Moving away then back is still a drag. */
}

static void custom_wrong_direction(void)
{
  struct drawer_gesture s = {0};
  sample(&s, 1, 200, 100, DRAWER_HEIGHT);
  sample(&s, 1, 200, 220, DRAWER_HEIGHT);
  assert(s.cover == DRAWER_HEIGHT); /* Pulling down cannot expose stock. */
  assert(sample(&s, 0, 0, 0, DRAWER_HEIGHT) ==
         (DRAWER_CAPTURE | DRAWER_RELEASE));
  assert(s.target == DRAWER_HEIGHT);
}

static void custom_horizontal_cancel(void)
{
  struct drawer_gesture s = {0};
  sample(&s, 1, 100, 300, DRAWER_HEIGHT);
  sample(&s, 1, 170, 250, DRAWER_HEIGHT);
  assert(s.cancelled && s.cover == DRAWER_HEIGHT);
  sample(&s, 1, 100, 100, DRAWER_HEIGHT);
  assert(sample(&s, 0, 0, 0, DRAWER_HEIGHT) ==
         (DRAWER_CAPTURE | DRAWER_RELEASE));
  assert(s.target == DRAWER_HEIGHT);
}

static void clamp_and_integer_range(void)
{
  struct drawer_gesture s = {0};
  sample(&s, 1, 100, 0, 0);
  sample(&s, 1, 100, INT16_MIN, 0);
  assert(!s.cover);
  sample(&s, 1, 100, INT16_MAX, 0);
  assert(s.cover == DRAWER_HEIGHT);
  assert(!(sample(&s, 0, 0, 0, 0) & DRAWER_TAP));
  sample(&s, 1, INT16_MIN, INT16_MAX, DRAWER_HEIGHT);
  sample(&s, 1, INT16_MAX, INT16_MIN, DRAWER_HEIGHT);
  assert(!s.cover); /* Differences fit signed int, even with extreme samples. */
  assert(sample(&s, 0, 0, 0, DRAWER_HEIGHT) ==
         (DRAWER_CAPTURE | DRAWER_RELEASE));
  assert(!s.target);
}

static void framebuffer_independent(void)
{
  struct drawer_gesture a = {0}, b = {0};
  int y;
  sample(&a, 1, 140, 5, 0);
  sample(&b, 1, 140, 5, 0);
  for (y = 6; y <= 200; ++y) {
    assert(sample(&a, 1, 140, y, 0) == sample(&b, 1, 140, y, 319));
    assert(a.cover == b.cover);
  }
  assert(sample(&a, 0, 0, 0, 0) == sample(&b, 0, 0, 0, 70));
  assert(a.target == b.target && a.target == DRAWER_HEIGHT);
}

int main(void)
{
  stock_top_contact();
  stock_short_contact();
  stock_outside_contact();
  horizontal_cancel();
  custom_close();
  custom_short_close();
  custom_tap_once();
  custom_tap_slop();
  custom_wrong_direction();
  custom_horizontal_cancel();
  clamp_and_integer_range();
  framebuffer_independent();
  puts("PASS: 12 drawer gesture scenarios (capture, release, cancellation, tap, range, frame independence)");
  return 0;
}
