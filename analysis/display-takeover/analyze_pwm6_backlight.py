"""Offline PWM6 and retained backlight-service review, exact 1.50.10 NOR only."""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'analysis' / 'pinout'))
import analyze_a7_peripherals as a

SOURCE_URL = ('https://github.com/openharmony/device_soc_bestechnic/blob/'
              '17f61a22388e6f2fbd8fe855b0ccb298b9a3bd45/'
              'bes2600/liteos_m/sdk/bsp/platform/hal/reg_pwm.h')

def main():
    data = a.FILE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
    bases = struct.unpack_from('<2I', data, a.address_to_offset(0x384bc44c))
    assert bases == (0x40083000, 0x40089000)
    ioctl_table = 0x38016a4e
    target = ioctl_table + 2 * struct.unpack_from('<H', data,
        a.address_to_offset(ioctl_table) + (0x2812 - 0x2801) * 2)[0]
    assert target == 0x38016c94
    assert struct.unpack_from('<I', data, a.address_to_offset(0x384ef84c) + 0x40)[0] == 0x383dde7c
    windows = [
        ('cold_pwm6_setup', 0x38007262, 0x54, 'Thumb'),
        ('hal_pwm_bank_selection', 0x383dfaa4, 0x94, 'ARM'),
        ('hal_pwm_enable_invert', 0x383dfbc4, 0x50, 'ARM'),
        ('hal_pwm_load_toggle_local2', 0x383dfd20, 0x60, 'ARM'),
        ('lcd_brightness_callback_registration', 0x38006c56, 0x4c, 'Thumb'),
        ('lcd_brightness_pwm6', 0x38040394, 0x9e, 'Thumb'),
        ('fbupper_ioctl_dispatch', 0x38016a24, 0x2a, 'Thumb'),
        ('fbupper_ioctl2812', 0x38016c94, 0xa, 'Thumb'),
        ('fbupper_callback_arg', 0x38016c6e, 0x8, 'Thumb'),
        ('fb_lower_brightness', 0x383dde7c, 0x44, 'ARM'),
        ('panel_brightness_ioctl', 0x38181afc, 0x3e, 'Thumb'),
        ('panel_brightness_current_update', 0x38181c38, 0x66, 'Thumb'),
        ('auto_brightness_timer_callback', 0x38181f98, 0xe4, 'Thumb'),
        ('auto_brightness_timer_registration', 0x38182f90, 0x6c, 'Thumb'),
        ('panel_apps_brightness_topics', 0x38184de4, 0x12c, 'Thumb'),
    ]
    report = {
        'scope': 'Offline existing NOR/code only; no hardware access or payload modifications.',
        'firmware': {'file': str(a.FILE.relative_to(ROOT)), 'sha256': digest,
                     'version': '1.50.10', 'A7_file_start': '0x8e0004', 'A7_VA_start': '0x38000000'},
        'primary_register_definition_source': SOURCE_URL,
        'bank_evidence': {'hal_pwm_enable_ARM': '0x383dfaa4',
                          'bank_table_VA': '0x384bc44c', 'bank_table_words': [hex(v) for v in bases],
                          'selection': 'channel 6 selects bank1, local channel2', 'PWM6_base': '0x40089000'},
        'read_only_register_candidates': [
            {'address': '0x40089004', 'field': 'EN_2', 'mask': '0x4'},
            {'address': '0x40089008', 'field': 'INV_2', 'mask': '0x4'},
            {'address': '0x40089010', 'field': 'PHASE23_2', 'mask': '0xffff'},
            {'address': '0x40089018', 'field': 'LOAD23_2', 'mask': '0xffff'},
            {'address': '0x40089020', 'field': 'TOGGLE23_2', 'mask': '0xffff'},
            {'address': '0x40089024', 'field': 'PHASEMOD_2', 'mask': '0x4'},
            {'address': '0x40089028', 'field': 'REG_PWM2_ST1', 'mask': '0xffff'},
            {'address': '0x4008902c', 'field': 'REG_PWM2_BR_EN', 'mask': '0x800000'},
            {'address': '0x4008902c', 'field': 'SUBCNT_DATA2', 'mask': '0xff'},
            {'address': '0x4008902c', 'field': 'TG_SUBCNT_D2_ST', 'mask': '0x7f0000'},
        ],
        'register_limits': 'Raw LOAD/TOGGLE are counter values, not percentages; BR_EN capability does not prove the mode is active. No live registers are read by this script.',
        'cold_boot': '38007262..380072b6 sets PWM6 config duty byte100 and enables PWM6 before LCD/fb initialization. Same code invokes LCD initialization and P2_6/PWM6 mux.',
        'lcd_config': {'VA': '0x384e9fe4', 'frequency_word': 1000, 'duty_byte_offset': 4,
                       'cold_duty_byte': 100, 'inverse_byte_offset': 5, 'clock_source_byte_offset': 6},
        'brightness_call_chain': [
            'timer callback38181f98 updates current brightness toward target',
            '38182036/38182070 ->38181c38 ->38181afc',
            '38181b2e..38181b32 ioctl([384ea600],0x2812,brightness)',
            'fbupper TBH command2812 ->38016c94 ->gdev384ef84c+40',
            'gdev+40 = ARM383dde7c ->LCDobject+0c',
            'LCDobject384f87c0+0c registered Thumb38040395 at38006c80..88',
            '38040394 stores brightness LCDobject+21, disables/enables PWM6; scales brightness0..255 to duty byte',
        ],
        'retained_background_service': {
            'panel_apps_entry': '0x38184b41',
            'normal_rcS': 'panel_apps is started before panel_fb_switch and vapp; replacing vapp retains panel_apps.',
            'auto_brightness_timer_registration': '38182f90..38182ffa registers callback38181f99 with name3843f344 auto brightness into38500768 and passes0x28 to timer helper381822fc.',
            'gradual_change_proof': '3818200a..3818203c compares target/current, computes a step, changes current up/down, then calls real brightness setter.',
            'runtime_read_candidates': {
                '0x384ea634': 'current brightness int32',
                '0x384ea638': 'callback proceeds only when this word equals1; exact higher-level mode semantics not claimed',
                '0x384ea63c': 'timer FD; -1 means not created in inspected registration path',
                '0x384ea5e0': 'target brightness int32',
                '0x384ea600': 'brightness ioctl FD',
                '0x384e9fe8': 'PWM config duty byte',
            },
            'limit': 'This proves a reachable retained software brightness interpolation service, not that it caused the observed breathing. Current mode, target changes and PWM waveform need separate live observations.',
        },
        'native_counter': 'Reviewed native counter paints fixed pixels initially and when count changes. It contains no brightness/PWM calls or periodic animation; white glyph variant only changes one immediate to0xffffffff.',
        'code_evidence': {name: a.disassemble(data, a.address_to_offset(va), size, mode)
                          for name, va, size, mode in windows},
    }
    out = ROOT / 'analysis' / 'display-takeover' / 'pwm6-backlight-review-1.50.10.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(out.relative_to(ROOT)), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                      'PWM6_base': '0x40089000', 'ioctl2812_target': hex(target), 'hardware_access': False}))

if __name__ == '__main__':
    main()
