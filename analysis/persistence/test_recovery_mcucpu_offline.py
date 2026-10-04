"""Offline recovery probe paths. All adapter/MEM-AP commands are substituted.

Never imports a hardware client or runs native OpenOCD init. MAIN accesses,
secondary SPI and APDBG are fatal mock errors in every scenario.
"""
from pathlib import Path
import json
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "diagnostics/mcu-recovery-mcucpu-bootbreak-probe.cfg"
OUT = ROOT / "analysis/persistence/offline-recovery-mcucpu"
OUT.mkdir(exist_ok=True)
EXE = ROOT / "tools/xpack-openocd-0.12.0-7/bin/openocd.exe"
# Reuse only the existing OFFLINE reset model, never its test execution loop.
model_file = ROOT / "analysis/persistence/test_mcucpu_pulse_offline.py"
model_source = model_file.read_text()
ns = {"__file__": str(model_file)}
exec(compile(model_source[:model_source.index("CASES = {")], "<offline-pilot-model>", "exec"), ns)
HARNESS = ns["HARNESS"]
assert "proc init {} {}" in HARNESS and "proc adapter {args} {}" in HARNESS
assert 'proc source {path}' in HARNESS and 'proc read_memory {address width count}' in HARNESS
HARNESS = HARNESS.replace("set sim_dp_unavailable 0", "set sim_dp_unavailable 0\nset sim_main_reads 0\nset sim_secondary_reads 0\nset sim_apdbg_reads 0", 1)

image = (ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin").read_bytes()
review = json.loads((ROOT / "analysis/persistence/recovery-mcucpu-probe-review.json").read_text())
seed = "array set sim_boot_words {\n"
for window in review["BOOT_signature_windows"]:
    address = int(window["address"], 16)
    for n in range(0, window["bytes"], 4):
        word = struct.unpack_from("<I", image, address-0x0C000000+n)[0]
        seed += f" {address+n} {word}\n"
seed += "}\n"
seed += '''# Explicitly bad MAIN state: a regression must not consult any of it.
array set sim_bad_main {0x20003948 0 0x2000394c 0 0x2000417c 0 0x200041f4 0xffffffff}
if {$sim_case == "boot_source_invalid"} { set sim_boot_words(201326592) 0 }
'''
HARNESS = HARNESS.replace("proc read_memory {address width count} {", seed + '''proc read_memory {address width count} {
    set address [expr {$address + 0}]
    if {($address >= 0x0c150000 && $address < 0x0d000000) ||
        ($address >= 0x20003948 && $address < 0x20003950) ||
        ($address >= 0x2000417c && $address < 0x200041a0) || $address == 0x200041f4} {
        incr ::sim_main_reads
        error "Forbidden recovery dependency on invalid MAIN code/runtime"
    }
    if {$address >= 0x40140000 && $address < 0x40141000} {
        incr ::sim_secondary_reads
        error "Forbidden secondary SPI read"
    }
    if {$address >= 0x58000000 && $address < 0x58100000} {
        incr ::sim_apdbg_reads
        error "Forbidden APDBG read"
    }
    if {$address >= 0x0c000000 && $address < 0x0c150000 && [info exists ::sim_boot_words($address)]} {
        set words {}
        for {set n 0} {$n < $count} {incr n} {
            set entry [expr {$address+4*$n}]
            if {![info exists ::sim_boot_words($entry)]} { error "Unseeded preserved BOOT read" }
            lappend words $::sim_boot_words($entry)
        }
        return $words
    }
''')
HARNESS = HARNESS.replace('0x2f000 | ($::sim_case == "nor_locked" ? 0x100 : 0)',
    '0x2f000 | ($::sim_case == "nor_locked" ? 0x100 : ($::sim_case == "nor_reset_active" ? 0x200 : 0))')
HARNESS = HARNESS.replace('            if {$::sim_case == "pulse_lost_debug"} {\n                set ::sim_dp_unavailable 1',
    '            if {$::sim_case == "pulse_commit_error"} { error "AP error after pulse committed; catch remains accessible" }\n'
    '            if {$::sim_case == "pulse_lost_debug"} {\n                set ::sim_dp_unavailable 1')
HARNESS = HARNESS.replace('writes isolation_stores global_count pulse_count}',
    'writes isolation_stores global_count pulse_count main_reads secondary_reads apdbg_reads}')

CASES = {
    "success": {"source_error":0,"break_hit":1,"global":1,"pulse":1,"fresh":1,"dispatch":1,"cleanup":0},
    "main_invalid": {"source_error":0,"break_hit":1,"global":1,"pulse":1,"fresh":1,"dispatch":1,"cleanup":0},
    "spi_settle": {"source_error":0,"break_hit":1,"global":1,"pulse":1,"fresh":1,"dispatch":1,"cleanup":0},
    "boot_source_invalid": {"source_error":1,"break_hit":0,"global":0,"pulse":0,"fresh":0,"dispatch":1,"cleanup":1},
    "nor_busy": {"source_error":1,"break_hit":0,"global":0,"pulse":0,"fresh":0,"dispatch":1,"cleanup":1},
    "nor_locked": {"source_error":1,"break_hit":0,"global":0,"pulse":0,"fresh":0,"dispatch":1,"cleanup":1},
    "nor_reset_active": {"source_error":1,"break_hit":0,"global":0,"pulse":0,"fresh":0,"dispatch":1,"cleanup":1},
    "isolation_commit_error": {"source_error":1,"break_hit":0,"global":1,"pulse":0,"fresh":1,"dispatch":1,"cleanup":0},
    "pulse_commit_error": {"source_error":0,"break_hit":1,"global":1,"pulse":1,"fresh":1,"dispatch":1,"cleanup":0},
    "pulse_lost_debug": {"source_error":1,"break_hit":0,"global":1,"pulse":1,"fresh":1,"dispatch":0,"cleanup":0},
    "break_not_hit": {"source_error":1,"break_hit":0,"global":1,"pulse":1,"fresh":1,"dispatch":1,"cleanup":0},
    "second_reset": {"source_error":1,"break_hit":0,"global":1,"pulse":1,"fresh":1,"dispatch":1,"cleanup":0},
}
reports = []
for case, expected in CASES.items():
    result = OUT / f"{case}-result.txt"
    summary = OUT / f"{case}-state.txt"
    harness = OUT / f"{case}-harness.cfg"
    prefix = f"set sim_case {{{case}}}\nset sim_cfg {{{CFG.as_posix()}}}\nset sim_summary {{{summary.as_posix()}}}\nset boot_result_path {{{result.as_posix()}}}\n"
    harness.write_text(prefix + HARNESS)
    run = subprocess.run([str(EXE), "-f", str(harness)], cwd=ROOT, capture_output=True, text=True, timeout=10)
    (OUT / f"{case}-host.txt").write_text(run.stdout + run.stderr)
    if not summary.exists() or not result.exists():
        raise RuntimeError(f"Missing offline output for {case}; see host transcript")
    state = dict(line.split(" ",1) for line in summary.read_text().splitlines())
    evidence = dict(line.split(" ",1) for line in result.read_text().splitlines() if " " in line)
    observed = {"source_error":int(state["status"]),"break_hit":int(evidence["break_hit"]),"global":int(state["global_count"]),
        "pulse":int(state["pulse_count"]),"fresh":int(evidence["fresh_process_required"]),
        "dispatch":int(evidence["cleanup_dispatch_complete"]),"cleanup":int(evidence["cleanup_complete"])}
    assert observed == expected, (case, observed, expected, evidence)
    assert all(int(state[key]) == 0 for key in ("main_reads", "secondary_reads", "apdbg_reads")), (case, state)
    writes = state["writes"].split()
    assert not any(w.startswith(("0x580", "0x4014", "0x200", "0x340", "0x0c", "0xe000ed0c:")) for w in writes)
    if expected["global"]:
        assert writes[-1] == "0x400800a4:0x00000200" and evidence["resumed"] == "0"
        assert evidence["cleanup_global_requested"] == "1" and int(state["global_count"]) == 1
    else:
        assert state["isolation_stores"] == "0" and evidence["a7_reset_possible"] == "0"
        assert not any(w.startswith("0x400") for w in writes), (case, writes)
        assert int(state["demcr"], 0) == 0x01110000 and int(state["comp0"], 0) == 0
        assert int(state["controls"]) == 0, "Temporary debug must roll back before any reset commit"
    reports.append({"case":case,"passed":True,"observed":observed,"MAIN_reads":0,"secondary_SPI_reads":0,"APDBG_reads":0,"evidence":str(result.relative_to(ROOT))})
summary = {"scope":"Offline Jim Tcl only; source/init/adapter/read/write commands substituted before CFG evaluation", "cases":reports,
    "limits":"Reset semantics modeled from measured original pilot; new recovery variant has no hardware proof and no MAIN corruption test."}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(f"Recovery MCUCPU offline paths passed: {len(reports)}; no MAIN/secondary/APDBG reads, no hardware initialization")
