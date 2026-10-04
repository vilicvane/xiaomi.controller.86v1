"""Record root hardware evidence for BOOT-only recovery and WDT stop."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
result = ROOT / 'diagnostics/mcu-boot-watchdog-stop-result.txt'
reconnect = ROOT / 'diagnostics/mcu-after-watchdog-stop-state.txt'
values = dict(line.split(' ',1) for line in result.read_text().splitlines() if ' ' in line)
assert values['reset_caught'] == values['break_hit'] == '1'
assert values['unexpected_reset'] == '0'
assert values['cleanup_global_transport_error'] == values['pre_global_debug_cleanup_error'] == '0'
assert values['watchdog_stop_verified'] == 'CTRL0 lock1 VALUEunchanged 0x0000ac25'
assert '03100000 00000000 200d3e00 01110000' in reconnect.read_text()
report = {
    'executed_by':'root', 'firmware':'1.50.10',
    'recovery_entry_MAIN_code_or_runtime_reads':False,
    'fresh_ROM_then_preserved_BOOT_stop_verified':True,
    'BOOT_stop_PC':'0x0c0104c6','A7CPU_held_reset':True,
    'watchdog':{'base':'0x40082000','original_control':3,
        'origin':'Original BOOT PMU initialization starts 4-second SP805 watchdog',
        'stop_equivalent_of':'0x0c013040', 'control_after':0,'lock_after':1,
        'software_start_flag_after':0,'VALUE_two_reads_20ms_apart':'0x0000ac25',
        'LOAD_INTCLR_or_clock_writes':False,'old_counter_replayed':False},
    'rollback':'Temporary FPB removed, GLOBAL requested once; fresh OpenOCD process verified MCU running, debug disabled/default DEMCR and all comparators zero',
    'NOR_debugger_program_erase_status_commands':False,
    'stop_library_sha256':hashlib.sha256((ROOT / 'diagnostics/boot-watchdog-stop.cfg').read_bytes()).hexdigest(),
    'evidence':[str(result.relative_to(ROOT)),str(reconnect.relative_to(ROOT))],
    'limits':['Known debug/readable-BOOT/clocked-idle-controller entry is required; not arbitrary chip recovery.',
        'Native NOR read/program/erase were not invoked by this pilot.']
}
(ROOT / 'analysis/persistence/watchdog-stop-hardware-result.json').write_text(json.dumps(report,indent=2)+'\n')
print('Recorded verified immutable-BOOT entry/WDT stop and GLOBAL reconnect')
