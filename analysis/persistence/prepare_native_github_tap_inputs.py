"""Prepare independent GitHub tap inputs offline; restore returns the original GitHub card.

This never freezes inputs or accesses hardware. The immutable GitHub card pages
are the new baseline, while the stock NOR remains checked provenance. The proven
168-byte native caller remains exact. The writer adds a bounded third auxiliary
page and requires independent review of its changed orchestration/allowlist.
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
CARD_WRITER_SHA = '9bc8faf960b37962647f3336532edb82a36b5da9e18674ef320d95dc13d8cfd8'
GENERATOR_SHA = '7aaf96b3a4ff0378d1ac9645aece5c037fcdf3a177290f1b6ce964c27e70123e'
ONECALL_SHA = 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'
CARD_SECTOR_SHA = {
    'code': '53beefb16316e2a326030aabf92c0245f2eb49bb0cbccd03dcac1fe544e4e265',
    'entry': 'ed3bc98fdd0af88b22107c506dc4bc6e00fef11ae844d5f0c237199acde24c26',
}
PRIOR_FREEZE_SHA = {
    'native-ui-broker-frozen-inputs.json': 'be8a154b8c5b44e8899062d9373a9395c99ff8ca2d90ddc9e4b824fa1fd1f4ba',
    'native-drawer-frozen-inputs.json': 'b6d30c6efaa28158c6596c4283a41a9be79412d66f099980145434b10fe5b28f',
    'native-drawer-ease-frozen-inputs.json': '1c4e519efc84063024d106966bf159a65cc2b378af81b7ad6cc5bc19888e2e6b',
    'native-drawer-smooth-frozen-inputs.json': 'c464db59ec74849396d6ea2bcd3c0aa9d2110f7766068c6f08a23a82522aa392',
    'native-github-card-frozen-inputs.json': '7bd88c1f217fd53219a054bf3c24ef197ee5666133d45f1557bfd8173c4c41db',
}
SESSION_SHAS = {
    'install': '569b4e5de2c46ac031f815e99e22733741d30ebe3568090663a71624e875d5e5',
    'restore': '937fa73201a1abe2b354ca77d0ef98e33b39448040c15acc3b6c62439f5ccaf8',
}
CODE_START, CODE_END = 0x3804b108, 0x3804be70
CODE_FILE_START, CODE_FILE_END = 0x92b10c, 0x92be74
AUX_START, AUX_END, AUX_FILE_START = 0x3807a764, 0x3807a920, 0x95a768
AUX_SECTOR_SHA = 'fe815dee80d04a6f4b35f238a4c0d05063ecb219ff53132534c71f08ef47f185'
ENTRY = 0x3804b2f5
TABLE_WORDS = ((0xcc8, ENTRY), (0xebc, 0x3804b111), (0xf20, 0x3804b111), (0xe80, 0x3804b109), (0xd2c, 0x3804b109))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    raw = path.read_bytes()
    assert sha(raw) == expected, 'Reviewed dependency changed: ' + str(path)
    return raw


def relative(path):
    return path.relative_to(ROOT).as_posix()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def linked_segments(raw):
    assert raw[:7] == b'\x7fELF\x01\x01\x01', 'ELF32 little-endian required'
    assert struct.unpack_from('<H', raw, 18)[0] == 40, 'ARM ELF required'
    assert struct.unpack_from('<I', raw, 24)[0] == ENTRY, 'Fixed Thumb entry drift'
    shoff = struct.unpack_from('<I', raw, 32)[0]
    stride, count = struct.unpack_from('<HH', raw, 46)
    sections = {'main': [], 'feedback': []}
    for index in range(count):
        _, kind, flags, address, offset, size, *_ = struct.unpack_from('<10I', raw, shoff + index * stride)
        if flags & 2 and size:
            assert kind == 1 and not flags & 1, 'No writable data/BSS permitted'
            label = next((name for name, lo, hi in (('main', CODE_START, CODE_END), ('feedback', AUX_START, AUX_END))
                          if lo <= address < address + size <= hi), None)
            assert label is not None, 'Allocated section leaves either reviewed container'
            assert offset + size <= len(raw), 'Truncated ELF section'
            sections[label].append((address, raw[offset:offset + size]))
    images = {}
    for label, start in (('main', CODE_START), ('feedback', AUX_START)):
        spans = sorted(sections[label])
        assert spans and spans[0][0] == start, 'Required independent segment is missing'
        image = bytearray()
        for address, data in spans:
            assert address >= start + len(image), 'Overlapping allocated sections'
            image.extend(bytes(address - start - len(image)))
            image.extend(data)
        images[label] = bytes(image)
    return images


def prepare():
    assert not (PERSIST / 'native-github-tap-frozen-inputs.json').exists(), 'Frozen tap inputs are immutable'
    for name, expected in PRIOR_FREEZE_SHA.items():
        checked(PERSIST / name, expected)
    broker_freeze = json.loads((PERSIST / 'native-ui-broker-frozen-inputs.json').read_text())
    drawer_freeze = json.loads((PERSIST / 'native-drawer-frozen-inputs.json').read_text())
    ease_freeze = json.loads((PERSIST / 'native-drawer-ease-frozen-inputs.json').read_text())
    smooth_freeze = json.loads((PERSIST / 'native-drawer-smooth-frozen-inputs.json').read_text())
    card_freeze = json.loads((PERSIST / 'native-github-card-frozen-inputs.json').read_text())
    for frozen in (broker_freeze, drawer_freeze, ease_freeze, smooth_freeze, card_freeze):
        for name, expected in frozen['sha256'].items():
            checked(ROOT / name, expected)
    image_path = ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin'
    nor = checked(image_path, NOR_SHA)
    assert len(nor) == 0x1000000
    program_path = OUT / 'native-github-tap.bin'
    program = program_path.read_bytes()
    feedback_path = OUT / 'native-github-tap-feedback.bin'
    feedback = feedback_path.read_bytes()
    elf_path = OUT / 'native-github-tap.elf'
    assert {'main': program, 'feedback': feedback} == linked_segments(elf_path.read_bytes()), 'Segment BINs do not match every ELF allocated byte/gap'
    assert 0 < len(program) <= CODE_END - CODE_START
    assert 0 < len(feedback) <= AUX_END - AUX_START
    proof_path = PERSIST / 'github-tap-aux-live-baseline-result.json'
    proof = json.loads(proof_path.read_text())
    assert proof['read_only_live_baseline'] and proof['matches_exact_stock_backup_page']
    assert proof['target_writes'] == proof['halt_reset_native_calls'] == 0
    assert proof['offline_backup_sha256'] == NOR_SHA and proof['live_sha256'] == AUX_SECTOR_SHA
    assert proof['NOR_sector'] == '0x95a000' and proof['bytes'] == 4096
    assert program[:6] == bytes.fromhex('262040427047'), 'ntpcstatus stub drift'
    assert program[8:12] == bytes.fromhex('00207047'), 'showlogo/faclvgl stub drift'
    assert program[0x1ec:0x1f0] == bytes.fromhex('00f000b8'), 'Fixed entry branch drift'
    assert CODE_FILE_START - 0x92b000 == 0x10c
    assert CODE_FILE_END - CODE_FILE_START == CODE_END - CODE_START
    sectors, values = {}, {}
    for label, offset in (('code', 0x92b000), ('entry', 0xccd000), ('aux', 0x95a000)):
        if label == 'aux':
            drawer_path = image_path
            baseline = nor[offset:offset + 4096]
            assert sha(baseline) == AUX_SECTOR_SHA
        else:
            drawer_path = PERSIST / f'native-github-card-patched-sector-{offset:x}.bin'
            baseline = checked(drawer_path, CARD_SECTOR_SHA[label])
        assert len(baseline) == 4096
        patched = bytearray(baseline)
        if label == 'code':
            patched[0x10c:0x10c + len(program)] = program
            assert patched[:0x10c] == baseline[:0x10c]
            assert patched[0x10c + len(program):] == baseline[0x10c + len(program):]
            assert patched[0xe74:] == baseline[0xe74:], 'Shared code after wifi_recorder worker must be preserved'
            mutations = [{'sector_offset': '0x10c', 'bytes': len(program)}]
        elif label == 'aux':
            patched[0x768:0x768 + len(feedback)] = feedback
            assert patched[:0x768] == baseline[:0x768] and patched[0x768 + len(feedback):] == baseline[0x768 + len(feedback):]
            assert patched[0x924:] == baseline[0x924:], 'Factory/shared helpers after auxiliary slot changed'
            mutations = [{'sector_offset': '0x768', 'bytes': len(feedback)}]
        else:
            for word_offset, expected in TABLE_WORDS:
                assert struct.unpack_from('<I', baseline, word_offset)[0] == expected
            assert patched == baseline, 'GitHub card keeps every existing builtin entry unchanged'
            mutations = []
        sectors[label] = {'offset': hex(offset), 'mutations': mutations,
                          'baseline_kind': 'verified-stock-auxiliary-page' if label == 'aux' else 'verified-native-github-card-v1',
                          'baseline_source': relative(drawer_path)}
        if label == 'aux':
            sectors[label]['baseline_source_offset'] = hex(offset)
        for state, data in (('original', baseline), ('patched', bytes(patched))):
            path = PERSIST / f'native-github-tap-{state}-sector-{offset:x}.bin'
            path.write_bytes(data)
            sectors[label][state] = {'path': relative(path), 'bytes': len(data), 'sha256': sha(data)}
            values[('table' if label == 'entry' else label) + '_' + state] = data
    assert sectors['code']['original']['sha256'] != sectors['code']['patched']['sha256'], 'Tap payload still equals the original GitHub card'
    manifest_path = PERSIST / 'native-github-tap-patch-inputs-1.50.10.json'
    manifest = {
        'offline_only': True, 'frozen': False, 'hardware_actions': 0,
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'local_only_session_configs': ['diagnostics/mcu-native-github-tap-install-session.cfg',
                                       'diagnostics/mcu-native-github-tap-restore-session.cfg'],
        'firmware': {'path': relative(image_path), 'bytes': len(nor), 'sha256': sha(nor)},
        'aux_live_baseline': {'path': relative(proof_path), 'sha256': sha(proof_path.read_bytes()),
                              'sector_sha256': AUX_SECTOR_SHA},
        'runtime_context': {'bytes': 184, 'words': 46, 'feedback_ms_offset': 176, 'feedback_pending_offset': 180,
                            'animation_from_offset': 164, 'pending_offset': 168, 'phase_offset': 172},
        'rollback': {'kind': 'native-github-card-v1', 'freeze': 'analysis/persistence/native-github-card-frozen-inputs.json',
                     'freeze_sha256': sha((PERSIST / 'native-github-card-frozen-inputs.json').read_bytes())},
        'program': {'path': relative(program_path), 'elf': relative(elf_path), 'sha256': sha(program),
                    'elf_sha256': sha(elf_path.read_bytes()), 'bytes': len(program), 'entry': hex(ENTRY),
                    'start': hex(CODE_START), 'container_end_exclusive': hex(CODE_END),
                    'container_bytes': CODE_END - CODE_START, 'file_start': hex(CODE_FILE_START),
                    'elf_image_kind': 'two-independent-allocated-spans',
                    'feedback': {'path': relative(feedback_path), 'sha256': sha(feedback), 'bytes': len(feedback),
                                 'start': hex(AUX_START), 'container_end_exclusive': hex(AUX_END),
                                 'file_start': hex(AUX_FILE_START), 'container_bytes': AUX_END - AUX_START}},
        'scope': 'Three exact full NOR pages. Replace the card main code and only bounded factory socket-worker slot 0x3807a764..0x3807a920 with segmented tap feedback; every builtin entry and every other byte stay unchanged. Restore original card code and stock auxiliary page. Preserve helpers at/after 0x3804be70 and 0x3807a920.',
        'disabled_commands': {'wifi_recorder': '-ENOSYS stub at 0x3804b109 retained from smooth v1; no new entry mutation'},
        'install_baseline': 'Exact native-github-card-v1 code and entry pages only. Smooth, ease, first drawer, broker, stock and old counter require their separate reviewed flow first.',
        'install_order': ['aux', 'code', 'entry'], 'restore_order': ['entry', 'code', 'aux'], 'sectors': sectors,
    }
    write_json(manifest_path, manifest)
    writer_source = ROOT / 'diagnostics/boot-nor-native-github-card-runner.cfg'
    writer = checked(writer_source, CARD_WRITER_SHA).decode('utf-8').replace('\r\n', '\n')
    generator_path = PERSIST / 'build_native_app_runner.py'
    checked(generator_path, GENERATOR_SHA)
    spec = importlib.util.spec_from_file_location('reviewed_native_app_generator', generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    extension_path = PERSIST / 'native_github_tap_three_page_writer.py'
    extension_spec = importlib.util.spec_from_file_location('tap_three_page_extension', extension_path)
    extension = importlib.util.module_from_spec(extension_spec)
    extension_spec.loader.exec_module(extension)
    stages = extension.stages(module.STAGES)
    onecall = checked(PERSIST / 'boot-nor-one-call.bin', ONECALL_SHA)
    assert len(onecall) == 168
    inputs = '# Generated offline only. GitHub tap payload and exact GitHub card rollback pages; no hardware operations.\n'
    inputs += module.tcl_list('ngti_one_call_words', onecall)
    for label, data in values.items():
        inputs += module.tcl_list('ngti_' + label + '_words', data)
    inputs += stages
    input_path = ROOT / 'diagnostics/boot-nor-native-github-tap-stage-inputs.cfg'
    input_path.write_text(inputs, encoding='utf-8')
    writer = extension.writer(writer)
    writer_path = ROOT / 'diagnostics/boot-nor-native-github-tap-runner.cfg'
    writer_path.write_text(writer, encoding='utf-8')
    for mode, expected in SESSION_SHAS.items():
        source = checked(ROOT / f'diagnostics/mcu-native-github-card-{mode}-session.cfg', expected).decode('utf-8').replace('\r\n', '\n')
        source = source.replace('native-github-card', 'native-github-tap').replace('ngc_', 'ngt_').replace('ngci_', 'ngti_')
        source = source.replace('ngt_run_native_github_card', 'ngt_run_native_github_tap')
        assert source.count(f'ngt_run_native_github_tap $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$ngt_safe_to_resume || !$ngt_app_complete))' in source
        assert 'automatic GLOBAL suppressed' in source
        (ROOT / f'diagnostics/mcu-native-github-tap-{mode}-session.cfg').write_text(source, encoding='utf-8')
    report_path = PERSIST / 'native-github-tap-writer-preparation.json'
    report = {
        'offline_only': True, 'hardware_actions': 0, 'frozen': False,
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'local_only_session_configs': manifest['local_only_session_configs'],
        'session_git_policy': 'Both generated MCU sessions contain the unchanged vendor boot_header_page words; keep these exact local files excluded from Git.',
        'manifest': relative(manifest_path), 'manifest_sha256': sha(manifest_path.read_bytes()),
        'writer': relative(writer_path), 'writer_sha256': sha(writer_path.read_bytes()),
        'stage_inputs': relative(input_path), 'stage_inputs_sha256': sha(input_path.read_bytes()),
        'reused_caller_sha256': ONECALL_SHA, 'reviewed_writer_source_sha256': CARD_WRITER_SHA,
        'three_page_extension': relative(extension_path), 'three_page_extension_sha256': sha(extension_path.read_bytes()),
        'changes_to_native_caller': 'Exact 168-byte ARM payload and native caller prefix retained. New fixed auxiliary stages and three-page orchestration alter its admitted inputs; require separate peer review.',
        'changes_to_public_flow': 'All three pages must form exact card+stock-aux or exact tap triples; mixed triples rejected before native calls. Aux-first install and main-before-aux restore each enforce whole-page readback/status gates. Third page 95a000 adds exact allowlisted erase/program/I/D invalidation stages only. Independent writer peer review required.',
        'pending': 'Independent program/writer reviews and current-payload offline mocks must pass before explicit freezing. Preparation does not permit device execution.',
    }
    write_json(report_path, report)
    for frozen in (broker_freeze, drawer_freeze, ease_freeze, smooth_freeze, card_freeze):
        for name, expected in frozen['sha256'].items():
            checked(ROOT / name, expected)
    print(json.dumps({'program_bytes': len(program), 'manifest': relative(manifest_path),
                      'manifest_sha256': report['manifest_sha256'], 'writer_sha256': report['writer_sha256'],
                      'stage_inputs_sha256': report['stage_inputs_sha256'], 'frozen': False, 'hardware_actions': 0}, indent=2))


if __name__ == '__main__':
    prepare()
