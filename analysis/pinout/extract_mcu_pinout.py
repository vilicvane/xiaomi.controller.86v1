"""Offline-only MCU pin mapping evidence; reads NOR backups, never device/logs.

All instruction addresses in reports are NOR file offsets. This intentionally
exports only selected code/pin configuration bytes, never identity data.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'analysis/wifi/python-packages'))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from capstone.arm import ARM_REG_PC

OUT = ROOT / 'analysis/pinout'
ref = json.loads((OUT / 'public-pinmux-reference.json').read_text())
functions = {v: k for k, v in ref['enums']['HAL_IOMUX_FUNCTION_T'].items()}
source_matrix = [[0] * 11 for _ in range(32)]
for p in ref['pins']:
    for f in p['alternate_functions']:
        source_matrix[p['pin_enum']][f['table_column']] = f['function_enum']
source_matrix = bytes(v for row in source_matrix for v in row)

VERSIONS = {
    '1.48.5': {
        'file': 'mi-panel-flash-16m-20261003.bin',
        'iomux': 0x56da88, 'setfunc': 0x56d8d0, 'voltage': 0x56da20,
        'uart0': 0x56dad8, 'uart_init': 0x571bdc, 'uart_cfg': 0x7a8ff4,
        'reset_cont': 0x5785f4, 'board': 0x578350,
        'board_entry_calls': [0x1a3174, 0x578616],
        'pa_init': 0x578228, 'pa_cfg': 0x7aaf7f, 'pa_setter': 0x54fbe0,
        'pa_ctrl': 0x54f3a0, 'gpio_dir': 0x573e90,
        'key_open': 0x5750bc, 'key_table': 0x77ff6c, 'key_wrapper': 0x1579ea,
        'key_veneer': 0x17b2ec,
        'i2c': [(0x56dc78, 0x7a8101), (0x56dc98, 0x7a80f9), (0x56dcb8, 0x7a80f1)],
        'i2c_desc': 0x7aa804, 'func_map': 0x7a7f8d,
        'uart2': 0x56db38, 'uart2_call': 0x54c73c,
        'diag_entry': 0x54c728,
    },
    '1.50.10': {
        'file': 'mi-panel-flash-16m-1.50.10-20261004.bin',
        'iomux': 0x5cb9c4, 'setfunc': 0x5cb80c, 'voltage': 0x5cb95c,
        'uart0': 0x5cba14, 'uart_init': 0x5cfb18, 'uart_cfg': 0x821f70,
        'reset_cont': 0x5d6538, 'board': 0x5d6294,
        'board_entry_calls': [0x1a3d4c, 0x5d655a],
        'pa_init': 0x5d616c, 'pa_cfg': 0x823efb, 'pa_setter': 0x5ad6d0,
        'pa_ctrl': None, 'gpio_dir': 0x5d1dcc,
        'key_open': 0x5d2ff8, 'key_table': 0x7f8b08, 'key_wrapper': 0x1579f2,
        'key_veneer': 0x17b74c,
        'i2c': [(0x5cbbb4, 0x82107d), (0x5cbbd4, 0x821075), (0x5cbbf4, 0x82106d)],
        'i2c_desc': 0x823780, 'func_map': 0x820f09,
        'uart2': 0x5cba74, 'uart2_call': 0x5aa22c,
        'diag_entry': 0x5aa218,
    },
}


def h(x):
    return hex(x)


def pin_record(data, off):
    p, f, v, pull = data[off:off + 4]
    return {'pin_enum': p, 'gpio': f'P{p // 8}_{p % 8}',
            'function_enum': f, 'function': functions.get(f, f'UNRESOLVED_{f}'),
            'voltage_domain_enum': v, 'voltage_domain': ['VIO', 'MEM', 'VBAT'][v],
            'pull_enum': pull, 'pull': ['none', 'up', 'down'][pull]}


def code_dump(data, ranges):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
    md.detail = True
    md.skipdata = True
    lines = ['Addresses below are NOR file offsets, not running PC addresses.',
             'Selected instructions only; literal pools can appear as bogus instructions.']
    for name, lo, hi in ranges:
        lines.append(f'\n{name}: {lo:#x}..{hi:#x}')
        for ins in md.disasm(data[lo:hi], lo):
            line = f'{ins.address:08x} {ins.mnemonic:10} {ins.op_str}'
            if ins.mnemonic in ('ldr', 'ldr.w') and len(ins.operands) > 1 and ins.operands[1].type == 3 and ins.operands[1].mem.base == ARM_REG_PC:
                pool = ((ins.address + 4) & ~3) + ins.operands[1].mem.disp
                word = struct.unpack_from('<I', data, pool)[0]
                line += f' ; literal@{pool:#x} = {word:#010x}'
            lines.append(line)
    return '\n'.join(lines) + '\n'


all_data = {}
reports = {}
for ver, a in VERSIONS.items():
    data = (ROOT / 'backups' / a['file']).read_bytes()
    assert len(data) == 0x1000000
    all_data[ver] = data
    uart_cfg = data[a['uart_cfg']:a['uart_cfg'] + 16]
    assert uart_cfg == bytes.fromhex('000003000102000000100e0000000000')
    pa = pin_record(data, a['pa_cfg'])
    assert [pa[k] for k in ['pin_enum', 'function_enum', 'voltage_domain_enum', 'pull_enum']] == [31, 1, 0, 0]
    iomux_table = data[a['func_map']:a['func_map'] + 32 * 11]
    assert iomux_table == source_matrix, f'Public enum/pin table mismatch: {ver}'
    i2cs = []
    for n, (routine, table) in enumerate(a['i2c']):
        i2cs.append({'controller': n, 'iomux_helper_offset': h(routine),
                     'table_offset': h(table),
                     'pins': [pin_record(data, table), pin_record(data, table + 4)],
                     'evidence_status': 'Compiled HAL helper calls hal_iomux_init(count=2); referenced by HAL descriptor. Normal board invocation not established.'})
    keys = []
    for n in range(3):
        off = a['key_table'] + 8 * n
        keys.append({'entry_offset': h(off), 'key_mask': struct.unpack_from('<H', data, off)[0],
                     'pin_config': pin_record(data, off + 2)})
    report = {
        'scope': 'Offline-only selected MCU/BES2003 pin mapping; no target reads, code execution, RAM or Flash writes.',
        'firmware_version': ver, 'backup_file': a['file'],
        'backup_sha256': hashlib.sha256(data).hexdigest(),
        'address_convention': 'Every code/data address named offset is a NOR file offset. MCU XIP aliases commonly add 0x0c000000 or 0x2c000000. GPIO labels are logical bank/bit, not package balls or board test pads.',
        'abi': {'hal_iomux_init_offset': h(a['iomux']), 'entry_size': 4,
                'fields_offsets': {'pin': 0, 'function': 1, 'voltage_domain': 2, 'pull': 3},
                'evidence': 'ldrb at offsets 0/1/2/3; postincrement pointer by 4.',
                'public_function_table_exactly_matches_all_32_by_11_bytes': True},
        'confirmed_startup_routes': {
            'UART0': {
                'pins': [{'gpio': 'P1_6', 'pin_enum': 14, 'signal': 'RX', 'function_enum': 89, 'mux_register_value': 1, 'pull': 'up'},
                         {'gpio': 'P1_7', 'pin_enum': 15, 'signal': 'TX', 'function_enum': 90, 'mux_register_value': 1, 'pull': 'none'}],
                'startup_chain_offsets': [h(0x150010), h(0x150056), h(a['reset_cont']), h(a['uart_init']), h(a['uart0'])],
                'board_init_offset': h(a['board']),
                'board_init_is_called_at_offsets': list(map(h, a['board_entry_calls'])),
                'configuration_offset': h(a['uart_cfg']),
                'serial': {'baud': struct.unpack_from('<I', uart_cfg, 8)[0], 'data_bits': 8, 'parity': 'none', 'stop_bits': 1, 'hardware_flow_control': False, 'dma_flags': 0},
                'limits': 'Proves startup configuration; no passive wire measurement and no physical test-pad trace yet. Later runtime changes not excluded.'},
            'PA_control_GPIO': {
                **pa, 'initial_direction': 'output', 'initial_level': 0,
                'board_init_offset': h(a['board']), 'gpio_init_offset': h(a['pa_init']),
                'pin_config_offset': h(a['pa_cfg']), 'set_dir_offset': h(a['gpio_dir']),
                'control_pin_setter_offset': h(a['pa_setter']),
                'role_evidence': 'Board init passes pin31 to the persistent PA-control pin selector; old PA-control function reads the same selector and toggles GPIO with open all PA / close all PA strings.',
                'limits': 'PA denotes firmware control path; amplifier part, physical trace and polarity beyond observed initialization are unverified.'},
        },
        'conditional_routes': {
            'GPIO_keys': {'hal_key_open_offset': h(a['key_open']),
                          'wrapper_offset': h(a['key_wrapper']), 'veneer_offset': h(a['key_veneer']),
                          'table_offset': h(a['key_table']), 'entries': keys,
                          'evidence_status': 'Wrapper calls hal_key_open; hal_key_open iterates three table entries and calls hal_iomux_init for nonzero key masks. The wrapper invocation and physical keys are not established as normal startup.'},
            'I2C': i2cs,
            'UART2_BLE_diagnostic': {'iomux_helper_offset': h(a['uart2']), 'caller_offset': h(a['uart2_call']),
                                     'pins': [{'gpio': 'P0_0', 'signal': 'RX', 'pull': 'up'}, {'gpio': 'P0_1', 'signal': 'TX', 'pull': 'none'}],
                                     'mux_register_value': 1,
                                     'evidence_status': 'Old call chain is ble_nosignal_start test mode, with UART2 opened. New mux helper remains byte-identical and has one direct caller. No normal board use proved.',
                                     'debug_overlap': 'Public guide also assigns P0_0/P0_1 to JTMS/SWDIO and JTCK/SWCK under debug mux; choosing UART2 here can change debug pin function.'},
        },
        'not_established': ['MCU normal SPI or SPILCD assignments', 'MCU normal SDMMC assignments', 'Physical GPIO-to-BES2600WM package ball and board-pad mapping', 'Runtime pin state after all services start'],
        'voltage_limit': 'VIO enum0 is a requested voltage domain, not 0 V or a proven 1.8/2.8/3.3 V level. Compiled normal-GPIO voltage setter is effectively a no-op; bank supply must be established separately.',
        'source_reference': 'public-pinmux-reference.json and reference/hal_uart.h; source is public OpenHarmony BEST2003 HAL, cross-version alignment confirmed by exact pin-function table match.',
    }
    reports[ver] = report
    (OUT / f'mcu-pinout-{ver}.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    ranges = [('MCU reset entry', 0x150010, 0x15005c),
              ('Reset continuation', a['reset_cont'], a['reset_cont'] + 0x1c),
              ('UART0 startup open', a['uart_init'], a['uart_init'] + 0x14),
              ('UART0 mux', a['uart0'], a['uart0'] + 0x30),
              ('Board init', a['board'], a['board'] + 0x6c),
              ('PA GPIO initialization', a['pa_init'], a['pa_init'] + 0x46),
              ('PA pin selector', a['pa_setter'], a['pa_setter'] + 6),
              ('IOMUX init', a['iomux'], a['iomux'] + 0x50),
              ('Voltage setter', a['voltage'], a['voltage'] + 0x1c),
              ('GPIO key table initialization', a['key_open'], a['key_open'] + 0xd4),
              ('I2C0 helper', a['i2c'][0][0], a['i2c'][0][0] + 0x16),
              ('I2C1 helper', a['i2c'][1][0], a['i2c'][1][0] + 0x16),
              ('I2C2 helper', a['i2c'][2][0], a['i2c'][2][0] + 0x16)]
    if a['pa_ctrl']:
        ranges.append(('Old PA control selected GPIO and safe literal references', 0x54f3c8, 0x54f48e))
    (OUT / f'mcu-code-evidence-{ver}.txt').write_text(code_dump(data, ranges), encoding='utf-8')

runtime_dir = ROOT / 'backups/pinout-registers-1.50.10'
if (runtime_dir / 'iomux-before.bin').exists() and (runtime_dir / 'iomux-after.bin').exists():
    before = (runtime_dir / 'iomux-before.bin').read_bytes()
    after = (runtime_dir / 'iomux-after.bin').read_bytes()
    assert len(before) == len(after) == 0x98
    pu, pd = struct.unpack_from('<II', before, 0x2c)
    def runtime_pin(n):
        mux = (struct.unpack_from('<I', before, 4 + 4 * (n // 8))[0] >> (4 * (n % 8))) & 15
        matches = [f['function'] for f in ref['pins'][n]['alternate_functions'] if f['mux_register_value'] == mux]
        if mux == 15:
            matches = ['HAL_IOMUX_FUNC_GPIO']
        return {'gpio': f'P{n // 8}_{n % 8}', 'pin_enum': n, 'mux_register_value': mux,
                'decoded_functions': matches, 'pullup': bool(pu & (1 << n)), 'pulldown': bool(pd & (1 << n))}
    actual = {str(n): runtime_pin(n) for n in [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 25, 26, 27, 31]}
    report = reports['1.50.10']
    report['runtime_cross_check'] = {
        'source': 'Root-agent-provided read-only IOMUX snapshots; this script reads saved files only.',
        'snapshot_files': ['backups/pinout-registers-1.50.10/iomux-before.bin', 'backups/pinout-registers-1.50.10/iomux-after.bin'],
        'base_address': '0x40086000', 'byte_length': len(before), 'two_reads_identical': before == after,
        'capture_limits': 'Running non-atomic register snapshots. Agreement is a stable observation, not a guarantee that every service always uses this mux.',
        'selected_pins': actual,
        'UART0_startup_mux_confirmed': actual['14']['decoded_functions'] == ['HAL_IOMUX_FUNC_UART0_RX'] and actual['15']['decoded_functions'] == ['HAL_IOMUX_FUNC_UART0_TX'],
        'PA_GPIO_mux_and_nopull_confirmed': actual['31']['mux_register_value'] == 15 and not actual['31']['pullup'] and not actual['31']['pulldown'],
        'GPIO_key_configs_mux_and_pull_confirmed': all(actual[str(n)]['mux_register_value'] == 15 and actual[str(n)]['pullup'] and not actual[str(n)]['pulldown'] for n in [25, 26, 27]),
        'SDMMC_runtime_pins': [actual[str(n)] for n in [11, 10, 12, 13, 8, 9]],
        'SDMMC_limits': 'Shared chip IOMUX registers show SDMMC CLK/CMD/DATA0..3 assignments; MCU versus A7 initializer/driver ownership and physical MMC wiring are not determined by this capture.',
        'compiled_I2C_helpers_active_on_their_selected_pins': False,
        'I2C_limit': 'P0_4/P0_5, P0_6/P0_7, P1_0/P1_1 are not currently in the functions specified by the three compiled MCU I2C helper tables. This does not prove the device lacks other I2C routes.',
    }
    report['not_established'] = ['MCU normal SPI or SPILCD assignments', 'MCU versus A7 ownership and initializer of the observed SDMMC mux', 'Physical GPIO-to-BES2600WM package ball and board-pad mapping', 'Current UART baud/format beyond startup configuration']
    (OUT / 'mcu-pinout-1.50.10.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

comparison = {
    'UART0_iomux_body_identical': all_data['1.48.5'][0x56dad8:0x56db0c] == all_data['1.50.10'][0x5cba14:0x5cba48],
    'UART0_config_identical': all_data['1.48.5'][0x7a8ff4:0x7a9004] == all_data['1.50.10'][0x821f70:0x821f80],
    'PA_GPIO_config_identical': all_data['1.48.5'][0x7aaf7f:0x7aaf83] == all_data['1.50.10'][0x823efb:0x823eff],
    'GPIO_key_table_identical': all_data['1.48.5'][0x77ff6c:0x77ff84] == all_data['1.50.10'][0x7f8b08:0x7f8b20],
    'I2C_three_pin_tables_identical': all_data['1.48.5'][0x7a80f1:0x7a8109] == all_data['1.50.10'][0x82106d:0x821085],
}
(OUT / 'mcu-pinout-version-comparison.json').write_text(json.dumps(comparison, indent=2) + '\n')
print(json.dumps({'created_reports': list(reports), 'comparison': comparison}, indent=2))
