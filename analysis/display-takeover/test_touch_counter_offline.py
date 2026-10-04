"""Check GUI changes and posted partial pixel writes survive cleanup; no hardware."""
from pathlib import Path
from tempfile import TemporaryDirectory
from run_touch_counter import Counter, SLOTS, render_rows


class Pixels:
    def __init__(self):
        self.memory = {Counter.address(base, row): [0xFF203040]*32 for base in SLOTS for row in range(280)}
        self.writes = []
        self.fail_once = False

    def read(self, address, count):
        if address == 0x58050314:
            return [0x2B]  # Historical bits remain set with debug locks set.
        if address == 0x581000F4:
            return [SLOTS[0], 0, 1280, 0x80000000, 0x01E00140, 0x01E00140]
        if address == 0x58100264:
            return [0x401]
        assert address in self.memory and count == 32
        return self.memory[address][:]

    def write_rows(self, base, first, rows):
        assert base in SLOTS and 0 <= first < 280 and 1 <= len(rows) <= 8 and first+len(rows) <= 280
        for offset, row in enumerate(rows):
            assert len(row) == 32
            address = Counter.address(base, first+offset)
            self.writes.append(address)
            self.memory[address] = row[:]
            if self.fail_once and offset == 2:
                self.fail_once = False
                raise RuntimeError('Simulated lost reply after partial posted write')

    def read_rows(self, base, first, count):
        return [self.read(Counter.address(base, row), 32) for row in range(first, first+count)]


with TemporaryDirectory() as directory:
    pixels = Pixels()
    counter = Counter(pixels, Path(directory))
    counter.backup()
    first = Counter.address(SLOTS[0], 1)
    pixels.memory[first] = [0xFFAABBCC]*32  # GUI update after backup, before first draw.
    counter.draw(active=False)
    pixels.memory[first][0] = 0xFF123456  # GUI update after overlay, before cleanup.
    result = counter.restore()
    assert result['status'] == 'overlay_removed'
    assert pixels.memory[first] == [0xFF123456]+[0xFFAABBCC]*31
    assert all(row == [0xFF203040]*32 for address, row in pixels.memory.items() if address != first)

with TemporaryDirectory() as directory:
    pixels = Pixels()
    counter = Counter(pixels, Path(directory))
    counter.backup()
    pixels.fail_once = True
    try:
        counter.draw(active=False)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Partial posted write was not simulated')
    assert len(counter.possible) == 8
    counter.restore()
    assert all(row == [0xFF203040]*32 for row in pixels.memory.values())
    assert set(pixels.writes) <= {Counter.address(SLOTS[0], row) for row in range(8)}

zero, one = render_rows(0), render_rows(1)
assert len(zero) == 280 and all(len(row) == 32 for row in zero)
changed = [279-r for r in range(280) if zero[r] != one[r]]
assert changed and min(changed) >= 5+11*18
assert any(value == 0xFFFF00FF for row in zero for value in row)
render_rows(9999)
with TemporaryDirectory() as directory:
    pixels = Pixels()
    counter = Counter(pixels, Path(directory))
    counter.backup()
    counter.draw(active=False)
    before_writes = len(pixels.writes)
    counter.count = 1
    counter.draw(active=False, full=False)
    assert len(pixels.writes)-before_writes <= 30, 'A single digit still repainted the entire label'
    counter.restore()
print('Offline counter: rotated text, latest pre-draw GUI baseline, concurrent GUI pixel preservation and partial posted-write restoration passed')
