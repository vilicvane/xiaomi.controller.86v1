"""Bind reviewed drawer smooth inputs offline; never alter prior freezes or access hardware.

Freezing records already-completed review and current-payload test evidence; it
does not grant approval. A frozen drawer set cannot be overwritten in place.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

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
    parser.add_argument('--arm-summary', nargs=2, metavar=('PATH', 'SHA256'), required=True)
    parser.add_argument('--arm-test', required=True)
    parser.add_argument('--capacity-review', nargs=2, metavar=('PATH', 'SHA256'), required=True)
    parser.add_argument('--dependency', nargs=2, metavar=('PATH', 'SHA256'), action='append', default=[])
    args = parser.parse_args()
    freeze_path = ROOT / 'analysis/persistence/native-drawer-smooth-frozen-inputs.json'
    assert not freeze_path.exists(), 'Existing freeze is immutable; use a new reviewed version instead'
    assert len(args.review) >= 2, 'Supply independent program and writer review artifacts'
    manifest_name = 'analysis/persistence/native-drawer-smooth-patch-inputs-1.50.10.json'
    manifest_path = ROOT / manifest_name
    assert digest(manifest_path) == args.manifest_sha256, 'Explicit reviewed manifest drift'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['program']['entry'] == '0x3804b2f5'
    assert manifest['program']['start'] == '0x3804b108'
    assert manifest['program']['container_end_exclusive'] == '0x3804be70'
    assert manifest['program']['container_bytes'] == 0x3804be70 - 0x3804b108
    assert manifest['install_order'] == ['code', 'entry'] and manifest['restore_order'] == ['entry', 'code']
    assert manifest['rollback']['kind'] == 'native-drawer-ease-v1'
    ease_freeze_path = within_root(manifest['rollback']['freeze'])
    assert digest(ease_freeze_path) == manifest['rollback']['freeze_sha256']
    ease_freeze = json.loads(ease_freeze_path.read_text())
    broker_freeze_path = within_root('analysis/persistence/native-ui-broker-frozen-inputs.json')
    broker_freeze = json.loads(broker_freeze_path.read_text())
    drawer_freeze_path = within_root('analysis/persistence/native-drawer-frozen-inputs.json')
    drawer_freeze = json.loads(drawer_freeze_path.read_text())
    for frozen in (broker_freeze, drawer_freeze, ease_freeze):
        for name, expected in frozen['sha256'].items():
            assert digest(within_root(name)) == expected, 'Immutable prior input changed: ' + name
    files = [
        manifest_name,
        'analysis/display-takeover/native-drawer-smooth.c',
        'analysis/display-takeover/native-drawer-smooth-entry.S',
        'analysis/display-takeover/native-drawer-smooth.ld',
        'analysis/display-takeover/build-native-drawer-smooth.sh',
        'analysis/display-takeover/native-drawer-smooth.elf',
        'analysis/display-takeover/native-drawer-smooth.bin',
        'analysis/display-takeover/test_native_drawer_ease_arm.py',
        'analysis/display-takeover/test_native_drawer_arm.py',
        'analysis/display-takeover/test_ui_broker_arm.py',
        'analysis/persistence/prepare_native_drawer_smooth_inputs.py',
        'analysis/persistence/run_native_drawer_smooth_firmware.py',
        'analysis/persistence/freeze_native_drawer_smooth_inputs.py',
        'analysis/persistence/review_native_drawer_smooth_installer.py',
        'diagnostics/swd-memory.cfg',
        'diagnostics/swd-dap.cfg',
        'diagnostics/boot-watchdog-stop.cfg',
        'diagnostics/boot-nor-read-runner.cfg',
        'analysis/persistence/boot-nor-read-runner-data.cfg',
        'diagnostics/boot-nor-native-drawer-smooth-runner.cfg',
        'diagnostics/boot-nor-native-drawer-smooth-stage-inputs.cfg',
        'diagnostics/mcu-native-drawer-smooth-install-session.cfg',
        'diagnostics/mcu-native-drawer-smooth-restore-session.cfg',
        'diagnostics/read-native-drawer-smooth-state.cfg',
        'diagnostics/read-native-drawer-smooth-runtime.cfg',
        'analysis/persistence/native-drawer-smooth-writer-preparation.json',
        'analysis/persistence/test_native_drawer_smooth_runner_offline.py',
        'analysis/persistence/mock_boot_read_runner.tcl',
        'scripts/Set-PanelNativeDrawerSmooth.ps1',
        'tools/xpack-openocd-0.12.0-7/bin/openocd.exe',
        manifest['firmware']['path'],
        manifest['rollback']['freeze'],
        'analysis/persistence/native-ui-broker-frozen-inputs.json',
        'analysis/persistence/native-drawer-frozen-inputs.json',
        args.arm_test,
    ]
    for label, sector in manifest['sectors'].items():
        assert sector['baseline_kind'] == 'verified-native-drawer-ease-v1'
        baseline_source = within_root(sector['baseline_source'])
        assert digest(baseline_source) == sector['original']['sha256']
        assert ease_freeze['sha256'][sector['baseline_source']] == sector['original']['sha256']
        files.append(sector['baseline_source'])
        for state in ('original', 'patched'):
            item = sector[state]
            path = within_root(item['path'])
            assert len(path.read_bytes()) == item['bytes'] == 4096 and digest(path) == item['sha256']
            files.append(item['path'])
    assert manifest['sectors']['entry']['original']['sha256'] == manifest['sectors']['entry']['patched']['sha256']
    assert manifest['sectors']['entry']['mutations'] == []
    assert digest(within_root(manifest['program']['path'])) == manifest['program']['sha256']
    assert digest(within_root(manifest['program']['elf'])) == manifest['program']['elf_sha256']
    assert digest(within_root(manifest['firmware']['path'])) == manifest['firmware']['sha256']
    for mode in ('install', 'restore'):
        cfg = (ROOT / f'diagnostics/mcu-native-drawer-smooth-{mode}-session.cfg').read_text()
        assert cfg.count(f'ndrs_run_native_drawer_smooth $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$ndrs_safe_to_resume || !$ndrs_app_complete))' in cfg
        assert 'automatic GLOBAL suppressed' in cfg
        assert 'boot_stop_aon_watchdog' in cfg and 'bnor_run_read_probe' in cfg
    supplied = args.review + [args.offline_summary, args.arm_summary, args.capacity_review] + args.dependency
    artifacts = []
    for name, expected in supplied:
        path = within_root(name)
        assert digest(path) == expected, 'Supplied review/evidence artifact changed: ' + name
        assert path.stat().st_size, 'Empty review/evidence artifact'
        normalized = path.relative_to(ROOT).as_posix()
        files.append(normalized)
        artifacts.append({'path': normalized, 'sha256': expected})
        if path.suffix == '.json':
            evidence = json.loads(path.read_text())
            for item, reviewed_sha in evidence.get('reviewed_inputs', {}).items():
                candidates = [ROOT / item, path.parent / item]
                actual = next((candidate for candidate in candidates if candidate.is_file()), None)
                assert actual is not None and actual.resolve().is_relative_to(ROOT)
                assert digest(actual) == reviewed_sha, 'Reviewed input changed: ' + item
    arm = json.loads(within_root(args.arm_summary[0]).read_text())
    assert arm['passed'] and len(arm['checks']) >= 9, 'Current actual-ELF model incomplete'
    assert arm['elf_sha256'] == manifest['program']['elf_sha256'], 'ARM model belongs to another ELF'
    assert arm['source_sha256'] == digest(within_root('analysis/display-takeover/native-drawer-smooth.c')), 'ARM model source drift'
    assert arm['test_sha256'] == digest(within_root(args.arm_test)), 'ARM model test drift'
    summary = json.loads(within_root(args.offline_summary[0]).read_text())
    assert summary['all_passed'] and len(summary['cases']) >= 41, 'Current drawer writer mocks incomplete'
    for name, expected in summary['source_sha256'].items():
        assert digest(within_root(name)) == expected, 'Offline writer inputs changed after test'
    for label, sector in (('code', 'code'), ('table', 'entry')):
        for state in ('original', 'patched'):
            assert summary['independent_sector_sha256'][label + '_' + state] == manifest['sectors'][sector][state]['sha256']
    # Discover all local quoted includes transitively. A helper header cannot
    # silently change after review while the main C file stays identical.
    pending = [within_root('analysis/display-takeover/native-drawer-smooth.c')]
    seen = set()
    while pending:
        source = pending.pop()
        if source in seen:
            continue
        seen.add(source)
        files.append(source.relative_to(ROOT).as_posix())
        for include in re.findall(r'^\s*#\s*include\s*"([^"\n]+)"', source.read_text(), re.MULTILINE):
            path = (source.parent / include).resolve()
            assert path.is_relative_to(ROOT) and path.is_file(), 'Local include leaves reviewed workspace or is missing'
            pending.append(path)
    hashes = {name: digest(within_root(name)) for name in dict.fromkeys(files)}
    result = {'scope': 'Exact independently reviewed 1.50.10 native drawer smooth, verified ease-v1/smooth baselines only; two NOR sectors; restore ease v1',
              'review_artifacts': artifacts, 'sha256': hashes}
    freeze_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Frozen {len(hashes)} separate drawer smooth inputs offline; no hardware access.')


if __name__ == '__main__':
    main()
