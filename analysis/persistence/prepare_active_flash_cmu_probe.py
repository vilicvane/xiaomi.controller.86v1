"""Correct verified controller mapping in a new variant; never overwrite failed logs/config."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "diagnostics/mcu-cmu-bootbreak-probe.cfg").read_text()
source = source.replace("diagnostics/mcu-cmu-bootbreak-result.txt", "diagnostics/mcu-cmu-active-flash-bootbreak-result.txt")
source = source.replace("# Current boot+main binaries both store0x200 toAON40080000+0xa4 for reboot.",
    "# Current boot+main binaries both store0x200 toAON40080000+0xa4 for reboot.\n"
    "# Corrected SPI mapping: MAINtable20003948 /BOOTtable20003300:\n"
    "# {40148000,40140000}. id0 is40148000, not the old assumed40140000.\n"
    "# Always verify the live SRAM table before any SPI register access.")
gate = '''    set boot_saved 1
    # Enabling debug requires MASKINTS=0. Never SNAPSTALL/STEP/mask IRQs.'''
extra = '''    # Validate physical controller ownership from the actual SRAM table and
    # both original image copies, before using any controller peripheral.
    set boot_main_controller_table [read_memory 0x20003948 32 2]
    set boot_active_controller [expr {[lindex $boot_main_controller_table 0] + 0}]
    set boot_secondary_controller [expr {[lindex $boot_main_controller_table 1] + 0}]
    boot_log [format "main_controller_id0 0x%08x id1 0x%08x" $boot_active_controller $boot_secondary_controller]
    if {$boot_active_controller != 0x40148000 || $boot_secondary_controller != 0x40140000} {
        error "Live controller table differs from corrected actual-firmware mapping"
    }
    if {[boot_word 0x0c155858] != 0x40148000 || [boot_word 0x0c15585c] != 0x40140000 || [boot_word 0x0c005378] != 0x40148000 || [boot_word 0x0c00537c] != 0x40140000} {
        error "Original MAIN/BOOT controller source tables differ from corrected mapping"
    }
    set boot_main_opened_word [boot_word 0x2000417c]
    set boot_main_suspend_word [boot_word 0x200041f4]
    set boot_main_suspend_state [expr {($boot_main_suspend_word >> 16) & 255}]
    boot_log [format "main_nor_opened %d recorded_suspend_state %d original_sleep_observed %d" [expr {$boot_main_opened_word & 255}] $boot_main_suspend_state [expr {($boot_original_dhcsr & 0x40000) != 0}]]
    if {($boot_main_opened_word & 255) != 1 || $boot_main_suspend_state != 0} {
        error "Main NOR context not opened or records a suspended operation"
    }
    # SuspendNONE and old saved-lock/pending fields are NOT synchronous busy
    # indicators. The real controller idle/readlock check still follows.
    set boot_saved 1
    # Enabling debug requires MASKINTS=0. Never SNAPSTALL/STEP/mask IRQs.'''
assert gate in source
source = source.replace(gate, extra)
source = source.replace('    set boot_phase "reset_requested"', '    set boot_phase "cmu_reset_preflight"')
idle_proc = '''proc boot_wait_active_spi_idle {controller timeout_ms} {
    global boot_reset_seen
    set begin [clock milliseconds]
    for {set i 0} {$i < 32} {incr i} {
        boot_stable_halt
        if {$boot_reset_seen} { error "Reset occurred before intended global write" }
        set status [boot_word [expr {$controller + 0x0c}]]
        if {($status & 1) == 0} { return $status }
        if {[clock milliseconds] - $begin >= $timeout_ms} {
            boot_log [format "active_spi_idle_timeout_status 0x%08x" $status]
            error "Active SPI controller busy did not settle; no global reset issued"
        }
        sleep 5
    }
    error "Active SPI controller idle poll count bound reached; no global reset issued"
}
'''
source = source.replace('proc boot_fpb_snapshot {prefix} {', idle_proc + 'proc boot_fpb_snapshot {prefix} {')
old = '''    set boot_before_nor_status [boot_word 0x4014000c]
    set boot_before_nor_lock [boot_word 0x40140034]'''
new = '''    set boot_halted_controller_table [read_memory 0x20003948 32 2]
    if {[expr {[lindex $boot_halted_controller_table 0] + 0}] != $boot_active_controller || [expr {[lindex $boot_halted_controller_table 1] + 0}] != $boot_secondary_controller} {
        error "Controller SRAM pointer table changed before idle gate"
    }
    # MainHAL20000790 and BOOTHAL20000450 both poll status+0x0c bit0.
    # Our poll is bounded, unlike the firmware's unbounded wait loop.
    set boot_before_nor_status [boot_wait_active_spi_idle $boot_active_controller 200]
    set boot_before_nor_lock [boot_word [expr {$boot_active_controller + 0x34}]]'''
assert old in source
source = source.replace(old, new)
source = source.replace('    set reset_write_error [catch { boot_put 0x400800a4 0x200 boot_reset_possible } reset_write_message]',
    '    set boot_phase "reset_requested"\n    set reset_write_error [catch { boot_put 0x400800a4 0x200 boot_reset_possible } reset_write_message]')
mark = '''    # Read small control metadata only; no MPU/SAU selector/control writes.'''
boot_table = '''    set boot_live_controller_table [read_memory 0x20003300 32 2]
    boot_log "independent_boot_controller_table $boot_live_controller_table"
    if {[expr {[lindex $boot_live_controller_table 0] + 0}] != 0x40148000 || [expr {[lindex $boot_live_controller_table 1] + 0}] != 0x40140000} {
        error "Fresh independent BOOT controller ownership differs"
    }
    # Read small control metadata only; no MPU/SAU selector/control writes.'''
assert mark in source
source = source.replace(mark, boot_table)
out = ROOT / "diagnostics/mcu-cmu-active-flash-bootbreak-probe.cfg"
out.write_text(source)
print("Prepared new live-table-gated active-id0 CMU variant; no target access")
