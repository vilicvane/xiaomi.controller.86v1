"""Offline evidence only. Does not connect to a probe or mutate backup images."""
from pathlib import Path
import contextlib,hashlib,json,struct
import probe_nor as n

OUT=Path('analysis/persistence');OUT.mkdir(exist_ok=True)
controller_ids=list(struct.unpack_from('<II',n.B,n.off(0x20003948)))
assert controller_ids==[0x40148000,0x40140000]
def h(b):return hashlib.sha256(b).hexdigest()
functions=[
 ('hal_norflash_get_size',0x2000118c,0x200011f2,'r0=id, r1=total*, r2=block*, r3=sector*, [sp]=page*; r0=ret'),
 ('hal_norflash_get_id_cached',0x2000120c,0x20001244,'r0=id, r1=buffer, r2=len; copies min(len,3) cached bytes; r0=0'),
 ('hal_norflash_enable_protection',0x200012c0,0x20001310,'r0=id; writes protection state; NOT read-only'),
 ('hal_norflash_disable_protection',0x20001310,0x2000135c,'r0=id; writes protection state; NOT read-only'),
 ('hal_norflash_set_protection_candidate',0x2000135c,0x200013ac,'r0=id, r1=bp value; verified call to norflash_set_block_protection'),
 ('hal_norflash_erase_suspend',0x200013c4,0x2000144c,'r0=id, r1=start, r2=len, r3=suspend; r0=ret'),
 ('hal_norflash_erase',0x2000144c,0x20001454,'r0=id, r1=start, r2=len; forces suspend=0; r0=ret'),
 ('hal_norflash_write_suspend',0x20001504,0x20001590,'r0=id, r1=start, r2=buffer, r3=len, [sp]=suspend; r0=ret'),
 ('hal_norflash_write',0x20001590,0x200015a0,'r0=id, r1=start, r2=buffer, r3=len; forces suspend=0; r0=ret'),
 ('norflash_pre_operation',0x20001c34,0x20001c3c,'r0=id; sets memory-read bus lock and read-mode state; r0=ret'),
 ('norflash_post_operation',0x20001c84,0x20001c8c,'r0=id; restores mode/divider/read bus state; r0=ret'),
 ('norflash_read_reg',0x20001c8c,0x20001cc8,'r0=id, r1=command, r2=RAM output buffer, r3=len; r0=0; requires pre/post externally'),
 ('norflash_read_status_low',0x20001cc8,0x20001d00,'r0=id; r0=one byte from command05; includes Flash stack-canary reference'),
 ('norflash_status_WIP_wait',0x20001d00,0x20001d7c,'r0=id, r1=suspend; polls bit0 via read_status_low; no bounded timeout visible'),
 ('norflash_read_status_high',0x20001fb8,0x20001ff0,'r0=id; r0=one byte from command35; includes Flash stack-canary reference'),
 ('norflash_get_id_native_command',0x20002084,0x200020ac,'r0=id, r1=RAM buffer, r2=len; pre/readcmd9f(min3)/post; r0=0'),
 ('norflash_set_block_protection',0x200027a0,0x200027c8,'r0=id, r1=bp; callback type4; mutates protection'),
 ('chip_write_status_callback',0x20002900,0x20002a64,'native pointer RAMX0x00202901; r0=id, r1=status operation type, r2=parameter; reads/writes status regs'),
 ('norflash_api_irq_lock',0x2001348c,0x200134a4,'r0=id(0): saves PRIMASK to0x340eea08 and cpsid i; not RTOS mutex'),
 ('norflash_api_irq_unlock',0x200134a4,0x200134b8,'r0=id(0): restores IRQ enable per0x340eea08; not RTOS mutex'),
 ('norflash_api_invalidate_after_write',0x2001352c,0x20013578,'r0=id, r1=address, r2=len; only acts on cachedFlash2c alias; invalidates IC then DC'),
 ('hal_cache_invalidate',0x20003348,0x20003390,'r0=cache id(0I/1D), r1=start, r2=len; rounds cache lines32bytes; whole cache iflen>=0x4000'),
]
records=[]
with (OUT/'identified-functions-disassembly.txt').open('w',encoding='utf-8')as f,contextlib.redirect_stdout(f):
 for name,a,z,abi in functions:
  p=n.off(a);q=n.off(z)
  print('\nFUNCTION',name,hex(a),abi);n.dis(p,q,a)
  records.append(dict(name=name,address=hex(a),thumb_pointer=hex(a|1),file_offset=hex(p),end=hex(z),abi=abi,source_bytes_sha256=h(n.B[p:q]),prologue_hex=n.B[p:p+16].hex()))
context_path=Path('backups/display-takeover/norflash-context.bin')
ctx=context_path.read_bytes()if context_path.exists()else None
metadata={'runtime_capture':str(context_path),'runtime_size':len(ctx)if ctx else None,'record_size':'0x24','record_base':'0x2000417c','id0_fields':{'opened':'0x2000417c','cached_jedec_3':'0x2000417d','total_size_u32':'0x20004194','page_size_u32':'0x20004198'},'sector_size_fixed_in_binary':'0x1000','block_size_fixed_in_binary':'0x8000'}
if ctx:
 metadata.update(opened=ctx[0],jedec=ctx[1:4].hex(),total_size=hex(struct.unpack_from('<I',ctx,0x18)[0]),page_size=hex(struct.unpack_from('<I',ctx,0x1c)[0]))
guards=[]
for addr in [0x20001cfc,0x20001fec,0x20002a60]:
 guards.append(dict(ram_literal_pool=hex(addr),file_offset=hex(n.off(addr)),literal_value=hex(struct.unpack_from('<I',n.B,n.off(addr))[0]),kind='cachedFlash stack-canary load inside the SPI critical path'))
first=n.B[0x150000:0x151000];(OUT/'original-main-entry-sector-150000.bin').write_bytes(first)
firstmeta={'file':'analysis/persistence/original-main-entry-sector-150000.bin','size':len(first),'sha256':h(first),'target_flash_offset':'0x150000','purpose':'offline original bytes for future exact-sector restore; not a flash command'}
summary=dict(image='backups/mi-panel-flash-16m-1.50.10-20261004.bin',sha256=h(n.B),offline_only=True,functions=records,runtime_metadata=metadata,sram_copy_segments=[dict(file_start=hex(a),file_end=hex(z),ram_start=hex(d),size=hex(z-a))for a,z,d in n.SEGMENTS],flash_dependencies=guards,controller={'id0':hex(controller_ids[0]),'id1':hex(controller_ids[1]),'base_pointer_table':'0x20003948','memory_read_lock_bit':'controller+0x34 bit0x100','saved_bus_lock':'0x2000421c','selected_chip_index_byte':'0x20004216','current_mode_u32':'0x20004224','suspend_state_byte':'0x200041f6','chip_cfg_table':'0x20003d7c','chip_856518_table_index':15,'chip_cfg_856518':'0x20003f14','chip_cfg_856518_block_protect_mask':'0x407c','chip_cfg_856518_callback_thumb':'0x00202901'},entry_sector_original=firstmeta,main_hook_candidate={'file_offset':'0x150056','original_instruction_hex':n.B[0x150056:0x15005a].hex(),'semantics':'BL0x0c5d6538 after early RAM/PSRAM initialization; before main entry','not_verified':'image authentication/CRC coverage, cave ownership, reboot/recovery execution and smallest persistent payload'},blank_content_only=[{'start':'0x825000','end':'0x8e0000','all_ff':n.B[0x825000:0x8e0000]==b'\xff'*(0x8e0000-0x825000),'safe_unused_partition':False}],public_reference_discrepancy={'hal_not_opened_ret_in_binary':'0x10','hal_not_opened_ret_in_public_header':'0x0e','puya_p25q128h_and_l_datasheet_jedec':'85-60-18','actual_cached_jedec':'85-65-18','exact_chip_part':'not proved from those public datasheets; do not infer supply voltage/timing from them'})
summary['parent_reported_runtime_active_chip_confirmation']={'provenance':'root agent direct hardware reads, not reads performed by this script','values':{'0x20004216':'0x0f','0x20003db8':'0x20003f14','0x20003f2c':'0x00202901'}}
summary['read_only_probe']={'native_jedec_thumb':'0x20002085','status_sequence':['pre(0)','read_reg(0,0x05,out,1)','read_reg(0,0x35,out+1,1)','post(0)'],'maximum_callee_stack_bytes':64,'recommended_dedicated_stack_bytes_minimum':256,'stack_alignment_bytes':8,'registers_to_snapshot':[hex(controller_ids[0]+o) for o in (4,12,20,52,60)]+['0x2000421c'],'do_not_bulk_read_fifo':[hex(controller_ids[0]+o) for o in (8,16)],'entry_preconditions':['first verify liveSRAM controller table20003948={40148000,40140000}; no peripheral access before table verification','controller status+0x0c bit0 clear','controller+0x34 bit0x100 clear','A7 halted','MCU privileged and IRQ mask confirmed','SRAM bytes and active chip context compared','dedicated code/output/stack region preserved and exclusively used'],'postcondition_note':'read/command transfer fields can differ; divider and stable read-mode/bus-lock configuration must return to baseline; software saved-lock word is the only software write in pre/post'}
summary['controller_mapping_correction']={'previous_wrong_assumption':'logicalid0=40140000; oldreport labels were not rawtable verified','raw_table_file_offset':hex(n.off(0x20003948)),'raw_bytes':n.B[n.off(0x20003948):n.off(0x20003948)+8].hex(),'corrected_mapping':[hex(v) for v in controller_ids],'provenance':'exact currentimage bytes plus rootreported live20003948={40148000,40140000} in diagnostics/mcu-safe-reset-metadata.txt; this script performs no hardware I/O','root_observed_limit':'old unused4014000c access stalled AP; correctbase4014800c/34 reads succeed whileMCUrunning; mapping correction proved, underlying stallcause not independently proved'}
(OUT/'nor-programming-review.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
print('wrote evidence; no hardware I/O; image sha256',h(n.B))
