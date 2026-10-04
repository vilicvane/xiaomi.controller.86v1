"""Compose the reviewed immutable BOOT recovery with the fixed A7 app writer."""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=('install', 'restore'))
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'diagnostics/mcu-boot-native-read-session.cfg').read_text()
source = source.replace('diagnostics/mcu-boot-native-read-result.txt',
                        f'diagnostics/mcu-native-counter-{args.mode}-result.txt')
source = source.replace('set boot_native_read_entered 0',
                        'set boot_native_read_entered 0\nset boot_app_entered 0\nset bna_safe_to_resume 0\nset bna_app_complete 0')
anchor = '    set boot_phase "native_read_verified"\n'
assert source.count(anchor) == 1
source = source.replace(anchor, anchor + f'''    source [find boot-nor-native-app-runner.cfg]
    set boot_app_entered 1
    set boot_app_capture_dir [format "analysis/persistence/native-app-{args.mode}-hardware-%s" [clock format [clock seconds] -format %Y%m%d-%H%M%S]]
    bna_run_native_app $boot_app_capture_dir {args.mode} {{boot_remove_fpb}}
    boot_log "native_app_safe_to_resume $bna_safe_to_resume"
    boot_log "native_app_complete $bna_app_complete"
    if {{!$bna_safe_to_resume || !$bna_app_complete}} {{ error "Native app operation did not verify all sectors/protection/context" }}
    set boot_phase "native_app_{args.mode}_verified"
''')
source = source.replace('if {$boot_native_read_entered && !$bnor_safe_to_resume}',
                       'if {($boot_native_read_entered && !$bnor_safe_to_resume) || ($boot_app_entered && (!$bna_safe_to_resume || !$bna_app_complete))}')
source = source.replace('native_reader_failed', 'reader_or_native_app_failed').replace(
    'Native reader failed: automatic GLOBAL suppressed',
    'Reader or native app failed: automatic GLOBAL suppressed')
out = ROOT / f'diagnostics/mcu-native-counter-{args.mode}-session.cfg'
out.write_text(source)
print(f'Prepared native counter {args.mode} session; no target execution')
