#ifndef PANEL_IMAGE_STORE_H
#define PANEL_IMAGE_STORE_H

#include "panel.h"

/* Private to the serialized network worker, outside the broker context.
 * This identifies the last record whose image actually decoded or whose
 * validated upload completed independent readback, not just a valid hash.
 */
struct panel_image_store { u32 sequence, length, hash, valid; };
_Static_assert(sizeof(struct panel_image_store) == 16, "Image store state layout changed");

/* Serialized network-worker operations, with no GUI lock held. These touch
 * only /data/86v1-image.0 and .1 on this image's verified native FAT ABI.
 * save requires a complete, already decoded input of 1..1048576 bytes.
 * A known record must still match both-slot preflight and is never overwritten.
 * The state changes only after confirmation; failed saves retain the prior state.
 * It returns 0 only after sync, close and independent full readback; errors
 * are 409 (foreign file) or 503 (I/O, resources or confirmation failure).
 */
int panel_image_save(struct panel_image_store *store, const u8 *encoded, u32 bytes);

/* Load into the caller's inactive 480x320 RGB565 frame, never publish here.
 * Clear worker state first and record the chosen slot only after actual decode.
 * A damaged or undecodable newer slot can fall back to the older one.
 * Return 0 on success, or 404 absent / 422 damaged / 409 foreign / 503 I/O
 * or resources. Failed output is disposable; no file is modified by load.
 */
int panel_image_load(u16 *destination, struct panel_image_store *store);

#endif
