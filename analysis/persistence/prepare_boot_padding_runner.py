"""Build NEW definitions-only padding runner from reviewed reader safeguards.

Does not edit or execute the source read runner, reset pilot, or target hardware.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
reader_path = ROOT / "diagnostics/boot-nor-read-runner.cfg"
assert hashlib.sha256(reader_path.read_bytes()).hexdigest() == "1bd3b194645e755753b0253c9d0f0cab5a3b3cb189c83451cc522130d9560742", "Reader changed: independently review before generating padding runner"
source = reader_path.read_text().replace("bnor_", "bnp_")
source = source.replace("# Root may call bnp_run_read_probe only while halted at a fresh original BOOT", "# Root may call bnp_run_padding_test only after successful same-epoch reader")
source = source.replace("# breakpoint. This payload issues JEDEC/status reads, never program/erase/WREN.", "# and fresh BOOT halt. Native writes are allowlisted to one proven FF4K sector.")
source = source.replace('source [file join $bnp_library_directory ../analysis/persistence/boot-nor-read-runner-data.cfg]',
    '''source [file join $bnp_library_directory ../analysis/persistence/boot-nor-read-runner-data.cfg]
source [file join $bnp_library_directory boot-nor-padding-stage-inputs.cfg]
foreach suffix {expected_boot_words expected_probe_words expected_nor_page_words} {
    set bnp_$suffix [set bnor_$suffix]
}
set bnp_flash_mutation_possible 0
set bnp_padding_restored 0
set bnp_last_sr1 0
set bnp_last_sr2 0
set bnp_native_return_closed 0''')
start = source.index('proc bnp_a7_gate {policy} {')
end = source.index('proc bnp_verify_boot_code {} {', start)
source = source[:start] + '''proc bnp_a7_gate {policy} {
    if {$policy != "held-reset-cmu-verified"} { error "Padding caller requires independent BOOT reset isolation" }
    # APDBG was reset: never read A7 PRSR/DSCR. Original BOOT has released the
    # A7 subsystem bit0 but holds A7CPU/WFCPU/BTCPU bits1/7/8 before main.
    for {set i 0} {$i < 2} {incr i} {
        set status [bnp_word 0x400800a4]
        bnp_log [format "held_reset_aon_%d 0x%08x" $i $status]
        if {$status & 0x182} { error "A7/WF/BT CPU reset no longer asserted" }
    }
}
''' + source[end:]
source = source.replace('proc bnp_run_read_probe {capture_dir a7_policy remove_fpb_command} {',
    'proc bnp_execute_call {capture_dir kind stage original_bp remove_fpb_command} {\n    set a7_policy "held-reset-cmu-verified"')
source = source.replace('    global bnp_expected_probe_words bnp_expected_nor_page_words',
    '    global bnp_expected_probe_words bnp_expected_nor_page_words bnp_native_return_closed\n    global bnp_last_sr1 bnp_last_sr2 bnp_flash_mutation_possible\n    set bnp_native_return_closed 0')
source = source.replace('scope BOOT JEDEC9f/status05/status35; no NOR mutation; preserve SP/limits; leave halted',
    'scope admittedBOOTHAL stage=$stage kind=$kind; preserve1KiB/core/SP/limits; leavehalted; no arbitrarycallees')
source = source.replace('    set test_error [catch {\n        set original_dhcsr',
    '''    set test_error [catch {
        if {$kind == "read"} {
            if {$stage != "read-status"} { error "Read payload stage is fixed" }
        } elseif {$kind != "onecall"} { error "Payload kind must be exact reviewed read or onecall" }
        # Root owns the separately proved original BOOT watchdog-stop sequence.
        # Gate every caller entry before transfers or scratch/core modifications.
        set entry_wdt_ctrl [bnp_word 0x40082008]
        bnp_log [format "entry_AON_WDT_CTRL 0x%08x" $entry_wdt_ctrl]
        if {$entry_wdt_ctrl != 0} { error "Original BOOT AON watchdog must already be stopped" }
        set original_dhcsr''')
anchor = '        foreach selector $selectors { bnp_log [format "saved_regsel_%02x 0x%08x" $selector $saved($selector)] }'
setup = '''        if {$kind == "read"} {
            set expected_image $bnp_expected_probe_words
            set bkpt_offset 94
            set output_count 10
            set guard_after_offset 168
        } else {
            array set admitted [bnt_stage_inputs $stage $original_sp $original_bp]
            set expected_image $admitted(image_words)
            set admitted_input $admitted(io_input_words)
            for {set i 0} {$i < 5} {incr i} {
                lset expected_image [expr {32+$i}] [lindex $admitted_input $i]
            }
            set bkpt_offset 46
            set output_count 9
            set guard_after_offset 164
        }
'''
assert anchor in source
source = source.replace(anchor, setup + anchor)
old = '''        write_memory $data_base 32 $bnp_expected_probe_words
        if {[bnp_words $data_base 43] != $bnp_expected_probe_words ||
            [bnp_words $exec_base 43] != $bnp_expected_probe_words} { error "Probe image failed alias readback" }'''
new = '''        write_memory $data_base 32 $expected_image
        if {[bnp_words $data_base [llength $expected_image]] != $expected_image ||
            [bnp_words $exec_base [llength $expected_image]] != $expected_image} { error "Exact admitted caller image failed dualalias readback" }
        if {$kind == "onecall" && $stage == "program"} {
            write_memory $admitted(payload_address) 32 $admitted(payload_words)
            if {[bnp_words $admitted(payload_address) 64] != $admitted(payload_words)} { error "Exact admitted page payload failed RAM readback" }
        }'''
assert old in source
source = source.replace(old,new)
source = source.replace('        set started 1\n        bnp_put 0xe000edf0 0xa05f0009',
    '''        # Recheck immediately before execution. If active, restore the
        # borrowed context without admitting any native NOR command.
        set pre_run_wdt_ctrl [bnp_word 0x40082008]
        bnp_log [format "pre_run_AON_WDT_CTRL 0x%08x" $pre_run_wdt_ctrl]
        if {$pre_run_wdt_ctrl != 0} { error "AON watchdog became active before native execution" }
        set started 1
        # A CPU-run transport error may follow commit. Record irreversible
        # command possibility before executing any admitted mutation caller.
        if {$kind == "onecall" && $stage in {unprotect program erase_restore reprotect}} {
            set bnp_flash_mutation_possible 1
            bnp_log "native_flash_mutation_possible 1 stage $stage"
        }
        bnp_put 0xe000edf0 0xa05f0009''')
old_poll = '''        set begin [clock milliseconds]
        set stopped 0
        for {set i 0} {$i < 150} {incr i} {
            set dhcsr [bnp_word 0xe000edf0]
            if {$bnp_reset_seen || ($dhcsr & 0x2080000)} { set context_safe 0; error "Reset/lockup during SPI read caller" }
            if {$dhcsr & 0x20000} { set stopped 1; break }
            if {[clock milliseconds] - $begin >= 250} { break }
        }'''
new_poll = '''        # These are bounded host observation budgets, not datasheet maxima.
        # The independently stopped AON WDT is required for every stage.
        set timeout_ms 250
        if {$kind == "onecall" && $stage == "erase_restore"} { set timeout_ms 5000 }
        if {$kind == "onecall" && $stage in {unprotect program reprotect}} { set timeout_ms 1000 }
        set poll_limit [expr {$timeout_ms/5 + 2}]
        bnp_log "native_poll_budget_ms $timeout_ms max_polls $poll_limit"
        set begin [clock milliseconds]
        set stopped 0
        for {set i 0} {$i < $poll_limit} {incr i} {
            set dhcsr [bnp_word 0xe000edf0]
            if {$bnp_reset_seen || ($dhcsr & 0x2080000)} { set context_safe 0; error "Reset/lockup during SPI read caller" }
            if {$dhcsr & 0x20000} { set stopped 1; break }
            if {[clock milliseconds] - $begin >= $timeout_ms} { break }
            sleep 5
        }'''
assert old_poll in source
source = source.replace(old_poll, new_poll)
source = source.replace('SPI read caller', 'BOOT native caller')
source = source.replace('$stop_pc != $exec_base + 94', '$stop_pc != $exec_base + $bkpt_offset')
source = source.replace('set output [bnp_words [expr {$data_base+128}] 10]', 'set output [bnp_words [expr {$data_base+128}] $output_count]')
start = source.index('        if {[lindex $output 0] != ($saved(20) & 255)')
end = source.index('        set controller_after [bnp_controller_snapshot]',start)
validation = '''        if {[bnp_word [expr {$data_base+124}]] != 0xc0def00d ||
            [bnp_word [expr {$data_base+$guard_after_offset}]] != 0x0df0dec0} {
            set context_safe 0; error "Native caller memory guards changed"
        }
        if {$kind == "read"} {
            if {[lindex $output 0] != ($saved(20) & 255) || [lindex $output 1] != 1 || [lindex $output 7] != 0x52454144} {
                set context_safe 0; error "Read caller mask/completion invalid"
            }
            foreach index {2 3 4 5 6} {
                if {[lindex $output $index] != 0} { set context_safe 0; error "Native read/pre/post returned an error" }
            }
        } else {
            for {set i 0} {$i < 5} {incr i} {
                if {[lindex $output $i] != [lindex $admitted_input $i]} { set context_safe 0; error "Onecall admitted arguments changed" }
            }
            if {[lindex $output 5] != ($saved(20) & 255) || [lindex $output 6] != 1 ||
                [lindex $output 7] != 0 || [lindex $output 8] != 0x43414c4c} {
                set context_safe 0; error "Onecall mask/native-return/completion invalid"
            }
        }
'''
source = source[:start] + validation + source[end:]
start = source.index('        if {([lindex $output 8] & 0xffffff)')
end = source.index('        if {[bnp_word 0x20003b80] != 0}', start)
status = '''        set bnp_native_return_closed 1
        if {$kind == "read"} {
            if {([lindex $output 8] & 0xffffff) != 0x186585} { error "Native JEDEC differs from known856518" }
            set bnp_last_sr1 [expr {([lindex $output 8] >> 24) & 255}]
            set bnp_last_sr2 [expr {[lindex $output 9] & 255}]
            bnp_log [format "JEDEC856518 SR1 0x%02x SR2 0x%02x" $bnp_last_sr1 $bnp_last_sr2]
            if {$bnp_last_sr1 & 3} { error "Flash WIP/WEL set after completed status reader" }
        }
'''
source = source[:start] + status + source[end:]
source = source.replace('read_execution_verified 1', 'native_execution_verified 1 stage $stage kind $kind')
source = source.replace('BOOT NOR read runner failed; suppress outer resume and inspect preserved captures',
    'BOOT admitted native caller failed; suppress subsequent stages/resume and inspect captures')

orchestrator = r'''

# Main test entry. Definitions only: sourcing this file never runs anything.
# Root must first complete the separate read runner in this SAME debug epoch.
proc bnp_test_log {line} { global bnp_test_result; puts $bnp_test_result $line; echo $line }
proc bnp_status_stage {capture_dir phase original_sr1 original_sr2 remove_fpb_command} {
    global bnp_last_sr1 bnp_last_sr2
    bnp_execute_call $capture_dir read read-status 0 $remove_fpb_command
    bnt_verify_status $phase $original_sr1 $original_sr2 $bnp_last_sr1 $bnp_last_sr2
    bnp_test_log [format "verified_status_phase %s SR1%02x SR2%02x" $phase $bnp_last_sr1 $bnp_last_sr2]
}
proc bnp_run_padding_test {capture_dir remove_fpb_command} {
    global bnp_safe_to_resume bnp_padding_restored bnp_flash_mutation_possible bnp_test_result
    global bnp_last_sr1 bnp_last_sr2 bnor_safe_to_resume bnor_reset_seen bnor_track_reset
    set bnp_safe_to_resume 0
    set bnp_padding_restored 0
    set bnp_flash_mutation_possible 0
    if {![info exists bnor_safe_to_resume] || !$bnor_safe_to_resume ||
        ![info exists bnor_reset_seen] || $bnor_reset_seen || ![info exists bnor_track_reset] || !$bnor_track_reset} {
        error "Requires successful independent read runner in the same current debug process/epoch"
    }
    if {[file exists $capture_dir]} { error "New padding capture directory required" }
    file mkdir $capture_dir
    set bnp_test_result [open [file join $capture_dir result.txt] w]
    bnp_test_log "scope FFsector825000/4096B only; one256B page825100 thenerase_restore; optional exact407c BP handling; no mainentry/boot/recovery/factory writes"
    set test_error [catch {
        bnp_execute_call [file join $capture_dir 00-status-before] read read-status 0 $remove_fpb_command
        set original_sr1 $bnp_last_sr1
        set original_sr2 $bnp_last_sr2
        bnt_verify_status before $original_sr1 $original_sr2 $original_sr1 $original_sr2
        set original_bp [expr {($original_sr1|($original_sr2<<8)) & 0x407c}]
        bnp_test_log [format "original_SR1%02x SR2%02x BP%04x" $original_sr1 $original_sr2 $original_bp]
        set original_sector [bnp_words 0x28825000 1024]
        bnt_verify_sector before $original_sector
        dump_image [file join $capture_dir sector-original-live.bin] 0x28825000 4096
        bnp_test_log "whole_sector_live_backup_verified 1"
        if {$original_bp != 0} {
            bnp_execute_call [file join $capture_dir 01-unprotect] onecall unprotect $original_bp $remove_fpb_command
            bnp_status_stage [file join $capture_dir 02-status-unprotected] unprotected $original_sr1 $original_sr2 $remove_fpb_command
        } else { bnp_test_log "original_BP0 protection_writes_omitted 1" }
        bnp_execute_call [file join $capture_dir 03-program] onecall program $original_bp $remove_fpb_command
        set programmed [bnp_words 0x28825000 1024]
        bnt_verify_sector programmed $programmed
        dump_image [file join $capture_dir sector-programmed-live.bin] 0x28825000 4096
        bnp_test_log "whole_sector_programmed_verified 1"
        bnp_status_stage [file join $capture_dir 04-status-programmed] programmed $original_sr1 $original_sr2 $remove_fpb_command
        bnp_execute_call [file join $capture_dir 05-erase-restore] onecall erase_restore $original_bp $remove_fpb_command
        set restored_sector [bnp_words 0x28825000 1024]
        bnt_verify_sector restored $restored_sector
        if {$restored_sector != $original_sector} { error "Whole4K differs from actual original live backup after erase" }
        dump_image [file join $capture_dir sector-restored-live.bin] 0x28825000 4096
        bnp_test_log "whole_sector_restored_verified 1"
        bnp_status_stage [file join $capture_dir 06-status-erased] erased $original_sr1 $original_sr2 $remove_fpb_command
        if {$original_bp != 0} {
            bnp_execute_call [file join $capture_dir 07-reprotect] onecall reprotect $original_bp $remove_fpb_command
        }
        bnp_status_stage [file join $capture_dir 08-status-restored] restored $original_sr1 $original_sr2 $remove_fpb_command
        bnp_execute_call [file join $capture_dir 09-invalidate-I] onecall invalidate_i $original_bp $remove_fpb_command
        bnp_execute_call [file join $capture_dir 10-invalidate-D] onecall invalidate_d $original_bp $remove_fpb_command
        if {[bnp_words 0x28825000 1024] != $original_sector} { error "Whole sector differs after scoped cache calls" }
        bnp_stable_halt
        set final_reset_status [bnp_word 0x400800a4]
        if {$final_reset_status & 0x182} { error "Other CPU reset isolation lost after final cache call" }
        bnp_test_log [format "final_held_reset_aon 0x%08x" $final_reset_status]
        set bnp_padding_restored 1
        set bnp_safe_to_resume 1
        bnp_test_log "padding_and_protection_and_context_restored 1; BOOT remains halted; outer root owns final recovery"
    } test_message]
    if {$test_error} {
        # Do not call erase/reprotect or replay another stage after an uncertain
        # native failure/reset/fault/unclosed SPI. Independent BOOT recovery and
        # durable exact-sector/status captures remain the outer root's choice.
        set bnp_safe_to_resume 0
        bnp_test_log "test_error $test_message"
        bnp_test_log "NO_AUTO_RESUME_OR_NEXT_STAGE; inspect physical sector/protection and caller closure before root recovery"
    }
    bnp_test_log "native_flash_mutation_possible $bnp_flash_mutation_possible padding_restored $bnp_padding_restored safe_to_resume $bnp_safe_to_resume"
    close $bnp_test_result
    if {$test_error} { error "Bounded padding test failed; retain halt and all captures; independent recovery required" }
    return 1
}
'''
source += orchestrator
assert "0x58050314" not in source and "0x58050088" not in source
out = ROOT / "diagnostics/boot-nor-padding-runner.cfg"
out.write_text(source)
review = {"offline_only": True,"cfg":str(out.relative_to(ROOT)),"sha256":hashlib.sha256(out.read_bytes()).hexdigest(),
          "derived_read_runner":str(reader_path.relative_to(ROOT)),"derived_read_runner_sha256":hashlib.sha256(reader_path.read_bytes()).hexdigest(),
          "signature":"bnp_run_padding_test capture_dir remove_fpb_command",
          "executor":"bnp_execute_call capture_dir read|onecall fixed_stage original_bp remove_fpb_command",
          "dependencies":["analysis/persistence/boot-nor-read-runner-data.cfg","diagnostics/boot-nor-padding-stage-inputs.cfg"],
          "status":"Prepared only; not executed on hardware; offline protocol tests pending",
          "watchdog_contract":"Root owns hardware-proved original BOOT AON watchdog stop; every native caller gates CTRL40082008==0 at entry and immediately before CPU run. This library does not unlock/stop/start/feed the watchdog.",
          "watchdog_stop_evidence":"diagnostics/mcu-boot-watchdog-stop-result.txt",
          "native_poll_budget_ms":{"read-status":250,"unprotect":1000,"program":1000,"erase_restore":5000,"reprotect":1000,"invalidate_i":250,"invalidate_d":250},
          "poll_contract":"5ms between nonhalt samples; elapsed-time and timeout/5+2 count bounds; exact BKPT/native closure still mandatory; budgets are not claimed datasheet maxima.",
          "initialized_data_contract":"Only source words3ad0/3ad4 gain proved PMU/sysfreq initialization exceptions. Each caller saves independent8B before/after captures and requires whole two words exactly unchanged.",
          "mutation_contract":"BP0 omits statuswrites. Program one page, verify whole4K, erase exact4K, verify live originalFF, restoreoriginalBPifnonzero with fresh status/QE check; no failure auto-nextstage or resume.",
          "held_reset_gate":"Only AONstatus, no A7 debug domain accesses; A7CPU/WFCPU/BTCPU bits1/7/8 must remain resetasserted"}
(ROOT / "analysis/persistence/boot-nor-padding-runner-review.json").write_text(json.dumps(review,indent=2)+"\n")
print("Prepared definitions-only padding runner and allowlisted native caller; no target access")
