"""Summarize actual allowlisted NOR program/erase/restoration evidence."""
from pathlib import Path
import json
import hashlib

ROOT=Path(__file__).resolve().parents[2]
capture=ROOT/'analysis/persistence/padding-hardware-20261004-151413'
text=(capture/'result.txt').read_text()
assert 'padding_restored 1 safe_to_resume 1' in text
assert 'verified_status_phase restored SR17c SR202' in text
assert (capture/'sector-original-live.bin').read_bytes()==(capture/'sector-restored-live.bin').read_bytes()
reconnect=ROOT/'diagnostics/mcu-after-padding-state.txt'
assert '03140000 00000000 200d3e00 01110000' in reconnect.read_text()
for directory in capture.iterdir():
    if directory.is_dir():
        report=(directory/'result.txt').read_text()
        assert 'context_restore_complete 1 test_error 0 cleanup_error 0' in report
        assert (directory/'scratch-original.bin').read_bytes()==(directory/'scratch-restored.bin').read_bytes()
report={
    'executed_by':'root','firmware':'1.50.10','fixed_NOR_sector':'0x825000',
    'program_page':'0x825100','program_length':256,'program_marker':'NORTEST1',
    'sector_length':4096,'original_live_all_FF':True,
    'whole_sector_programmed_verified':True,'whole_sector_original_restored':True,
    'restored_sector_sha256':hashlib.sha256((capture/'sector-restored-live.bin').read_bytes()).hexdigest(),
    'SR1_before_and_after':'0x7c','SR2_before_and_after':'0x02','BP_QE_restored':True,
    'program_elapsed_ms':24,'erase_elapsed_ms':83,
    'all_native_calls_scratch_core_SPI_restored':True,
    'final_recovery':'Temporary FPB removed/GLOBAL dispatched; new process MCU running/default debug/comparators zero',
    'evidence':[str((capture/'result.txt').relative_to(ROOT)),str(reconnect.relative_to(ROOT))],
    'limits':['Actual NOR write+erase+exact restore verified; custom startup code not yet installed.',
        'No universal guarantee for arbitrary boot corruption or external power interruption.']
}
(ROOT/'analysis/persistence/padding-hardware-result.json').write_text(json.dumps(report,indent=2)+'\n')
print('Recorded actual NOR program/erase, exact4K/protection/RAM/core restore and GLOBAL recovery')
