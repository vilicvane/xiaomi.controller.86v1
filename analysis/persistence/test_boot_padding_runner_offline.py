"""Native padding flow simulation in Jim Tcl, strictly no adapter/hardware."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "tools/xpack-openocd-0.12.0-7/bin/openocd.exe"
OUT = ROOT / "analysis/persistence/offline-padding-runner"
OUT.mkdir(exist_ok=True)
source = (ROOT / "analysis/persistence/mock_boot_read_runner.tcl").read_text()
model = source[:source.index('set mock_error [catch {bnor_run_read_probe')]
model = model.replace('source diagnostics/boot-nor-read-runner.cfg', 'source diagnostics/boot-nor-padding-runner.cfg')
model = model.replace('set mock_mode $bnor_mock_mode', 'set mock_mode $padding_mock_mode\nset bnor_safe_to_resume 1\nset bnor_reset_seen 0\nset bnor_track_reset 1')
anchor = 'set mock_saved_regs [array get mock_regs]'
extra = r'''
set mock_mem([expr {0x400800a4}]) 0x24d
set mock_mem([expr {0x40082008}]) 0
if {$mock_mode == "active_watchdog"} { set mock_mem([expr {0x40082008}]) 3 }
set mock_wdt_reads 0
set mock_delay_remaining 0
set mock_delayed_samples 0
if {$mock_mode in {erase_delayed erase_timeout}} {
    # Virtual host time exercises the full timeout without any real wait.
    set mock_virtual_ms 0
    rename clock mock_host_clock
    proc clock {subcommand} {
        if {$subcommand == "milliseconds"} { return $::mock_virtual_ms }
        return [mock_host_clock $subcommand]
    }
    rename sleep mock_host_sleep
    proc sleep {ms} { incr ::mock_virtual_ms $ms }
}
for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28825000+4*$i}]) 0xffffffff }
set mock_sr1 0
set mock_sr2 2
if {$mock_mode == "success_bp"} { set mock_sr1 0x7c }
set mock_original_sr1 $mock_sr1
set mock_original_sr2 $mock_sr2
if {$mock_mode == "sector_not_ff"} { set mock_mem([expr {0x28825ffc}]) 0xfffffffe }
set mock_mutation_calls {}
set mock_calls {}
set mock_after_program 0
set mock_failed_run 0
set mock_stale_replay 0
'''
model = model.replace(anchor, extra + anchor)
model = model.replace('    if {$bits != 32} { error "Mock only supports32bit reads" }',
    '    if {$address >= 0x58000000 && $address < 0x59000000} { error "Forbidden A7 debug-domain access" }\n'
    '    if {$address == 0x40082008} {\n'
    '        incr ::mock_wdt_reads\n'
    '        if {$mock_mode == "watchdog_reenabled" && $::mock_wdt_reads == 2} { set mock_mem([expr {0x40082008}]) 3 }\n'
    '    }\n'
    '    if {$address == 0xe000edf0 && $::mock_delay_remaining > 0} {\n'
    '        incr ::mock_delay_remaining -1\n'
    '        incr ::mock_delayed_samples\n'
    '        return {0x00110009}\n'
    '    }\n'
    '    if {$bits != 32} { error "Mock only supports32bit reads" }')
start = model.index('            if {($value & 15) == 9} {')
end = model.index('        } else { set mock_mem($addr) $value }', start)
native = r'''
            if {($value & 15) == 9} {
                incr mock_exec
                set base $mock_scratch_base
                set callee $mock_mem([expr {$base+128}])
                if {$callee == 0} {
                    lappend ::mock_calls read
                    set mock_mem([expr {$base+128}]) 0
                    set mock_mem([expr {$base+132}]) 1
                    foreach off {136 140 144 148 152} { set mock_mem([expr {$base+$off}]) 0 }
                    set mock_mem([expr {$base+156}]) 0x52454144
                    set mock_mem([expr {$base+160}]) [expr {0x186585 | ($::mock_sr1<<24)}]
                    set mock_mem([expr {$base+164}]) $::mock_sr2
                    set pc_offset 94
                } else {
                    set arg0 $mock_mem([expr {$base+132}])
                    set arg1 $mock_mem([expr {$base+136}])
                    set arg2 $mock_mem([expr {$base+140}])
                    set arg3 $mock_mem([expr {$base+144}])
                    switch [format "0x%08x" $callee] {
                        0x00200fe9 {
                            if {$arg0 != 0 || $arg2 != 0 || $arg3 != 0 || $arg1 & ~0x407c ||
                                ($arg1 != 0 && $arg1 != (($::mock_original_sr1|($::mock_original_sr2<<8))&0x407c))} { error "Bad admitted BP arguments" }
                            lappend ::mock_mutation_calls bp
                            set composite [expr {(($::mock_sr1|($::mock_sr2<<8)) & ~0x407c) | $arg1}]
                            set ::mock_sr1 [expr {$composite&255}]
                            set ::mock_sr2 [expr {($composite>>8)&255}]
                        }
                        0x00201249 {
                            if {$arg0 != 0 || $arg1 != 0x28825100 || $arg2 != $base+256 || $arg3 != 256} { error "Bad admitted page program arguments" }
                            lappend ::mock_mutation_calls program
                            for {set j 0} {$j < 64} {incr j} {
                                set mock_mem([expr {$arg1+4*$j}]) [expr {$mock_mem([expr {$arg1+4*$j}]) & $mock_mem([expr {$arg2+4*$j}])}]
                            }
                            set ::mock_after_program 1
                            if {$mock_mode == "programmed_mismatch"} { set mock_mem([expr {0x28825ffc}]) 0xfffffffe }
                        }
                        0x00201105 {
                            if {$arg0 != 0 || $arg1 != 0x28825000 || $arg2 != 4096 || $arg3 != 0} { error "Bad admitted sector erase arguments" }
                            lappend ::mock_mutation_calls erase
                            for {set j 0} {$j < 1024} {incr j} { set mock_mem([expr {$arg1+4*$j}]) 0xffffffff }
                            if {$mock_mode == "erase_delayed"} { set ::mock_delay_remaining 60 }
                            if {$mock_mode == "erase_timeout"} { set ::mock_delay_remaining 2000; set ::mock_failed_run 1 }
                        }
                        0x00202fb5 {
                            if {$arg0 > 1 || $arg1 != 0x2c825000 || $arg2 != 4096 || $arg3 != 0} { error "Bad admitted cache arguments" }
                        }
                        default { error "Arbitrary callee not admitted" }
                    }
                    lappend ::mock_calls [format "native_%08x" $callee]
                    set mock_mem([expr {$base+148}]) 0
                    set mock_mem([expr {$base+152}]) 1
                    set mock_mem([expr {$base+156}]) 0
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
                # Exercise maximum caller stack spill and full borrowed restore.
                for {set j 198} {$j < 256} {incr j} { set mock_mem([expr {$base+4*$j}]) [expr {0xbb000000+$j}] }
                if {$::mock_after_program && $mock_mode == "reset_program"} { set mock_mem($addr) 0x0213000b; set ::mock_failed_run 1 }
                if {$::mock_after_program && $mock_mode == "fault_program"} { set mock_mem([expr {0xe000ed28}]) 1; set mock_regs(16) 0x01000003; set ::mock_failed_run 1 }
                if {$mock_mode == "initialized_config_changed"} { set mock_mem([expr {0x20003ad4}]) 0x00001605 }
            }
'''
model = model[:start] + native + model[end:]
model = model.replace('    set i 0\n    foreach value $values {',
    '    if {$::mock_failed_run && ($address == $mock_scratch_base || $address == 0x20003b80)} { set ::mock_stale_replay 1; error "Stale replay after unsafe native run" }\n'
    '    if {$::mock_failed_run && $address == 0xe000edf4 && ([lindex $values 0]&0x10000)} { set ::mock_stale_replay 1; error "Stale core replay after unsafe native run" }\n'
    '    set i 0\n    foreach value $values {')
model = model.replace('if {$address < 0x20000000 || $address >= 0x20100000}',
    'if {!(($address >= 0x20000000 && $address < 0x20100000) || ($address == 0x28825000 && $size == 4096))}')
checks = r'''
set mock_error [catch {bnp_run_padding_test $padding_mock_output mock_remove_fpb} mock_message]
if {$mock_mode in {success_bp0 success_bp erase_delayed}} {
    if {$mock_error || !$bnp_safe_to_resume || !$bnp_padding_restored || !$bnp_flash_mutation_possible} { error "Padding success failed: $mock_message" }
    for {set i 0} {$i < 1024} {incr i} {
        if {$mock_mem([expr {0x28825000+4*$i}]) != 0xffffffff} { error "Whole original sector not restored" }
    }
    if {$mock_sr1 != $mock_original_sr1 || $mock_sr2 != $mock_original_sr2} { error "Exact stable status/QE not restored" }
    array set wanted $mock_saved_regs
    foreach sel [array names wanted] { if {$mock_regs($sel) != $wanted($sel)} { error "Core restore mismatch $sel" } }
    for {set i 0} {$i < 256} {incr i} { if {$mock_mem([expr {$mock_scratch_base+4*$i}]) != 0xab000000+$i} { error "Whole borrowed RAM not restored" } }
    if {$mock_mem([expr {0xe000edf8}]) != 0x11223344 || ($mock_mem([expr {0xe000edf0}])&15) != 3} { error "Debug context not restored" }
    if {$mock_mode == "success_bp0" && $mock_mutation_calls != {program erase}} { error "BP0 caused unwanted status writes" }
    if {$mock_mode == "success_bp" && $mock_mutation_calls != {bp program erase bp}} { error "Protection handling/order incorrect" }
    if {$mock_mode == "erase_delayed" && ($mock_mutation_calls != {program erase} || $mock_delayed_samples != 60 || $mock_virtual_ms < 300)} { error "Longer erase budget not exercised" }
    if {$mock_wdt_reads != 2*$mock_exec} { error "Every caller must gate WDT at entry and immediately before run" }
} elseif {$mock_mode in {active_watchdog watchdog_reenabled}} {
    if {!$mock_error || $bnp_safe_to_resume || $bnp_flash_mutation_possible || [llength $mock_mutation_calls] || $mock_exec} { error "Active watchdog did not block all native execution/NOR mutation" }
    if {$mock_mode == "active_watchdog" && $mock_wdt_reads != 1} { error "Entry watchdog rejection missed" }
    if {$mock_mode == "watchdog_reenabled" && $mock_wdt_reads != 2} { error "Pre-run watchdog recheck missed" }
    array set wanted $mock_saved_regs
    foreach sel [array names wanted] { if {$mock_regs($sel) != $wanted($sel)} { error "Watchdog refusal core restore mismatch $sel" } }
    for {set i 0} {$i < 256} {incr i} { if {$mock_mem([expr {$mock_scratch_base+4*$i}]) != 0xab000000+$i} { error "Watchdog refusal changed borrowed RAM" } }
    if {$mock_mem([expr {0xe000edf8}]) != 0x11223344 || ($mock_mem([expr {0xe000edf0}])&15) != 3} { error "Watchdog refusal debug context restore failed" }
} elseif {$mock_mode == "initialized_config_changed"} {
    if {!$mock_error || $bnp_safe_to_resume || $bnp_flash_mutation_possible || $mock_exec != 1 || [llength $mock_mutation_calls]} { error "PMU/sysfreq change did not stop before NOR mutation" }
    if {![file exists [file join $padding_mock_output 00-status-before boot-initialized-config-before.bin]] ||
        ![file exists [file join $padding_mock_output 00-status-before boot-initialized-config-after.bin]]} { error "Independent initialized-data evidence captures missing" }
} elseif {$mock_mode == "sector_not_ff"} {
    if {!$mock_error || $bnp_safe_to_resume || $bnp_flash_mutation_possible || [llength $mock_mutation_calls]} { error "NonFF live sector did not refuse all NOR mutations" }
} elseif {$mock_mode in {reset_program fault_program erase_timeout}} {
    if {!$mock_error || $bnp_safe_to_resume || $bnp_padding_restored || !$mock_failed_run || $mock_stale_replay} { error "Unsafe native run did not stop without replay" }
    if {$mock_regs(15) == 0x0c0104c6 || $mock_mem($mock_scratch_base) == 0xab000000} { error "Stale original core/RAM replay occurred" }
    if {$mock_mode == "erase_timeout"} {
        if {$mock_mutation_calls != {program erase} || $mock_virtual_ms != 5000 || $mock_delayed_samples < 1001} { error "Erase timeout not bounded to reviewed 5000ms or followed by extra stage" }
    } elseif {$mock_mutation_calls != {program}} { error "Unsafe program followed by another mutating stage" }
} elseif {$mock_mode == "programmed_mismatch"} {
    if {!$mock_error || $bnp_safe_to_resume || $bnp_padding_restored || $mock_mutation_calls != {program}} { error "Whole-sector mismatch did not stop before erase/nextstage" }
} else { error "Unknown focused padding mode" }
set f [open [file join $padding_mock_output mock-summary.txt] w]
foreach name {mode error message mutation_calls calls exec stale_replay wdt_reads delayed_samples} { puts $f "$name [set mock_$name]" }
puts $f "safe_to_resume $bnp_safe_to_resume"
puts $f "padding_restored $bnp_padding_restored"
puts $f "mutation_possible $bnp_flash_mutation_possible"
close $f
echo "MOCK_ONLY_PASS $mock_mode"
shutdown
'''
cases = ["success_bp0", "success_bp", "sector_not_ff", "reset_program", "fault_program", "programmed_mismatch",
         "active_watchdog", "watchdog_reenabled", "initialized_config_changed", "erase_delayed", "erase_timeout"]
reports = []
for case in cases:
    case_dir = OUT / case
    if case_dir.exists():
        # Never discard prior mock evidence. Select a new invocation directory.
        index = 2
        while (OUT / f"{case}-{index}").exists(): index += 1
        case_dir = OUT / f"{case}-{index}"
    harness = OUT / f"{case}-harness.cfg"
    prefix = f"set padding_mock_mode {{{case}}}\nset bnor_mock_mode {{{case}}}\nset padding_mock_output {{{case_dir.as_posix()}}}\n"
    harness.write_text(prefix+model+checks)
    run = subprocess.run([str(EXE), "-f", str(harness)], cwd=ROOT, capture_output=True, text=True, timeout=20)
    (OUT / f"{case}-host.txt").write_text(run.stdout+run.stderr)
    if "MOCK_ONLY_PASS " + case not in run.stdout+run.stderr:
        raise RuntimeError(f"Padding offline mock failed:{case}; inspect local host output")
    reports.append({"case":case,"passed":True,"evidence":str((case_dir / "mock-summary.txt").relative_to(ROOT))})
(OUT / "summary.json").write_text(json.dumps({"scope":"Offline mock only, no adapter/init/target connection", "cases":reports},indent=2)+"\n")
print(f"Focused padding runner offline scenarios passed:{len(reports)}; no target access")
