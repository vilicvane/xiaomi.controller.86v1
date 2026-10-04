"""Offline metadata for a future live HAL capture. Does not capture hardware."""
from pathlib import Path
import json,hashlib,struct
from probe_nor import B,off
OUT=Path('analysis/persistence')
C=json.loads((OUT/'sram-call-closure-no-suspend.json').read_text())
controller_ids=list(struct.unpack_from('<II',B,off(0x20003948)))
assert controller_ids==[0x40148000,0x40140000]
globals=[
 (0x20003948,8,'controller base pointer table, raw verified id0=0x40148000/id1=0x40140000','read'),
 (0x20003cf1,4,'erase opcode table; exact 4K erase uses first opcode','read'),
 (0x20003d7c,34*4,'chip cfg pointer table; active index0x0f separately runtime-confirmed','read'),
 (0x20003f14,28,'active chip cfg856518: JEDEC/BP mask/total/mode/callback RAMX pointer','read'),
 (0x20004174,4,'live timer frequency calibration word, read by microsecond delays','read'),
 (0x2000417c,0x24,'id0 context; opened,total+0x18,page+0x1c','read'),
 (0x200041c4,8,'saved suspend/resume Flash address; written on suspended-operation return','read/write conditional'),
 (0x200041cc,8,'saved suspend/resume write-source pointer','read/write conditional'),
 (0x200041d4,8,'saved suspend/resume remaining length','read/write conditional'),
 (0x200041f6,2,'suspend state per flash id; id0 must start0; successful non-suspend operation returns to0','read/write'),
 (0x200041f8,24,'IRQ mask arrays; not dereferenced by WIP wait when suspend=0','conditional read'),
 (0x20004210,2,'pre-operation divider bytes per id','read'),
 (0x20004212,2,'normal read divider bytes per id','read'),
 (0x20004214,2,'alternate read divider bytes per id','read'),
 (0x20004216,2,'active chip cfg index bytes; id0=0x0f','read'),
 (0x20004218,2,'controller memory-read arbitration flag; suspend path only','conditional read'),
 (0x2000421c,8,'saved memory-read bus-lock per id; pre writes and post reads','read/write'),
 (0x20004224,8,'current driver read-mode bitmap per id','read'),
 (0x2000423a,2,'IRQ-mask selection flags; suspend path only','conditional read'),
]
records=[]
for a,size,label,access in globals:
 p=off(a)
 records.append({'address':hex(a),'size':size,'meaning':label,'access':access,
  'in_startup_initialized_segment':p is not None,
  'must_use_live_capture':a>=0x20004174,
  'nor_source_file_offset':hex(p) if p is not None else None})
closure=set()
for name in ('native_jedec','HAL_write','HAL_erase','HAL_set_protection','cache_invalidate'):
 closure.update(C['roots'][name]['closure'])
instructions=set()
literals={}
for f in closure:
 instructions.update(C['functions'][f]['instructions'])
 for item in C['functions'][f]['literal_targets']:
  literals[(item['pool'],item['value'])]=item
runtime_code_start=0x200001a8;runtime_code_end=0x2000417c
source=B[off(runtime_code_start):off(runtime_code_end-1)+1]
m={'offline_only':True,'not_a_flashing_program':True,
 'source_image_sha256':hashlib.sha256(B).hexdigest(),
 'capture_request':{'start':hex(runtime_code_start),'end_exclusive':'0x20004240','size':0x20004240-runtime_code_start,
  'reason':'contiguous code, literal pools, pointer tables, timer calibration, HAL context; preserve live values before transplant',
  'live_capture_performed_by_this_script':False},
 'code_and_rodata':{'start':hex(runtime_code_start),'end_exclusive':hex(runtime_code_end),'size':len(source),
  'startup_nor_source_start':hex(off(runtime_code_start)),'startup_nor_source_sha256':hashlib.sha256(source).hexdigest(),
  'do_not_replace_live_state_with_nor_initializers':['0x20004174 frequency calibration', '0x2000417c..0x20004240 context/BSS']},
 'instruction_closure':{'specialization':'HAL entry wrappers force suspend0; WIP nonzero-suspend branch0x20001d26 is excluded',
  'instruction_count':len(instructions),'min':hex(min(map(lambda x:int(x,16),instructions))),
  'max':hex(max(map(lambda x:int(x,16),instructions))),
  'secondary_sram_segment_functions_required':False,'psram_globals_required':False},
 'noncode_globals':records,
 'literal_references':list(literals.values()),
 'guard_relocation_required':[{'pool':hex(a),'original_pointer':hex(struct.unpack_from('<I',B,off(a))[0]),'replacement':'dedicated SRAM pointer to copied live canary value'} for a in (0x20001cfc,0x20001fec,0x20002a60)],
 'controller_mapping_correction':{'previous_wrong_assumption':'id0=40140000; public default naming was incorrectly treated as current image table order',
  'raw_table_file_offset':'0x155858','raw_table_RAM_address':'0x20003948','raw_mapping':[hex(v) for v in controller_ids],
  'first_step':'verify live SRAM table before any SPI peripheral access; pointer order is image-specific'},
 'hardware_dependencies':[{'node':hex(controller_ids[0])+' SPI logical id0','required':'live pointer table verified first, then initialized compatibly with captured mode/divider; no pending transaction or memory-read lock'},
  {'node':'0x40003004 timer counter','required':'advancing counter; captured calibration word matches current timer clock before Puya400/450us delays'},
  {'node':'A7/MCU','required':'both halted for injection; MCU privileged, IRQ masked for invocation; device watchdog pause budget verified'},
  {'node':'0x28000000 NOR mapping','required':'after pre/read/post, uncached known NOR page must match backup; direct JEDEC/status alone does not establish mapping timing/mode compatibility'}],
 'cold_recovery_not_yet_proved':['main header invalidation still reaches boot/recovery and debug-accessible state',
  'A7 can be halted without relying on broken main','boot/recovery SPI clock/controller mode is compatible or deliberately initialized',
  'transplant region/code/output/stack chosen and prior contents preserved','normal calls return with controller read-route and masks restored',
  'a real minimal write/erase/restore test is readback-correct across subsequent cold boot'],
 'abnormal_path_limit':'assert/stack-failure veneers lead to Flash; they are excluded only under validated args/context/guard integrity. This is not a general failure-safe independently initializing loader.'}
(OUT/'hal-transplant-manifest.json').write_text(json.dumps(m,indent=2))
print('capture region',m['capture_request']['size'],'bytes; normal instructions',len(instructions),'; no hardware I/O')
