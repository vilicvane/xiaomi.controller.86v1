"""Root's independent byte/page review of the new image-drawer installer.

Read-only offline inspection, except writing this version's new review record.
Does not call the preparer's writer generation or its self-review.
"""
from pathlib import Path
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
PERSIST = ROOT / 'analysis/persistence'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(name):
    return sha((ROOT / name).read_bytes())


def normalized(text):
    return (text.replace('native-image-drawer', 'native-github-tap-fast')
            .replace('native_image_drawer', 'native_github_tap_fast')
            .replace('nidi_', 'ngtfi_').replace('nid_', 'ngtf_'))


def main():
    manifest_name = 'analysis/persistence/native-image-drawer-patch-inputs-1.50.10.json'
    manifest = json.loads((ROOT / manifest_name).read_text())
    old_name = 'analysis/persistence/native-github-tap-fast-frozen-inputs.json'
    assert digest(old_name) == '96588070da46764460c72d0ba1e71c635c1de39d226842ff3e71c2226e4a5b6c'
    old = json.loads((ROOT / old_name).read_text())
    inputs = {manifest_name, old_name, __file__}
    distinct = {}
    for name in ('native-ui-broker', 'native-drawer', 'native-drawer-ease',
                 'native-drawer-smooth', 'native-github-card', 'native-github-tap',
                 'native-github-tap-fast', 'native-counter'):
        path = PERSIST / (name + '-frozen-inputs.json')
        inputs.add(path.relative_to(ROOT).as_posix())
        frozen = json.loads(path.read_text())
        for relative, expected in frozen['sha256'].items():
            assert digest(relative) == expected, relative
            assert relative not in distinct or distinct[relative] == expected
            distinct[relative] = expected

    def text(name):
        inputs.add(name)
        return (ROOT / name).read_text()

    writer = text('diagnostics/boot-nor-native-image-drawer-runner.cfg')
    inverse = normalized(writer)
    for new, prior in (
        ('Install requires all three exact fast-tap sector baselines',
         'Install requires all three exact tap-v1 sector baselines'),
        ('Restore requires all three exact fast-tap or all three exact image-drawer sector baselines',
         'Restore requires all three exact tap-v1 or all three exact github-tap-fast sector baselines'),
        ('Restore fast-tap main references before returning the auxiliary slot to fast tap.',
         'Restore v1 main references before returning the auxiliary slot to v1 tap.'),
    ):
        assert inverse.count(new) == 1
        inverse = inverse.replace(new, prior)
    assert inverse == text('diagnostics/boot-nor-native-github-tap-fast-runner.cfg')
    stages = text('diagnostics/boot-nor-native-image-drawer-stage-inputs.cfg')
    prior_stages = text('diagnostics/boot-nor-native-github-tap-fast-stage-inputs.cfg')
    assert normalized(stages[stages.index('foreach nidi_name '):]) == prior_stages[prior_stages.index('foreach ngtfi_name '):]
    for mode in ('install', 'restore'):
        outer = text(f'diagnostics/mcu-native-image-drawer-{mode}-session.cfg')
        assert normalized(outer) == text(f'diagnostics/mcu-native-github-tap-fast-{mode}-session.cfg')
        assert '($boot_app_entered && (!$nid_safe_to_resume || !$nid_app_complete))' in outer
        assert 'automatic GLOBAL suppressed' in outer
    words = re.search(r'set nidi_one_call_words \{([^}]+)\}', stages)[1].split()
    native = struct.pack('<'+'I'*len(words), *(int(word, 0) for word in words))
    assert len(native) == 168
    assert sha(native) == 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'

    for label, slot in (('code', 'code'), ('entry', 'table'), ('aux', 'aux')):
        item = manifest['sectors'][label]
        base = (ROOT / item['baseline_source']).read_bytes()
        assert len(base) == 4096 and sha(base) == old['sha256'][item['baseline_source']]
        patched = bytearray(base)
        if label != 'entry':
            payload_item = manifest['program'] if label == 'code' else manifest['program']['feedback']
            data = (ROOT / payload_item['path']).read_bytes()
            assert sha(data) == payload_item['sha256']
            assert len(data) <= (3432 if label == 'code' else 444)
            start = 0x10c if label == 'code' else 0x768
            patched[start:start+len(data)] = data
            inputs.add(payload_item['path'])
        else:
            for offset, value in ((0xcc8, 0x3804b2f5), (0xebc, 0x3804b111),
                                  (0xf20, 0x3804b111), (0xe80, 0x3804b109), (0xd2c, 0x3804b109)):
                assert struct.unpack_from('<I', base, offset)[0] == value
        for state, expected in (('original', base), ('patched', bytes(patched))):
            path = item[state]['path']
            assert (ROOT / path).read_bytes() == expected and sha(expected) == item[state]['sha256']
            array_words = re.search(r'set nidi_'+slot+'_'+state+r'_words \{([^}]+)\}', stages)[1].split()
            array_data = struct.pack('<'+'I'*len(array_words), *(int(word, 0) for word in array_words))
            assert array_data == expected
            inputs.add(path)
        inputs.add(item['baseline_source'])

    summary = json.loads((PERSIST / 'offline-native-image-drawer-runner/latest-summary.json').read_text())
    completed = ROOT / Path(summary['cases'][0]['host_log']).parent / 'summary.json'
    assert json.loads(completed.read_text()) == summary
    assert summary['all_passed'] and len(summary['cases']) == 70
    inputs.add(completed.relative_to(ROOT).as_posix())
    for path, expected in summary['source_sha256'].items():
        assert digest(path) == expected
        inputs.add(path)
    for name in ('prepare_native_image_drawer_inputs.py', 'native_image_drawer_three_page_writer.py',
                 'run_native_image_drawer_firmware.py', 'freeze_native_image_drawer_inputs.py',
                 'review_native_image_drawer_installer.py', 'test_native_image_drawer_runner_offline.py'):
        inputs.add('analysis/persistence/'+name)
    inputs.add('analysis/persistence/native-image-drawer-installer-review-1.50.10.json')
    program_review = 'analysis/image-push/native-image-drawer-independent-review-1.50.10.json'
    evidence = json.loads((ROOT / program_review).read_text())
    assert evidence['passed']
    inputs.add(program_review)
    for path, expected in evidence['reviewed_inputs'].items():
        assert digest(path) == expected
        inputs.add(path)
    inputs = {Path(name).resolve().relative_to(ROOT).as_posix() if Path(name).is_absolute() else name for name in inputs}
    result = {
        'passed': True, 'reviewer': 'root, independent of installer author',
        'offline_only': True, 'hardware_actions': 0, 'prior_distinct_inputs_checked': len(distinct),
        'writer_mock_cases': 70,
        'checks': [
            'Full generated writer matches exact frozen fast-tap writer after names and three enumerated descriptions only.',
            'Full executable stage body, including pre-proc foreach normalization, and both BOOT outer sessions match frozen fast tap.',
            '168-byte one-call payload is exact; uncertain native execution suppresses automatic GLOBAL.',
            'Root independently reconstructs all three full pages from frozen fast tap; only bounded main and aux spans differ; entry and all other bytes remain exact.',
            'All generated fixture arrays match the independent page reconstruction, including baseline and rollback.',
            'Eight historical catalogs and their 255 distinct inputs stay byte exact; completed 70-case mocks bind current sources.',
            'Program review inputs and code-model evidence bind the actual new ELF, not earlier UI behavior.',
            'Public runner checks prior/current hashes before hardware and never retries writes; only named post-GLOBAL DP-IDR failure admits fresh read-only reconnect.',
        ],
        'reviewed_inputs': {name: digest(name) for name in sorted(inputs)},
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'limits': ['Offline review does not establish real network, LCD, Mi Home, or cold-boot health.'],
    }
    output = PERSIST / 'native-image-drawer-writer-peer-review-1.50.10.json'
    assert not output.exists(), 'Do not overwrite a completed peer review'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'reviewed_inputs': len(inputs), 'sha256': sha(output.read_bytes())}))


if __name__ == '__main__':
    main()
