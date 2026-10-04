"""Independently compare prepared broker sectors and proven writer offline.

No generator import, hardware API, adapter init, native call or freeze. The
report binds the current payload, full sector images, and current mock run.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(path):
    return path.read_text(encoding='utf-8').replace('\r\n', '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-program-sha256', required=True)
    parser.add_argument('--offline-summary', type=Path, required=True)
    args = parser.parse_args()
    summary_path = (ROOT / args.offline_summary).resolve()
    assert summary_path.is_relative_to(ROOT)
    summary = json.loads(summary_path.read_text())
    assert summary['all_passed'] and len(summary['cases']) == 33
    assert all(item['passed'] for item in summary['cases'])
    old_freeze_path = ROOT / 'analysis/persistence/native-counter-frozen-inputs.json'
    old_freeze = json.loads(old_freeze_path.read_text())
    assert len(old_freeze['sha256']) == 21
    for name, expected in old_freeze['sha256'].items():
        assert sha(ROOT / name) == expected, 'Old frozen input changed: ' + name
    manifest_path = ROOT / 'analysis/display-takeover/native-ui-broker-patch-inputs-1.50.10.json'
    manifest = json.loads(manifest_path.read_text())
    program_path = ROOT / manifest['program']['path']
    program = program_path.read_bytes()
    assert sha(program_path) == args.expected_program_sha256 == manifest['program']['sha256']
    assert len(program) == manifest['program']['bytes'] <= 0xb90
    assert manifest['program']['start'] == '0x3804b108'
    assert manifest['program']['file_start'] == '0x92b10c'
    assert manifest['program']['container_end_exclusive'] == '0x3804bc98'
    nor_path = ROOT / manifest['firmware']['path']
    nor = nor_path.read_bytes()
    assert len(nor) == 0x1000000
    assert sha(nor_path) == '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
    assert program[:6] == bytes.fromhex('262040427047')
    assert program[8:12] == bytes.fromhex('00207047')
    assert program[0x1ec:0x1f0] == bytes.fromhex('00f000b8')
    table_words = [(0xcc8, 0x3818f9fd, 0x3804b2f5),
                   (0xebc, 0x3804b2f5, 0x3804b111),
                   (0xf20, 0x3804b87d, 0x3804b111)]
    fixtures = {}
    changes = {}
    inputs = [manifest_path, program_path, ROOT / manifest['program']['elf'],
              summary_path, old_freeze_path, Path(__file__).resolve(),
              ROOT / 'analysis/persistence/prepare_native_ui_broker_inputs.py',
              ROOT / 'analysis/persistence/freeze_native_ui_broker_inputs.py',
              ROOT / 'analysis/persistence/run_native_ui_broker_firmware.py',
              ROOT / 'analysis/persistence/test_native_ui_broker_runner_offline.py',
              ROOT / 'diagnostics/read-native-ui-broker-state.cfg']
    for label, offset in (('code', 0x92b000), ('entry', 0xccd000)):
        original = nor[offset:offset + 4096]
        expected = bytearray(original)
        if label == 'code':
            expected[0x10c:0x10c + len(program)] = program
            assert expected[0xc9c:] == original[0xc9c:]
        else:
            for start, before, after in table_words:
                assert struct.unpack_from('<I', original, start)[0] == before
                struct.pack_into('<I', expected, start, after)
            assert struct.unpack_from('<I', expected, 0xe80)[0] == 0x3804b109
        for state, wanted in (('original', original), ('patched', bytes(expected))):
            item = manifest['sectors'][label][state]
            path = ROOT / item['path']
            assert path.read_bytes() == wanted
            assert sha(path) == item['sha256']
            fixtures[('table' if label == 'entry' else label) + '_' + state] = wanted
            inputs.append(path)
        changes[label] = [i for i, (before, after) in enumerate(zip(original, expected)) if before != after]
    writer_path = ROOT / 'diagnostics/boot-nor-native-ui-broker-runner.cfg'
    stage_path = ROOT / 'diagnostics/boot-nor-native-ui-broker-stage-inputs.cfg'
    old_writer_path = ROOT / 'diagnostics/boot-nor-native-app-runner.cfg'
    assert sha(old_writer_path) == 'a39977808f17c040dd8d2969d548beee1377cc20c095c2084e3aa5df01854edb'
    restored = text(writer_path).replace('nub_', 'bna_').replace('nubi_', 'bnai_')
    restored = restored.replace('boot-nor-native-ui-broker-stage-inputs.cfg', 'boot-nor-native-app-stage-inputs.cfg')
    restored = restored.replace('bna_run_native_ui_broker', 'bna_run_native_app')
    stricter = '''            if {!(($code_before == $bnai_code_original_words && $table_before == $bnai_table_original_words) ||
                ($code_before == $bnai_code_patched_words && $table_before == $bnai_table_patched_words))} { error "Restore requires both exact original or both exact broker sector baselines" }'''
    prior = '''            if {($code_before != $bnai_code_original_words && $code_before != $bnai_code_patched_words) ||
                ($table_before != $bnai_table_original_words && $table_before != $bnai_table_patched_words)} { error "Restore requires exact original/patched sector baselines" }'''
    assert restored.count(stricter) == 1
    restored = restored.replace(stricter, prior)
    assert restored == text(old_writer_path), 'Unexpected native caller/orchestration change'
    stage_text = text(stage_path)
    onecall_path = ROOT / 'analysis/persistence/boot-nor-one-call.bin'
    fixture_words = dict(fixtures, one_call=onecall_path.read_bytes())
    for label, raw in fixture_words.items():
        match = re.search(r'^set nubi_' + label + r'_words \{\s*([^}]*)\}', stage_text, re.MULTILINE)
        assert match, 'Missing fixed stage fixture: ' + label
        nums = list(map(int, match[1].split()))
        actual = struct.pack('<' + 'I' * len(nums), *nums)
        assert actual == raw, 'Stage words differ from independent binary: ' + label
    old_stage = text(ROOT / 'diagnostics/boot-nor-native-app-stage-inputs.cfg')
    assert stage_text[stage_text.index('foreach nubi_name'):].replace('nubi_', 'bnai_') == old_stage[old_stage.index('foreach bnai_name'):]
    inputs.extend([writer_path, stage_path, onecall_path])
    for mode in ('install', 'restore'):
        path = ROOT / f'diagnostics/mcu-native-ui-broker-{mode}-session.cfg'
        restored = text(path).replace('boot-nor-native-ui-broker-runner.cfg', 'boot-nor-native-app-runner.cfg')
        restored = restored.replace('native-ui-broker-writer-', 'native-app-')
        restored = restored.replace('native-ui-broker-reader-%s', 'native-read-%s')
        restored = restored.replace('native-ui-broker', 'native-counter')
        restored = restored.replace('nub_', 'bna_').replace('nubi_', 'bnai_')
        restored = restored.replace('bna_run_native_ui_broker', 'bna_run_native_app')
        assert restored == text(ROOT / f'diagnostics/mcu-native-counter-{mode}-session.cfg'), 'Unexpected recovery/session change'
        inputs.append(path)
    for name, expected in summary['source_sha256'].items():
        assert sha(ROOT / name) == expected
    for label, raw in fixtures.items():
        assert summary['independent_sector_sha256'][label] == hashlib.sha256(raw).hexdigest()
    report = {
        'offline_only': True, 'hardware_actions': 0, 'passed': True,
        'scope': 'Independent whole-sector broker payload and frozen-writer differential review; no hardware or freeze.',
        'reviewed_inputs': {path.relative_to(ROOT).as_posix(): sha(path) for path in inputs},
        'old_counter_frozen_inputs_preserved': 21,
        'normalized_writer_diff': 'Exact match after namespace/source filename reversal and reverting only stricter coupled restore gate.',
        'normalized_session_diff': 'Both exact old reviewed install/restore sessions after namespace/source/capture filename reversal.',
        'stage_inputs': 'Exact independent four whole-sector binaries and identical168B caller; stage functions unchanged after namespace reversal.',
        'table_words': [{'sector_offset': hex(start), 'original': hex(before), 'patched': hex(after)} for start, before, after in table_words],
        'duplicate_gui_prevention': 'faclvgl registry now returns-zero stub, so its former entry cannot launch broker again.',
        'whole_sector_changes': {'code_changed_byte_count': len(changes['code']), 'entry_changed_byte_count': len(changes['entry']),
                                 'entry_changed_offsets': [hex(value) for value in changes['entry']]},
        'offline_mock_cases': 33, 'all_mock_cases_passed': True, 'offline_summary': summary_path.relative_to(ROOT).as_posix(),
        'inherited_guards': ['Live id0 controller40148000 only;40140000 never dereferenced', 'Fresh BOOT halt and same-process reader',
                            'A7/WF/BT held reset', 'Stopped watchdog at entry/prerun/final', 'Exact scratch/core/dualalias return closure',
                            'WIP/WEL0 and BP/QE stable-status restoration', 'Code whole4Kverified before registryerase;restore registry first',
                            'No retry/nextstage/stale context/GLOBAL after unclosed calls; outer requires complete and safe'],
        'limits': 'Mock ARM calls do not prove hardware display/input/scheduling/coldboot or recovery from deliberately corrupted MAIN.',
    }
    destination = ROOT / 'analysis/persistence/native-ui-broker-installer-review-1.50.10.json'
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': destination.relative_to(ROOT).as_posix(), 'sha256': sha(destination),
                      'program_sha256': sha(program_path), 'mock_cases': 33, 'hardware_actions': 0}, indent=2))


if __name__ == '__main__':
    main()
