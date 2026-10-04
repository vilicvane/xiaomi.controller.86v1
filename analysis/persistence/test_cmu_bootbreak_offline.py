"""Offline Jim Tcl CMU-reset probe validation; all hardware commands replaced."""
from pathlib import Path
import ast
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "tools/xpack-openocd-0.12.0-7/bin/openocd.exe"
CFG = ROOT / "diagnostics/mcu-cmu-bootbreak-probe.cfg"
OUT = ROOT / "analysis/persistence/offline-cmu-bootbreak"
OUT.mkdir(exist_ok=True)
tree = ast.parse((ROOT / "analysis/persistence/test_bootbreak_offline.py").read_text())
assignments = {s.targets[0].id: ast.literal_eval(s.value) for s in tree.body
               if isinstance(s, ast.Assign) and len(s.targets) == 1
               and isinstance(s.targets[0], ast.Name) and s.targets[0].id in ("HARNESS", "CASES")}
HARNESS = assignments["HARNESS"]
reads = '''
        0x0c012b78 { set value 0x40080000 }
        0x0c5cb734 { set value 0x40080000 }
        0x0c012b68 { set value 0xf44fffd5 }
        0x0c012b6c { set value 0x4b027200 }
        0x0c012b70 { set value 0x20a4f8c3 }
        0x0c5cb724 { set value 0xf44fffcd }
        0x0c5cb728 { set value 0x4b027200 }
        0x0c5cb72c { set value 0x20a4f8c3 }
        0x4014000c { set value [expr {$::sim_case == "nor_busy"}] }
        0x40140034 { set value [expr {$::sim_case == "nor_locked" ? 0x100 : 0}] }
        0x400800a4 { set value 0 }
        0x400800a8 { set value 0 }
        0x40080004 { set value 0 }
        0x40080008 { set value 0 }
        0x40000034 { set value 0 }
        0x40000044 { set value 0 }
        0x40000140 { set value 0 }
        0x40000150 { set value 0 }
        0x40000154 { set value 0 }
        0x40000160 { set value 0 }
        0xe000ed08 { set value 0x20000000 }
        0xe000ed90 { set value 0x1000 }
        0xe000ed94 { set value 0 }
        0xe000ed98 { set value 0 }
        0xe000ed9c { set value 0 }
        0xe000eda0 { set value 0 }
        0xe000edc0 { set value 0 }
        0xe000edd0 { set value 0 }
        0xe000edd4 { set value 8 }
        0x58050314 { set value [expr {$::sim_case == "a7_powered" ? 5 : 4}] }
        0x58050088 {
            if {$::sim_case != "a7_powered"} { error "Forbidden DSCR powered-off-domain read" }
            set value 0x02000002
        }
'''
HARNESS = HARNESS.replace('        0xe000ed00 { set value 0x630f1321 }', reads + '        0xe000ed00 { set value 0x630f1321 }')
HARNESS = HARNESS.replace('        0xe000ed0c {\n            if {$value != 0x05fa0004} { error "Unexpected AIRCR request" }',
    '        0x400800a4 {\n            if {$value != 0x200 || $::sim_controls != 3 || $::sim_mode != "manual_halt"} { error "Unexpected CMU value/old halt not preserved" }')
assert 'Unexpected AIRCR request' not in HARNESS
CASES = dict(assignments["CASES"])
CASES.update(nor_busy=(1, 0, 1), nor_locked=(1, 0, 1), a7_powered=(0, 1, 1))
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
        raise RuntimeError(f"Offline harness failed: {case}; see host output")
    state = dict(line.split(" ", 1) for line in summary.read_text().splitlines())
    evidence = dict(line.split(" ", 1) for line in result.read_text().splitlines() if " " in line)
    observed = (int(state["status"]), int(evidence["break_hit"]), int(evidence["cleanup_complete"]))
    assert observed == expected, (case, observed, expected)
    assert int(state["comp0"]) == 0 and int(state["demcr"]) == 0x01110000, (case, state)
    assert "0xe000ed0c:" not in state["writes"], "AIRCR mutation is forbidden in this probe"
    assert state["writes"].count("0x400800a4:0x00000200") <= 1, "CMU reset repeated"
    if case in ("nor_busy", "nor_locked"):
        assert int(state["reset_count"]) == 0 and "0x400800a4:" not in state["writes"]
    reports.append({"case": case, "passed": True, "observed": {
        "source_error": observed[0], "boot_break_hit": observed[1],
        "cleanup_complete": observed[2], "simulated_resets": int(state["reset_count"]),
        "final_mode": state["mode"], "stock_demcr_preserved": True,
        "temporary_fpb_removed": True, "aircr_untouched": True},
        "evidence": str(result.relative_to(ROOT))})
(OUT / "summary.json").write_text(json.dumps({"scope": "Offline Jim Tcl only; all hardware commands replaced",
    "silicon_retention_not_verified": True, "cases": reports}, indent=2) + "\n")
print(f"Offline CMU boot-break scenarios passed: {len(reports)}; no hardware/adapter initialization")
