"""Actual ARM ELF model for the image drawer; all native APIs are mocked.

No hardware access and no historical result writer invocation. This model checks
protocol, owned pixel-buffer boundaries and GUI publication, not LCD timing,
real socket RPC latency, SMP/IRQ behavior, heap availability or cold boot.
"""
from pathlib import Path
import array
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis/display-takeover'))
import test_native_drawer_smooth_arm as smooth
from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
    UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
    UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,
    UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC)

ELF = ROOT/'analysis/image-push/native-image-drawer.elf'
smooth.original.old.ELF = ELF
CTX, PIXELS, DRIVERS, UPPERS, SUBS, PLANE = (smooth.CTX,smooth.PIXELS,
    smooth.DRIVERS,smooth.UPPERS,smooth.SUBS,smooth.PLANE)
STOP = smooth.original.old.STOP
IMAGE = PIXELS+1228800
RECEIVE = IMAGE+307200
F = dict(smooth.original.F, image=176,receive=180,image_pending=184,
         generation=188,displayed_generation=192,server_state=196,
         server_error=200,reserved=204,ipv4=208)
FROM,PENDING,PHASE = 164,168,172
ERROR = 0x38bf0000


def fnv(data):
    value=2166136261
    for byte in data: value=((value^byte)*16777619)&0xffffffff
    return value


def frame(value):
    return struct.pack('<H',value)*153600


def rgb(value):
    r=(value>>11)&31;g=(value>>5)&63;b=value&31
    return 0xff000000|((r<<3)|(r>>2))<<16|((g<<2)|(g>>4))<<8|(b<<3)|(b>>2)


class Machine(smooth.Machine):
    def __init__(self,**options):
        self.receives=[];self.sends=[];self.accepts=[]
        self.sent=bytearray();self.closed=[];self.io=[]
        self.socket_result=11;self.bind_result=0;self.listen_result=0
        self.ip_result=0;self.ip_value=0x070200c0
        self.printf_result=None;self.printf_calls=0
        self.sleep_calls=0;self.worker_saved=None;self.return_on_empty=True
        self.read_delay=0;self.allocation_sizes=[]
        super().__init__(**options)

    def f(self,name,value=None): return self.field(F[name],value)

    def hook(self,address,method):
        if address==0x383d9420:
            def allocate():
                self.allocation_sizes.append(self.uc.reg_read(UC_ARM_REG_R0));method()
            return super().hook(address,allocate)
        if address==0x38042130:
            def sleep():
                assert not self.locks,'worker sleeps with a lock'
                pointer=self.uc.reg_read(UC_ARM_REG_R0)
                assert pointer%8==0
                assert bytes(self.uc.mem_read(pointer,16))==struct.pack('<qii',0,20000000,0)
                self.sleep_calls+=1;self.now+=20;self.ret();self.uc.emu_stop()
            return super().hook(address,sleep)
        return super().hook(address,method)

    def _graph(self):
        super()._graph()
        self.uc.mem_write(CTX+176,bytes(36))
        self.f('image',IMAGE);self.f('receive',RECEIVE)
        self.uc.mem_write(IMAGE,frame(0xf800));self.uc.mem_write(RECEIVE,frame(0x001f))

    def _install_hooks(self):
        super()._install_hooks()
        r=lambda reg:self.uc.reg_read(reg)
        def check(kind):
            assert not self.locks,'socket/native formatting operation while broker locked'
            self.io.append(kind)
        def socket():
            check('socket');assert (r(UC_ARM_REG_R0),r(UC_ARM_REG_R1),r(UC_ARM_REG_R2))==(2,0x801,0)
            self.ret(self.socket_result)
        def bind():
            check('bind');assert r(UC_ARM_REG_R0)==11 and r(UC_ARM_REG_R2)==16
            assert bytes(self.uc.mem_read(r(UC_ARM_REG_R1),16))==struct.pack('<HHI8s',2,0xa646,0,bytes(8))
            self.ret(self.bind_result)
        def listen():
            check('listen');assert (r(UC_ARM_REG_R0),r(UC_ARM_REG_R1))==(11,1);self.ret(self.listen_result)
        def accept():
            check('accept');assert (r(UC_ARM_REG_R0),r(UC_ARM_REG_R1),r(UC_ARM_REG_R2))==(11,0,0)
            if self.accepts:self.ret(self.accepts.pop(0))
            else:
                if self.return_on_empty:self.f('alive',0)
                self.word(ERROR,11);self.ret(-1)
        def receive():
            check('recv');assert r(UC_ARM_REG_R3)==0x40
            sp=r(UC_ARM_REG_SP);assert self.word(sp)==0 and self.word(sp+4)==0
            self.now+=self.read_delay
            event=self.receives.pop(0) if self.receives else ('error',11)
            if isinstance(event,tuple):self.word(ERROR,event[1]);self.ret(-1);return
            if isinstance(event,int):self.ret(event);return
            maximum=r(UC_ARM_REG_R2);part=event[:maximum]
            if len(event)>maximum:self.receives.insert(0,event[maximum:])
            self.uc.mem_write(r(UC_ARM_REG_R1),part);self.ret(len(part))
        def send():
            check('send');assert r(UC_ARM_REG_R3)==0x40
            maximum=r(UC_ARM_REG_R2);event=self.sends.pop(0) if self.sends else maximum
            if isinstance(event,tuple):self.word(ERROR,event[1]);self.ret(-1);return
            n=min(event,maximum)
            if n>0:self.sent+=bytes(self.uc.mem_read(r(UC_ARM_REG_R1),n))
            self.ret(n)
        def close():check('close');self.closed.append(r(UC_ARM_REG_R0));self.ret()
        def ioctl():
            check('ioctl');assert r(UC_ARM_REG_R0)==11 and r(UC_ARM_REG_R1)==0x701
            request=r(UC_ARM_REG_R2);assert request%4==0
            data=bytes(self.uc.mem_read(request,40))
            assert data[:6]==b'wlan0\x00' and data[6:]==bytes(34)
            if not self.ip_result:
                self.word(request+20,2);self.word(request+24,self.ip_value)
            self.ret(self.ip_result)
        def printf():
            self.printf_calls+=1
            assert r(UC_ARM_REG_R1)==24
            pointer=r(UC_ARM_REG_R2);text=bytearray()
            while self.byte(pointer):text.append(self.byte(pointer));pointer+=1
            assert bytes(text)==b'%u.%u.%u.%u:18086'
            sp=r(UC_ARM_REG_SP)
            ip=[r(UC_ARM_REG_R3),self.word(sp),self.word(sp+4),self.word(sp+8)]
            output=('.'.join(map(str,ip))+':18086').encode()
            self.uc.mem_write(r(UC_ARM_REG_R0),output+b'\0')
            self.ret(len(output) if self.printf_result is None else self.printf_result)
        for address,method in [(0x3802b528,socket),(0x381792ec,bind),(0x381794fc,listen),
            (0x38394354,accept),(0x38179784,receive),(0x381798a0,send),
            (0x38025de0,close),(0x38025c40,ioctl),(0x3801a418,printf)]:self.hook(address,method)
        self.hook(0x38018c5c,lambda:self.ret(ERROR))

    def worker(self):
        if self.worker_saved is None:
            self.uc.reg_write(UC_ARM_REG_SP,0x389cff00);self.uc.reg_write(UC_ARM_REG_LR,STOP|1)
            self.uc.reg_write(UC_ARM_REG_R0,CTX);pc=self.symbols['bootstrap']|1
        else:
            self.uc.context_restore(self.worker_saved);pc=self.uc.reg_read(UC_ARM_REG_PC)|1
        self.uc.emu_start(pc,STOP,count=30000000)
        assert not self.locks
        self.worker_saved=self.uc.context_save()
        return self.uc.reg_read(UC_ARM_REG_PC)==STOP

    def transact(self,data,send_events=()):
        self.return_on_empty=False
        self.accepts=[12];self.receives=list(data);self.sends=list(send_events)
        for _ in range(2000):
            finished=self.worker()
            if 12 in self.closed:return
            assert not finished
        raise AssertionError('transaction did not complete')

    def call5(self,name,*args):
        self.uc.reg_write(UC_ARM_REG_SP,0x389eff00);self.uc.reg_write(UC_ARM_REG_LR,STOP|1)
        for reg,value in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):self.uc.reg_write(reg,value)
        if len(args)>4:self.word(0x389eff00,args[4])
        self.uc.emu_start(self.symbols[name]|1,STOP,count=30000000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==STOP and not self.locks
        return self.uc.reg_read(UC_ARM_REG_R0)

    def custom(self):
        super().custom();self.f('generation',1)
        return self


def layout_checks():
    with ELF.open('rb') as stream:
        elf=ELFFile(stream)
        sections={s.name:s for s in elf.iter_sections() if s['sh_flags']&2 and s['sh_size']}
        assert set(sections)=={'.prefix','.start','.broker','.feedback'}
        assert not any(s['sh_flags']&1 for s in sections.values())
        for name,start,end in [('.prefix',0x3804b108,0x3804b2f4),('.start',0x3804b2f4,0x3804b2f8),
                                ('.broker',0x3804b2f8,0x3804be70),('.feedback',0x3807a764,0x3807a920)]:
            s=sections[name];assert s['sh_addr']==start and start+s['sh_size']<=end
        assert sections['.start']['sh_size']==4
        symbol={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        assert symbol['broker_start']==0x3804b2f5 and symbol['pause20']%8==0
        for name in ['digits','pause20','glyph','compose','clock_value','bootstrap']:
            address=symbol[name]&~1
            assert any(s['sh_addr']<=address<s['sh_addr']+s['sh_size'] for s in sections.values())
        image=bytearray(max(sections[n]['sh_addr']+sections[n]['sh_size'] for n in ['.prefix','.start','.broker'])-0x3804b108)
        for n in ['.prefix','.start','.broker']:
            s=sections[n];offset=s['sh_addr']-0x3804b108;image[offset:offset+s['sh_size']]=s.data()
        assert bytes(image)==ELF.with_suffix('.bin').read_bytes()
        assert sections['.feedback'].data()==ELF.with_name('native-image-drawer-feedback.bin').read_bytes()
        assert not any(s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size'] for s in elf.iter_sections())
    return ['Exactly four read-only ALLOC sections remain in approved main/aux containers; no LTO orphans/relocations/RW storage',
            'Both output BINs reconstructed exactly from ELF including entry/padding; digit/time literals are mapped and timespec8-aligned']


def rendering_checks():
    checks=[]
    payload=array.array('H',((i*37) & 65535 for i in range(153600))).tobytes()
    snapshot=array.array('I',(0xff000000|(i*123)&0xffffff for i in range(153600))).tobytes()
    m=Machine();m.f('generation',1);m.uc.mem_write(IMAGE,payload);m.uc.mem_write(PIXELS+614400,snapshot)
    guard=bytes([0xa7])*128;m.uc.mem_write(PIXELS-128,guard)
    source=array.array('H');source.frombytes(payload);background=array.array('I');background.frombytes(snapshot)
    for cover in range(321):
        m.f('cover',cover);m.call('compose',CTX)
        expected=array.array('I',(rgb(source[i+(320-cover)*480]) if i<cover*480 else background[i] for i in range(153600)))
        assert bytes(m.uc.mem_read(PIXELS,614400))==expected.tobytes(),cover
        assert bytes(m.uc.mem_read(PIXELS-128,128))==guard
        assert bytes(m.uc.mem_read(IMAGE,307200))==payload
        assert bytes(m.uc.mem_read(PIXELS+614400,614400))==snapshot
    checks.append('Actual RGB565 compose exactly matches independent channel expansion/cropped-image plus stock-background oracle at all321 cover positions')
    m.f('generation',0);m.f('cover',320)
    reads=[]
    hook=m.uc.hook_add(UC_HOOK_MEM_READ,lambda uc,kind,address,size,value,_:reads.append(address),begin=IMAGE,end=IMAGE+307199)
    m.call('compose',CTX);m.uc.hook_del(hook);assert not reads
    assert bytes(m.uc.mem_read(PIXELS,614400))==struct.pack('<I',0xff101010)*153600
    checks.append('Default page is solid opaque101010 and does not read uninitialized source pixels')
    # Independent bitmap rows, not copied from the ELF table.
    glyph_rows=['111101101101111','010010010010010','111001111100111',
                '111001111001111','101101111001001','111100111001111',
                '111100111101111','111001001001001','111101111101111',
                '111101111001111','000000000000010','000010000010000']
    # Table uses bit0 as left; row strings above are little-bit-order.
    regs=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,
          UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
    sentinels=[0xabcdef00+i for i in range(8)]
    bad_sp=[];m.uc.hook_add(UC_HOOK_CODE,lambda uc,pc,size,_:bad_sp.append(pc) if uc.reg_read(UC_ARM_REG_SP)%8 else None)
    zero=bytes(614400)
    for glyph in range(12):
        for cover in (0,155,156,157,160,169,170,171,319,320):
            m.uc.mem_write(PIXELS,zero);m.f('cover',cover)
            for reg,v in zip(regs,sentinels):m.uc.reg_write(reg,v)
            m.call('glyph',CTX,114,glyph)
            expected=bytearray(zero)
            for bit,enabled in enumerate(glyph_rows[glyph]):
                if enabled!='1':continue
                for dy in range(3):
                    y=150+(bit//3)*3+cover-320+dy
                    if not 0<=y<320:continue
                    for dx in range(3):
                        x=114+(bit%3)*3+dx;struct.pack_into('<I',expected,(y*480+x)*4,0xffffffff)
            assert bytes(m.uc.mem_read(PIXELS,614400))==bytes(expected),(glyph,cover)
            assert [m.uc.reg_read(r) for r in regs]==sentinels
            assert m.uc.reg_read(UC_ARM_REG_SP)==0x389eff00
    assert not bad_sp
    checks.append('Private IP glyph ARM kernel clips each output row, preservesr4-r11/SP and8-byte stack alignment; independent all12 glyph pixels matched')
    return checks


def protocol_checks():
    checks=[];data=frame(0x07e0);header=struct.pack('<4sHHII',b'VIMG',480,320,len(data),fnv(data))
    m=Machine().ready().custom();m.transact([header[:3],('error',11),header[3:9],('error',4),header[9:],data[:127],data[127:]],
                                         [2,('error',11),1,('error',4),5])
    assert bytes(m.sent)==struct.pack('<4sI',b'VACK',0) and m.f('image_pending')==1
    assert m.f('image')==IMAGE and bytes(m.uc.mem_read(IMAGE,307200))==frame(0xf800)
    assert bytes(m.uc.mem_read(RECEIVE,307200))==data
    assert m.f('clock_ms')<m.now and m.f('ipv4')==0x070200c0
    assert 12 in m.closed and not m.locks
    checks.append('Fragmented header/payload and partial ACK surviveEAGAIN/EINTR withnonblockingflags; worker I/O occurs outside broker lock and old image remains unchanged untilGUI admission')
    m.tick(ms=0);assert m.f('image')==RECEIVE and m.f('receive')==IMAGE and not m.f('image_pending')
    assert m.f('generation')==2 and m.f('displayed_generation')==2
    assert bytes(m.uc.mem_read(PIXELS,614400))==struct.pack('<I',rgb(0x07e0))*153600
    checks.append('Completed validated image is atomically swapped by settled customGUI and copied into existingRGB32 source; displayedgeneration advances only after acceptedPAN')
    for invalid in [b'NOPE'+header[4:],struct.pack('<4sHHII',b'VIMG',481,320,307200,0),
                    struct.pack('<4sHHII',b'VIMG',480,320,0xffffffff,0)]:
        m=Machine().ready().custom();m.transact([invalid]);assert not m.f('image_pending')
        assert bytes(m.sent)==struct.pack('<4sI',b'VACK',1)
        assert bytes(m.uc.mem_read(IMAGE,307200))==frame(0xf800)
    checks.append('Wrong magic/dimensions/oversized length rejected before pixel receive, old active image and pending state preserved')
    m=Machine().ready().custom();m.transact([header,frame(0x001f)])
    assert not m.f('image_pending') and bytes(m.sent)==struct.pack('<4sI',b'VACK',2)
    checks.append('Checksum mismatch never publishes the receive slot or replaces the visible image')
    for events in [[header,data[:50],0],[header,data[:50],('error',5)], [header[:4],0]]:
        m=Machine().ready().custom();m.transact(events);assert not m.f('image_pending')
        assert bytes(m.uc.mem_read(IMAGE,307200))==frame(0xf800)
    checks.append('Truncated header/body, EOF and terminal receive errors preserve old image and close connection')
    m=Machine().ready().custom();m.transact([('error',11)]*400)
    assert not m.f('image_pending') and m.now>=6000 and m.now<6100
    checks.append('Five-second no-progress receive timeout is measured by privateCLOCK and bounds stalled header')
    m=Machine().ready().custom();m.read_delay=1000;m.transact([header]+[data[i:i+1] for i in range(40)])
    assert not m.f('image_pending') and m.now>=31000 and m.now<35000
    checks.append('Thirty-second connection-wide deadline rejects a trickle payload even with continuous one-byte progress')
    m=Machine().ready().custom();m.now=0xfffffff0;m.transact([header,data]);assert m.f('image_pending')==1
    checks.append('Connection deadline comparison toleratesUINT32 monotonic-clock wrap')
    m=Machine().ready().custom();m.clock_result=-1;m.transact([header,data]);assert not m.f('image_pending')
    checks.append('Failed workerCLOCK rejects upload rather than weakening deadline or modifying GUIclock')
    for sending in [[0],[('error',5)],[('error',11)]*400]:
        m=Machine().ready().custom();m.transact([header,data],sending)
        assert m.f('image_pending')==1 and 12 in m.closed
        assert len(m.sent)<8
    checks.append('Failed/closed/stalledACK send remains bounded and keeps already validated staged image; ACK cannot promise physical display')
    m=Machine().ready();m.return_on_empty=False
    m.worker();assert m.f('server_error')==0 and m.f('server_state')==1
    checks.append('Ordinary nonblocking acceptEAGAIN is healthy idle state, not recorded as server failure; query uses exact40B ifreq')
    for setting,value,error in [('socket_result',-1,1),('bind_result',-1,2),('listen_result',-1,2)]:
        m=Machine().ready();setattr(m,setting,value);assert m.worker();assert m.f('server_error')==error
        assert m.closed==([] if setting=='socket_result' else [11])
    checks.append('Socket/bind/listen failures leaveGUI usable and close only established network descriptors')
    m=Machine().ready().custom();m.accepts=[12];m.receives=[header,data[:50],('error',11)]
    m.worker();assert not m.f('image_pending') and bytes(m.uc.mem_read(IMAGE,307200))==frame(0xf800)
    m.tick(ms=0);assert m.f('image')==IMAGE and m.f('generation')==1
    m.receives=[data[50:]]
    while 12 not in m.closed:m.worker()
    assert m.f('image_pending')==1;m.tick(ms=0)
    checks.append('GUI continues with old active image while a payload is incomplete; worker resumes into the same receive slot and only complete validation stages replacement')
    second=frame(0x001f);second_header=struct.pack('<4sHHII',b'VIMG',480,320,307200,fnv(second))
    m.closed=[];m.sent.clear();m.transact([second_header,second]);assert m.f('image')==RECEIVE
    assert bytes(m.uc.mem_read(RECEIVE,307200))==data
    m.tick(ms=0);assert m.f('image')==IMAGE and m.f('generation')==3 and m.f('displayed_generation')==3
    assert bytes(m.uc.mem_read(PIXELS,614400))==struct.pack('<I',rgb(0x001f))*153600
    checks.append('Two consecutive complete uploads reuse only the GUI-returned spare slot and advance activation/display generations without overwriting active source')
    m=Machine().ready().custom();m.transact([header,data[:50],0]);m.closed=[];m.sent.clear()
    m.transact([header,data]);m.tick(ms=0)
    assert m.f('displayed_generation')==2 and bytes(m.sent)==struct.pack('<4sI',b'VACK',0)
    checks.append('A complete upload following a truncated failed upload validates its entire new body and replaces the old frame successfully')
    m=Machine().ready().custom();m.transact([header,data]);m.accepts=[13]
    for _ in range(3):m.worker()
    assert m.accepts==[13] and m.f('image_pending')==1
    checks.append('Pending completed image prevents furtheraccept/receive until GUI returns an unused slot; queued clients cannot overwrite pending source')
    return checks


def publication_checks():
    checks=[]
    for field in ['overlay','gesture','queue']:
        m=Machine().ready().custom();m.f('image_pending',1)
        if field=='overlay':m.f('overlay',1);m.field(PHASE,150)
        elif field=='gesture':m.contact(m.physical_index,True,y=100)
        else:m.word(0x384ef93c,1)
        m.tick(ms=0);assert m.f('image')==IMAGE and m.f('image_pending')==1,field
    checks.append('Image pointer swap is deferred while frame queue busy, gesture active or drawer overlay transitioning')
    m=Machine().ready();m.f('image_pending',1);m.tick(ms=0)
    assert m.f('image')==RECEIVE and m.f('generation')==1 and not m.f('displayed_generation')
    m.f('wanted',1);m.settle();assert m.f('displayed_generation')==1 and m.f('mode')==1
    checks.append('Image may activate between animations while stock mode remains intact, but displaygeneration advances only when custom pixels actually submitted')
    m=Machine().ready().custom();m.f('image_pending',1);m.pan_result=-1;m.tick(ms=0)
    assert not m.f('image_pending') and m.f('dirty')==1 and not m.f('displayed_generation')
    m.pan_result=0;m.tick(ms=0);assert m.f('displayed_generation')==2 and not m.f('dirty')
    checks.append('Failed image redrawPAN retainsdirty and old displayedgeneration, later successful submission completes redraw')
    m=Machine().ready();m.f('wanted',1);m.start();m.field(PHASE,150);m.f('cover',320);m.f('dirty',1)
    before=len(m.frames);m.tick(ms=0)
    assert len(m.frames)==before+1 and m.f('overlay')==1 and not m.f('dirty')
    m.tick(ms=0);assert m.f('mode')==1 and not m.f('overlay')
    checks.append('Dirty IP/default redraw at phase150 is submitted before final owner handoff, never cleared unseen')
    m=Machine().ready().custom();m.f('generation',0);m.f('ipv4',0x01010101);m.f('dirty',1);m.printf_result=-1;m.tick(ms=0)
    assert bytes(m.uc.mem_read(PIXELS,614400))==struct.pack('<I',0xff101010)*153600
    m.f('dirty',1);m.printf_result=24;m.tick(ms=0)
    assert bytes(m.uc.mem_read(PIXELS,614400))==struct.pack('<I',0xff101010)*153600
    checks.append('Negative/truncated snprintf results are rejected before glyph reads; default pixels stay bounded')
    for allocations,create,frees in [([CTX,PIXELS],0,[]),([0],0,[]),([CTX,0],0,[CTX]),([CTX,PIXELS],-1,[PIXELS,CTX])]:
        m=Machine();m.allocations=list(allocations);m.create_result=create
        assert m.call('broker_main',2,0x389d0200)==17 and m.original_calls==1 and m.freed==frees
        assert m.allocation_sizes==([212,1843200] if len(allocations)>1 else [212])
    checks.append('Context212B andsingle1,843,200B allocation own all four buffers; allocation/create failures unwind and call untouched original main once')
    return checks


def gesture_checks():
    checks=[]
    for physical in (0,1):
        m=Machine(physical=physical).ready().custom();m.contact(physical,True);m.contact(physical,False)
        assert m.f('count')==0 and not m.f('overlay')
        m.contact(physical,True,y=300);m.contact(physical,True,y=200);m.contact(physical,False)
        m.settle();assert m.f('mode')==0
        m.contact(physical,True,y=0);m.contact(physical,True,y=120);m.contact(physical,False)
        m.settle();assert m.f('mode')==1
    checks.append('Both physical-input orderings retain upwarddismiss/top-edgeopen while ordinary taps remain no-op')
    for custom in (False,True):
        m=Machine().ready().start(custom=custom)
        before=m.f('cover')
        for phase in (30,60,90,120,150):
            m.tick(ms=300);assert m.field(PHASE)==phase
            assert m.f('cover')<=before if custom else m.f('cover')>=before
            before=m.f('cover')
        m.tick(ms=0);assert m.f('mode')==int(not custom)
    checks.append('Original smooth capped30ms/phase150 animation works in both directions, starting from accepted origin')
    for pending in (0,1):
        m=Machine().ready().custom();m.f('wanted',0);m.word(SUBS[pending]+8,32)
        assert m.call('handoff',CTX)==0xffffffff and m.f('mode')==1
        m.word(SUBS[pending]+12,32);assert m.call('handoff',CTX)==0 and m.f('mode')==0
        assert ('lock',UPPERS[0]+4) in m.lock_history and ('lock',UPPERS[1]+4) in m.lock_history
    checks.append('Original two-publisher locked PAN/owner transaction retains both physical and virtual ring-empty guards')
    m=Machine().ready().custom();m.f('wanted',0);m.byte(0x384f50a1,1)
    assert m.call('handoff',CTX)==0xffffffff
    m.byte(0x384f50a1,0);m.word(0x384ef93c,1);assert m.call('handoff',CTX)==0xffffffff
    m.word(0x384ef93c,0);m.byte(CTX+156,1);assert m.call('handoff',CTX)==0xffffffff
    checks.append('Raw pressed state, gesture activity and display queue independently prevent owner handoff')
    m=Machine().ready();m.f('overlay',1);m.word(PLANE+24,0);before=len(m.frames)
    m.call('pan',0x384ef84c,PLANE);m.call('area',0x384ef84c,PLANE)
    assert len(m.frames)==before and m.area_calls==0
    m.f('overlay',0);m.call('pan',0x384ef84c,PLANE);m.call('area',0x384ef84c,PLANE)
    assert m.frames[-1]==0 and m.area_calls==1
    m.word(PLANE+24,0xffffffff);before=len(m.frames)
    assert m.call('pan',0x384ef84c,PLANE)==0xffffffff and len(m.frames)==before
    checks.append('Shared private submit preserves original stockPAN/AREA delegation, custom suppression and relocation-source rejection')
    m=Machine().ready().custom()
    for _ in range(3):
        for _ in range(5):m.tick(gpio=0x0c000000)
        for _ in range(5):m.tick(gpio=0x0e000000)
    m.settle();assert m.f('mode')==0
    for _ in range(3):
        for _ in range(5):m.tick(gpio=0x0c000000)
        for _ in range(5):m.tick(gpio=0x0e000000)
    m.settle();assert m.f('mode')==1
    checks.append('Third-key triple click still roundtrips both owners without restarting original framework')
    return checks


def main():
    checks=layout_checks()+rendering_checks()+protocol_checks()+publication_checks()+gesture_checks()
    result={'passed':True,'hardware_operation':False,'check_count':len(checks),'checks':checks,
        'source_sha256':hashlib.sha256(ELF.with_suffix('.c').read_bytes()).hexdigest(),
        'entry_sha256':hashlib.sha256(ELF.with_name('native-image-drawer-entry.S').read_bytes()).hexdigest(),
        'elf_sha256':hashlib.sha256(ELF.read_bytes()).hexdigest(),
        'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'main_bytes':len(ELF.with_suffix('.bin').read_bytes()),
        'aux_bytes':len(ELF.with_name('native-image-drawer-feedback.bin').read_bytes()),
        'runtime_context_bytes':212,'context_bytes':212,'owned_pixels_bytes':1843200,
        'main_sha256':hashlib.sha256(ELF.with_suffix('.bin').read_bytes()).hexdigest(),
        'feedback_bytes':len(ELF.with_name('native-image-drawer-feedback.bin').read_bytes()),
        'feedback_sha256':hashlib.sha256(ELF.with_name('native-image-drawer-feedback.bin').read_bytes()).hexdigest(),
        'limitations':'Actual ARM instructions run, but all native functions, socketRPCs, display scanout, locks, IRQs and scheduling are mocked. No proof of heap availability, physical cadence, network reachability or cold boot.'}
    (ROOT/'analysis/image-push/image-drawer-arm-offline-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
