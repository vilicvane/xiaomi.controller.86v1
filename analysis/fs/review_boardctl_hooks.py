"""Offline review of boardctl command dispatch, pointers and copy sizes only."""
from pathlib import Path
import sys,struct,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis/wifi/python-packages'))
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
d=(ROOT/'backups/mi-panel-flash-16m-20261003.bin').read_bytes()
md=Cs(CS_ARCH_ARM,CS_MODE_THUMB);md.detail=True
out={'flash_sha256':hashlib.sha256(d).hexdigest(),'instruction_addresses':'NOR backup file offsets; mapped MCU PC adds 0x2c000000 or 0x0c000000 alias','default_hook_table':[],'functions':{}}
def flash_offset(ptr):
 for base in (0x0c000000,0x2c000000):
  if base<=ptr<base+len(d):return ptr-base
 return None
for i in range(16):
 val=struct.unpack_from('<I',d,0x5fbb68+i*4)[0]
 function_offset=flash_offset(val&~1) if val&1 else None
 out['default_hook_table'].append({'relative_offset':hex(i*4),'pointer':hex(val),'thumb_function_file_offset':hex(function_offset) if function_offset is not None else None})
for name,start,end in [('psk_hook',0x24e760,0x24e794),('boardctl',0x1adae8,0x1adbf0),('misc_getter',0x1bc8fc,0x1bc960),('misc_initializer',0x1bc6f8,0x1bc8b0)]:
 insns=[]
 for insn in md.disasm(d[start:end],start):
  row={'offset':hex(insn.address),'mnemonic':insn.mnemonic,'operands':insn.op_str}
  if insn.mnemonic.startswith('ldr') and len(insn.operands)>1:
   op=insn.operands[1]
   if op.type==3 and md.reg_name(op.mem.base)=='pc':
    pool=((insn.address+4)&~3)+op.mem.disp
    val=struct.unpack_from('<I',d,pool)[0]
    row['literal_pool_offset']=hex(pool);row['literal_numeric_value']=hex(val)
  insns.append(row)
 out['functions'][name]=insns
ram=(ROOT/'backups/mi-panel-psram-first1m-20261003.bin').read_bytes()
allowed={'sn','mac_wifi','mac_bt','miio_did','miio_key','color_id','color_desc','misc','miio','device'}
records=[]
for i in range(7):
 addr=0x340007c0+i*0x2c;off=addr-0x34000000
 namespace,name=struct.unpack_from('<II',ram,off-8)
 names=[]
 for ptr in [namespace,name]:
  fo=flash_offset(ptr)
  s=d[fo:fo+60].split(b'\0',1)[0].decode('ascii',errors='replace') if fo is not None else ''
  names.append(s if s in allowed else '[unrecognized static label]')
 records.append({'record_index':i,'record_start':hex(addr-8),'buffer_address':hex(addr),'buffer_storage_capacity':32,'first_static_label_pointer':hex(namespace),'name_pointer':hex(name),'approved_static_labels':names,'record_read_length_field_address':hex(addr+32),'record_read_requested_length':struct.unpack_from('<I',ram,off+32)[0], 'value_published':False})
out['misc_record_layout_from_psram_snapshot']=records
(Path(__file__).parent/'boardctl-hook-review.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
for name in ['psk_hook','misc_getter']:
 print(name)
 for row in out['functions'][name]:print(json.dumps(row))
print('hook_table',json.dumps(out['default_hook_table'][:6]))
