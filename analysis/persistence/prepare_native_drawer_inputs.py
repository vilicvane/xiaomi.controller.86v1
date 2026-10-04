"""Prepare independent drawer inputs offline; restore returns the verified broker.

This never freezes inputs or accesses hardware. The immutable broker v1 pages
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
BROKER_WRITER_SHA = '16ede0302b05be1208dac176c3ee6b8f92e459c7dfee91a27a0d74324053c3b8'
GENERATOR_SHA = '7aaf96b3a4ff0378d1ac9645aece5c037fcdf3a177290f1b6ce964c27e70123e'
ONECALL_SHA = 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'
BROKER_SECTOR_SHA = {
    'code': '59552c638d1c590449e540f3fd103729f414f2998ced519e8fe18b65ab5a136d',
    'entry': '3e640058142473156b76d160be85a9543d07385a03828d887d4deeeb1c362916',
}
SESSION_SHAS = {
    'install': 'ff8aad2b26cc28037ea7d60903a680c38ccb6f0a00405c9b9d1612b138dd5cd6',
    'restore': 'b0e8032239f14cacd260301d1beeb5c8327ee789aa0ff3a2941ce4e13d2ed91a',
}
CODE_START, CODE_END = 0x3804b108, 0x3804be70
CODE_FILE_START, CODE_FILE_END = 0x92b10c, 0x92be74
ENTRY = 0x3804b2f5
TABLE_WORDS = ((0xcc8, ENTRY), (0xebc, 0x3804b111), (0xf20, 0x3804b111), (0xe80, 0x3804b109))
WIFI_RECORDER_WORD = (0xd2c, 0x38048c41, 0x3804b109)


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
    assert not (PERSIST / 'native-drawer-frozen-inputs.json').exists(), 'Frozen drawer inputs are immutable'
    broker_freeze = json.loads((PERSIST / 'native-ui-broker-frozen-inputs.json').read_text())
    for name, expected in broker_freeze['sha256'].items():
        checked(ROOT / name, expected)
    image_path = ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin'
    nor = checked(image_path, NOR_SHA)
    assert len(nor) == 0x1000000
    program_path = OUT / 'native-drawer.bin'
    program = program_path.read_bytes()
    elf_path = OUT / 'native-drawer.elf'
    assert program == linked_bytes(elf_path.read_bytes()), 'BIN does not match complete ELF address span'
    assert 0 < len(program) <= CODE_END - CODE_START
    assert program[:6] == bytes.fromhex('262040427047'), 'ntpcstatus stub drift'
    assert program[8:12] == bytes.fromhex('00207047'), 'showlogo/faclvgl stub drift'
    assert program[0x1ec:0x1f0] == bytes.fromhex('00f000b8'), 'Fixed entry branch drift'
    assert CODE_FILE_START - 0x92b000 == 0x10c
    assert CODE_FILE_END - CODE_FILE_START == CODE_END - CODE_START
    sectors, values = {}, {}
    for label, offset in (('code', 0x92b000), ('entry', 0xccd000)):
        broker_path = OUT / f'native-ui-broker-patched-sector-{offset:x}.bin'
        baseline = checked(broker_path, BROKER_SECTOR_SHA[label])
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
            word_offset, before, after = WIFI_RECORDER_WORD
            assert struct.unpack_from('<I', baseline, word_offset)[0] == before
            struct.pack_into('<I', patched, word_offset, after)
            changed = {i for i, (a, b) in enumerate(zip(baseline, patched)) if a != b}
            assert changed <= set(range(word_offset, word_offset + 4))
            mutations = [{'sector_offset': hex(word_offset), 'bytes': 4,
                          'before': hex(before), 'after': hex(after)}]
        sectors[label] = {'offset': hex(offset), 'mutations': mutations,
                          'baseline_kind': 'verified-native-ui-broker-v1',
                          'baseline_source': relative(broker_path)}
        for state, data in (('original', baseline), ('patched', bytes(patched))):
            path = PERSIST / f'native-drawer-{state}-sector-{offset:x}.bin'
            path.write_bytes(data)
            sectors[label][state] = {'path': relative(path), 'bytes': len(data), 'sha256': sha(data)}
            values[('table' if label == 'entry' else label) + '_' + state] = data
    assert sectors['code']['original']['sha256'] != sectors['code']['patched']['sha256'], 'Drawer payload still equals broker'
    manifest_path = PERSIST / 'native-drawer-patch-inputs-1.50.10.json'
    manifest = {
        'offline_only': True, 'frozen': False, 'hardware_actions': 0,
        'firmware': {'path': relative(image_path), 'bytes': len(nor), 'sha256': sha(nor)},
        'rollback': {'kind': 'native-ui-broker-v1', 'freeze': 'analysis/persistence/native-ui-broker-frozen-inputs.json',
                     'freeze_sha256': sha((PERSIST / 'native-ui-broker-frozen-inputs.json').read_bytes())},
        'program': {'path': relative(program_path), 'elf': relative(elf_path), 'sha256': sha(program),
                    'elf_sha256': sha(elf_path.read_bytes()), 'bytes': len(program), 'entry': hex(ENTRY),
                    'start': hex(CODE_START), 'container_end_exclusive': hex(CODE_END),
                    'container_bytes': CODE_END - CODE_START, 'file_start': hex(CODE_FILE_START)},
        'scope': 'Replace the existing broker code span and audited unused wifi_recorder worker up to 0x3804be70; disable wifi_recorder builtin via -ENOSYS stub. Original means exact verified broker v1 rollback pages, not stock firmware. Preserve shared code at/after 0x3804be70, original vapp/NTP, all identity/config and every other NOR byte.',
        'disabled_commands': {'wifi_recorder': '-ENOSYS stub at 0x3804b109; replaces builtin 0x38048c41 at NOR 0xccdd2c so borrowed pthread worker 0x3804bc98 cannot be started by this command'},
        'install_baseline': 'Exact native-ui-broker-v1 code and entry pages only. Stock and old counter require their separate reviewed flow first.',
        'install_order': ['code', 'entry'], 'restore_order': ['entry', 'code'], 'sectors': sectors,
    }
    write_json(manifest_path, manifest)
    writer_source = ROOT / 'diagnostics/boot-nor-native-ui-broker-runner.cfg'
    writer = checked(writer_source, BROKER_WRITER_SHA).decode('utf-8').replace('\r\n', '\n')
    generator_path = PERSIST / 'build_native_app_runner.py'
    checked(generator_path, GENERATOR_SHA)
    spec = importlib.util.spec_from_file_location('reviewed_native_app_generator', generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stages = module.STAGES.replace('bnai_', 'ndri_')
    onecall = checked(PERSIST / 'boot-nor-one-call.bin', ONECALL_SHA)
    assert len(onecall) == 168
    inputs = '# Generated offline only. Drawer payload and exact broker rollback pages; no hardware operations.\n'
    inputs += module.tcl_list('ndri_one_call_words', onecall)
    for label, data in values.items():
        inputs += module.tcl_list('ndri_' + label + '_words', data)
    inputs += stages
    input_path = ROOT / 'diagnostics/boot-nor-native-drawer-stage-inputs.cfg'
    input_path.write_text(inputs, encoding='utf-8')
    writer = writer.replace('nub_', 'ndr_').replace('nubi_', 'ndri_').replace('native-ui-broker', 'native-drawer')
    writer = writer.replace('ndr_run_native_ui_broker', 'ndr_run_native_drawer')
    assert writer.count('Install requires both exact original sector baselines') == 1
    assert writer.count('Restore requires both exact original or both exact broker sector baselines') == 1
    writer = writer.replace('Install requires both exact original sector baselines', 'Install requires both exact broker-v1 sector baselines')
    writer = writer.replace('Restore requires both exact original or both exact broker sector baselines', 'Restore requires both exact broker-v1 or both exact drawer sector baselines')
    writer_path = ROOT / 'diagnostics/boot-nor-native-drawer-runner.cfg'
    writer_path.write_text(writer, encoding='utf-8')
    for mode, expected in SESSION_SHAS.items():
        source = checked(ROOT / f'diagnostics/mcu-native-ui-broker-{mode}-session.cfg', expected).decode('utf-8').replace('\r\n', '\n')
        source = source.replace('native-ui-broker', 'native-drawer').replace('nub_', 'ndr_').replace('nubi_', 'ndri_')
        source = source.replace('ndr_run_native_ui_broker', 'ndr_run_native_drawer')
        assert source.count(f'ndr_run_native_drawer $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$ndr_safe_to_resume || !$ndr_app_complete))' in source
        assert 'automatic GLOBAL suppressed' in source
        (ROOT / f'diagnostics/mcu-native-drawer-{mode}-session.cfg').write_text(source, encoding='utf-8')
    report_path = PERSIST / 'native-drawer-writer-preparation.json'
    report = {
        'offline_only': True, 'hardware_actions': 0, 'frozen': False,
        'manifest': relative(manifest_path), 'manifest_sha256': sha(manifest_path.read_bytes()),
        'writer': relative(writer_path), 'writer_sha256': sha(writer_path.read_bytes()),
        'stage_inputs': relative(input_path), 'stage_inputs_sha256': sha(input_path.read_bytes()),
        'reused_caller_sha256': ONECALL_SHA, 'reviewed_writer_source_sha256': BROKER_WRITER_SHA,
        'changes_to_native_caller': 'None. Namespace/source filenames only; exact 168-byte payload and all context, watchdog, controller, protection, timeout and closure checks retained.',
        'changes_to_public_flow': 'Exact broker-v1/broker-v1 install baseline; restore accepts matched exact broker-v1/broker-v1 or drawer/drawer pages and restores broker v1. Mixed code/table, stock/counter/unknown pages refused before native calls.',
        'pending': 'Independent program/writer reviews and current-payload offline mocks must pass before explicit freezing. Preparation does not permit device execution.',
    }
    write_json(report_path, report)
    for name, expected in broker_freeze['sha256'].items():
        checked(ROOT / name, expected)
    print(json.dumps({'program_bytes': len(program), 'manifest': relative(manifest_path),
                      'manifest_sha256': report['manifest_sha256'], 'writer_sha256': report['writer_sha256'],
                      'stage_inputs_sha256': report['stage_inputs_sha256'], 'frozen': False, 'hardware_actions': 0}, indent=2))


if __name__ == '__main__':
    prepare()
