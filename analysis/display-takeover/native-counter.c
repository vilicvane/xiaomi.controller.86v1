/* Persistent A7 task entry for this exact 1.50.10 image. No host loop. */
typedef unsigned int u32;
typedef unsigned char u8;
typedef signed long long i64;
#define FN(type, address) ((type)(address))
#define OPEN FN(int (*)(const char *, int), 0x3802c901u)
#define IOCTL FN(int (*)(int, int, void *), 0x38025c41u)
#define GETFILE FN(int (*)(int, void **), 0x38025679u)
#define READ FN(int (*)(void *, void *, u32), 0x3802954du)
#define CLOSE FN(int (*)(int), 0x38025d21u)
#define ALLOC FN(void *(*)(u32), 0x383d9421u)
#define FREE FN(void (*)(void *), 0x383d93e5u)
#define SLEEP FN(int (*)(const void *, void *), 0x38042131u)
#define ORIGINAL FN(int (*)(int, char **), 0x3818f9fdu)

static const char alphabet[] = "vilcane+0123456789";
static const u8 font[][7] = {
    {0,0,17,17,17,10,4}, {4,0,12,4,4,4,14}, {12,4,4,4,4,4,14},
    {0,0,15,16,16,16,15}, {0,0,14,1,15,17,15}, {0,0,30,17,17,17,17},
    {0,0,14,17,31,16,15}, {0,4,4,31,4,4,0},
    {14,17,19,21,25,17,14}, {4,12,4,4,4,4,14}, {14,17,1,2,4,8,31},
    {30,1,1,14,1,1,30}, {2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
    {14,16,16,30,17,17,14}, {31,1,2,4,8,8,8}, {14,17,17,14,17,17,14},
    {14,17,17,15,1,1,14}
};

static void paint(u32 *pixels, u32 count)
{
    char text[22], reverse[10];
    const char *prefix = "vilicvane +";
    unsigned length = 0, digits = 0;
    while (prefix[length]) { text[length] = prefix[length]; ++length; }
    do { reverse[digits++] = (char)('0'+count%10); count /= 10; } while (count);
    while (digits) { text[length++] = reverse[--digits]; }
    for (unsigned y = 140; y < 172; ++y)
        for (unsigned x = 0; x < 480; ++x) pixels[y*480+x] = 0xff101010u;
    unsigned left = (480-length*18)/2;
    for (unsigned c = 0; c < length; ++c) {
        if (text[c] == ' ') continue;
        unsigned glyph = 0;
        while (alphabet[glyph] && alphabet[glyph] != text[c]) ++glyph;
        if (!alphabet[glyph]) continue;
        for (unsigned y = 0; y < 21; ++y)
            for (unsigned x = 0; x < 15; ++x)
                if (font[glyph][y/3] & (16u >> (x/3)))
                    pixels[(145+y)*480+left+c*18+x] = 0xffffffffu;
    }
}

__attribute__((section(".text.entry")))
int counter_main(int argc, char **argv)
{
    /* All state belongs to this ordinary 128KiB-stack NuttX task. */
    struct { i64 seconds; int nanoseconds; int pad; } pause = {0,20000000,0};
    u32 video[2], plane[7], sample[8], *pixels = 0;
    void *input_file = 0;
    int display = OPEN("/dev/fb0",2), input = -1;
    if (display < 0 || IOCTL(display,0x2801,video) < 0 ||
        IOCTL(display,0x2802,plane) < 0) goto fallback;
    /* Video: format@0, xres:u16@2, yres:u16@4. Actual RGB32 format13. */
    if (((u8 *)video)[0] != 13 || ((unsigned short *)video)[1] != 480 ||
        ((unsigned short *)video)[2] != 320 || ((u8 *)plane)[11] != 32 ||
        plane[1] != 614400 || ((unsigned short *)plane)[4] != 1920 ||
        plane[3] != 480 || plane[4] != 320 || plane[5] != 0 ||
        *(volatile u8 *)0x38641232u != 1) goto fallback;
    input = OPEN("/dev/input0",0x41);
    if (input < 0 || GETFILE(input,&input_file) < 0) goto fallback;
    pixels = ALLOC(480u*320u*4u);
    if (!pixels) goto fallback;
    for (unsigned i = 0; i < 480u*320u; ++i) pixels[i] = 0xff101010u;
    /* The private PAN ABI selects its source at+24, NOT fbmem@0. */
    plane[6] = (u32)pixels;
    u32 count = 0;
    int pressed = *(volatile u8 *)0x384f50a1u == 1;
    int dirty = 1;
    paint(pixels,0);
    for (;;) {
        int changed = 0;
        for (unsigned n = 0; n < 16 && READ(input_file,sample,32) == 32; ++n) {
            if (sample[0] != 1) continue;
            u8 flags = ((u8 *)sample)[9];
            if (flags & 4) pressed = 0;
            else if ((flags & 3) && !pressed) { pressed = 1; ++count; changed = 1; }
        }
        if (changed) { paint(pixels,count); dirty = 1; }
        if (dirty && IOCTL(display,0x2816,plane) >= 0) dirty = 0;
        SLEEP(&pause,0);
    }
fallback:
    if (pixels) FREE(pixels);
    if (input >= 0) CLOSE(input);
    if (display >= 0) CLOSE(display);
    return ORIGINAL(argc,argv);
}
