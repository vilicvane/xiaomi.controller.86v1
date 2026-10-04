"""Run the actual linked drawer ARM ELF with mocked native APIs, without hardware.

Reuses only the prior broker harness's memory/register helpers. Touch data, heap,
publication and frame hooks below model the drawer ABI independently. This does
not validate LCD rotation, IRQ concurrency, native mutex implementations or OS
scheduling. Workspace-local dependencies: tools/python-ui-broker.
"""
from pathlib import Path
import hashlib
import json
import struct

import test_ui_broker_arm as old
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2

ROOT = Path(__file__).resolve().parents[2]
ELF = ROOT / 'analysis/display-takeover/native-drawer.elf'
old.ELF = ELF
CTX, PIXELS, DRIVERS, FILES, UPPERS, SUBS = (
    old.CTX, old.PIXELS, old.DRIVERS, old.FILES, old.UPPERS, old.SUBS)
DATA = 0x389d0000
PLANE = 0x389d0100
F = {
    'alive': 24, 'pixels': 28, 'snapshot': 32, 'mode': 36, 'wanted': 40,
    'ready': 44, 'dirty': 48, 'count': 52, 'idle': 56, 'drivers': 60,
    'released': 68, 'physical': 76, 'overlay': 80, 'cover': 84, 'target': 88,
    'shown': 92, 'background': 96, 'gui_cycles': 100, 'toggles': 104,
    'last_present': 108, 'last_x': 112, 'last_y': 116, 'clock_ms': 120,
    'animation_ms': 124, 'keys': 128, 'gesture': 148,
}


class Machine(old.Machine):
    def __init__(self, physical=0, cached_held=False):
        self.physical_index = physical
        self.cached_held = cached_held
        self.create_result = 0
        self.freed = []
        self.lock_history = []
        self.clock_result = 0
        super().__init__()

    def f(self, name, value=None):
        return self.field(F[name], value)

    def _install_hooks(self):
        r = lambda register: self.uc.reg_read(register)

        def lock():
            address = r(UC_ARM_REG_R0)
            assert address not in self.locks, f'recursive lock {address:x}'
            self.locks.add(address)
            self.lock_history.append(('lock', address))
            self.ret()

        def unlock():
            address = r(UC_ARM_REG_R0)
            assert address in self.locks, f'unowned unlock {address:x}'
            self.locks.remove(address)
            self.lock_history.append(('unlock', address))
            self.ret()

        def zero():
            destination, size = r(UC_ARM_REG_R0), r(UC_ARM_REG_R2)
            self.uc.mem_write(destination, bytes([r(UC_ARM_REG_R1) & 255]) * size)
            self.ret(destination)

        def getfile():
            fd = r(UC_ARM_REG_R0)
            if fd not in (6, 7):
                self.ret(-9)
                return
            self.word(r(UC_ARM_REG_R1), FILES[fd - 6])
            self.ret()

        def pan():
            assert r(UC_ARM_REG_R0) == 0x384ef84c
            self.frames.append(self.word(r(UC_ARM_REG_R1) + 24))
            self.ret()

        def area():
            self.area_calls += 1
            self.ret()

        def touch():
            index = DRIVERS.index(r(UC_ARM_REG_R0))
            data, sample = r(UC_ARM_REG_R1), self.touches[index]
            self.uc.mem_write(data, bytes([0x5a]) * 20)
            self.word(data, sample.get('x', 200))
            self.word(data + 4, sample.get('y', 100))
            self.byte(data + 0x12, sample.get('state', 0))
            self.byte(data + 0x13, sample.get('again', 0))
            self.byte(self.word(DRIVERS[index] + 12) + 4, sample.get('state', 0))
            if sample.get('again', 0):
                self.word(SUBS[index] + 0xc, self.word(SUBS[index] + 8))
            self.ret()

        def timer():
            self.gui_ticks += 1
            self.word(0x384fce58, 0x3806a93d)
            self.ret()

        def clock():
            assert r(UC_ARM_REG_R0) == 1
            if not self.clock_result:
                self.uc.mem_write(r(UC_ARM_REG_R1), struct.pack(
                    '<qii', self.now // 1000, (self.now % 1000) * 1000000, 0))
            self.ret(self.clock_result)

        def original():
            self.original_calls += 1
            self.ret(17)

        def allocate():
            self.ret(self.allocations.pop(0))

        def free():
            self.freed.append(r(UC_ARM_REG_R0))
            self.ret()

        def sleep():
            assert not self.locks, 'sleep while holding a mutex'
            self.ret()
            self.uc.emu_stop()

        for address in [0x3800da2c, 0x3800c1f8]:
            self.hook(address, lock)
        for address in [0x3800b0b4, 0x3800bb3c]:
            self.hook(address, unlock)
        for address, method in [
            (0x383d8fa0, zero), (0x38025678, getfile), (0x383df2dc, pan),
            (0x383df474, area), (0x3806ab74, touch), (0x3806a93c, timer),
            (0x38004c38, clock), (0x3818f9fc, original), (0x383d9420, allocate),
            (0x383d93e4, free), (0x38042130, sleep),
        ]:
            self.hook(address, method)
        self.hook(0x383acc04, lambda: self.ret(self.create_result))

    def _graph(self):
        super()._graph()
        self.uc.mem_write(CTX, bytes(164))
        self.field(0, 1)
        self.field(12, 0xffffffff)
        self.f('alive', 1)
        self.f('pixels', PIXELS)
        self.f('snapshot', PIXELS + 614400)
        self.f('shown', 0xffffffff)
        self.byte(CTX + F['keys'] + 16, 1)
        self.word(0x384f50b0, UPPERS[self.physical_index])
        self.byte(self.word(DRIVERS[self.physical_index] + 12) + 4,
                  int(self.cached_held))
        self.word(0x50000000, 0xffabcdef)
        self.word(0x50000000 + 319 * 480 * 4, 0xff445566)

    def tick(self, ms=20, gpio=None):
        if gpio is not None:
            self.word(0x40081050, gpio)
        if self.f('ready'):
            # Model GUI's next empty/cached read after each delivered sample.
            # Rings explicitly held pending below represent publication after
            # that scan; an empty poll must not erase that test condition.
            for i in range(2):
                previous = self.touches[i]
                self.contact(i, previous.get('state', 0), previous.get('x', 200),
                             previous.get('y', 100), again=0)
        self.now += ms
        self.gui()

    def contact(self, index, down, x=200, y=100, again=1):
        self.touches[index] = {'state': int(down), 'again': again, 'x': x, 'y': y}
        self.call('touch', DRIVERS[index], DATA)
        return bytes(self.uc.mem_read(DATA, 20))

    def release(self):
        for i in range(2):
            self.contact(i, False, again=0)

    def ready(self):
        self.tick()
        assert self.f('ready') == 1
        self.release()
        self.tick()
        self.tick()
        return self

    def custom(self):
        self.f('mode', 1)
        self.f('wanted', 1)
        self.f('cover', 320)
        self.f('shown', 320)
        self.f('target', 320)
        return self

    def settle(self):
        for _ in range(30):
            self.tick()
            if not self.f('overlay'):
                return
        raise AssertionError('drawer did not settle')


def main():
    checks = []

    for physical in (0, 1):
        m = Machine(physical=physical, cached_held=True)
        m.tick()
        assert m.f('ready') == 1 and m.f('physical') == physical
        assert m.word(DRIVERS[0] + 4) == m.symbols['touch']
        assert m.word(DRIVERS[1] + 4) == m.symbols['touch']
        assert m.byte(CTX + F['gesture'] + 8) == 1
        held = m.contact(physical, True, x=100, y=0)
        assert held[18] == 1 and not m.f('overlay')
        m.release()
        assert not m.byte(CTX + F['gesture'] + 8)
    checks.append('installs both callbacks, classifies reversed physical/virtual ordering, and ignores boot-held contact')

    m = Machine()
    m.word(0x384f50b0, 0x3870b200)
    m.tick()
    assert not m.f('ready')
    assert m.word(DRIVERS[0] + 4) == 0x3806ab75
    checks.append('unknown physical publisher fails setup without partial callback installation')

    m = Machine().ready()
    m.f('wanted', 1)
    m.tick()
    assert m.f('mode') == 0 and m.f('overlay') == 1
    m.settle()
    assert m.f('mode') == 1 and m.f('cover') == 320 and m.frames[-1] == PIXELS
    assert m.call('bootstrap', CTX) == 0
    checks.append('default custom startup opens through animation and bootstrap returns after GUI hook readiness')

    m = Machine().ready()
    data = m.contact(0, True, x=100, y=5)
    assert data[18] == 0 and data[19] == 1 and data[8:18] == bytes([0x5a]) * 10
    assert m.f('overlay') == 1 and m.f('cover') == 0
    m.contact(0, True, x=100, y=125)
    assert m.f('cover') == 120
    m.tick()
    assert m.f('shown') == 120 and m.frames[-1] == PIXELS
    assert m.word(PIXELS) == 0xff101010
    assert m.word(PIXELS + 319 * 480 * 4) == 0xff445566
    m.contact(0, False, x=0, y=0)
    assert m.f('target') == 320 and m.f('wanted') == 1
    m.settle()
    assert m.f('mode') == 1
    checks.append('first top-edge DOWN is suppressed; actual pixels follow vertical displacement and release opens')

    m = Machine().ready()
    assert m.contact(0, True, x=100, y=21)[18] == 1
    assert m.contact(0, True, x=100, y=0)[18] == 1
    assert m.contact(0, False)[18] == 0
    assert not m.f('overlay') and not m.f('count')
    checks.append('stock contact starting below top band passes completely and never becomes a drawer gesture')

    m = Machine().ready()
    m.contact(0, True, x=100, y=0)
    m.contact(0, True, x=170, y=40)
    assert m.f('cover') == 0
    assert m.contact(0, True, x=100, y=200)[18] == 0
    m.contact(0, False)
    m.settle()
    assert m.f('mode') == 0 and not m.f('count')
    checks.append('horizontal cancellation remains captured through UP and returns stock without a stray tap')

    m = Machine().ready().custom()
    m.contact(0, True)
    for _ in range(20):
        m.contact(0, True)
    assert not m.f('count')
    m.contact(0, False)
    assert m.f('count') == 1
    m.contact(0, False)
    assert m.f('count') == 1
    m.contact(0, True, y=300)
    m.contact(0, True, y=180)
    m.contact(0, False)
    m.settle()
    assert m.f('mode') == 0 and m.f('count') == 1
    checks.append('custom tap counts on UP exactly once; hold repeats do not count and upward drag closes without counting')

    m = Machine().ready().custom()
    assert m.contact(1, True, y=0)[18] == 0
    m.contact(1, True, y=200)
    m.contact(1, False)
    assert not m.f('count') and not m.f('overlay')
    m.f('mode', 0); m.f('wanted', 0); m.f('cover', 0)
    m.contact(1, True)
    assert m.contact(0, True, y=0)[18] == 1
    assert not m.f('overlay')
    m.release()
    checks.append('virtual input never drives drawer/count; an already delivered virtual DOWN prevents truncating stock input')

    m = Machine().ready()
    m.contact(0, True, y=0); m.contact(0, True, y=100); m.contact(0, False)
    assert m.f('overlay') == 1
    assert m.contact(0, True, y=200)[18] == 0
    for _ in range(10):
        m.tick()
    assert m.f('mode') == 0 and m.f('overlay') == 1 and not m.f('count')
    assert m.contact(0, False)[18] == 0
    m.settle()
    assert m.f('mode') == 1 and not m.f('count')
    checks.append('contact begun during snap is consumed fully and blocks final ownership handoff until release')

    m = Machine().ready()
    m.contact(0, True, y=0)
    m.contact(0, True, y=40)
    m.word(PIXELS, 0x12345678)
    m.word(0x384ef93c, 1)
    before = len(m.frames)
    m.tick()
    assert m.word(PIXELS) == 0x12345678 and len(m.frames) == before
    assert not m.f('background')
    m.word(0x384ef93c, 0)
    m.tick()
    assert m.word(PIXELS) == 0xff101010 and m.f('shown') == 40
    checks.append('queued native frame prevents both canvas mutation and snapshot/presentation; queue release permits redraw')

    for pending in (0, 1):
        m = Machine().ready().custom()
        m.f('overlay', 1); m.f('wanted', 0); m.f('target', 0)
        m.f('cover', 0); m.f('shown', 0); m.f('background', 1)
        m.word(SUBS[pending] + 8, 32)
        m.tick()
        assert m.f('mode') == 1 and m.f('overlay') == 1
        m.word(SUBS[pending] + 12, 32)
        m.tick()
        assert m.f('mode') == 0 and m.f('overlay') == 0 and m.frames[-1] == 0
        assert ('lock', UPPERS[0] + 4) in m.lock_history
        assert ('lock', UPPERS[1] + 4) in m.lock_history
    checks.append('either physical or virtual queued ring blocks final ownership; final PAN runs under both publisher mutexes')

    m = Machine().ready().custom()
    m.f('wanted', 0)
    for address, value in [(0x384f50a1, 1), (0x384ef93c, 1)]:
        if address == 0x384f50a1:
            m.byte(address, value)
        else:
            m.word(address, value)
        before = len(m.frames)
        assert m.call('handoff', CTX) == 0xffffffff
        assert len(m.frames) == before and m.f('mode') == 1
        if address == 0x384f50a1:
            m.byte(address, 0)
        else:
            m.word(address, 0)
    m.word(0x3870a000 + 0x10, 0x12345678)
    assert m.call('handoff', CTX) == 0xffffffff
    assert m.f('mode') == 1
    checks.append('final handoff independently rejects physical pressed byte, display queue, and changed touch inode class')

    m = Machine().ready()
    m.f('overlay', 1)
    before = len(m.frames)
    m.word(PLANE + 24, 0)
    m.call('pan', 0x384ef84c, PLANE)
    m.call('area', 0x384ef84c, PLANE)
    assert len(m.frames) == before and not m.area_calls
    m.f('overlay', 0)
    m.call('pan', 0x384ef84c, PLANE)
    m.call('area', 0x384ef84c, PLANE)
    assert m.frames[-1] == 0 and m.area_calls == 1
    m.word(PLANE + 24, 0xffffffff)
    before = len(m.frames)
    assert m.call('pan', 0x384ef84c, PLANE) == 0xffffffff
    assert len(m.frames) == before
    checks.append('overlay suppresses both original display routes, settled stock restores both, and relocation remains rejected')

    m = Machine().ready()
    m.word(0x384fce54, 3)
    m.tick()
    assert m.word(0x384fce58) == 0x3806a93d
    ticks = m.gui_ticks
    m.call('timer', 0x389d0200)
    assert m.gui_ticks == ticks + 1
    checks.append('closing native timer is not rearmed; foreign timer handle delegates to original callback')

    for allocations, create_result, expected_frees in [
        ([CTX, PIXELS], 0, []), ([0], 0, []), ([CTX, 0], 0, [CTX]),
        ([CTX, PIXELS], -1, [PIXELS, CTX]),
    ]:
        m = Machine()
        context_allocated = bool(allocations[0])
        m.allocations = allocations
        m.create_result = create_result
        assert m.call('broker_main', 2, 0x389d0200) == 17
        assert m.original_calls == 1 and m.freed == expected_frees
        if context_allocated and create_result == 0:
            assert m.f('alive') == 0
    checks.append('original main runs exactly once and preserves status through normal return, heap failures and thread-create failure')

    m = Machine().ready()
    for _ in range(3):
        for _ in range(5):
            m.tick(gpio=0x0c000000)
        for _ in range(5):
            m.tick(gpio=0x0e000000)
    assert m.f('wanted') == 1 and m.f('toggles') == 1
    m.settle()
    assert m.f('mode') == 1
    m.clock_result = -1
    m.tick()
    assert m.byte(CTX + F['keys'] + 16) == 1
    checks.append('GUI-clock-driven key3 triple release opens without a worker; clock failure disarms gesture state')

    result = {
        'passed': True,
        'hardware_operation': False,
        'elf_sha256': hashlib.sha256(ELF.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256((ELF.with_suffix('.c')).read_bytes()).hexdigest(),
        'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'check_count': len(checks),
        'checks': checks,
        'limitations': 'Actual ARM instructions execute; native APIs, IRQs, locks, LCD scanout and OS scheduling are mocked. No hardware accessed.',
    }
    destination = ROOT / 'analysis/display-takeover/drawer-arm-offline-result.json'
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
