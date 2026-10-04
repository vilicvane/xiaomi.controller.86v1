"""BOOT-specific read-only evidence. Does not import hardware/debug helpers."""
from pathlib import Path
import json,struct,hashlib
from audit_cold_recovery import B,offset,decode
OUT=Path('analysis/persistence')
def h(x):return hex(x)
def word(a):return struct.unpack_from('<I',B,offset(a,'boot'))[0]
controller_ids=[word(0x20003300),word(0x20003304)]
assert controller_ids==[0x40148000,0x40140000]
controller_correction={'previous_wrong_assumption':'logical id0=40140000; report labels were not raw-table verified',
 'corrected_mapping':{'id0':h(controller_ids[0]),'id1':h(controller_ids[1])},
 'proof':'BOOT source file5378..5380 / RAM20003300..3308 raw bytes='+B[offset(0x20003300,'boot'):offset(0x20003300,'boot')+8].hex()+'; HAL uses table[id]',
 'live_status':'root captured main matching table; BOOT live table must be revalidated before any peripheral access',
 'hardware_failure_limit':'inactive4014000c access stalled root AP; mapping correction is proved, stall causality not independently proved'}
functions=[
 ('get_size',0x20000f20,0x20000fa0,'r0=id,r1=total*,r2=block*,r3=sector*,[sp]=page*; valid id/opened required'),
 ('set_protection',0x20000fe8,0x20001038,'r0=id,r1=BP composite; pre/status callback type4/post; IRQ save/restore; r0=0 success,0x10 not-open,0x0a callback unavailable'),
 ('erase',0x20001104,0x2000110c,'r0=id,r1=address,r2=len; forces suspend0'),
 ('write',0x20001248,0x20001258,'r0=id,r1=address,r2=RAM source,r3=len; forces suspend0'),
 ('pre_operation',0x200018a8,0x200018b0,'r0=id; pre_ex with suspend0'),
 ('post_operation',0x200018f8,0x20001900,'r0=id; restores mode/divider/read-bus state'),
 ('read_register',0x20001900,0x2000193c,'r0=id,r1=opcode,r2=RAM output,r3=len; requires pre/post'),
 ('status_low',0x2000193c,0x20001974,'r0=id; returns command05 byte; guard SRAM20003a58'),
 ('wait_WIP',0x20001974,0x200019f0,'r0=id,r1=suspend; no bounded timeout; suspend0 excludes NVIC helpers'),
 ('status_high',0x20001c2c,0x20001c64,'r0=id; returns command35 byte; guard SRAM20003a58'),
 ('write_status_register',0x20001cb4,0x20001cf8,'r0=id,r1=volatile bool,r2=opcode,r3=RAM source,[sp]=len; not read-only'),
 ('native_JEDEC',0x20001cf8,0x20001d20,'r0=id,r1=RAM output,r2=len; pre/9f min3/post; return0'),
 ('set_BP_dispatch',0x20002394,0x200023bc,'r0=id,r1=BP; indirect cfg callback type4; ignores callback detailed result'),
 ('chip_status_callback',0x200024f4,0x20002658,'r0=id,r1=type0..4,r2=parameter; guard SRAM20003a58; activecfg RAMX pointer002024f5'),
 ('delay_us',0x20002d78,0x20002da8,'r0=us; uses timer40003004 and calibration20003adc /4'),
 ('cache_invalidate',0x20002fb4,0x20002ffc,'r0=cache0I/1D,r1=start,r2=len; line32; IRQ save/restore; len>=0x4000 clears whole cache'),
 ('timer_frequency',0x20003008,0x20003014,'r0=live word20003adc >>2'),
]
rows=[];dis=[]
closure=json.loads((OUT/'boot-sram-call-closure-no-suspend.json').read_text())
for name,a,z,abi in functions:
 p,q=offset(a,'boot'),offset(z-1,'boot')+1
 rows.append({'name':name,'address':h(a),'thumb_data_pointer':h(a|1),'thumb_RAMX_pointer':h((a-0x1fe00000)|1),
              'file_offset':h(p),'size':z-a,'sha256':hashlib.sha256(B[p:q]).hexdigest(),'abi':abi})
 dis.append({'function':name,'abi':abi,'instructions':decode(a,z-a,'boot')})
globals=[
 (0x20003300,8,'controller base pointer table; raw verified id0=40148000,id1=40140000','read'),
 (0x20003607,4,'erase opcodes; aligned4KiB uses first opcode20','read'),
 (0x20003694,34*4,'chip cfg pointer table','read'),
 (0x2000382c,28,'85-65-18 chip cfg; BPmask407c, callback002024f5','read'),
 (0x20003a58,4,'stack guard, inside boot SRAM initialized block; initialDEADBEEF','read'),
 (0x20003adc,4,'live timer frequency calibration; initial24000000; getter>>2','read'),
 (0x20003ae0,0x24,'id0 context; opened0,JEDEC1..3,total+18,page+1c','read'),
 (0x20003b28,8,'saved resume Flash address','conditional write on suspend'),
 (0x20003b30,8,'saved resume write buffer','conditional write on suspend'),
 (0x20003b38,8,'saved resume remaining length','conditional write on suspend'),
 (0x20003b5a,2,'suspend state, id0 must start0 and normal non-suspend return sets0','read/write'),
 (0x20003b5c,24,'interrupt masks; WIP suspend0 path does not dereference','conditional read'),
 (0x20003b74,2,'pre-operation divider per id','read'),
 (0x20003b76,2,'standard read divider per id','read'),
 (0x20003b78,2,'alternate read divider per id','read'),
 (0x20003b7a,2,'active chip table index; expect0f after actual856518 open','read'),
 (0x20003b7c,2,'memory-read suspend arbitration flag','conditional read'),
 (0x20003b80,8,'saved bus-lock per id; pre writes/post reads','read/write'),
 (0x20003b88,8,'selected read-mode bitmap per id','read'),
 (0x20003b9e,2,'IRQ mask selection flags, suspend path only','conditional read'),
]
data=[{'address':h(a),'size':size,'meaning':meaning,'access':access} for a,size,meaning,access in globals]
summary={'offline_only':True,'hardware_operations_performed':0,'source_image':'backups/mi-panel-flash-16m-1.50.10-20261004.bin',
 'source_sha256':hashlib.sha256(B).hexdigest(),'view':'boot only; do not use these addresses with main/recovery code',
 'functions':rows,'globals':data,'normal_closure':closure['roots'],
 'boot_owned_capture_region':{'start':'0x200001a8','end_exclusive':'0x20003c20','size':0x3c20-0x1a8,
  'initialized_code_rodata':'200001a8..20003ae0 from file2220..5b58',
  'mutable_BSS_context':'20003ae0..20003c20; must use post-init boot live state',
  'never_overwrite_running_main_and_resume_without_complete_original_restore':True},
 'guard':{'address':'0x20003a58','initial_value':h(word(0x20003a58)),
  'all_critical_guard_pools_point_into_this_boot_copy':True,'Flash_guard_redirect_required':False},
 'current_boot_chip_runtime_not_yet_captured_by_this_audit':{'index_node':'0x20003b7a','expected_index':'0x0f',
  'table_slot':'0x200036d0','expected_cfg':'0x2000382c','callback_node':'0x20003844','expected_callback':'0x002024f5'},
 'geometry':{'context':'0x20003ae0','total_node':'0x20003af8','page_node':'0x20003afc',
  'expected_total':'0x1000000','expected_page':'0x100','fixed_sector':'0x1000','fixed_block':'0x8000'},
 'read_only_sequence':['native_JEDEC(0,out,3)','pre(0)','read_reg(0,05,out+3,1)','read_reg(0,35,out+4,1)','post(0)','BKPT with IRQ still masked; host validates and restores core/software state'],
 'controller_mapping_correction':controller_correction,
 'controller_snapshot':{'base':h(controller_ids[0]),'logical_id':0,'table':'0x20003300','table_file_offset':'0x5378',
  'first_step':'read and validate live SRAM table before any peripheral register access',
  'safe_metadata_offsets':['0x04','0x0c','0x14','0x34','0x3c'],
  'entry_idle_checks':{'+0x0c bit0':'0','+0x34 bit0x100':'0'},
  'restore_expectation':'divider+14 and stable mode/lock values return; command/address+00 and transfer-length fields+04 can change',
  'do_not_bulk_read_FIFO_offsets':['0x08','0x10']},
 'software_restore':{'read_only_probe_writes':'id0 saved-bus-lock word20003b80 only, beyond output/scratch stack',
  'successful_non_suspend_write_erase_additional_software_write':'id0 suspend state byte20003b5a set0; pending/resume fields only on suspended result1',
  'protection_setter':'pre/post saved lock; IRQ save/restore; actual chip volatile status bits mutate, so capture and explicitly restore originalBP',
  'fixed_code_tables':'not changed by selected normal operations',
  'restore_paused_boot_core':'all GPRs,CONTROL,MSP,PSP,MSPLIM,PSPLIM,PRIMASK and debugger halt/breakpoint state must be retained',
  'scratch_stack_limit':'boot initializes MSP200d5e00 and MSPLIM200d3e00; dedicated MSP stack elsewhere must satisfy or deliberately preserve/adjust/restore limit; write/erase callee peak232 plus caller requires >=512-byte recommendation'},
 'status_restore':{'mask':'0x407c','formula':'(SR1 | (SR2<<8)) & 0x407c',
  'setter':'boot HAL20000fe8 forces type4 through active cfg; low01/high31 status writes use volatileWREN50',
  'verify':'read both05/35 again; compareBP and preserved QE/other stable bits; HAL return0 does not prove callback success'},
 'timer':{'counter':'0x40003004','calibration_word':'0x20003adc','initial_calibration':word(0x20003adc),
  'getter':'boot20003008 returns calibration>>2','delay':'boot20002d78, Puya erase/program400/450us',
  'precondition':'counter advances and live calibration matches cold timer clock; stock boot initialization must already have run'},
 'cache':{'invalidate_function':'0x20002fb4','id0I_controller':'0x27ffc000','id1D_controller':'0x27ffa000',
  'line_bytes':32,'normal_stack_bytes':8,'Flash_dependencies':False,
  'after_restore':'uncached28000000+offset readback first; invalidate changed Flash lines for I andD before continuing boot',
  'address_alias_reference':'current main wrapper uses cached data alias2c000000+offset for both cacheIDs; whole-cache len>=4000 is possible but may affect unrelated cached data ownership'},
 'cold_scope_limits':['requires deterministic stop after preserved boot initialized NOR and before main overwrites SRAM',
  'assert/stack-failure paths still call Flash; only validargs/context/guard normal closure proved',
  'watchdog/A7/IRQ and DMA ownership constraints still apply','noboot NOR erase/program/protection operation has been exercised by this audit',
  'this proves static independent boot driver availability, not completed cold write/restore validation']}
(OUT/'boot-nor-programming-review.json').write_text(json.dumps(summary,indent=2))
(OUT/'boot-nor-functions-disassembly.json').write_text(json.dumps(dis,indent=2))
print('saved boot-specific entries, SRAM closures, globals and restore conditions; no hardware I/O')
