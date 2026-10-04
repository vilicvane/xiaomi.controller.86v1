"""Record reviewed install/revert dependencies; offline, no device access."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
manifest_path = 'analysis/display-takeover/native-counter-patch-inputs-1.50.10.json'
manifest = json.loads((ROOT / manifest_path).read_text())
assert hashlib.sha256((ROOT / manifest_path).read_bytes()).hexdigest() == '55fbb71be4fe4abd40a245f72f303073cc5afce0288a5aa238bf35ea475af4ed'
files = [
    manifest_path,
    'analysis/display-takeover/native-counter.c',
    'analysis/display-takeover/native-counter-entry.S',
    'analysis/display-takeover/native-counter.ld',
    'analysis/display-takeover/native-counter.elf',
    'analysis/display-takeover/native-counter.bin',
    'analysis/persistence/run_native_counter_firmware.py',
    'diagnostics/swd-memory.cfg',
    'diagnostics/swd-dap.cfg',
    'diagnostics/boot-watchdog-stop.cfg',
    'diagnostics/boot-nor-read-runner.cfg',
    'analysis/persistence/boot-nor-read-runner-data.cfg',
    'diagnostics/boot-nor-native-app-runner.cfg',
    'diagnostics/boot-nor-native-app-stage-inputs.cfg',
    'diagnostics/mcu-native-counter-install-session.cfg',
    'diagnostics/mcu-native-counter-restore-session.cfg',
    'diagnostics/read-native-counter-state.cfg',
]
for sector in manifest['sectors'].values():
    for state in ('original', 'patched'):
        artifact = sector[state]
        assert hashlib.sha256((ROOT / artifact['path']).read_bytes()).hexdigest() == artifact['sha256']
        files.append(artifact['path'])
for mode in ('install', 'restore'):
    cfg = (ROOT / f'diagnostics/mcu-native-counter-{mode}-session.cfg').read_text()
    assert cfg.count(f'bna_run_native_app $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
    assert '($boot_app_entered && (!$bna_safe_to_resume || !$bna_app_complete))' in cfg
    assert 'automatic GLOBAL suppressed' in cfg
    assert 'boot_stop_aon_watchdog' in cfg and 'bnor_run_read_probe' in cfg
result = {'scope': 'Exact 1.50.10 native task install/revert inputs',
          'sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}}
path = ROOT / 'analysis/persistence/native-counter-frozen-inputs.json'
path.write_text(json.dumps(result, indent=2)+'\n')
print(f'Frozen {len(files)} inputs; no device access.')
