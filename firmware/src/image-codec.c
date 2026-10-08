#include "image-codec.h"

#define PNG_CREATE FN(void *(*)(void *), 0x3838d925u)
#define PNG_SAFE FN(int (*)(void *, int (*)(void *), void *), 0x38100f05u)
#define PNG_HEADER FN(int (*)(void *), 0x38073489u)
#define PNG_FREE FN(void (*)(void *), 0x383c3475u)
#define PNG_ERROR FN(void (*)(void *, const char *), 0x38102811u)
#define PNG_ALPHA FN(void (*)(void *, int, int), 0x381044f9u)
#define PNG_TRANSFORM FN(void (*)(void *), 0x38102891u)
#define PNG_INFO_TRANSFORM FN(void (*)(void *, void *), 0x381046b5u)
#define PNG_ROW FN(void (*)(void *, u8 *), 0x3838a221u)
#define COPY FN(void *(*)(void *, const void *, u32), 0x383d8ac0u)

struct png_image {
    void *opaque;
    u32 version, width, height, format, flags, colors, warning;
    char message[64];
};
struct png_control { void *png, *info, *jump, *memory; u32 bytes, flags; };
struct png_decoder {
    struct png_image image;
    const u8 *cursor;
    u32 left, oom;
    u16 *destination;
    u8 row[PANEL_WIDTH * 4];
};

static u32 be32(const u8 *p) {
    return (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
}

static u32 png_crc(const u8 *p, u32 bytes) {
    static const u32 table[16] = {
        0, 0x1db71064u, 0x3b6e20c8u, 0x26d930acu,
        0x76dc4190u, 0x6b6b51f4u, 0x4db26158u, 0x5005713cu,
        0xedb88320u, 0xf00f9344u, 0xd6d6a3e8u, 0xcb61b38cu,
        0x9b64c2b0u, 0x86d3d2d4u, 0xa00ae278u, 0xbdbdf21cu
    };
    u32 crc = ~0u;
    while (bytes--) {
        crc ^= *p++;
        crc = crc >> 4 ^ table[crc & 15];
        crc = crc >> 4 ^ table[crc & 15];
    }
    return ~crc;
}

/* Restrict decoder work before allocation: 8-bit, no Adam7/APNG or compressed
 * ancillary data. CRC, ordering and exact IEND are required independently of
 * the simplified library, which otherwise stops after the last pixel row.
 */
static int png_validate(const u8 *p, u32 bytes) {
    if (bytes < 45 || be32(p + 8) != 13 || be32(p + 12) != 0x49484452u)
        return 422;
    if (be32(p + 16) != PANEL_WIDTH || be32(p + 20) != PANEL_HEIGHT)
        return 422;
    u32 color = p[25];
    if (p[24] != 8 || color == 1 || color == 5 || color > 6 || p[26] || p[27] || p[28])
        return 415;
    u32 position = 8, palette = 0, transparency = 0, idat = 0;
    while (bytes - position >= 12) {
        const u8 *chunk = p + position;
        u32 length = be32(chunk), type = be32(chunk + 4);
        if (length > bytes - position - 12 || png_crc(chunk + 4, length + 4) != be32(chunk + 8 + length))
            return 422;
        if (type == 0x49484452u) {
            if (position != 8) return 422;
        } else if (type == 0x504c5445u) {
            if (idat || palette || !length || length > 768 || length % 3 || color == 0 || color == 4)
                return 422;
            palette = length / 3;
        } else if (type == 0x74524e53u) {
            if (idat || transparency || (color == 3 ? !palette || !length || length > palette : color == 0 ? length != 2 : color == 2 ? length != 6 : 1))
                return 422;
            transparency = 1;
        } else if (type == 0x49444154u) {
            if (color == 3 && !palette) return 422;
            idat = 1;
        } else if (type == 0x49454e44u) {
            return !length && idat && position + 12 == bytes ? 0 : 422;
        } else {
            if (idat) return 415;
            if (!((type == 0x70485973u && length == 9) ||
                  (type == 0x73424742u && length == 1) ||
                  (type == 0x67414d41u && length == 4) ||
                  (type == 0x6348524du && length == 32)))
                return 415;
        }
        position += length + 12;
    }
    return 422;
}

static void png_read(void *png, u8 *out, u32 need) {
    struct png_decoder *decoder = *(struct png_decoder **)((u8 *)png + 0x8c);
    if (need > decoder->left) {
        PNG_ERROR(png, "read beyond end of data");
        return;
    }
    COPY(out, decoder->cursor, need);
    decoder->cursor += need;
    decoder->left -= need;
}

static void *png_allocate(void *png, u32 bytes) {
    void *p = ALLOC(bytes);
    if (!p) (*(struct png_decoder **)((u8 *)png + 0x80))->oom = 1;
    return p;
}

static void png_release(void *png, void *p) {
    (void)png;
    FREE(p);
}

static int png_rows(void *argument) {
    struct png_decoder *decoder = argument;
    struct png_control *control = decoder->image.opaque;
    u8 *png = control->png;
    u32 format = decoder->image.format;
    /* These are the original 1.50.10 png_set_expand/gray_to_rgb/add_alpha
     * effects, followed by its actual alpha-mode/transform primitives.
     * Image dimensions stay 480x320 throughout; no simplified-height bypass.
     */
    *(u32 *)(png + 0xa4) |= 0x4000;
    *(u32 *)(png + 0xa8) |= 0x02001000;
    if (!(format & 2)) *(u32 *)(png + 0xa8) |= 0x5000;
    if (!(format & 1)) {
        *(u16 *)(png + 0x186) = 255;
        *(u32 *)(png + 0xa8) |= 0x01008000;
        *(u32 *)(png + 0xa4) |= 0x80;
    }
    PNG_ALPHA(png, 0, -1);
    PNG_TRANSFORM(png);
    PNG_INFO_TRANSFORM(png, control->info);
    u8 *info = control->info;
    if (info[0x18] != 8 || info[0x19] != 6 || *(u32 *)(info + 12) != PANEL_WIDTH * 4)
        PNG_ERROR(png, "unsupported output");
    for (u32 y = 0; y < PANEL_HEIGHT; y++) {
        PNG_ROW(png, decoder->row);
        for (u32 x = 0; x < PANEL_WIDTH; x++) {
            const u8 *pixel = decoder->row + x * 4;
            u32 alpha = pixel[3];
            u32 r = (pixel[0] * alpha + 127) / 255;
            u32 g = (pixel[1] * alpha + 127) / 255;
            u32 b = (pixel[2] * alpha + 127) / 255;
            decoder->destination[y * PANEL_WIDTH + x] = (r >> 3) << 11 | (g >> 2) << 5 | b >> 3;
        }
    }
    return 1;
}

static int png_decode(const u8 *encoded, u32 bytes, u16 *destination) {
    int status = png_validate(encoded, bytes);
    if (status) return status;
    struct png_decoder *decoder = ALLOC(sizeof *decoder);
    if (!decoder) return 503;
    ZERO(decoder, 0, sizeof *decoder);
    decoder->image.version = 1;
    decoder->cursor = encoded;
    decoder->left = bytes;
    decoder->destination = destination;
    u8 *png = PNG_CREATE(&decoder->image);
    struct png_control *control = png ? ALLOC(sizeof *control) : 0;
    if (!control) {
        FREE(png);
        FREE(decoder);
        return 503;
    }
    ZERO(control, 0, sizeof *control);
    control->png = png;
    decoder->image.opaque = control;
    control->info = ALLOC(280);
    if (!control->info) {
        PNG_FREE(&decoder->image);
        FREE(decoder);
        return 503;
    }
    ZERO(control->info, 0, 280);
    *(u32 *)(png + 0xa0) = 0x8000;
    *(void (**)(void *, u8 *, u32))(png + 0x88) = png_read;
    *(struct png_decoder **)(png + 0x8c) = decoder;
    *(void *(**)(void *, u32))(png + 0x28c) = png_allocate;
    *(void (**)(void *, void *))(png + 0x290) = png_release;
    *(u32 *)(png + 0x2d8) = 8192;
    status = PNG_SAFE(&decoder->image, PNG_HEADER, &decoder->image) &&
             !decoder->image.warning && PNG_SAFE(&decoder->image, png_rows, decoder) &&
             !decoder->image.warning && decoder->left == 12 ? 0 : decoder->oom ? 503 : 422;
    if (decoder->image.opaque) PNG_FREE(&decoder->image);
    FREE(decoder);
    return status;
}

#define JPEG_CREATE FN(void (*)(void *), 0x3838cfa5u)
#define JPEG_SOURCE FN(void (*)(void *, const u8 *, u32), 0x380d16c5u)
#define JPEG_HEADER FN(int (*)(void *), 0x3838d259u)
__attribute__((naked, returns_twice, noinline)) static int jpeg_setjmp(void *buffer) {
    __asm__ volatile("ldr r12, =0x383e22cb\nbx r12\n");
}

__attribute__((naked, noreturn, noinline)) static void jpeg_longjmp(void *buffer, int value) {
    __asm__ volatile("ldr r12, =0x383e22e1\nbx r12\n");
}

/* LTO private frame for the retained master-initialization region. CINFO is
 * 464B at +0x140, error 128B at +0x50, native jump buffer at +0xd4. It never enters
 * the wrapper's FILE loading, full-frame GUI allocation, logging or cleanup.
 */
struct jpeg_decoder {
    u32 frame[0x320 / 4];
    u8 row[PANEL_WIDTH * 4];
    void *array_allocate;
    u32 status;
};

static u32 be16(const u8 *p) { return (u32)p[0] << 8 | p[1]; }

static int jpeg_validate(const u8 *p, u32 bytes) {
    u32 position = 2, components = 0;
    while (bytes - position >= 4) {
        if (p[position++] != 255) return 422;
        while (position < bytes && p[position] == 255) position++;
        if (bytes - position < 3) return 422;
        u32 marker = p[position++], length = be16(p + position);
        if (length < 2 || length > bytes - position) return 422;
        const u8 *payload = p + position + 2;
        if (marker == 0xc0) {
            if (components || length < 8) return 422;
            components = payload[5];
            if (payload[0] != 8 || (components != 1 && components != 3)) return 415;
            if (length != 8 + components * 3 || be16(payload + 1) != PANEL_HEIGHT || be16(payload + 3) != PANEL_WIDTH)
                return 422;
            if (components == 1 ? payload[7] != 0x11 :
                (payload[7] != 0x11 && payload[7] != 0x21 && payload[7] != 0x22) ||
                payload[10] != 0x11 || payload[13] != 0x11)
                return 415;
        } else if (marker == 0xda) {
            if (!components || length != 6 + components * 2 || payload[0] != components ||
                payload[1 + components * 2] || payload[2 + components * 2] != 63 || payload[3 + components * 2])
                return 415;
            position += length;
            while (position < bytes) {
                if (p[position++] != 255) continue;
                while (position < bytes && p[position] == 255) position++;
                if (position == bytes) return 422;
                marker = p[position++];
                if (!marker || (marker >= 0xd0 && marker <= 0xd7)) continue;
                return marker == 0xd9 && position == bytes ? 0 : 422;
            }
            return 422;
        } else if (!(marker == 0xdb || marker == 0xc4 || marker == 0xfe ||
                     (marker == 0xdd && length == 4) || (marker >= 0xe0 && marker <= 0xef))) {
            return 415;
        }
        position += length;
    }
    return 422;
}

static struct jpeg_decoder *jpeg_owner(void *ci) {
    return (struct jpeg_decoder *)((u8 *)ci - 0x140);
}

__attribute__((noreturn)) static void jpeg_error(void *ci) {
    struct jpeg_decoder *decoder = jpeg_owner(ci);
    decoder->status = *(u32 *)(decoder->frame + 0x50 / 4 + 5) == 54 ? 503 : 422;
    jpeg_longjmp((u8 *)decoder + 0xd4, 1);
}

static void jpeg_message(void *ci, int level) {
    if (level < 0) jpeg_error(ci);
}

static void *jpeg_array(void *ci, int pool, u32 samples, u32 rows) {
    struct jpeg_decoder *decoder = jpeg_owner(ci);
    /* Stock 16-bit BLX at 0x3806b5a2 returns to 0x3806b5a4 in Thumb state. */
    if ((u32)__builtin_return_address(0) == 0x3806b5a5u) {
        u8 *c = ci;
        u32 *master = *(u32 **)(c + 0x1a4), *main = *(u32 **)(c + 0x1a8);
        if (pool != 1 || samples != PANEL_WIDTH * 4 || rows != 1 ||
            *(u32 *)(c + 0x14) != 205 || *(u32 *)(c + 0x70) != PANEL_WIDTH ||
            *(u32 *)(c + 0x74) != PANEL_HEIGHT || *(u32 *)(c + 0x7c) != 4 || *(u32 *)(c + 0x8c) ||
            !master || master[0] != 0x3810dc49u || master[1] != 0x3810dd81u || !main ||
            (main[1] != 0x3814a3c1u && main[1] != 0x3814a5edu))
            jpeg_error(ci);
        jpeg_longjmp((u8 *)decoder + 0xd4, 2);
    }
    return ((void *(*)(void *, int, u32, u32))decoder->array_allocate)(ci, pool, samples, rows);
}

__attribute__((naked, noreturn, noinline)) static void jpeg_initialize(struct jpeg_decoder *decoder) {
    __asm__ volatile(
        "sub sp, #32\n"
        "mov r7, r0\n"
        "movs r0, #0\n"
        "mov r11, r0\n"
        "ldr r12, =0x3806b765\n"
        "bx r12\n"
    );
}

static int jpeg_decode(const u8 *encoded, u32 bytes, u16 *destination) {
    int status = jpeg_validate(encoded, bytes);
    if (status) return status;
    struct jpeg_decoder *decoder = ALLOC(sizeof *decoder);
    if (!decoder) return 503;
    ZERO(decoder, 0, sizeof *decoder);
    u8 *ci = (u8 *)decoder + 0x140;
    u32 *error = decoder->frame + 0x50 / 4;
    error[0] = (u32)jpeg_error;
    error[1] = (u32)jpeg_message;
    error[2] = 0x380cffcdu;
    error[3] = 0x380d09c1u;
    error[4] = 0x380ca741u;
    error[0x70 / 4] = 0x384056e8u;
    error[0x74 / 4] = 128;
    *(u32 **)ci = error;
    decoder->status = 422;
    int jumped = jpeg_setjmp((u8 *)decoder + 0xd4);
    if (!jumped) {
        JPEG_CREATE(ci);
        JPEG_SOURCE(ci, encoded, bytes);
        if (JPEG_HEADER(ci) != 1) jpeg_error(ci);
        ci[0x29] = 9; /* Original validated BGRX output selector. */
        u32 *memory = *(u32 **)(ci + 4);
        decoder->array_allocate = (void *)memory[2];
        memory[2] = (u32)jpeg_array;
        jpeg_initialize(decoder);
    }
    if (jumped == 2) {
        u32 *memory = *(u32 **)(ci + 4);
        memory[2] = (u32)decoder->array_allocate;
        u32 *master = *(u32 **)(ci + 0x1a4), *main = *(u32 **)(ci + 0x1a8);
        u8 *row = decoder->row;
        for (u32 y = 0; y < PANEL_HEIGHT; y++) {
            u32 count = 0;
            FN(void (*)(void *, u8 **, u32 *, u32), main[1])(ci, &row, &count, 1);
            if (count != 1) jpeg_error(ci);
            *(u32 *)(ci + 0x8c) += count;
            for (u32 x = 0; x < PANEL_WIDTH; x++) {
                u8 *pixel = row + x * 4;
                destination[y * PANEL_WIDTH + x] = (pixel[2] >> 3) << 11 | (pixel[1] >> 2) << 5 | pixel[0] >> 3;
            }
        }
        FN(void (*)(void *), master[1])(ci);
        *(u32 *)(ci + 0x14) = 210;
        u32 *input = *(u32 **)(ci + 0x1b4);
        while (!input[5]) {
            if (!FN(int (*)(void *), input[0])(ci)) jpeg_error(ci);
        }
        u32 *source = *(u32 **)(ci + 24);
        if (source[1]) jpeg_error(ci);
        FN(void (*)(void *), source[6])(ci);
        decoder->status = 0;
    }
    u32 *memory = *(u32 **)(ci + 4);
    if (memory) FN(void (*)(void *), memory[10])(ci);
    status = decoder->status;
    FREE(decoder);
    return status;
}

int panel_image_decode(const u8 *encoded, u32 bytes, u16 *destination) {
    if (bytes >= 4 && be32(encoded) == 0x56494d47u) {
        if (bytes != 307216u || be32(encoded + 4) != 0xe0014001u ||
            be32(encoded + 8) != 0x00b00400u) return 400;
        u32 expected = (u32)encoded[12] | (u32)encoded[13] << 8 |
                       (u32)encoded[14] << 16 | (u32)encoded[15] << 24;
        u32 check = 2166136261u;
        for (u32 i = 16; i < bytes; ++i) check = (check ^ encoded[i]) * 16777619u;
        if (check != expected) return 422;
        COPY(destination, encoded + 16, PANEL_IMAGE_BYTES);
        return 0;
    }
    if (bytes >= 8 && be32(encoded) == 0x89504e47u && be32(encoded + 4) == 0x0d0a1a0au)
        return png_decode(encoded, bytes, destination);
    if (bytes >= 2 && encoded[0] == 255 && encoded[1] == 216)
        return jpeg_decode(encoded, bytes, destination);
    return 415;
}
