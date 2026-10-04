"""Offline BOOT-only padding test caller and bounded host inputs.

Never imports or opens hardware/debug transports. Generated Tcl only calculates
arguments and checks supplied readbacks; it has no device read/write command.
"""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis/wifi/python-packages'))
sys.path.insert(0,str(OUT/'python-packages'))
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB,CS_MODE_MCLASS
from capstone.arm import ARM_OP_MEM,ARM_OP_IMM,ARM_REG_PC,ARM_REG_SP
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
raw=(OUT/'boot-nor-one-call.bin').read_bytes()
with (OUT/'boot-nor-one-call.o').open('rb') as f:
    elf=ELFFile(f)
    assert all(section.num_relocations()==0 for section in elf.iter_sections() if isinstance(section,RelocationSection))
    symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
    code_size=next(s['st_size'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name=='boot_nor_one_call')
assert len(raw)==symbols['boot_nor_one_call_end']==168
assert symbols['boot_nor_one_call_io']==128
assert struct.unpack_from('<I',raw,124)[0]==0xc0def00d
assert struct.unpack_from('<I',raw,164)[0]==0x0df0dec0
cs=Cs(CS_ARCH_ARM,CS_MODE_THUMB|CS_MODE_MCLASS);cs.detail=True
instructions=[]
for instruction in cs.disasm(raw[:code_size],0x002d5980):
    assert instruction.mnemonic not in ('push','pop','stmdb','ldm')
    assert not instruction.mnemonic.startswith('v')
    assert not(instruction.operands and instruction.operands[0].type==1 and instruction.operands[0].reg==ARM_REG_SP)
    if instruction.mnemonic=='adr':
        assert ((instruction.address+4)&~3)+instruction.operands[1].imm==0x002d5980+128
    instructions.append({'offset':hex(instruction.address-0x002d5980),'bytes':instruction.bytes.hex(),'mnemonic':instruction.mnemonic,'operands':instruction.op_str})
assert len([i for i in instructions if i['mnemonic']=='blx'])==1
bkpt=next(int(i['offset'],16) for i in instructions if i['mnemonic']=='bkpt')
source=(ROOT/'backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
assert hashlib.sha256(source).hexdigest()=='777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
original=source[0x825000:0x826000]
assert original==b'\xff'*4096
page=b'NORTEST1'+b'\xff'*248
expected_program=bytearray(original);expected_program[0x100:0x200]=page
(OUT/'nor-test-sector-programmed-825000.bin').write_bytes(expected_program)
def tcl_list(name,data):
    vals=struct.unpack('<'+'I'*(len(data)//4),data)
    lines=['set '+name+' {']
    lines+=['    '+' '.join(str(v) for v in vals[i:i+8])for i in range(0,len(vals),8)]
    return '\n'.join(lines+['}'])
constants='\n'.join([tcl_list('bnt_one_call_words',raw),tcl_list('bnt_page_words',page),
    tcl_list('bnt_original_sector_words',original),tcl_list('bnt_programmed_sector_words',expected_program)])
definitions=r'''
# Definitions/input calculations only. NO init, adapter, memory read/write,
# target execution, reset, resume, program, erase or status command is issued.
foreach bnt_name {bnt_one_call_words bnt_page_words bnt_original_sector_words bnt_programmed_sector_words} {
    set bnt_norm {}
    foreach bnt_v [set $bnt_name] { lappend bnt_norm [expr {$bnt_v+0}] }
    set $bnt_name $bnt_norm
}
proc bnt_stage_inputs {stage original_sp original_bp} {
    global bnt_one_call_words bnt_page_words
    if {$original_sp & 7 || $original_sp-1024 < 0x200d3e00 || $original_sp > 0x200d5e00} {
        error "Stage inputs require the reviewed fresh BOOT SP/limit ownership"
    }
    if {$original_bp & ~0x407c} { error "BP value must be actual composite status masked407c" }
    set base [expr {$original_sp-1024}]
    set source [expr {$base+256}]
    if {$stage == "unprotect"} {
        if {$original_bp == 0} { error "Original BP=0: omit protection writes entirely" }
        set input [list 0x00200fe9 0 0 0 0]
    } elseif {$stage == "program"} {
        set input [list 0x00201249 0 0x28825100 $source 0x100]
    } elseif {$stage == "erase_restore"} {
        set input [list 0x00201105 0 0x28825000 0x1000 0]
    } elseif {$stage == "reprotect"} {
        if {$original_bp == 0} { error "Original BP=0: omit protection writes entirely" }
        set input [list 0x00200fe9 0 $original_bp 0 0]
    } elseif {$stage == "invalidate_i"} {
        set input [list 0x00202fb5 0 0x2c825000 0x1000 0]
    } elseif {$stage == "invalidate_d"} {
        set input [list 0x00202fb5 1 0x2c825000 0x1000 0]
    } else { error "Unreviewed stage: no generic arbitrary callee admission" }
    set canonical_input {}
    foreach value $input { lappend canonical_input [expr {$value+0}] }
    set input $canonical_input
    # Return a pure metadata association list, not executable write commands.
    return [list stage $stage original_sp $original_sp data_base $base exec_base [expr {$base-0x1fe00000}] \
        image_words $bnt_one_call_words io_address [expr {$base+128}] io_input_words $input \
        payload_address $source payload_words $bnt_page_words payload_bytes 256 \
        bkpt_offset @BKPT@ output_words 9 guard_before_address [expr {$base+124}] guard_after_address [expr {$base+164}]]
}
proc bnt_verify_sector {phase supplied_words} {
    global bnt_original_sector_words bnt_programmed_sector_words
    if {[llength $supplied_words] != 1024} { error "Exact whole4K sector required" }
    set actual {}
    foreach value $supplied_words { lappend actual [expr {$value+0}] }
    if {$phase == "before" || $phase == "restored"} { set expected $bnt_original_sector_words
    } elseif {$phase == "programmed"} { set expected $bnt_programmed_sector_words
    } else { error "Unreviewed sector phase" }
    if {$actual != $expected} { error "Whole4K NOR sector differs from phase-specific exact backup" }
    return 1
}
proc bnt_verify_status {phase original_sr1 original_sr2 current_sr1 current_sr2} {
    foreach value [list $original_sr1 $original_sr2 $current_sr1 $current_sr2] {
        if {$value < 0 || $value > 255} { error "Only actual single-byte05/35 status samples accepted" }
    }
    set original [expr {$original_sr1|($original_sr2<<8)}]
    set current [expr {$current_sr1|($current_sr2<<8)}]
    if {$original_sr1 & 3} { error "Independent original status must have WIP/WEL clear" }
    if {$current_sr1 & 3} { error "WIP/WEL must be clear at completed-stage verification" }
    if {$phase == "unprotected" || $phase == "programmed" || $phase == "erased"} {
        set expected [expr {$original & ~0x407c}]
    } elseif {$phase == "before" || $phase == "restored"} { set expected $original
    } else { error "Unreviewed status phase" }
    # Ignore only volatile WIP/WEL; retain QE and every other status bit.
    if {($current & 0xfffc) != ($expected & 0xfffc)} {
        error "BP/QE/other stable status differs from exact measured expectation"
    }
    return 1
}
'''.replace('@BKPT@',str(bkpt))
cfg=ROOT/'diagnostics/boot-nor-padding-stage-inputs.cfg'
cfg.write_text('# Generated offline by build_boot_padding_plan.py\n'+constants+'\n'+definitions,encoding='ascii')
plan={
    'offline_only':True,'hardware_calls_performed':0,'automatic_execution':False,
    'target_image_sha256':hashlib.sha256(source).hexdigest(),
    'scope':{'NOR_sector_offset':'0x825000','sector_length':'0x1000','page_offset':'0x825100','page_length':'0x100',
             'payload':'NORTEST1 plus248FF','original_sector':'4096FF; must be refreshed live and byte-equal before any write',
             'ownership':'within reviewed AP150000..8e0000 and FF in current1.50.10; not permanent linker allocation; remove test immediately'},
    'stub':{'file':'analysis/persistence/boot-nor-one-call.bin','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),
            'code_bytes':code_size,'relocations':0,'IO_offset':128,'IO_words':9,'BKPT_offset':bkpt,
            'guard_before_offset':124,'guard_after_offset':164,'originalSP_changes':False,
            'HAL_maximum_stack_bytes':232,'uses_FPU':False,
            'IO_layout':['callee','r0','r1','r2','r3','original_PRIMASK','masked_PRIMASK_must1','return_must0','completion43414c4c'],
            'preconditions':'only fresh BOOT SRAM code/context; originalSP8aligned,MSPLIM200d3e00; Secure privileged Thread; C_DEBUGEN; IRQ masked; A7/other bus masters independently stopped; concrete rollback captured'},
    'host_inputs_library':'diagnostics/boot-nor-padding-stage-inputs.cfg',
    'host_inputs_library_status':'pure calculations and readback validators; defines no device I/O or automatic execution',
    'placement':{'scratch':'save full[oldSP-1024,oldSP) before each caller','code_output':'base=oldSP-1024;168B belowoldSP-856',
                 'payload':'base+0x100..base+0x200=oldSP-768..oldSP-512','callee_stack':'unchangedoldSP down,max232B; no overlap with code/output/payload'},
    'allowed_calls':{'unprotect':'00200fe9(r0=0,r1=0,r2=0,r3=0), omit iforigBP0',
                     'program':'00201249(r0=0,r1=28825100,r2=base+100,r3=100)',
                     'erase_restore':'00201105(r0=0,r1=28825000,r2=1000,r3=0)',
                     'reprotect':'00200fe9(r0=0,r1=(actualSR1|actualSR2<<8)&407c,r2=0,r3=0), omit iforigBP0',
                     'invalidate_i':'00202fb5(r0=0,r1=2c825000,r2=1000,r3=0)',
                     'invalidate_d':'00202fb5(r0=1,r1=2c825000,r2=1000,r3=0)'},
    'stages':[
        {'stage':'independent_read_verification','require':'real BOOT JEDEC9f=856518,status05/35 captured,controllerpost/restoration/knownNORpage/A7state verified; exactrootreset recovery route established'},
        {'stage':'live_backup','require':'read full4096B from28825000 and compare originalFF; save originalSR1/SR2,origBP=combined&407c,exactglobals/controller/core/scratch before changes'},
        {'stage':'unprotect_if_needed','require':'only iforigBP!=0; callsetBP0; freshnative05/35 readback matchesoriginalstablebits with407c cleared; QE and othersunchanged; allstatusWIP/WEL0'},
        {'stage':'program','require':'load exact256B NORTEST1+FF RAMpayload; admittedaddress/len; one-callret0/exactBKPT/guard/controllerpost; remainhalted'},
        {'stage':'host_program_readback','require':'read entire4096B uncached28825000; equals nor-test-sector-programmed-825000.bin exactly, not just8markerbytes; fresh05/35 states agree'},
        {'stage':'erase_restore','require':'erase exactsector28825000,len1000; one-callret0/exactBKPT/guard/controllerpost; remainhalted'},
        {'stage':'host_restoration_readback','require':'entire4096B byte-equal originalFF backup; no program restoration necessary solely because originalsector is provenlive4096FF'},
        {'stage':'restore_protection_if_needed','require':'only iforiginalBP!=0; setBP exactsavedvalue; fresh05/35 stablebitsincludingQE equaloriginal; origBP0 means no status-writecommands atanyphase'},
        {'stage':'scoped_cache_invalidation','require':'after physicalreadback succeeds, invalidateI thenD using2c825000,len1000, notwholecache; allcalls guarded/restored; no activecachedconsumer while bothcoresstopped'},
        {'stage':'final_context_restore','require':'BORROWEDRAM all1024 exact,core/DCRDR/PRIMASK/limits original,allBOOTHAL globals/state/savedlock stable,controllerpost verified; originalBOOTPC restored butremainhalted'},
        {'stage':'outer_resume','require':'root-only separate finalaction afterallchecks; originalmainbootandpanelhealth verified; noauto resume onerrors'}],
    'software_globals':'read-only stage saved-lock20003b80 restored afterpost; no-suspendwrite/erase state20003b5a may beassigned0 (requiresoriginal0); resumeaddr/src/len mustremainunchanged; verifywholeBSS320B',
    'status_rule':'originalBP0 skips bothunprotect/reprotect; originalBPnonzero onlymask407c changes; compare composite&fffc preservingQE and otherbits; WIP/WEL must0',
    'independent_reviews':{
        'one_call_ABI':'verify_boot_call independently verified168B,no relocation,I/O128,guards124/164,BKPT46; r4/r5/r7 saved by all normal callees; write/erase/BP peaks200/232/200; no normalFlash/FPU',
        'cache':'00202fb5 normal closure self-only,8B stack; all exits setr0=0; ID0I/1D; 2c825000,len1000 invalidates12832B lines,notwholecache; invalidcacheID also returns0 so exactinputs remainmandatory',
        'RAMX_output':'ADR usesexecalias,therefore independentrealread-probe dualalias/writeability evidence requiredbeforeNVMcaller',
    },
    'error_policy':'stop transaction/neverauto resume; do not callnextstage afterfailedguard/reset/exception/unknownpost; preserveactualhaltedstate and durablebackups; root may useindependentBOOT recovery torestoreexactsector/protection aftercontrollerstate is revalidated',
    'cold_loss_scope':'only inactiveFF apppadding marker canremain; boot/recovery/A7/factory/mainentry untouched; thisisnotpersistenthook installation',
    'readback_files':{'original':'analysis/persistence/nor-test-original-sector-825000.bin','payload':'analysis/persistence/nor-test-page-825100.bin','programmed':'analysis/persistence/nor-test-sector-programmed-825000.bin'},
    'readback_sha256':{'original':hashlib.sha256(original).hexdigest(),'payload':hashlib.sha256(page).hexdigest(),'programmed':hashlib.sha256(expected_program).hexdigest()},
    'limitations':['BOOT liveaccess/power recovery notyetprovedbythisofflineartifact','no actualNVMoperationperformed','no full16MiBNORdifferenceaudit is implied byone-sectorreadback','timer/WIP polling and watchdogbudget requireliveevidence'],
    'disassembly':instructions,
}
(OUT/'boot-nor-padding-test-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print(json.dumps({'stub_bytes':len(raw),'code_bytes':code_size,'BKPT_offset':bkpt,'input_cfg':str(cfg.relative_to(ROOT)),'planned_NOR_scope':'825000/4K only, page825100/256B','device_calls':0}))
