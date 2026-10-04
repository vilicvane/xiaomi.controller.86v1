"""Execute only a frozen drawer operation; restore returns the verified drawer v1."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=('install', 'restore'))
parser.add_argument('--execute', action='store_true')
parser.add_argument('--verify-existing-capture', type=Path,
                    help='Only read live state and verify a completed saved operation; no write/reset')
args = parser.parse_args()
freeze_path = ROOT / 'analysis/persistence/native-drawer-ease-frozen-inputs.json'
freeze = json.loads(freeze_path.read_text())
for name, expected in freeze['sha256'].items():
    actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f'Frozen input changed before device access: {name}')
if not args.execute and args.verify_existing_capture is None:
    print('All frozen inputs verified. Add --execute to run the fixed device operation.')
    raise SystemExit(0)
stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
if args.verify_existing_capture is None:
    capture = ROOT / f'analysis/persistence/native-drawer-ease-{args.mode}-session-{stamp}'
    capture.mkdir()
else:
    capture = args.verify_existing_capture.resolve()
    assert capture.is_relative_to(ROOT / 'analysis/persistence')
    assert capture.name.startswith(f'native-drawer-ease-{args.mode}-session-')
    assert capture.is_dir()
exe = ROOT / 'tools/xpack-openocd-0.12.0-7/bin/openocd.exe'
flags = subprocess.CREATE_NO_WINDOW

def run(cfg, label):
    log = capture / f'{label}.txt'
    command = [str(exe), '-s', 'diagnostics', '-f', cfg, '-l', log.relative_to(ROOT).as_posix()]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, creationflags=flags)
    (capture / f'{label}-console.txt').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(f'{label} failed ({result.returncode}); inspect {log}. No automatic retry/reset.')
    return log.read_text()

result = {'mode': args.mode, 'capture': str(capture), 'passed': False,
          'scope': 'NOR sectors92b000/ccd000 only; native boot task; restore returns verified drawer v1'}
try:
    if args.verify_existing_capture is None:
        print(f'Running fixed native drawer {args.mode}; keep USB/panel power connected.', flush=True)
        run(f'diagnostics/mcu-native-drawer-ease-{args.mode}-session.cfg', 'operation')
        outer = (ROOT / f'diagnostics/mcu-native-drawer-ease-{args.mode}-result.txt').read_text()
        (capture / 'boot-outer-result.txt').write_text(outer)
    else:
        print('Read-only verification of saved operation; no write or reset.', flush=True)
        outer = (capture / 'boot-outer-result.txt').read_text()
    assert 'native_app_safe_to_resume 1' in outer
    assert 'native_app_complete 1' in outer
    assert f'phase native_app_{args.mode}_verified' in outer or 'phase cleanup_global_requested' in outer
    assert 'cleanup_global_transport_error 0' in outer and 'cleanup_dispatch_complete 1' in outer
    assert not re.search(r'^(test_error|cleanup_error) ', outer, re.MULTILINE)
    # GLOBAL may briefly make the debug port unavailable. Retry only a new
    # read-only process after this exact DP connection failure; never replay
    # the installation, reset, native caller or a partially closed operation.
    for attempt in range(1, 5):
        label = f'fresh-state-{attempt}'
        try:
            state = run('diagnostics/read-native-drawer-ease-state.cfg', label)
            (capture / 'fresh-state.txt').write_text(state)
            result['read_only_connection_attempts'] = attempt
            break
        except RuntimeError:
            log = (capture / f'{label}.txt').read_text()
            if attempt == 4 or 'Error connecting DP: cannot read IDR' not in log:
                raise
            time.sleep(1)
    manifest = json.loads((ROOT / 'analysis/persistence/native-drawer-ease-patch-inputs-1.50.10.json').read_text())
    expected_state = 'patched' if args.mode == 'install' else 'original'
    for name in ('code', 'entry'):
        data = (ROOT / f'analysis/persistence/native-drawer-ease-live-{name}-sector.bin').read_bytes()
        (capture / f'live-{name}-sector.bin').write_bytes(data)
        actual = hashlib.sha256(data).hexdigest()
        assert actual == manifest['sectors'][name][expected_state]['sha256'], name+' whole sector readback'
        result[name+'_sha256'] = actual
    def word(label):
        return int(re.search(r'NATIVE_DRAWER_EASE_'+label+r' (0x[0-9a-fA-F]+)', state)[1], 16)
    assert not word('MCU_DHCSR') & 0x20000, 'MCU still halted'
    assert not word('MCU_DEMCR') & 1, 'Reset catch still enabled'
    assert word('FPBCOMP0') == 0, 'Temporary breakpoint remains'
    expected_entry = 0x3804b2f5  # Drawer v1 and ease share the same fixed UI entry.
    assert word('ENTRY') == expected_entry
    assert word('SHOWLOGO_ENTRY') == 0x3804b111
    assert word('FACLVGL_ENTRY') == 0x3804b111
    assert word('NTPCSTATUS_ENTRY') == 0x3804b109
    assert word('WIFI_RECORDER_ENTRY') == 0x3804b109
    result['entry'] = hex(expected_entry)
    result['mcu_running'] = True
    result['passed'] = True
except Exception as error:
    result['error'] = type(error).__name__+': '+str(error)
finally:
    (capture / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
if not result['passed']:
    raise SystemExit(1)
