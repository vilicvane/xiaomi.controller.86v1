"""Independent pixel reference for the static card; no device or native calls."""
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FONT = {
    '.': (0,0x60,0x60,0,0), '1': (0,0x42,0x7f,0x40,0),
    '6': (0x3c,0x4a,0x49,0x49,0x30), '8': (0x36,0x49,0x49,0x49,0x36),
    'G': (0x3e,0x41,0x49,0x49,0x7a), 'H': (0x7f,8,8,8,0x7f),
    'S': (0x46,0x49,0x49,0x49,0x31), 'a': (0x20,0x54,0x54,0x54,0x78),
    'b': (0x7f,0x48,0x44,0x44,0x38), 'c': (0x38,0x44,0x44,0x44,0x20),
    'e': (0x38,0x54,0x54,0x54,0x18), 'i': (0,0x44,0x7d,0x40,0),
    'l': (0,0x41,0x7f,0x40,0), 'm': (0x7c,4,0x18,4,0x78),
    'n': (0x7c,8,4,4,0x78), 'o': (0x38,0x44,0x44,0x44,0x38),
    'r': (0x7c,8,4,4,8), 't': (4,0x3f,0x44,0x40,0x20),
    'u': (0x3c,0x40,0x40,0x20,0x7c), 'v': (0x1c,0x20,0x40,0x20,0x1c),
    'x': (0x44,0x28,0x10,0x28,0x44), '*': (0x44,0x3c,0x1f,0x3c,0x44),
}


def logo_rows():
    # Original24 row raster from the official white PNG, independent of the
    # firmware column storage. Bits23..0 map to left x0..23.
    return (
        0x00ff00,0x03ffc0,0x07ffe0,0x0ffff0,
        0x1ffff8,0x3cff3c,0x7c003e,0x7c003e,
        0xfc003f,0xf8001f,0xf8001f,0xf8001f,
        0xf8001f,0xf8001f,0xfc003f,0x7e007e,
        0x7781fe,0x7383fe,0x3801fc,0x1c01f8,
        0x0f81f0,0x0781e0,0x018180,0x000000,
    )


def render(cover=320, seed=0xff101010):
    assert 0 <= cover <= 320
    pixels = array('I', [seed])*(480*320)

    def dot(x, y, scale, color):
        for dy in range(scale):
            row = y+dy+cover-320
            if 0 <= row < 320:
                for dx in range(scale):
                    assert 0 <= x+dx < 480
                    pixels[row*480+x+dx] = color

    for y, bits in enumerate(logo_rows()):
        for x in range(24):
            if bits & (1 << (23-x)):
                dot(216+x*2, 66+y*2, 2, 0xffffffff)
    for text, left, top, scale, color in (
        ('vilicvane',159,151,3,0xffffffff),
        ('xiaomi.controller.86v1',108,192,2,0xffa0a0a0),
        ('* Star on GitHub',144,253,2,0xffe3b341),
    ):
        for index, char in enumerate(text):
            if char == ' ':
                continue
            for column, bits in enumerate(FONT[char]):
                for row in range(7):
                    if bits & (1 << row):
                        dot(left+(index*6+column)*scale, top+row*scale, scale, color)
    return pixels


if __name__ == '__main__':
    target = ROOT/'analysis/display-takeover/github-card-reference.rgba'
    target.write_bytes(render().tobytes())
    print('Saved logical RGB32 reference; no hardware access.')
