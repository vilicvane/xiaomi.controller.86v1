"""Freeze separately reviewed broker inputs offline, after root closes reviews.

This command does not review code or grant approval. Exact review artifacts
and the successful current writer mock summary must be supplied explicitly.
"""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def within_root(value):
    path = (ROOT / value).resolve()
    assert path.is_relative_to(ROOT), 'Freeze dependency leaves workspace'
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--review', nargs=2, metavar=('PATH', 'SHA256'), action='append', required=True)
    parser.add_argument('--offline-summary', nargs=2, metavar=('PATH', 'SHA256'), required=True)
    args = parser.parse_args()
    assert len(args.review) >= 2, 'Supply independent program and writer review artifacts'
    manifest_name = 'analysis/display-takeover/native-ui-broker-patch-inputs-1.50.10.json'
    manifest_path = ROOT / manifest_name
    assert digest(manifest_path) == args.manifest_sha256, 'Explicit reviewed manifest drift'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['program']['entry'] == '0x3804b2f5'
    assert manifest['program']['start'] == '0x3804b108'
    assert manifest['program']['container_end_exclusive'] == '0x3804bc98'
    assert manifest['install_order'] == ['code', 'entry'] and manifest['restore_order'] == ['entry', 'code']
    files = [
        manifest_name,
        'analysis/display-takeover/native-ui-broker.c',
        'analysis/display-takeover/native-ui-broker-entry.S',
        'analysis/display-takeover/native-ui-broker.ld',
        'analysis/display-takeover/build-native-ui-broker.sh',
        'analysis/display-takeover/key3-gesture.h',
        'analysis/display-takeover/test-key3-gesture.c',
        'analysis/display-takeover/key3-gesture-offline-result.json',
        'analysis/display-takeover/test_ui_broker_arm.py',
        'analysis/display-takeover/ui-broker-arm-offline-result.json',
        'analysis/display-takeover/native-ui-broker.elf',
        'analysis/display-takeover/native-ui-broker.bin',
        'analysis/persistence/prepare_native_ui_broker_inputs.py',
        'analysis/persistence/run_native_ui_broker_firmware.py',
        'diagnostics/swd-memory.cfg',
        'diagnostics/swd-dap.cfg',
        'diagnostics/boot-watchdog-stop.cfg',
        'diagnostics/boot-nor-read-runner.cfg',
        'analysis/persistence/boot-nor-read-runner-data.cfg',
        'diagnostics/boot-nor-native-ui-broker-runner.cfg',
        'diagnostics/boot-nor-native-ui-broker-stage-inputs.cfg',
        'diagnostics/mcu-native-ui-broker-install-session.cfg',
        'diagnostics/mcu-native-ui-broker-restore-session.cfg',
        'diagnostics/read-native-ui-broker-state.cfg',
        'analysis/persistence/native-ui-broker-writer-preparation.json',
        'analysis/persistence/test_native_ui_broker_runner_offline.py',
        'analysis/persistence/mock_boot_read_runner.tcl',
        'tools/xpack-openocd-0.12.0-7/bin/openocd.exe',
        manifest['firmware']['path'],
    ]
    for sector in manifest['sectors'].values():
        for state in ('original', 'patched'):
            item = sector[state]
            path = within_root(item['path'])
            assert len(path.read_bytes()) == item['bytes'] == 4096 and digest(path) == item['sha256']
            files.append(item['path'])
    assert digest(within_root(manifest['program']['path'])) == manifest['program']['sha256']
    assert digest(within_root(manifest['program']['elf'])) == manifest['program']['elf_sha256']
    arm = json.loads((ROOT / 'analysis/display-takeover/ui-broker-arm-offline-result.json').read_text())
    assert arm['passed'] and len(arm['checks']) >= 9
    assert arm['elf_sha256'] == manifest['program']['elf_sha256'], 'ARM test result belongs to another ELF'
    assert digest(within_root(manifest['firmware']['path'])) == manifest['firmware']['sha256']
    for mode in ('install', 'restore'):
        cfg = (ROOT / f'diagnostics/mcu-native-ui-broker-{mode}-session.cfg').read_text()
        assert cfg.count(f'nub_run_native_ui_broker $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$nub_safe_to_resume || !$nub_app_complete))' in cfg
        assert 'automatic GLOBAL suppressed' in cfg
        assert 'boot_stop_aon_watchdog' in cfg and 'bnor_run_read_probe' in cfg
    supplied = args.review + [args.offline_summary]
    artifacts = []
    for name, expected in supplied:
        path = within_root(name)
        assert digest(path) == expected, 'Supplied review artifact changed: ' + name
        assert path.stat().st_size, 'Empty review artifact'
        normalized = path.relative_to(ROOT).as_posix()
        files.append(normalized)
        artifacts.append({'path': normalized, 'sha256': expected})
        # Review input hashes must still match the current reviewed materials;
        # reports may use paths relative to workspace or their own directory.
        review = json.loads(path.read_text())
        for item, reviewed_sha in review.get('reviewed_inputs', {}).items():
            candidates = [ROOT / item, path.parent / item]
            actual = next((candidate for candidate in candidates if candidate.is_file()), None)
            assert actual is not None and actual.resolve().is_relative_to(ROOT)
            assert digest(actual) == reviewed_sha, 'Reviewed input changed: ' + item
    summary = json.loads(within_root(args.offline_summary[0]).read_text())
    assert summary['all_passed'] and len(summary['cases']) >= 33, 'Current payload writer mocks incomplete'
    for name, expected in summary['source_sha256'].items():
        assert digest(within_root(name)) == expected, 'Offline writer inputs changed after test'
    for label, sector in (('code', 'code'), ('table', 'entry')):
        for state in ('original', 'patched'):
            assert summary['independent_sector_sha256'][label + '_' + state] == manifest['sectors'][sector][state]['sha256']
    # Capture all first-party broker headers too; no silent unfrozen include.
    files.extend(path.relative_to(ROOT).as_posix() for path in (ROOT / 'analysis/display-takeover').glob('native-ui-broker*.h'))
    hashes = {name: digest(within_root(name)) for name in dict.fromkeys(files)}
    result = {'scope': 'Exact independently reviewed 1.50.10 native UI broker, original/broker baselines only; two NOR sectors',
              'review_artifacts': artifacts, 'sha256': hashes}
    path = ROOT / 'analysis/persistence/native-ui-broker-frozen-inputs.json'
    assert not path.exists(), 'Existing freeze is immutable; use a new reviewed version instead'
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Frozen {len(hashes)} separate broker inputs offline; no hardware access.')


if __name__ == '__main__':
    main()
