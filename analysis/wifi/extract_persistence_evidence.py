"""Extract bounded code evidence for MiIO persistent field handling.

All addresses are backup file offsets. This script reads only the backup and
writes only analysis artifacts; it does not access the connected device.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'python-packages'))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

SOURCE = HERE.parents[1] / 'backups' / 'mi-panel-flash-16m-20261003.bin'
data = SOURCE.read_bytes()

def string_at(offset):
    return data[offset:offset+1024].split(b'\0', 1)[0].decode('utf-8')

encrypted_fields = []
for index in range(4):
    entry = 0x5fe080 + index * 8
    namespace, key = struct.unpack_from('<II', data, entry)
    encrypted_fields.append({'table_offset': hex(entry),
                             'namespace': string_at(namespace-0x2c000000),
                             'key': string_at(key-0x2c000000)})

ranges = {
    'payload_crc8': (0x236610, 0x236668),
    'read_checked_file': (0x258fcc, 0x259088),
    'write_checked_file': (0x259094, 0x25911c),
    'read_encrypted_value': (0x259128, 0x259348),
    'write_encrypted_value': (0x259368, 0x259420),
    'match_encrypted_field': (0x259d3c, 0x259db0),
    'string_getter': (0x259e28, 0x259e84),
    'remove_checked_file': (0x4d5454, 0x4d5496),
    'remove_field_and_encrypted_counterpart': (0x4d54a4, 0x4d5530),
}
safe_literals = {'/data/miot', '%s/%s.%s', 'e#', '%s%s',
                 'network', 'password', 'password_5g', 'ssid', 'ssid_5g',
                 'read_encrypted_value', 'arch_psm', 'vfs/fs_unlink.c'}
logs = {hex(offset): string_at(offset) for offset in
        [0x5fc29f, 0x5fc2e8, 0x5fc4d4, 0x5fc512, 0x5fc5aa, 0x5fc5df]}
safe_literals.update(logs.values())

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
md.detail = True
assembly = []
for name, (start, end) in ranges.items():
    assembly.append(f'; {name} at file offset 0x{start:x}')
    for insn in md.disasm(data[start:end], start):
        note = ''
        if insn.mnemonic.startswith('ldr') and len(insn.operands) > 1:
            operand = insn.operands[1]
            if operand.type == 3 and md.reg_name(operand.mem.base) == 'pc':
                pool = ((insn.address+4) & ~3) + operand.mem.disp
                if 0 <= pool <= len(data)-4:
                    pointer = struct.unpack_from('<I', data, pool)[0]
                    offset = pointer - 0x2c000000
                    if 0 <= offset < len(data):
                        try:
                            literal = string_at(offset)
                        except UnicodeError:
                            literal = ''
                        if literal in safe_literals:
                            note = f' ; static literal {literal!r}'
        assembly.append(f'{insn.address:08x}: {insn.mnemonic} {insn.op_str}{note}')
    assembly.append('')
(HERE / 'miio-persistence-code.txt').write_text('\n'.join(assembly), encoding='utf-8')

report = {
    'source_sha256': hashlib.sha256(data).hexdigest(),
    'evidence_kind': 'disassembly of original backed-up MCU image, not recovered source code',
    'addresses': 'all function and data addresses below are backup file offsets',
    'encrypted_field_table': encrypted_fields,
    'file_format': {
        'path_template': '/data/miot/{namespace}.{key}',
        'contents': 'payload followed by one CRC byte',
        'crc': {'polynomial': '0x31', 'initial_value': 0, 'reflect_input': False,
                'reflect_output': False, 'xor_output': 0},
        'reader_failure': 'CRC mismatch returns -1; encrypted getter may still try the other file',
        'source_ranges': ['0x236610..0x236668', '0x258fcc..0x259088', '0x259094..0x25911c']
    },
    'encrypted_storage': {
        'namespace_prefix': 'e#',
        'password_path': '/data/miot/e#network.password',
        'password_5g_path': '/data/miot/e#network.password_5g',
        'ssid_is_not_in_encrypted_field_table': True,
        'cipher_not_named_by_this_analysis': True,
        'legacy_plaintext_migration': 'reader checks both files; valid plaintext can be re-encrypted, checked encrypted file written, and plaintext removed',
        'disagreement_log': logs['0x5fc29f'],
        'source_ranges': ['0x259128..0x259348', '0x259368..0x259420', '0x259d3c..0x259db0']
    },
    'cleanup': {
        'generic_remove': 'for an encrypted-listed field, wrapper removes unprefixed and e# namespace files',
        'main_setter_empty_fields': {'password_remove_call': '0x4990fa', 'ssid_remove_call': '0x499110'},
        'five_ghz_setter_empty_fields': {'password_5g_remove_call': '0x25a78c', 'ssid_5g_remove_call': '0x25a7ae'},
        'explicit_paths_in_KEYCODE_CONFIG_setup_entry': {'password_unlink_call': '0x217c16', 'encrypted_password_unlink_call': '0x217c1c'},
        'bind_timeout_callback': {'name': 'mico_device_bind_timeout_cb',
                                  'ssid_unlink_call': '0x37215c',
                                  'device_id_property_remove_call': '0x372162',
                                  'log': 'miio bind timeout, try again(%d)'},
        'all_user_reset_flows_not_traced': True,
        'no_claim_of_actual_stale_values': True,
        'source_ranges': ['0x4d54a4..0x4d5530']
    },
    'diagnostic_log_templates': logs,
    'actual_ssid_password_security_ip_dhcp_values_recovered': False,
    'all_printable_wifi_field_hits_were_inside_known_image_regions': True,
    'json_candidates_were_printf_templates': ['0x5fc305', '0x5fc32a'],
    'credential_values_not_saved': True
}
(HERE / 'miio-persistence-evidence.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'source_sha256': report['source_sha256'], 'encrypted_field_table': encrypted_fields,
                  'report': str(HERE / 'miio-persistence-evidence.json'),
                  'code': str(HERE / 'miio-persistence-code.txt')}, indent=2))
