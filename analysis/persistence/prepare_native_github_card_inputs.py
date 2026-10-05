"""Prepare independent GitHub card inputs offline; restore returns smooth v1.

This never freezes inputs or accesses hardware. The immutable smooth v1 pages
are the new baseline, while the stock NOR remains checked provenance. The proven
168-byte native caller and guarded writer differ only in namespace and payload.
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
SMOOTH_WRITER_SHA = 'e2f111de80c54a1c954a026f09820a34f059d003239f1d4d1b567bfe26afb45f'
GENERATOR_SHA = '7aaf96b3a4ff0378d1ac9645aece5c037fcdf3a177290f1b6ce964c27e70123e'
ONECALL_SHA = 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'
SMOOTH_SECTOR_SHA = {
    'code': '2dd9c29734f67fea598973f3f44b843f3d25de28d70ecc37da56df0f6b18ec31',
    'entry': 'ed3bc98fdd0af88b22107c506dc4bc6e00fef11ae844d5f0c237199acde24c26',
}
PRIOR_FREEZE_SHA = {
    'native-ui-broker-frozen-inputs.json': 'be8a154b8c5b44e8899062d9373a9395c99ff8ca2d90ddc9e4b824fa1fd1f4ba',
    'native-drawer-frozen-inputs.json': 'b6d30c6efaa28158c6596c4283a41a9be79412d66f099980145434b10fe5b28f',
    'native-drawer-ease-frozen-inputs.json': '1c4e519efc84063024d106966bf159a65cc2b378af81b7ad6cc5bc19888e2e6b',
    'native-drawer-smooth-frozen-inputs.json': 'c464db59ec74849396d6ea2bcd3c0aa9d2110f7766068c6f08a23a82522aa392',
}
SESSION_SHAS = {
    'install': 'ae3d034e5453fa0977e0a7c16ced609293c2bbd26136b88e781b106136e9dde2',
    'restore': '89a1596c35ae338ea86ddb590e34a98f9f8cd9587f9a26d4e3f05b7de82c75a1',
}
CODE_START, CODE_END = 0x3804b108, 0x3804be70
CODE_FILE_START, CODE_FILE_END = 0x92b10c, 0x92be74
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


def linked_bytes(raw):
    assert raw[:7] == b'\x7fELF\x01\x01\x01', 'ELF32 little-endian required'
    assert struct.unpack_from('<H', raw, 18)[0] == 40, 'ARM ELF required'
    assert struct.unpack_from('<I', raw, 24)[0] == ENTRY, 'Fixed Thumb entry drift'
    shoff = struct.unpack_from('<I', raw, 32)[0]
    stride, count = struct.unpack_from('<HH', raw, 46)
    sections = []
    for index in range(count):
        _, kind, flags, address, offset, size, *_ = struct.unpack_from('<10I', raw, shoff + index * stride)
        if flags & 2 and size:
            assert kind == 1 and not flags & 1, 'No writable data/BSS permitted'
            assert CODE_START <= address < address + size <= CODE_END, 'Allocated section leaves reviewed containers'
            assert offset + size <= len(raw), 'Truncated ELF section'
            sections.append((address, raw[offset:offset + size]))
    sections.sort()
    assert sections and sections[0][0] == CODE_START
    image = bytearray()
    for address, data in sections:
        assert address >= CODE_START + len(image), 'Overlapping allocated sections'
        image.extend(bytes(address - CODE_START - len(image)))
        image.extend(data)
    return bytes(image)


def prepare():
    assert not (PERSIST / 'native-github-card-frozen-inputs.json').exists(), 'Frozen card inputs are immutable'
    for name, expected in PRIOR_FREEZE_SHA.items():
        checked(PERSIST / name, expected)
    broker_freeze = json.loads((PERSIST / 'native-ui-broker-frozen-inputs.json').read_text())
    drawer_freeze = json.loads((PERSIST / 'native-drawer-frozen-inputs.json').read_text())
    ease_freeze = json.loads((PERSIST / 'native-drawer-ease-frozen-inputs.json').read_text())
    smooth_freeze = json.loads((PERSIST / 'native-drawer-smooth-frozen-inputs.json').read_text())
    for frozen in (broker_freeze, drawer_freeze, ease_freeze, smooth_freeze):
        for name, expected in frozen['sha256'].items():
            checked(ROOT / name, expected)
    image_path = ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin'
    nor = checked(image_path, NOR_SHA)
    assert len(nor) == 0x1000000
    program_path = OUT / 'native-github-card.bin'
    program = program_path.read_bytes()
    elf_path = OUT / 'native-github-card.elf'
    assert program == linked_bytes(elf_path.read_bytes()), 'BIN does not match complete ELF address span'
    assert 0 < len(program) <= CODE_END - CODE_START
    assert program[:6] == bytes.fromhex('262040427047'), 'ntpcstatus stub drift'
    assert program[8:12] == bytes.fromhex('00207047'), 'showlogo/faclvgl stub drift'
    assert program[0x1ec:0x1f0] == bytes.fromhex('00f000b8'), 'Fixed entry branch drift'
    assert CODE_FILE_START - 0x92b000 == 0x10c
    assert CODE_FILE_END - CODE_FILE_START == CODE_END - CODE_START
    sectors, values = {}, {}
    for label, offset in (('code', 0x92b000), ('entry', 0xccd000)):
        drawer_path = PERSIST / f'native-drawer-smooth-patched-sector-{offset:x}.bin'
        baseline = checked(drawer_path, SMOOTH_SECTOR_SHA[label])
        assert len(baseline) == 4096
        patched = bytearray(baseline)
        if label == 'code':
            patched[0x10c:0x10c + len(program)] = program
            assert patched[:0x10c] == baseline[:0x10c]
            assert patched[0x10c + len(program):] == baseline[0x10c + len(program):]
            assert patched[0xe74:] == baseline[0xe74:], 'Shared code after wifi_recorder worker must be preserved'
            mutations = [{'sector_offset': '0x10c', 'bytes': len(program)}]
        else:
            for word_offset, expected in TABLE_WORDS:
                assert struct.unpack_from('<I', baseline, word_offset)[0] == expected
            assert patched == baseline, 'GitHub card keeps every existing builtin entry unchanged'
            mutations = []
        sectors[label] = {'offset': hex(offset), 'mutations': mutations,
                          'baseline_kind': 'verified-native-drawer-smooth-v1',
                          'baseline_source': relative(drawer_path)}
        for state, data in (('original', baseline), ('patched', bytes(patched))):
            path = PERSIST / f'native-github-card-{state}-sector-{offset:x}.bin'
            path.write_bytes(data)
            sectors[label][state] = {'path': relative(path), 'bytes': len(data), 'sha256': sha(data)}
            values[('table' if label == 'entry' else label) + '_' + state] = data
    assert sectors['code']['original']['sha256'] != sectors['code']['patched']['sha256'], 'Card payload still equals smooth v1'
    manifest_path = PERSIST / 'native-github-card-patch-inputs-1.50.10.json'
    manifest = {
        'offline_only': True, 'frozen': False, 'hardware_actions': 0,
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'firmware': {'path': relative(image_path), 'bytes': len(nor), 'sha256': sha(nor)},
        'rollback': {'kind': 'native-drawer-smooth-v1', 'freeze': 'analysis/persistence/native-drawer-smooth-frozen-inputs.json',
                     'freeze_sha256': sha((PERSIST / 'native-drawer-smooth-frozen-inputs.json').read_bytes())},
        'program': {'path': relative(program_path), 'elf': relative(elf_path), 'sha256': sha(program),
                    'elf_sha256': sha(elf_path.read_bytes()), 'bytes': len(program), 'entry': hex(ENTRY),
                    'start': hex(CODE_START), 'container_end_exclusive': hex(CODE_END),
                    'container_bytes': CODE_END - CODE_START, 'file_start': hex(CODE_FILE_START)},
        'scope': 'Replace only the existing smooth v1 code span with the static GitHub information card, preserving smooth gesture ownership. Original means exact verified smooth v1 rollback pages, not stock firmware. All builtin entries remain unchanged, including disabled wifi_recorder. Preserve shared code at/after 0x3804be70 and every other NOR byte.',
        'disabled_commands': {'wifi_recorder': '-ENOSYS stub at 0x3804b109 retained from smooth v1; no new entry mutation'},
        'install_baseline': 'Exact native-drawer-smooth-v1 code and entry pages only. Ease, first drawer, broker, stock and old counter require their separate reviewed flow first.',
        'install_order': ['code', 'entry'], 'restore_order': ['entry', 'code'], 'sectors': sectors,
    }
    write_json(manifest_path, manifest)
    writer_source = ROOT / 'diagnostics/boot-nor-native-drawer-smooth-runner.cfg'
    writer = checked(writer_source, SMOOTH_WRITER_SHA).decode('utf-8').replace('\r\n', '\n')
    generator_path = PERSIST / 'build_native_app_runner.py'
    checked(generator_path, GENERATOR_SHA)
    spec = importlib.util.spec_from_file_location('reviewed_native_app_generator', generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stages = module.STAGES.replace('bnai_', 'ngci_')
    onecall = checked(PERSIST / 'boot-nor-one-call.bin', ONECALL_SHA)
    assert len(onecall) == 168
    inputs = '# Generated offline only. GitHub card payload and exact smooth v1 rollback pages; no hardware operations.\n'
    inputs += module.tcl_list('ngci_one_call_words', onecall)
    for label, data in values.items():
        inputs += module.tcl_list('ngci_' + label + '_words', data)
    inputs += stages
    input_path = ROOT / 'diagnostics/boot-nor-native-github-card-stage-inputs.cfg'
    input_path.write_text(inputs, encoding='utf-8')
    writer = writer.replace('ndrs_', 'ngc_').replace('ndrsi_', 'ngci_').replace('native-drawer-smooth', 'native-github-card')
    writer = writer.replace('ngc_run_native_drawer_smooth', 'ngc_run_native_github_card')
    assert writer.count('Install requires both exact ease-v1 sector baselines') == 1
    assert writer.count('Restore requires both exact ease-v1 or both exact drawer-smooth sector baselines') == 1
    writer = writer.replace('Install requires both exact ease-v1 sector baselines', 'Install requires both exact smooth-v1 sector baselines')
    writer = writer.replace('Restore requires both exact ease-v1 or both exact drawer-smooth sector baselines', 'Restore requires both exact smooth-v1 or both exact github-card sector baselines')
    writer_path = ROOT / 'diagnostics/boot-nor-native-github-card-runner.cfg'
    writer_path.write_text(writer, encoding='utf-8')
    for mode, expected in SESSION_SHAS.items():
        source = checked(ROOT / f'diagnostics/mcu-native-drawer-smooth-{mode}-session.cfg', expected).decode('utf-8').replace('\r\n', '\n')
        source = source.replace('native-drawer-smooth', 'native-github-card').replace('ndrs_', 'ngc_').replace('ndrsi_', 'ngci_')
        source = source.replace('ngc_run_native_drawer_smooth', 'ngc_run_native_github_card')
        assert source.count(f'ngc_run_native_github_card $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$ngc_safe_to_resume || !$ngc_app_complete))' in source
        assert 'automatic GLOBAL suppressed' in source
        (ROOT / f'diagnostics/mcu-native-github-card-{mode}-session.cfg').write_text(source, encoding='utf-8')
    report_path = PERSIST / 'native-github-card-writer-preparation.json'
    report = {
        'offline_only': True, 'hardware_actions': 0, 'frozen': False,
        'cold_poweroff_verification': {'status': 'skipped_by_user_request', 'requested': False},
        'manifest': relative(manifest_path), 'manifest_sha256': sha(manifest_path.read_bytes()),
        'writer': relative(writer_path), 'writer_sha256': sha(writer_path.read_bytes()),
        'stage_inputs': relative(input_path), 'stage_inputs_sha256': sha(input_path.read_bytes()),
        'reused_caller_sha256': ONECALL_SHA, 'reviewed_writer_source_sha256': SMOOTH_WRITER_SHA,
        'changes_to_native_caller': 'None. Namespace/source filenames only; exact 168-byte payload and all context, watchdog, controller, protection, timeout and closure checks retained.',
        'changes_to_public_flow': 'Exact smooth-v1 install baseline; restore accepts exact smooth-v1 or github-card code pages with the unchanged drawer entry page and returns smooth v1. Ease/first-drawer/broker/stock/counter/unknown code pages refused before native calls. Entry page alone cannot distinguish these two drawer variants.',
        'pending': 'Independent program/writer reviews and current-payload offline mocks must pass before explicit freezing. Preparation does not permit device execution.',
    }
    write_json(report_path, report)
    for frozen in (broker_freeze, drawer_freeze, ease_freeze, smooth_freeze):
        for name, expected in frozen['sha256'].items():
            checked(ROOT / name, expected)
    print(json.dumps({'program_bytes': len(program), 'manifest': relative(manifest_path),
                      'manifest_sha256': report['manifest_sha256'], 'writer_sha256': report['writer_sha256'],
                      'stage_inputs_sha256': report['stage_inputs_sha256'], 'frozen': False, 'hardware_actions': 0}, indent=2))


if __name__ == '__main__':
    prepare()
