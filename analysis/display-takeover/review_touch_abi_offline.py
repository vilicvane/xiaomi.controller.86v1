"""Review saved firmware touch/file ABI against minimal pinned public headers."""
import ctypes
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
manifest = json.loads((HERE / 'touch-abi-reference-manifest.json').read_text())
route = json.loads((ROOT / 'analysis/pinout/a7-touch-input-route-1.50.10.json').read_text())

def header(name):
    item = next(x for x in manifest['files'] if Path(x['file']).name == name)
    raw = (HERE / item['file']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item['sha256']
    return raw.decode()

flags = {'TOUCH_DOWN': 1, 'TOUCH_MOVE': 2, 'TOUCH_UP': 4,
         'TOUCH_ID_VALID': 8, 'TOUCH_POS_VALID': 16,
         'TOUCH_PRESSURE_VALID': 32, 'TOUCH_SIZE_VALID': 64,
         'TOUCH_GESTURE_VALID': 128}
for name in ['touch-apache-master.h', 'touch-open-vela-dev.h']:
    text = header(name)
    for symbol, value in flags.items():
        match = re.search(r'#define\s+' + symbol + r'\s+\(1\s*<<\s*(\d+)\)', text)
        assert match and 1 << int(match.group(1)) == value

for name, rdonly_shift, nonblock_shift in [
    ('touch-fcntl-open-vela-dev.h', 1, 6),
    ('touch-fcntl-apache-12.7.0.h', 1, 6),
    ('touch-fcntl-apache-master.h', 0, 11),
]:
    text = header(name)
    assert re.search(r'#define\s+O_RDONLY\s+\(' + str(rdonly_shift) + r'U?\s*<<\s*0\)', text)
    assert re.search(r'#define\s+O_NONBLOCK\s+\(1U?\s*<<\s*' + str(nonblock_shift) + r'\)', text)

point_fields = [('id', ctypes.c_uint8), ('flags', ctypes.c_uint8),
                ('x', ctypes.c_int16), ('y', ctypes.c_int16),
                ('h', ctypes.c_int16), ('w', ctypes.c_int16),
                ('gesture', ctypes.c_uint16), ('pressure', ctypes.c_uint16)]
class NaturalPoint(ctypes.Structure):
    _fields_ = point_fields + [('timestamp', ctypes.c_uint64)]
class NaturalSample(ctypes.Structure):
    _fields_ = [('npoints', ctypes.c_int32), ('point', NaturalPoint * 1)]
class VelaPoint(ctypes.Structure):
    _pack_ = 1
    _fields_ = point_fields + [('dummy', ctypes.c_uint16), ('timestamp', ctypes.c_uint64)]
class VelaSample(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('npoints', ctypes.c_int32), ('dummy', ctypes.c_int32), ('point', VelaPoint * 1)]

assert ctypes.sizeof(ctypes.c_int32) == 4 and ctypes.alignment(ctypes.c_uint64) == 8
offsets = {'id': 8, 'flags': 9, 'x': 10, 'y': 12, 'h': 14, 'w': 16,
           'gesture': 18, 'pressure': 20, 'timestamp': 24}
for sample, point in [(NaturalSample, NaturalPoint), (VelaSample, VelaPoint)]:
    assert ctypes.sizeof(sample) == 32 and ctypes.sizeof(point) == 24
    assert sample.point.offset == 8
    assert {name: sample.point.offset + getattr(point, name).offset for name in offsets} == offsets
assert route['event_abi']['one_point_bytes'] == 32
assert route['event_abi']['point_stride_bytes'] == 24

def insns(filename):
    return {x['address']: x for x in json.loads((HERE / filename).read_text())}

worker = insns('touch-worker-tail-1.50.10.json')
for address, operand in [('0x38021534', 'r3, #0x19'),
                         ('0x38021576', 'r3, #0x1a'),
                         ('0x38021348', 'r3, #0x1c'),
                         ('0x38021362', 'r3, #0xc')]:
    assert worker[address]['operands'] == operand
file_read = insns('touch-file-read-body-1.50.10.json')
assert file_read['0x38029564']['operands'] == 'r4, r4, #0x1f'
assert file_read['0x38029562']['operands'] == 'r3, [r0, #0x10]'
assert file_read['0x38029572']['mnemonic'] == 'blx'

report = {
    'scope': 'Saved firmware and public headers only. No target access, execution, raw logs or credentials.',
    'firmware': {'version': route['firmware_version'], 'image_sha256': route['image_sha256']},
    'public_references': manifest,
    'touch_flags': flags,
    'sample_abi': {
        'endian': 'little', 'npoints': {'offset': 0, 'bytes': 4, 'signed': True},
        'point0_base': 8, 'point_stride': 24, 'single_point_bytes': 32,
        'point0_offsets': offsets,
        'padding_bytes': ['sample[4:8]', 'sample[22:24]'],
        'timestamp': {'bytes': 8, 'unsigned': True, 'units': 'microseconds',
                      'evidence': 'Publisher 0x38021320..0x3802133c computes seconds * 1000000 + nanoseconds / 1000, then stores pair at sample+24.'},
        'public_layout_difference': 'Apache natural structs require 32-bit int and uint64_t 8-byte alignment (A7 AAPCS). open-vela uses packed structs plus explicit 4-byte and 2-byte dummy fields, preserving identical byte offsets.',
        'layout_verification': 'Host ctypes with fixed-width fields and verified uint64 alignment models the A7 natural layout; separately verified the explicit packed layout. Not an ARM compiler or target execution test.',
        'target_confirmed': ['npoints0', 'point0 id8', 'flags9', 'x10', 'y12', 'timestamp24', '32-byte single point', '24-byte stride'],
        'public_only_field_semantics': ['h', 'w', 'gesture enum', 'pressure'],
    },
    'target_flag_evidence': {
        'down': '0x38021534 writes flags0x19 = DOWN|ID_VALID|POS_VALID',
        'move': '0x38021576 writes flags0x1a = MOVE|ID_VALID|POS_VALID',
        'up_with_position': '0x38021348 writes flags0x1c = UP|ID_VALID|POS_VALID',
        'up_without_position': '0x38021362 writes flags0x0c = UP|ID_VALID',
        'gui': '0x3806abce checks mask3 and 0x3806abd4 checks bit2; signed x/y loaded from sample+10/+12.',
        'parse_rule': 'Require npoints==1 and successful read length32. Inspect event bits; only update position if POS_VALID. UP without POS_VALID ends contact at its preceding valid position.',
    },
    'open_flag_version_difference': {
        'target_and_old_public': {'O_RDONLY': 1, 'O_NONBLOCK': 64, 'combined': 65},
        'apache_master_current': {'O_RDONLY': 0, 'O_NONBLOCK': 2048, 'combined': 2048},
        'target_evidence': ['0x383c972c passes0x41 to fd opener',
                            '0x38015068 shifts file flags left25 to test bit6; empty nonblocking read returns-11 at0x380150b8',
                            '0x38029564 shifts file flags left31 to test read-access bit0'],
        'warning': 'Use confirmed firmware constants0x01 and0x40; current Apache master fcntl.h is incompatible.',
    },
    'file_api': {
        'public_file_open': 'int file_open(struct file *filep, const char *path, int oflags, ...);',
        'public_file_read': 'ssize_t file_read(struct file *filep, void *buf, size_t nbytes);',
        'semantics': 'file_open fills caller-owned file structure and returns0 or negative errno. file_read takes that pointer, returns bytes or negative errno. Neither sets errno or adds cancellation points.',
        'public_fs_reference': 'https://raw.githubusercontent.com/open-vela/nuttx/9e79ad292fd103d3b9ef737757081a3f7fbbf9a4/include/nuttx/fs/fs.h',
        'local_fs_reference': 'analysis/fs/nuttx-inode.h lines1146..1166 and1474..1496 (pre-existing; no pinned provenance established here)',
        'target_fd_open': {'address': '0x3802c900 Thumb', 'ABI': 'open(path,oflags,...) -> fd or-1/errno', 'confirmed': True},
        'target_fd_to_file': {'address': '0x38025678 Thumb', 'ABI': '(fd,struct file **out)->0 or negative errno', 'confirmed': True},
        'target_file_read': {'address': '0x3802954c Thumb', 'ABI': '(file*,buf,len)->bytes or negative errno', 'confirmed': True},
        'target_file_open_candidate': {'address': '0x3802c958 Thumb', 'ABI': '(file*,path,flags,...)', 'status': 'Strong offline match: forwards r0/r1/r2 and va_list to0x3802c388 without errno conversion. No live execution or symbols.'},
        'target_file_structure': {'stride': 24, 'f_oflags_offset': 0, 'f_inode_offset': 16, 'f_priv_offset': 20,
                                  'limit': 'Observed target fields/stride. Do not substitute the current public struct file/config layout blindly.'},
        'warning': 'A file descriptor is an integer index, not a file pointer. Existing GUI calls fd-to-file helper before file_read.',
    },
    'other_version_difference': 'Public gesture enums differ: Apache double-click0/palm5; open-vela single-click0/double-click1/palm6. Target gesture names not independently confirmed; minimal input should ignore gesture.',
    'limits': ['Target NuttX/open-vela source revision and complete config are unidentified.',
               'No live sample or native file call was performed.',
               'Public header semantic matches do not establish a safe execution context, scheduler state or code/stack allocation.'],
    'binary_evidence_files': [
        'analysis/pinout/a7-touch-input-route-1.50.10.json',
        *['analysis/display-takeover/' + name for name in [
          'touch-worker-tail-1.50.10.json', 'touch-worker-prologue-1.50.10.json',
          'touch-file-read-body-1.50.10.json', 'touch-open-fd-body-1.50.10.json',
          'touch-fd-getfile-body-1.50.10.json', 'touch-file-vopen-entry-1.50.10.json']]
    ],
}
out = HERE / 'touch-abi-public-review-1.50.10.json'
out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'report': str(out), 'single_point_bytes': 32, 'target_open_flags': '0x41',
                  'scope': report['scope']}))
