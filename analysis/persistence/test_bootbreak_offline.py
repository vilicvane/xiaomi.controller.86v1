"""Real Jim Tcl parser, strictly substituted adapter/MEM-AP commands; no hardware.

Models resets, read-clear sticky status, FPB, debug transfers, ignored requests,
and transport errors after target writes commit. Does not model BES reset wiring.
"""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis/persistence/offline-bootbreak"
OUT.mkdir(exist_ok=True)
EXE = ROOT / "tools/xpack-openocd-0.12.0-7/bin/openocd.exe"
CFG = ROOT / "diagnostics/mcu-reset-bootbreak-probe.cfg"
HARNESS = r'''
rename source sim_source
proc source {path} { if {$path != "swd-memory.cfg"} { error "Forbidden source" } }
rename find sim_find
proc find {path} { if {$path != "swd-memory.cfg"} { error "Forbidden find" }; return $path }
rename init sim_init
proc init {} {}
rename adapter sim_adapter
proc adapter {args} {}
rename shutdown sim_shutdown
proc shutdown {} {}
rename sleep sim_sleep
proc sleep {ms} { incr ::sim_ms $ms }
rename clock sim_clock
proc clock {subcommand args} {
    if {$subcommand == "milliseconds"} { incr ::sim_ms; return $::sim_ms }
    return [sim_clock $subcommand {*}$args]
}
if {[llength [info commands read_memory]]} { rename read_memory sim_read_memory }
if {[llength [info commands write_memory]]} { rename write_memory sim_write_memory }
set sim_ms 0
set sim_mode application
set sim_controls 0
set sim_demcr 0x01110000
set sim_dfsr 0
set sim_fpctrl 0x10000081
set sim_comp0 0
set sim_dcrdr 0x40000000
set sim_sticky 0
set sim_writes {}
set sim_reset_count 0
set sim_once 0
set sim_reset_delay 0
proc sim_dhcsr {} {
    if {$::sim_reset_delay > 0} {
        incr ::sim_reset_delay -1
        if {$::sim_reset_delay == 0} {
            set ::sim_mode reset_catch
            set ::sim_sticky 1
            set ::sim_controls 3
            set ::sim_dfsr [expr {$::sim_dfsr | 8}]
        }
    }
    if {$::sim_mode == "boot_running" && $::sim_comp0 == 0x0c0104c7 && ($::sim_fpctrl & 1)} {
        if {$::sim_case != "break_not_hit"} {
            set ::sim_mode boot_hit
            set ::sim_controls 3
            set ::sim_dfsr [expr {$::sim_dfsr | 2}]
        }
    }
    if {$::sim_mode == "boot_hit" && $::sim_case == "second_reset" && !$::sim_once} {
        set ::sim_once 1
        set ::sim_mode reset_catch
        set ::sim_sticky 1
        incr ::sim_reset_count
        set ::sim_dfsr [expr {$::sim_dfsr | 8}]
    }
    set value [expr {0x01100000 | $::sim_controls}]
    if {$::sim_mode == "manual_halt" || $::sim_mode == "reset_catch" || $::sim_mode == "boot_hit"} {
        set value [expr {$value | 0x30000}]
    } else { set value [expr {$value | 0x40000}] }
    if {$::sim_sticky} { set value [expr {$value | 0x02000000}]; set ::sim_sticky 0 }
    return $value
}
proc read_memory {address width count} {
    if {$width != 32} { error "Forbidden read width" }
    if {$address == 0xe0002008 && $count == 8} {
        return [list $::sim_comp0 0 0 0 0 0 0 0]
    }
    if {$address == 0x20003ae0 && $count == 9} {
        if {$::sim_mode != "boot_hit"} { error "Boot context read before breakpoint" }
        return {0x18658501 0 0 0 0 0 0x1000000 0 0}
    }
    if {$count != 1} { error "Forbidden read count" }
    switch [format "0x%08x" $address] {
        0xe000ed00 { set value 0x630f1321 }
        0xe000edf0 { set value [sim_dhcsr] }
        0xe000edfc { set value $::sim_demcr }
        0xe000ed0c { set value 0xfa050000 }
        0xe000ed30 { set value $::sim_dfsr }
        0xe000ee08 { set value 0x30000 }
        0xe000efb8 { set value 0xff }
        0xe0002000 { set value $::sim_fpctrl }
        0xe0002008 { set value $::sim_comp0 }
        0xe000edf8 { set value $::sim_dcrdr }
        0x0c0104c4 { set value 0xf006f895 }
        0x0c0104c8 { set value 0x4b5bf887 }
        default { error [format "Forbidden read 0x%08x" $address] }
    }
    return [list $value]
}
proc write_memory {address width values} {
    if {$width != 32 || [llength $values] != 1} { error "Forbidden write shape" }
    set value [expr {[lindex $values 0] + 0}]
    lappend ::sim_writes [format "0x%08x:0x%08x" $address $value]
    switch [format "0x%08x" $address] {
        0xe000edf0 {
            if {($value & 0xffff0000) != 0xa05f0000 || ($value & 0xfffc)} { error "Forbidden DHCSR control" }
            set next [expr {$value & 3}]
            if {$next & 2} { set ::sim_mode manual_halt }
            if {($next & 2) == 0} {
                if {$::sim_mode == "reset_catch" && $::sim_comp0} {
                    set ::sim_mode boot_running
                } elseif {$::sim_mode == "boot_hit" && $::sim_case == "resume_ignored"} {
                    return
                } else { set ::sim_mode application }
            }
            set ::sim_controls $next
        }
        0xe000edfc { set ::sim_demcr $value }
        0xe000ed30 { set ::sim_dfsr [expr {$::sim_dfsr & ~$value}] }
        0xe000ed0c {
            if {$value != 0x05fa0004} { error "Unexpected AIRCR request" }
            if {$::sim_case == "reset_ignored"} { return }
            incr ::sim_reset_count
            if {$::sim_case == "delayed_reset"} { set ::sim_reset_delay 4; return }
            set ::sim_sticky 1
            set ::sim_controls 3
            set ::sim_mode reset_catch
            set ::sim_dfsr [expr {$::sim_dfsr | 8}]
            if {$::sim_case == "lost_debug"} {
                set ::sim_controls 0
                set ::sim_mode application
                set ::sim_demcr [expr {$::sim_demcr & ~1}]
            }
            if {$::sim_case == "reset_transport_error"} { error "AP error after committed reset" }
        }
        0xe0002000 {
            if {$value != 2 && $value != 3} { error "Invalid FP_CTRL write" }
            set ::sim_fpctrl [expr {0x10000080 | ($value & 1)}]
        }
        0xe0002008 {
            if {$value != 0 && ($::sim_mode != "reset_catch" || $::sim_reset_count != 1)} {
                error "FPB programmed without fresh reset catch"
            }
            set ::sim_comp0 $value
            if {$value && $::sim_case == "comp_transport_error" && !$::sim_once} {
                set ::sim_once 1
                error "AP error after committed comparator"
            }
        }
        0xe000edf4 {
            if {$value & 0x10000} { error "CPU register write forbidden" }
            if {$::sim_mode != "reset_catch" && $::sim_mode != "boot_hit"} { error "Core read without accepted halt" }
            switch $value {
                15 { if {$::sim_mode == "reset_catch"} { set ::sim_dcrdr 0x0c000010 } else { set ::sim_dcrdr 0x0c0104c6 } }
                13 { if {$::sim_mode == "reset_catch"} { set ::sim_dcrdr 0x200d5e00 } else { set ::sim_dcrdr 0x200d5dd0 } }
                16 { set ::sim_dcrdr 0x01000000 }
                28 { set ::sim_dcrdr 0x200d3e00 }
                default { error "Unexpected core register selector" }
            }
        }
        0xe000edf8 { set ::sim_dcrdr $value }
        default { error [format "Forbidden target data write 0x%08x" $address] }
    }
}
set sim_status [catch {sim_source $sim_cfg} sim_message]
set sim_file [open $sim_summary w]
foreach name {status message mode controls demcr comp0 reset_count dcrdr writes} {
    puts $sim_file "$name [set sim_$name]"
}
close $sim_file
sim_shutdown
'''
CASES = {
    "success": (0, 1, 1),
    "delayed_reset": (0, 1, 1),
    "reset_transport_error": (0, 1, 1),
    "reset_ignored": (1, 0, 1),
    "lost_debug": (1, 0, 1),
    "comp_transport_error": (1, 0, 1),
    "break_not_hit": (1, 0, 1),
    "second_reset": (1, 0, 1),
    "resume_ignored": (1, 1, 0),
}
reports = []
for case, expected in CASES.items():
    result = OUT / f"{case}-result.txt"
    summary = OUT / f"{case}-state.txt"
    harness = OUT / f"{case}-harness.cfg"
    prefix = f"set sim_case {{{case}}}\nset sim_cfg {{{CFG.as_posix()}}}\nset sim_summary {{{summary.as_posix()}}}\nset boot_result_path {{{result.as_posix()}}}\n"
    harness.write_text(prefix + HARNESS)
    run = subprocess.run([str(EXE), "-f", str(harness)], cwd=ROOT,
                         capture_output=True, text=True, timeout=10)
    (OUT / f"{case}-host.txt").write_text(run.stdout + run.stderr)
    if not summary.exists():
        raise RuntimeError(f"Offline harness failed: {case}; see local host output")
    state = dict(line.split(" ", 1) for line in summary.read_text().splitlines())
    evidence = dict(line.split(" ", 1) for line in result.read_text().splitlines() if " " in line)
    observed = (int(state["status"]), int(evidence["break_hit"]), int(evidence["cleanup_complete"]))
    assert observed == expected, (case, observed, expected)
    assert int(state["comp0"]) == 0, (case, state)
    assert int(state["demcr"]) == 0x01110000, (case, state)
    assert "0xe000edf4:0x000100" not in state["writes"]
    reports.append({"case": case, "passed": True, "observed": {
        "source_error": observed[0], "break_hit": observed[1],
        "cleanup_complete": observed[2], "reset_requests": int(state["reset_count"]),
        "final_mode": state["mode"], "comparator_removed": True,
        "stock_monitor_trace_preserved": True}, "result": str(result.relative_to(ROOT))})
(OUT / "summary.json").write_text(json.dumps({
    "scope": "Offline Jim Tcl only; hardware/adapter commands substituted",
    "not_proven": "BES AIRCR reset integration, FPB silicon behavior and watchdog reset scope",
    "cases": reports}, indent=2) + "\n")
print(f"Offline boot-break Jim Tcl scenarios passed: {len(reports)}; no adapter or hardware initialization")
