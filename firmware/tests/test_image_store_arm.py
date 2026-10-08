"""Exercise compiled ARM image persistence and native decoding, without hardware.

File descriptors, FAT objects and I/O are modeled. Interrupted writes prove
the application's two-slot selection, not FAT/MMC/RPMsgFS power-loss durability.
Private fixtures and the exact stock image remain outside Git.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import os
import struct

import test_image_codec_arm as codec
from elftools.elf.elffile import ELFFile
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_PC, UC_ARM_REG_SP,
                               UC_ARM_REG_LR)

ROOT = Path(__file__).resolve().parents[2]
ELF = Path(os.environ.get('PANEL_FIRMWARE_ELF', ROOT / 'build/panel/panel.elf'))
IMAGE_PATHS = ('/data/86v1-image.0', '/data/86v1-image.1')
SETTINGS_PATHS = ('/data/86v1-return.0', '/data/86v1-return.1')
MAGIC, FAT_OPS = 0x31495056, 0x383f18dc
FILE_BASE, INODE_BASE, ERROR = 0x386d0000, 0x386e0000, 0x386f0000
STATE = 0x386f2000
MAX_BYTES = 1048576
STACK_BYTES = 16384
CALL_EVIDENCE = []


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def record(sequence, encoded, *, length=None, checksum=None, magic=MAGIC,
           header_check=None):
    """Build a protocol fixture; selection and verification run in ARM code."""
    length = len(encoded) if length is None else length
    checksum = fnv(encoded) if checksum is None else checksum
    header = struct.pack('<IIII', magic, sequence, length, checksum)
    return header + struct.pack('<I', fnv(header) if header_check is None else header_check) + encoded


class InterruptedWrite(Exception):
    pass


class FileSystem:
    """Native file ABI boundary shared by image-store and HTTP ARM models."""
    def init_files(self, files=None, mounts=None, faults=None, read_limit=None,
                   write_limit=None, interrupt_after_write=None):
        self.files = dict(files or {})
        self.mounts = dict(mounts or {})
        self.file_faults = dict(faults or {})
        self.read_limit = read_limit
        self.write_limit = write_limit
        self.interrupt_after_write = interrupt_after_write
        self.file_operations = []
        self.file_counts = Counter()
        self.descriptors = {}
        self.next_fd = 20
        self.on_file_operation = None

    def file_word(self, address, value=None):
        if value is None:
            return struct.unpack('<I', self.uc.mem_read(address, 4))[0]
        self.uc.mem_write(address, struct.pack('<I', value & 0xffffffff))

    def file_string(self, address):
        data = bytearray()
        while self.uc.mem_read(address, 1)[0]:
            data.extend(self.uc.mem_read(address, 1))
            address += 1
            assert len(data) < 256
        return data.decode('ascii')

    def file_operation(self, kind, path, **details):
        assert not getattr(self, 'locks', set()), f'{kind} while GUI locked'
        assert self.uc.reg_read(UC_ARM_REG_SP) % 8 == 0, kind
        self.file_counts[kind] += 1
        event = dict(op=kind, path=path, call=self.file_counts[kind], **details)
        self.file_operations.append(event)
        if self.on_file_operation:
            self.on_file_operation(self, event)
        return self.file_faults.get((kind, self.file_counts[kind]))

    def file_fail(self, error):
        self.file_word(getattr(self, 'file_errno', ERROR), error)
        self.ret(-1)

    def file_open(self):
        r = self.uc.reg_read
        path = self.file_string(r(UC_ARM_REG_R0))
        assert path in IMAGE_PATHS + SETTINGS_PATHS, path
        flags, mode = r(UC_ARM_REG_R1), r(UC_ARM_REG_R2)
        assert (flags, mode) in ((1, 0), (0x26, 0o644)), (flags, mode)
        fault = self.file_operation('open', path, flags=flags, mode=mode)
        if fault:
            return self.file_fail(fault)
        if flags == 1 and path not in self.files:
            return self.file_fail(2)
        if flags == 0x26:
            self.files[path] = b''
        fd = self.next_fd
        self.next_fd += 1
        pointer, inode = FILE_BASE + 32 * (fd - 20), INODE_BASE + 32 * (fd - 20)
        assert pointer + 32 < INODE_BASE and inode + 32 < ERROR
        self.descriptors[fd] = dict(path=path, flags=flags, position=0, file=pointer)
        self.uc.mem_write(pointer, bytes(24))
        self.uc.mem_write(inode, bytes(32))
        self.file_word(pointer, flags)
        self.file_word(pointer + 0x10, inode)
        self.uc.mem_write(inode + 0xe, b'\x03')
        self.file_word(inode + 0x10, FAT_OPS)
        self.file_mount(pointer, self.mounts.get(path, 'fat'))
        self.ret(fd)

    def file_mount(self, pointer, mount):
        inode = self.file_word(pointer + 0x10)
        if mount == 'null':
            self.file_word(pointer + 0x10, 0)
        elif mount == 'type':
            self.uc.mem_write(inode + 0xe, b'\x01')
        elif mount != 'fat':
            assert mount in ('tmp', 'rpmsg')
            self.file_word(inode + 0x10, 0x383f0000 if mount == 'tmp' else 0x383f0100)

    def file_getfile(self):
        r = self.uc.reg_read
        descriptor = self.descriptors[r(UC_ARM_REG_R0)]
        fault = self.file_operation('getfile', descriptor['path'])
        if fault == 'null':
            self.file_word(r(UC_ARM_REG_R1), 0)
            return self.ret(0)
        if isinstance(fault, tuple) and fault[0] == 'mount':
            self.file_mount(descriptor['file'], fault[1])
            fault = None
        if fault:
            return self.ret(-fault)
        self.file_word(r(UC_ARM_REG_R1), descriptor['file'])
        self.ret(0)

    def file_read(self):
        r = self.uc.reg_read
        pointer, output, requested = r(UC_ARM_REG_R0), r(UC_ARM_REG_R1), r(UC_ARM_REG_R2)
        descriptor = next(item for item in self.descriptors.values() if item['file'] == pointer)
        assert descriptor['flags'] == 1 and 0 < requested <= 512
        fault = self.file_operation('read', descriptor['path'], requested=requested,
                                    position=descriptor['position'])
        if isinstance(fault, tuple) and fault[0] == 'error':
            return self.ret(-fault[1])  # file_read returns negative errno.
        data = self.files[descriptor['path']][descriptor['position']:]
        if isinstance(fault, bytes):
            data = fault
        limit = requested if fault is None or isinstance(fault, bytes) else fault
        if self.read_limit is not None:
            limit = min(limit, self.read_limit)
        if limit > requested:
            return self.ret(limit)
        part = data[:min(requested, limit)]
        if part:
            self.uc.mem_write(output, part)
        descriptor['position'] += len(part)
        self.ret(len(part))

    def file_write(self):
        r = self.uc.reg_read
        descriptor = self.descriptors[r(UC_ARM_REG_R0)]
        pointer, requested = r(UC_ARM_REG_R1), r(UC_ARM_REG_R2)
        assert descriptor['flags'] == 0x26 and 0 < requested <= 512
        data = bytes(self.uc.mem_read(pointer, requested))
        fault = self.file_operation('write', descriptor['path'], requested=requested,
                                    position=descriptor['position'])
        if isinstance(fault, tuple) and fault[0] == 'error':
            return self.file_fail(fault[1])
        completed = requested if fault is None else fault
        if self.write_limit is not None:
            completed = min(completed, self.write_limit)
        if completed <= requested:
            position = descriptor['position']
            current = self.files[descriptor['path']]
            self.files[descriptor['path']] = current[:position] + data[:completed] + current[position + completed:]
            descriptor['position'] += completed
        if self.file_counts['write'] == self.interrupt_after_write:
            raise InterruptedWrite()
        self.ret(completed)

    def file_sync(self):
        descriptor = self.descriptors[self.uc.reg_read(UC_ARM_REG_R0)]
        assert descriptor['flags'] == 0x26
        fault = self.file_operation('sync', descriptor['path'])
        if fault:
            return self.file_fail(fault)
        self.ret(0)

    def file_close(self):
        fd = self.uc.reg_read(UC_ARM_REG_R0)
        descriptor = self.descriptors.pop(fd)
        fault = self.file_operation('close', descriptor['path'], fd=fd)
        if fault:
            return self.file_fail(fault)
        self.ret(0)


class Machine(FileSystem, codec.Machine):
    def __init__(self, files=None, mounts=None, faults=None, fail_allocation=0,
                 persistent_failure=False, **options):
        self.init_files(files, mounts, faults, **options)
        codec.ELF = ELF
        super().__init__(fail_allocation, persistent_failure)
        with ELF.open('rb') as stream:
            self.symbols = {item.name: item['st_value'] for item in
                            ELFFile(stream).get_section_by_name('.symtab').iter_symbols()}
        for address, method in ((0x3802c900, self.file_open), (0x38025678, self.file_getfile),
                                (0x3802954c, self.file_read), (0x3802b378, self.file_write),
                                (0x3802b3ec, self.file_sync), (0x38025de0, self.file_close)):
            self.hook(address, method)
        self.hook(0x38018c5c, lambda: self.ret(ERROR))
        self.uc.mem_write(codec.STACK - STACK_BYTES - 128, codec.GUARD)
        self.uc.mem_write(codec.OUTPUT - 128, codec.GUARD)
        self.uc.mem_write(codec.OUTPUT, b'\xcd' * 307200)
        self.uc.mem_write(codec.OUTPUT + 307200, codec.GUARD)
        self.uc.mem_write(STATE - 128, codec.GUARD)
        self.uc.mem_write(STATE, bytes(16))
        self.uc.mem_write(STATE + 16, codec.GUARD)

    def call(self, name, *arguments):
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), arguments):
            self.uc.reg_write(register, value)
        self.uc.reg_write(UC_ARM_REG_SP, codec.STACK)
        self.uc.reg_write(UC_ARM_REG_LR, codec.STOP | 1)
        self.uc.emu_start(self.symbols[name] | 1, 0, timeout=60_000_000, count=100_000_000)
        assert self.uc.reg_read(UC_ARM_REG_PC) == codec.STOP
        self.complete()
        status = self.uc.reg_read(UC_ARM_REG_R0)
        CALL_EVIDENCE.append(dict(function=name, status=status,
                                  allocator_peak=self.peak,
                                  allocation_attempts=self.attempts,
                                  observed_stack_bytes=codec.STACK - self.minimum_sp,
                                  open_descriptors=0, allocated_heap_bytes=0,
                                  native_file_calls=len(self.file_operations),
                                  guarded_buffers_and_code_unchanged=True))
        return status

    def complete(self):
        assert not self.descriptors, self.descriptors
        assert not self.live, self.live
        assert self.uc.mem_read(codec.STACK - STACK_BYTES - 128, 128) == codec.GUARD
        assert self.minimum_sp >= codec.STACK - STACK_BYTES
        assert self.uc.mem_read(codec.OUTPUT - 128, 128) == codec.GUARD
        assert self.uc.mem_read(codec.OUTPUT + 307200, 128) == codec.GUARD
        assert self.uc.mem_read(STATE - 128, 128) == codec.GUARD
        assert self.uc.mem_read(STATE + 16, 128) == codec.GUARD
        assert bytes(self.uc.mem_read(codec.BASE, codec.LENGTH)) == self.stock_text
        for address, data in self.project_segments:
            assert bytes(self.uc.mem_read(address, len(data))) == data

    def save(self, encoded):
        self.uc.mem_write(codec.INPUT - 128, codec.GUARD)
        self.uc.mem_write(codec.INPUT, encoded)
        self.uc.mem_write(codec.INPUT + len(encoded), codec.GUARD)
        before = self.state()
        status = self.call('panel_image_save', STATE, codec.INPUT, len(encoded))
        if status:
            assert self.state() == before, 'Failed save changed the known recoverable record'
        else:
            sequence, length, checksum, valid = self.state()
            assert (length, checksum, valid) == (len(encoded), fnv(encoded), 1)
            assert self.files[IMAGE_PATHS[sequence & 1]] == record(sequence, encoded)
        assert self.uc.mem_read(codec.INPUT - 128, 128) == codec.GUARD
        assert self.uc.mem_read(codec.INPUT + len(encoded), 128) == codec.GUARD
        assert bytes(self.uc.mem_read(codec.INPUT, len(encoded))) == encoded
        return status

    def load(self, reference=None):
        status = self.call('panel_image_load', codec.OUTPUT, STATE)
        if status:
            assert self.state() == (0, 0, 0, 0)
        else:
            sequence, length, checksum, valid = self.state()
            assert valid == 1
            header = self.files[IMAGE_PATHS[sequence & 1]][:20]
            assert header == record(sequence, b'', length=length, checksum=checksum)[:20]
        if reference is not None:
            assert status == 0
            assert bytes(self.uc.mem_read(codec.OUTPUT, 307200)) == reference
        return status

    def state(self):
        return struct.unpack('<IIII', self.uc.mem_read(STATE, 16))


def fixtures():
    values = []
    for name in ('card-original.png', 'card-jpeg-q85.jpg'):
        values.append((name, (codec.FIXTURES / name).read_bytes(),
                       (codec.FIXTURES / (name + '.expected.rgb565')).read_bytes()))
    pixels = b''.join(struct.pack('<H', (index * 73) & 0xffff) for index in range(480 * 320))
    values.append(('synthetic-vimg', struct.pack('<4sHHII', b'VIMG', 480, 320, len(pixels), fnv(pixels)) + pixels, pixels))
    return values


def load_checks(values):
    checks = []
    _, png, png_pixels = values[0]
    _, jpeg, jpeg_pixels = values[1]
    for files, pixels in (({IMAGE_PATHS[0]: record(2, png)}, png_pixels),
                          ({IMAGE_PATHS[1]: record(3, jpeg)}, jpeg_pixels),
                          ({IMAGE_PATHS[0]: record(2, png), IMAGE_PATHS[1]: record(3, jpeg)}, jpeg_pixels),
                          ({IMAGE_PATHS[0]: record(4, png), IMAGE_PATHS[1]: record(3, jpeg)}, png_pixels),
                          ({IMAGE_PATHS[0]: record(0, png), IMAGE_PATHS[1]: record(0xffffffff, jpeg)}, png_pixels)):
        machine = Machine(files)
        assert machine.load(pixels) == 0
        assert machine.files == files and not machine.file_counts['write']
    checks.append('Load either slot, newest parity-bound sequence and UINT32 wrap using actual native PNG/JPEG, without file writes')
    malformed = [record(3, png, length=0), record(3, png, length=MAX_BYTES + 1),
                 record(3, png, checksum=0), record(3, png, header_check=0),
                 record(2, png), record(3, png)[:4], record(3, png)[:19],
                 record(3, png)[:-1], record(3, png) + b'x']
    for data in malformed:
        assert Machine({IMAGE_PATHS[1]: data}).load() == 422
        files = {IMAGE_PATHS[0]: record(2, png), IMAGE_PATHS[1]: data}
        machine = Machine(files)
        assert machine.load(png_pixels) == 0
        assert machine.files == files and not machine.file_counts['write']
    for data in (b'', b'V', b'VPI', b'FOREIGN', struct.pack('<I', MAGIC ^ 1)):
        assert Machine({IMAGE_PATHS[1]: data}).load() == 409
        assert Machine({IMAGE_PATHS[0]: record(2, png), IMAGE_PATHS[1]: data}).load(png_pixels) == 0
    checks.append('Zero/oversized length, header/body checksum, wrong parity, truncation and trailing data reject owned records; foreign namespace is distinct and older complete image survives')
    bad_png = bytearray(png)
    bad_png[-1] ^= 1
    for encoded in (bytes(bad_png), png[:-12], jpeg[:-2], b'not an image'):
        assert Machine({IMAGE_PATHS[1]: record(3, encoded)}).load() == 422
        files = {IMAGE_PATHS[0]: record(2, png), IMAGE_PATHS[1]: record(3, encoded)}
        assert Machine(files).load(png_pixels) == 0
    checks.append('A valid envelope cannot bypass native codec checks; bad newest PNG/JPEG/format falls back to older successfully decoded image')
    for mount in ('tmp', 'rpmsg', 'null', 'type'):
        machine = Machine({IMAGE_PATHS[0]: record(2, png)}, {IMAGE_PATHS[0]: mount})
        assert machine.load() == 503 and not machine.file_counts['read']
        assert machine.file_counts['close'] == 1
    baseline = Machine({IMAGE_PATHS[0]: record(2, png)})
    assert baseline.load(png_pixels) == 0
    for event in baseline.file_operations:
        if event['op'] in ('open', 'getfile', 'read', 'close'):
            value = ('error', 5) if event['op'] == 'read' else 5
            machine = Machine({IMAGE_PATHS[0]: record(2, png)}, faults={(event['op'], event['call']): value})
            expected = 0 if event['path'] == IMAGE_PATHS[1] else 503
            assert machine.load(png_pixels if expected == 0 else None) == expected, event
    checks.append('File inode/type/exact FAT ops and every load open/getfile/read/close error are checked; acquired descriptors and decoder heap are released')
    for limit in (1, 7, 31, 511):
        machine = Machine({IMAGE_PATHS[0]: record(2, png)}, read_limit=limit)
        assert machine.load(png_pixels) == 0
    # The first header read contains the ownership magic. EOF afterwards is a
    # truncated owned file, rather than a fabricated I/O error.
    for call in (2, 3):
        machine = Machine({IMAGE_PATHS[0]: record(2, png)}, faults={('read', call): 0})
        assert machine.load() == 422
    checks.append('Positive short reads are completed; zero progress in owned header/body is rejected as truncation with no unbounded retry')
    baseline = Machine({IMAGE_PATHS[1]: record(3, png)})
    assert baseline.load(png_pixels) == 0
    for failed in range(1, baseline.attempts + 1):
        machine = Machine({IMAGE_PATHS[1]: record(3, png)}, fail_allocation=failed, persistent_failure=True)
        assert machine.load() == 503
    # A single allocation failure for the newest body may recover by loading
    # the older complete image. Persistent OOM must clean both attempts.
    files = {IMAGE_PATHS[0]: record(2, png), IMAGE_PATHS[1]: record(3, jpeg)}
    assert Machine(files, fail_allocation=1).load(png_pixels) == 0
    assert Machine(files, fail_allocation=1, persistent_failure=True).load() == 503
    checks.append('Encoded-body/native-decoder OOM cleans heap; failed newest allocation can recover older, persistent allocation failure never claims a loaded image')
    for data, fault, expected in ((b'FOREIGN', None, 409),
                                 (record(3, png, checksum=0), None, 422),
                                 (b'FOREIGN', {('open', 1): 5}, 503),
                                 (record(3, png, checksum=0), {('open', 1): 5}, 503)):
        machine = Machine({IMAGE_PATHS[1]: data}, faults=fault)
        assert machine.load() == expected
    assert Machine({IMAGE_PATHS[0]: b'FOREIGN', IMAGE_PATHS[1]: record(3, png, checksum=0)}).load() == 409
    checks.append('When neither image loads, I/O503 outranks foreign409, which outranks damaged422 and absent404')
    for replacement, expected in ((record(4, png), 422),
                                  (record(2, png + bytes(len(png))), 422),
                                  (b'FOREIGN', 409)):
        machine = Machine({IMAGE_PATHS[0]: record(2, png)})
        def change_between_reads(model, event):
            if event['op'] == 'open' and event['path'] == IMAGE_PATHS[0] and event['call'] == 3:
                model.files[IMAGE_PATHS[0]] = replacement
        machine.on_file_operation = change_between_reads
        assert machine.load() == expected
    checks.append('Second boot read revalidates pinned header and allocation capacity: changed sequence, growing file and foreign replacement cannot become a loaded image or overrun guarded buffers')
    return checks


def collision(encoded):
    """Forge a different same-length FNV body to exercise byte readback."""
    prime, mask = 16777619, 0xffffffff
    inverse = pow(prime, -1, 1 << 32)
    target = fnv(encoded)
    for flip in (1, 2, 4, 8, 16, 32, 64, 128):
        prefix = encoded[:-5] + bytes([encoded[-5] ^ flip])
        start = fnv(prefix)
        forward = {}
        for first in range(256):
            step = ((start ^ first) * prime) & mask
            for second in range(256):
                forward[((step ^ second) * prime) & mask] = bytes([first, second])
        for fourth in range(256):
            step = ((target * inverse) & mask) ^ fourth
            for third in range(256):
                earlier = ((step * inverse) & mask) ^ third
                if earlier in forward:
                    forged = prefix + forward[earlier] + bytes([third, fourth])
                    assert len(forged) == len(encoded) and forged != encoded and fnv(forged) == target
                    return forged
    raise AssertionError('No deterministic FNV collision fixture')


def save_checks(values):
    checks = []
    _, png, png_pixels = values[0]
    _, jpeg, jpeg_pixels = values[1]
    initial = {IMAGE_PATHS[0]: record(2, png), IMAGE_PATHS[1]: record(1, png)}
    machine = Machine(initial)
    assert machine.save(jpeg) == 0
    assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
    assert machine.files[IMAGE_PATHS[1]] == record(3, jpeg)
    assert machine.save(png) == 0
    assert machine.files[IMAGE_PATHS[0]] == record(4, png)
    assert machine.files[IMAGE_PATHS[1]] == record(3, jpeg)
    assert Machine(machine.files).load(png_pixels) == 0
    wrapped = Machine({IMAGE_PATHS[0]: record(0xfffffffe, png), IMAGE_PATHS[1]: record(0xffffffff, jpeg)})
    assert wrapped.save(png) == 0
    assert wrapped.files[IMAGE_PATHS[0]] == record(0, png)
    assert wrapped.files[IMAGE_PATHS[1]] == record(0xffffffff, jpeg)
    assert Machine(wrapped.files).load(png_pixels) == 0
    checks.append('Save alternates only the older slot, keeps original encoded PNG/JPEG bytes and reloads newest including UINT32 wrap')
    for slot in IMAGE_PATHS:
        for data in (b'', b'VPI', b'FOREIGN', struct.pack('<I', MAGIC ^ 1)):
            files = dict(initial, **{slot: data})
            machine = Machine(files)
            assert machine.save(png) == 409
            assert machine.files == files and not machine.file_counts['write']
            assert not any(item['flags'] == 0x26 for item in machine.file_operations if item['op'] == 'open')
    checks.append('Foreign bytes in either project path return409 before create/truncate/write and preserve both files')
    for data in (struct.pack('<I', MAGIC), record(3, png, checksum=0), record(3, png) + b'x'):
        machine = Machine({IMAGE_PATHS[0]: initial[IMAGE_PATHS[0]], IMAGE_PATHS[1]: data})
        assert machine.save(jpeg) == 0
        assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
        assert machine.files[IMAGE_PATHS[1]] == record(3, jpeg)
    checks.append('Owned damaged inactive slot may be replaced while latest verified image is retained')
    for read_limit, write_limit in ((7, 3), (31, 127), (511, 511)):
        machine = Machine(initial, read_limit=read_limit, write_limit=write_limit)
        assert machine.save(png) == 0
        assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
        assert machine.files[IMAGE_PATHS[1]] == record(3, png)
        assert max(item['requested'] for item in machine.file_operations if item['op'] in ('read', 'write')) <= 512
    checks.append('Bounded512B operations complete positive short reads/writes, then sync, close and independent full readback before success')
    baseline = Machine(initial)
    assert baseline.save(png) == 0
    for event in baseline.file_operations:
        if event['op'] in ('open', 'getfile', 'read', 'sync', 'close'):
            value = ('error', 5) if event['op'] == 'read' else 5
            machine = Machine(initial, faults={(event['op'], event['call']): value})
            assert machine.save(png) == 503, event
            assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
    for event in (item for item in baseline.file_operations if item['op'] == 'write'):
        for value in (0, event['requested'] + 1, ('error', 5)):
            machine = Machine(initial, faults={('write', event['call']): value})
            assert machine.save(png) == 503
            assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
    checks.append('Every preflight/write/readback open/getfile/read/sync/close error and zero/oversized/error write returns503, cleans descriptors and never overwrites latest validated slot')
    first_write = next(index for index, item in enumerate(baseline.file_operations) if item['op'] == 'write')
    readback = next(item for item in baseline.file_operations[first_write:] if item['op'] == 'read')
    for value in (0, readback['requested'] + 1, record(5, png)[:20], record(3, png, header_check=0)[:20]):
        machine = Machine(initial, faults={('read', readback['call']): value})
        assert machine.save(png) == 503
        assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
    forged = collision(png)
    machine = Machine(initial)
    def alter_after_close(model, event):
        if event['op'] == 'close' and model.file_counts['sync'] and model.file_counts['write']:
            model.files[IMAGE_PATHS[1]] = record(3, forged)
            model.on_file_operation = None
    machine.on_file_operation = alter_after_close
    assert machine.save(png) == 503
    assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
    checks.append('Independent readback enforces exact header/EOF and byte identity, including a same-length FNV collision rather than only hash equality')
    for slot in IMAGE_PATHS:
        for mount in ('tmp', 'rpmsg', 'null', 'type'):
            machine = Machine(initial, {slot: mount})
            assert machine.save(png) == 503
            assert machine.files == initial and not machine.file_counts['write']
    # Select the write descriptor's FAT check, not a later readback descriptor.
    create_open = next(index for index, item in enumerate(baseline.file_operations)
                       if item['op'] == 'open' and item['flags'] == 0x26)
    create_getfile = baseline.file_operations[create_open + 1]
    assert create_getfile['op'] == 'getfile'
    for fault in (9, 'null', ('mount', 'tmp'), ('mount', 'rpmsg'), ('mount', 'null'), ('mount', 'type')):
        machine = Machine(initial, faults={('getfile', create_getfile['call']): fault})
        assert machine.save(png) == 503 and not machine.file_counts['write']
        assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
    checks.append('Exact FAT inode/type/ops gate applies to both preflight slots and newly created write descriptor')
    for encoded in (b'', bytes(MAX_BYTES + 1)):
        machine = Machine(initial)
        assert machine.save(encoded) == 503
        assert machine.files == initial and not machine.file_counts['write']
    checks.append('Save rejects internal input lengths0 and above1MiB without file mutation')
    return checks


def interruption_checks(values):
    _, png, png_pixels = values[0]
    _, jpeg, jpeg_pixels = values[1]
    bad_png = bytearray(png)
    bad_png[-1] ^= 1
    # The newer envelope is checksum-valid but its PNG CRC fails. Real boot
    # must protect the older JPEG that actually decoded, not the newest hash.
    initial = {IMAGE_PATHS[0]: record(2, jpeg), IMAGE_PATHS[1]: record(3, bytes(bad_png))}
    baseline = Machine(initial, write_limit=127)
    assert baseline.load(jpeg_pixels) == 0 and baseline.state()[0] == 2
    assert baseline.save(png) == 0
    assert baseline.state()[0] == 5 and baseline.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
    transitions = []
    for boundary in range(1, baseline.file_counts['write'] + 1):
        machine = Machine(initial, write_limit=127, interrupt_after_write=boundary)
        assert machine.load(jpeg_pixels) == 0 and machine.state()[0] == 2
        known = machine.state()
        try:
            machine.save(png)
            raise AssertionError('Write interruption was not reached')
        except InterruptedWrite:
            pass
        assert machine.state() == known
        assert bytes(machine.uc.mem_read(codec.INPUT, len(png))) == png
        assert machine.uc.mem_read(codec.INPUT - 128, 128) == codec.GUARD
        assert machine.uc.mem_read(codec.INPUT + len(png), 128) == codec.GUARD
        assert machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
        complete = machine.files[IMAGE_PATHS[1]] == record(5, png)
        expected = png_pixels if complete else jpeg_pixels
        reboot = Machine(machine.files)
        assert reboot.load(expected) == 0
        assert reboot.state()[0] == (5 if complete else 2)
        assert reboot.files == machine.files and not reboot.file_counts['write']
        transitions.append(dict(write_boundary=boundary, complete_new_record=complete,
                                loaded='new PNG' if complete else 'previous JPEG'))
    partial_magic = []
    for count in (1, 2, 3):
        machine = Machine(initial, write_limit=count, interrupt_after_write=1)
        assert machine.load(jpeg_pixels) == 0 and machine.state()[0] == 2
        known = machine.state()
        try:
            machine.save(png)
            raise AssertionError('Partial-magic interruption was not reached')
        except InterruptedWrite:
            pass
        assert machine.state() == known
        assert len(machine.files[IMAGE_PATHS[1]]) == count
        reboot = Machine(machine.files)
        assert reboot.load(jpeg_pixels) == 0
        assert reboot.save(png) == 409 and reboot.files == machine.files
        partial_magic.append(dict(header_bytes=count, loaded='previous JPEG',
                                  subsequent_save_status=409))
    return dict(case='protect-decoded-old-slot-after-undecodable-newest-at-every-write-boundary', boundaries=transitions,
                partial_magic=partial_magic,
                scope='Application logical slots with immediate modeled disk bytes; not actual FAT, fsync or power-loss atomicity')


def known_record_checks(values):
    _, png, png_pixels = values[0]
    _, jpeg, jpeg_pixels = values[1]
    checks = []
    initial = {IMAGE_PATHS[0]: record(2, png), IMAGE_PATHS[1]: record(1, jpeg)}
    replacements = (None, struct.pack('<I', MAGIC), record(4, png),
                    record(2, jpeg), record(2, png, checksum=0))
    for replacement in replacements:
        machine = Machine(initial)
        assert machine.load(png_pixels) == 0
        known = machine.state()
        if replacement is None:
            del machine.files[IMAGE_PATHS[0]]
        else:
            machine.files[IMAGE_PATHS[0]] = replacement
        before = dict(machine.files)
        assert machine.save(jpeg) == 503
        assert machine.files == before and machine.state() == known
        assert not machine.file_counts['write']
    checks.append('Known decoded record must remain present with exact sequence/length/FNV; missing, torn, modified or replaced known slot returns503 before any truncate/write and keeps worker state')
    for fault in ({('write', 1): 0}, {('sync', 1): 5}, {('close', 1): 5}):
        machine = Machine(initial)
        assert machine.load(png_pixels) == 0
        known = machine.state()
        machine.file_faults = {(kind, machine.file_counts[kind] + call): value
                              for (kind, call), value in fault.items()}
        assert machine.save(jpeg) == 503
        assert machine.state() == known and machine.files[IMAGE_PATHS[0]] == initial[IMAGE_PATHS[0]]
    checks.append('Failure after a known image is loaded never advances worker state or overwrites its recoverable file, including sync/close ambiguity')
    bad_png = bytearray(png)
    bad_png[-1] ^= 1
    files = {IMAGE_PATHS[1]: record(0xffffffff, jpeg), IMAGE_PATHS[0]: record(0, bytes(bad_png))}
    machine = Machine(files)
    assert machine.load(jpeg_pixels) == 0 and machine.state()[0] == 0xffffffff
    assert machine.save(png) == 0 and machine.state()[0] == 2
    assert machine.files[IMAGE_PATHS[1]] == files[IMAGE_PATHS[1]]
    assert machine.files[IMAGE_PATHS[0]] == record(2, png)
    reboot = Machine(machine.files)
    assert reboot.load(png_pixels) == 0 and reboot.state()[0] == 2
    checks.append('Sequence skips checksum-valid undecodable newest record while preserving decoded old slot, including UINT32 wrap and parity correction')
    return checks


def main():
    CALL_EVIDENCE.clear()
    checks = []
    for name, encoded, reference in fixtures():
        machine = Machine()
        assert machine.load() == 404
        assert machine.save(encoded) == 0
        assert machine.files == {IMAGE_PATHS[1]: record(1, encoded)}
        assert Machine(machine.files).load(reference) == 0
        checks.append(dict(case=name + '-save-boot', input_bytes=len(encoded),
                           output_sha256=hashlib.sha256(reference).hexdigest(),
                           allocator_peak=machine.peak, observed_stack_bytes=codec.STACK - machine.minimum_sp))
    values = fixtures()
    checks.extend(load_checks(values))
    checks.extend(save_checks(values))
    checks.extend(known_record_checks(values))
    checks.append(interruption_checks(values))
    result = dict(scope='Offline compiled ARM image storage and original native PNG/JPEG; file/FAT/allocator OS boundaries mocked, no hardware or actual power loss.',
                  elf_sha256=hashlib.sha256(ELF.read_bytes()).hexdigest(),
                  test_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  native_codec_model_sha256=hashlib.sha256(Path(codec.__file__).read_bytes()).hexdigest(),
                  stock_sha256=hashlib.sha256(codec.original).hexdigest(), checks=checks,
                  actual_arm_call_count=len(CALL_EVIDENCE), calls=CALL_EVIDENCE)
    output = os.environ.get('PANEL_IMAGE_STORE_RESULT_PATH')
    if output:
        Path(output).write_text(json.dumps(result, indent=2))
    print('Passed', len(checks), 'actual ARM image-store groups')
    return result


if __name__ == '__main__':
    main()
