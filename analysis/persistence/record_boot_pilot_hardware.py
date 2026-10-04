"""Record actual root-only pilot result and independent reconnect evidence."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
result = ROOT / 'diagnostics/mcu-mcucpu-pulse-bootbreak-result.txt'
reconnect = ROOT / 'diagnostics/mcu-after-mcucpu-pilot-state.txt'
cfg = ROOT / 'diagnostics/mcu-mcucpu-pulse-bootbreak-probe.cfg'
evidence = dict(line.split(' ',1) for line in result.read_text().splitlines() if ' ' in line)
assert evidence['reset_caught'] == evidence['break_hit'] == '1'
assert evidence['unexpected_reset'] == '0'
assert evidence['pre_global_debug_cleanup_error'] == '0'
assert evidence['cleanup_global_transport_error'] == '0'
text = reconnect.read_text()
assert '00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000' in text
assert '03140000 00000000 200d3e00 01110000' in text
report = {
    'hardware_execution':'root', 'pilot_cfg_sha256':hashlib.sha256(cfg.read_bytes()).hexdigest(),
    'reset_catch_pc':'0x00027b0c', 'fresh_BOOT_stop_pc':'0x0c0104c6',
    'BOOT_SP':'0x200d5dc8', 'BOOT_MSPLIM_S':'0x200d3e00',
    'BOOT_NOR_opened_context':'0x18658501', 'primary_controller':'0x40148000',
    'BOOT_AON_reset_readback':'0x0000024d', 'A7CPU_held_reset':True,
    'APDBG_read_after_isolation':False, 'debugger_NOR_API_or_data_writes':False,
    'temporary_comparator_removed_before_GLOBAL':True,
    'GLOBAL_recovery_dispatch_returned':True,
    'fresh_process_reconnect':{'MCU_running':True,'C_DEBUGEN':False,
        'FPB_all_comparators_zero':True,'DEMCR':'0x01110000'},
    'user_screen_observation_after_this_pilot':'not_requested_or_confirmed',
    'evidence':[str(result.relative_to(ROOT)),str(reconnect.relative_to(ROOT))],
    'limits':['Starting preflight still uses current MAIN runtime/controller fields.',
        'Original BOOT independent initialization reached, but native NOR read/restore not yet verified.',
        'No claim that every cold/crashed-main state has been recovered.']
}
(ROOT / 'analysis/persistence/mcucpu-pilot-hardware-result.json').write_text(json.dumps(report,indent=2)+'\n')
print('Recorded actual ROM/BOOT capture and fresh-process running-state evidence')
