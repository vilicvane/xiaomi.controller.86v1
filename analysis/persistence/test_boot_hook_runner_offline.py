"""Independent fixed-hook Jim model. No adapter, init, or target connection.

Only reads source and immutable binary fixtures; creates this task's new mock
outputs. Native callees are simulated from actual r0..r3 and scratch contents,
not by replacing the runner's stage/orchestration procedures.
"""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "tools/xpack-openocd-0.12.0-7/bin/openocd.exe"
OUT = ROOT / "analysis/persistence/offline-hook-runner"
OUT.mkdir(exist_ok=True)
run_index = 1
while (OUT / f"run-{run_index}").exists():
    run_index += 1
RUN = OUT / f"run-{run_index}"
RUN.mkdir()

def wordlist(data):
    return " ".join(map(str, struct.unpack("<" + "I" * (len(data) // 4), data)))

fixture = {}
seed = []
for label, offset in [("entry", 0x150000), ("payload", 0x824000)]:
    for state in ["original", "patched"]:
        path = ROOT / f"analysis/persistence/boot-hook-{state}-sector-{offset:x}.bin"
        data = path.read_bytes()
        assert len(data) == 4096
        fixture[label, state] = data
        seed.append(f"set mock_{label}_{state} {{{wordlist(data)}}}")
stub = (ROOT / "analysis/persistence/boot-hook-1.50.10.bin").read_bytes()
assert len(stub) == 32
assert fixture["payload", "original"][0x400:0x500] == b"\xff" * 256
assert fixture["payload", "patched"][0x400:0x500] == stub + b"\xff" * 224
assert all((a & b) == b for a, b in zip(fixture["payload", "original"], fixture["payload", "patched"]))

source = (ROOT / "analysis/persistence/mock_boot_read_runner.tcl").read_text()
model = source[:source.index("set mock_error [catch {bnor_run_read_probe")]
model = model.replace("source diagnostics/boot-nor-read-runner.cfg", "source diagnostics/boot-nor-hook-runner.cfg")
model = model.replace("set mock_mode $bnor_mock_mode", "set mock_mode $hook_mock_mode\nset bnor_safe_to_resume 1\nset bnor_reset_seen 0\nset bnor_track_reset 1")
extra = "\n".join(seed) + r'''
foreach {name wanted} [list bhi_entry_original_words $mock_entry_original bhi_entry_patched_words $mock_entry_patched bhi_payload_original_words $mock_payload_original bhi_payload_patched_words $mock_payload_patched] {
    set normalized {}
    foreach number [set $name] { lappend normalized [expr {$number+0}] }
    if {$normalized != $wanted} { error "Runner fixture differs from independent raw binary $name" }
}
set mock_flow install
if {[string match "restore_*" $mock_mode]} { set mock_flow restore }
set mock_seed_state original
if {$mock_flow == "restore"} { set mock_seed_state patched }
foreach {label address} {entry 0x28150000 payload 0x28824000} {
    set wanted [set mock_${label}_${mock_seed_state}]
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {$address+4*$i}]) [lindex $wanted $i] }
}
set mock_mem([expr {0x400800a4}]) 0x24d
set mock_mem([expr {0x40082008}]) 0
set mock_sr1 0
set mock_sr2 2
if {[string match "*bp7c" $mock_mode]} { set mock_sr1 0x7c }
set mock_original_sr1 $mock_sr1
set mock_original_sr2 $mock_sr2
set mock_wdt_reads 0
set mock_mutation_calls {}
set mock_calls {}
set mock_order {}
set mock_payload_programmed 0
set mock_entry_erased 0
set mock_payload_erased 0
set mock_payload_verified 0
set mock_entry_restored_verified 0
set mock_failed_run 0
set mock_stale_replay 0
set mock_delay_remaining 0
set mock_delayed_samples 0
set mock_virtual_ms 0
if {$mock_mode == "active_watchdog"} { set mock_mem([expr {0x40082008}]) 3 }
if {$mock_mode == "baseline_entry_mismatch"} { set mock_mem([expr {0x28150ffc}]) [expr {$mock_mem([expr {0x28150ffc}]) ^ 1}] }
if {$mock_mode == "baseline_payload_mismatch"} { set mock_mem([expr {0x28824ffc}]) 0xfffffffe }
if {$mock_mode == "partial_entry_fixed_restore"} {
    set mock_flow partial
    set mock_sr1 0x7c
    set mock_original_sr1 $mock_sr1
    for {set i 0} {$i < 128} {incr i} { set mock_mem([expr {0x28150000+4*$i}]) 0xffffffff }
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28824000+4*$i}]) [lindex $mock_payload_patched $i] }
}
rename clock mock_host_clock
proc clock {subcommand} {
    if {$subcommand == "milliseconds"} { return $::mock_virtual_ms }
    return [mock_host_clock $subcommand]
}
rename sleep mock_host_sleep
proc sleep {ms} { incr ::mock_virtual_ms $ms }
'''
model = model.replace("set mock_saved_regs [array get mock_regs]", extra + "\nset mock_saved_regs [array get mock_regs]")
model = model.replace('    if {$bits != 32} { error "Mock only supports32bit reads" }', r'''
    if {$address >= 0x58000000 && $address < 0x59000000} { error "Forbidden APDBG read" }
    if {$address == 0x40082008} {
        incr ::mock_wdt_reads
        if {$mock_mode == "watchdog_reenabled" && $::mock_wdt_reads == 3} { set mock_mem([expr {0x40082008}]) 3 }
    }
    if {$address == 0xe000edf0 && $::mock_delay_remaining > 0} {
        incr ::mock_delay_remaining -1
        incr ::mock_delayed_samples
        return {0x00110009}
    }
    if {$bits != 32} { error "Mock only supports32bit reads" }
''')
model = model.replace("    return $result\n}", r'''
    if {$count == 1024 && $address == 0x28824000 && $::mock_payload_programmed && $result == $::mock_payload_patched} {
        set ::mock_payload_verified 1
        lappend ::mock_order verify_payload_4k
    }
    if {$count == 1024 && $address == 0x28150000 && $::mock_entry_erased && $result == $::mock_entry_original} {
        set ::mock_entry_restored_verified 1
        lappend ::mock_order verify_original_entry_4k
    }
    return $result
}''', 1)
start = model.index("            if {($value & 15) == 9} {")
end = model.index("        } else { set mock_mem($addr) $value }", start)
native = r'''
            if {($value & 15) == 9} {
                incr mock_exec
                set base $mock_scratch_base
                set callee $mock_mem([expr {$base+128}])
                set ret 0
                if {$callee == 0} {
                    lappend ::mock_calls read
                    lappend ::mock_order status_read
                    set mock_mem([expr {$base+128}]) 0
                    set mock_mem([expr {$base+132}]) 1
                    foreach off {136 140 144 148 152} { set mock_mem([expr {$base+$off}]) 0 }
                    set mock_mem([expr {$base+156}]) 0x52454144
                    set mock_mem([expr {$base+160}]) [expr {0x186585 | ($::mock_sr1<<24)}]
                    set mock_mem([expr {$base+164}]) $::mock_sr2
                    set pc_offset 94
                    if {$mock_mode == "read_timeout"} { set ::mock_delay_remaining 100; set ::mock_failed_run 1 }
                } else {
                    set arg0 $mock_mem([expr {$base+132}])
                    set arg1 $mock_mem([expr {$base+136}])
                    set arg2 $mock_mem([expr {$base+140}])
                    set arg3 $mock_mem([expr {$base+144}])
                    switch [format "0x%08x" $callee] {
                        0x00200fe9 {
                            if {$arg0 != 0 || $arg2 != 0 || $arg3 != 0 || $arg1 & ~0x407c ||
                                ($arg1 != 0 && $arg1 != (($::mock_original_sr1|($::mock_original_sr2<<8))&0x407c))} { error "Bad admitted BP arguments" }
                            set tag unprotect
                            if {$arg1 != 0} { set tag reprotect }
                            lappend ::mock_mutation_calls $tag
                            set composite [expr {(($::mock_sr1|($::mock_sr2<<8)) & ~0x407c) | $arg1}]
                            set ::mock_sr1 [expr {$composite&255}]
                            set ::mock_sr2 [expr {($composite>>8)&255}]
                        }
                        0x00201249 {
                            if {$arg0 != 0 || $arg2 != $base+256 || $arg3 != 256 || $arg1 & 255} { error "Bad admitted page ABI" }
                            if {($::mock_sr1|($::mock_sr2<<8))&0x407c} { error "NOR program while protected" }
                            if {$arg1 >= 0x28150000 && $arg1 < 0x28151000} {
                                if {!$::mock_entry_erased} { error "Entry programmed without erase" }
                                set page [expr {($arg1-0x28150000)/256}]
                                if {$::mock_flow == "install"} { set wanted $::mock_entry_patched } else { set wanted $::mock_entry_original }
                                set expected [lrange $wanted [expr {$page*64}] [expr {$page*64+63}]]
                                set tag program_entry_$page
                            } elseif {$arg1 == 0x28824400 && $::mock_flow == "install"} {
                                if {$::mock_payload_programmed || $::mock_entry_erased} { error "Payload installation order invalid" }
                                set expected [lrange $::mock_payload_patched 256 319]
                                set tag program_payload_hook
                            } elseif {$arg1 >= 0x28824000 && $arg1 < 0x28825000 && $::mock_flow == "restore"} {
                                if {!$::mock_payload_erased || !$::mock_entry_restored_verified} { error "Payload restore before exact original entry" }
                                set page [expr {($arg1-0x28824000)/256}]
                                if {$page > 3} { error "Unwanted FF payload page program" }
                                set expected [lrange $::mock_payload_original [expr {$page*64}] [expr {$page*64+63}]]
                                set tag program_payload_$page
                            } else { error "Arbitrary NOR program address" }
                            set actual {}
                            for {set j 0} {$j < 64} {incr j} { lappend actual $mock_mem([expr {$arg2+4*$j}]) }
                            if {$actual != $expected} { error "Native scratch payload differs from independent exact binary page" }
                            lappend ::mock_mutation_calls $tag
                            for {set j 0} {$j < 64} {incr j} {
                                set old $mock_mem([expr {$arg1+4*$j}])
                                set new [lindex $expected $j]
                                if {($old & $new) != $new} { error "NOR 0-to-1 program without erase" }
                                set mock_mem([expr {$arg1+4*$j}]) [expr {$old & $new}]
                            }
                            if {$tag == "program_payload_hook"} {
                                set ::mock_payload_programmed 1
                                if {$mock_mode == "payload_whole_readback_mismatch"} { set mock_mem([expr {0x28824ffc}]) 0xfffffffe }
                                if {$mock_mode == "native_error_payload"} { set ret 7; set ::mock_failed_run 1 }
                                if {$mock_mode == "qe_changed_payload"} { set ::mock_sr2 0 }
                                if {$mock_mode == "program_timeout"} { set ::mock_delay_remaining 400; set ::mock_failed_run 1 }
                            }
                        }
                        0x00201105 {
                            if {$arg0 != 0 || $arg2 != 4096 || $arg3 != 0 || $arg1 & 4095} { error "Bad admitted erase ABI" }
                            if {($::mock_sr1|($::mock_sr2<<8))&0x407c} { error "NOR erase while protected" }
                            if {$arg1 == 0x28150000} {
                                if {$::mock_flow == "install" && !$::mock_payload_verified} { error "Entry erased before exact whole payload readback" }
                                if {$::mock_entry_erased} { error "Repeated entry erase" }
                                set ::mock_entry_erased 1
                                set tag erase_entry
                            } elseif {$arg1 == 0x28824000 && $::mock_flow == "restore"} {
                                if {!$::mock_entry_restored_verified || $::mock_payload_erased} { error "Payload erased before original entry whole readback" }
                                set ::mock_payload_erased 1
                                set tag erase_payload
                            } else { error "Arbitrary NOR erase address" }
                            lappend ::mock_mutation_calls $tag
                            for {set j 0} {$j < 1024} {incr j} { set mock_mem([expr {$arg1+4*$j}]) 0xffffffff }
                            if {$mock_mode == "erase_delayed"} { set ::mock_delay_remaining 60 }
                            if {$mock_mode == "erase_timeout"} { set ::mock_delay_remaining 2000; set ::mock_failed_run 1 }
                        }
                        0x00202fb5 {
                            if {$arg0 < 0 || $arg0 > 1 || ($arg1 != 0x2c150000 && $arg1 != 0x2c824000) || $arg2 != 4096 || $arg3 != 0} { error "Bad scoped cache ABI" }
                            set tag [format "invalidate_%08x_%d" $arg1 $arg0]
                        }
                        default { error "Arbitrary callee not admitted" }
                    }
                    lappend ::mock_calls $tag
                    lappend ::mock_order $tag
                    set mock_mem([expr {$base+148}]) 0
                    set mock_mem([expr {$base+152}]) 1
                    set mock_mem([expr {$base+156}]) $ret
                    set mock_mem([expr {$base+160}]) 0x43414c4c
                    set pc_offset 46
                }
                set mock_mem([expr {0x20003b80}]) 0
                set mock_regs(15) [expr {$base-0x1fe00000+$pc_offset}]
                foreach sel {0 1 2 3 4 5 7 14} { set mock_regs($sel) [expr {0x200000+$sel}] }
                set mock_regs(20) 1
                set mock_regs(34) 1
                set mock_mem($addr) 0x0013000b
                set mock_mem([expr {0xe000ed30}]) 2
                for {set j 198} {$j < 256} {incr j} { set mock_mem([expr {$base+4*$j}]) [expr {0xbb000000+$j}] }
                if {$::mock_payload_programmed && $mock_mode == "reset_payload"} { set mock_mem($addr) 0x0213000b; set ::mock_failed_run 1 }
                if {$::mock_payload_programmed && $mock_mode == "fault_payload"} { set mock_mem([expr {0xe000ed28}]) 1; set mock_regs(16) 0x01000003; set ::mock_failed_run 1 }
                if {$mock_mode == "initialized_config_changed"} { set mock_mem([expr {0x20003ad4}]) 0x00001605 }
            }
'''
model = model[:start] + native + model[end:]
model = model.replace("    set i 0\n    foreach value $values {", r'''
    if {$::mock_failed_run && ($address == $mock_scratch_base || $address == 0x20003b80)} { set ::mock_stale_replay 1; error "Stale RAM/lock replay after unsafe native run" }
    if {$::mock_failed_run && $address == 0xe000edf4 && ([lindex $values 0]&0x10000)} { set ::mock_stale_replay 1; error "Stale core replay after unsafe native run" }
    if {$address >= 0x58000000 && $address < 0x59000000} { error "Forbidden APDBG write" }
    if {$address >= 0x40140000 && $address < 0x40141000} { error "Forbidden secondary SPI write" }
    set i 0
    foreach value $values {''')
model = model.replace("if {$address < 0x20000000 || $address >= 0x20100000}",
    "if {!(($address >= 0x20000000 && $address < 0x20100000) || ($address in {0x28150000 0x28824000} && $size == 4096))}")

checks = r'''
proc mock_assert_original_context {} {
    global mock_saved_regs mock_regs mock_mem mock_scratch_base
    array set wanted $mock_saved_regs
    foreach sel [array names wanted] { if {$mock_regs($sel) != $wanted($sel)} { error "Core restore mismatch $sel" } }
    for {set i 0} {$i < 256} {incr i} { if {$mock_mem([expr {$mock_scratch_base+4*$i}]) != 0xab000000+$i} { error "Whole 1024B borrowed RAM not restored" } }
    if {$mock_mem([expr {0xe000edf8}]) != 0x11223344 || ($mock_mem([expr {0xe000edf0}])&15) != 3} { error "Original DCRDR/halted controls not restored" }
}
proc mock_partial_restore {} {
    global hook_mock_output mock_original_sr1 mock_original_sr2 bnh_last_sr1 bnh_last_sr2 bhi_entry_original_words bnh_hook_result
    file mkdir $hook_mock_output
    set bnh_hook_result [open [file join $hook_mock_output supervised-result.txt] w]
    set bp [expr {($mock_original_sr1|($mock_original_sr2<<8))&0x407c}]
    bnh_execute_call [file join $hook_mock_output status-before] read read-status 0 mock_remove_fpb
    bhi_verify_status original $mock_original_sr1 $mock_original_sr2 $bnh_last_sr1 $bnh_last_sr2
    bnh_execute_call [file join $hook_mock_output unprotect] onecall unprotect $bp mock_remove_fpb
    bnh_status_stage [file join $hook_mock_output status-unprotected] unprotected $mock_original_sr1 $mock_original_sr2 mock_remove_fpb
    bnh_write_sector $hook_mock_output restore-entry $bhi_entry_original_words $bp mock_remove_fpb
    bnh_verify_sector $hook_mock_output entry $bhi_entry_original_words
    bnh_execute_call [file join $hook_mock_output reprotect] onecall reprotect $bp mock_remove_fpb
    bnh_status_stage [file join $hook_mock_output status-restored] original $mock_original_sr1 $mock_original_sr2 mock_remove_fpb
    foreach cache {i d} { bnh_execute_call [file join $hook_mock_output invalidate-entry-$cache] onecall invalidate-entry-$cache $bp mock_remove_fpb }
    close $bnh_hook_result
}
if {$mock_mode == "arbitrary_mode"} {
    set mock_error [catch {bnh_run_hook $hook_mock_output program mock_remove_fpb} mock_message]
} elseif {$mock_mode == "arbitrary_stage"} {
    file mkdir $hook_mock_output
    set mock_error [catch {bnh_execute_call [file join $hook_mock_output refused] onecall arbitrary-28825100 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "arbitrary_helper_prefix"} {
    set mock_error [catch {bnh_write_sector $hook_mock_output arbitrary-28825100 $bhi_entry_original_words 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "arbitrary_helper_words"} {
    set wrong [lreplace $bhi_entry_original_words 0 0 0xffffffff]
    set mock_error [catch {bnh_write_sector $hook_mock_output restore-entry $wrong 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "partial_entry_fixed_restore"} {
    set mock_error [catch {mock_partial_restore} mock_message]
} else {
    set mock_error [catch {bnh_run_hook $hook_mock_output $mock_flow mock_remove_fpb} mock_message]
}
set mock_operation_log ""
if {[file exists [file join $hook_mock_output result.txt]]} {
    set f [open [file join $hook_mock_output result.txt] r]
    set mock_operation_log [read $f]
    close $f
}
set mock_success [expr {$mock_mode in {install_bp0 install_bp7c restore_bp0 restore_bp7c erase_delayed partial_entry_fixed_restore}}]
if {$mock_success} {
    if {$mock_error || !$bnh_safe_to_resume || !$bnh_flash_mutation_possible} { error "Fixed hook success failed: $mock_message" }
    mock_assert_original_context
    if {$mock_sr1 != $mock_original_sr1 || $mock_sr2 != $mock_original_sr2} { error "BP/QE/full stable status not restored" }
    if {$mock_flow == "install"} {
        set final_entry $mock_entry_patched; set final_payload $mock_payload_patched
        set expected_mutations {program_payload_hook erase_entry}
    } else {
        set final_entry $mock_entry_original; set final_payload $mock_payload_original
        if {$mock_flow == "partial"} { set final_payload $mock_payload_patched }
        set expected_mutations {erase_entry}
    }
    for {set page 0} {$page < 16} {incr page} { lappend expected_mutations program_entry_$page }
    if {$mock_flow == "restore"} { lappend expected_mutations erase_payload; for {set page 0} {$page < 4} {incr page} { lappend expected_mutations program_payload_$page } }
    if {$mock_original_sr1 & 0x7c} { set expected_mutations [concat unprotect $expected_mutations reprotect] }
    if {$mock_mutation_calls != $expected_mutations} { error "Mutation order/count differs: $mock_mutation_calls" }
    foreach {address wanted} [list 0x28150000 $final_entry 0x28824000 $final_payload] {
        set got {}
        for {set i 0} {$i < 1024} {incr i} { lappend got [expr {$mock_mem([expr {$address+4*$i}])+0}] }
        if {$got != $wanted} {
            for {set j 0} {$j < 1024} {incr j} {
                if {[lindex $got $j] != [lindex $wanted $j]} { error [format "Independent sector %08x word %d got=%s wanted=%s" $address $j [lindex $got $j] [lindex $wanted $j]] }
            }
            error "Independent whole sector string representation differs despite identical numeric words"
        }
    }
    if {$mock_flow != "partial" && !$bnh_hook_complete} { error "Final complete flag missing" }
    if {$mock_mode == "erase_delayed" && ($mock_delayed_samples != 60 || $mock_virtual_ms < 300)} { error "5000ms erase budget failed slow success" }
} else {
    if {!$mock_error || $bnh_safe_to_resume || $bnh_hook_complete} { error "Failure did not leave operation unsafe/incomplete: $mock_message" }
    if {$mock_mode in {baseline_entry_mismatch baseline_payload_mismatch active_watchdog watchdog_reenabled arbitrary_mode arbitrary_stage arbitrary_helper_prefix arbitrary_helper_words}} {
        if {$mock_exec || [llength $mock_mutation_calls] || $bnh_flash_mutation_possible} { error "Refusal allowed native execution/mutation: $mock_calls" }
        mock_assert_original_context
        if {$mock_mode in {baseline_entry_mismatch baseline_payload_mismatch} && (![string match "*exact original sector baselines*" $mock_operation_log] || $mock_wdt_reads != 1)} { error "Wrong baseline refusal gate" }
        if {$mock_mode == "active_watchdog" && (![string match "*Outer verified native AON watchdog stop required*" $mock_operation_log] || $mock_wdt_reads != 1)} { error "Wrong active watchdog refusal gate" }
        if {$mock_mode == "watchdog_reenabled" && $mock_wdt_reads != 3} { error "Watchdog did not reject immediately before native execution" }
    } elseif {$mock_mode in {reset_payload fault_payload native_error_payload}} {
        if {$mock_mutation_calls != {program_payload_hook} || !$mock_failed_run || $mock_stale_replay || !$bnh_flash_mutation_possible} { error "Unclosed payload run followed by mutation or stale replay" }
        if {$mock_regs(15) == 0x0c0104c6 || $mock_mem($mock_scratch_base) == 0xab000000} { error "Stale PC/scratch was replayed" }
    } elseif {$mock_mode == "erase_timeout"} {
        if {$mock_mutation_calls != {program_payload_hook erase_entry} || !$mock_failed_run || $mock_stale_replay || $mock_virtual_ms != 5000 || $mock_delayed_samples < 1001} { error "Erase timeout unsafe or not bounded to 5000ms" }
    } elseif {$mock_mode == "program_timeout"} {
        if {$mock_mutation_calls != {program_payload_hook} || !$mock_failed_run || $mock_stale_replay || $mock_virtual_ms != 1000 || $mock_delayed_samples < 201} { error "Program timeout unsafe or not bounded to 1000ms" }
    } elseif {$mock_mode == "read_timeout"} {
        if {[llength $mock_mutation_calls] || !$mock_failed_run || $mock_stale_replay || $mock_virtual_ms != 250 || $mock_delayed_samples < 51} { error "Read timeout unsafe or not bounded to 250ms" }
    } elseif {$mock_mode in {payload_whole_readback_mismatch qe_changed_payload}} {
        if {$mock_mutation_calls != {program_payload_hook} || !$bnh_flash_mutation_possible} { error "Payload readback/QE mismatch allowed entry erase" }
        mock_assert_original_context
    } elseif {$mock_mode == "initialized_config_changed"} {
        if {$mock_exec != 1 || [llength $mock_mutation_calls] || $bnh_flash_mutation_possible} { error "Initialized data drift did not stop before NOR mutation" }
        mock_assert_original_context
    } else { error "Unknown mock case" }
}
if {$mock_apdbg_reads != 0} { error "A7 isolation violated" }
if {![file exists $hook_mock_output]} { file mkdir $hook_mock_output }
set f [open [file join $hook_mock_output mock-summary.txt] w]
foreach name {mode error message mutation_calls calls order exec stale_replay wdt_reads delayed_samples virtual_ms} { puts $f "$name [set mock_$name]" }
puts $f "safe_to_resume $bnh_safe_to_resume"
puts $f "complete $bnh_hook_complete"
puts $f "mutation_possible $bnh_flash_mutation_possible"
close $f
echo "MOCK_ONLY_PASS $mock_mode"
shutdown
'''

cases = ["install_bp0", "install_bp7c", "restore_bp0", "restore_bp7c", "baseline_entry_mismatch", "baseline_payload_mismatch",
         "reset_payload", "fault_payload", "native_error_payload", "payload_whole_readback_mismatch", "qe_changed_payload",
         "active_watchdog", "watchdog_reenabled", "initialized_config_changed", "erase_delayed", "erase_timeout", "program_timeout", "read_timeout",
         "arbitrary_mode", "arbitrary_stage", "arbitrary_helper_prefix", "arbitrary_helper_words", "partial_entry_fixed_restore"]
hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
          [ROOT / "diagnostics/boot-nor-hook-runner.cfg", ROOT / "diagnostics/boot-nor-hook-stage-inputs.cfg"]}

def run_case(case):
    case_dir = RUN / case
    harness = RUN / f"{case}-harness.cfg"
    prefix = f"set hook_mock_mode {{{case}}}\nset hook_mock_output {{{case_dir.as_posix()}}}\n"
    # These commands can never reach a real target even if a reviewed library regresses.
    prefix += 'foreach dangerous {init adapter reset halt resume load_image flash} {\n    if {[llength [info commands $dangerous]]} { rename $dangerous mock_real_$dangerous }\n    proc $dangerous args { error "Hardware/API use forbidden in offline mock" }\n}\n'
    harness.write_text(prefix + model + checks, encoding="utf-8")
    result = subprocess.run([str(EXE), "-f", str(harness)], cwd=ROOT, capture_output=True, text=True, timeout=30)
    log = result.stdout + result.stderr
    (RUN / f"{case}-host.txt").write_text(log, encoding="utf-8")
    passed = f"MOCK_ONLY_PASS {case}" in log
    return {"case": case, "passed": passed, "evidence": str((case_dir / "mock-summary.txt").relative_to(ROOT)),
            "host_log": str((RUN / f"{case}-host.txt").relative_to(ROOT))}

with ThreadPoolExecutor(max_workers=4) as pool:
    reports = list(pool.map(run_case, cases))
summary = {"scope": "Offline Jim mocks only; no adapter/init/target connection, no device memory access", "source_sha256": hashes,
           "independent_sector_sha256": {f"{label}_{state}": hashlib.sha256(data).hexdigest() for (label, state), data in fixture.items()},
           "cases": reports, "all_passed": all(r["passed"] for r in reports),
           "limits": ["Native ARM instruction execution is simulated, not CPU-emulated", "Cold boot acceptance and physical recovery are not demonstrated by this test",
                      "Partial entry uses fixed supervised helper after model fresh-reader/controller provenance, not expanded public mode"]}
(RUN / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
(OUT / "latest-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
failed = [r["case"] for r in reports if not r["passed"]]
print(f"Fixed hook offline mocks: {len(reports) - len(failed)}/{len(reports)} passed; output={RUN.relative_to(ROOT)}")
if failed:
    raise RuntimeError("Failed cases: " + ", ".join(failed))
