#ifndef PANEL_IMAGE_CODEC_H
#define PANEL_IMAGE_CODEC_H

#include "panel.h"

/* Decode a complete, caller-bounded (1 MiB maximum) input into its inactive
 * 480x320 RGB565 frame. PNG/JPEG and complete VIMG are accepted. Success is 0;
 * failures are HTTP statuses 400/415/422/503.
 * Partial failed output is disposable. The module and all its native ABIs
 * require the exact 1.50.10 image.
 */
int panel_image_decode(const u8 *encoded, u32 bytes, u16 *destination);

#endif
