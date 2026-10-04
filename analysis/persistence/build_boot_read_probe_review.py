"""Validate the locally assembled read-only BOOT RAM caller and NOR-test inputs.

No hardware/debug imports.  No Flash command script is generated.
"""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis/wifi/python-packages'))
sys.path.insert(0,str(OUT/'python-packages'))
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB,CS_MODE_MCLASS
from capstone.arm import ARM_OP_IMM,ARM_OP_MEM,ARM_REG_PC,ARM_REG_R7,ARM_REG_SP
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
raw=(OUT/'boot-nor-read-probe.bin').read_bytes()
with (OUT/'boot-nor-read-probe.o').open('rb') as f:
 elf=ELFFile(f);symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
 assert all(s.num_relocations()==0 for s in elf.iter_sections() if isinstance(s,RelocationSection))
 code_size=next(s['st_size'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name=='boot_nor_read_probe')
assert len(raw)==symbols['boot_nor_read_probe_end']==172
out=symbols['boot_nor_read_probe_output'];assert out==128
assert struct.unpack_from('<I',raw,symbols['boot_nor_read_probe_guard_before'])[0]==0xc0def00d
assert struct.unpack_from('<I',raw,symbols['boot_nor_read_probe_guard_after'])[0]==0x0df0dec0
cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_MCLASS);cs.detail=True
expected=[0x00201cf9,0x002018a9,0x00201901,0x00201901,0x002018f9]
windows=[]
for base in (0x20010000,0x200d5400):
 calls=[];r7=None;instructions=[]
 for i in cs.disasm(raw[:code_size],base):
  record={'offset':hex(i.address-base),'bytes':i.bytes.hex(),'mnemonic':i.mnemonic,'operands':i.op_str}
  if i.mnemonic in ('ldr','ldr.w') and i.operands[1].type==ARM_OP_MEM and i.operands[1].mem.base==ARM_REG_PC:
   pool=((i.address+4)&~3)+i.operands[1].mem.disp-base
   value=struct.unpack_from('<I',raw,pool)[0];record['literal_value']=hex(value)
   if i.operands[0].reg==ARM_REG_R7:r7=value
  if i.mnemonic=='blx':calls.append(r7)
  if i.mnemonic=='adr':
   target=((i.address+4)&~3)+i.operands[1].imm
   assert target==base+out;record['resolved_output_address']=hex(target)
  assert i.mnemonic not in ('push','pop','stmdb','ldm')
  assert not (i.operands and i.operands[0].type==1 and i.operands[0].reg==ARM_REG_SP)
  instructions.append(record)
 assert calls==expected
 windows.append({'illustrative_base':hex(base),'instructions':instructions,'absolute_callees':list(map(hex,calls))})
source=(ROOT/'backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
sector=source[0x825000:0x826000];assert sector==b'\xff'*4096
(OUT/'nor-test-original-sector-825000.bin').write_bytes(sector)
page=b'NORTEST1'+b'\xff'*248
(OUT/'nor-test-page-825100.bin').write_bytes(page)
fields=[(0,4,'original_PRIMASK'),(4,4,'masked_PRIMASK_must_be1'),(8,4,'native_ID_return'),(12,4,'pre_return'),
 (16,4,'SR1_read_return'),(20,4,'SR2_read_return'),(24,4,'post_return'),(28,4,'completion_52454144_or_abort_bad00001'),
 (32,3,'JEDEC'),(35,1,'SR1_opcode05'),(36,1,'SR2_opcode35'),(37,3,'reserved')]
review={'offline_only':True,'target_execution_performed':False,'NOR_write_script_generated':False,
 'stub':{'source':'analysis/persistence/boot-nor-read-probe.S','binary':'analysis/persistence/boot-nor-read-probe.bin',
  'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'code_bytes':code_size,'relocations':0,'position_independent':True,
  'absolute_function_targets':list(map(hex,expected)),'output_offset':out,'output_bytes':40,
  'guard_before_offset':symbols['boot_nor_read_probe_guard_before'],'guard_after_offset':symbols['boot_nor_read_probe_guard_after'],
  'BKPT_offset':next(i.address for i in cs.disasm(raw[:code_size],0)if i.mnemonic=='bkpt'),
  'fields':[{'offset':a,'bytes':n,'name':name}for a,n,name in fields],
  'stub_stack_changes':False,'maximum_HAL_callee_stack_bytes':64,'IRQ_state_at_BKPT':'masked; host restores original PRIMASK after RAM/core/controller validation'},
 'placement':{'borrowed_scratch':'[originalSP-1024, originalSP), originalSP must be8-aligned; save exact full1024 first',
  'code_base':'originalSP-1024; complete172-byte image ends at originalSP-852, below originalSP-512',
  'callee_stack':'uses unchanged originalSP downward, max64B for this stub; below-SP top512 band reserved for later max232B HAL calls',
  'limits':'originalSP-1024 must remain valid owned SRAM; SP and MSPLIM/PSPLIM unchanged; boot MSPLIM200d3e00 must permit originalSP-64',
  'after_stop':'capture outputs then restore original1024 scratch bytes and all saved core/debug state; do not resume the BKPT loop'},
 'host_state_to_save':['R0-R12','LR','originalSP and selected bank','MSP','PSP','MSPLIM','PSPLIM','CONTROL','PRIMASK','BASEPRI','FAULTMASK','xPSR','DCRDR','DHCSR/C_DEBUGEN and breakpoint/lock state','scratch1024','boot saved-lock20003b80','controller stable metadata'],
 'entry_preconditions':['deterministic boot breakpoint after NOR open and before main HAL overwrite',
  'boot code matches source excluding explicitly identified live mutable guard/frequency words',
  'opened byte20003ae0=1; cachedID856518; total20003af8=1000000; page20003afc=100',
  'active index20003b7a=0f; table200036d0=2000382c; callback20003844=002024f5',
  'first validate liveBOOT table20003300={40148000,40140000}; only then readid0base+0c busybit0 andbase+34 lockbit100, both0; A7 stopped; watchdog budget demonstrated',
  'MCU privileged and selected-bank SP/limits identified; originalSP8-aligned; chosen scratch saved/exclusive',
  'inject xPSR withT=1 andIT state cleared; boot pause is thread modeIPSR0; restore originalxPSR after completion',
  'C_DEBUGEN set so BKPT halts debug instead of faulting'],
 'success_conditions':['completion52454144; maskedPRIMASK1; both output guards intact; all5 returns0',
  'JEDEC856518; SR1/SR2 values captured as metadata and originalBP=(SR1|(SR2<<8))&407c',
  'post restores stable controller divider/mode/bus lock; saved software lock restored to original',
  'known existing NOR page from uncached28 alias equals saved backup after post',
  'original scratch/core/DCRDR and debug/A7 locks restored; original boot resumes and normal panel function confirmed'],
 'failure_policy':'if stub fails/does not return, keep cores stopped while collecting metadata; do not blindly resume/unlock pending SPI; no NVM command exists in this payload',
 'later_reversible_NOR_test_inputs':{
  'status':'prepared offline inputs only; no program/erase/protection runner; not authorized to execute by this builder',
  'prerequisites':'complete above boot-independent read recovery validation, refresh target sector live backup equality, verify current partition ownership and watchdog timing; root controls device execution',
  'candidate_sector_offset':'0x825000','sector_length':'0x1000','sector_uncached_alias':'0x28825000',
  'candidate_program_offset':'0x825100','program_uncached_alias':'0x28825100','program_length':'0x100','payload':'NORTEST1 then248 FF bytes, within one aligned page',
  'payload_file':'analysis/persistence/nor-test-page-825100.bin','payload_sha256':hashlib.sha256(page).hexdigest(),
  'original_sector_file':'analysis/persistence/nor-test-original-sector-825000.bin','original_sha256':hashlib.sha256(sector).hexdigest(),
  'partition_scope':'root independently confirmed ap partition spans150000..8e0000;825000 is within it and FF in this image, not an active firmware entry sector; this is not proof of permanent unallocated linker ownership',
  'exact_HAL_inputs_after_validation':{'unprotect':'bootsetBP(r0=0,r1=0); immediately05/35 readback validates supported BPbits clear',
   'program':'bootwrite1248(r0=0,r1=28825100,r2=exclusiveRAMpage256,r3=100); candidateRAMsource=code_base+100 (256B) if futurewriter code+output stay below+100; source ends oldSP-512',
   'restore':'booterase1104(r0=0,r1=28825000,r2=1000); no additional program required only because originalsector4096FF verified live',
   'reprotect':'bootsetBP0fe8(r0=0,r1=originalBP);05/35 verifyBP/QE/stable bits'},
  'required_readback':'after program entire4096 bytes equals originalsector with page atoffset100 replaced; after erase entire4096 equals original exactly; no other NOR differences permitted',
  'interrupt_power_loss_scope':'only selected FF app padding sector is changed; preserved boot can be recaught for restore; no change toboot/recovery/A7/factory/main entry or other metadata in this test',
  'future_OTA_limit':'future OTA can replace this padding; test marker must be removed immediately, not a permanent storage allocation',
  'later_persistent_hook':'separate reviewed two-sector scope150000/824000; this FF sector test does not itself install or validate that hook'},
 'disassembly':windows}
(OUT/'boot-nor-read-probe-review.json').write_text(json.dumps(review,indent=2))
print('validated RAM read-only probe',len(raw),'bytes; relocations0; noSPchange; prepared offline NOR test inputs only')
