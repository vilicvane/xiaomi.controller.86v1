"""Prepare NEW fixed hook installer/restorer; strictly offline, no target APIs."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/persistence'
padding = ROOT / 'diagnostics/boot-nor-padding-runner.cfg'
frozen_kernel = OUT / 'boot-nor-hook-kernel-source-68b1b7fb.cfg'
kernel_sha = '68b1b7fb778cd507bee20837979f2529af4ed31bf369437dc45ebf8917d4655c'
if not frozen_kernel.exists():
    contents = padding.read_bytes()
    assert hashlib.sha256(contents).hexdigest() == kernel_sha
    frozen_kernel.write_bytes(contents)
assert hashlib.sha256(frozen_kernel.read_bytes()).hexdigest() == kernel_sha
original_kernel = frozen_kernel.read_text(encoding='utf-8')
# Preserve the peer's frozen files. Copy only its reviewed single-call kernel.
kernel = original_kernel[:original_kernel.index('# Main test entry.')]
kernel = kernel.replace('bnp_', 'bnh_').replace('bnt_', 'bhi_')
kernel = kernel.replace('boot-nor-padding-stage-inputs.cfg', 'boot-nor-hook-stage-inputs.cfg')
kernel = kernel.replace('bnh_padding_restored', 'bnh_hook_complete')
kernel = kernel.replace('bnh_run_padding_test', 'bnh_run_hook')
kernel = kernel.replace('one proven FF4K sector', 'two exact reviewed hook sectors')
kernel = kernel.replace('set bnh_native_return_closed 0\n', 'set bnh_native_return_closed 0\nset bnh_call_log_active 0\n',1)
old_log = 'proc bnh_log {line} { global bnh_result; puts $bnh_result $line; echo $line }'
assert old_log in kernel
kernel = kernel.replace(old_log,'''proc bnh_log {line} {
    global bnh_result bnh_hook_result bnh_call_log_active
    if {$bnh_call_log_active} { puts $bnh_result $line
    } else { puts $bnh_hook_result $line }
    echo $line
}''')
kernel = kernel.replace('    global bnh_last_sr1 bnh_last_sr2 bnh_flash_mutation_possible\n',
                        '    global bnh_last_sr1 bnh_last_sr2 bnh_flash_mutation_possible bnh_call_log_active\n')
kernel = kernel.replace('    set bnh_result [open [file join $capture_dir result.txt] w]\n',
                        '    set bnh_result [open [file join $capture_dir result.txt] w]\n    set bnh_call_log_active 1\n')
kernel = kernel.replace('    close $bnh_result\n', '    close $bnh_result\n    set bnh_call_log_active 0\n')
# Narrow initialization exclusions have independently proved writer evidence.
kernel = kernel.replace('$address == 0x20003acc || $address == 0x20003ad8',
                        '$address == 0x20003acc || $address == 0x20003ad0 || $address == 0x20003ad4 || $address == 0x20003ad8')
if 'set initialized_config_before' not in kernel:
    kernel = kernel.replace('        set globals_before [bnh_words 0x20003ae0 80]',
        '''        set initialized_config_before [bnh_words 0x20003ad0 2]
        dump_image [file join $capture_dir boot-initialized-config-before.bin] 0x20003ad0 8
        set globals_before [bnh_words 0x20003ae0 80]''')
    kernel = kernel.replace('        set bootmode_after [bnh_word 0x20003acc]',
        '''        set initialized_config_after [bnh_words 0x20003ad0 2]
        dump_image [file join $capture_dir boot-initialized-config-after.bin] 0x20003ad0 8
        if {$initialized_config_after != $initialized_config_before} { error "BOOT PMU/sysfreq initialized data changed" }
        set bootmode_after [bnh_word 0x20003acc]''')
kernel = kernel.replace('$kind == "onecall" && $stage == "program"',
                        '$kind == "onecall" && $admitted(payload_bytes) == 256')
kernel = kernel.replace('$kind == "onecall" && $stage in {unprotect program erase_restore reprotect}',
                        '$kind == "onecall" && ![string match "invalidate-*" $stage]')
if 'set pre_run_wdt_ctrl' not in kernel:
    raise AssertionError('Frozen reviewed kernel must include the immediate pre-run watchdog gate')
# Host deadline is separate from watchdog proof and never licenses stale replay.
deadline_start = kernel.index('        set timeout_ms 250\n')
deadline_end = kernel.index('        set begin [clock milliseconds]\n',deadline_start)
kernel = kernel[:deadline_start]+'''        set timeout_ms 250
        if {$kind == "onecall"} {
            set timeout_ms 1000
            if {[string match "*-erase" $stage]} { set timeout_ms 5000 }
        }
        set poll_limit [expr {$timeout_ms/5+2}]
        bnh_log "native_poll_budget_ms $timeout_ms max_polls $poll_limit stage $stage"
'''+kernel[deadline_end:]

def words(b):
    return list(struct.unpack('<' + 'I' * (len(b)//4), b))

sectors = {}
for label, offset in [('entry',0x150000),('payload',0x824000)]:
    for state in ['original','patched']:
        path = OUT / f'boot-hook-{state}-sector-{offset:x}.bin'
        data = path.read_bytes()
        assert len(data) == 4096
        sectors[label,state] = data
image = (ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
assert hashlib.sha256(image).hexdigest() == '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
assert sectors['entry','original'] == image[0x150000:0x151000]
assert sectors['payload','original'] == image[0x824000:0x825000]
stub = (OUT / 'boot-hook-1.50.10.bin').read_bytes()
assert len(stub) == 32
assert sectors['payload','original'][0x400:0x500] == b'\xff'*256
assert sectors['payload','patched'] == sectors['payload','original'][:0x400] + stub + sectors['payload','original'][0x420:]
assert sectors['entry','patched'][:0x56] == sectors['entry','original'][:0x56]
assert sectors['entry','patched'][0x5a:] == sectors['entry','original'][0x5a:]
one_call = (OUT / 'boot-nor-one-call.bin').read_bytes()
assert len(one_call) == 168

lines = ['# NEW fixed hook inputs; generated offline; sourcing does not run hardware.']
constants = {'bhi_one_call_words': words(one_call)}
for (label,state), data in sectors.items():
    constants[f'bhi_{label}_{state}_words'] = words(data)
constants['bhi_hook_page_words'] = words(stub + b'\xff'*(256-len(stub)))
for name, values in constants.items():
    lines.append('set '+name+' {')
    for i in range(0,len(values),8):
        lines.append('    '+' '.join(str(v) for v in values[i:i+8]))
    lines.append('}')

inputs = r'''
# Tcl source strings and read_memory lists have different text representations.
# Convert every generated constant into canonical numeric list before equality.
foreach bhi_name {bhi_one_call_words bhi_entry_original_words bhi_entry_patched_words bhi_payload_original_words bhi_payload_patched_words bhi_hook_page_words} {
    set bhi_normalized {}
    foreach bhi_value [set $bhi_name] { lappend bhi_normalized [expr {$bhi_value+0}] }
    set $bhi_name $bhi_normalized
}
# Pure calculation. Every admitted stage fixes both native callee and NOR range.
proc bhi_stage_inputs {stage original_sp original_bp} {
    global bhi_one_call_words bhi_hook_page_words
    global bhi_entry_original_words bhi_entry_patched_words bhi_payload_original_words
    if {$original_sp & 7 || $original_sp-1024 < 0x200d3e00 || $original_sp > 0x200d5e00} { error "Unreviewed BOOT stack" }
    if {$original_bp & ~0x407c} { error "Unreviewed BP bits" }
    set base [expr {$original_sp-1024}]
    set source [expr {$base+256}]
    set payload_words {}
    set payload_bytes 0
    if {$stage == "unprotect" || $stage == "reprotect"} {
        if {$original_bp == 0} { error "BP0 must skip status writes" }
        set bp 0
        if {$stage == "reprotect"} { set bp $original_bp }
        set input [list 0x00200fe9 0 $bp 0 0]
    } elseif {$stage == "install-payload-page"} {
        set input [list 0x00201249 0 0x28824400 $source 256]
        set payload_words $bhi_hook_page_words
        set payload_bytes 256
    } elseif {$stage == "install-entry-erase" || $stage == "restore-entry-erase"} {
        set input [list 0x00201105 0 0x28150000 4096 0]
    } elseif {$stage == "restore-payload-erase"} {
        set input [list 0x00201105 0 0x28824000 4096 0]
    } elseif {[regexp {^(install-entry|restore-entry|restore-payload)-page-([0-9]+)$} $stage all prefix page]} {
        if {$page < 0 || $page > 15 || $page != [expr {$page+0}]} { error "Page index is not admitted0..15" }
        if {$prefix == "install-entry"} {
            set sector $bhi_entry_patched_words; set address 0x28150000
        } elseif {$prefix == "restore-entry"} {
            set sector $bhi_entry_original_words; set address 0x28150000
        } else { set sector $bhi_payload_original_words; set address 0x28824000 }
        set payload_words [lrange $sector [expr {64*$page}] [expr {64*$page+63}]]
        if {[bhi_page_is_ff $payload_words]} { error "FF pages must be skipped after erase" }
        set payload_bytes 256
        set input [list 0x00201249 0 [expr {$address+256*$page}] $source 256]
    } elseif {[regexp {^invalidate-(entry|payload)-(i|d)$} $stage all label cache]} {
        if {$label == "entry"} { set address 0x2c150000 } else { set address 0x2c824000 }
        set id 0
        if {$cache == "d"} { set id 1 }
        set input [list 0x00202fb5 $id $address 4096 0]
    } else { error "No arbitrary native callee/address stage admitted" }
    set canonical {}
    foreach value $input { lappend canonical [expr {$value+0}] }
    return [list image_words $bhi_one_call_words io_input_words $canonical \
        payload_address $source payload_words $payload_words payload_bytes $payload_bytes]
}
proc bhi_page_is_ff {values} {
    if {[llength $values] != 64} { error "Exact256Bpage required" }
    foreach value $values { if {$value != 0xffffffff} { return 0 } }
    return 1
}
proc bhi_verify_status {phase original_sr1 original_sr2 current_sr1 current_sr2} {
    foreach value [list $original_sr1 $original_sr2 $current_sr1 $current_sr2] {
        if {$value < 0 || $value > 255} { error "Only native single-byte status accepted" }
    }
    set original [expr {$original_sr1|($original_sr2<<8)}]
    set current [expr {$current_sr1|($current_sr2<<8)}]
    if {($original_sr1|$current_sr1)&3} { error "WIP/WEL must be clear" }
    if {$phase == "unprotected"} { set expected [expr {$original & ~0x407c}]
    } elseif {$phase == "original"} { set expected $original
    } else { error "Unreviewed stable status phase" }
    if {($current & 0xfffc) != ($expected & 0xfffc)} { error "BP/QE/stable status mismatch" }
}
'''
inputs_path = ROOT / 'diagnostics/boot-nor-hook-stage-inputs.cfg'
inputs_path.write_text('\n'.join(lines)+'\n'+inputs,encoding='utf-8')

orchestrator = r'''
# ONLY public operation: install or restore, exact original/patched sectors.
proc bnh_hook_log {line} { global bnh_hook_result; puts $bnh_hook_result $line; echo $line }
proc bnh_status_stage {dir phase sr1 sr2 remove_fpb_command} {
    global bnh_last_sr1 bnh_last_sr2
    bnh_execute_call $dir read read-status 0 $remove_fpb_command
    bhi_verify_status $phase $sr1 $sr2 $bnh_last_sr1 $bnh_last_sr2
    bnh_hook_log [format "verified_status %s SR1%02x SR2%02x" $phase $bnh_last_sr1 $bnh_last_sr2]
}
proc bnh_verify_sector {dir label expected} {
    if {$label == "entry"} { set address 0x28150000
    } elseif {$label == "payload"} { set address 0x28824000
    } else { error "Unreviewed sector" }
    if {[bnh_words $address 1024] != $expected} { error "Exact whole4K $label readback failed" }
    dump_image [file join $dir sector-$label-verified.bin] $address 4096
    bnh_hook_log "whole_sector_verified $label"
}
proc bnh_write_sector {dir prefix words original_bp remove_fpb_command} {
    global bhi_entry_original_words bhi_entry_patched_words bhi_payload_original_words
    if {$prefix == "install-entry"} { set fixed_words $bhi_entry_patched_words
    } elseif {$prefix == "restore-entry"} { set fixed_words $bhi_entry_original_words
    } elseif {$prefix == "restore-payload"} { set fixed_words $bhi_payload_original_words
    } else { error "Sector helper admits only exact reviewed entry/payload stages" }
    if {$words != $fixed_words} { error "Sector helper refuses arbitrary source data before erase" }
    bnh_execute_call [file join $dir $prefix-erase] onecall $prefix-erase $original_bp $remove_fpb_command
    for {set page 0} {$page < 16} {incr page} {
        set expected_page [lrange $words [expr {64*$page}] [expr {64*$page+63}]]
        if {[bhi_page_is_ff $expected_page]} {
            bnh_hook_log "skip_FF_page $prefix $page"
        } else {
            bnh_execute_call [file join $dir $prefix-page-$page] onecall $prefix-page-$page $original_bp $remove_fpb_command
        }
    }
}
proc bnh_run_hook {capture_dir mode remove_fpb_command} {
    global bnh_safe_to_resume bnh_hook_complete bnh_flash_mutation_possible bnh_hook_result
    global bnh_last_sr1 bnh_last_sr2 bnor_safe_to_resume bnor_reset_seen bnor_track_reset
    global bhi_entry_original_words bhi_entry_patched_words bhi_payload_original_words bhi_payload_patched_words
    set bnh_safe_to_resume 0; set bnh_hook_complete 0; set bnh_flash_mutation_possible 0
    if {$mode != "install" && $mode != "restore"} { error "Only reviewed install or restore accepted" }
    if {![info exists bnor_safe_to_resume] || !$bnor_safe_to_resume ||
        ![info exists bnor_reset_seen] || $bnor_reset_seen || ![info exists bnor_track_reset] || !$bnor_track_reset} {
        error "Successful same-process independent reader is required"
    }
    if {[file exists $capture_dir]} { error "New capture directory required" }
    file mkdir $capture_dir
    set bnh_hook_result [open [file join $capture_dir result.txt] w]
    bnh_hook_log "scope mode=$mode; fixedsectors150000/824000 only; no automatic retry/resume"
    set operation_error [catch {
        bnh_stable_halt
        if {[bnh_word 0x40082008] != 0} { error "Outer verified native AON watchdog stop required" }
        bnh_a7_gate held-reset-cmu-verified
        # BOTH full sectors admitted before any protection/program/erase call.
        set entry_before [bnh_words 0x28150000 1024]
        set payload_before [bnh_words 0x28824000 1024]
        if {$mode == "install"} {
            if {$entry_before != $bhi_entry_original_words || $payload_before != $bhi_payload_original_words} { error "Install requires both exact original sector baselines" }
        } else {
            if {($entry_before != $bhi_entry_original_words && $entry_before != $bhi_entry_patched_words) ||
                ($payload_before != $bhi_payload_original_words && $payload_before != $bhi_payload_patched_words)} { error "Restore requires exact original/patched sector baselines" }
        }
        dump_image [file join $capture_dir sector-entry-before.bin] 0x28150000 4096
        dump_image [file join $capture_dir sector-payload-before.bin] 0x28824000 4096
        bnh_execute_call [file join $capture_dir status-before] read read-status 0 $remove_fpb_command
        set original_sr1 $bnh_last_sr1; set original_sr2 $bnh_last_sr2
        bhi_verify_status original $original_sr1 $original_sr2 $original_sr1 $original_sr2
        set original_bp [expr {($original_sr1|($original_sr2<<8))&0x407c}]
        if {$original_bp != 0} { bnh_execute_call [file join $capture_dir unprotect] onecall unprotect $original_bp $remove_fpb_command }
        bnh_status_stage [file join $capture_dir status-unprotected] unprotected $original_sr1 $original_sr2 $remove_fpb_command
        if {$mode == "install"} {
            # Payload completed+whole-sector verified before touching entry.
            bnh_execute_call [file join $capture_dir install-payload-page] onecall install-payload-page $original_bp $remove_fpb_command
            bnh_verify_sector $capture_dir payload $bhi_payload_patched_words
            bnh_status_stage [file join $capture_dir status-payload] unprotected $original_sr1 $original_sr2 $remove_fpb_command
            bnh_write_sector $capture_dir install-entry $bhi_entry_patched_words $original_bp $remove_fpb_command
            set expected_entry $bhi_entry_patched_words; set expected_payload $bhi_payload_patched_words
            bnh_verify_sector $capture_dir entry $expected_entry
        } else {
            # Restore entry first so no installed branch remains before payload erase.
            bnh_write_sector $capture_dir restore-entry $bhi_entry_original_words $original_bp $remove_fpb_command
            bnh_verify_sector $capture_dir entry $bhi_entry_original_words
            bnh_status_stage [file join $capture_dir status-entry-restored] unprotected $original_sr1 $original_sr2 $remove_fpb_command
            bnh_write_sector $capture_dir restore-payload $bhi_payload_original_words $original_bp $remove_fpb_command
            set expected_entry $bhi_entry_original_words; set expected_payload $bhi_payload_original_words
            bnh_verify_sector $capture_dir payload $expected_payload
        }
        bnh_status_stage [file join $capture_dir status-final-data] unprotected $original_sr1 $original_sr2 $remove_fpb_command
        if {$original_bp != 0} { bnh_execute_call [file join $capture_dir reprotect] onecall reprotect $original_bp $remove_fpb_command }
        bnh_status_stage [file join $capture_dir status-restored] original $original_sr1 $original_sr2 $remove_fpb_command
        foreach sector {entry payload} {
            foreach cache {i d} {
                set stage invalidate-$sector-$cache
                bnh_execute_call [file join $capture_dir $stage] onecall $stage $original_bp $remove_fpb_command
            }
        }
        if {[bnh_words 0x28150000 1024] != $expected_entry || [bnh_words 0x28824000 1024] != $expected_payload} { error "Whole sectors changed after cache invalidation" }
        bnh_stable_halt; bnh_a7_gate held-reset-cmu-verified
        if {[bnh_word 0x40082008] != 0} { error "Stopped AON watchdog changed" }
        set bnh_hook_complete 1; set bnh_safe_to_resume 1
        bnh_hook_log "hook_data_protection_context_verified 1; leaveBOOT halted; outer owns finalGLOBAL"
    } operation_message]
    if {$operation_error} {
        set bnh_safe_to_resume 0
        bnh_hook_log "operation_error $operation_message"
        bnh_hook_log "NO_AUTO_NEXT_STAGE_OR_RESUME; inspect physical sectors/status and closed native context"
    }
    bnh_hook_log "flash_mutation_possible $bnh_flash_mutation_possible complete $bnh_hook_complete safe_to_resume $bnh_safe_to_resume"
    close $bnh_hook_result
    if {$operation_error} { error "Fixed hook operation failed; retain halt/evidence for independent root recovery" }
    return 1
}
'''
runner = ROOT / 'diagnostics/boot-nor-hook-runner.cfg'
runner.write_text(kernel+'\n'+orchestrator,encoding='utf-8')
report = {
    'offline_only':True,'hardware_actions':0,'runner':str(runner.relative_to(ROOT)),
    'runner_sha256':hashlib.sha256(runner.read_bytes()).hexdigest(),
    'kernel_derived_from':str(padding.relative_to(ROOT)),
    'kernel_source_sha256':kernel_sha,
    'frozen_kernel_source':str(frozen_kernel.relative_to(ROOT)),
    'inputs_sha256':hashlib.sha256(inputs_path.read_bytes()).hexdigest(),
    'public_operation':'bnh_run_hook capture_dir install|restore remove_fpb_command',
    'immutable_dependencies':['boot-nor-read-runner-data.cfg','boot-nor-one-call.bin','boot-hook-review-1.50.10.json'],
    'scope':{'sectors':['150000/4096','824000/4096'],'install_first':'program256B824400=32Bstub+FF withoutpayloadsectorerase;verifywholepayload4096','install_second':'eraseentry150000+exactpatchednonFFpages;verifywholeentry4096','restore_first':'eraseentry150000+originalnonFFpages;verifywholeentry4096','restore_second':'erasepayload824000+originalnonFFpages;verifywholepayload4096'},
    'preconditions':['same-process successfulreader','freshoriginalBOOTHAL/staticcode andopenedctx','A7/WF/BTCPUs heldreset','outerverifiedAONwatchdogCTRL0','installrequiresbothoriginal4Kbaselines;restorerequiresoriginal-or-patched4Kpersector'],
    'failure_policy':'noautomatic retry/nextstage/reprotect/erase/resume; unclosednativecontext not replayed; halted root diagnosis and independentrecovery',
    'partial_restore_supervised_helper':'after independentfreshBOOT/reader/controller revalidation, root may supervisefixedoriginal restore-entry helper evenifentrybaselineunknown; exactcompiledoriginalpages,sourceandprefixadmissionbeforeerase,no payloadaccess,noautofailurewrite; protection/status/cachestepsalsofixedandexplicit; separatefrompublicrestorebaselinegate',
    'status_semantics':'BPmask407c only;BP0skipstatuswrites;native05/35 before andafterphases;WIP/WEL0,QE/everyotherstablebitexact;bothscopedcacheI/D;leaveBOOTstopped',
    'mock_status':'pending; not authorized forhardwareuntil rootreviewand independent tests',
    'sector_hashes':{label+'_'+state:hashlib.sha256(data).hexdigest() for (label,state),data in sectors.items()},
}
(OUT/'boot-nor-hook-runner-review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'prepared':str(runner.relative_to(ROOT)),'sha256':report['runner_sha256'],'hardware_actions':0}))
