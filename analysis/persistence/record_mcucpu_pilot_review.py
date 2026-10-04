"""Record frozen pilot scope, opcode gates and four focused offline outcomes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "diagnostics/mcu-mcucpu-pulse-bootbreak-probe.cfg"
SUMMARY = ROOT / "analysis/persistence/offline-mcucpu-pulse/summary.json"
results = json.loads(SUMMARY.read_text())
assert len(results["cases"]) == 4 and all(case["passed"] for case in results["cases"])
code = CFG.read_text()
assert "0x58050314" not in code and "0x58050088" not in code
assert code.count("boot_put 0x400800a0 0x40") == 1
assert code.count("boot_put 0x400800a4 0x200") == 1
report = {
    "offline_only":True, "cfg":str(CFG.relative_to(ROOT)), "cfg_sha256":hashlib.sha256(CFG.read_bytes()).hexdigest(),
    "default_result":"diagnostics/mcu-mcucpu-pulse-bootbreak-result.txt",
    "scope":"One exact-firmware DSP reset_set isolation, one MCUCPU-only reset pulse, reset catch and pre-main FPB observation, then one finalGLOBAL recovery dispatch whenever isolation/pulse may have committed",
    "preflight_code_checks":[{"address":"0x0c5cb498","bytes":48,"role":"MAIN DSP reset_set exact opcodes and literals"},
                             {"address":"0x0c012a54","bytes":48,"role":"BOOT independently matching DSP reset_set"},
                             {"address":"0x0c5caa68","bytes":156,"role":"MAIN generic reset_pulse: AON enum base0x83, MCUCPU0x89→mask40"},
                             {"role":"Original BOOT breakpoint0c0104c6 and GLOBAL reboot opcode gates retained"}],
    "isolation_stores":[["0x400800a4","0x00000003"],["0x40000044","0x1c000000"],["0x40000114","0x00041fef"],["0x40000160","0x0000009f"],["0x40000034","0x00000400"]],
    "pulse":["0x400800a0","0x00000040"],
    "reset_isolation_status":"Only AON/MCU CMU reset state readbacks; masked requested resets must read0. No A7 debug-domain read after reset.",
    "primary_spi_gate":"Actual MAIN/BOOT source tables and liveRAM20003948 must showid0=40148000/id1=40140000. While MCU kept halted, controller busy bit0 settles within200ms/32reads and readlockbit0x100 clear, before and after isolation.",
    "boot_gate":"Joint observed MCU reset+HALT+VCATCH; only original BOOT PC0c000010 or publicROM20000..40000; programFPB after fresh catch, exactBOOTstop0c0104c6, SecureThread,bootstack/MSPLIM,openedBOOTcontext,liveBOOTtable20003300; AON A7CPUbit1 remains reset asserted",
    "writes_not_performed":"No native NORAPI, Flashdata, RAMpayload or CPUregister WnR. DCRSR selector reads temporarily changeDCRDR. Original BOOT initializes NOR and may configure chip status/protection; this is not an overall NOR-register-readonly claim.",
    "rollback":{
        "before_any_isolation_possible":"Ordinary temporary debug control rollback, without CPU context writes.",
        "after_any_isolation_or_pulse_possible":"Never replay prior MCU/A7 state. Verified fresh BOOT halt first removes this probe's FPB/catch; uncertain failures dispatch GLOBAL directly. No A7 debug access. Global commit flag set before dispatch.",
        "global_transport":"A transport error may follow commit. Recordcleanup_global_requested1 and fresh_process_required1; cleanup_dispatch_complete distinguishes a returned write from uncertain outcome.",
        "completion":"cleanup_complete remains0 afterGLOBAL because ordinary main startup must be confirmed by root in a fresh OpenOCD process; root uses known full power cycle if fresh access/recovery cannot be verified."},
    "focused_offline_summary":str(SUMMARY.relative_to(ROOT)),"focused_cases":[case["case"] for case in results["cases"]],
    "hardware_status":"Not executed by this agent. Root owns review and actual measurements; silicon retention is unverified until then.",
    "source_review":"analysis/persistence/reset-alternative-review.json"
}
out = ROOT / "analysis/persistence/mcucpu-pulse-pilot-review.json"
out.write_text(json.dumps(report,indent=2)+"\n")
print(f"Saved frozen pilot SHA {report['cfg_sha256']} and four-case offline evidence; no target access")
