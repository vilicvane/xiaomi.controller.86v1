"""Execute the GitHub card ARM ELF with native APIs mocked; no hardware.

Prior Machine helpers are imported without invoking any older result writer.
Tests distinguish submitted poses from animation phase and clock admission.
"""
from pathlib import Path
import hashlib
import json

import test_native_drawer_arm as original
import render_github_card_reference as reference
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP,
)

ROOT = Path(__file__).resolve().parents[2]
ELF = ROOT / 'analysis/display-takeover/native-github-card.elf'
original.old.ELF = ELF
CTX, PIXELS, DRIVERS, UPPERS, SUBS = (
    original.CTX, original.PIXELS, original.DRIVERS, original.UPPERS, original.SUBS)
PLANE = original.PLANE
FROM, PENDING, PHASE = 164, 168, 172


class Machine(original.Machine):
    def __init__(self, **options):
        self.pan_delay = 0
        self.pan_result = 0
        self.pan_calls = 0
        self.clock_calls = 0
        self.fail_clock_calls = set()
        self.poses = []
        super().__init__(**options)

    def hook(self, address, method):
        if address == 0x383df2dc:
            def wrapped():
                self.pan_calls += 1
                self.now += self.pan_delay
                if self.pan_result:
                    self.ret(self.pan_result)
                else:
                    method()
                    if self.frames[-1] == PIXELS:
                        self.poses.append(self.f('cover'))
            return super().hook(address, wrapped)
        if address == 0x38004c38:
            def wrapped():
                self.clock_calls += 1
                if self.clock_calls in self.fail_clock_calls:
                    self.ret(-1)
                else:
                    method()
            return super().hook(address, wrapped)
        return super().hook(address, method)

    def _graph(self):
        super()._graph()
        self.field(FROM, 0)
        self.field(PENDING, 0)
        self.field(PHASE, 150)

    def start(self, custom=False):
        if custom:
            self.custom()
        self.f('wanted', int(not custom))
        self.tick(ms=0)
        assert self.f('overlay') == 1 and self.field(PENDING) == 0
        assert self.field(PHASE) == 0
        assert self.f('cover') == (320 if custom else 0)
        assert self.field(FROM) == self.f('cover')
        assert self.f('animation_ms') == (self.now & 0xffffffff)
        return self


def renderer_checks():
    m = Machine()
    seed = 0x13579bdf
    blank = seed.to_bytes(4, 'little') * (480 * 320)
    guard = bytes([0xa7]) * 128
    saved_registers = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                       UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
    sentinel = [0x12340000 + i * 0x111 for i in range(8)]
    stack_failures = []

    def stack_guard(uc, pc, size, ignored):
        if uc.reg_read(UC_ARM_REG_SP) % 8:
            stack_failures.append(pc)

    m.uc.hook_add(UC_HOOK_CODE, stack_guard)
    for cover in range(321):
        m.uc.mem_write(PIXELS - len(guard), guard)
        m.uc.mem_write(PIXELS, blank)
        m.uc.mem_write(PIXELS + len(blank), guard)
        for reg, value in zip(saved_registers, sentinel):
            m.uc.reg_write(reg, value)
        m.call('paint', PIXELS, cover)
        assert bytes(m.uc.mem_read(PIXELS, len(blank))) == reference.render(cover, seed).tobytes(), cover
        assert bytes(m.uc.mem_read(PIXELS - len(guard), len(guard))) == guard
        assert bytes(m.uc.mem_read(PIXELS + len(blank), len(guard))) == guard
        assert [m.uc.reg_read(reg) for reg in saved_registers] == sentinel
        assert m.uc.reg_read(UC_ARM_REG_SP) == 0x389eff00
    assert not stack_failures
    m.uc.mem_write(PIXELS, reference.render(0).tobytes())
    m.call('paint', PIXELS, 320)
    framebuffer = bytes(m.uc.mem_read(PIXELS, len(blank)))
    assert framebuffer == reference.render().tobytes()
    (ROOT / 'analysis/display-takeover/github-card-preview.rgba').write_bytes(framebuffer)
    smooth = (ROOT / 'analysis/display-takeover/native-drawer-smooth.c').read_text()
    card = ELF.with_suffix('.c').read_text()
    normalized = card[card.index('static int pan('):].replace(
        'paint(c->pixels,c->cover);', 'paint(c->pixels,c->count,c->cover);')
    assert normalized == smooth[smooth.index('static int pan('):]
    return [
        'all321 cover positions match independent original-row pixel oracle exactly, including48px official logo and exact22-character project label',
        'paint cover0 changes no pixels; unpainted pixels keep arbitrary seed and both128-byte framebuffer red zones remain unchanged',
        'private paint/stamp preserve allr4-r11, exactSP return and8-byte stack alignment at every executed instruction across321 covers',
        'fullcard dark background/white-gray-gold framebuffer matches independent oracle; ignored raw preview emitted for visual review',
        'ownership/touch/key/animation source frompan onward equals frozen smooth after normalizing only the private renderer call',
    ]


def main():
    checks = []

    for physical in (0, 1):
        m = Machine(physical=physical, cached_held=True)
        m.tick()
        assert m.f('ready') == 1 and m.f('physical') == physical
        assert m.word(DRIVERS[0] + 4) == m.symbols['touch']
        assert m.word(DRIVERS[1] + 4) == m.symbols['touch']
        assert m.contact(physical, True, x=100, y=0)[18] == 1
        assert not m.f('overlay')
        m.release()
        assert not m.byte(CTX + original.F['gesture'] + 8)
    checks.append('new ELF preserves two input hooks, physical/virtual classification in either order and boot-held contact protection')

    for custom, expected in [(False, (33, 112, 207, 286, 320)),
                             (True, (287, 208, 113, 34, 0))]:
        m = Machine().ready().start(custom=custom)
        for phase, cover in zip((30, 60, 90, 120, 150), expected):
            m.tick(ms=30)
            assert m.field(PHASE) == phase and m.f('cover') == cover
            assert m.f('shown') == cover
        assert len(set(m.poses)) >= 6  # Origin plus five distinct transitions.
        m.tick(ms=0)
        assert m.f('mode') == int(not custom) and not m.f('overlay')
    checks.append('150ms smoothstep admits origin plus five distinct capped poses in both directions, then commits owner')

    for custom in (False, True):
        m = Machine().ready().start(custom=custom)
        previous = m.f('cover')
        for _ in range(30):
            m.tick(ms=5)
            current = m.f('cover')
            assert 0 <= current <= 320
            assert current <= previous if custom else current >= previous
            previous = current
        assert m.field(PHASE) == 150 and previous == (0 if custom else 320)
    checks.append('every5ms accepted pose is monotonic and bounded, including integer-rounded near-end frames')

    m = Machine().ready()
    m.contact(0, True, x=100, y=0)
    m.contact(0, True, x=100, y=40)
    m.tick()
    assert m.f('shown') == 40
    m.contact(0, True, x=100, y=100)
    assert m.f('cover') == 100 and m.f('shown') == 40
    m.now += 100  # UP arrives with a stale previously sampled GUI clock.
    m.contact(0, False)
    assert m.field(PENDING) == 1 and m.field(FROM) == 40 and m.f('cover') == 40
    m.word(0x384ef93c, 1)
    frames = len(m.frames)
    pixels = bytes(m.uc.mem_read(PIXELS, 64))
    m.tick(ms=300)
    assert m.field(PHASE) == 0 and m.field(PENDING) == 1
    assert len(m.frames) == frames and bytes(m.uc.mem_read(PIXELS, 64)) == pixels
    m.word(0x384ef93c, 0)
    m.pan_delay = 150
    m.tick(ms=0)
    assert m.f('cover') == 40 and m.f('shown') == 40 and m.field(PHASE) == 0
    assert m.field(PENDING) == 0 and m.f('animation_ms') == (m.now & 0xffffffff)
    m.tick(ms=30)
    assert m.field(PHASE) == 30 and 40 < m.f('cover') < 100
    checks.append('staleUP100ms, queued wait300ms and originPAN150ms all preserve last admitted40px origin; phase starts only after fresh post-origin clock')

    m = Machine().ready()
    m.f('shown', 0xffffffff)
    m.f('cover', 17)
    m.f('wanted', 1)
    m.tick(ms=0)
    assert m.field(FROM) == 17 and m.f('shown') == 17 and m.field(PHASE) == 0
    checks.append('unavailable shown sentinel falls back to logical cover before snapshot resets shown')

    for custom in (False, True):
        m = Machine().ready().start(custom=custom)
        previous = m.f('cover')
        for phase in (30, 60, 90, 120, 150):
            m.tick(ms=300)
            assert m.field(PHASE) == phase
            assert m.f('cover') <= previous if custom else m.f('cover') >= previous
            previous = m.f('cover')
        assert len(set(m.poses)) == 6
    checks.append('each300ms scheduling stall earns at most30ms phase, preserving five intermediate transitions rather than jumping to endpoint')

    m = Machine().ready()
    m.pan_delay = 20
    m.start()
    transitions = 0
    while m.field(PHASE) < 150:
        m.tick(ms=5)
        transitions += 1
    assert transitions == 7 and len(set(m.poses)) >= 6
    checks.append('20ms render/PAN plus5ms idle completes in seven transition submissions, counting previous render cost instead of stretching to thirty frames')

    m = Machine().ready()
    m.f('wanted', 1)
    m.fail_clock_calls.add(m.clock_calls + 2)  # First draw's post-PAN CLOCK.
    m.tick(ms=0)
    assert m.field(PENDING) == 1 and m.field(PHASE) == 0 and m.f('shown') == 0
    assert m.f('mode') == 0
    m.pan_delay = 150
    m.tick(ms=300)
    assert m.field(PENDING) == 0 and m.field(PHASE) == 0 and m.f('cover') == 0
    assert m.f('animation_ms') == (m.now & 0xffffffff)
    checks.append('CLOCK failure after admitted origin keeps pending and phase0; recovery re-admits origin and anchors freshly without ownership change')

    m = Machine().ready().start()
    m.pan_result = -1
    before = len(m.frames)
    m.tick(ms=30)
    assert m.field(PHASE) == 0 and m.f('shown') == 0 and len(m.frames) == before
    assert m.f('mode') == 0
    m.pan_result = 0
    m.tick(ms=300)
    assert m.field(PHASE) == 30 and m.f('shown') == 33
    checks.append('failedPAN does not admit a pose, consume phase or commit owner; later recovery receives only one capped phase increment')

    m = Machine().ready().start()
    old_anchor = m.f('animation_ms')
    m.fail_clock_calls.add(m.clock_calls + 2)
    m.tick(ms=30)
    assert m.f('shown') == 33 and m.field(PHASE) == 0
    assert m.f('animation_ms') == old_anchor and m.f('mode') == 0
    m.tick(ms=30)
    assert m.field(PHASE) == 30 and m.f('shown') == 33
    assert m.poses[-2:] == [33, 33]
    checks.append('postPAN CLOCK failure records admitted pose but leaves phase/anchor unchanged; recovery re-admits same pose without moving backward')

    m = Machine().ready()
    m.now = 0xfffffff0
    m.start()
    for phase in (30, 60, 90, 120, 150):
        m.tick(ms=30)
        assert m.field(PHASE) == phase
    assert m.f('clock_ms') == 134 and m.f('cover') == 320
    checks.append('UINT32 clock wrap preserves capped phase progression and final endpoint')

    m = Machine().ready().start()
    m.tick(ms=30)
    assert m.f('shown') == 33
    m.pan_result = -1
    m.tick(ms=30)
    assert m.f('cover') == 112 and m.f('shown') == 33
    m.word(0x384ef93c, 1)
    for _ in range(3):
        for _ in range(5): m.tick(gpio=0x0c000000)
        for _ in range(5): m.tick(gpio=0x0e000000)
    assert m.f('wanted') == 0 and m.field(PENDING) == 1
    assert m.field(FROM) == 33 and m.f('cover') == 33 and m.field(PHASE) == 0
    m.pan_result = 0; m.word(0x384ef93c, 0)
    m.tick(ms=0)
    assert m.f('shown') == 33 and m.field(PENDING) == 0
    m.settle()
    assert m.f('mode') == 0 and not m.f('overlay')
    checks.append('key retarget resets from actually admitted33px pose, never logical112px pose from failedPAN')

    m = Machine().ready().custom()
    m.contact(0, True, y=300)
    m.contact(0, True, y=220)
    m.tick(ms=300)
    assert m.f('cover') == 240 and m.f('shown') == 240
    assert m.byte(CTX + original.F['gesture'] + 8) == 1
    m.tick(ms=300)
    assert m.f('cover') == 240  # Held touch cannot start snap progression.
    m.contact(0, False)
    assert m.field(PENDING) == 1 and m.field(FROM) == 240
    m.settle()
    assert m.f('mode') == 0 and not m.f('count')
    checks.append('held contact remains direct finger-follow even across300ms GUI gaps; upward release starts closing only afterward')

    m = Machine().ready().custom()
    m.f('shown', 1); m.f('cover', 1); m.f('wanted', 0)
    m.tick(ms=0)
    for phase in (30, 60, 90, 120, 150):
        m.tick(ms=30)
        assert m.field(PHASE) == phase
    assert m.f('cover') == 0
    m.tick(ms=0)
    assert m.f('mode') == 0
    checks.append('one-pixel transition advances through rounded-identical admitted poses and reaches handoff instead of freezing phase')

    m = Machine().ready().start()
    assert m.contact(0, True, y=200)[18] == 0
    for _ in range(6): m.tick(ms=30)
    assert m.field(PHASE) == 150 and m.f('mode') == 0 and m.f('overlay') == 1
    assert m.contact(0, False)[18] == 0
    m.tick(ms=0); m.tick(ms=0)
    assert m.f('mode') == 1 and not m.f('count')
    checks.append('new contact during snap is swallowed untilUP and blocks owner handoff despite completed phase')

    m = Machine().ready().custom()
    m.contact(0, True)
    for _ in range(10): m.contact(0, True)
    assert not m.f('count')
    m.contact(0, False)
    assert m.f('count') == 1 and not m.f('overlay') and not m.field(PENDING)
    m.contact(0, False)
    m.contact(1, True, y=0); m.contact(1, True, y=200); m.contact(1, False)
    assert m.f('count') == 1 and not m.f('overlay') and not m.field(PENDING)
    checks.append('ordinary physical tap counts once onUP without pendingoverlay; held/repeatedUP and virtual contacts do not count or animate')

    m = Machine().ready()
    assert m.contact(0, True, y=21)[18] == 1
    assert m.contact(0, True, y=0)[18] == 1
    m.contact(0, False)
    assert not m.f('overlay')
    m.contact(1, True)
    assert m.contact(0, True, y=0)[18] == 1 and not m.f('overlay')
    m.release()
    m.contact(0, True, x=100, y=0); m.contact(0, True, x=170, y=40)
    assert m.contact(0, True, x=100, y=200)[18] == 0
    m.contact(0, False); m.settle()
    assert m.f('mode') == 0
    checks.append('stock contacts below top band pass completely; delivered virtualDOWN prevents interception; cancelled horizontal contact remains swallowed')

    for pending in (0, 1):
        m = Machine().ready().custom()
        m.f('wanted', 0)
        m.word(SUBS[pending] + 8, 32)
        assert m.call('handoff', CTX) == 0xffffffff and m.f('mode') == 1
        m.word(SUBS[pending] + 12, 32)
        assert m.call('handoff', CTX) == 0 and m.f('mode') == 0
        assert ('lock', UPPERS[0] + 4) in m.lock_history
        assert ('lock', UPPERS[1] + 4) in m.lock_history
    checks.append('physical and virtual queued rings independently block final handoff, enclosed by both publisher mutexes')

    m = Machine().ready().custom()
    m.f('wanted', 0)
    m.byte(0x384f50a1, 1)
    assert m.call('handoff', CTX) == 0xffffffff
    m.byte(0x384f50a1, 0); m.word(0x384ef93c, 1)
    assert m.call('handoff', CTX) == 0xffffffff
    m.word(0x384ef93c, 0); m.word(0x3870a000 + 0x10, 0x12345678)
    assert m.call('handoff', CTX) == 0xffffffff and m.f('mode') == 1
    checks.append('physical pressed byte, queued display frame and changed inode class retain independent final handoff guards')

    m = Machine().ready()
    m.f('overlay', 1); m.word(PLANE + 24, 0)
    before = len(m.frames)
    m.call('pan', 0x384ef84c, PLANE); m.call('area', 0x384ef84c, PLANE)
    assert len(m.frames) == before and not m.area_calls
    m.f('overlay', 0)
    m.call('pan', 0x384ef84c, PLANE); m.call('area', 0x384ef84c, PLANE)
    assert m.frames[-1] == 0 and m.area_calls == 1
    m.word(PLANE + 24, 0xffffffff); before = len(m.frames)
    assert m.call('pan', 0x384ef84c, PLANE) == 0xffffffff and len(m.frames) == before
    checks.append('custom/overlay still suppresses both stock display paths; stock delegation and relocation rejection remain intact')

    m = Machine().ready()
    m.word(0x384fce54, 3); m.tick()
    assert m.word(0x384fce58) == 0x3806a93d and m.call('bootstrap', CTX) == 0
    for allocations, create_result, frees in [
        ([CTX, PIXELS], 0, []), ([0], 0, []), ([CTX, 0], 0, [CTX]),
        ([CTX, PIXELS], -1, [PIXELS, CTX]),
    ]:
        m = Machine(); m.allocations = allocations; m.create_result = create_result
        assert m.call('broker_main', 2, 0x389d0200) == 17
        assert m.original_calls == 1 and m.freed == frees
    checks.append('closed native timer and bootstrap lifetime stay safe; originalmain runs once with exact status across allocation/thread failures')

    m = Machine().ready().start()
    for _ in range(5): m.tick(ms=30)
    assert m.field(PHASE) == 150 and m.f('mode') == 0
    m.clock_result = -1; m.tick()
    assert m.f('mode') == 0 and m.f('overlay') == 1
    m.clock_result = 0; m.tick()
    assert m.f('mode') == 1 and not m.f('overlay')
    checks.append('CLOCK failure at finalphase blocks owner commit until a valid fresh timer clock is restored')

    checks.extend(renderer_checks())
    result = {
        'passed': True, 'hardware_operation': False,
        'elf_sha256': hashlib.sha256(ELF.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(ELF.with_suffix('.c').read_bytes()).hexdigest(),
        'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reference_sha256': hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest(),
        'logo_header_sha256': hashlib.sha256((ELF.parent / 'github-card-logo.h').read_bytes()).hexdigest(),
        'check_count': len(checks), 'checks': checks,
        'limitations': 'Actual ARM instructions execute. Native APIs, IRQs, mutexes, LCD scanout and OS scheduling are mocked; admitted poses do not prove physical LCD cadence. No hardware accessed.',
    }
    destination = ROOT / 'analysis/display-takeover/github-card-arm-offline-result.json'
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
