"""Bind reviewed GitHub tap inputs offline; never alter prior freezes or access hardware.

Freezing records already-completed review and current-payload test evidence; it
does not grant approval. A frozen tap set cannot be overwritten in place.
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
    parser.add_argument('--writer-review', nargs=2, metavar=('PATH', 'SHA256'), required=True)
    parser.add_argument('--aux-baseline-proof', nargs=2, metavar=('PATH', 'SHA256'), required=True)
    parser.add_argument('--dependency', nargs=2, metavar=('PATH', 'SHA256'), action='append', default=[])
    args = parser.parse_args()
    freeze_path = ROOT / 'analysis/persistence/native-github-tap-fast-frozen-inputs.json'
    assert not freeze_path.exists(), 'Existing freeze is immutable; use a new reviewed version instead'
    assert len(args.review) >= 2, 'Supply independent program and writer review artifacts'
    manifest_name = 'analysis/persistence/native-github-tap-fast-patch-inputs-1.50.10.json'
    manifest_path = ROOT / manifest_name
    assert digest(manifest_path) == args.manifest_sha256, 'Explicit reviewed manifest drift'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['cold_poweroff_verification'] == {'status': 'skipped_by_user_request', 'requested': False}
    assert manifest['local_only_session_configs'] == ['diagnostics/mcu-native-github-tap-fast-install-session.cfg',
                                                      'diagnostics/mcu-native-github-tap-fast-restore-session.cfg']
    assert manifest['program']['entry'] == '0x3804b2f5'
    assert manifest['program']['start'] == '0x3804b108'
    assert manifest['program']['container_end_exclusive'] == '0x3804be70'
    assert manifest['program']['container_bytes'] == 0x3804be70 - 0x3804b108
    assert manifest['install_order'] == ['aux', 'code', 'entry'] and manifest['restore_order'] == ['entry', 'code', 'aux']
    assert manifest['runtime_context'] == {'bytes': 184, 'words': 46, 'feedback_ms_offset': 176, 'feedback_pending_offset': 180,
                                          'animation_from_offset': 164, 'pending_offset': 168, 'phase_offset': 172}
    feedback = manifest['program']['feedback']
    assert feedback['start'] == '0x3807a764' and feedback['container_end_exclusive'] == '0x3807a920'
    assert feedback['file_start'] == '0x95a768' and feedback['container_bytes'] == 444
    assert 0 < feedback['bytes'] <= 444
    assert digest(within_root(feedback['path'])) == feedback['sha256']
    assert within_root(feedback['path']).stat().st_size == feedback['bytes']
    assert manifest['aux_live_baseline']['path'] == args.aux_baseline_proof[0]
    assert manifest['aux_live_baseline']['sha256'] == args.aux_baseline_proof[1]
    proof = json.loads(within_root(args.aux_baseline_proof[0]).read_text())
    assert proof['read_only_live_baseline'] and proof['matches_exact_stock_backup_page']
    assert proof['target_writes'] == proof['halt_reset_native_calls'] == 0
    assert proof['live_sha256'] == 'fe815dee80d04a6f4b35f238a4c0d05063ecb219ff53132534c71f08ef47f185'
    peer = json.loads(within_root(args.writer_review[0]).read_text())
    assert peer['passed'], 'Independent three-page writer peer review did not pass'
    for name in ('analysis/persistence/native_github_tap_fast_three_page_writer.py',
                 'analysis/persistence/prepare_native_github_tap_fast_inputs.py',
                 'analysis/persistence/test_native_github_tap_fast_runner_offline.py',
                 'diagnostics/boot-nor-native-github-tap-fast-runner.cfg',
                 'diagnostics/boot-nor-native-github-tap-fast-stage-inputs.cfg'):
        assert peer['reviewed_inputs'][name] == digest(within_root(name)), 'Peer review does not bind changed three-page input: ' + name
    assert manifest['rollback']['kind'] == 'native-github-tap-v1'
    tap_freeze_path = within_root(manifest['rollback']['freeze'])
    assert digest(tap_freeze_path) == manifest['rollback']['freeze_sha256']
    tap_freeze = json.loads(tap_freeze_path.read_text())
    card_freeze_path = within_root('analysis/persistence/native-github-card-frozen-inputs.json')
    card_freeze = json.loads(card_freeze_path.read_text())
    broker_freeze_path = within_root('analysis/persistence/native-ui-broker-frozen-inputs.json')
    broker_freeze = json.loads(broker_freeze_path.read_text())
    drawer_freeze_path = within_root('analysis/persistence/native-drawer-frozen-inputs.json')
    drawer_freeze = json.loads(drawer_freeze_path.read_text())
    ease_freeze_path = within_root('analysis/persistence/native-drawer-ease-frozen-inputs.json')
    ease_freeze = json.loads(ease_freeze_path.read_text())
    smooth_freeze_path = within_root('analysis/persistence/native-drawer-smooth-frozen-inputs.json')
    smooth_freeze = json.loads(smooth_freeze_path.read_text())
    for frozen in (broker_freeze, drawer_freeze, ease_freeze, smooth_freeze, card_freeze, tap_freeze):
        for name, expected in frozen['sha256'].items():
            assert digest(within_root(name)) == expected, 'Immutable prior input changed: ' + name
    files = [
        manifest_name,
        'analysis/display-takeover/native-github-tap-fast.c',
        'analysis/display-takeover/native-github-tap-fast-entry.S',
        'analysis/display-takeover/native-github-tap-fast.ld',
        'analysis/display-takeover/build-native-github-tap-fast.sh',
        'analysis/display-takeover/render_github_tap_reference.py',
        'analysis/display-takeover/native-github-tap-fast.elf',
        'analysis/display-takeover/native-github-tap-fast.bin',
        feedback['path'],
        'analysis/display-takeover/test_native_github_tap_arm.py',
        'analysis/display-takeover/test_native_github_card_arm.py',
        'analysis/display-takeover/test_native_drawer_smooth_arm.py',
        'analysis/display-takeover/test_native_drawer_ease_arm.py',
        'analysis/display-takeover/test_native_drawer_arm.py',
        'analysis/display-takeover/test_ui_broker_arm.py',
        'analysis/persistence/prepare_native_github_tap_fast_inputs.py',
        'analysis/persistence/run_native_github_tap_fast_firmware.py',
        'analysis/persistence/freeze_native_github_tap_fast_inputs.py',
        'analysis/persistence/review_native_github_tap_fast_installer.py',
        'analysis/persistence/native_github_tap_fast_three_page_writer.py',
        'diagnostics/swd-memory.cfg',
        'diagnostics/swd-dap.cfg',
        'diagnostics/boot-watchdog-stop.cfg',
        'diagnostics/boot-nor-read-runner.cfg',
        'analysis/persistence/boot-nor-read-runner-data.cfg',
        'diagnostics/boot-nor-native-github-tap-fast-runner.cfg',
        'diagnostics/boot-nor-native-github-tap-fast-stage-inputs.cfg',
        'diagnostics/mcu-native-github-tap-fast-install-session.cfg',
        'diagnostics/mcu-native-github-tap-fast-restore-session.cfg',
        'diagnostics/read-native-github-tap-fast-state.cfg',
        'diagnostics/read-native-github-tap-fast-runtime.cfg',
        'analysis/persistence/native-github-tap-fast-writer-preparation.json',
        'analysis/persistence/test_native_github_tap_fast_runner_offline.py',
        'analysis/persistence/mock_boot_read_runner.tcl',
        'scripts/Set-PanelNativeGitHubTapFast.ps1',
        'tools/xpack-openocd-0.12.0-7/bin/openocd.exe',
        manifest['firmware']['path'],
        manifest['rollback']['freeze'],
        'analysis/persistence/native-ui-broker-frozen-inputs.json',
        'analysis/persistence/native-drawer-frozen-inputs.json',
        'analysis/persistence/native-drawer-ease-frozen-inputs.json',
        'analysis/persistence/native-drawer-smooth-frozen-inputs.json',
        'analysis/persistence/native-github-card-frozen-inputs.json',
        args.arm_test,
    ]
    for label, sector in manifest['sectors'].items():
        baseline_source = within_root(sector['baseline_source'])
        assert sector['baseline_kind'] == 'verified-native-github-tap-v1'
        assert digest(baseline_source) == sector['original']['sha256']
        assert tap_freeze['sha256'][sector['baseline_source']] == sector['original']['sha256']
        assert baseline_source.read_bytes() == within_root(sector['original']['path']).read_bytes()
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
        cfg = (ROOT / f'diagnostics/mcu-native-github-tap-fast-{mode}-session.cfg').read_text()
        assert cfg.count(f'ngtf_run_native_github_tap_fast $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$ngtf_safe_to_resume || !$ngtf_app_complete))' in cfg
        assert 'automatic GLOBAL suppressed' in cfg
        assert 'boot_stop_aon_watchdog' in cfg and 'bnor_run_read_probe' in cfg
    supplied = args.review + [args.offline_summary, args.arm_summary, args.capacity_review, args.writer_review,
                             args.aux_baseline_proof] + args.dependency
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
                # These inputs remain checked at execution, not merely once
                # while freezing the review artifact (including .map/.md).
                files.append(actual.resolve().relative_to(ROOT).as_posix())
    arm = json.loads(within_root(args.arm_summary[0]).read_text())
    assert arm['passed'] and arm['check_count'] == len(arm['checks']) >= 53, 'Current actual-ELF segmented fast-tap model incomplete'
    assert arm['elf_sha256'] == manifest['program']['elf_sha256'], 'ARM model belongs to another ELF'
    assert arm['source_sha256'] == digest(within_root('analysis/display-takeover/native-github-tap-fast.c')), 'ARM model source drift'
    assert arm['test_sha256'] == digest(within_root(args.arm_test)), 'ARM model test drift'
    assert arm['reference_sha256'] == digest(within_root('analysis/display-takeover/render_github_tap_reference.py')), 'ARM model pixel oracle drift'
    assert arm['logo_header_sha256'] == digest(within_root('analysis/display-takeover/github-tap-logo.h')), 'ARM model logo header drift'
    assert arm['context_bytes'] == manifest['runtime_context']['bytes'] == 184
    assert arm['feedback_ms_offset'] == 176 and arm['feedback_pending_offset'] == 180
    assert arm['feedback_pending_states'] == manifest['feedback_pending_states'] == {
        '0': 'accepted_and_clock_anchored', '1': 'new_count_waiting_successful_pan',
        '2': 'successful_pan_waiting_fresh_clock'}
    assert arm['main_bytes'] == manifest['program']['bytes'] and arm['main_sha256'] == manifest['program']['sha256']
    assert arm['feedback_bytes'] == feedback['bytes'] and arm['feedback_sha256'] == feedback['sha256']
    summary = json.loads(within_root(args.offline_summary[0]).read_text())
    assert summary['all_passed'] and len(summary['cases']) >= 68, 'Current three-page tap writer mocks incomplete'
    for name, expected in summary['source_sha256'].items():
        assert digest(within_root(name)) == expected, 'Offline writer inputs changed after test'
    for label, sector in (('code', 'code'), ('table', 'entry'), ('aux', 'aux')):
        for state in ('original', 'patched'):
            assert summary['independent_sector_sha256'][label + '_' + state] == manifest['sectors'][sector][state]['sha256']
    # Discover all local quoted includes transitively. A helper header cannot
    # silently change after review while the main C file stays identical.
    pending = [within_root('analysis/display-takeover/native-github-tap-fast.c')]
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
    result = {'scope': 'Exact reviewed 1.50.10 segmented fast GitHub tap; three NOR pages, exact tap-v1 or fast-tap triples only; restore the precise original tap-v1 triple',
              'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
              'local_only_session_configs': manifest['local_only_session_configs'],
              'review_artifacts': artifacts, 'sha256': hashes}
    freeze_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Frozen {len(hashes)} separate GitHub tap inputs offline; no hardware access.')


if __name__ == '__main__':
    main()
