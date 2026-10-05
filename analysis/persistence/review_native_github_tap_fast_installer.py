"""Reproduce the GitHub-tap three-page installer self-check offline; no device access."""
from pathlib import Path
import ast
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name):
    return json.loads((ROOT / name).read_text())


def main():
    manifest_name = 'analysis/persistence/native-github-tap-fast-patch-inputs-1.50.10.json'
    manifest = load(manifest_name)
    assert manifest['cold_poweroff_verification'] == {'status': 'skipped_by_user_request', 'requested': False}
    summary_name = 'analysis/persistence/offline-native-github-tap-fast-runner/latest-summary.json'
    summary = load(summary_name)
    # Bind the immutable completed run rather than the convenient latest alias.
    run_summary = ROOT / Path(summary['cases'][0]['host_log']).parent / 'summary.json'
    assert run_summary.resolve().is_relative_to(ROOT / 'analysis/persistence/offline-native-github-tap-fast-runner')
    assert json.loads(run_summary.read_text()) == summary
    summary_name = run_summary.relative_to(ROOT).as_posix()
    freeze_names = ['analysis/persistence/native-ui-broker-frozen-inputs.json',
                    'analysis/persistence/native-drawer-frozen-inputs.json',
                    'analysis/persistence/native-drawer-ease-frozen-inputs.json',
                    'analysis/persistence/native-drawer-smooth-frozen-inputs.json',
                    'analysis/persistence/native-github-card-frozen-inputs.json',
                    'analysis/persistence/native-github-tap-frozen-inputs.json']
    freezes = [load(name) for name in freeze_names]
    for frozen in freezes:
        for name, expected in frozen['sha256'].items():
            assert digest(ROOT / name) == expected, name
    checks = ['All six relevant previous frozen input sets retain their exact bytes; stock NOR provenance remains SHA-checked.']
    for label in ('code', 'entry', 'aux'):
        item = manifest['sectors'][label]
        original = (ROOT / item['original']['path']).read_bytes()
        patched = (ROOT / item['patched']['path']).read_bytes()
        assert len(original) == len(patched) == 4096
        assert original == (ROOT / item['baseline_source']).read_bytes()
        assert digest(ROOT / item['original']['path']) == freezes[5]['sha256'][item['baseline_source']]
        assert digest(ROOT / item['patched']['path']) == item['patched']['sha256']
        if label == 'code':
            program = (ROOT / manifest['program']['path']).read_bytes()
            assert digest(ROOT / manifest['program']['path']) == manifest['program']['sha256']
            assert patched[0x10c:0x10c + len(program)] == program
            assert patched[:0x10c] == original[:0x10c]
            assert patched[0x10c + len(program):] == original[0x10c + len(program):]
            assert patched[0xe74:] == original[0xe74:]
        elif label == 'aux':
            auxiliary = manifest['program']['feedback']
            payload = (ROOT / auxiliary['path']).read_bytes()
            assert digest(ROOT / auxiliary['path']) == auxiliary['sha256']
            assert 0 < len(payload) <= 444
            assert patched[0x768:0x768 + len(payload)] == payload
            assert patched[:0x768] == original[:0x768]
            assert patched[0x768 + len(payload):] == original[0x768 + len(payload):]
            assert patched[0x924:] == original[0x924:]
        else:
            assert original == patched and item['mutations'] == []
            assert struct.unpack_from('<I', patched, 0xd2c)[0] == 0x3804b109
    checks.append('Rollback fixtures are exact frozen tap-v1 main/entry/auxiliary full pages. Main and auxiliary changes stay inside declared spans; entry is identical, main tail and auxiliary helpers remain untouched.')
    writer = (ROOT / 'diagnostics/boot-nor-native-github-tap-fast-runner.cfg').read_text()
    old_writer = (ROOT / 'diagnostics/boot-nor-native-github-tap-runner.cfg').read_text()
    inverse = (writer.replace('native-github-tap-fast', 'native-github-tap')
               .replace('native_github_tap_fast', 'native_github_tap')
               .replace('ngtfi_', 'ngti_').replace('ngtf_', 'ngt_'))
    inverse = inverse.replace('Install requires all three exact tap-v1 sector baselines',
                              'Install requires all three exact card-v1 sector baselines')
    inverse = inverse.replace('Restore requires all three exact tap-v1 or all three exact github-tap-fast sector baselines',
                              'Restore requires all three exact card-v1 or all three exact github-tap sector baselines')
    inverse = inverse.replace('Restore v1 main references before returning the auxiliary slot to v1 tap.',
                              'Remove all main references before returning the auxiliary slot to stock.')
    assert inverse == old_writer
    checks.append('Entire native/public writer is exactly frozen tap v1 after namespace/path normalization and two explicitly listed baseline-error descriptions and one accurate rollback comment. No native callee, ABI, allowlist, protection, status, control-flow, readback, cache or completion-gate differences.')
    assert 'Install requires all three exact tap-v1 sector baselines' in writer
    assert 'Restore requires all three exact tap-v1 or all three exact github-tap-fast sector baselines' in writer
    assert writer.index('ngtf_write_sector $capture_dir install-aux') < writer.index('ngtf_write_sector $capture_dir install-code') < writer.index('ngtf_write_sector $capture_dir install-table')
    assert writer.index('ngtf_write_sector $capture_dir restore-table') < writer.index('ngtf_write_sector $capture_dir restore-code') < writer.index('ngtf_write_sector $capture_dir restore-aux')
    assert 'foreach sector {aux code table}' in writer and 'Whole three sectors changed after cache invalidation' in writer
    for mode in ('install', 'restore'):
        text = (ROOT / f'diagnostics/mcu-native-github-tap-fast-{mode}-session.cfg').read_text()
        inverse = (text.replace('native-github-tap-fast', 'native-github-tap')
                   .replace('native_github_tap_fast', 'native_github_tap')
                   .replace('ngtfi_', 'ngti_').replace('ngtf_', 'ngt_'))
        assert inverse == (ROOT / f'diagnostics/mcu-native-github-tap-{mode}-session.cfg').read_text()
    checks.append('Both outer MCU sessions are exact frozen GitHub tap v1 clones after namespace/path normalization, including fresh BOOT, isolated A7, watchdog stop, verified reader, completion gate and suppressed GLOBAL after uncertain native execution.')
    stages = (ROOT / 'diagnostics/boot-nor-native-github-tap-fast-stage-inputs.cfg').read_text()
    old_stages = (ROOT / 'diagnostics/boot-nor-native-github-tap-stage-inputs.cfg').read_text()
    executable = stages[stages.index('foreach ngtfi_name '):]
    inverse_stages = executable.replace('ngtfi_', 'ngti_').replace('ngtf_', 'ngt_')
    assert inverse_stages == old_stages[old_stages.index('foreach ngti_name '):]
    checks.append('The entire executable stage body is exactly frozen v1 tap after namespace normalization; only independently checked caller/page fixture array values differ.')
    words = re.search(r'set ngtfi_one_call_words \{([^}]+)\}', stages)[1].split()
    raw = struct.pack('<' + 'I' * len(words), *(int(word, 0) for word in words))
    native_sha = hashlib.sha256(raw).hexdigest()
    assert len(raw) == 168 and native_sha == 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'
    checks.append('The exact reviewed 168-byte one-call ARM payload remains intact. Native caller ABI is unchanged; exact auxiliary fixture and bounded auxiliary stage arguments are additional reviewed inputs.')
    assert summary['all_passed'] and len(summary['cases']) >= 68
    for name, expected in summary['source_sha256'].items():
        assert digest(ROOT / name) == expected
    for label, sector in [('code', 'code'), ('table', 'entry'), ('aux', 'aux')]:
        for state in ('original', 'patched'):
            assert summary['independent_sector_sha256'][label + '_' + state] == manifest['sectors'][sector][state]['sha256']
    checks.append('Current Jim cases pass, covering exact triple success, old-version/unknown/mixed triple refusal, auxiliary-first full-page/status gating, main-before-aux rollback, six cache closures, auxiliary/main/entry faults, bounded timeouts and no stale replay. Equal entry pages cannot identify the drawer variant; the code page must match.')
    for path in (ROOT / 'analysis/persistence').glob('*native_github_tap_fast*.py'):
        ast.parse(path.read_text())
    freeze_source = (ROOT / 'analysis/persistence/freeze_native_github_tap_fast_inputs.py').read_text()
    runner_source = (ROOT / 'analysis/persistence/run_native_github_tap_fast_firmware.py').read_text()
    assert 'assert not freeze_path.exists()' in freeze_source
    assert "arm['elf_sha256'] == manifest['program']['elf_sha256']" in freeze_source
    assert 'for frozen in (broker_freeze, drawer_freeze, ease_freeze, smooth_freeze, card_freeze, tap_freeze):' in freeze_source
    assert 'Conflicting frozen input hash:' in runner_source
    checks.append('Freeze rejects overwrites and binds all prior freezes, exact tap-v1 triple rollback, stock NOR, current ELF/BIN/pages, reviews, current ELF model, writer summary and local headers. The public runner rechecks all merged prior catalogs before any hardware access, including zero-execute mode.')
    files = [manifest_name, summary_name, *freeze_names,
             'analysis/persistence/prepare_native_github_tap_fast_inputs.py',
             'analysis/persistence/run_native_github_tap_fast_firmware.py',
             'analysis/persistence/freeze_native_github_tap_fast_inputs.py',
             'analysis/persistence/test_native_github_tap_fast_runner_offline.py',
             'analysis/persistence/review_native_github_tap_fast_installer.py',
             'analysis/persistence/native_github_tap_fast_three_page_writer.py',
             manifest['aux_live_baseline']['path'],
             'analysis/persistence/native-github-tap-fast-writer-preparation.json',
             'diagnostics/boot-nor-native-github-tap-fast-runner.cfg',
             'diagnostics/boot-nor-native-github-tap-fast-stage-inputs.cfg',
             'diagnostics/mcu-native-github-tap-fast-install-session.cfg',
             'diagnostics/mcu-native-github-tap-fast-restore-session.cfg',
             'diagnostics/read-native-github-tap-fast-state.cfg',
             'diagnostics/read-native-github-tap-fast-runtime.cfg',
             'scripts/Set-PanelNativeGitHubTapFast.ps1',
             'analysis/display-takeover/native-github-tap-fast.c',
             'analysis/display-takeover/native-github-tap-fast-entry.S',
             'analysis/display-takeover/native-github-tap-fast.ld',
             'analysis/display-takeover/build-native-github-tap-fast.sh',
             'analysis/display-takeover/github-tap-logo.h',
             'analysis/display-takeover/render_github_tap_reference.py',
             manifest['program']['path'], manifest['program']['elf'], manifest['program']['feedback']['path']]
    for sector in manifest['sectors'].values():
        files.extend([sector['baseline_source'], sector['original']['path'], sector['patched']['path']])
    report = {
        'scope': 'Fast GitHub tap installer and precise tap-v1 rollback only for this panel 1.50.10; no device access',
        'offline_only': True, 'hardware_actions': 0, 'passed': True, 'checks': checks,
        'review_kind': 'Author reproducer/self-check; separate independent writer peer review required before freeze',
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'reviewed_inputs': {name: digest(ROOT / name) for name in files},
        'native_payload_sha256': native_sha, 'program_bytes': len(program), 'auxiliary_program_bytes': len(payload),
        'writer_mock_cases': len(summary['cases']), 'rollback': 'Exact verified original GitHub tap v1 triple; then card, smooth, ease, first drawer, broker and stock require their own matching rollback chain',
        'local_only_session_configs': manifest['local_only_session_configs'],
        'limitations': ['Core animation behavior requires independent program review and actual ELF model matching this ELF.',
                       'No tap installation, display, power-cycle or cloud behavior is verified by this offline review.',
                       'The existing BOOT flow was tested under healthy MAIN; arbitrary damaged-MAIN recovery is not demonstrated.'],
    }
    path = ROOT / 'analysis/persistence/native-github-tap-fast-installer-review-1.50.10.json'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'review': path.relative_to(ROOT).as_posix(),
                      'review_sha256': digest(path), 'summary_sha256': digest(ROOT / summary_name),
                      'manifest_sha256': digest(ROOT / manifest_name),
                      'program_sha256': manifest['program']['sha256'], 'elf_sha256': manifest['program']['elf_sha256'],
                      'sectors': {k: v['patched']['sha256'] for k, v in manifest['sectors'].items()}}, indent=2))


if __name__ == '__main__':
    main()
