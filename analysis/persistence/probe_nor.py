from pathlib import Path
import sys,struct,json,hashlib,re
sys.path.insert(0,str(Path('analysis/wifi/python-packages').resolve()))
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB,CS_MODE_LITTLE_ENDIAN,CS_MODE_MCLASS
from capstone.arm import ARM_OP_MEM,ARM_OP_IMM,ARM_REG_PC
B=Path('backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
CS=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_LITTLE_ENDIAN|CS_MODE_MCLASS);CS.detail=True;CS.skipdata=True
SEGMENTS=[(0x1520b8,0x15608c,0x200001a8),(0x15608c,0x17fe78,0x200042c0),(0x17fe78,0x181ed8,0x200f5f00),(0x182924,0x19be20,0x34000000)]
def runtime(p):
 for a,z,d in SEGMENTS:
  if a<=p<z:return d+p-a
 return 0x0c000000+p
def off(addr):
 if 0x00200000<=addr<0x00300000:addr=addr+0x1fe00000
 for a,z,d in SEGMENTS:
  if d<=addr<d+z-a:return a+addr-d
 for base in (0x0c000000,0x2c000000,0x28000000):
  if base<=addr<base+len(B):return addr-base
 if 0<=addr<len(B):return addr
 return None
def dis(start,end,base=None):
 addr=runtime(start) if base is None else base
 for i in CS.disasm(B[start:end],addr):
  notes=[]
  for o in i.operands if i.id else []:
   if o.type==ARM_OP_MEM and o.mem.base==ARM_REG_PC:
    lit=((i.address+4)&~3)+o.mem.disp; p=off(lit)
    if p is not None and p+4<=len(B):
     v=struct.unpack_from('<I',B,p)[0];notes.append(f'pool {lit:#x}={v:#x}')
     q=off(v)
     if q is not None:
      m=re.match(rb'[ -~]{4,100}\0',B[q:q+101])
      if m and any(k in m.group().lower() for k in (b'norflash',b'flash',b'error',b'id <')):notes.append(m.group()[:-1].decode())
  print(f'{i.address:08x} {i.bytes.hex():10} {i.mnemonic:9} {i.op_str}'+(' ; '+'; '.join(notes) if notes else ''))
if __name__=='__main__':
 a=int(sys.argv[1],0);z=int(sys.argv[2],0);base=int(sys.argv[3],0)if len(sys.argv)>3 else None
 dis(a,z,base)
