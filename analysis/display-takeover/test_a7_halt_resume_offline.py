"""Exercise the real Jim Tcl parser with all target/adapter commands replaced.

The harness never loads a real adapter/target configuration and never calls the
real init/adapter/read_memory/write_memory commands. Failures model committed
target writes, pending HRQ, reset, and lock restoration, rather than silicon.
"""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "tools/xpack-openocd-0.12.0-7/bin/openocd.exe"
CFG = ROOT / "diagnostics/a7-halt-resume-probe.cfg"
OUT = ROOT / "analysis/display-takeover/offline-a7-probe"
OUT.mkdir(exist_ok=True)

HARNESS = r'''
rename source offline_real_source
proc source {path} {
    if {[file tail $path] != "swd-memory.cfg"} { error "Forbidden real config source in offline harness" }
}
rename find offline_real_find
proc find {path} {
    if {$path != "swd-memory.cfg"} { error "Forbidden real find in offline harness" }
    return $path
}
rename init offline_real_init
proc init {} {}
rename adapter offline_real_adapter
proc adapter {args} {}
rename shutdown offline_real_shutdown
proc shutdown {} {}
# Command replacement, not a simulated transport backed by real hardware.
if {[llength [info commands read_memory]]} { rename read_memory offline_real_read_memory }
if {[llength [info commands write_memory]]} { rename write_memory offline_real_write_memory }
set sim_slock 1
set sim_oslock 1
set sim_halted 0
set sim_reset 0
set sim_history 0x0a
set sim_writes {}
set sim_rrq_count 0
set sim_fault_once 0
set sim_clock_ms 0
rename clock offline_real_clock
proc clock {subcommand args} {
    if {$subcommand == "milliseconds"} {
        incr ::sim_clock_ms
        return $::sim_clock_ms
    }
    return [offline_real_clock $subcommand {*}$args]
}
proc read_memory {address width count} {
    if {$width != 32 || $count != 1} { error "Unexpected simulated read shape" }
    switch [format "0x%08x" $address] {
        0x58050000 { set value 0x3515f005 }
        0x58050d00 { set value 0x410fc075 }
        0x58050024 { set value 0 }
        0x58050fb4 { set value [expr {1 | ($::sim_slock << 1)}] }
        0x58050304 { set value [expr {8 | ($::sim_oslock << 1)}] }
        0x58050fb8 { set value 255 }
        0x58050088 {
            if {$::sim_halted} { set value 0x03000001 } else { set value 0x02000002 }
        }
        0x58050314 {
            set value [expr {1 | $::sim_history | ($::sim_oslock << 5) | ($::sim_halted << 4)}]
            if {$::sim_reset} { set value [expr {$value | 0x0c}] }
            if {!$::sim_slock} { set ::sim_history 0 }
        }
        default { error [format "Forbidden target read 0x%08x" $address] }
    }
    return [list $value]
}
proc write_memory {address width values} {
    if {$width != 32 || [llength $values] != 1} { error "Unexpected simulated write shape" }
    set value [expr {[lindex $values 0] + 0}]
    lappend ::sim_writes [format "0x%08x:0x%08x" $address $value]
    switch [format "0x%08x" $address] {
        0x58050fb0 {
            if {$::sim_case != "lar_ignored"} { set ::sim_slock [expr {$value != 0xc5acce55}] }
            if {$value == 0 && $::sim_case == "lar_restore_fail"} { set ::sim_slock 0 }
        }
        0x58050300 {
            if {$::sim_slock} { error "OSLAR write through Software Lock" }
            if {$::sim_case != "os_unlock_ignored" || $value != 0} { set ::sim_oslock [expr {$value == 0xc5acce55}] }
        }
        0x58050090 {
            if {$::sim_slock || $::sim_oslock} { error "DRCR write through a lock" }
            if {$value == 1} {
                if {$::sim_case != "hrq_pending"} { set ::sim_halted 1 }
                if {$::sim_case == "reset_on_hrq"} { set ::sim_reset 1 }
                if {$::sim_case == "hrq_partial_error" && !$::sim_fault_once} {
                    set ::sim_fault_once 1
                    error "Simulated transport failure after committed HRQ"
                }
            } elseif {$value == 6} {
                incr ::sim_rrq_count
                if {$::sim_case != "rrq_ignored"} { set ::sim_halted 0 }
            } else { error "Forbidden DRCR value" }
        }
        default { error [format "Forbidden target write 0x%08x" $address] }
    }
}
set offline_status [catch {offline_real_source $::sim_cfg} offline_message]
set offline_summary [open $::sim_summary w]
puts $offline_summary "source_status $offline_status"
puts $offline_summary "source_message $offline_message"
puts $offline_summary "slock $sim_slock"
puts $offline_summary "oslock $sim_oslock"
puts $offline_summary "halted $sim_halted"
puts $offline_summary "rrq_count $sim_rrq_count"
puts $offline_summary "writes $sim_writes"
close $offline_summary
offline_real_shutdown
'''

CASES = {
    "success": (0, 1, 1, 0, 1, 0),
    "lar_ignored": (1, 1, 1, 0, 0, 0),
    "os_unlock_ignored": (1, 1, 1, 0, 0, 0),
    "hrq_partial_error": (1, 1, 1, 0, 1, 0),
    "hrq_pending": (1, 0, 0, 0, 0, 1),
    "reset_on_hrq": (1, 0, 0, 1, 0, 0),
    "rrq_ignored": (1, 0, 0, 1, 2, 0),
    "lar_restore_fail": (1, 0, 1, 0, 1, 0),
}

reports = []
for case, expected in CASES.items():
    result_path = OUT / f"{case}-result.txt"
    summary_path = OUT / f"{case}-state.txt"
    harness_path = OUT / f"{case}-harness.cfg"
    # Every substituted value is a local path or fixed case name, no user input.
    prefix = f"set sim_case {{{case}}}\nset sim_cfg {{{CFG.as_posix()}}}\nset sim_summary {{{summary_path.as_posix()}}}\nset a7_result_path {{{result_path.as_posix()}}}\n"
    harness_path.write_text(prefix + HARNESS)
    run = subprocess.run([str(EXE), "-f", str(harness_path)], cwd=ROOT,
                         capture_output=True, text=True, timeout=8)
    (OUT / f"{case}-host.txt").write_text(run.stdout + run.stderr)
    if not summary_path.exists():
        raise RuntimeError(f"Offline Jim Tcl harness failed before summary: {case}; see local host output")
    state = dict(line.split(" ", 1) for line in summary_path.read_text().splitlines())
    evidence = dict(line.split(" ", 1) for line in result_path.read_text().splitlines() if " " in line)
    observed = tuple(int(state[k]) for k in ("source_status", "slock", "oslock", "halted", "rrq_count")) + (int(evidence["pending_hrq_uncertain"]),)
    if observed != expected:
        raise AssertionError((case, observed, expected))
    if case in ("lar_ignored", "os_unlock_ignored"):
        assert "0x58050090" not in state["writes"], case
    reports.append({"case": case, "passed": True, "observed": {
        "source_error": observed[0], "software_lock": observed[1],
        "os_lock": observed[2], "halted": observed[3],
        "rrq_writes": observed[4], "pending_hrq_uncertain": observed[5]},
        "evidence": str(result_path.relative_to(ROOT))})
report = {"scope": "Offline Jim Tcl only; real target and adapter commands replaced; no hardware access", "cases": reports}
(OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
print(f"Offline Jim Tcl scenarios passed: {len(reports)}; no adapter/target initialization")
