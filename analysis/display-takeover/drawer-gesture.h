#ifndef MI_PANEL_DRAWER_GESTURE_H
#define MI_PANEL_DRAWER_GESTURE_H

#include <stdint.h>

/* Coordinates are the original GUI's logical 480 x 320 coordinates. The
 * physical framebuffer rotates independently. DOWN and MOVE both call this
 * recognizer with down=1; UP calls with down=0 and its coordinates are ignored.
 * Start a contact only at a settled cover endpoint (0 or DRAWER_HEIGHT).
 * Consume contacts begun during a snap animation in the caller until release.
 */
#define DRAWER_HEIGHT 320
#define DRAWER_TOP_BAND 20
#define DRAWER_RELEASE_DISTANCE 80
#define DRAWER_TAP_SLOP 12

enum drawer_event {
  DRAWER_CAPTURE = 1,
  DRAWER_RELEASE = 2,
  DRAWER_TAP = 4
};

struct drawer_gesture {
  int16_t x0, y0;
  uint16_t cover, target;
  uint8_t active, captured, custom, cancelled, moved;
};

/* cover follows the last valid DOWN/MOVE sample; target is the endpoint to
 * animate towards after a captured RELEASE. Keep consuming CAPTURE through
 * that UP, including cancelled contacts. A stock contact begun outside the
 * top band stays unclaimed through UP even if it later crosses the top edge.
 * current_cover is consulted only on the initial DOWN, making recognition
 * independent of framebuffer submission frequency or delay.
 */
static inline unsigned drawer_gesture_sample(struct drawer_gesture *s, int down,
                                              int16_t x, int16_t y,
                                              unsigned current_cover)
{
  int dx, dy, ax, ay, cover;
  unsigned event;

  if (!s->active) {
    if (!down)
      return 0;
    s->active = 1;
    s->x0 = x;
    s->y0 = y;
    s->custom = current_cover == DRAWER_HEIGHT;
    s->captured = s->custom || (y >= 0 && y <= DRAWER_TOP_BAND);
    s->cancelled = s->moved = 0;
    s->cover = s->target = s->custom ? DRAWER_HEIGHT : 0;
  }

  if (!s->captured) {
    if (!down)
      s->active = 0;
    return 0;
  }

  event = DRAWER_CAPTURE;
  if (down) {
    dx = (int)x - s->x0;
    dy = (int)y - s->y0;
    ax = dx < 0 ? -dx : dx;
    ay = dy < 0 ? -dy : dy;
    if (ax > DRAWER_TAP_SLOP || ay > DRAWER_TAP_SLOP)
      s->moved = 1;
    /* Latch a predominantly horizontal contact; never return it halfway to
     * the stock UI, which did not receive its DOWN. Consume the eventual UP.
     */
    if (ax > DRAWER_TAP_SLOP && ax > ay)
      s->cancelled = 1;
    cover = s->custom ? DRAWER_HEIGHT : 0;
    if (!s->cancelled)
      cover += dy;
    if (cover < 0)
      cover = 0;
    if (cover > DRAWER_HEIGHT)
      cover = DRAWER_HEIGHT;
    s->cover = (uint16_t)cover;
  } else {
    event |= DRAWER_RELEASE;
    if (!s->cancelled && (s->custom ? DRAWER_HEIGHT - s->cover : s->cover)
                              >= DRAWER_RELEASE_DISTANCE)
      s->target = s->custom ? 0 : DRAWER_HEIGHT;
    if (s->custom && !s->moved && !s->cancelled)
      event |= DRAWER_TAP;
    s->active = 0;
  }
  return event;
}

#endif
