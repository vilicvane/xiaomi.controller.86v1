"""Execute the GitHub tap ARM ELF with native APIs mocked; no hardware.

Prior Machine helpers are imported without invoking any older result writer.
Tests distinguish submitted poses from animation phase and clock admission.
"""
from pathlib import Path
import hashlib
import json

import test_native_drawer_arm as original
import render_github_tap_reference as reference
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP,
)

ROOT = Path(__file__).resolve().parents[2]
ELF = ROOT / 'analysis/display-takeover/native-github-tap.elf'
original.old.ELF = ELF
CTX, PIXELS, DRIVERS, UPPERS, SUBS = (
    original.CTX, original.PIXELS, original.DRIVERS, original.UPPERS, original.SUBS)
PLANE = original.PLANE
FROM, PENDING, PHASE, FEEDBACK_MS, FEEDBACK_PENDING = 164, 168, 172, 176, 180


class Machine(original.Machine):
    def __init__(self, **options):
        self.pan_delay = 0
        self.pan_result = 0
        self.pan_calls = 0
        self.clock_calls = 0
        self.fail_clock_calls = set()
        self.poses = []
        self.allocation_sizes = []
        super().__init__(**options)

    def hook(self, address, method):
        if address == 0x383d9420:
            def allocate():
                self.allocation_sizes.append(self.uc.reg_read(UC_ARM_REG_R0))
                method()
            return super().hook(address,allocate)
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
        self.field(FEEDBACK_MS, 0)
        self.field(FEEDBACK_PENDING, 0)

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
    regs = [UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
            UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11]
    sentinel = [0x12340000+i*0x111 for i in range(8)]
    stack_failures = []
    m.uc.hook_add(UC_HOOK_CODE, lambda uc,pc,size,_: stack_failures.append(pc)
                  if uc.reg_read(UC_ARM_REG_SP)%8 else None)
    for count in (0, 1):
        for cover in range(321):
            m.uc.mem_write(PIXELS-len(guard), guard)
            m.uc.mem_write(PIXELS, blank)
            m.uc.mem_write(PIXELS+len(blank), guard)
            for reg,value in zip(regs,sentinel): m.uc.reg_write(reg,value)
            m.call('paint', PIXELS, cover, count)
            assert bytes(m.uc.mem_read(PIXELS,len(blank))) == reference.render(cover,seed,count).tobytes(), (cover,count)
            assert bytes(m.uc.mem_read(PIXELS-len(guard),len(guard))) == guard
            assert bytes(m.uc.mem_read(PIXELS+len(blank),len(guard))) == guard
            assert [m.uc.reg_read(reg) for reg in regs] == sentinel
            assert m.uc.reg_read(UC_ARM_REG_SP) == 0x389eff00
    for count in (2,9,10,99,100,1234567890,0xffffffff):
        m.uc.mem_write(PIXELS, blank)
        m.call('paint',PIXELS,320,count)
        assert bytes(m.uc.mem_read(PIXELS,len(blank))) == reference.render(320,seed,count).tobytes(),count
        assert [m.uc.reg_read(reg) for reg in regs] == sentinel
        assert m.uc.reg_read(UC_ARM_REG_SP) == 0x389eff00
    assert not stack_failures
    for count in (0,1,10):
        m.uc.mem_write(PIXELS,reference.render(0).tobytes())
        m.call('paint',PIXELS,320,count)
        framebuffer=bytes(m.uc.mem_read(PIXELS,len(blank)))
        assert framebuffer == reference.render(count=count).tobytes()
        (ROOT/f'analysis/display-takeover/github-tap-preview-{count}.rgba').write_bytes(framebuffer)
    return [
        'all321 cover positions in both star and+1 states match independent logical pixel oracle exactly',
        'multi-digit2/9/10/99/100/1234567890/UINT32_MAX match centered5x7 scale3 independent oracle',
        'cover0 paints no pixels and arbitrary unpainted seeds plus both128-byte framebuffer redzones remain unchanged',
        'paint/stamp/number preserve allr4-r11 and exactSP with8-byte alignment at every executed instruction',
        'static star state preserves frozen card pixel layout; ignored0/1/10 raw previews emitted for root inspection',
    ]


def feedback_checks():
    checks=[]
    def tap(m, x=200,y=100):
        m.contact(m.physical_index,True,x=x,y=y)
        m.contact(m.physical_index,False,x=x,y=y)
    def pixels(m,count):
        assert bytes(m.uc.mem_read(PIXELS,614400)) == reference.render(count=count).tobytes(),count
    m=Machine().ready().custom()
    tap(m); assert m.f('count')==1 and m.field(FEEDBACK_PENDING)==1
    m.tick(ms=0); pixels(m,1)
    for value in range(2,11):
        m.now+=30;tap(m);m.tick(ms=0);assert m.f('count')==value
    pixels(m,10)
    m.f('count',98);tap(m);m.tick(ms=0);pixels(m,99)
    tap(m);m.tick(ms=0);pixels(m,100)
    m.f('count',0xfffffffe);tap(m);m.tick(ms=0);pixels(m,0xffffffff)
    tap(m);assert m.f('count')==0xffffffff and m.field(FEEDBACK_PENDING)==1
    checks.append('physicalUP increments sequence across9/10 and99/100 and saturatesUINT32_MAX while extending feedback timestamp')

    m=Machine().ready().custom();tap(m);m.tick(ms=0)
    m.tick(ms=799);assert m.f('count')==1;pixels(m,1)
    m.tick(ms=1);assert m.f('count')==0;pixels(m,0)
    tap(m);m.tick(ms=0);assert m.f('count')==1;pixels(m,1)
    m.tick(ms=700);tap(m);m.tick(ms=0);m.tick(ms=799);assert m.f('count')==2;pixels(m,2)
    m.tick(ms=1);assert m.f('count')==0;pixels(m,0)
    checks.append('800ms expiry restores star on accepted frame then restarts at1; repeatedUP resets full feedback interval')

    m=Machine().ready().custom();tap(m);m.tick(ms=0)
    m.word(0x384ef93c,1);before=bytes(m.uc.mem_read(PIXELS,614400));frames=len(m.frames)
    m.tick(ms=900);assert m.f('count')==1 and len(m.frames)==frames
    assert bytes(m.uc.mem_read(PIXELS,614400))==before
    tap(m);assert m.f('count')==2
    m.word(0x384ef93c,0);m.tick(ms=0);pixels(m,2)
    m.word(0x384ef93c,1);m.tick(ms=800);assert m.f('count')==2
    m.word(0x384ef93c,0);m.tick(ms=0);assert m.f('count')==0;pixels(m,0)
    tap(m);assert m.f('count')==1
    checks.append('busyframe queue never mutates canvas; overdue but unsubmitted star keeps sequence for next tap until accepted restoration')

    m=Machine().ready().custom();tap(m);m.tick(ms=0)
    m.pan_result=-1;m.tick(ms=800);assert m.f('count')==1 and m.f('dirty')==1
    tap(m);assert m.f('count')==2
    m.pan_result=0;m.tick(ms=0);pixels(m,2)
    m.tick(ms=800);assert m.f('count')==0;pixels(m,0)
    checks.append('failed restorationPAN cannot reset sequence; next tap retains count and success later clears it')

    for physical in (0,1):
        m=Machine(physical=physical).ready().custom()
        m.contact(physical,True)
        for _ in range(10):m.tick(ms=100)
        assert m.f('count')==0
        m.contact(physical,False);assert m.f('count')==1
        m.contact(physical,False);assert m.f('count')==1
        m.contact(physical^1,True);m.contact(physical^1,False);assert m.f('count')==1
    checks.append('long-held contacts do not increment while held; originaltapUP counts once with either physical ordering and ignores virtual/repeatedUP')

    for dx,dy in [(70,0),(0,-15),(0,-80),(0,30),(30,40)]:
        m=Machine().ready().custom();m.contact(0,True,x=100,y=200)
        m.contact(0,True,x=100+dx,y=200+dy);m.contact(0,False)
        assert m.f('count')==0,(dx,dy)
    checks.append('horizontal/up/down/diagonal movements past12px slop never fire feedback, including dismiss gestures')

    m=Machine().ready().custom();m.now=0xfffffff0;tap(m);m.tick(ms=0);m.tick(ms=799)
    assert m.f('count')==1 and m.field(FEEDBACK_MS)==0xfffffff0
    m.tick(ms=1);assert m.f('count')==0;pixels(m,0)
    m=Machine().ready().custom();m.clock_result=-1;tap(m)
    assert m.f('count')==1 and m.field(FEEDBACK_PENDING)==1
    m.tick(ms=900);assert m.f('count')==1 and m.field(FEEDBACK_PENDING)==1
    m.clock_result=0;m.tick(ms=0)
    assert m.field(FEEDBACK_MS)==m.now and not m.field(FEEDBACK_PENDING)
    m.tick(ms=799);assert m.f('count')==1
    m.tick(ms=1);assert m.f('count')==0;pixels(m,0)
    checks.append('UINT32 feedback clockwrap expires at800ms; tap survivesCLOCKfailure and receives a fresh full interval on validclock recovery')

    m=Machine().ready().custom();m.now+=1000;tap(m)
    assert m.f('count')==1 and m.field(FEEDBACK_PENDING)==1
    m.tick(ms=0);assert m.f('count')==1 and m.field(FEEDBACK_MS)==m.now;pixels(m,1)
    m.tick(ms=799);assert m.f('count')==1
    m.tick(ms=1);assert m.f('count')==0
    m=Machine().ready().custom();m.now=0xffffffff;tap(m);m.tick(ms=0)
    assert m.field(FEEDBACK_MS)==0xffffffff and not m.field(FEEDBACK_PENDING)
    m.tick(ms=799);assert m.f('count')==1
    m.tick(ms=1);assert m.f('count')==0
    checks.append('staleUP1000ms anchors on firstfreshGUIclock and genuineFFFFFFFF anchor never collides with explicitpending flag')

    m=Machine().ready().custom();m.word(0x384ef93c,1);m.clock_result=-1
    before=bytes(m.uc.mem_read(PIXELS,614400));frames=len(m.frames)
    tap(m);m.tick(ms=1000);tap(m);m.tick(ms=1000)
    assert m.f('count')==2 and m.field(FEEDBACK_PENDING)==1
    assert len(m.frames)==frames and bytes(m.uc.mem_read(PIXELS,614400))==before
    m.clock_result=0;m.tick(ms=0);anchor=m.now
    assert m.field(FEEDBACK_MS)==anchor and not m.field(FEEDBACK_PENDING)
    m.tick(ms=700);tap(m);m.tick(ms=0)
    assert m.f('count')==3 and m.field(FEEDBACK_MS)==m.now
    m.word(0x384ef93c,0);m.tick(ms=799);assert m.f('count')==3;pixels(m,3)
    m.tick(ms=1);assert m.f('count')==0;pixels(m,0)
    checks.append('queuedrepeatedtaps acrossinvalidCLOCK retain sequence/pending/canvas then each valid freshanchor extends expiry without replay')

    m=Machine().ready().custom();tap(m);m.tick(ms=0)
    m.contact(0,True,y=300);m.contact(0,True,y=200);m.contact(0,False)
    assert m.f('target')==0 and m.f('count')==0 and not m.field(FEEDBACK_PENDING)
    m.settle();assert m.f('mode')==0
    m.f('wanted',1);m.settle();assert m.f('mode')==1 and m.f('count')==0
    tap(m);assert m.f('count')==1
    checks.append('dismiss transition discards prior feedback and returning to custom starts a new sequence at1')
    return checks

def layout_checks():
    from elftools.elf.elffile import ELFFile
    with ELF.open('rb') as stream:
        elf=ELFFile(stream)
        sections={s.name:s for s in elf.iter_sections() if s['sh_flags']&2 and s['sh_size']}
        assert set(sections)=={'.prefix','.start','.broker','.feedback'}
        assert sections['.prefix']['sh_addr']==0x3804b108 and sections['.prefix']['sh_size']<=492
        assert sections['.start']['sh_addr']==0x3804b2f4 and sections['.start']['sh_size']==4
        assert sections['.broker']['sh_addr']==0x3804b2f8
        assert sections['.broker']['sh_addr']+sections['.broker']['sh_size']<=0x3804be70
        assert sections['.feedback']['sh_addr']==0x3807a764 and sections['.feedback']['sh_size']<=444
        main=bytearray(sections['.broker']['sh_addr']+sections['.broker']['sh_size']-0x3804b108)
        for name in ('.prefix','.start','.broker'):
            s=sections[name];off=s['sh_addr']-0x3804b108;main[off:off+s['sh_size']]=s.data()
        assert bytes(main)==ELF.with_suffix('.bin').read_bytes()
        assert sections['.feedback'].data()==(ELF.parent/'native-github-tap-feedback.bin').read_bytes()
    frozen=json.loads((ROOT/'analysis/persistence/native-github-card-frozen-inputs.json').read_text())
    changed=[p for p,h in frozen['sha256'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    m=Machine();m.call('broker_main',2,0x389d0200)
    assert m.allocation_sizes==[184,1228800]
    return [
        'ELF has only four approved alloc sections; main stays belowbe70 and auxiliary stays in444-byte bounded3807a764 slot',
        'separate main andfeedback BIN files exactly match actual linked ARM ELF sections without high-address flattened hole',
        f'all{len(frozen["sha256"])} priorcard frozen inputs remainbyte-identical and broker actuallyALLOCs184-byte context plus1228800-byte canvas/snapshot',
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

    checks.extend(feedback_checks())
    checks.extend(renderer_checks())
    checks.extend(layout_checks())
    result = {
        'passed': True, 'hardware_operation': False,
        'context_bytes': 184, 'feedback_ms_offset': 176, 'feedback_pending_offset': 180,
        'main_bytes': (ELF.with_suffix('.bin')).stat().st_size,
        'feedback_bytes': (ELF.parent/'native-github-tap-feedback.bin').stat().st_size,
        'main_sha256': hashlib.sha256(ELF.with_suffix('.bin').read_bytes()).hexdigest(),
        'feedback_sha256': hashlib.sha256((ELF.parent/'native-github-tap-feedback.bin').read_bytes()).hexdigest(),
        'main_runtime_start': '0x3804b108', 'main_runtime_end_exclusive': '0x3804be48', 'main_limit_end_exclusive': '0x3804be70',
        'feedback_runtime_start': '0x3807a764', 'feedback_limit_end_exclusive': '0x3807a920',
        'elf_sha256': hashlib.sha256(ELF.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256(ELF.with_suffix('.c').read_bytes()).hexdigest(),
        'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reference_sha256': hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest(),
        'logo_header_sha256': hashlib.sha256((ELF.parent / 'github-tap-logo.h').read_bytes()).hexdigest(),
        'check_count': len(checks), 'checks': checks,
        'limitations': 'Actual ARM instructions execute. Native APIs, IRQs, mutexes, LCD scanout and OS scheduling are mocked; admitted poses do not prove physical LCD cadence. No hardware accessed.',
    }
    destination = ROOT / 'analysis/display-takeover/github-tap-arm-offline-result.json'
    destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
