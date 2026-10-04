"""Compose verified recovery/read setup and allowlisted padding test."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'diagnostics/mcu-boot-native-read-session.cfg').read_text()
source = source.replace('diagnostics/mcu-boot-native-read-result.txt','diagnostics/mcu-boot-padding-session-result.txt')
source = source.replace('set boot_native_read_entered 0',
    'set boot_native_read_entered 0\nset boot_padding_entered 0\nset bnp_safe_to_resume 0')
source = source.replace('    set boot_phase "native_read_verified"\n', '''    set boot_phase "native_read_verified"
    source [find boot-nor-padding-runner.cfg]
    set boot_padding_entered 1
    set boot_padding_capture_dir [format "analysis/persistence/padding-hardware-%s" [clock format [clock seconds] -format %Y%m%d-%H%M%S]]
    bnp_run_padding_test $boot_padding_capture_dir {boot_remove_fpb}
    boot_log "padding_safe_to_resume $bnp_safe_to_resume"
    if {!$bnp_safe_to_resume} { error "Padding test did not verify full original restoration" }
    set boot_phase "padding_verified_and_restored"
''')
source = source.replace('if {$boot_native_read_entered && !$bnor_safe_to_resume}',
    'if {($boot_native_read_entered && !$bnor_safe_to_resume) || ($boot_padding_entered && !$bnp_safe_to_resume)}')
source = source.replace('native_reader_failed','reader_or_padding_failed').replace(
    'Native reader failed: automatic GLOBAL suppressed','Reader or padding failed: automatic GLOBAL suppressed')
(ROOT / 'diagnostics/mcu-boot-padding-session.cfg').write_text(source)
print('Prepared composed padding session; no target execution')
