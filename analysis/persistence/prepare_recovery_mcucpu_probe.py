"""Prepare an offline recovery variant; never connects to a target.

Reuse the measured MCUCPU reset/catch flow, but remove every MAIN code/runtime
precondition. Only write this new variant and its own review artifacts.
"""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin"
PILOT = ROOT / "diagnostics/mcu-mcucpu-pulse-bootbreak-probe.cfg"
OUTPUT = ROOT / "diagnostics/mcu-recovery-mcucpu-bootbreak-probe.cfg"
B = IMAGE.read_bytes()
assert hashlib.sha256(B).hexdigest() == "777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b"
source = PILOT.read_text()
source = source.replace("diagnostics/mcu-mcucpu-pulse-bootbreak-result.txt", "diagnostics/mcu-recovery-mcucpu-bootbreak-result.txt")
start = source.index("    if {[boot_word 0x0c0104c4]")
end = source.index("    set boot_saved 1", start)
source = source[:start] + '''    # Recovery entry deliberately does not require MAIN code, SRAM controller
    # pointers, opened context, suspend byte or a healthy MAIN startup sector.
    # Bind physical primary ownership to preserved BOOT Flash source only.
    boot_verify_recovery_code
    set boot_active_controller [boot_word 0x0c005378]
    set boot_secondary_controller [boot_word 0x0c00537c]
    if {$boot_active_controller != 0x40148000 || $boot_secondary_controller != 0x40140000} {
        error "Preserved BOOT source controller mapping differs"
    }
    boot_log [format "recovery_primary_from_boot_source 0x%08x secondary_literal_only 0x%08x" $boot_active_controller $boot_secondary_controller]
    boot_log "recovery_MAIN_code_and_runtime_prerequisites 0; NOR_internal_WIP_and_suspend_not_independently_proved"
''' + source[end:]
start = source.index("    set boot_halted_controller_table")
end = source.index("    set boot_before_nor_status", start)
source = source[:start] + '''    # Recheck immutable BOOT signatures after the old MCU is held halted;
    # MAIN SRAM may be corrupt or owned by BOOT/recovery and is never read.
    boot_verify_recovery_code
    # Original BOOTHAL20000450 polls primary+0x0c bit0. The source signature
    # is checked above; this bounded MEM-AP poll does not execute that HAL.
''' + source[end:]
source = source.replace("($boot_before_nor_lock & 0x100)", "($boot_before_nor_lock & 0x300)")
source = source.replace("($isolation_lock & 0x100)", "($isolation_lock & 0x300)")
source = source.replace("NOR controller busy or memory-read-lock active; no MCUCPU pulse issued", "Primary SPI busy/readlock/reset active; no A7 isolation or MCUCPU pulse issued")
source = source.replace("# Exactly the actual MAIN0c5cb498 and BOOT0c012a54 reset_set closure.", "# Exactly the preserved BOOT0c012a54 reset_set closure.")
source = source.replace("# Current boot+main binaries both store0x200 toAON40080000+0xa4 for reboot.\n# Corrected SPI mapping: MAINtable20003948 /BOOTtable20003300:\n# {40148000,40140000}. id0 is40148000, not the old assumed40140000.\n# Always verify the live SRAM table before any SPI register access.", "# Recovery entry binds id0=40148000 to preserved BOOTsource0c005378.\n# MAIN code and all MAIN runtime pointers are deliberately unused.\n# Original BOOT generic-pulse opcodes were not identified: MCUCPU40 route\n# provenance is the successful root-owned pilot and its hardware result.\n# BOOT signatures are limited gates, not a checksum of the entire BOOT.\n# Requires readable/clocked primary SPI and controllable Secure MCU debug.\n# It cannot recover arbitrary bad BOOT, chip-WIP/suspend, lost-DP or lockup states.")

windows = [
    ("boot_header_page", 0x0C000000, 256),
    ("boot_startup_copy", 0x0C00018C, 0x98),
    ("boot_primary_idle_HAL_source", 0x0C0024C8, 0x14),
    ("boot_native_nor_init_source", 0x0C0033F8, 0x24),
    ("boot_controller_table_source", 0x0C005378, 8),
    ("boot_breakpoint", 0x0C0104C4, 8),
    ("boot_dsp_reset_set", 0x0C012A54, 0x30),
    ("boot_global_reset", 0x0C012B68, 0x14),
]
procedure = '''proc boot_verify_recovery_code {} {
    # All expected words come from the preserved exact original BOOT image.
    # Secondary SPI is represented only by a literal; never dereferenced.
    foreach {label address expected} {
'''
report_windows = []
for label, address, size in windows:
    words = struct.unpack_from("<" + "I" * (size // 4), B, address - 0x0C000000)
    expected = " ".join(f"0x{w:08x}" for w in words)
    procedure += f"        {label} 0x{address:08x} {{{expected}}}\n"
    report_windows.append({"label": label, "address": hex(address), "bytes": size, "sha256": hashlib.sha256(B[address-0x0C000000:address-0x0C000000+size]).hexdigest()})
procedure += '''    } {
        set actual [read_memory $address 32 [llength $expected]]
        if {[llength $actual] != [llength $expected]} { error "Incomplete preserved BOOT signature read: $label" }
        foreach found $actual wanted $expected {
            if {[expr {$found + 0}] != [expr {$wanted + 0}]} { error "Preserved BOOT source signature differs: $label" }
        }
        boot_log "recovery_signature_verified $label"
    }
}
'''
anchor = 'boot_log "scope verified DSP reset_set isolation'
assert source.count(anchor) == 1
source = source.replace(anchor, procedure + anchor, 1)
source = source.replace("scope verified DSP reset_set isolation + one MCUCPU", "scope recovery preserved-BOOT source gates without MAIN prerequisites; verified DSP reset_set isolation + one MCUCPU", 1)
source = source.replace("MCUCPU pulse pilot completed;", "Recovery MCUCPU pulse BOOT probe completed;", 1)
for forbidden in ("0x20003948", "0x2000417c", "0x200041f4", "0x0c5c", "0x0c155858", "0x58050314", "0x58050088"):
    assert forbidden not in source, forbidden
assert source.count("boot_put 0x400800a0 0x40") == 1
assert source.count("boot_put 0x400800a4 0x200") == 1
OUTPUT.write_text(source)
report = {"offline_only": True, "hardware_execution_performed": False, "cfg": str(OUTPUT.relative_to(ROOT)), "cfg_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
          "source_image_sha256": hashlib.sha256(B).hexdigest(), "reused_pilot_sha256": hashlib.sha256(PILOT.read_bytes()).hexdigest(), "BOOT_signature_windows": report_windows,
          "primary_controller": "0x40148000", "secondary_controller_access": False, "MAIN_code_or_runtime_reads": False, "APDBG_reads": False,
          "pulse_route_provenance": "Root measured original MCUCPU40 pilot; analysis/persistence/mcucpu-pilot-hardware-result.json. No claim of identified BOOT generic-pulse code.",
          "scope": "One DSP isolation + MCUCPU pulse, joint fresh-reset/VCATCH, pre-MAIN BOOT FPB, opened BOOT context, then GLOBAL cleanup whenever reset mutation may have committed.",
          "limits": ["Requires accessible matching preserved BOOT signature windows, debug/FPB availability and MCU capable of reaching a controlled halt.",
                     "Requires clocked/readable primary SPI, bounded controller idle, and clear readlock/reset bits; these do not prove chip internal WIP or suspend state.",
                     "Signature windows do not hash every BOOT instruction or establish arbitrary corruption tolerance.",
                     "Stock BOOT may change NOR status/protection. No debugger NOR API/data writes.",
                     "No MAIN corruption experiment or recovery-mode hardware execution performed.",
                     "Uncertain posted reset commit triggers one GLOBAL cleanup request; transport failure still needs fresh process/full power recovery verification."]}
(ROOT / "analysis/persistence/recovery-mcucpu-probe-review.json").write_text(json.dumps(report, indent=2) + "\n")
print("Prepared new recovery probe only; existing pilot/read library unchanged; no hardware")
