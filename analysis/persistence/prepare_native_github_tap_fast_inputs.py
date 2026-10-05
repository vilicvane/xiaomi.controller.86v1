"""Prepare fast-tap inputs offline; exact v1 tap triple is the rollback.

No hardware, build or freezing. Old six catalog sets are immutable. The writer
and executable stages are full v1 namespace clones, with two error texts and one rollback comment fixed.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/display-takeover'
PERSIST = ROOT / 'analysis/persistence'
NOR_SHA = '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
TAP_WRITER_SHA = '1a50a2626d40eab4b5df18ad568cda03afa288c470df69a3d2c002b8d215d89f'
TAP_STAGES_SHA = 'c6741246a9381bc5fb3c426309d6c7d02416699db8e875e2fe5faa3c07aeb674'
GENERATOR_SHA = '7aaf96b3a4ff0378d1ac9645aece5c037fcdf3a177290f1b6ce964c27e70123e'
ONECALL_SHA = 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'
PRIOR_FREEZE_SHA = {
    'native-ui-broker-frozen-inputs.json': 'be8a154b8c5b44e8899062d9373a9395c99ff8ca2d90ddc9e4b824fa1fd1f4ba',
    'native-drawer-frozen-inputs.json': 'b6d30c6efaa28158c6596c4283a41a9be79412d66f099980145434b10fe5b28f',
    'native-drawer-ease-frozen-inputs.json': '1c4e519efc84063024d106966bf159a65cc2b378af81b7ad6cc5bc19888e2e6b',
    'native-drawer-smooth-frozen-inputs.json': 'c464db59ec74849396d6ea2bcd3c0aa9d2110f7766068c6f08a23a82522aa392',
    'native-github-card-frozen-inputs.json': '7bd88c1f217fd53219a054bf3c24ef197ee5666133d45f1557bfd8173c4c41db',
    'native-github-tap-frozen-inputs.json': '680a5f173a55c2e9811987a794b5332628f55d76a142076b9088aab3fea94f0e',
}
TAP_SECTOR_SHA = {
    'code': '1b28758ee8597a676589bca406226208914afce4a54a583428f0a4c51f7bf3d0',
    'entry': 'ed3bc98fdd0af88b22107c506dc4bc6e00fef11ae844d5f0c237199acde24c26',
    'aux': '5d6321192144e869a82d424ad32b6d6bb64014c179205cd481c3379e8a28b1e6',
}
SESSION_SHAS = {
    'install': 'e7bd7ccb652156f7c2df12a4049d90f47a4a5035d22ae83545784b84e7151bb6',
    'restore': 'a8df2fc31baedbb63e2b2dd313c3fcd4b1bdf5476de0d18a7ef714866adce10e',
}
CODE_START, CODE_END = 0x3804b108, 0x3804be70
CODE_FILE_START = 0x92b10c
AUX_START, AUX_END, AUX_FILE_START = 0x3807a764, 0x3807a920, 0x95a768
ENTRY = 0x3804b2f5
TABLE_WORDS = ((0xcc8, ENTRY), (0xebc, 0x3804b111), (0xf20, 0x3804b111), (0xe80, 0x3804b109), (0xd2c, 0x3804b109))
# Renderer explicitly confirmed this layout; payload/model must still be locked
# before invoking preparation. Pending 1 is not accepted until a successful PAN.
RUNTIME_CONTEXT = {'bytes': 184, 'words': 46, 'feedback_ms_offset': 176, 'feedback_pending_offset': 180,
                   'animation_from_offset': 164, 'pending_offset': 168, 'phase_offset': 172}
FEEDBACK_PENDING_STATES = {'0': 'accepted_and_clock_anchored', '1': 'new_count_waiting_successful_pan',
                           '2': 'successful_pan_waiting_fresh_clock'}
PAYLOAD_LOCK = {
    'main': '9c529291e9c32534df89f17939e9b9d63a38267f45d0b04a579a84b0c1c7c6d9',
    'feedback': '61285fe7177bafa255b4dc880a70d58cd44f6edbd25171db4674f81b7da52cf0',
    'elf': 'd36daa251ce820e0e4038d6a0190554306a1bc6a545d0f7a502a8327000454f0',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    assert sha(data) == expected, 'Reviewed dependency changed: ' + str(path)
    return data


def relative(path):
    return path.relative_to(ROOT).as_posix()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def prepare():
    assert PAYLOAD_LOCK is not None, 'Renderer payload/model is not locked; do not prepare moving payload'
    assert not (PERSIST / 'native-github-tap-fast-frozen-inputs.json').exists(), 'Frozen fast-tap inputs are immutable'
    freezes = []
    for name, expected in PRIOR_FREEZE_SHA.items():
        freezes.append(json.loads(checked(PERSIST / name, expected)))
    for frozen in freezes:
        for name, expected in frozen['sha256'].items():
            checked(ROOT / name, expected)
    image_path = ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin'
    nor = checked(image_path, NOR_SHA)
    assert len(nor) == 0x1000000
    # Reuse the exact frozen ELF32 segmented reader, not a flat address-hole BIN.
    previous = module('frozen_tap_prepare', PERSIST / 'prepare_native_github_tap_inputs.py')
    extension = module('fast_tap_names', PERSIST / 'native_github_tap_fast_three_page_writer.py')
    generator_path = PERSIST / 'build_native_app_runner.py'
    checked(generator_path, GENERATOR_SHA)
    generator = module('frozen_native_generator', generator_path)
    program_path = OUT / 'native-github-tap-fast.bin'
    feedback_path = OUT / 'native-github-tap-fast-feedback.bin'
    elf_path = OUT / 'native-github-tap-fast.elf'
    program, feedback = program_path.read_bytes(), feedback_path.read_bytes()
    assert sha(program) == PAYLOAD_LOCK['main'] and sha(feedback) == PAYLOAD_LOCK['feedback']
    assert sha(elf_path.read_bytes()) == PAYLOAD_LOCK['elf']
    assert {'main': program, 'feedback': feedback} == previous.linked_segments(elf_path.read_bytes())
    assert 0 < len(program) <= CODE_END - CODE_START and 0 < len(feedback) <= AUX_END - AUX_START
    assert program[:6] == bytes.fromhex('262040427047') and program[8:12] == bytes.fromhex('00207047')
    assert program[0x1ec:0x1f0] == bytes.fromhex('00f000b8')
    sectors, values = {}, {}
    for label, offset in (('code', 0x92b000), ('entry', 0xccd000), ('aux', 0x95a000)):
        baseline_path = PERSIST / f'native-github-tap-patched-sector-{offset:x}.bin'
        baseline = checked(baseline_path, TAP_SECTOR_SHA[label])
        assert len(baseline) == 4096 and freezes[-1]['sha256'][relative(baseline_path)] == sha(baseline)
        patched = bytearray(baseline)
        if label in ('code', 'aux'):
            start, payload, limit = (0x10c, program, 0xe74) if label == 'code' else (0x768, feedback, 0x924)
            patched[start:start + len(payload)] = payload
            assert patched[:start] == baseline[:start] and patched[start + len(payload):] == baseline[start + len(payload):]
            assert patched[limit:] == baseline[limit:]
            mutations = [{'sector_offset': hex(start), 'bytes': len(payload)}]
        else:
            for word_offset, expected in TABLE_WORDS:
                assert struct.unpack_from('<I', baseline, word_offset)[0] == expected
            assert patched == baseline
            mutations = []
        sectors[label] = {'offset': hex(offset), 'mutations': mutations,
                          'baseline_kind': 'verified-native-github-tap-v1', 'baseline_source': relative(baseline_path)}
        for state, data in (('original', baseline), ('patched', bytes(patched))):
            path = PERSIST / f'native-github-tap-fast-{state}-sector-{offset:x}.bin'
            path.write_bytes(data)
            sectors[label][state] = {'path': relative(path), 'bytes': 4096, 'sha256': sha(data)}
            values[('table' if label == 'entry' else label) + '_' + state] = data
    assert sectors['code']['original']['sha256'] != sectors['code']['patched']['sha256'], 'Fast payload equals v1 tap'
    proof_path = PERSIST / 'github-tap-aux-live-baseline-result.json'
    checked(proof_path, freezes[-1]['sha256'][relative(proof_path)])
    manifest_path = PERSIST / 'native-github-tap-fast-patch-inputs-1.50.10.json'
    manifest = {
        'offline_only': True, 'frozen': False, 'hardware_actions': 0,
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'local_only_session_configs': [f'diagnostics/mcu-native-github-tap-fast-{mode}-session.cfg' for mode in ('install', 'restore')],
        'firmware': {'path': relative(image_path), 'bytes': len(nor), 'sha256': NOR_SHA},
        'aux_live_baseline': {'path': relative(proof_path), 'sha256': sha(proof_path.read_bytes()),
                              'sector_sha256': 'fe815dee80d04a6f4b35f238a4c0d05063ecb219ff53132534c71f08ef47f185',
                              'role': 'Historical stock provenance before v1 tap; current fast baseline is the exact frozen v1 tap auxiliary page'},
        'runtime_context': RUNTIME_CONTEXT, 'feedback_pending_states': FEEDBACK_PENDING_STATES,
        'rollback': {'kind': 'native-github-tap-v1', 'freeze': 'analysis/persistence/native-github-tap-frozen-inputs.json',
                     'freeze_sha256': PRIOR_FREEZE_SHA['native-github-tap-frozen-inputs.json']},
        'program': {'path': relative(program_path), 'elf': relative(elf_path), 'sha256': sha(program), 'elf_sha256': sha(elf_path.read_bytes()),
                    'bytes': len(program), 'entry': hex(ENTRY), 'start': hex(CODE_START), 'container_end_exclusive': hex(CODE_END),
                    'container_bytes': CODE_END - CODE_START, 'file_start': hex(CODE_FILE_START), 'elf_image_kind': 'two-independent-allocated-spans',
                    'feedback': {'path': relative(feedback_path), 'sha256': sha(feedback), 'bytes': len(feedback), 'start': hex(AUX_START),
                                 'container_end_exclusive': hex(AUX_END), 'file_start': hex(AUX_FILE_START), 'container_bytes': AUX_END - AUX_START}},
        'scope': 'Three exact full NOR pages. Bounded fast-tap main/feedback spans only; preserve every other v1 tap byte and every builtin entry. Restore all three exact v1 tap pages, not card or stock.',
        'disabled_commands': {'wifi_recorder': '-ENOSYS stub at 0x3804b109 retained; no new entry mutation'},
        'install_baseline': 'Exact frozen native-github-tap-v1 triple only; restore returns this triple before any older version writer can be used.',
        'install_order': ['aux', 'code', 'entry'], 'restore_order': ['entry', 'code', 'aux'], 'sectors': sectors,
    }
    write_json(manifest_path, manifest)
    old_writer = checked(ROOT / 'diagnostics/boot-nor-native-github-tap-runner.cfg', TAP_WRITER_SHA).decode('utf-8')
    old_stages = checked(ROOT / 'diagnostics/boot-nor-native-github-tap-stage-inputs.cfg', TAP_STAGES_SHA).decode('utf-8')
    onecall = checked(PERSIST / 'boot-nor-one-call.bin', ONECALL_SHA)
    assert len(onecall) == 168
    inputs = '# Generated offline only. Fast GitHub tap payload and exact v1 tap triple rollback; no hardware operations.\n'
    inputs += generator.tcl_list('ngtfi_one_call_words', onecall)
    for label, data in values.items():
        inputs += generator.tcl_list('ngtfi_' + label + '_words', data)
    inputs += extension.stages(old_stages)
    input_path = ROOT / 'diagnostics/boot-nor-native-github-tap-fast-stage-inputs.cfg'
    input_path.write_text(inputs, encoding='utf-8')
    writer_path = ROOT / 'diagnostics/boot-nor-native-github-tap-fast-runner.cfg'
    writer_path.write_text(extension.writer(old_writer), encoding='utf-8')
    for mode, expected in SESSION_SHAS.items():
        old = checked(ROOT / f'diagnostics/mcu-native-github-tap-{mode}-session.cfg', expected).decode('utf-8')
        source = extension.outer(old)
        assert source.count(f'ngtf_run_native_github_tap_fast $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$ngtf_safe_to_resume || !$ngtf_app_complete))' in source and 'automatic GLOBAL suppressed' in source
        (ROOT / f'diagnostics/mcu-native-github-tap-fast-{mode}-session.cfg').write_text(source, encoding='utf-8')
    report_path = PERSIST / 'native-github-tap-fast-writer-preparation.json'
    report = {'offline_only': True, 'hardware_actions': 0, 'frozen': False,
              'cold_poweroff_verification': manifest['cold_poweroff_verification'], 'local_only_session_configs': manifest['local_only_session_configs'],
              'session_git_policy': 'Generated MCU sessions contain vendor boot-header words; exact local files remain excluded from Git.',
              'manifest': relative(manifest_path), 'manifest_sha256': sha(manifest_path.read_bytes()), 'writer': relative(writer_path),
              'writer_sha256': sha(writer_path.read_bytes()), 'stage_inputs': relative(input_path), 'stage_inputs_sha256': sha(input_path.read_bytes()),
              'reused_caller_sha256': ONECALL_SHA, 'reviewed_writer_source_sha256': TAP_WRITER_SHA,
              'three_page_extension': 'analysis/persistence/native_github_tap_fast_three_page_writer.py',
              'three_page_extension_sha256': sha((PERSIST / 'native_github_tap_fast_three_page_writer.py').read_bytes()),
              'changes_to_native_caller': 'Exact 168-byte ARM payload. Whole native/public writer and entire executable stages remain exact v1 tap after namespace normalization and two baseline error texts plus one rollback comment.',
              'changes_to_public_flow': 'No control-flow, callee, stage whitelist, protection, scratch, readback, cache or completion-gate changes. Fixtures now admit v1 tap or fast tap triples; rollback is v1 tap.',
              'pending': 'Current program, model, mocks and separate writer/program review must pass before explicit freezing.'}
    write_json(report_path, report)
    for frozen in freezes:
        for name, expected in frozen['sha256'].items():
            checked(ROOT / name, expected)
    print(json.dumps({'program_bytes': len(program), 'feedback_bytes': len(feedback), 'manifest': relative(manifest_path),
                      'manifest_sha256': report['manifest_sha256'], 'writer_sha256': report['writer_sha256'],
                      'stage_inputs_sha256': report['stage_inputs_sha256'], 'frozen': False, 'hardware_actions': 0}, indent=2))


if __name__ == '__main__':
    prepare()
