"""Bounded offline original screen-idle policy analysis from exact 1.50.10 NOR."""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'analysis' / 'pinout'))
import analyze_a7_peripherals as a

def main():
    data = a.FILE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
    defaults = struct.unpack_from('<4I', data, a.address_to_offset(0x384ea610))
    assert defaults == (0xffffffff, 60, 1, 0)
    for va, expected in [(0x38440190, b'auto-screen-off'), (0x384401b8, b'screen-off-time')]:
        off = a.address_to_offset(va)
        assert data[off:off+len(expected)+1] == expected + b'\0'
    windows = [
        ('panel_apps_property_registration', 0x38184be4, 0xa8),
        ('auto_screen_off_setter', 0x38182738, 0x88),
        ('auto_screen_off_getter', 0x3817f2a4, 0x8c),
        ('screen_off_time_setter', 0x381829f4, 0xde),
        ('screen_off_time_getter', 0x3817f334, 0x82),
        ('timer_milliseconds_to_seconds_nanoseconds', 0x381822fc, 0x4c),
        ('screen_turn_off', 0x38181ca8, 0x86),
        ('screen_turn_on', 0x381827c8, 0x82),
        ('screen_timer_stop', 0x38181a24, 0xd0),
        ('screen_timer_callback', 0x38181d34, 0x1cc),
        ('screen_timer_start_and_restart', 0x38182460, 0x2ce),
        ('screen_policy_control_topic', 0x38182854, 0x130),
        ('panel_apps_touch_activity', 0x38182ad8, 0x24c),
        ('panel_apps_bind_state', 0x38184dd0, 0x14),
        ('panel_apps_unbound_flag', 0x38184f2c, 0x26),
    ]
    report = {
        'scope': 'Offline exact 1.50.10 backup only; no target communications or payload edits.',
        'firmware_file': str(a.FILE.relative_to(ROOT)), 'firmware_sha256': digest,
        'native_counter': {'own_idle_or_screen_off_logic': False,
                           'behavior': 'Creates framebuffer/input FDs and fixed canvas, polls touch and sleeps; no timeout property setters, screen_onoff writes or brightness/PWM calls.',
                           'preserved_service': 'Original rcS still starts panel_apps before vapp; registry patch replaces vapp entry only.'},
        'original_policy_owner': 'Native panel_apps, not solely the original vapp JS loop.',
        'properties': [
            {'name': 'auto-screen-off', 'string_VA': '0x38440190', 'registration': '0x38184be4..0x38184c18',
             'service_id': 16, 'property_id': 3, 'set_callback_Thumb': '0x38182739',
             'get_callback_Thumb': '0x3817f2a5', 'state_address': '0x384ea618',
             'set_semantics': 'Require property record type1, value at+8 >=0; write boolean(value!=0). Zero stores disabled and returns without directly calling timer stop/close. Nonzero invokes screen timer start/restart unconditionally. The helper creates an absent timer; its existing-timer restart path rearms only while screen-state384ea638 equals1.'},
            {'name': 'screen-off-time', 'string_VA': '0x384401b8', 'registration': '0x38184c54..0x38184c88',
             'service_id': 17, 'property_id': 12, 'set_callback_Thumb': '0x381829f5',
             'get_callback_Thumb': '0x3817f335', 'state_address': '0x384ea614',
             'set_semantics': 'Require type2 and integer value at+8 >0. Save period; timer already present and screen on leads to rearming. Ordinary enabled path multiplies seconds by1000 for timer helper.'},
        ],
        'period_unit_proof': 'Screen-off-time setter38182aaa..38182ab4 multiplies the period by1000 before timer helper381822fc. Helper38182316..3818233e computes milliseconds/1000 for seconds and milliseconds%1000*1000000 for nanoseconds. Therefore property600 denotes600seconds in the ordinary enabled nonoverride path; flags can select a separate60second or300second policy.',
        'state': {'0x384ea610': 'screen-off timer FD, -1 when absent/closed',
                  '0x384ea614': 'configured screen-off period in seconds',
                  '0x384ea618': 'normalized auto-screen-off enable flag',
                  '0x384ea61c': 'policy flags: bit0/bit1/bit2 influence timeout/override paths; not blanket always-off rule',
                  '0x384ea638': 'screen on/off state;1 on,0 off. Previously considered an unspecified auto-brightness callback gate; exact screen-state semantics now closed.',
                  '0x384ea63c': 'different timer FD for auto-brightness smoothing, not screen-off timer'},
        'static_defaults': {'screen_timer_FD': -1, 'period_seconds': defaults[1],
                            'auto_screen_off_enable': defaults[2], 'flags': defaults[3]},
        'parent_supplied_read_only_observation': {
            'description': 'Parent read current device state in this turn; this script does not read live hardware.',
            'screen_timer_FD': -1, 'period_seconds': 600, 'auto_screen_off_enable': 0, 'flags': 2,
            'screen_state': 1, 'current_brightness': 255, 'PWM6_duty_byte': 100,
            'interpretation': 'Original native idle-policy state currently says automatic screen-off disabled and no screen-off timer allocated. This agrees with user disabled setting. Period600/enable0 differ from source defaults60/1, so nondefault values were supplied after startup.'},
        'off_call_chain': 'Timer callback38181d34 ->38181eb6 screen_turn_off38181ca8 ->brightness setter38181afc(0) ->ioctl0x2812 ->LCD/PWM6 zero; successful off stores0 into384ea638 and stops timer.',
        'on_call_chain': 'screen_turn_on381827c8 restores saved brightness via38181afc(-1), stores1 into384ea638, then starts/restarts idle timer.',
        'activity_path': 'panel_apps native touch callback38182ad8 reads32B event and can wake screen or restart idle timer. Normal activity handling is retained; counter does not implement equivalent settings itself.',
        'provenance_limit': 'The exact persistent file/database-to-property sender chain is not closed in this bounded audit. Runtime0/600 plus native setter bindings prove policy state and compatibility with previous settings, but do not identify which startup component loaded it or prove a particular settings file was read. No claim is made that all original vapp idle/screen-saver presentation remains.',
        'conclusion': 'Both facts matter: native counter contains no independent screen-off timer, and the preserved original native service currently has auto-screen-off disabled. Current observations support the retained disabled policy; omission of counter-local timeout alone is not the complete original-system explanation.',
        'code_evidence': {name: a.disassemble(data, a.address_to_offset(va), size, 'Thumb')
                          for name, va, size in windows},
    }
    out = ROOT / 'analysis' / 'display-takeover' / 'screen-idle-policy-review-1.50.10.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(out.relative_to(ROOT)), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                      'offline_only': True, 'default_period': defaults[1], 'default_enable': defaults[2]}))

if __name__ == '__main__':
    main()
