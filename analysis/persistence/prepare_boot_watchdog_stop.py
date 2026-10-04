"""Prepare exact-MMIO equivalent of the verified original BOOT WDT stop."""
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
image = (ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
words = struct.unpack_from('<13I', image, 0x13040)
source = '''# Definitions only. Requires fresh, secure BOOT halt established by outer.
# BOOT hal_wdt_stop0c013040: unlock, CTRL0, relock, flush, softwareflag0.
# No LOAD/INTCLR/clock/NVM access, no CPU register or scratch changes.
# This belongs to a reset-discarded BOOT recovery epoch. Never replay old timer.
proc boot_stop_aon_watchdog {} {
    boot_stable_halt
    set expected {%s}
    set actual [read_memory 0x0c013040 32 13]
    foreach a $actual b $expected {
        if {[expr {$a+0}] != [expr {$b+0}]} { error "Original BOOT WDT stop code/literals differ" }
    }
    set control [boot_word 0x40082008]
    set software [boot_word 0x2000b010]
    if {$control != 0 && $control != 3} { error "Unexpected AON WDT control state" }
    boot_log [format "watchdog_stop_original_ctrl 0x%%08x softwareflag 0x%%08x" $control $software]
    # Every store is marked possible before dispatch. Outer never replays old
    # MCU/A7 context and uses GLOBAL recovery after successful probes.
    boot_put 0x40082c00 0x1acce551 boot_watchdog_stop_possible
    boot_put 0x40082008 0 boot_watchdog_stop_possible
    boot_put 0x40082c00 1 boot_watchdog_stop_possible
    set lock [boot_word 0x40082c00]
    boot_put 0x2000b010 0 boot_watchdog_stop_possible
    boot_stable_halt
    if {$lock != 1 || [boot_word 0x40082008] != 0 || [boot_word 0x2000b010] != 0} {
        error "Original BOOT WDT stop equivalent did not verify CTRL/lock/softwareflag"
    }
    # A softwareflag0 can precede stop due to startup BSS clear. HardwareCTRL
    # and stopped VALUE are the evidence; never infer hardware state from flag.
    sleep 20
    set value1 [boot_word 0x40082004]
    sleep 20
    set value2 [boot_word 0x40082004]
    if {$value1 != $value2 || [boot_word 0x40082008] != 0} {
        error "AON WDT counter did not remain stopped"
    }
    boot_stable_halt
    boot_log [format "watchdog_stop_verified CTRL0 lock1 VALUEunchanged 0x%%08x" $value2]
}
''' % ' '.join(f'0x{v:08x}' for v in words)
(ROOT / 'diagnostics/boot-watchdog-stop.cfg').write_text(source)
print('Prepared verified BOOT WDT stop equivalent; no hardware')
