"""Record actual native NOR read and complete caller restoration."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
capture = ROOT / 'analysis/persistence/native-read-20261004-150456'
result = capture / 'result.txt'
text = result.read_text()
assert 'JEDEC 856518 SR1 0x7c SR2 0x02 saved_BP 0x007c' in text
assert 'context_restore_complete 1 test_error 0 cleanup_error 0' in text
assert (capture/'scratch-original.bin').read_bytes() == (capture/'scratch-restored.bin').read_bytes()
reconnect = ROOT / 'diagnostics/mcu-after-native-read-state.txt'
assert '03140000 00000000 200d3e00 01110000' in reconnect.read_text()
report = {
    'executed_by':'root','firmware':'1.50.10','fresh_preserved_BOOT_stop':'0x0c0104c6',
    'entry_has_no_MAIN_runtime_or_code_dependencies':True,
    'A7CPU_held_reset_without_APDBG_reads':True,'BOOT_WDT_CTRL0_verified':True,
    'native_commands':['0x9f','0x05','0x35'],'JEDEC':'856518',
    'SR1':'0x7c','SR2':'0x02','BP_mask':'0x007c',
    'native_read_pre_post_returns':[0,0,0,0,0],'native_elapsed_ms':25,
    'full_1KiB_scratch_original_equals_restored':True,
    'scratch_sha256':hashlib.sha256((capture/'scratch-original.bin').read_bytes()).hexdigest(),
    'core_context_restored_and_verified':True,'SPI_post_and_BOOTHAL_globals_verified':True,
    'debugger_NOR_program_erase_or_status_write_commands':False,
    'rollback':'GLOBAL dispatch after verified restoration; fresh process confirms running MCU and zero comparators/default debug state',
    'evidence':[str(result.relative_to(ROOT)),str(reconnect.relative_to(ROOT))],
    'limits':['Read recovery is verified; erase/program/restoration remains untested.',
        'Entry still requires debug/readable preserved BOOT and clocked idle primary controller.']
}
(ROOT/'analysis/persistence/native-read-hardware-result.json').write_text(json.dumps(report,indent=2)+'\n')
print('Recorded native JEDEC/status read, exact RAM/core restore and fresh reconnect')
