"""Execute the new drawer ease ELF with native APIs mocked; never use hardware.

Only the prior drawer Machine helpers are imported. Its main/result generator
is never called, preserving the first drawer's frozen tests and evidence.
"""
from pathlib import Path
import hashlib
import json

import test_native_drawer_arm as original

ROOT = Path(__file__).resolve().parents[2]
ELF = ROOT / 'analysis/display-takeover/native-drawer-ease.elf'
original.old.ELF = ELF
CTX, PIXELS, DRIVERS, UPPERS, SUBS = (
    original.CTX, original.PIXELS, original.DRIVERS, original.UPPERS, original.SUBS)
DATA, PLANE = original.DATA, original.PLANE
ANIMATION_FROM = 164


class Machine(original.Machine):
    def _graph(self):
        super()._graph()
        self.field(ANIMATION_FROM, 0)


def start_snap(custom=False, now=None):
    m = Machine().ready()
    if custom:
        m.custom()
    if now is not None:
        m.now = now
    m.f('wanted', int(not custom))
    m.tick(ms=0)
    assert m.f('overlay') == 1
    assert m.f('cover') == (320 if custom else 0)
    assert m.field(ANIMATION_FROM) == m.f('cover')
    assert m.f('animation_ms') == (m.now & 0xffffffff)
    return m


def main():
    checks = []

    for physical in (0, 1):
        m = Machine(physical=physical, cached_held=True)
        m.tick()
        assert m.f('ready') == 1 and m.f('physical') == physical
        assert m.word(DRIVERS[0] + 4) == m.symbols['touch']
        assert m.word(DRIVERS[1] + 4) == m.symbols['touch']
        assert m.byte(CTX + original.F['gesture'] + 8) == 1
        assert m.contact(physical, True, x=100, y=0)[18] == 1
        assert not m.f('overlay')
        m.release()
        assert not m.byte(CTX + original.F['gesture'] + 8)
    checks.append('new ELF retains reversed publisher classification, both callbacks, and boot-held contact protection')

    m = start_snap()
    observed = []
    for expected in (185, 280, 315, 320):
        m.tick(ms=30)
        observed.append(m.f('cover'))
        assert m.f('cover') == expected and m.f('shown') == expected
    m.tick(ms=0)
    assert m.f('mode') == 1 and not m.f('overlay')
    checks.append('opening cubic ease-out reaches exact cover 185/280/315/320 at 30/60/90/120ms and then commits custom owner')

    m = start_snap(custom=True)
    for expected in (135, 40, 5, 0):
        m.tick(ms=30)
        assert m.f('cover') == expected and m.f('shown') == expected
    m.tick(ms=0)
    assert m.f('mode') == 0 and not m.f('overlay') and m.frames[-1] == 0
    checks.append('closing uses the same curve in reverse, reaches 135/40/5/0, and returns default stock framebuffer')

    for custom in (False, True):
        m = start_snap(custom=custom)
        previous = m.f('cover')
        for _ in range(24):
            m.tick(ms=5)
            current = m.f('cover')
            assert 0 <= current <= 320
            assert current <= previous if custom else current >= previous
            previous = current
        assert previous == (0 if custom else 320)
    checks.append('every 5ms animation sample remains monotonic and within endpoints without overshoot in either direction')

    m = Machine().ready()
    assert m.contact(0, True, x=100, y=5)[18] == 0
    m.contact(0, True, x=100, y=85)
    assert m.f('cover') == 80
    m.tick(ms=30)
    assert m.f('cover') == 80 and m.f('shown') == 80
    m.contact(0, True, x=100, y=205)
    m.tick(ms=120)
    assert m.f('cover') == 200 and m.f('shown') == 200
    release_time = m.f('clock_ms')
    m.contact(0, False, x=0, y=0)
    assert m.f('target') == 320 and m.field(ANIMATION_FROM) == 200
    assert m.f('animation_ms') == release_time
    m.tick(ms=30)
    assert 200 < m.f('cover') < 320
    m.tick(ms=90)
    assert m.f('cover') == 320
    m.tick(ms=0)
    assert m.f('mode') == 1 and not m.f('count')
    checks.append('follow-finger displacement stays immediate while held; release records partial origin and starts a fresh 120ms snap')

    m = Machine().ready().custom()
    m.contact(0, True, y=300)
    m.contact(0, True, y=180)
    assert m.f('cover') == 200
    m.tick(ms=150)
    assert m.f('cover') == 200
    m.contact(0, False)
    assert m.field(ANIMATION_FROM) == 200 and m.f('target') == 0
    m.tick(ms=30)
    assert 0 < m.f('cover') < 200
    m.tick(ms=90)
    assert m.f('cover') == 0
    m.tick(ms=0)
    assert m.f('mode') == 0 and not m.f('count')
    checks.append('partial upward release animates from actual 200px cover and does not count the closing contact')

    m = start_snap()
    m.word(0x384ef93c, 1)
    pixel = m.word(PIXELS)
    frames = len(m.frames)
    m.tick(ms=30)
    m.tick(ms=60)
    assert m.word(PIXELS) == pixel and len(m.frames) == frames
    m.word(0x384ef93c, 0)
    m.tick(ms=30)
    assert m.f('cover') == 320 and m.f('shown') == 320
    checks.append('queued frames prevent canvas writes while absolute elapsed snap deadline still expires at120ms, without extending animation')

    m = start_snap(now=0xfffffff0)
    m.tick(ms=30)
    assert m.f('clock_ms') == 14 and m.f('cover') == 185
    m.tick(ms=90)
    assert m.f('cover') == 320
    m.tick(ms=0)
    assert m.f('mode') == 1
    checks.append('monotonic milliseconds wrapping across UINT32_MAX retain 30ms ease position and120ms endpoint')

    m = start_snap()
    m.tick(ms=30)
    assert m.f('cover') == 185
    m.word(0x384ef93c, 1)
    for _ in range(3):
        for _ in range(5):
            m.tick(gpio=0x0c000000)
        for _ in range(5):
            m.tick(gpio=0x0e000000)
    assert m.f('cover') == 185 and m.f('target') == 0 and m.f('wanted') == 0
    assert m.field(ANIMATION_FROM) == 185
    assert 0 <= ((m.now & 0xffffffff) - m.f('animation_ms')) <= 40
    m.word(0x384ef93c, 0)
    m.tick(ms=30)
    assert 0 <= m.f('cover') < 185
    m.tick(ms=120)
    m.tick(ms=0)
    assert m.f('mode') == 0 and not m.f('overlay')
    checks.append('key3 retargets an in-flight queued animation from actual185px cover with fresh start time, without jumping to an endpoint')

    m = start_snap()
    m.tick(ms=30)
    m.clock_result = -1
    m.tick(ms=30)
    assert m.f('cover') == 185
    m.clock_result = 0
    m.tick(ms=30)
    assert m.f('cover') == 315
    checks.append('CLOCK failure holds last valid eased position; recovered monotonic time catches up to actual elapsed90ms')

    m = start_snap()
    assert m.contact(0, True, y=200)[18] == 0
    m.tick(ms=120)
    m.tick(ms=0)
    assert m.f('mode') == 0 and m.f('overlay') == 1 and not m.f('count')
    assert m.contact(0, False)[18] == 0
    m.tick(ms=0)
    m.tick(ms=0)
    assert m.f('mode') == 1 and not m.f('overlay') and not m.f('count')
    checks.append('contact begun during snap remains fully swallowed through UP and blocks ownership even after animation deadline')

    m = Machine().ready()
    assert m.contact(0, True, y=21)[18] == 1
    assert m.contact(0, True, y=0)[18] == 1
    m.contact(0, False)
    assert not m.f('overlay')
    m.contact(0, True, x=100, y=0)
    m.contact(0, True, x=170, y=40)
    assert m.contact(0, True, x=100, y=200)[18] == 0
    m.contact(0, False)
    m.settle()
    assert m.f('mode') == 0 and not m.f('count')
    checks.append('new animation preserves complete stock contacts outside top band and latched horizontal cancellation inside it')

    m = Machine().ready().custom()
    m.contact(0, True)
    for _ in range(10):
        m.contact(0, True)
        m.tick()
    assert not m.f('count')
    m.contact(0, False)
    assert m.f('count') == 1
    m.contact(0, False)
    assert m.f('count') == 1
    m.contact(1, True, y=0)
    m.contact(1, True, y=200)
    m.contact(1, False)
    assert m.f('count') == 1 and not m.f('overlay')
    checks.append('custom hold counts once on physical UP, repeated release does not count, and virtual input never drives drawer or counter')

    for pending in (0, 1):
        m = Machine().ready().custom()
        m.f('wanted', 0)
        m.word(SUBS[pending] + 8, 32)
        assert m.call('handoff', CTX) == 0xffffffff
        assert m.f('mode') == 1
        m.word(SUBS[pending] + 12, 32)
        assert m.call('handoff', CTX) == 0
        assert m.f('mode') == 0 and m.frames[-1] == 0
        assert ('lock', UPPERS[0] + 4) in m.lock_history
        assert ('lock', UPPERS[1] + 4) in m.lock_history
    checks.append('either queued touch ring blocks final handoff and both publisher mutexes enclose successful mode commit')

    m = Machine().ready().custom()
    m.f('wanted', 0)
    m.byte(0x384f50a1, 1)
    assert m.call('handoff', CTX) == 0xffffffff
    m.byte(0x384f50a1, 0)
    m.word(0x384ef93c, 1)
    assert m.call('handoff', CTX) == 0xffffffff
    m.word(0x384ef93c, 0)
    m.word(0x3870a000 + 0x10, 0x12345678)
    assert m.call('handoff', CTX) == 0xffffffff and m.f('mode') == 1
    checks.append('new ELF keeps independent physical-pressed, display-queue and touch-class guards on final handoff')

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
    checks.append('both original display routes remain suppressed only under custom/overlay; stock delegation and relocation rejection remain intact')

    m = Machine().ready()
    m.word(0x384fce54, 3)
    m.tick()
    assert m.word(0x384fce58) == 0x3806a93d
    assert m.call('bootstrap', CTX) == 0
    checks.append('closed timer is not revived and bootstrap completes after readiness instead of running an input worker')

    for allocations, create_result, expected_frees in [
        ([CTX, PIXELS], 0, []), ([0], 0, []), ([CTX, 0], 0, [CTX]),
        ([CTX, PIXELS], -1, [PIXELS, CTX]),
    ]:
        m = Machine()
        m.allocations = allocations
        m.create_result = create_result
        assert m.call('broker_main', 2, 0x389d0200) == 17
        assert m.original_calls == 1 and m.freed == expected_frees
    checks.append('original main remains single-call with original status through ordinary return, heap failures and thread creation failure')

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
    assert m.byte(CTX + original.F['keys'] + 16) == 1
    checks.append('third-key triple trigger still opens via new snap and CLOCK failure disarms key state')

    result = {
        'passed': True,
        'hardware_operation': False,
        'elf_sha256': hashlib.sha256(ELF.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(ELF.with_suffix('.c').read_bytes()).hexdigest(),
        'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'check_count': len(checks),
        'checks': checks,
        'limitations': 'Actual ARM instructions execute; native APIs, IRQs, locks, LCD scanout and OS scheduling are mocked. No hardware accessed.',
    }
    destination = ROOT / 'analysis/display-takeover/drawer-ease-arm-offline-result.json'
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
