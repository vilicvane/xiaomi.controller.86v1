"""Prepare image-drawer inputs offline; exact fast-tap triple is the rollback.

No hardware, build or freezing. Seven UI catalogs and the old counter catalog
are immutable. The writer and executable stages are full fast-tap namespace
clones with two error texts and one rollback comment fixed.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import struct

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/image-push'
PERSIST = ROOT / 'analysis/persistence'
NOR_SHA = '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
FAST_WRITER_SHA = '61f9bd68f09555614f279ef86b5b3a2944924d351daffe7ada670cb588fb85f8'
FAST_STAGES_SHA = 'ca64293959e7956430996c26aaf4f16362b3229dbcfe30062aac7f472dd97838'
GENERATOR_SHA = '7aaf96b3a4ff0378d1ac9645aece5c037fcdf3a177290f1b6ce964c27e70123e'
ONECALL_SHA = 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'
PRIOR_FREEZE_SHA = {
    'native-ui-broker-frozen-inputs.json': 'be8a154b8c5b44e8899062d9373a9395c99ff8ca2d90ddc9e4b824fa1fd1f4ba',
    'native-drawer-frozen-inputs.json': 'b6d30c6efaa28158c6596c4283a41a9be79412d66f099980145434b10fe5b28f',
    'native-drawer-ease-frozen-inputs.json': '1c4e519efc84063024d106966bf159a65cc2b378af81b7ad6cc5bc19888e2e6b',
    'native-drawer-smooth-frozen-inputs.json': 'c464db59ec74849396d6ea2bcd3c0aa9d2110f7766068c6f08a23a82522aa392',
    'native-github-card-frozen-inputs.json': '7bd88c1f217fd53219a054bf3c24ef197ee5666133d45f1557bfd8173c4c41db',
    'native-github-tap-frozen-inputs.json': '680a5f173a55c2e9811987a794b5332628f55d76a142076b9088aab3fea94f0e',
    'native-github-tap-fast-frozen-inputs.json': '96588070da46764460c72d0ba1e71c635c1de39d226842ff3e71c2226e4a5b6c',
}
COUNTER_FREEZE_SHA = 'b9619a62ea8613eca200aa29b9e466df76194b90e637534c03937176deb2fad2'
FAST_SECTOR_SHA = {
    'code': '6b1213342d9f97ef3c53e4691f0533217eb9fd15fc76b5dc06d8bca1df286bf9',
    'entry': 'ed3bc98fdd0af88b22107c506dc4bc6e00fef11ae844d5f0c237199acde24c26',
    'aux': '27ccfe87b0e1e5a71a286e91e587964cdab1fa0a9f1b4778860a299f7eb3eed6',
}
SESSION_SHAS = {
    'install': '93040b51dcb9ba526f93a19f6cab712e1453e8a1613f2293379e110a7f149a89',
    'restore': 'e01b381385f868228462a0f5ff023fa04f7823b35148734027e232a6558e751f',
}
CODE_START, CODE_END = 0x3804b108, 0x3804be70
CODE_FILE_START = 0x92b10c
AUX_START, AUX_END, AUX_FILE_START = 0x3807a764, 0x3807a920, 0x95a768
ENTRY = 0x3804b2f5
TABLE_WORDS = ((0xcc8, ENTRY), (0xebc, 0x3804b111), (0xf20, 0x3804b111), (0xe80, 0x3804b109), (0xd2c, 0x3804b109))
# Exact renderer LOCK, 33 actual-ELF ARM groups. Common first 176 bytes retain
# drawer ABI; no historical tap feedback fields are assumed here.
RUNTIME_CONTEXT = {
    'bytes': 212, 'words': 53, 'common_prefix_bytes': 176,
    'animation_from_offset': 164, 'pending_offset': 168, 'phase_offset': 172,
    'image_offset': 176, 'receive_offset': 180, 'image_pending_offset': 184,
    'generation_offset': 188, 'displayed_generation_offset': 192,
    'server_state_offset': 196, 'server_error_offset': 200,
    'reserved_offset': 204, 'ipv4_offset': 208,
    'ipv4_encoding': 'four raw network-order bytes',
    'reserved_semantics': 'unused received field remains zero',
}
PAYLOAD_LOCK = {
    'main': 'e82a9814e711443e93670f5f60eae9a2a754ceb82199e9bd7d1bef14d2c2d5ee',
    'feedback': '29feeebfd3cac736b53724d844b972e9ef6aeaed9b7710667fb87b5191b5b144',
    'elf': 'ba55f04a751b71e4a2d9933e7459889cf12287e3ec6f97a83f4559d7f7ccfa8b',
    'arm_checks': 33,
    'reviewed_inputs': {
        'native-image-drawer.c': '3bc6affa3969ce4e54264781117b8738fcea9576aeeed1d7f323cdf580a24a8d',
        'native-image-drawer-entry.S': '7ff49a4ee51343cf348cfb9085ff5a7b8a801c2f0dac37d846ee61039e43f37e',
        'native-image-drawer.ld': '43aed8dc7a4a95057c127dfe7f87e2f717a34dffc85d53b0892ed3b7eb3f7868',
        'build-native-image-drawer.sh': 'e8fa4505598dba27abf64c9bc15bd032b1de93274b20186f8d11f4424d6559f6',
        'native-image-drawer.map': '1ba04921738ca2e78744b0e554884b5721dee20c08fe2792879e548797765693',
        'native-image-drawer.md': '5f71982d54d0a5f748ea1efed3ec56ed52f40f97404468fa9ffc5e16c20cd431',
        'network-abi-1.50.10.json': '10a64906deb91c6d1006cb436da829723b9718091ef48c86c61b935ef788da66',
        'image-drawer-arm-offline-result.json': 'fe8cf3c37db6803b0e1d7b9869539a2a08ebc68213e895647ab336ceae18b4f0',
        'test_native_image_drawer_arm.py': '655e7d0665dc4a404b57e5c5ca1dc4944956c90b5a0938d9e640260ee352ea70',
    },
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
    assert RUNTIME_CONTEXT is not None, 'Image-drawer runtime ABI is not locked'
    assert not (PERSIST / 'native-image-drawer-frozen-inputs.json').exists(), 'Frozen image-drawer inputs are immutable'
    for name, expected in PAYLOAD_LOCK['reviewed_inputs'].items():
        checked(OUT / name, expected)
    freezes = []
    for name, expected in PRIOR_FREEZE_SHA.items():
        freezes.append(json.loads(checked(PERSIST / name, expected)))
    counter_freeze = json.loads(checked(PERSIST / 'native-counter-frozen-inputs.json', COUNTER_FREEZE_SHA))
    for name, expected in counter_freeze['sha256'].items():
        checked(ROOT / name, expected)
    for frozen in freezes:
        for name, expected in frozen['sha256'].items():
            checked(ROOT / name, expected)
    image_path = ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin'
    nor = checked(image_path, NOR_SHA)
    assert len(nor) == 0x1000000
    # Reuse the exact frozen ELF32 segmented reader, not a flat address-hole BIN.
    previous = module('frozen_tap_prepare', PERSIST / 'prepare_native_github_tap_inputs.py')
    extension = module('image_drawer_names', PERSIST / 'native_image_drawer_three_page_writer.py')
    generator_path = PERSIST / 'build_native_app_runner.py'
    checked(generator_path, GENERATOR_SHA)
    generator = module('frozen_native_generator', generator_path)
    program_path = OUT / 'native-image-drawer.bin'
    feedback_path = OUT / 'native-image-drawer-feedback.bin'
    elf_path = OUT / 'native-image-drawer.elf'
    program, feedback = program_path.read_bytes(), feedback_path.read_bytes()
    assert sha(program) == PAYLOAD_LOCK['main'] and sha(feedback) == PAYLOAD_LOCK['feedback']
    assert sha(elf_path.read_bytes()) == PAYLOAD_LOCK['elf']
    assert {'main': program, 'feedback': feedback} == previous.linked_segments(elf_path.read_bytes())
    assert 0 < len(program) <= CODE_END - CODE_START and 0 < len(feedback) <= AUX_END - AUX_START
    assert program[:6] == bytes.fromhex('262040427047') and program[8:12] == bytes.fromhex('00207047')
    assert program[0x1ec:0x1f0] == bytes.fromhex('00f000b8')
    sectors, values = {}, {}
    for label, offset in (('code', 0x92b000), ('entry', 0xccd000), ('aux', 0x95a000)):
        baseline_path = PERSIST / f'native-github-tap-fast-patched-sector-{offset:x}.bin'
        baseline = checked(baseline_path, FAST_SECTOR_SHA[label])
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
                          'baseline_kind': 'verified-native-github-tap-fast', 'baseline_source': relative(baseline_path)}
        for state, data in (('original', baseline), ('patched', bytes(patched))):
            path = PERSIST / f'native-image-drawer-{state}-sector-{offset:x}.bin'
            path.write_bytes(data)
            sectors[label][state] = {'path': relative(path), 'bytes': 4096, 'sha256': sha(data)}
            values[('table' if label == 'entry' else label) + '_' + state] = data
    assert sectors['code']['original']['sha256'] != sectors['code']['patched']['sha256'], 'Image payload equals fast tap'
    proof_path = PERSIST / 'github-tap-aux-live-baseline-result.json'
    checked(proof_path, freezes[-1]['sha256'][relative(proof_path)])
    manifest_path = PERSIST / 'native-image-drawer-patch-inputs-1.50.10.json'
    manifest = {
        'offline_only': True, 'frozen': False, 'hardware_actions': 0,
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'local_only_session_configs': [f'diagnostics/mcu-native-image-drawer-{mode}-session.cfg' for mode in ('install', 'restore')],
        'firmware': {'path': relative(image_path), 'bytes': len(nor), 'sha256': NOR_SHA},
        'aux_live_baseline': {'path': relative(proof_path), 'sha256': sha(proof_path.read_bytes()),
                              'sector_sha256': 'fe815dee80d04a6f4b35f238a4c0d05063ecb219ff53132534c71f08ef47f185',
                              'role': 'Historical stock provenance before v1 tap; current image-drawer baseline is the exact frozen fast-tap auxiliary page'},
        'runtime_context': RUNTIME_CONTEXT,
        'rollback': {'kind': 'native-github-tap-fast', 'freeze': 'analysis/persistence/native-github-tap-fast-frozen-inputs.json',
                     'freeze_sha256': PRIOR_FREEZE_SHA['native-github-tap-fast-frozen-inputs.json']},
        'program': {'path': relative(program_path), 'elf': relative(elf_path), 'sha256': sha(program), 'elf_sha256': sha(elf_path.read_bytes()),
                    'bytes': len(program), 'entry': hex(ENTRY), 'start': hex(CODE_START), 'container_end_exclusive': hex(CODE_END),
                    'container_bytes': CODE_END - CODE_START, 'file_start': hex(CODE_FILE_START), 'elf_image_kind': 'two-independent-allocated-spans',
                    'feedback': {'path': relative(feedback_path), 'sha256': sha(feedback), 'bytes': len(feedback), 'start': hex(AUX_START),
                                 'container_end_exclusive': hex(AUX_END), 'file_start': hex(AUX_FILE_START), 'container_bytes': AUX_END - AUX_START}},
        'scope': 'Three exact full NOR pages. Bounded image-drawer main/aux spans only; preserve every other fast-tap byte and every builtin entry. Restore all three exact fast-tap pages, not v1 tap/card/stock.',
        'disabled_commands': {'wifi_recorder': '-ENOSYS stub at 0x3804b109 retained; no new entry mutation'},
        'install_baseline': 'Exact frozen native-github-tap-fast triple only; restore returns this triple before any older version writer can be used.',
        'install_order': ['aux', 'code', 'entry'], 'restore_order': ['entry', 'code', 'aux'], 'sectors': sectors,
    }
    write_json(manifest_path, manifest)
    old_writer = checked(ROOT / 'diagnostics/boot-nor-native-github-tap-fast-runner.cfg', FAST_WRITER_SHA).decode('utf-8')
    old_stages = checked(ROOT / 'diagnostics/boot-nor-native-github-tap-fast-stage-inputs.cfg', FAST_STAGES_SHA).decode('utf-8')
    onecall = checked(PERSIST / 'boot-nor-one-call.bin', ONECALL_SHA)
    assert len(onecall) == 168
    inputs = '# Generated offline only. Image-drawer payload and exact fast-tap triple rollback; no hardware operations.\n'
    inputs += generator.tcl_list('nidi_one_call_words', onecall)
    for label, data in values.items():
        inputs += generator.tcl_list('nidi_' + label + '_words', data)
    inputs += extension.stages(old_stages)
    input_path = ROOT / 'diagnostics/boot-nor-native-image-drawer-stage-inputs.cfg'
    input_path.write_text(inputs, encoding='utf-8')
    writer_path = ROOT / 'diagnostics/boot-nor-native-image-drawer-runner.cfg'
    writer_path.write_text(extension.writer(old_writer), encoding='utf-8')
    for mode, expected in SESSION_SHAS.items():
        old = checked(ROOT / f'diagnostics/mcu-native-github-tap-fast-{mode}-session.cfg', expected).decode('utf-8')
        source = extension.outer(old)
        assert source.count(f'nid_run_native_image_drawer $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$nid_safe_to_resume || !$nid_app_complete))' in source and 'automatic GLOBAL suppressed' in source
        (ROOT / f'diagnostics/mcu-native-image-drawer-{mode}-session.cfg').write_text(source, encoding='utf-8')
    report_path = PERSIST / 'native-image-drawer-writer-preparation.json'
    report = {'offline_only': True, 'hardware_actions': 0, 'frozen': False,
              'cold_poweroff_verification': manifest['cold_poweroff_verification'], 'local_only_session_configs': manifest['local_only_session_configs'],
              'session_git_policy': 'Generated MCU sessions contain vendor boot-header words; exact local files remain excluded from Git.',
              'manifest': relative(manifest_path), 'manifest_sha256': sha(manifest_path.read_bytes()), 'writer': relative(writer_path),
              'writer_sha256': sha(writer_path.read_bytes()), 'stage_inputs': relative(input_path), 'stage_inputs_sha256': sha(input_path.read_bytes()),
              'reused_caller_sha256': ONECALL_SHA, 'reviewed_writer_source_sha256': FAST_WRITER_SHA,
              'three_page_extension': 'analysis/persistence/native_image_drawer_three_page_writer.py',
              'three_page_extension_sha256': sha((PERSIST / 'native_image_drawer_three_page_writer.py').read_bytes()),
              'changes_to_native_caller': 'Exact 168-byte ARM payload. Whole native/public writer and entire executable stages remain exact fast tap after namespace normalization and two baseline error texts plus one rollback comment.',
              'changes_to_public_flow': 'No control-flow, callee, stage whitelist, protection, scratch, readback, cache or completion-gate changes. Fixtures now admit fast tap or image drawer triples; rollback is fast tap.',
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
