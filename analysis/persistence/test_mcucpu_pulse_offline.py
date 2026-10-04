"""Four focused offline Jim Tcl pilot paths; all target commands substituted."""
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
base = (ROOT / "analysis/persistence/test_active_flash_bootbreak_offline.py").read_text()
ns = {"__file__": str(ROOT / "analysis/persistence/test_active_flash_bootbreak_offline.py")}
exec(compile(base[:base.index('CASES = dict(assignments["CASES"])')], "<offline-model-template>", "exec"), ns)
HARNESS = ns["HARNESS"]
CFG = ROOT / "diagnostics/mcu-mcucpu-pulse-bootbreak-probe.cfg"
OUT = ROOT / "analysis/persistence/offline-mcucpu-pulse"
OUT.mkdir(exist_ok=True)
EXE = ROOT / "tools/xpack-openocd-0.12.0-7/bin/openocd.exe"

HARNESS = HARNESS.replace("set sim_once 0", "set sim_once 0\nset sim_isolation_stores 0\nset sim_global_count 0\nset sim_pulse_count 0\nset sim_dp_unavailable 0")
bulk = ""
for name, address in (("main_dsp_reset_set", 0x0c5cb498), ("boot_dsp_reset_set", 0x0c012a54), ("main_reset_pulse", 0x0c5caa68)):
    match = re.search(rf"set expected_{name} \{{([^}}]+)\}}", CFG.read_text())
    assert match
    words = match.group(1).split()
    bulk += f"    if {{$address == 0x{address:08x} && $count == {len(words)}}} {{\n"
    if name == "main_reset_pulse":
        bulk += '        if {$::sim_case == "opcode_mismatch"} { return [lrepeat $count 0] }\n'
    bulk += "        return {" + " ".join(words) + "}\n    }\n"
HARNESS = HARNESS.replace('    if {$width != 32} { error "Forbidden read width" }',
    '    if {$width != 32} { error "Forbidden read width" }\n'
    '    if {$::sim_dp_unavailable} { error "Simulated DP lost after pulse" }\n' + bulk)
HARNESS = HARNESS.replace('        0x40000140 { set value 0 }', '        0x40000114 { set value 0 }\n        0x40000140 { set value 0 }')

begin = HARNESS.index('        0x400800a4 {\n            if {$value != 0x200')
end = HARNESS.index('        0xe0002000 {', begin)
reset_model = r'''
        0x400800a4 {
            if {$value == 3} {
                if {$::sim_mode != "manual_halt" || $::sim_isolation_stores != 0} { error "Isolation order/halt violated" }
                incr ::sim_isolation_stores
            } elseif {$value == 0x200} {
                if {$::sim_isolation_stores == 0} { error "GLOBAL before any isolation/pulse mutation" }
                incr ::sim_global_count
                incr ::sim_reset_count
                set ::sim_mode application
                set ::sim_controls 0
                set ::sim_demcr 0x01110000
                set ::sim_comp0 0
                set ::sim_dp_unavailable 0
                if {$::sim_case == "pulse_lost_debug"} { error "AP error after possible GLOBAL commit" }
            } else { error "Forbidden AON reset value" }
        }
        0x40000044 - 0x40000114 - 0x40000160 - 0x40000034 {
            set expected {{0x400800a4 3} {0x40000044 0x1c000000} {0x40000114 0x41fef} {0x40000160 0x9f} {0x40000034 0x400}}
            set entry [lindex $expected $::sim_isolation_stores]
            if {$address != [lindex $entry 0] || $value != [lindex $entry 1]} { error "DSP reset store order/value violated" }
            incr ::sim_isolation_stores
            if {$::sim_case == "isolation_commit_error" && $address == 0x40000114} { error "AP error after isolation store committed" }
        }
        0x400800a0 {
            if {$value != 0x40 || $::sim_isolation_stores != 5 || $::sim_mode != "manual_halt" || $::sim_controls != 3} { error "MCUCPU pulse state/order/value violated" }
            incr ::sim_pulse_count
            incr ::sim_reset_count
            set ::sim_sticky 1
            set ::sim_controls 3
            set ::sim_mode reset_catch
            set ::sim_dfsr [expr {$::sim_dfsr | 8}]
            if {$::sim_case == "pulse_lost_debug"} {
                set ::sim_dp_unavailable 1
                set ::sim_controls 0
                set ::sim_mode application
                error "AP error after MCUCPU pulse committed"
            }
        }
'''
HARNESS = HARNESS[:begin] + reset_model + HARNESS[end:]
HARNESS = HARNESS.replace('foreach name {status message mode controls demcr comp0 reset_count dcrdr writes}',
    'foreach name {status message mode controls demcr comp0 reset_count dcrdr writes isolation_stores global_count pulse_count}')
CASES = {
    "success": {"source_error":0,"break_hit":1,"global":1,"pulse":1,"fresh":1,"dispatch":1,"cleanup":0},
    "opcode_mismatch": {"source_error":1,"break_hit":0,"global":0,"pulse":0,"fresh":0,"dispatch":1,"cleanup":1},
    "isolation_commit_error": {"source_error":1,"break_hit":0,"global":1,"pulse":0,"fresh":1,"dispatch":1,"cleanup":0},
    "pulse_lost_debug": {"source_error":1,"break_hit":0,"global":1,"pulse":1,"fresh":1,"dispatch":0,"cleanup":0},
}
reports = []
for case, expected in CASES.items():
    result = OUT / f"{case}-result.txt"
    summary = OUT / f"{case}-state.txt"
    harness = OUT / f"{case}-harness.cfg"
    prefix = f"set sim_case {{{case}}}\nset sim_cfg {{{CFG.as_posix()}}}\nset sim_summary {{{summary.as_posix()}}}\nset boot_result_path {{{result.as_posix()}}}\n"
    harness.write_text(prefix+HARNESS)
    run = subprocess.run([str(EXE), "-f", str(harness)], cwd=ROOT, capture_output=True, text=True, timeout=10)
    (OUT / f"{case}-host.txt").write_text(run.stdout+run.stderr)
    if not summary.exists() or not result.exists():
        raise RuntimeError(f"Missing offline output for {case}")
    state = dict(line.split(" ",1) for line in summary.read_text().splitlines())
    evidence = dict(line.split(" ",1) for line in result.read_text().splitlines() if " " in line)
    observed = {"source_error":int(state["status"]),"break_hit":int(evidence["break_hit"]),"global":int(state["global_count"]),
                "pulse":int(state["pulse_count"]),"fresh":int(evidence["fresh_process_required"]),
                "dispatch":int(evidence["cleanup_dispatch_complete"]),"cleanup":int(evidence["cleanup_complete"])}
    assert observed == expected, (case, observed, expected, evidence)
    writes = state["writes"].split()
    assert not any("0xe000ed0c:" in w or w.startswith("0x580") or w.startswith("0x4014") for w in writes)
    assert not any(w.startswith("0x200") or w.startswith("0x340") or w.startswith("0x0c") for w in writes)
    if expected["global"]:
        assert writes[-1] == "0x400800a4:0x00000200", (case,writes)
        assert evidence["resumed"] == "0", "Cannot claim stale-context/ordinary main resume"
        assert evidence["cleanup_global_requested"] == "1"
    else:
        assert not writes and evidence["a7_reset_possible"] == "0"
    reports.append({"case":case,"passed":True,"observed":observed,"evidence":str(result.relative_to(ROOT))})
(OUT / "summary.json").write_text(json.dumps({"scope":"Offline Jim Tcl only, all target/adapter commands replaced", "cases":reports,
    "limits":"Silicon reset wiring, SCS retention and ordinary main recovery after finalGLOBAL require root hardware observation"},indent=2)+"\n")
print(f"Focused MCUCPU pilot offline scenarios passed: {len(reports)}; no adapter/hardware initialization")
