"""Offline A7 peripheral analysis; reads a saved NOR image only.

No target communication and no raw log or credential output.
Use --xrefs for bounded MOVW/MOVT reconstruction and --disasm for code windows.
"""
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'analysis' / 'wifi' / 'python-packages'))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

FILE = ROOT / 'backups' / 'mi-panel-flash-16m-1.50.10-20261004.bin'
START = 0x8e0004
BASE = 0x38000000

def offset_to_address(offset):
    return BASE + offset - START

def address_to_offset(address):
    return (address & ~1) - BASE + START

def instruction_immediate(data, offset, mode):
    if mode == 'Thumb':
        a, b = struct.unpack_from('<HH', data, offset)
        kind = a & 0xfbf0
        if kind not in (0xf240, 0xf2c0):
            return None
        value = ((a & 15) << 12) | ((a & 0x400) << 1) | ((b & 0x7000) >> 4) | (b & 255)
        return ('movw' if kind == 0xf240 else 'movt', (b >> 8) & 15, value)
    word = struct.unpack_from('<I', data, offset)[0]
    kind = word & 0x0ff00000
    if kind not in (0x03000000, 0x03400000):
        return None
    return ('movw' if kind == 0x03000000 else 'movt', (word >> 12) & 15,
            (word & 0xfff) | ((word >> 4) & 0xf000))

def find_xrefs(data, end, targets):
    hits = []
    for mode, stride in [('Thumb', 2), ('ARM', 4)]:
        recent = {}
        for offset in range(START, end - 3, stride):
            decoded = instruction_immediate(data, offset, mode)
            if not decoded:
                continue
            kind, register, immediate = decoded
            if kind == 'movw':
                recent[register] = (offset, immediate)
                continue
            low = recent.get(register)
            if not low or offset - low[0] > 32:
                continue
            pointer = low[1] | (immediate << 16)
            if pointer in targets:
                hits.append({'mode': mode, 'movw_offset': hex(low[0]), 'movt_offset': hex(offset),
                             'register': register, 'pointer': hex(pointer), 'target': targets[pointer],
                             'limit': 'Pair reconstructed syntactically; validate nearby instructions for register clobbers.'})
    return hits

def disassemble(data, offset, size, mode):
    engine = Cs(CS_ARCH_ARM, (CS_MODE_THUMB if mode == 'Thumb' else CS_MODE_ARM) | CS_MODE_LITTLE_ENDIAN)
    engine.skipdata = True
    result = []
    for ins in engine.disasm(data[offset:offset+size], offset_to_address(offset)):
        result.append({'address': hex(ins.address), 'file_offset': hex(ins.address-BASE+START),
                       'bytes': bytes(ins.bytes).hex(), 'mnemonic': ins.mnemonic, 'operands': ins.op_str})
    return result

def find_direct_calls(data, end, targets, include_jumps=False):
    """Decode candidate direct branches, retaining only exact known destinations."""
    hits = []
    for offset in range(START, end - 3, 2):
        h1, h2 = struct.unpack_from('<HH', data, offset)
        if h1 & 0xf800 != 0xf000 or (h2 & 0xc000 != 0xc000 and not (include_jumps and h2 & 0xd000 == 0x9000)):
            continue
        s, j1, j2 = (h1 >> 10) & 1, (h2 >> 13) & 1, (h2 >> 11) & 1
        value = (s << 24) | ((1 ^ j1 ^ s) << 23) | ((1 ^ j2 ^ s) << 22) | ((h1 & 0x3ff) << 12) | ((h2 & 0x7ff) << 1)
        if s:
            value -= 1 << 25
        if h2 & 0x1000:
            destination = offset_to_address(offset) + 4 + value
        elif h2 & 1 == 0:
            destination = ((offset_to_address(offset) + 4) & ~3) + value
        else:
            continue
        if destination not in targets:
            continue
        ins = disassemble(data, offset, 4, 'Thumb')
        if len(ins) == 1 and ins[0]['mnemonic'] in (('bl', 'blx', 'b.w') if include_jumps else ('bl', 'blx')):
            hits.append({'mode': 'Thumb', 'target': targets[destination], 'target_address': hex(destination), **ins[0]})
    for offset in range(START, end - 3, 4):
        word = struct.unpack_from('<I', data, offset)[0]
        if word & (0x0e000000 if include_jumps else 0x0f000000) != (0x0a000000 if include_jumps else 0x0b000000):
            continue
        value = (word & 0xffffff) << 2
        if value & (1 << 25):
            value -= 1 << 26
        destination = offset_to_address(offset) + 8 + value
        if destination not in targets:
            continue
        ins = disassemble(data, offset, 4, 'ARM')
        if len(ins) == 1 and (ins[0]['mnemonic'].startswith('bl') or (include_jumps and ins[0]['mnemonic'].startswith('b'))):
            hits.append({'mode': 'ARM', 'target': targets[destination], 'target_address': hex(destination), **ins[0]})
    return hits

def build_report(data, image):
    payload_length = int.from_bytes(data[START-4:START], 'big')
    end = START + payload_length
    assert payload_length == 0x4f3fe0 and end == 0xdd3fe4
    def words(address, count):
        return [hex(v) for v in struct.unpack_from('<' + str(count) + 'I', data, address_to_offset(address))]
    touch_bus_words = words(0x384e13d8, 2)
    assert touch_bus_words == ['0xa0810', '0xb0811']
    sdmmc = json.loads((ROOT / 'analysis/pinout/a7-sdmmc-evidence.json').read_text(encoding='utf-8'))
    windows = [
        ('encoded_gpio_configuration_decoder', 0xcac050, 0x9c, 'ARM'),
        ('gpio_high_low_wrappers', 0xcabf9c, 0x40, 'ARM'),
        ('gpio_direction_and_output_hardware', 0xcb48f4, 0x100, 'ARM'),
        ('touch_gpio_init_and_reset', 0x8e61c8, 0x9c, 'Thumb'),
        ('touch_i2c_object_setup', 0x8e6270, 0x92, 'Thumb'),
        ('touch_i2c_getter_and_mux', 0x8e3ca4, 0x110, 'Thumb'),
        ('touch_irq_attach', 0x8e3edc, 0x68, 'Thumb'),
        ('touch_diagnostic_binding', 0x8e6b60, 0x44, 'Thumb'),
        ('lcd_reset_and_dsi_init', 0x922340, 0xe8, 'Thumb'),
        ('lcd_dimensions', 0x922830, 0x5c, 'Thumb'),
        ('lcd_backlight_pwm6_route', 0x8e7266, 0x54, 'Thumb'),
        ('pwm_enable_channel_and_duty_validation', 0xcbfaa8, 0x54, 'ARM'),
        ('touch_i2c_read_messages', 0x9009d4, 0xbc, 'Thumb'),
    ]
    evidence = [{'name': name, 'mode': mode, 'file_offset': hex(offset),
                 'mapped_address': hex(offset_to_address(offset)),
                 'instructions': disassemble(data, offset, size, mode)}
                for name, offset, size, mode in windows]
    registers = []
    for suffix in ['before', 'after']:
        path = ROOT / f'backups/pinout-registers-1.50.10/iomux-{suffix}.bin'
        if path.is_file():
            raw = path.read_bytes()
            assert len(raw) == 0x98
            registers.append({'file': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
                              'base_address': '0x40086000',
                              'mux_words': {hex(o): hex(struct.unpack_from('<I', raw, o)[0]) for o in (4, 8, 12, 16)}})
    confirmed = [
        {'peripheral': 'ST7797 LCD reset', 'pin': 'P2_7', 'pin_enum': 23,
         'encoded_config': '0x00014817', 'function_enum': 1, 'function': 'GPIO',
         'direction': 'output', 'pull': 'up', 'voltage_domain': 'VIO',
         'sequence': 'high 10 ms, low 20 ms, high 120 ms, then DSI initialization',
         'evidence': ['lcd_reset_and_dsi_init', 'encoded_gpio_configuration_decoder', 'gpio_high_low_wrappers'],
         'register_crosscheck': 'P2_7 hardware mux nibble F matches GPIO'},
        {'peripheral': 'LCD backlight PWM route', 'pin': 'P2_6', 'pin_enum': 22,
         'encoded_config': '0x00354816', 'function_enum': 53, 'function': 'PWM6',
         'pull': 'up', 'voltage_domain': 'VIO',
         'evidence': ['lcd_backlight_pwm6_route', 'encoded_gpio_configuration_decoder'],
         'pwm_call': {'channel': 6, 'config_address': '0x384e9fe4', 'initial_words': words(0x384e9fe4, 2),
                      'duty_byte': 100, 'frequency_field_candidate': 1000},
         'register_crosscheck': 'P2_6 hardware mux nibble0 maps PWM6 in the public HAL table',
         'limit': 'The same LCD initialization path configures and enables PWM channel6. A physical pad/connector and actual brightness waveform were not measured.'},
        {'peripheral': 'TLSC6x touch interrupt', 'pin': 'P0_6', 'pin_enum': 6,
         'encoded_config': '0x00010806', 'function': 'GPIO', 'direction': 'input', 'pull': 'up',
         'irq_attach': {'file_offset': '0x8e3f08', 'pin_argument': 6, 'enabled': True,
                        'encoded_irq_flags': '0x00010c06', 'edge': 'falling', 'handler': '0x38001375'},
         'evidence': ['touch_gpio_init_and_reset', 'touch_irq_attach', 'touch_diagnostic_binding'],
         'register_crosscheck': 'P0_6 hardware mux nibbleF and pullup match the saved runtime registers'},
        {'peripheral': 'TLSC6x touch reset', 'pin': 'P0_7', 'pin_enum': 7,
         'encoded_config': '0x00014807', 'function': 'GPIO', 'direction': 'output', 'pull': 'up',
         'sequence': 'low20ms then high20ms',
         'evidence': ['touch_gpio_init_and_reset', 'touch_diagnostic_binding'],
         'register_crosscheck': 'P0_7 hardware mux nibbleF and pullup match the saved runtime registers'},
        {'peripheral': 'TLSC6x touch I2C clock', 'pin': 'P2_0', 'pin_enum': 16,
         'encoded_config': '0x000a0810', 'function_enum': 10, 'function': 'I2C0_SCL', 'pull': 'up',
         'evidence': ['touch_i2c_object_setup', 'touch_i2c_getter_and_mux'],
         'register_crosscheck': 'P2_0 mux3 / pullup match'},
        {'peripheral': 'TLSC6x touch I2C data', 'pin': 'P2_1', 'pin_enum': 17,
         'encoded_config': '0x000b0811', 'function_enum': 11, 'function': 'I2C0_SDA', 'pull': 'up',
         'evidence': ['touch_i2c_object_setup', 'touch_i2c_getter_and_mux'],
         'register_crosscheck': 'P2_1 mux3 / pullup match'},
    ]
    report = {
        'image': str(image.resolve()), 'sha256': hashlib.sha256(data).hexdigest(),
        'firmware_version': '1.50.10', 'scope': 'Offline code/data analysis of an existing NOR backup and existing register captures; no device access',
        'A7_mapping': {'payload_offset': hex(START), 'mapped_base': hex(BASE), 'header_length_big_endian': hex(payload_length),
                       'payload_end_exclusive': hex(end), 'limit': 'Mixed ARM/Thumb code; stale bytes beyond this payload end are excluded.'},
        'encoded_pin_config_decoder': {'pin': 'low5bits', 'function': 'bits16..23', 'voltage_domain': 'bits25..26',
                                       'pull': 'bits11..13', 'gpio_direction': 'bits14..15 when function==GPIO',
                                       'HAL_map': 'four one-byte fields, pin/function/voltage/pull'},
        'confirmed_logical_routes': confirmed,
        'LCD': {'driver': 'ST7797', 'width': 320, 'height': 480,
                'interface': 'DSI code initialization and DCS command transfers',
                'physical_signal_pads': 'Dedicated DSI pads are expected; no physical lane/BGA/connector map established',
                'dimensions_evidence': 'lcd_dimensions'},
        'touch': {'driver_family': 'TLSC6x', 'exact_chip_model': 'not established',
                  'descriptor_address': '0x384e93c8', 'descriptor_initial_words': words(0x384e93c8, 11),
                  'I2C_controller': 0, 'I2C_bus_object': '0x384e13e8', 'I2C_mux_data': '0x384e13d8',
                  'I2C_config_words': touch_bus_words, 'transaction_address_field': '0x2e',
                  'transaction_frequency': 400000,
                  'transfer_address_evidence': 'touch_i2c_object_setup writes0x2e to object+0x58; touch_i2c_read_messages places that field in I2C-message addr. Report retains the raw transfer addr field; lower-layer wire-address encoding has not been fully verified, so the field is not labeled conclusively7bit.',
                  'unresolved': 'Descriptor leading word0x24 remains unnamed; it is not assumed to be the I2C address.'},
        'SDMMC': sdmmc,
        'saved_runtime_registers': registers,
        'code_evidence': evidence,
        'limits': ['Logical routes and saved runtime mux agreement are not physical trace continuity or package ball numbers.',
                   'VIO is a domain name; no actual GPIO voltage is inferred from its enum.',
                   'Exact touch IC suffix, DSI lane pads and LCD connector pin numbers remain unresolved.',
                   'PWM frequency field is a header-layout inference; the PWM6 pin/channel and LCD initialization call are directly observed in code.',
                   'No firmware execution, Flash/RAM modification, raw-log read or credential output occurred.'],
        'reproduce': 'python analysis/pinout/analyze_a7_peripherals.py --report --save analysis/pinout/a7-peripherals-1.50.10.json'
    }
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--file', type=Path, default=FILE)
    p.add_argument('--xrefs', action='store_true')
    p.add_argument('--report', action='store_true')
    p.add_argument('--disasm', type=lambda s: int(s, 0))
    p.add_argument('--size', type=lambda s: int(s, 0), default=0x200)
    p.add_argument('--mode', choices=['Thumb', 'ARM'], default='Thumb')
    p.add_argument('--save', type=Path)
    args = p.parse_args()
    data = args.file.read_bytes()
    payload_length = int.from_bytes(data[START-4:START], 'big')
    end = START + payload_length
    if not START < end <= len(data):
        raise ValueError('Invalid A7 payload length candidate')
    if args.report:
        output = build_report(data, args.file)
    elif args.disasm is not None:
        output = disassemble(data, args.disasm, args.size, args.mode)
    elif args.xrefs:
        safe_patterns = [b'st7797_lcdinitialize', b'src/lcd_st7797.c', b'/dev/utouch',
                         b'hal_iomux_set_function', b'hal_dsi_init', b'hal_sdmmc_open',
                         b'hal_gpio_pin_set_dir', b'hal_gpio_pin_set', b'hal_gpio_pin_clr']
        targets = {}
        for needle in safe_patterns:
            for match in re.finditer(re.escape(needle), data[START:end]):
                offset = START + match.start()
                targets[offset_to_address(offset)] = {'name': needle.decode(), 'file_offset': hex(offset)}
        output = {'image': str(args.file.resolve()), 'sha256': hashlib.sha256(data).hexdigest(),
                  'A7_start_offset': hex(START), 'mapped_base': hex(BASE),
                  'BE_payload_length_candidate': hex(payload_length), 'payload_end_exclusive': hex(end),
                  'targets': {hex(k):v for k,v in targets.items()}, 'xrefs': find_xrefs(data, end, targets)}
    else:
        p.error('Choose --xrefs, --disasm or --report')
    if args.save:
        args.save.write_text(json.dumps(output, indent=2), encoding='utf-8')
        print(json.dumps({'saved': str(args.save.resolve()), 'records': len(output.get('xrefs', [])) if isinstance(output, dict) else len(output)}))
    else:
        print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
