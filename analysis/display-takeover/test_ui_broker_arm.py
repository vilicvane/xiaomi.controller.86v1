"""Execute the actual A7 ELF with mocked native APIs; never access hardware.

Tests ownership/ABI glue, not LCD rotation, native locks, IRQs or NuttX scheduling.
Workspace-local dependencies: tools/python-ui-broker (unicorn, pyelftools).
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/python-ui-broker'))
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ELF = ROOT / 'analysis/display-takeover/native-ui-broker.elf'
STOP = 0x389f0000
CTX = 0x38710000
PIXELS = 0x38800000
DRIVERS = [0x38703000, 0x38704000]
FILES = [0x38709000, 0x38709100, 0x38709200]
UPPERS = [0x3870b000, 0x3870b100]
SUBS = [0x3870c000, 0x3870c100, 0x3870c200]


class Machine:
    def __init__(self):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.uc.mem_map(0x38000000, 0x1000000)
        self.uc.mem_map(0x40080000, 0x10000)
        self.uc.mem_map(0x50000000, 0x100000)
        self.symbols = {}
        with ELF.open('rb') as stream:
            elf = ELFFile(stream)
            for section in elf.iter_sections():
                if section['sh_flags'] & 2 and section['sh_size']:
                    self.uc.mem_write(section['sh_addr'], section.data())
            for symbol in elf.get_section_by_name('.symtab').iter_symbols():
                self.symbols[symbol.name] = symbol['st_value']
        self.locks = set()
        self.frames = []
        self.area_calls = 0
        self.touches = [{}, {}]
        self.native_ring = []
        self.gui_ticks = 0
        self.now = 1000
        self.worker_state = None
        self.original_calls = 0
        self.allocations = [CTX, PIXELS]
        self._install_hooks()
        self._graph()

    def word(self, address, value=None):
        if value is not None:
            self.uc.mem_write(address, struct.pack('<I', value & 0xffffffff))
        return struct.unpack('<I', self.uc.mem_read(address, 4))[0]

    def field(self, offset, value=None):
        return self.word(CTX + offset, value)

    def byte(self, address, value=None):
        if value is not None:
            self.uc.mem_write(address, bytes([value]))
        return self.uc.mem_read(address, 1)[0]

    def ret(self, value=0):
        self.uc.reg_write(UC_ARM_REG_R0, value & 0xffffffff)
        self.uc.reg_write(UC_ARM_REG_PC, self.uc.reg_read(UC_ARM_REG_LR))

    def hook(self, address, method):
        self.uc.hook_add(UC_HOOK_CODE, lambda uc, pc, size, data: method(), begin=address, end=address)

    def _install_hooks(self):
        r = lambda reg: self.uc.reg_read(reg)

        def lock():
            address = r(UC_ARM_REG_R0)
            assert address not in self.locks, f'recursive lock {address:x}'
            self.locks.add(address)
            self.ret()

        def unlock():
            address = r(UC_ARM_REG_R0)
            assert address in self.locks, f'unowned unlock {address:x}'
            self.locks.remove(address)
            self.ret()

        def zero():
            destination, size = r(UC_ARM_REG_R0), r(UC_ARM_REG_R2)
            self.uc.mem_write(destination, bytes([r(UC_ARM_REG_R1) & 255])*size)
            self.ret(destination)

        def getfile():
            fd = r(UC_ARM_REG_R0)
            if fd not in (6, 7, 8): self.ret(-9); return
            self.word(r(UC_ARM_REG_R1), FILES[fd-6])
            self.ret()

        def pan():
            assert r(UC_ARM_REG_R0) == 0x384ef84c
            source = self.word(r(UC_ARM_REG_R1)+24)
            self.frames.append(source)
            self.ret()

        def area():
            self.area_calls += 1
            self.ret()

        def touch():
            index = DRIVERS.index(r(UC_ARM_REG_R0))
            data = r(UC_ARM_REG_R1)
            self.uc.mem_write(data, bytes([0x5a])*20)
            state = self.touches[index].get('state', 0)
            again = self.touches[index].get('again', 0)
            self.byte(data+0x12, state)
            self.byte(data+0x13, again)
            self.word(SUBS[index]+0xc, self.word(SUBS[index]+8))
            self.ret()

        def timer():
            self.gui_ticks += 1
            self.word(0x384fce58, 0x3806a93d)
            self.ret()

        def clock():
            assert r(UC_ARM_REG_R0) == 1
            self.uc.mem_write(r(UC_ARM_REG_R1), struct.pack('<qii', self.now//1000, (self.now%1000)*1000000, 0))
            self.ret()

        def read():
            assert r(UC_ARM_REG_R0) == FILES[2] and r(UC_ARM_REG_R2) == 32
            if not self.native_ring: self.ret(-11); return
            flags = self.native_ring.pop(0)
            sample = bytearray(32)
            sample[:4] = struct.pack('<I', 1)
            sample[9] = flags
            self.uc.mem_write(r(UC_ARM_REG_R1), bytes(sample))
            if not self.native_ring: self.word(SUBS[2]+0xc, self.word(SUBS[2]+8))
            self.ret(32)

        def sleep():
            assert not self.locks, 'sleep with owned mutex'
            self.ret()
            self.uc.emu_stop()

        def original():
            self.original_calls += 1
            self.ret(17)

        for address in [0x3800da2c, 0x3800c1f8]: self.hook(address, lock)
        for address in [0x3800b0b4, 0x3800bb3c]: self.hook(address, unlock)
        for address, method in [(0x383d8fa0,zero),(0x38025678,getfile),(0x383df2dc,pan),
            (0x383df474,area),(0x3806ab74,touch),(0x3806a93c,timer),
            (0x38004c38,clock),(0x3802954c,read),(0x38042130,sleep),(0x3818f9fc,original)]:
            self.hook(address, method)
        self.hook(0x3802c900, lambda: self.ret(8))
        self.hook(0x38025d20, lambda: self.ret())
        self.hook(0x383d9420, lambda: self.ret(self.allocations.pop(0)))
        self.hook(0x383d93e4, lambda: self.ret())
        self.hook(0x383acc04, lambda: self.ret())

    def _graph(self):
        self.word(0x384fc864, CTX)
        self.field(0,1); self.field(12,0xffffffff)
        self.field(0x18,1); self.field(0x1c,PIXELS); self.field(0x20,FILES[2])
        self.field(0x28,1)
        self.word(0x384fcbdc,0x38701000)
        self.word(0x38701000,DRIVERS[0]); self.word(0x38701084,0x38702000)
        self.word(0x38702000,DRIVERS[1]); self.word(0x38702084,0)
        for i, driver in enumerate(DRIVERS):
            self.word(driver+4,0x3806ab75)
            self.word(driver+12,0x38707000+i*0x100)
            self.word(0x38707000+i*0x100,6+i)
        self.word(0x384fcc4c,0x38706000); self.word(0x38706000,0x3870501c)
        self.word(0x387052a4,0x50000000); self.byte(0x387052d0,0)
        for address,value in [(0x384ef8a0,0x50000000),(0x384ef8a4,614400),
            (0x384ef898,0x01e0000d),(0x384ef89c,320),(0x384ef8a8,0x20000780),
            (0x384ef87c,0x383df2dc),(0x384ef854,0x383df474),
            (0x384fce20,18),(0x384fce54,12),(0x384fce58,0x3806a93d),
            (0x40081050,0x0e000000)]: self.word(address,value)
        self.byte(0x384fce30,13)
        for i, file in enumerate(FILES):
            inode = 0x3870a000+(i%2)*0x100
            self.word(file+0x10,inode); self.word(file+0x14,SUBS[i])
            self.word(inode+0x10,0x384b621c); self.word(inode+0x18,UPPERS[i%2])

    def call(self, name, *arguments):
        self.uc.reg_write(UC_ARM_REG_SP,0x389eff00)
        self.uc.reg_write(UC_ARM_REG_LR,STOP|1)
        for reg,value in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],arguments): self.uc.reg_write(reg,value)
        self.uc.emu_start(self.symbols[name]|1,STOP,count=10000000)
        assert self.uc.reg_read(UC_ARM_REG_PC) == STOP, name+' failed to return'
        assert not self.locks
        return self.uc.reg_read(UC_ARM_REG_R0)

    def gui(self):
        self.call('timer',0x384fce28)

    def release(self):
        for i,driver in enumerate(DRIVERS):
            self.touches[i] = {'state':0}
            self.call('touch',driver,0x389d0000)

    def worker_tick(self, gpio=0x0e000000, flags=()):
        self.word(0x40081050,gpio)
        self.native_ring.extend(flags)
        if flags: self.word(SUBS[2]+8,self.word(SUBS[2]+8)+32*len(flags))
        self.now += 20
        if self.worker_state is None:
            self.uc.reg_write(UC_ARM_REG_SP,0x389cff00)
            self.uc.reg_write(UC_ARM_REG_R0,CTX)
            self.uc.reg_write(UC_ARM_REG_LR,STOP|1)
            pc = self.symbols['worker']|1
        else:
            self.uc.context_restore(self.worker_state)
            pc = self.uc.reg_read(UC_ARM_REG_PC)|1
        self.uc.emu_start(pc,STOP,count=10000000)
        assert not self.locks
        self.worker_state = self.uc.context_save()


def main():
    checks = []
    m = Machine()
    m.gui(); assert m.field(0x2c) == 1
    assert m.word(DRIVERS[0]+4) == m.symbols['touch']
    assert m.word(DRIVERS[1]+4) == m.symbols['touch']
    checks.append('actual linked next+0x84 setup installs both input callbacks')
    m.release()
    m.gui(); m.gui(); m.gui()
    assert m.field(0x24) == 1 and m.frames[-1] == PIXELS
    checks.append('default custom transition requires release and native frame admission')
    m.touches[0] = {'state':1,'again':1}
    m.call('touch',DRIVERS[0],0x389d0000)
    data = bytes(m.uc.mem_read(0x389d0000,20))
    assert data[:18] == bytes([0x5a])*18 and data[18] == 0 and data[19] == 1
    checks.append('custom input suppresses only state byte18; continues draining byte19')
    before = len(m.frames)
    m.word(0x389d0100+24,0)
    m.call('pan',0x384ef84c,0x389d0100)
    m.call('area',0x384ef84c,0x389d0100)
    assert len(m.frames) == before and not m.area_calls
    checks.append('both stock frame submission routes suppressed in custom mode')
    m.release(); m.field(0x28,0); m.field(0x38,2)
    m.word(SUBS[2]+8,32); m.gui()
    assert m.field(0x24) == 1
    m.word(SUBS[2]+0xc,32)
    m.word(SUBS[1]+8,32); m.gui()
    assert m.field(0x24) == 1
    m.word(SUBS[1]+0xc,32); m.word(0x384ef93c,1); m.gui()
    assert m.field(0x24) == 1
    m.word(0x384ef93c,0); m.gui()
    assert m.field(0x24) == 0 and m.frames[-1] == 0
    checks.append('owned/virtual queued touch and queued old frame prevent stock return')
    m.call('pan',0x384ef84c,0x389d0100); m.call('area',0x384ef84c,0x389d0100)
    assert m.frames[-1] == 0 and m.area_calls == 1
    m.word(0x389d0100+24,0xffffffff)
    before = len(m.frames)
    assert m.call('pan',0x384ef84c,0x389d0100) == 0xffffffff and len(m.frames) == before
    checks.append('stock submission restored; relocating framebuffer source rejected')
    m.word(0x384fce54,3); m.gui()
    assert m.word(0x384fce58) == 0x3806a93d
    checks.append('closing timer is not rearmed by broker')
    m = Machine(); m.worker_tick(); m.field(0x2c,1); m.field(0x24,1)
    for flags in [(1,),(2,),(2,),(4,)]: m.worker_tick(flags=flags)
    assert m.field(0x34) == 1
    m.worker_tick(flags=(1,4)); assert m.field(0x34) == 2
    m.field(0x24,0); m.field(0x28,0); m.worker_tick(flags=(1,4))
    assert m.field(0x34) == 2
    for _ in range(4): m.worker_tick()
    for _ in range(3):
        for _ in range(5): m.worker_tick(0x0c000000)
        for _ in range(5): m.worker_tick()
    assert m.field(0x28) == 1 and m.field(0x60) == 1
    checks.append('compiled worker counts one per press and triple GPIO release requests toggle')
    m = Machine(); result = m.call('broker_main',2,0x389d0200)
    assert result == 17 and m.original_calls == 1 and m.field(0x18) == 0
    checks.append('original main called once; wrapper returns original status and stops worker')
    result = {'passed':True,'elf_sha256':hashlib.sha256(ELF.read_bytes()).hexdigest(),
              'checks':checks,'limitations':'Native APIs, IRQs, locks and OS scheduling are mocked; no hardware accessed.'}
    destination = ROOT/'analysis/display-takeover/ui-broker-arm-offline-result.json'
    destination.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__': main()
