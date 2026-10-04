"""Compose verified recovery/read setup with fixed hook install or restore."""
from pathlib import Path
import argparse

parser=argparse.ArgumentParser()
parser.add_argument('mode',choices=('install','restore'))
args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[2]
source=(ROOT/'diagnostics/mcu-boot-native-read-session.cfg').read_text()
source=source.replace('diagnostics/mcu-boot-native-read-result.txt',f'diagnostics/mcu-boot-hook-{args.mode}-result.txt')
source=source.replace('set boot_native_read_entered 0',
    'set boot_native_read_entered 0\nset boot_hook_entered 0\nset bnh_safe_to_resume 0')
source=source.replace('    set boot_phase "native_read_verified"\n',f'''    set boot_phase "native_read_verified"
    source [find boot-nor-hook-runner.cfg]
    set boot_hook_entered 1
    set boot_hook_capture_dir [format "analysis/persistence/hook-{args.mode}-hardware-%s" [clock format [clock seconds] -format %Y%m%d-%H%M%S]]
    bnh_run_hook $boot_hook_capture_dir {args.mode} {{boot_remove_fpb}}
    boot_log "hook_safe_to_resume $bnh_safe_to_resume"
    if {{!$bnh_safe_to_resume}} {{ error "Fixed hook operation did not verify data/protection/context" }}
    set boot_phase "hook_{args.mode}_verified"
''')
source=source.replace('if {$boot_native_read_entered && !$bnor_safe_to_resume}',
    'if {($boot_native_read_entered && !$bnor_safe_to_resume) || ($boot_hook_entered && !$bnh_safe_to_resume)}')
source=source.replace('native_reader_failed','reader_or_hook_failed').replace(
    'Native reader failed: automatic GLOBAL suppressed','Reader or hook failed: automatic GLOBAL suppressed')
anchor='        set boot_fresh_process_required 1\n'
assert source.count(anchor)==1
source=source.replace(anchor,'''        if {$boot_hook_entered && $bnh_safe_to_resume} {
            # A fresh boot must produce the marker itself. Clear DCRDR after
            # all core transfers; FPB/catch removal uses MMIO only.
            boot_stable_halt
            boot_put 0xe000edf8 0 boot_dcrdr_possible
            if {[boot_word 0xe000edf8] != 0} { error "Pre-boot marker clear failed" }
            boot_log "pre_GLOBAL_DCRDR_cleared 1"
        }
'''+anchor)
out=ROOT/f'diagnostics/mcu-boot-hook-{args.mode}-session.cfg'
out.write_text(source)
print(f'Prepared fixed hook {args.mode} session; no target execution')
