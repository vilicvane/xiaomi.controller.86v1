"""Summarize current-machine-code reset alternatives and coherency limits."""
from pathlib import Path
import hashlib
import json
from audit_cold_recovery import ROOT, B, IMAGE, decode

actual = ROOT / "diagnostics/mcu-cmu-active-flash-bootbreak-result.txt"
values = dict(line.split(" ", 1) for line in actual.read_text().splitlines() if " " in line)
assert values["reset_possible"] == "1" and values["write_count"] == "5"
assert values["write_possible_05"] == "0x400800a4 0x00000200"
report = {
    "scope": "Offline review only; no target accesses/actions by this agent",
    "image": str(IMAGE.relative_to(ROOT)), "sha256": hashlib.sha256(B).hexdigest(),
    "global_hardware_result": {
        "path": str(actual.relative_to(ROOT)), "primary_controller_idle": "status0x1082 busy0 / lock0x2f000 bit0x100 clear",
        "global_write": "One AON0x400800a4=0x200 committed without transport error",
        "reset_catch_observed": False, "cleanup_complete": False,
        "fresh_connection_root_result": "DP recovered in a fresh OpenOCD process; FPBcomparators0; DHCSR0x03100000 DEBUGEN0/running; DEMCR0x01110000",
        "interpretation": "Global reset demonstrably does not provide the assumed retained-debug vector-catch route. Loss of debug/catch versus ROM/BOOT overwriting it is not yet distinguished. Do not repeat as if retention were established.",
        "nor_data_written": False, "device_root_report": "Original screen/firmware returned normal"
    },
    "exact_reset_routes": {
        "aon_base": "0x40080000", "pulse": "0x400800a0", "set": "0x400800a4", "clear": "0x400800a8",
        "enum_a7_base": "0x83", "enum_mcu": "0x85", "enum_mcucpu": "0x89", "enum_global": "0x8c",
        "mcucpu_only_pulse_value": "0x40", "mcu_subsystem_pulse_value": "0x4",
        "current_main_generic_pulse": {"entry": "0x0c5caa68", "store": "0x0c5caae8", "base_pool": "0x0c5cab00=0x40080000",
            "dispatch": "AON enum range subtracts0x83 then shifts1;0x89 therefore generates0x40. Three AON CHIP_ID reads follow to allow asynchronous-domain completion.",
            "instructions": decode(0x0c5caa68, 0x9c, "main")},
        "boot_generic_pulse_status": "Not identified in bounded BOOT code scan; BOOT generic reset_set/reset_clear are independently verified. Absence is not a ROM silicon limitation.",
        "retention": "MCUCPU-only register name and Arm warm-reset behavior do not prove BEST2003 SCS/DP/FPB/DEMCR retention. One bounded hardware measurement is still needed."
    },
    "boot_shared_resource_order": {
        "entry": "0x0c000264", "module_init_call": "0x0c002026→0x0c001a84", "nor_open": "0x0c002090→0x0c002148→RAMX0x00201381",
        "a7_reset_assert": "0x0c001af8 writes AON0x400800a4=0x1bb before NOR open",
        "mask_roles": "1bb holds A7/A7CPU,CODEC,WF/WFCPU,BT/BTCPU; leaves MCU/MCUCPU unasserted",
        "before_a7_assert": "MCU cache/low SRAM ownership is rebuilt. module_init calls MCU SRAM SYS_DIV setup0c001808 and MCU DMA request mapping0c0018c4, then resets/disables A7 bus/cache/peripheral routes0c001ac4..ae4 before AON reset0c001af8.",
        "after_assert": "Shared NOR divider/readmode/JEDEC initialization then PSRAM34000000..34003184 writes; old A7 execution context must never be resumed.",
        "late_a7_release": "0x0c012aa6 clears only A7 subsystem bit0 through AON+0xa8; A7CPUbit1 remains held until explicit start. At pre-main stop verify actual AON reset bits and PRSR rather than assume.",
        "boot_module_init_instructions": decode(0x0c001a84, 0xb0, "boot"),
        "boot_wrapper_instructions": decode(0x0c00201c, 0x78, "boot"),
        "boot_late_a7_release_instructions": decode(0x0c012a84, 0x30, "boot")
    },
    "suggested_coherency_preparation": {
        "preference": "If root selects MCUCPU pulse, use exact firmware DSP reset_set register sequence before MCU pulse so A7 and its bus/DMA/peripherals cannot run while BOOT rebuilds shared state.",
        "main_entry": "0x0c5cb498", "boot_entry": "0x0c012a54",
        "direct_stores_in_order": [
            {"address":"0x400800a4","value":"0x00000003","role":"A7 and A7CPU reset"},
            {"address":"0x40000044","value":"0x1c000000","role":"A7 watchdog/timers ORESET"},
            {"address":"0x40000114","value":"0x00041fef","role":"A7 XRESET bus/cache/core/debug/SCU routes"},
            {"address":"0x40000160","value":"0x0000009f","role":"A7 APRESET bootreg/watchdog/timers/TQ/DAP"},
            {"address":"0x40000034","value":"0x00000400","role":"AX2H_A7 bridge HRESET"}],
        "instructions_main": decode(0x0c5cb498, 0x30, "main"), "instructions_boot": decode(0x0c012a54, 0x30, "boot"),
        "limits": "This closure does not change PLL/clock enables or PSRAM reset. It is state-changing and destroys prior A7 state; no halt-resume rollback. Controller table and busy/lock must be freshly rechecked. Root may instead measure simpler pulse only if it accepts BOOT's preassert ordering; that is not independent cold proof."
    },
    "bounded_candidate_protocol": [
        "Fresh MCU/DP access, current image/FPB controls/table checked; save only controls for current epoch, not context for post-reset restoration.",
        "Pause MCU and verify primarySPI0x40148000 controller busy0/readlock clear; set temporary DEBUGEN and VC_CORERESET with stock fields preserved.",
        "If choosing explicit DSP hold, perform the verified reset_set sequence with possible-write flags first; verify AON read reset-state bits0/1 cleared. No old A7 context replay is permitted afterward.",
        "Still retain MCU halt through final primarySPI settle check; then one AONpulse0x400800a0=0x40, followed only by bounded reset/catch polling. No AIRCR/global as the experimental trigger.",
        "Require jointly observed reset and fresh halt/VCATCH; old manual halt is not success. Fresh PC/stack/security allowlist gates apply. If debug is lost, reconnect once and report retention failure; do not pretend a later ordinary main halt is BOOT catch.",
        "Only after verified fresh resetcatch arm0c0104c6 FPB and resume into original BOOT; verify independentBOOT context/table, A7 reset/power state and then use only separately reviewed read-only JEDEC runner.",
        "On all outcomes finish with one independent GLOBAL reset back to original firmware, including new connection if needed; never restore old MCU/A7 registers across reset. If transport prevents this, require the known user full-power-cycle recovery."
    ],
    "rom_download_alternative": {
        "bootmode_address":"0x40080038", "software_mask":"0xfffffff0", "force_usb_download":"0x80", "force_uart_download":"0x100", "skip_flash_boot":"0x400", "jtag_enabled":"0x40",
        "header":"analysis/persistence/reference/hal_bootmode.h",
        "source":"https://raw.githubusercontent.com/openharmony/device_soc_bestechnic/17f61a22388e6f2fbd8fe855b0ccb298b9a3bd45/bes2600/liteos_m/sdk/bsp/platform/hal/hal_bootmode.h",
        "current_code":"BOOTset0c001e50/store0c001e62 and MAINset0c151de0/store0c151df2 both write(current|argument)&~0xf; getters mask low hardware reason bits; clear similarly masks low0xf",
        "instructions_boot":decode(0x0c001e40,0x54,"boot"), "instructions_main":decode(0x0c151dd0,0x54,"main"),
        "status":"Public masks and actual register semantics confirmed, but current ROM mode-selection implementation, mode retention acrossGLOBAL, timeout and SWD auth in downloader have not been captured. No direct bootmode experiment/config prepared. ROM mode cannot yet be called deterministic parking.",
        "further_evidence":"A bounded readonly current ROM code dump around mode-get/test and download-loop entry would be needed; saved NOR does not contain that ROM implementation."
    },
    "evidence":"analysis/persistence/reset-alternative-static-evidence.json",
    "unverified":"No MCUCPU pulse or ROM_DOWNLOAD hardware test has been performed by this agent. No claim of cold independent recovery or usable persistent loader yet."
}
out = ROOT / "analysis/persistence/reset-alternative-review.json"
out.write_text(json.dumps(report, indent=2) + "\n")
print("Saved exact MCUCPU pulse, BOOT/A7 coherency and ROM-mode limitations; no target access")
