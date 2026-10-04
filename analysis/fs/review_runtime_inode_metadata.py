"""Review metadata using inode offsets established from this NOR binary."""
from pathlib import Path
import struct,json
ROOT=Path(__file__).resolve().parents[2]
p=(ROOT/'backups/mi-panel-psram-first1m-20261003.bin').read_bytes()
s=(ROOT/'backups/mi-panel-sram-20261003.bin').read_bytes()
def read(a,n):
 for base,b in ((0x34000000,p),(0x20000000,s)):
  if base<=a and a+n<=base+len(b):return b[a-base:a-base+n]
 return None
def u32(a):
 b=read(a,4);return struct.unpack('<I',b)[0] if b else None
groot=0x3401a65c;root=u32(groot)
out={'evidence_kind':'offline, non-atomic saved MCU SRAM and first 1MiB PSRAM snapshots',
 'inode_root_global':hex(groot),'inode_root_pointer':hex(root) if root is not None else None,
 'layout_confirmed_by_firmware_instructions':{'peer':4,'child':8,'references_i16':12,'flags_u16':14,'ops_pointer':16,'name_inline':28},
 'unavailable_node_addresses':[],'target_nodes':[]}
seen=set();pending=[(root,'')] if root else []
while pending and len(seen)<2000:
 addr,parent=pending.pop()
 if not addr or addr in seen:continue
 seen.add(addr);head=read(addr,28);name=read(addr+28,64)
 if head is None or name is None:
  out['unavailable_node_addresses'].append(hex(addr));continue
 name=name.split(b'\0',1)[0]
 if not name or any(c<32 or c>126 or c==47 for c in name):continue
 peer,child=struct.unpack_from('<II',head,4)
 flags=struct.unpack_from('<H',head,14)[0];ops=struct.unpack_from('<I',head,16)[0]
 label=name.decode('ascii');path=parent+'/'+label
 if path in ('/data','/data/etc','/data/etc/device.info','/dev','/dev/misc_etc'):
  out['target_nodes'].append({'path':path,'address':hex(addr),'inode_type_nibble':flags&15,'inode_flags':hex(flags),'ops_pointer':hex(ops),'name_address':hex(addr+28)})
 # Do not emit any other filenames or strings.
 if peer:pending.append((peer,parent))
 if child:pending.append((child,path))
out['nodes_examined']=len(seen)
out['errno_accessor_binary_evidence']={
 'open_negative_result_store_site':'0x2fbdfe',
 'errno_accessor':'0x1adaac',
 'current_tcb_global':'0x3401a650',
 'current_tcb_tls_pointer_offset':'0x44',
 'errno_offset_in_tls':'0x14',
 'limitation':'errno in an arbitrary later snapshot need not still belong to the device.info open failure'}
out['mount_read_only_state_confirmed']=False
(Path(__file__).parent/'runtime-inode-review.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
