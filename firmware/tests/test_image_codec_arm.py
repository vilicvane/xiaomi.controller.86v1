"""Actual1.50.10 codec instructions plus compiled project C; offline only.

Requires the private exact original NOR backup and private image fixtures.
Only allocator and getenv OS boundaries are substituted, not image decoding.
"""
from pathlib import Path
import hashlib, json, os, struct, sys, zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/python-ui-broker'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_BLOCK
from unicorn.arm_const import *
from elftools.elf.elffile import ELFFile

BASE, SOURCE, LENGTH = 0x38000000, 0x8e0004, 0x4f3fe0
INPUT, OUTPUT, HEAP, STACK, STOP = 0x38700000, 0x38820000, 0x38900000, 0x38ff0000, 0x38fff000
ELF = Path(os.environ.get('PANEL_CODEC_ELF', ROOT/'build/panel/panel.elf'))
FIXTURES = ROOT/'build/compression-research/direct-image-fixtures-20261008/fixtures'
JPEG_FIXTURES = ROOT/'build/compression-research/production-codec-20261008-01/fixtures'
GUARD = b'\xa7'*128
original = (ROOT/'backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
assert hashlib.sha256(original).hexdigest() == '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'

class Machine:
    def __init__(self, fail_allocation=0, persistent_failure=False):
        self.uc = Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A7)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2,0xf00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        self.uc.mem_map(BASE,0x1000000)
        self.uc.mem_write(BASE,original[SOURCE:SOURCE+LENGTH])
        with ELF.open('rb') as f:
            elf=ELFFile(f)
            # A full firmware ELF can have sparse LOAD segments spanning stock
            # text. Only actual allocated section bytes belong to this patch.
            self.project_segments=[]
            for section in elf.iter_sections():
                if section['sh_type']=='SHT_PROGBITS' and section['sh_flags']&2:
                    data=section.data();self.uc.mem_write(section['sh_addr'],data)
                    self.project_segments.append((section['sh_addr'],bytes(data)))
            symbols=elf.get_section_by_name('.symtab')
            self.entry=next(s['st_value'] for s in symbols.iter_symbols() if s.name=='panel_image_decode')
        self.stock_text=bytes(self.uc.mem_read(BASE,LENGTH))
        self.live={};self.next_heap=HEAP;self.peak=0;self.attempts=0;self.fail_allocation=fail_allocation;self.persistent_failure=persistent_failure
        self.minimum_sp=STACK;self.events=[]
        self.hook(STOP,lambda:self.uc.emu_stop())
        self.hook(0x383d9420,self.allocate);self.hook(0x383d93e4,self.release)
        self.hook(0x380051ec,lambda:self.ret(0))
        self.hook(0x38018c30,lambda:(_ for _ in ()).throw(AssertionError('stack protector')))
        for address in [0x3806b250,0x3838d87c,0x383da270,0x3823e8e4,0x3823ff48,0x380675c8]:
            self.hook(address,lambda address=address:(_ for _ in ()).throw(AssertionError('forbidden FILE/GUI boundary '+hex(address))))
        self.uc.hook_add(UC_HOOK_BLOCK,lambda uc,a,s,u:self.stack())
    def stack(self):
        sp=self.uc.reg_read(UC_ARM_REG_SP)
        if STACK-0x10000<sp<=STACK:self.minimum_sp=min(self.minimum_sp,sp)
    def hook(self,a,f):self.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,u:f(),begin=a,end=a)
    def ret(self,v):
        self.uc.reg_write(UC_ARM_REG_R0,v);self.uc.reg_write(UC_ARM_REG_PC,self.uc.reg_read(UC_ARM_REG_LR))
    def allocate(self):
        size=self.uc.reg_read(UC_ARM_REG_R0);assert 0<size<=2*1024*1024,size
        self.attempts+=1
        if self.fail_allocation and (self.attempts==self.fail_allocation or (self.persistent_failure and self.attempts>=self.fail_allocation)):
            self.events.append({'fail':size});self.ret(0);return
        p=self.next_heap+128;self.next_heap=p+((size+15)&~15)+128;assert self.next_heap<0x38f00000
        self.live[p]=size;self.peak=max(self.peak,sum(self.live.values()))
        self.uc.mem_write(p-128,GUARD);self.uc.mem_write(p,bytes(size));self.uc.mem_write(p+size,GUARD)
        self.events.append({'alloc':size});self.ret(p)
    def release(self):
        p=self.uc.reg_read(UC_ARM_REG_R0)
        if p:
            size=self.live.pop(p)
            assert self.uc.mem_read(p-128,128)==GUARD and self.uc.mem_read(p+size,128)==GUARD
            self.events.append({'free':size})
        self.ret(0)
    def run(self,encoded,expected_status,reference=None):
        self.uc.mem_write(INPUT-128,GUARD);self.uc.mem_write(INPUT,encoded);self.uc.mem_write(INPUT+len(encoded),GUARD)
        self.uc.mem_write(OUTPUT-128,GUARD);self.uc.mem_write(OUTPUT,b'\xcd'*307200);self.uc.mem_write(OUTPUT+307200,GUARD)
        for register,value in [(UC_ARM_REG_R0,INPUT),(UC_ARM_REG_R1,len(encoded)),(UC_ARM_REG_R2,OUTPUT),(UC_ARM_REG_SP,STACK),(UC_ARM_REG_LR,STOP|1)]:self.uc.reg_write(register,value)
        self.uc.emu_start(self.entry|1,0,timeout=60_000_000,count=100_000_000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==STOP,hex(self.uc.reg_read(UC_ARM_REG_PC))
        status=self.uc.reg_read(UC_ARM_REG_R0)
        allowed=expected_status if isinstance(expected_status,tuple) else (expected_status,)
        assert status in allowed,(status,expected_status,self.events)
        output=bytes(self.uc.mem_read(OUTPUT,307200))
        if reference is not None and status==0:assert output==reference,'pixel reference differs'
        assert not self.live,self.live
        assert self.uc.mem_read(OUTPUT-128,128)==GUARD and self.uc.mem_read(OUTPUT+307200,128)==GUARD
        assert self.uc.mem_read(INPUT-128,128)==GUARD and self.uc.mem_read(INPUT+len(encoded),128)==GUARD
        assert self.uc.mem_read(INPUT,len(encoded))==encoded
        assert bytes(self.uc.mem_read(BASE,LENGTH))==self.stock_text,'stock text changed'
        for address,data in self.project_segments:
            assert bytes(self.uc.mem_read(address,len(data)))==data,'codec text changed'
        return {'status':status,'output_sha256':hashlib.sha256(output).hexdigest(),'allocator_peak':self.peak,'allocation_attempts':self.attempts,'allocator_cleanup_bytes':0,'observed_stack_bytes':STACK-self.minimum_sp,'boundary_guards':True,'stock_and_project_text_unchanged':True,'events':self.events}

def png_parts(encoded):
    parts=[];position=8
    while position<len(encoded):
        length=struct.unpack_from('>I',encoded,position)[0]
        parts.append((encoded[position+4:position+8],encoded[position+8:position+8+length]))
        position+=12+length
    assert position==len(encoded)
    return parts

def png_bytes(parts):
    return b'\x89PNG\r\n\x1a\n'+b''.join(struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)) for kind,body in parts)

def security_cases():
    card=(FIXTURES/'card-rgb8.png').read_bytes()
    chunks=png_parts(card)
    compressed=b''.join(body for kind,body in chunks if kind==b'IDAT')
    before=[(kind,body) for kind,body in chunks if kind!=b'IDAT' and kind!=b'IEND']
    def idat(payload):return png_bytes(before+[(b'IDAT',payload),(b'IEND',b'')])
    raw=zlib.decompress(compressed)
    yield 'png-multi-idat',png_bytes(before+[(b'IDAT',compressed[:1]),(b'IDAT',compressed[1:7]),(b'IDAT',compressed[7:])]+[(b'IEND',b'')]),0
    yield 'png-empty-idat',png_bytes(before+[(b'IDAT',b''),(b'IDAT',compressed),(b'IEND',b'')]),0
    yield 'png-extra-deflate-input',idat(compressed+b'ignored'),422
    yield 'png-second-zlib-stream',idat(compressed+zlib.compress(b'other')),422
    yield 'png-under-row-count',idat(zlib.compress(raw[:-1441])),422
    yield 'png-over-row-count',idat(zlib.compress(raw+raw[-1441:])),422
    bad_adler=compressed[:-1]+bytes([compressed[-1]^1])
    yield 'png-bad-adler-correct-crc',idat(bad_adler),422
    bad_crc=bytearray(card);bad_crc[-1]^=1
    yield 'png-bad-iend-crc',bytes(bad_crc),422
    bad_crc=bytearray(card);bad_crc[29]^=1
    yield 'png-bad-ihdr-crc',bytes(bad_crc),422
    yield 'png-no-iend',card[:-12],422
    yield 'png-trailing-data',card+b'junk',422
    yield 'png-second-png',card+card,422
    yield 'png-truncated-chunk',card[:-20],422
    yield 'png-idat-oversize',card[:33]+struct.pack('>I',0xffffffff)+card[37:],422
    yield 'png-critical-unknown',png_bytes(before+[(b'ABCD',b''),(b'IDAT',compressed),(b'IEND',b'')]),415
    yield 'png-compressed-ancillary',png_bytes(before+[(b'zTXt',b'key\0\0'+zlib.compress(b'value')),(b'IDAT',compressed),(b'IEND',b'')]),415
    yield 'png-apng',png_bytes(before+[(b'acTL',struct.pack('>II',1,0)),(b'IDAT',compressed),(b'IEND',b'')]),415
    ihdr=bytearray(chunks[0][1]);ihdr[0:4]=struct.pack('>I',481)
    yield 'png-wrong-width',png_bytes([(b'IHDR',bytes(ihdr))]+chunks[1:]),422
    ihdr=bytearray(chunks[0][1]);ihdr[12]=1
    yield 'png-adam7',png_bytes([(b'IHDR',bytes(ihdr))]+chunks[1:]),415
    ihdr=bytearray(chunks[0][1]);ihdr[8]=16
    yield 'png-16bit',png_bytes([(b'IHDR',bytes(ihdr))]+chunks[1:]),415
    yield 'png-repeated-ihdr',png_bytes(chunks[:1]+chunks),422
    yield 'png-split-idat-by-metadata',png_bytes(before+[(b'IDAT',compressed[:7]),(b'pHYs',bytes(9)),(b'IDAT',compressed[7:]),(b'IEND',b'')]),415
    jpeg=(JPEG_FIXTURES/'card-444.jpg').read_bytes()
    yield 'jpeg-no-eoi',jpeg[:-2],422
    yield 'jpeg-trailing-data',jpeg+b'junk',422
    yield 'jpeg-second-jpeg',jpeg+jpeg,422
    yield 'jpeg-half-with-eoi',jpeg[:len(jpeg)//2]+b'\xff\xd9',422
    yield 'jpeg-empty-entropy',jpeg[:jpeg.index(b'\xff\xda')+14]+b'\xff\xd9',422
    yield 'jpeg-bad-marker-length',jpeg[:4]+b'\x00\x01'+jpeg[6:],422
    yield 'jpeg-progressive',(JPEG_FIXTURES/'progressive.jpg').read_bytes(),415
    yield 'jpeg-cmyk',(JPEG_FIXTURES/'cmyk.jpg').read_bytes(),415
    sof=jpeg.index(b'\xff\xc0')
    wrong=bytearray(jpeg);wrong[sof+7:sof+9]=struct.pack('>H',481)
    yield 'jpeg-wrong-width',bytes(wrong),422
    sos=jpeg.index(b'\xff\xda');length=struct.unpack_from('>H',jpeg,sos+2)[0]
    wrong=bytearray(jpeg);wrong[sos+2+length-2]=62
    yield 'jpeg-incomplete-scan',bytes(wrong),415
    wrong=bytearray(jpeg);wrong[sof+11]=0x31
    yield 'jpeg-unsupported-sampling',bytes(wrong),415
    yield 'unsupported-format',b'not an image',415
    yield 'truncated-png-signature',b'\x89PNG',415
    yield 'truncated-jpeg-soi',b'\xff\xd8',422

def main():
    results=[]
    successful=[]
    for name in ['card-original.png','card-rgb8.png','card-palette.png','card-rgba-alpha.png','card-gray8.png','photo-rgb8.png']:
        encoded=(FIXTURES/name).read_bytes();expected=(FIXTURES/(name+'.expected.rgb565')).read_bytes()
        result=Machine().run(encoded,0,expected);result['case']=name;results.append(result)
        successful.append((name,encoded,expected,result['allocation_attempts']))
        print(name,result['status'],result['allocator_peak'],result['observed_stack_bytes'])
    for folder,names in [(FIXTURES,['card-jpeg-q85.jpg','photo-jpeg-q85.jpg']),
                         (JPEG_FIXTURES,['card-444.jpg','card-422.jpg','card-420.jpg','photo-444.jpg','photo-422.jpg','photo-420.jpg','gray.jpg',
                                         'card-rgb-colorspace.jpg','gray-alpha.png','gray-trns.png','rgb-trns.png','palette-trns.png'])]:
        for name in names:
            encoded=(folder/name).read_bytes();expected=(folder/(name+'.expected.rgb565')).read_bytes()
            result=Machine().run(encoded,0,expected);result['case']=name;results.append(result)
            successful.append((name,encoded,expected,result['allocation_attempts']))
            print(name,result['status'],result['allocator_peak'],result['observed_stack_bytes'])
    for name,encoded,status in security_cases():
        result=Machine().run(encoded,status);result['case']=name;results.append(result)
        print(name,result['status'])
    for name,encoded,expected,attempts in successful:
        for failed in range(1,attempts+1):
            result=Machine(failed).run(encoded,(0,503),expected);result['case']=name+'-single-allocation-fault-'+str(failed);results.append(result)
            result=Machine(failed,True).run(encoded,503);result['case']=name+'-persistent-oom-'+str(failed);results.append(result)
        print(name,'single and persistent allocation faults',attempts*2,'cleanup0')
    path=os.environ.get('PANEL_CODEC_RESULT_PATH')
    if path:Path(path).write_text(json.dumps({'scope':'Offline actual ARM codec C and native libraries; malloc/free/getenv OS stubs only.',
                                            'elf_sha256':hashlib.sha256(ELF.read_bytes()).hexdigest(),
                                            'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                            'stock_sha256':hashlib.sha256(original).hexdigest(),'cases':results},indent=2))
    print('Passed',len(results),'actual ARM cases')
    return results

if __name__=='__main__':main()
