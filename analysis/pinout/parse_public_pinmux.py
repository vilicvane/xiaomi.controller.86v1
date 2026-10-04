"""Decode public BEST2003 header enums and mux choices; no device/firmware reads."""
import ast
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF = HERE / 'reference'

def uncomment(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)

symbols = {}
def expression(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.Name):
        return symbols[node.id]
    if isinstance(node, ast.BinOp):
        left, right = expression(node.left), expression(node.right)
        if isinstance(node.op, ast.LShift):
            return left << right
        if isinstance(node.op, ast.BitOr):
            return left | right
    raise ValueError('Unsupported constant expression')

enums = {}
for filename in ('hal_iomux_best2003.h', 'hal_iomux.h', 'hal_gpio.h', 'hal_uart.h'):
    text = uncomment((REF / filename).read_text(encoding='utf-8'))
    for name, body in re.findall(r'enum\s+(\w+)\s*\{(.*?)\}\s*;', text, re.S):
        if '#' in body:
            # Conditional controller-count enum is not a fixed chip-independent ABI.
            continue
        values, current = {}, -1
        for item in body.split(','):
            item = item.strip()
            if not item:
                continue
            if '=' in item:
                symbol, value = map(str.strip, item.split('=', 1))
                current = expression(ast.parse(value, mode='eval').body)
            else:
                symbol, current = item, current + 1
            values[symbol] = current
            symbols[symbol] = current
        enums[name] = values

source = uncomment((REF / 'hal_iomux_best2003.c').read_text(encoding='utf-8'))
column_body = re.search(r'index_to_func_val\[[^]]+\]\s*=\s*\{(.*?)\}', source, re.S)[1]
mux_values = [int(value.strip(), 0) for value in column_body.split(',') if value.strip()]
table_body = re.search(r'pin_func_map\[[^=]+?=\s*\{(.*?)\n\};', source, re.S)[1]
rows = [re.findall(r'HAL_IOMUX_FUNC_\w+', row) for row in re.findall(r'\{([^{}]+)\}', table_body)]
assert len(rows) == 32 and all(len(row) == 11 for row in rows)
assert mux_values == [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11]

pins = []
function_to_pins = {}
for index, row in enumerate(rows):
    pin = f'P{index // 8}_{index % 8}'
    options = []
    for column, function in enumerate(row):
        if function == 'HAL_IOMUX_FUNC_NONE':
            continue
        item = {'function': function, 'function_enum': symbols[function],
                'mux_register_value': mux_values[column], 'table_column': column}
        options.append(item)
        function_to_pins.setdefault(function, []).append({'pin': pin, 'pin_enum': index,
                                                          'mux_register_value': mux_values[column]})
    pins.append({'pin': pin, 'pin_enum': index, 'gpio_mux_register_value': 15,
                 'mux_register_address': hex(0x40086004 + (index // 8) * 4),
                 'mux_nibble_shift': (index % 8) * 4, 'alternate_functions': options})

routes = {
    'UART0_RX_TX': [('P1_6', 'P1_7')],
    'UART1_RX_TX': [('P0_2', 'P0_3'), ('P3_2', 'P0_3'), ('P1_0', 'P1_1'), ('P2_0', 'P2_1'), ('P3_0', 'P3_1'), ('P3_2', 'P3_3')],
    'UART2_RX_TX': [('P0_0', 'P0_1'), ('P1_2', 'P1_3'), ('P1_4', 'P1_5'), ('P2_2', 'P2_3'), ('P3_6', 'P3_7')],
    'UART3_RX_TX': [('P0_4', 'P0_5'), ('P0_6', 'P0_7'), ('P2_4', 'P2_5'), ('P2_6', 'P2_7'), ('P3_4', 'P3_5')],
    'I2C0_SCL_SDA': [('P0_0', 'P0_1'), ('P0_4', 'P0_5'), ('P1_6', 'P1_7'), ('P2_0', 'P2_1'), ('P2_6', 'P2_7'), ('P3_4', 'P3_5')],
    'I2C1_SCL_SDA': [('P0_2', 'P0_3'), ('P0_6', 'P0_7'), ('P1_4', 'P1_5'), ('P2_2', 'P2_3'), ('P3_0', 'P3_1')],
    'I2C2_SCL_SDA': [('P1_0', 'P1_1'), ('P1_2', 'P1_3'), ('P2_4', 'P2_5'), ('P3_2', 'P3_3'), ('P3_6', 'P3_7')],
}

manifest = json.loads((REF / 'source-manifest.json').read_text(encoding='utf-8'))
for local_name, remote_path in [('bsp_Makefile', 'Makefile'), ('bsp_config_common.mk', 'config/common.mk'),
                                ('hal_i2c.h', 'platform/hal/hal_i2c.h'),
                                ('hal_uart.h', 'platform/hal/hal_uart.h'),
                                ('best2003_cmsis.h', 'platform/cmsis/inc/best2003.h')]:
    path = REF / local_name
    manifest.append({'local': str(path.resolve()), 'bytes': path.stat().st_size,
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'source': 'https://raw.githubusercontent.com/openharmony/device_soc_bestechnic/master/bes2600/liteos_m/sdk/bsp/' + remote_path})

report = {
    'source_kind': 'Public first-party OpenHarmony BEST2003 HAL source and official evaluation-board documentation',
    'source_repository': 'openharmony/device_soc_bestechnic',
    'source_branch': 'master',
    'source_tree_sha': '17f61a22388e6f2fbd8fe855b0ccb298b9a3bd45',
    'enums': enums,
    'HAL_IOMUX_PIN_FUNCTION_MAP': {
        'source_fields': ['pin', 'function', 'volt', 'pull_sel'],
        'source_types': ['enum HAL_IOMUX_PIN_T', 'enum HAL_IOMUX_FUNCTION_T', 'enum HAL_IOMUX_PIN_VOLTAGE_DOMAINS_T', 'enum HAL_IOMUX_PIN_PULL_SELECT_T'],
        'observed_old_firmware_1_48_5': {'size_bytes': 4, 'offsets': {'pin': 0, 'function': 1, 'volt': 2, 'pull_sel': 3},
                                      'field_storage': 'unsigned one-byte enum containers',
                                      'evidence': 'Peer agent static disassembly: hal_iomux_init loads four fields using LDRB and advances entry by 4; no hardware read'},
        'public_build_flag': 'BSP Makefile line 447 enables -fshort-enums specifically for TOOLCHAIN=armclang',
        'normal_int_enum_abi_variant': {'size_bytes': 16, 'offsets': {'pin': 0, 'function': 4, 'volt': 8, 'pull_sel': 12}},
        'layout_limit': 'Header uses four enum fields without a packed attribute. Determine enum ABI from the specific binary/toolchain; do not universally assume either stride.'
    },
    'gpio_pin_number_rule': 'P<bank>_<bit> = bank*8+bit, bank 0..3 and bit 0..7; LED1=32, LED2=33 are PMU LED pins',
    'function_enum_vs_hardware_mux': {
        'GPIO_function_enum': 1, 'GPIO_mux_register_value': 15,
        'table_columns_to_mux_values': mux_values,
        'additional_register_modes_not_generically_described_by_table': {'2': 'UART CTS/RTS', '12': 'BTDM', '13': 'WiFi FEM', '14': 'test port'},
        'warning': 'Do not use function enum as the 4-bit hardware mux selector; NONE entries are not a recommended function to program.'
    },
    'pins': pins,
    'function_to_pins': function_to_pins,
    'helper_pair_routes': routes,
    'sdmmc_helper_route': {'CLK': 'P1_3', 'CMD': 'P1_2', 'DATA0': 'P1_4', 'DATA1': 'P1_5', 'DATA2': 'P1_0', 'DATA3': 'P1_1'},
    'display_helper_route': {'DSI_TE': 'P2_1', 'scope': 'Generic helper implementation, not proof of panel wiring; other TE candidates exist in the table'},
    'special_cases': [
        'P1_6/P1_7 with I2C0 SCL/SDA take the analog-I2C slave path: GPIO mux 15 plus REG_050 control, instead of only the generic table selector.',
        'P0_2/P0_3 SPDIF and P2_0/P2_1 clock-request selections have dedicated handling.',
        'hal_iomux_get_function in this public revision is a stub returning HAL_IOMUX_FUNC_NONE.',
        'hal_iomux_set_io_voltage_domains does not change ordinary GPIO supplies in this public revision; VIO/MEM/VBAT are logical rail names, not literal voltages.',
        'Compile-time IOMUX_INDEX macros select helper variants. Their SDK defaults are not necessarily the panel build settings.'
    ],
    'register_reference': {'IOMUX_BASE': '0x40086000', 'GPIO_BASE': '0x40081000', 'mux_register_formula': 'IOMUX_BASE + 4 + 4*(pin//8); shift=4*(pin%8)',
                           'pullup_register': '0x4008602c', 'pulldown_register': '0x40086030',
                           'UART0': '0x4000b000', 'UART1': '0x4000c000', 'UART2': '0x4000d000', 'UART3': '0x40016000',
                           'I2C0': '0x40005000', 'I2C1': '0x40006000', 'I2C2': '0x40015000',
                           'SPI0': '0x40007000', 'SPILCD_SPI1': '0x40008000', 'SDMMC': '0x40110000', 'LCDC': '0x58100000'},
    'interrupt_reference': {'source': 'best2003_cmsis.h enum IRQn', 'SDMMC': 4,
                            'I2C0': 21, 'I2C1': 22, 'SPI0': 23, 'SPILCD': 24, 'I2C2': 25,
                            'UART3': 26, 'UART0': 27, 'UART1': 28, 'UART2': 29, 'AON_GPIO': 35},
    'uart_configuration_reference': {
        'source_fields': ['parity', 'stop', 'data', 'flow', 'rx_level', 'tx_level', 'baud', 'dma_rx:1', 'dma_tx:1', 'dma_rx_stop_on_err:1'],
        'short_enum_abi_candidate_offsets': {'parity': 0, 'stop': 1, 'data': 2, 'flow': 3,
                                             'rx_level': 4, 'tx_level': 5, 'padding': [6, 7],
                                             'baud': 8, 'dma_bitfield_storage_candidate': 12},
        'old_config_peer_candidate': {'firmware': '1.48.5', 'address': '0x7a8ff4', 'baud': 921600,
                                      'data_bits': 8, 'stop_bits': 1, 'parity': 'none', 'flow_control': 'none',
                                      'rx_fifo_trigger': '1/4', 'tx_fifo_trigger': '1/2', 'dma_flags': 'all zero'},
        'limit': 'The peer supplied a static 16-byte configuration; enum and baud decoding matches the public header with short enums. Confirm the bitfield ABI against binary loads; not proof of physical UART wiring.'
    },
    'i2c_internal_descriptor_limit': 'Public complete OpenHarmony master tree has hal_i2c.h but no hal_i2c.c implementation. Base addresses and IRQ numbers can help identify a binary descriptor; its full layout and fourth word are not confirmed from source.',
    'old_firmware_code_offsets_from_peer_static_analysis': {'hal_iomux_set_function': '0x56d8d0', 'hal_iomux_init': '0x56da88',
                                                           'hal_gpio_pin_set_dir': '0x573e90', 'hal_gpio_pin_set': '0x573df0', 'hal_gpio_pin_clr': '0x573e40', 'hal_gpio_pin_get_val': '0x573efc'},
    'package_and_debug_reference': {
        'official_board_guide': 'https://www.fortune-co.com/Public/Uploads/ueditor/upload/file/20250801/1754019693187058.pdf',
        'guide_pages_one_based': [9, 10],
        'P0_0': 'JTMS/SWDIO in Function 7 column of official guide',
        'P0_1': 'JTCK/SWCK in Function 7 column of official guide',
        'guide_function_column_is_not_HAL_function_enum': True,
        'evaluation_board_J11': {'pin18': 'IO00/SWIO', 'pin20': 'IO01/SWCLK'},
        'module_schematic': 'https://github.com/openharmony/device_board_fnlink/blob/master/doc/V200Z-R-EVB_SCH_V3.0.pdf',
        'module_J1_pin_examples': {'63': 'GPIO_00', '64': 'GPIO_01', '73': 'GPIO_10', '46': 'GPIO_13', '29': 'GPIO_14'},
        'module_pin_scope': '85-pad BES2600 Module, not the bare chip BGA balls or Xiaomi board connectors',
        'official_brief_datasheet': 'https://www.bestechnic.com/en/Uploads/keditor/file/20260512/20260512152851_45585.pdf',
        'brief_datasheet_scope': 'Family brief lists 169-pin BGA but lacks a ball-to-GPIO map; not a verified mapping for this panel package',
        'bare_chip_ball_to_gpio_map_found': False
    },
    'sources': manifest,
    'limits': ['Generic chip multiplexing choices do not establish Xiaomi 86v1 wiring or which functions are active.',
               'The target is now 1.50.10, while the peer static pin-array analysis uses the existing 1.48.5 NOR backup; current assignments were not read from hardware.',
               'Public OpenHarmony HAL revision may differ from the firmware ABI/function ordering. Validate decoded arrays against call-site semantics and the binary function table.',
               'No target access, flash/RAM modification, raw-log reads, or credential output occurred in this task.']
}
(HERE / 'public-pinmux-reference.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'output': str((HERE / 'public-pinmux-reference.json').resolve()), 'pins': len(pins),
                  'functions_in_enum': len(enums['HAL_IOMUX_FUNCTION_T']), 'matrix_shape': [len(rows), len(mux_values)],
                  'old_binary_map_size': 4, 'bare_package_ball_map_found': False}))
