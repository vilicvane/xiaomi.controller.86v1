"""Create scoped offline tests for live-table-gated controller probe."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
text = (ROOT / "analysis/persistence/test_cmu_bootbreak_offline.py").read_text()
text = text.replace('diagnostics/mcu-cmu-bootbreak-probe.cfg', 'diagnostics/mcu-cmu-active-flash-bootbreak-probe.cfg')
text = text.replace('analysis/persistence/offline-cmu-bootbreak', 'analysis/persistence/offline-active-flash-bootbreak')
anchor = 'assert \'Unexpected AIRCR request\' not in HARNESS\n'
assert anchor in text
extra = """
HARNESS = HARNESS.replace("set sim_once 0", "set sim_once 0\\nset sim_spi_reads 0\\nset sim_table_reads 0")
table_reads = r'''\n    if {$address == 0x20003948 && $count == 2} {
        incr ::sim_table_reads
        if {$::sim_case == "wrong_table" || ($::sim_case == "table_changed" && $::sim_table_reads > 1)} { return {0x40140000 0x40148000} }
        return {0x40148000 0x40140000}
    }
    if {$address == 0x20003300 && $count == 2} { return {0x40148000 0x40140000} }
'''
HARNESS = HARNESS.replace('    if {$address == 0xe0002008 && $count == 8} {', table_reads + '    if {$address == 0xe0002008 && $count == 8} {')
active_reads = r'''
        0x2000417c { set value 0x18658501 }
        0x200041f4 { set value [expr {$::sim_case == "suspended" ? 0x10000 : 0}] }
        0x0c155858 { set value 0x40148000 }
        0x0c15585c { set value 0x40140000 }
        0x0c005378 { set value 0x40148000 }
        0x0c00537c { set value 0x40140000 }
        0x4014800c {
            if {$::sim_mode != "manual_halt"} { error "SPI settle read without held MCU halt" }
            incr ::sim_spi_reads
            set value 0x1052
            if {$::sim_case == "nor_busy" || ($::sim_case == "spi_settle" && $::sim_spi_reads < 4)} { incr value }
        }
        0x40148034 { set value [expr {0x2f000 | ($::sim_case == "nor_locked" ? 0x100 : 0)}] }
        0x4014000c { error "Forbidden old secondary controller read" }
        0x40140034 { error "Forbidden old secondary controller lock read" }
'''
HARNESS = HARNESS.replace('        0x4014000c { set value [expr {$::sim_case == "nor_busy"}] }', '')
HARNESS = HARNESS.replace('        0x40140034 { set value [expr {$::sim_case == "nor_locked" ? 0x100 : 0}] }', '')
HARNESS = HARNESS.replace('        0xe000ed00 { set value 0x630f1321 }', active_reads + '        0xe000ed00 { set value 0x630f1321 }')
"""
text = text.replace(anchor, anchor + extra)
text = text.replace('CASES.update(nor_busy=(1, 0, 1), nor_locked=(1, 0, 1), a7_powered=(0, 1, 1))',
    'CASES.update(nor_busy=(1, 0, 1), nor_locked=(1, 0, 1), a7_powered=(0, 1, 1), spi_settle=(0, 1, 1), wrong_table=(1, 0, 1), table_changed=(1, 0, 1), suspended=(1, 0, 1))')
text = text.replace('if case in ("nor_busy", "nor_locked"):', 'if case in ("nor_busy", "nor_locked", "wrong_table", "table_changed", "suspended"):')
text = text.replace('int(state["comp0"])', 'int(state["comp0"], 0)').replace('int(state["demcr"])', 'int(state["demcr"], 0)')
text = text.replace('Offline CMU boot-break scenarios passed:', 'Offline active-Flash CMU boot-break scenarios passed:')
(ROOT / "analysis/persistence/test_active_flash_bootbreak_offline.py").write_text(text)
print("Prepared live-table/busy-settle offline test; no target access")
