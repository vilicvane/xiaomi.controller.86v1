"""Generate a separate CMU variant of reviewed reset-catch config, offline only."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "diagnostics/mcu-reset-bootbreak-probe.cfg").read_text()
source = source.replace(
    "# One AIRCR SYSRESETREQ, reset vector catch, then one FPB v2 breakpoint at boot",
    "# One direct AON-CMU GLOBAL hard reset, reset catch, then one FPB v2 breakpoint.")
source = source.replace("diagnostics/mcu-reset-bootbreak-result.txt", "diagnostics/mcu-cmu-bootbreak-result.txt")
source = source.replace("# This is a warm system-reset experiment, NOT proof of full-power cold recovery.",
    "# Direct reset skips firmware shutdown/flush hooks and interrupts panel service.\n"
    "# It is NOT proof of full-power cold recovery or retained debug state.\n"
    "# Current boot+main binaries both store0x200 toAON40080000+0xa4 for reboot.")
source = source.replace("scope one SYSRESETREQ, reset catch, FPB boot breakpoint, immediate resume; no NOR/RAM/core-register data writes",
    "scope one direct AON400800a4=0x200 GLOBAL hard reset; reset catch and FPB boot stop; no debugger NOR/RAM/core-register data writes")
source = source.replace("# SYSRESETREQ can be posted while the old C_HALT remains visible.",
                        "# CMU reset can be posted while old state remains visible.")
old = '''    # Preserve RW configuration, exclude RO endianness/reserved/action bits.
    set boot_reset_value [expr {0x05fa0004 | ($boot_original_aircr & 0x6738)}]
    # AP may report an error after the reset write has committed. Poll anyway.
    set reset_write_error [catch { boot_put 0xe000ed0c $boot_reset_value boot_reset_possible } reset_write_message]'''
new = '''    # Gate the flash controller while MCU is paused. These are controller
    # busy/lock flags, not an independent read of the NOR chip's internal WIP.
    set boot_before_nor_status [boot_word 0x4014000c]
    set boot_before_nor_lock [boot_word 0x40140034]
    set boot_before_aon_reset [boot_word 0x400800a4]
    boot_log [format "pre_global_nor_status 0x%08x readlock 0x%08x aon_soft_reset_set 0x%08x" $boot_before_nor_status $boot_before_nor_lock $boot_before_aon_reset]
    if {($boot_before_nor_status & 1) || ($boot_before_nor_lock & 0x100)} {
        error "NOR controller busy or memory-read-lock active; no global reset issued"
    }
    # Retain the old MCU halt through the idle guard and hardware reset write:
    # resuming it would allow a new NOR transaction in between. AON reset is a
    # MEM-AP peripheral action, independent of CPU instruction execution.
    # Joint reset/catch polling must not mistake this old halt for a new catch.
    boot_stable_halt
    if {$boot_reset_seen} { error "Unexpected reset before the intended AON write" }
    # NOR/boot instruction words below were matched to actual1.50.10 backup:
    # BOOT0c012b6a mov200 /LDR40080000 /STR[a4]; MAIN0c5cb726 same.
    # Direct hard reset deliberately skips each function's shutdown hook.
    # AP can report an error after commit; do not send a second reset.
    set reset_write_error [catch { boot_put 0x400800a4 0x200 boot_reset_possible } reset_write_message]'''
assert old in source
source = source.replace(old, new)
gate = '''    if {[boot_word 0x0c0104c4] != 0xf006f895 || [boot_word 0x0c0104c8] != 0x4b5bf887} {
        error "Boot breakpoint instructions differ from reviewed original boot"
    }'''
assert gate in source
extra = '''
    if {[boot_word 0x0c012b78] != 0x40080000 || [boot_word 0x0c5cb734] != 0x40080000} {
        error "Global-reset base literals differ from reviewed BOOT/MAIN"
    }
    # Exact Thumb instruction bytes: MOV.W r2,#0x200 and STR.W r2,[r3,#0xa4].
    if {([boot_word 0x0c012b68] >> 16) != 0xf44f || ([boot_word 0x0c012b6c] & 0xffff) != 0x7200 || [boot_word 0x0c012b70] != 0x20a4f8c3 || ([boot_word 0x0c5cb724] >> 16) != 0xf44f || ([boot_word 0x0c5cb728] & 0xffff) != 0x7200 || [boot_word 0x0c5cb72c] != 0x20a4f8c3} {
        error "Global-reset store instructions differ from actual firmware"
    }'''
source = source.replace(gate, gate + extra)
mark = '''    # This probe only observes boot context; no NOR API is invoked.
    set boot_break_hit 1'''
metadata = '''    # Read small control metadata only; no MPU/SAU selector/control writes.
    foreach {name address} {
        vtor 0xe000ed08 mpu_type 0xe000ed90 mpu_ctrl 0xe000ed94
        mpu_rnr 0xe000ed98 mpu_rbar 0xe000ed9c mpu_rlar 0xe000eda0
        mpu_mair0 0xe000edc0 sau_ctrl 0xe000edd0 sau_type 0xe000edd4
        aon_top_clock_enable 0x40080004 aon_top_clock_disable 0x40080008
        aon_soft_reset_set 0x400800a4 aon_soft_reset_clear 0x400800a8
        cmu_hreset_set 0x40000034 cmu_oreset_set 0x40000044
        cmu_dsp_cfg0 0x40000140 cmu_ap_clock_enable 0x40000150
        cmu_ap_clock_disable 0x40000154 cmu_ap_reset_set 0x40000160
    } {
        boot_log [format "boot_meta_%s 0x%08x" $name [boot_word $address]]
    }
    # A7 may be reset/off before its boot image is launched. Optional status
    # failure is recorded; never write/unlock/halt its debug component here.
    set a7_status_error [catch { set boot_a7_prsr [boot_word 0x58050314] } a7_status_message]
    if {$a7_status_error} {
        boot_log "boot_meta_a7_prsr_read_error $a7_status_message"
    } else {
        boot_log [format "boot_meta_a7_prsr 0x%08x" $boot_a7_prsr]
        if {$boot_a7_prsr & 1} {
            set observation_error [catch { set value [boot_word 0x58050088] } observation_message]
            if {$observation_error} { boot_log "boot_meta_a7_dscr_read_error $observation_message" } else {
                boot_log [format "boot_meta_a7_dscr 0x%08x" $value]
            }
        } else { boot_log "boot_meta_a7_dscr_skipped powered_off" }
    }
    boot_stable_halt
    # This probe only observes boot context; no NOR API is invoked.
    set boot_break_hit 1'''
assert mark in source
source = source.replace(mark, metadata)
source = source.replace("Verified reset catch and boot breakpoint; original firmware resumed; no NOR data write",
                        "Verified CMU reset catch/boot breakpoint; original firmware resumed; no debugger NOR command")
out = ROOT / "diagnostics/mcu-cmu-bootbreak-probe.cfg"
out.write_text(source)
print("Prepared separate CMU-global probe; no target access")
