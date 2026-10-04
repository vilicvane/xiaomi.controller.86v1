"""Prepare the separate 1.50.10 broker pipeline offline; never freeze or access hardware.

The unchanged proven native caller is cloned with a distinct namespace. Only
the two exact sector payloads and the stricter public baseline policy change.
Preparation is not approval: run independent reviews and mocks before freezing.
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
ORIGINAL_WRITER_SHA = 'a39977808f17c040dd8d2969d548beee1377cc20c095c2084e3aa5df01854edb'
ORIGINAL_GENERATOR_SHA = '7aaf96b3a4ff0378d1ac9645aece5c037fcdf3a177290f1b6ce964c27e70123e'
ONECALL_SHA = 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32'
SESSION_SHAS = {
    'install': '5e0d3785918921f7ea1ddaf974118857be9e8ee9c27bb0ae923f43592bef9206',
    'restore': '79a44c8f3065dbc165604c0dc417411a0a247044e38cd952483828d9d9d537ca',
}
CODE_START, CODE_END = 0x3804b108, 0x3804bc98
CODE_FILE_START, CODE_FILE_END = 0x92b10c, 0x92bc9c
ENTRY = 0x3804b2f5
TABLE_WORDS = ((0xcc8, 0x3818f9fd, ENTRY),
               (0xebc, 0x3804b2f5, 0x3804b111),
               (0xf20, 0x3804b87d, 0x3804b111))


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
    # Preserve all existing counter inputs, including their exact CRLF bytes.
    old_freeze = json.loads((PERSIST / 'native-counter-frozen-inputs.json').read_text())
    for name, expected in old_freeze['sha256'].items():
        checked(ROOT / name, expected)
    image_path = ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin'
    nor = checked(image_path, NOR_SHA)
    assert len(nor) == 0x1000000
    program_path = OUT / 'native-ui-broker.bin'
    program = program_path.read_bytes()
    elf_path = OUT / 'native-ui-broker.elf'
    assert program == linked_bytes(elf_path.read_bytes()), 'BIN does not match complete ELF address span'
    assert 0 < len(program) <= CODE_END - CODE_START
    # Inert ntpcstatus and showlogo entry stubs, checked as exact Thumb opcodes.
    assert program[:6] == bytes.fromhex('262040427047')
    assert program[8:12] == bytes.fromhex('00207047')
    # Fixed four-byte B.W at b2f4 must branch to broker_main at b2f8;
    # this catches the historical four-byte linked/load alignment error.
    assert program[0x1ec:0x1f0] == bytes.fromhex('00f000b8'), 'Broker entry branch changed'
    assert CODE_FILE_START - 0x92b000 == 0x10c and CODE_FILE_END - CODE_FILE_START == CODE_END - CODE_START
    assert struct.unpack_from('<I', nor, 0xccde80)[0] == 0x3804b109, 'ntpcstatus builtin must still select inert stub'
    sectors = {}
    values = {}
    for label, offset in (('code', 0x92b000), ('entry', 0xccd000)):
        original = nor[offset:offset + 4096]
        patched = bytearray(original)
        if label == 'code':
            patched[0x10c:0x10c + len(program)] = program
            assert patched[:0x10c] == original[:0x10c]
            assert patched[0x10c + len(program):] == original[0x10c + len(program):]
            assert patched[0xc9c:] == original[0xc9c:]
            mutations = [{'sector_offset': '0x10c', 'bytes': len(program)}]
        else:
            for word_offset, before, after in TABLE_WORDS:
                assert struct.unpack_from('<I', original, word_offset)[0] == before
                struct.pack_into('<I', patched, word_offset, after)
            changed = {i for i, (a, b) in enumerate(zip(original, patched)) if a != b}
            assert changed <= {i for start, _, _ in TABLE_WORDS for i in range(start, start + 4)}
            mutations = [{'sector_offset': hex(start), 'bytes': 4, 'before': hex(before), 'after': hex(after)}
                         for start, before, after in TABLE_WORDS]
        sectors[label] = {'offset': hex(offset), 'mutations': mutations}
        for state, data in (('original', original), ('patched', bytes(patched))):
            path = OUT / f'native-ui-broker-{state}-sector-{offset:x}.bin'
            path.write_bytes(data)
            sectors[label][state] = {'path': relative(path), 'bytes': len(data), 'sha256': sha(data)}
            values[('table' if label == 'entry' else label) + '_' + state] = data
    manifest_path = OUT / 'native-ui-broker-patch-inputs-1.50.10.json'
    manifest = {
        'offline_only': True, 'frozen': False, 'hardware_actions': 0,
        'firmware': {'path': relative(image_path), 'bytes': len(nor), 'sha256': sha(nor)},
        'program': {'path': relative(program_path), 'elf': relative(elf_path), 'sha256': sha(program),
                    'elf_sha256': sha(elf_path.read_bytes()), 'bytes': len(program), 'entry': hex(ENTRY),
                    'start': hex(CODE_START), 'container_end_exclusive': hex(CODE_END),
                    'container_bytes': CODE_END - CODE_START, 'file_start': hex(CODE_FILE_START)},
        'scope': 'Only ntpcstatus/faclvgl/showlogo code containers and vapp/faclvgl/showlogo builtin entry words. Preserve original vapp, NTP daemon, all data/identity/config and every other NOR byte.',
        'disabled_commands': {'ntpcstatus': '-ENOSYS stub at 0x3804b109', 'showlogo': 'return-zero stub at 0x3804b111', 'faclvgl': 'return-zero stub at 0x3804b111 prevents a second broker launch'},
        'install_order': ['code', 'entry'], 'restore_order': ['entry', 'code'], 'sectors': sectors,
    }
    write_json(manifest_path, manifest)
    writer_source = ROOT / 'diagnostics/boot-nor-native-app-runner.cfg'
    writer = checked(writer_source, ORIGINAL_WRITER_SHA).decode('utf-8').replace('\r\n', '\n')
    generator_path = PERSIST / 'build_native_app_runner.py'
    checked(generator_path, ORIGINAL_GENERATOR_SHA)
    spec = importlib.util.spec_from_file_location('reviewed_native_app_generator', generator_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stages = module.STAGES.replace('bnai_', 'nubi_')
    onecall = checked(PERSIST / 'boot-nor-one-call.bin', ONECALL_SHA)
    assert len(onecall) == 168
    inputs = '# Generated offline only. New broker payloads; no hardware operations.\n'
    inputs += module.tcl_list('nubi_one_call_words', onecall)
    for label, data in values.items():
        inputs += module.tcl_list('nubi_' + label + '_words', data)
    inputs += stages
    input_path = ROOT / 'diagnostics/boot-nor-native-ui-broker-stage-inputs.cfg'
    input_path.write_text(inputs, encoding='utf-8')
    writer = writer.replace('bna_', 'nub_').replace('bnai_', 'nubi_')
    writer = writer.replace('boot-nor-native-app-stage-inputs.cfg', 'boot-nor-native-ui-broker-stage-inputs.cfg')
    writer = writer.replace('nub_run_native_app', 'nub_run_native_ui_broker')
    old_restore = '''            if {($code_before != $nubi_code_original_words && $code_before != $nubi_code_patched_words) ||
                ($table_before != $nubi_table_original_words && $table_before != $nubi_table_patched_words)} { error "Restore requires exact original/patched sector baselines" }'''
    new_restore = '''            if {!(($code_before == $nubi_code_original_words && $table_before == $nubi_table_original_words) ||
                ($code_before == $nubi_code_patched_words && $table_before == $nubi_table_patched_words))} { error "Restore requires both exact original or both exact broker sector baselines" }'''
    assert writer.count(old_restore) == 1
    writer = writer.replace(old_restore, new_restore)
    writer_path = ROOT / 'diagnostics/boot-nor-native-ui-broker-runner.cfg'
    writer_path.write_text(writer, encoding='utf-8')
    for mode, expected in SESSION_SHAS.items():
        source = checked(ROOT / f'diagnostics/mcu-native-counter-{mode}-session.cfg', expected).decode('utf-8').replace('\r\n', '\n')
        source = source.replace('native-counter', 'native-ui-broker')
        source = source.replace('bna_', 'nub_').replace('bnai_', 'nubi_')
        source = source.replace('boot-nor-native-app-runner.cfg', 'boot-nor-native-ui-broker-runner.cfg')
        source = source.replace('nub_run_native_app', 'nub_run_native_ui_broker')
        source = source.replace('native-app-', 'native-ui-broker-writer-')
        source = source.replace('native-read-%s', 'native-ui-broker-reader-%s')
        assert source.count(f'nub_run_native_ui_broker $boot_app_capture_dir {mode} {{boot_remove_fpb}}') == 1
        assert '($boot_app_entered && (!$nub_safe_to_resume || !$nub_app_complete))' in source
        assert 'automatic GLOBAL suppressed' in source
        (ROOT / f'diagnostics/mcu-native-ui-broker-{mode}-session.cfg').write_text(source, encoding='utf-8')
    report_path = PERSIST / 'native-ui-broker-writer-preparation.json'
    report = {
        'offline_only': True, 'hardware_actions': 0, 'frozen': False,
        'manifest': relative(manifest_path), 'manifest_sha256': sha(manifest_path.read_bytes()),
        'writer': relative(writer_path), 'writer_sha256': sha(writer_path.read_bytes()),
        'stage_inputs': relative(input_path), 'stage_inputs_sha256': sha(input_path.read_bytes()),
        'reused_caller_sha256': ONECALL_SHA,
        'reviewed_writer_source_sha256': ORIGINAL_WRITER_SHA,
        'changes_to_native_caller': 'None. Namespace/source filenames only; exact 168-byte payload and all context, watchdog, controller, protection, timeout and closure checks retained.',
        'changes_to_public_flow': 'Restore is strengthened to matched complete original/original or broker/broker baselines. Unknown, mixed and counter baselines are refused before native calls. Install still requires both exact original sectors.',
        'pending': 'Independent program/writer reviews and current-payload offline mocks must pass before explicit freezing. This preparation does not permit device execution.',
    }
    write_json(report_path, report)
    for name, expected in old_freeze['sha256'].items():
        checked(ROOT / name, expected)
    print(json.dumps({'program_bytes': len(program), 'manifest': relative(manifest_path),
                      'manifest_sha256': report['manifest_sha256'], 'writer_sha256': report['writer_sha256'],
                      'stage_inputs_sha256': report['stage_inputs_sha256'], 'frozen': False, 'hardware_actions': 0}, indent=2))


if __name__ == '__main__':
    prepare()
