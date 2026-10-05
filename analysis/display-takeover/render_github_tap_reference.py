"""Independent logical pixels for the tap feedback; no firmware or hardware calls."""
from array import array
from pathlib import Path
import render_github_card_reference as card

FONT = dict(card.FONT)
FONT.update({
    '0': (62,81,73,69,62), '2': (66,97,81,73,70),
    '3': (33,65,69,75,49), '4': (24,20,18,127,16),
    '5': (39,69,69,69,57), '7': (1,113,9,5,3),
    '9': (6,73,73,41,30), '+': (8,8,62,8,8),
})


def render(cover=320, seed=0xff101010, count=0):
    assert 0 <= cover <= 320 and 0 <= count <= 0xffffffff
    pixels = array('I', [seed])*(480*320)

    def dot(x, y, scale, color):
        for dy in range(scale):
            row = y+dy+cover-320
            if 0 <= row < 320:
                for dx in range(scale):
                    assert 0 <= x+dx < 480
                    pixels[row*480+x+dx] = color

    for y, bits in enumerate(card.logo_rows()):
        for x in range(24):
            if bits & (1 << (23-x)):
                dot(216+x*2, 66+y*2, 2, 0xffffffff)
    text = '+'+str(count)
    footer = (text, (480-18*len(text))//2, 249, 3, 0xffe3b341) if count else (
        '* Star on GitHub',144,253,2,0xffe3b341)
    for line, left, top, scale, color in (
        ('vilicvane',159,151,3,0xffffffff),
        ('xiaomi.controller.86v1',108,192,2,0xffa0a0a0),
        footer,
    ):
        for index, char in enumerate(line):
            if char == ' ':
                continue
            for column, bits in enumerate(FONT[char]):
                for row in range(7):
                    if bits & (1 << row):
                        dot(left+(index*6+column)*scale, top+row*scale, scale, color)
    return pixels


if __name__ == '__main__':
    folder = Path(__file__).resolve().parent
    for count in (0,1,2,10):
        (folder/f'github-tap-reference-{count}.rgba').write_bytes(render(count=count).tobytes())
    print('Saved logical RGB32 references; no hardware access.')
