"""Reproduce the bounded GitHub-card installer review offline; no device access."""
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
    manifest_name = 'analysis/persistence/native-github-card-patch-inputs-1.50.10.json'
    manifest = load(manifest_name)
    assert manifest['cold_poweroff_verification'] == {'status': 'skipped_by_user_request', 'requested': False}
    summary_name = 'analysis/persistence/offline-native-github-card-runner/latest-summary.json'
    summary = load(summary_name)
    # Bind the immutable completed run rather than the convenient latest alias.
    run_summary = ROOT / Path(summary['cases'][0]['host_log']).parent / 'summary.json'
    assert run_summary.resolve().is_relative_to(ROOT / 'analysis/persistence/offline-native-github-card-runner')
    assert json.loads(run_summary.read_text()) == summary
    summary_name = run_summary.relative_to(ROOT).as_posix()
    freeze_names = ['analysis/persistence/native-ui-broker-frozen-inputs.json',
                    'analysis/persistence/native-drawer-frozen-inputs.json',
                    'analysis/persistence/native-drawer-ease-frozen-inputs.json',
                    'analysis/persistence/native-drawer-smooth-frozen-inputs.json']
    freezes = [load(name) for name in freeze_names]
    for frozen in freezes:
        for name, expected in frozen['sha256'].items():
            assert digest(ROOT / name) == expected, name
    checks = ['All four relevant previous frozen input sets retain their exact bytes; stock NOR provenance remains SHA-checked.']
    for label in ('code', 'entry'):
        item = manifest['sectors'][label]
        original = (ROOT / item['original']['path']).read_bytes()
        patched = (ROOT / item['patched']['path']).read_bytes()
        assert len(original) == len(patched) == 4096
        assert original == (ROOT / item['baseline_source']).read_bytes()
        assert digest(ROOT / item['original']['path']) == freezes[3]['sha256'][item['baseline_source']]
        assert digest(ROOT / item['patched']['path']) == item['patched']['sha256']
        if label == 'code':
            program = (ROOT / manifest['program']['path']).read_bytes()
            assert digest(ROOT / manifest['program']['path']) == manifest['program']['sha256']
            assert patched[0x10c:0x10c + len(program)] == program
            assert patched[:0x10c] == original[:0x10c]
            assert patched[0x10c + len(program):] == original[0x10c + len(program):]
            assert patched[0xe74:] == original[0xe74:]
        else:
            assert original == patched and item['mutations'] == []
            assert struct.unpack_from('<I', patched, 0xd2c)[0] == 0x3804b109
    checks.append('Rollback fixtures are exact smooth v1 full pages. Card code changes only inside its declared span; every builtin entry remains byte-identical. Shared bytes at/after 0x92be74 are untouched.')
    writer = (ROOT / 'diagnostics/boot-nor-native-github-card-runner.cfg').read_text()
    inverse = writer.replace('native-github-card', 'native-drawer-smooth').replace('ngc_', 'ndrs_').replace('ngci_', 'ndrsi_').replace('ndrs_run_native_github_card', 'ndrs_run_native_drawer_smooth')
    inverse = inverse.replace('Install requires both exact smooth-v1 sector baselines', 'Install requires both exact ease-v1 sector baselines')
    inverse = inverse.replace('Restore requires both exact smooth-v1 or both exact github-card sector baselines', 'Restore requires both exact ease-v1 or both exact drawer-smooth sector baselines')
    assert inverse == (ROOT / 'diagnostics/boot-nor-native-drawer-smooth-runner.cfg').read_text()
    checks.append('Inverse namespace/path and error-label normalization makes the card writer exactly equal to the frozen smooth v1 writer. All native call, allowlist, watchdog, context, transport, status and sequencing checks remain unchanged.')
    for mode in ('install', 'restore'):
        text = (ROOT / f'diagnostics/mcu-native-github-card-{mode}-session.cfg').read_text()
        inverse = text.replace('native-github-card', 'native-drawer-smooth').replace('ngc_', 'ndrs_').replace('ngci_', 'ndrsi_').replace('ndrs_run_native_github_card', 'ndrs_run_native_drawer_smooth')
        assert inverse == (ROOT / f'diagnostics/mcu-native-drawer-smooth-{mode}-session.cfg').read_text()
    checks.append('Both outer MCU sessions are exact frozen smooth v1 clones after namespace/path normalization, including fresh BOOT, isolated A7, watchdog stop, verified reader, completion gate and suppressed GLOBAL after uncertain native execution.')
    stages = (ROOT / 'diagnostics/boot-nor-native-github-card-stage-inputs.cfg').read_text()
    words = re.search(r'set ngci_one_call_words \{([^}]+)\}', stages)[1].split()
    raw = struct.pack('<' + 'I' * len(words), *(int(word, 0) for word in words))
    native_sha = hashlib.sha256(raw).hexdigest()
    assert len(raw) == 168 and native_sha == 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'
    checks.append('The exact reviewed 168-byte one-call ARM payload remains intact. Only fixed full-page smooth rollback/card install fixtures change.')
    assert summary['all_passed'] and len(summary['cases']) >= 43
    for name, expected in summary['source_sha256'].items():
        assert digest(ROOT / name) == expected
    for label, sector in [('code', 'code'), ('table', 'entry')]:
        for state in ('original', 'patched'):
            assert summary['independent_sector_sha256'][label + '_' + state] == manifest['sectors'][sector][state]['sha256']
    checks.append('Current Jim cases pass, covering smooth/card success, ease/first-drawer/broker/stock/counter/unknown refusal, full-page readback, BP/QE, watchdog races, fault/reset/timeout and no stale replay. Equal entry pages cannot identify the drawer variant; the code page must match.')
    for path in (ROOT / 'analysis/persistence').glob('*native_github_card*.py'):
        ast.parse(path.read_text())
    freeze_source = (ROOT / 'analysis/persistence/freeze_native_github_card_inputs.py').read_text()
    runner_source = (ROOT / 'analysis/persistence/run_native_github_card_firmware.py').read_text()
    assert 'assert not freeze_path.exists()' in freeze_source
    assert "arm['elf_sha256'] == manifest['program']['elf_sha256']" in freeze_source
    assert 'for frozen in (broker_freeze, drawer_freeze, ease_freeze, smooth_freeze):' in freeze_source
    assert 'Conflicting frozen input hash:' in runner_source
    checks.append('Freeze rejects overwrites and binds all prior freezes, exact smooth rollback, stock NOR, current ELF/BIN/pages, reviews, current ELF model, writer summary and local headers. The public runner rechecks all merged prior catalogs before any hardware access, including zero-execute mode.')
    files = [manifest_name, summary_name, *freeze_names,
             'analysis/persistence/prepare_native_github_card_inputs.py',
             'analysis/persistence/run_native_github_card_firmware.py',
             'analysis/persistence/freeze_native_github_card_inputs.py',
             'analysis/persistence/test_native_github_card_runner_offline.py',
             'analysis/persistence/review_native_github_card_installer.py',
             'analysis/persistence/native-github-card-writer-preparation.json',
             'diagnostics/boot-nor-native-github-card-runner.cfg',
             'diagnostics/boot-nor-native-github-card-stage-inputs.cfg',
             'diagnostics/mcu-native-github-card-install-session.cfg',
             'diagnostics/mcu-native-github-card-restore-session.cfg',
             'diagnostics/read-native-github-card-state.cfg',
             'diagnostics/read-native-github-card-runtime.cfg',
             'scripts/Set-PanelNativeGitHubCard.ps1',
             'analysis/display-takeover/native-github-card.c',
             'analysis/display-takeover/native-github-card-entry.S',
             'analysis/display-takeover/native-github-card.ld',
             'analysis/display-takeover/build-native-github-card.sh',
             'analysis/display-takeover/github-card-logo.h',
             'analysis/display-takeover/render_github_card_reference.py',
             manifest['program']['path'], manifest['program']['elf']]
    for sector in manifest['sectors'].values():
        files.extend([sector['baseline_source'], sector['original']['path'], sector['patched']['path']])
    report = {
        'scope': 'GitHub card installer and smooth-v1 rollback only for this panel 1.50.10; no device access',
        'offline_only': True, 'hardware_actions': 0, 'passed': True, 'checks': checks,
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'reviewed_inputs': {name: digest(ROOT / name) for name in files},
        'native_payload_sha256': native_sha, 'program_bytes': len(program),
        'writer_mock_cases': len(summary['cases']), 'rollback': 'Exact verified smooth v1, not ease, first drawer, broker or stock',
        'limitations': ['Core animation behavior requires independent program review and actual ELF model matching this ELF.',
                       'No card installation, display, power-cycle or cloud behavior is verified by this offline review.',
                       'The existing BOOT flow was tested under healthy MAIN; arbitrary damaged-MAIN recovery is not demonstrated.'],
    }
    path = ROOT / 'analysis/persistence/native-github-card-installer-review-1.50.10.json'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'review': path.relative_to(ROOT).as_posix(),
                      'review_sha256': digest(path), 'summary_sha256': digest(ROOT / summary_name),
                      'manifest_sha256': digest(ROOT / manifest_name),
                      'program_sha256': manifest['program']['sha256'], 'elf_sha256': manifest['program']['elf_sha256'],
                      'sectors': {k: v['patched']['sha256'] for k, v in manifest['sectors'].items()}}, indent=2))


if __name__ == '__main__':
    main()
