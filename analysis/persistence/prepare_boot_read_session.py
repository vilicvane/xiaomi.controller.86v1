"""Compose the reviewed reset pilot and BOOT read library; offline only."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "diagnostics/mcu-recovery-mcucpu-bootbreak-probe.cfg").read_text()
source = source.replace(
    '"diagnostics/mcu-recovery-mcucpu-bootbreak-result.txt"',
    '"diagnostics/mcu-boot-native-read-result.txt"')
source = source.replace('set boot_saved 0',
    'set boot_native_read_entered 0\nset boot_watchdog_stop_possible 0\nset bnor_safe_to_resume 0\nset boot_saved 0', 1)
anchor = '    set boot_phase "boot_break_hit"\n'
assert source.count(anchor) == 1
source = source.replace(anchor, anchor + '''    # Fresh BOOT capture established above. A7CPU is held in reset and its
    # APDBG domain must not be read. Reader restores borrowed SRAM/core state.
    # The original BOOT HAL uses AON_WDT_BASE, proven by its literal+lock key.
    if {[boot_word 0x0c012ff8] != 0x40082000 || [boot_word 0x0c012ffc] != 0x1acce551} {
        error "BOOT watchdog base/unlock provenance differs"
    }
    foreach {name address} {
        load 0x40082000 value 0x40082004 control 0x40082008
        raw_interrupt 0x40082010 masked_interrupt 0x40082014
        aon_clock 0x40080000 aon_clock_other 0x40080004 aon_timer_clock 0x40080088
        mcu_preset 0x4000003c mcu_oreset 0x40000044
    } { boot_log [format "boot_watchdog_%s 0x%08x" $name [boot_word $address]] }
    source [find boot-watchdog-stop.cfg]
    boot_stop_aon_watchdog
    set boot_native_read_entered 1
    source [find boot-nor-read-runner.cfg]
    if {![info exists boot_native_capture_dir]} {
        set boot_native_capture_dir [format "analysis/persistence/native-read-%s" [clock format [clock seconds] -format %Y%m%d-%H%M%S]]
    }
    bnor_run_read_probe $boot_native_capture_dir held-reset-cmu-verified {boot_remove_fpb}
    boot_log "native_read_safe_to_resume $bnor_safe_to_resume"
    if {!$bnor_safe_to_resume} { error "Native BOOT reader did not verify complete context restoration" }
    set boot_phase "native_read_verified"
''')
cleanup = '    if {$boot_a7_reset_possible || $boot_reset_possible} {\n'
assert source.count(cleanup) == 1
source = source.replace(cleanup, '''    if {$boot_native_read_entered && !$bnor_safe_to_resume} {
        # Do not reset/resume an unclosed SPI caller or replay old context.
        boot_log "cleanup_retained_halt native_reader_failed; inspect current SPI/core state before recovery"
        set boot_cleanup_complete 0
        error "Native reader failed: automatic GLOBAL suppressed and target left halted"
    } elseif {$boot_a7_reset_possible || $boot_reset_possible} {
''')
if '--watchdog-only' in sys.argv:
    begin = source.index('    set boot_native_read_entered 1\n')
    end = source.index('    set boot_phase "native_read_verified"\n', begin)
    source = source[:begin] + '    set boot_phase "watchdog_stop_verified"\n' + source[end+len('    set boot_phase "native_read_verified"\n'):]
    source = source.replace('diagnostics/mcu-boot-native-read-result.txt', 'diagnostics/mcu-boot-watchdog-stop-result.txt')
    out = ROOT / 'diagnostics/mcu-boot-watchdog-stop-session.cfg'
else:
    out = ROOT / 'diagnostics/mcu-boot-native-read-session.cfg'
out.write_text(source)
print(f"Prepared {out.name}; no target execution")
