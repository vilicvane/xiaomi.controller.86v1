"""Read-only, current-image-only touchscreen interface evidence extractor."""
import hashlib
import json
import struct
from pathlib import Path
import analyze_a7_peripherals as a

ROOT = Path(__file__).resolve().parents[2]
data = a.FILE.read_bytes()
end = a.START + int.from_bytes(data[a.START-4:a.START], 'big')
assert end == 0xdd3fe4

def words(address, count):
    return [hex(x) for x in struct.unpack_from('<' + str(count) + 'I', data, a.address_to_offset(address))]

def safe_path(address):
    offset = a.address_to_offset(address)
    value = data[offset:data.index(0, offset)].decode('ascii')
    assert value in ('dev/input0', '/dev/input0', '/dev/utouch')
    return value

windows = [
    ('physical_registration', 0x38006540, 0x42),
    ('virtual_utouch_registration', 0x38007d88, 0x2a),
    ('touch_register_upper_half', 0x383ae02c, 0x76),
    ('virtual_utouch_write_callback', 0x38009800, 0x2e),
    ('touch_event_fanout', 0x380144f0, 0x8c),
    ('touch_open_per_subscriber_buffer', 0x38019360, 0xbe),
    ('touch_read_blocking_and_nonblocking', 0x38015024, 0xa8),
    ('touch_poll', 0x38013d8c, 0x80),
    ('gui_open_default_or_named_touch', 0x383c9728, 0x76),
    ('gui_read_single_touch_sample', 0x3806ab74, 0xb4),
    ('physical_worker_coordinates', 0x38021234, 0xbe),
    ('physical_worker_publish', 0x380213a8, 0x0a),
    ('irq_attach', 0x38003ed8, 0x68),
    ('irq_callback_setter', 0x38003f48, 0x20),
    ('irq_callback_dispatch', 0x38001374, 0x3c),
]
evidence = []
for name, address, size in windows:
    offset = a.address_to_offset(address)
    assert a.START <= offset < offset+size <= end
    evidence.append({'name': name, 'address': hex(address), 'file_offset': hex(offset),
                     'mode': 'Thumb', 'instructions': a.disassemble(data, offset, size, 'Thumb')})

fops = words(0x384b621c, 10)
assert fops == ['0x38019361', '0x38017375', '0x38015025', '0x380120cd', '0x0',
                '0x38013d29', '0x0', '0x0', '0x38013d8d', '0x0']

report = {
    'firmware_version': '1.50.10',
    'image': str(a.FILE.resolve()), 'image_sha256': hashlib.sha256(data).hexdigest(),
    'scope': 'Only saved NOR bytes. No hardware access, target execution, raw logs, or credentials.',
    'mapping': {'file_start': hex(a.START), 'virtual_base': hex(a.BASE),
                'length': '0x4f3fe0', 'file_end_exclusive': hex(end)},
    'result': 'Physical input0 and virtual utouch are distinct publishers sharing one upper-half character driver. A custom application should read physical /dev/input0 directly unless an upstream utouch writer is deliberately retained.',
    'registration': {
        'upper_half_register': '0x383ae02c',
        'physical': {'call': '0x3800657a', 'path_literal': safe_path(0x383ea6e4),
                     'path_literal_address': '0x383ea6e4',
                     'lower_half_address': words(0x38006840, 1)[0],
                     'lower_half_max_points_set_to': 1,
                     'driver_base': '0x384f5068',
                     'upper_handle_saved_at': 'driver_base + 0x48'},
        'virtual': {'call': '0x38007da8', 'path': safe_path(0x383ea9b4),
                    'allocated_lower_half_bytes': 16, 'max_points': 1,
                    'write_callback_thumb': '0x38009801',
                    'write_callback_behavior': 'Loads lower+4 upper handle; forwards buffer through touch_event; returns input buflen.'},
        'vfs_inode_mode': '0666 (0x1b6)',
        'fops_table': '0x384b621c', 'fops_words': fops,
        'callbacks': {'open': '0x38019361', 'close': '0x38017375', 'read': '0x38015025',
                      'write': '0x380120cd', 'ioctl': '0x38013d29', 'poll': '0x38013d8d'},
        'fanout': {'touch_event': '0x380144f0', 'sample_bytes_formula': '0x20 + (npoints-1)*0x18',
                   'per_open_buffer': True, 'buffered_sample_count': 8,
                   'evidence': 'register sets upper byte0=8; open allocates subscriber and its sample ring; touch_event iterates subscriber list and copies to each ring.'}},
    'event_abi': {
        'endianness': 'little', 'one_point_bytes': 32, 'point_stride_bytes': 24,
        'confirmed_by_current_gui': {'flags_byte_offset': 9,
                                     'x_signed_16_offset': 10, 'y_signed_16_offset': 12,
                                     'down_or_move_mask': '0x03', 'up_mask': '0x04'},
        'confirmed_by_current_publisher': {'npoints_int_offset': 0,
                                          'point0_id_byte_offset': 8,
                                          'timestamp_64_offset': 24},
        'public_header_correspondence': 'NuttX touch_sample_s/touch_point_s matches the observed ARM ABI. Remaining point fields are not required for minimal input and were not independently assigned.',
        'coordinates': 'GUI uses signed x/y directly and clamps to current display resolution; custom UI rotation/scaling must be checked against actual orientation.'},
    'hardware_dependencies': {
        'family': 'TLSC6x; exact suffix not established',
        'descriptor': '0x384e93c8', 'descriptor_words': words(0x384e93c8, 11),
        'i2c_bus_object': '0x384e13e8', 'controller': 0,
        'scl': 'P2_0', 'sda': 'P2_1', 'frequency_field_hz': 400000,
        'transfer_addr_field': '0x2e; lower-layer wire encoding not reverified here',
        'reset': 'P0_7; low20ms then high20ms',
        'irq': 'P0_6; input pull-up, falling edge',
        'irq_attach_address': '0x38003ed8', 'gpio_irq_configure': '0x383cbfd8',
        'irq_dispatch_thumb': '0x38001375', 'dynamic_irq_callback_slot': '0x384f9120',
        'physical_irq_callback_assigned': '0x380208d1',
        'physical_worker_entry_thumb': '0x380211b9',
        'physical_publish_call': '0x380213ae',
        'detail_source': 'analysis/pinout/a7-peripherals-1.50.10.json'},
    'minimal_application_route': [
        'Run an A7 task in the existing OS and keep the initialized physical touch driver/worker active.',
        'Open /dev/input0 read-only with nonblocking mode and read 32-byte one-point samples; alternatively use poll before blocking read.',
        'Parse flags at+9 and signed x/y at+10/+12; retain prior position on TOUCH_UP when position-valid is absent.',
        'Use firmware flag symbols/ABI rather than Linux numeric O_RDONLY constants. Existing opener calls 0x3802c900 with internal flags0x41.',
        'The lowest verified file reader is 0x3802954c(file*,buf,len). Existing GUI obtains file* from fd via 0x38025678 before reading.',
        'Do not require the original GUI or its virtual utouch feeder for direct physical input0. Keep I2C, IRQ, physical worker and OS synchronization intact.',
    ],
    'limits': [
        'No target ABI execution or live sample observation occurred.',
        'Physical registration literal omits leading slash; GUI default opener explicitly uses /dev/input0. VFS normalization is inferred from these matching paths.',
        'The upstream writer feeding virtual utouch was not identified. Virtual utouch is not proven to continue physical events if original userspace stops.',
        'Buffer overflow behavior and multitouch details were not fully audited; maxpoint is1 in the registration.',
        'Do not reset/re-register the initialized driver for the minimal application experiment.',
    ],
    'primary_reference': 'https://raw.githubusercontent.com/apache/nuttx/master/include/nuttx/input/touchscreen.h',
    'evidence': evidence,
}
out = ROOT / 'analysis/pinout/a7-touch-input-route-1.50.10.json'
out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'report': str(out.resolve()), 'physical_path': '/dev/input0',
                  'virtual_path': '/dev/utouch', 'one_point_bytes': 32,
                  'scope': report['scope']}, ensure_ascii=False))
