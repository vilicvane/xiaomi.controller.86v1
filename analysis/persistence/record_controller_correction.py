"""Record actual-image controller ownership and preserved failed probe scope."""
from pathlib import Path
import hashlib
import json
import struct

from audit_cold_recovery import B, IMAGE, ROOT, decode

tables = []
for view, offset, ram in (("main", 0x155858, 0x20003948), ("boot", 0x5378, 0x20003300)):
    values = struct.unpack_from("<II", B, offset)
    assert values == (0x40148000, 0x40140000)
    tables.append({"image": view, "file_offset": hex(offset), "ram_address": hex(ram),
                   "id0": hex(values[0]), "id1": hex(values[1])})

failed_path = ROOT / "diagnostics/mcu-cmu-bootbreak-result.txt"
failed = dict(line.split(" ", 1) for line in failed_path.read_text().splitlines() if " " in line)
assert failed["reset_possible"] == "0" and failed["write_count"] == "4"
assert all("0x400800a4" not in value for key, value in failed.items() if key.startswith("write_possible_"))
summary_path = ROOT / "analysis/persistence/offline-active-flash-bootbreak/summary.json"
summary = json.loads(summary_path.read_text())
assert len(summary["cases"]) == 16 and all(case["passed"] for case in summary["cases"])
cfg = ROOT / "diagnostics/mcu-cmu-active-flash-bootbreak-probe.cfg"
report = {
    "scope": "Offline source/image/report work only; no target access by this agent",
    "firmware": str(IMAGE.relative_to(ROOT)), "firmware_sha256": hashlib.sha256(B).hexdigest(),
    "controller_ownership": tables,
    "busy_bit_evidence": [
        {"image": "main", "meaning": "id-selected table, controller+0x0c bit0 wait loop; no firmware timeout",
         "instructions": decode(0x20000790, 0x14, "main")},
        {"image": "main", "meaning": "id-selected status+0x0c AND bit0 isbusy predicate",
         "instructions": decode(0x200008b4, 0x18, "main")},
        {"image": "boot", "meaning": "independent boot same table/index/bit0 wait semantics",
         "instructions": decode(0x20000450, 0x14, "boot")}
    ],
    "preserved_failed_attempt": {
        "result": str(failed_path.relative_to(ROOT)),
        "host_log": "diagnostics/mcu-cmu-bootbreak-probe.txt",
        "post_failure_log": "diagnostics/mcu-cmu-after-failure-state.txt",
        "failed_read_address": "0x4014000c", "actual_role": "id1 secondary controller",
        "reset_possible": False, "global_reset_written": False,
        "debug_writes_possible": 4, "debug_writes": [failed[k] for k in failed if k.startswith("write_possible_")],
        "nor_data_written": False, "ram_or_core_context_written": False,
        "cleanup_complete": False, "test_error": failed["test_error"], "cleanup_error": failed["cleanup_error"],
        "phase_label_correction": "Old reset_requested label preceded the failed controller preflight; it did not mean a reset write occurred",
        "recovery": "User completed full power cycle; root subsequently verified normal screen and fresh SCS/FPB access",
        "cause": "Wrong inactive/unused secondary controller is a plausible explanation for the stalled AP. Causality and clock/security/master-access alternatives have not been independently measured."
    },
    "root_live_evidence": {
        "main_table": {"path": "diagnostics/mcu-safe-reset-metadata.txt", "address": "0x20003948",
                       "values": ["0x40148000", "0x40140000"]},
        "correct_primary": {"path": "diagnostics/mcu-active-flash-metadata.txt",
                            "status_address": "0x4014800c", "status": "0x00001053",
                            "lock_address": "0x40148034", "lock": "0x0002f000",
                            "capture_state": "MCU running/sleeping; busy bit1 does not imply a program/erase fault"}
    },
    "corrected_probe": {"path": str(cfg.relative_to(ROOT)), "sha256": hashlib.sha256(cfg.read_bytes()).hexdigest(),
                        "controller_reads": "Only after actual-image + live SRAM pointer-table verification; id0=0x40148000",
                        "idle_gate": "Keep MCU halted; bounded <=32 reads/200ms of correct-primary status bit0, then lock bit0x100; reject before global write if not settled",
                        "global_reset": "At most one direct AON0x400800a4=0x200, no AIRCR; debug retention is still a silicon measurement",
                        "offline_cases_passed": len(summary["cases"]), "offline_summary": str(summary_path.relative_to(ROOT))},
    "limitations": [
        "Controller busy0 and read-bus lock0 are controller observations, not independent NOR chip WIP verification.",
        "Main opened1 and recorded suspend0 are context consistency gates, not synchronous-operation busy flags.",
        "Running status can be busy from instruction fetch or another master; halted settle can fail while A7 remains active.",
        "No assumption that a sleep observation identifies WFI or that halted PC is an idle loop.",
        "Corrected cfg remains unexecuted by this agent; only root may run hardware."
    ]
}
out = ROOT / "analysis/persistence/active-flash-controller-correction.json"
out.write_text(json.dumps(report, indent=2) + "\n")
print("Saved controller correction, failed-attempt scope and 16-case offline evidence; no target access")
