"""Execute the linked settings/HTTP ARM code against a file ABI model.

Only native NuttX calls are mocked. No device, real FAT/MMC durability, scheduler,
power loss, native mutex timing or hardware filesystem writes are exercised.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import os
import struct

import test_http_arm as http
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP

MAGIC = 0x31545256
STORE = 0x38732000
FILE_BASE, INODE_BASE = 0x38740000, 0x38750000
FAT_OPS = 0x383f18dc
PATHS = ('/data/86v1-return.0', '/data/86v1-return.1')


def record(sequence, seconds, *, magic=MAGIC, check=None):
    checksum = magic ^ sequence ^ seconds if check is None else check
    return struct.pack('<IIII', magic, sequence, seconds, checksum)


class Machine(http.Machine):
    def __init__(self, files=None, mounts=None, faults=None):
        self.files = dict(files or {})
        self.mounts = dict(mounts or {})
        self.faults = dict(faults or {})
        self.operations = []
        self.counts = Counter()
        self.descriptors = {}
        self.next_fd = 20
        self.on_operation = None
        super().__init__()
        self.uc.mem_write(STORE - 128, http.GUARD)
        self.uc.mem_write(STORE + 8, http.GUARD)

    def operation(self, kind, slot, **details):
        assert not self.locks, f'{kind} while holding GUI mutex'
        assert self.uc.reg_read(UC_ARM_REG_SP) % 8 == 0, kind
        self.counts[kind] += 1
        event = dict(op=kind, slot=slot, call=self.counts[kind], **details)
        self.operations.append(event)
        if self.on_operation:
            self.on_operation(self, event)
        return self.faults.get((kind, self.counts[kind]))

    def fail(self, error):
        self.word(http.ERROR, error)
        self.ret(-1)

    def file_open(self):
        r = self.uc.reg_read
        path = self.string(r(UC_ARM_REG_R0))
        assert path in PATHS, path
        slot = PATHS.index(path)
        flags, mode = r(UC_ARM_REG_R1), r(UC_ARM_REG_R2)
        assert (flags, mode) in ((1, 0), (0x26, 0o644))
        fault = self.operation('open', slot, flags=flags, mode=mode)
        if fault:
            return self.fail(fault)
        if flags == 1 and slot not in self.files:
            return self.fail(2)
        if flags == 0x26:
            self.files[slot] = b''
        fd = self.next_fd
        self.next_fd += 1
        pointer = FILE_BASE + 32 * (fd - 20)
        inode = INODE_BASE + 32 * (fd - 20)
        self.descriptors[fd] = dict(slot=slot, flags=flags, position=0, file=pointer)
        self.uc.mem_write(pointer, bytes(24))
        self.uc.mem_write(inode, bytes(32))
        self.word(pointer, flags)
        self.word(pointer + 0x10, inode)
        self.byte(inode + 0xe, 3)
        self.word(inode + 0x10, FAT_OPS)
        mount = self.mounts.get(slot, 'fat')
        if mount == 'null':
            self.word(pointer + 0x10, 0)
        elif mount == 'type':
            self.byte(inode + 0xe, 1)
        elif mount != 'fat':
            assert mount in ('tmp', 'rpmsg')
            self.word(inode + 0x10, 0x383f0000 if mount == 'tmp' else 0x383f0100)
        self.ret(fd)

    def file_getfile(self):
        r = self.uc.reg_read
        descriptor = self.descriptors[r(UC_ARM_REG_R0)]
        fault = self.operation('getfile', descriptor['slot'])
        if fault == 'null':
            self.word(r(UC_ARM_REG_R1), 0)
            return self.ret()
        if isinstance(fault, tuple) and fault[0] == 'mount':
            inode = self.word(descriptor['file'] + 0x10)
            if fault[1] == 'null':
                self.word(descriptor['file'] + 0x10, 0)
            elif fault[1] == 'type':
                self.byte(inode + 0xe, 1)
            else:
                assert fault[1] in ('tmp', 'rpmsg')
                self.word(inode + 0x10, 0x383f0000 if fault[1] == 'tmp' else 0x383f0100)
            fault = None
        if fault:
            return self.ret(-fault)
        self.word(r(UC_ARM_REG_R1), descriptor['file'])
        self.ret()

    def file_read(self):
        r = self.uc.reg_read
        pointer, output, maximum = r(UC_ARM_REG_R0), r(UC_ARM_REG_R1), r(UC_ARM_REG_R2)
        descriptor = next(value for value in self.descriptors.values() if value['file'] == pointer)
        assert descriptor['flags'] == 1 and maximum == 17 and output % 4 == 0
        fault = self.operation('read', descriptor['slot'], maximum=maximum)
        if isinstance(fault, tuple) and fault[0] == 'error':
            return self.ret(-fault[1])  # file_read returns negative errno, not -1/errno.
        data = self.files[descriptor['slot']][descriptor['position']:]
        if isinstance(fault, bytes):
            data = fault
        limit = maximum if fault is None or isinstance(fault, bytes) else fault
        if limit > maximum:
            return self.ret(limit)
        part = data[:min(maximum, limit)]
        self.uc.mem_write(output, part)
        descriptor['position'] += len(part)
        self.ret(len(part))

    def file_write(self):
        r = self.uc.reg_read
        descriptor = self.descriptors[r(UC_ARM_REG_R0)]
        pointer, count = r(UC_ARM_REG_R1), r(UC_ARM_REG_R2)
        assert descriptor['flags'] == 0x26 and count == 16 and pointer % 4 == 0
        data = bytes(self.uc.mem_read(pointer, count))
        magic, sequence, seconds, check = struct.unpack('<IIII', data)
        assert magic == MAGIC and (sequence & 1) == descriptor['slot']
        assert check == magic ^ sequence ^ seconds
        fault = self.operation('write', descriptor['slot'], bytes=count)
        if isinstance(fault, tuple):
            return self.fail(fault[1])
        completed = count if fault is None else fault
        self.files[descriptor['slot']] = data[:min(count, completed)]
        self.ret(completed)

    def file_sync(self):
        fd = self.uc.reg_read(UC_ARM_REG_R0)
        descriptor = self.descriptors[fd]
        assert descriptor['flags'] == 0x26
        fault = self.operation('sync', descriptor['slot'])
        if fault:
            return self.fail(fault)
        self.ret()

    def file_close(self):
        fd = self.uc.reg_read(UC_ARM_REG_R0)
        descriptor = self.descriptors.pop(fd)
        fault = self.operation('close', descriptor['slot'], fd=fd)
        self.closed.append(fd)
        if fault:
            return self.fail(fault)
        self.ret()

    def store(self, sequence=None, seconds=None):
        if sequence is not None:
            self.word(STORE, sequence)
            self.word(STORE + 4, seconds)
        return self.word(STORE), self.word(STORE + 4)

    def complete(self):
        assert not self.descriptors, self.descriptors
        assert not self.locks
        assert bytes(self.uc.mem_read(STORE - 128, 128)) == http.GUARD
        assert bytes(self.uc.mem_read(STORE + 8, 128)) == http.GUARD
        self.guards()

    def load(self):
        self.call('panel_settings_load', STORE)
        self.complete()
        return self.store()

    def save(self, seconds):
        status = self.call('panel_settings_save', STORE, seconds)
        self.complete()
        return status


def load_checks():
    checks = []
    for files, expected in (({}, (0, 60)), ({0: record(2, 0)}, (2, 0)),
                            ({1: record(3, 3600)}, (3, 3600)),
                            ({0: record(2, 2), 1: record(3, 3)}, (3, 3)),
                            ({0: record(4, 4), 1: record(3, 3)}, (4, 4)),
                            ({0: record(0, 0), 1: record(0xffffffff, 1)}, (0, 0))):
        m = Machine(files)
        assert m.load() == expected
        assert not m.counts['write'] and m.files == files
    checks.append('Actual ARM loads missing default60, either valid slot, newest parity-bound sequence, seconds0/3600 and modulo32 sequence wrap without writes')
    malformed = [b'', b'V', b'VRT', b'FOREIGN', struct.pack('<I', MAGIC),
                 record(2, 2)[:15], record(2, 2) + b'x', record(2, 2) + bytes(128),
                 record(2, 3601), record(2, 2, check=0), record(3, 3)]
    for data in malformed:
        m = Machine({0: data})
        assert m.load() == (0, 60), data
        m = Machine({0: data, 1: record(1, 7)})
        assert m.load() == (1, 7), data
    checks.append('Short/foreign/damaged/trailing/checksum/range/slot-sequence records cannot become active settings; other valid slot survives')
    for mount in ('tmp', 'rpmsg', 'null', 'type'):
        m = Machine({0: record(2, 10)}, {0: mount})
        assert m.load() == (0, 60)
        assert not m.counts['read'] and m.counts['close'] == 1
    for fault in ({('open', 1): 5}, {('getfile', 1): 9}, {('getfile', 1): 'null'},
                  {('read', 1): ('error', 5)}, {('read', 1): 8}, {('close', 1): 5}):
        m = Machine({0: record(2, 10)}, faults=fault)
        assert m.load() == (0, 60)
    checks.append('Exact f_inode/type/FAT-ops gate rejects tmpfs/RPMsgFS/null/wrong type; open/getfile/read/partial/close errors fall back and close every acquired descriptor')
    return checks


def save_checks():
    checks = []
    m = Machine()
    assert m.load() == (0, 60)
    for sequence, seconds in ((1, 1), (2, 3600), (3, 0)):
        prior = dict(m.files)
        assert m.save(seconds) == 0
        assert m.store() == (sequence, seconds)
        assert m.files[sequence & 1] == record(sequence, seconds)
        other = (sequence & 1) ^ 1
        if other in prior:
            assert m.files[other] == prior[other]
    assert Machine(m.files).load() == (3, 0)
    wrapped = Machine({0: record(0xfffffffe, 8), 1: record(0xffffffff, 9)})
    assert wrapped.load() == (0xffffffff, 9) and wrapped.save(10) == 0
    assert wrapped.store() == (0, 10) and Machine(wrapped.files).load() == (0, 10)
    checks.append('Actual ARM saves exact16B own-slot record, alternates slots, preserves previous record and reloads latest value including UINT32 sequence wrap')
    for slot in (0, 1):
        for data in (b'x', b'FOREIGN', record(2, 5, magic=0x12345678)):
            m = Machine({slot: data})
            m.store(0, 60)
            before = dict(m.files)
            assert m.save(5) == 409
            assert not m.counts['write'] and m.files == before and m.store() == (0, 60)
    checks.append('Either foreign namespace slot returns409 without create/truncate/write or runtime/store mutation; foreign bytes are preserved')
    for data in (struct.pack('<I', MAGIC), record(1, 3, check=0), record(1, 3) + b'x'):
        m = Machine({0: record(2, 60), 1: data})
        assert m.load() == (2, 60) and m.save(5) == 0
        assert m.files[0] == record(2, 60) and m.files[1] == record(3, 5)
    checks.append('Damaged project-owned inactive slot may be replaced while current validated slot remains unchanged')

    initial = {0: record(2, 60), 1: record(1, 1)}
    baseline = Machine(initial)
    baseline.store(2, 60)
    assert baseline.save(7) == 0
    assert baseline.counts['write'] == baseline.counts['sync'] == 1
    cases = []
    for event in baseline.operations:
        if event['op'] in ('open', 'getfile', 'read', 'sync', 'close'):
            cases.append(((event['op'], event['call']), ('error', 5) if event['op'] == 'read' else 5))
    for key, fault in cases:
        m = Machine(initial, faults={key: fault})
        m.store(2, 60)
        assert m.save(7) == 503, key
        assert m.store() == (2, 60) and m.files[0] == initial[0], key
    for fault in (0, 7, 15, 17, ('error', 5)):
        m = Machine(initial, faults={('write', 1): fault})
        m.store(2, 60)
        assert m.save(7) == 503 and m.store() == (2, 60)
        assert not m.counts['sync'] and m.files[0] == initial[0]
    checks.append('Fault at every preflight/create/readback open/getfile/read/close or sync, plus short/oversized/error write, returns503 without store publication and retains previous slot')
    readback = [event for event in baseline.operations if event['op'] == 'read'][-1]['call']
    for fault in (8, 18, record(3, 7) + b'x', record(3, 8), record(5, 7), record(3, 7, check=0)):
        m = Machine(initial, faults={('read', readback): fault})
        m.store(2, 60)
        assert m.save(7) == 503 and m.store() == (2, 60)
    checks.append('Readback exact length, sequence, value and checksum are required before save success; uncertain readback never updates store')
    for slot in (0, 1):
        m = Machine(initial, {slot: 'tmp'})
        m.store(2, 60)
        assert m.save(7) == 503 and not m.counts['write'] and m.files == initial
    create_getfile = [event for event in baseline.operations if event['op'] == 'getfile'][2]['call']
    for fault in (9, 'null', ('mount', 'tmp'), ('mount', 'rpmsg'),
                  ('mount', 'null'), ('mount', 'type')):
        m = Machine(initial, faults={('getfile', create_getfile): fault})
        m.store(2, 60)
        assert m.save(7) == 503 and not m.counts['write']
        assert m.store() == (2, 60) and m.files[0] == initial[0]
    checks.append('FAT validation is required on both existing slots and newly opened write descriptor; no file body WRITE occurs after mount/getfile rejection')
    return checks


def settings_request(value):
    payload = json.dumps({'return_after_seconds': value}, separators=(',', ':')).encode()
    return http.request('POST', '/api/settings', (f'Content-Length: {len(payload)}',)), payload


def again(machine, data, send_events=()):
    machine.closed.clear()
    machine.sent.clear()
    machine.transact(data, send_events)


def http_checks():
    checks = []
    for files, seconds in (({}, 60), ({1: record(1, 17)}, 17)):
        m = Machine(files).ready()
        m.f('activity_valid', 1)
        m.transact([http.request('GET', '/api/settings')])
        m.response(200, f'{{"return_after_seconds":{seconds}}}\n'.encode(), settings=True)
        assert m.f('return_after_ms') == seconds * 1000 and not m.f('activity_valid')
        assert not m.counts['write']
        m.complete()
    m = Machine().ready()
    m.transact([http.request('OPTIONS', '/api/settings')])
    m.response(204, settings=True)
    assert not m.counts['write']
    checks.append('Server startup loads and mutex-publishes persisted/default timer; GET returns exact JSON and OPTIONS CORS GET,POST without save')

    m = Machine().ready()
    m.transact([http.request('GET', '/api/settings')])
    for sequence, seconds in ((1, 2), (2, 60), (3, 0)):
        m.f('activity_ms', 123)
        m.f('activity_valid', 1)
        header, payload = settings_request(seconds)
        again(m, [header + payload])
        m.response(200, f'{{"return_after_seconds":{seconds}}}\n'.encode(), settings=True)
        assert m.files[sequence & 1] == record(sequence, seconds)
        assert m.f('return_after_ms') == seconds * 1000 and not m.f('activity_valid')
        m.f('activity_valid', 1)
        writes = m.counts['write']
        again(m, [http.request('GET', '/api/settings')])
        m.response(200, f'{{"return_after_seconds":{seconds}}}\n'.encode(), settings=True)
        assert m.counts['write'] == writes and m.f('activity_valid') == 1
        m.complete()
    assert Machine(m.files).load() == (3, 0)
    checks.append('One running server keeps sequence across consecutive POSTs, alternates record slots, resets activity only on confirmed changes and serves GET without resetting active timer')

    for seconds in (0, 1, 3600):
        header, payload = settings_request(seconds)
        m = Machine().ready()
        m.f('activity_valid', 1)
        def before_publish(machine, event):
            if event['op'] in ('write', 'sync'):
                assert machine.f('return_after_ms') == 60000, 'Published before verified save'
        m.on_operation = before_publish
        m.transact([header + payload[:3], payload[3:8], ('error', 4), payload[8:]])
        m.response(200, f'{{"return_after_seconds":{seconds}}}\n'.encode(), settings=True)
        assert m.files[1] == record(1, seconds)
        assert m.f('return_after_ms') == seconds * 1000 and not m.f('activity_valid')
        assert ('{"return_after_seconds":%u}\n', 64, (seconds,)) in m.format_calls
        m.complete()
    checks.append('Fragmented/coalesced POST JSON with EINTR saves0/1/3600, verifies fsync/close/readback before mutex publication and returns exact200 JSON')
    invalid = [(b'{"return_after_seconds":3601}', 422),
               (b'{"return_after_seconds":4294967296}', 422),
               (b'{"return_after_seconds":-1}', 400),
               (b'{"return_after_seconds":01}', 400),
               (b'{"return_after_seconds":1.0}', 400),
               (b'{"return_after_seconds":true}', 400),
               (b'{"return_after_seconds":1,"extra":0}', 400),
               (b'{"return_after_seconds":1}x', 400), (b'{}', 400)]
    for payload, status in invalid:
        m = Machine().ready()
        m.transact([http.request('POST', '/api/settings', (f'Content-Length: {len(payload)}',)) + payload])
        m.response(status, settings=True)
        assert not m.counts['write'] and m.f('return_after_ms') == 60000
        m.complete()
    for length, status in ((0, 400), (65, 413)):
        m = Machine().ready()
        m.transact([http.request('POST', '/api/settings', (f'Content-Length: {length}',))])
        m.response(status)
        assert len(m.receive_calls) == 1 and not m.counts['write']
    header, payload = settings_request(2)
    m = Machine().ready()
    m.transact([header + payload[:4], 0])
    m.response(400, settings=True)
    assert not m.counts['write'] and m.f('return_after_ms') == 60000
    checks.append('HTTP shape/range/overflow/leading-zero/float/bool/extra/trailing/length/short-body rejection never calls native WRITE or changes runtime timer')

    for files, faults, status in (({0: b'FOREIGN'}, {}, 409), ({1: b'FOREIGN'}, {}, 409),
                                  ({}, {('write', 1): 8}, 503),
                                  ({}, {('sync', 1): 5}, 503),
                                  ({}, {('close', 1): 5}, 503)):
        m = Machine(files).ready()
        m.transact([http.request('GET', '/api/settings')])
        m.f('activity_ms', 123)
        m.f('activity_valid', 1)
        # Fault counters include boot load; inject only the later POST operation.
        m.faults = {(kind, m.counts[kind] + number): value
                    for (kind, number), value in faults.items()}
        again(m, [header + payload])
        m.response(status, settings=True)
        assert m.f('return_after_ms') == 60000 and m.f('server_error') == status
        assert m.f('activity_ms') == 123 and m.f('activity_valid') == 1
        m.complete()
    checks.append('HTTP namespace409 and write/sync/close503 preserve runtime setting and return failure rather than false saved confirmation')
    m = Machine().ready()
    m.lock_fail_calls.add(m.lock_calls + 3)  # startup, IP, then settings publication.
    m.transact([header + payload])
    m.response(503, settings=True)
    assert m.files[1] == record(1, 2) and m.f('return_after_ms') == 60000
    m.complete()
    checks.append('Failed publication mutex returns503 without runtime change even if file save completed; persistent commit and response status are distinguished')
    for sends in ([0], [('error', 5)]):
        m = Machine().ready()
        m.transact([header + payload], sends)
        assert not m.sent and 12 in m.closed
        assert m.files[1] == record(1, 2) and m.f('return_after_ms') == 2000
        m.complete()
    checks.append('Lost HTTP response after completed save leaves committed/runtime value intact and closes client; no successful client acknowledgement is inferred')
    for method in ('GET', 'POST'):
        for result in (-1, 64):
            m = Machine().ready()
            m.printf_result = result
            m.transact([http.request('GET', '/api/settings')] if method == 'GET' else [header + payload])
            assert not m.sent and not m.send_calls and 12 in m.closed
            assert any(size == 64 for _, size, _ in m.format_calls)
            assert m.f('return_after_ms') == (60000 if method == 'GET' else 2000)
            assert m.files == ({} if method == 'GET' else {1: record(1, 2)})
            m.complete()
    checks.append('JSON uses64B snprintf bound; negative or truncated formatting sends no confirmation, while completed POST save/publication is not falsely rolled back')
    return checks


def main():
    checks = load_checks() + save_checks() + http_checks()
    result = dict(passed=True, hardware_operation=False, check_count=len(checks), checks=checks,
                  elf_sha256=hashlib.sha256(http.ELF.read_bytes()).hexdigest(),
                  test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  http_model_sha256=hashlib.sha256(Path(http.__file__).read_bytes()).hexdigest(),
                  context_bytes=224, settings_record_bytes=16,
                  limitations='Actual linked ARM runs with mocked file/mount/errno/lock/socket APIs. Real FAT/MMC flush durability, OS latency, LCD, SMP and cold boot remain unverified.')
    output = Path(os.environ.get('PANEL_SETTINGS_TEST_OUTPUT',
                                http.ROOT / 'build/reviews/settings-arm-offline-result.json'))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
