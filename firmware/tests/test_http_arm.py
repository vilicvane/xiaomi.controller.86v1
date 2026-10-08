"""Run HTTP/GUI and original PNG/JPEG ARM instructions without hardware.

Historical Machine helpers are imported without their result writers. Native
OS boundaries are mocked, not image decoding. Native RPC latency, real
scheduling, locks, heap availability and LCD timing remain unestablished.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[2]
TEST_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
sys.path.insert(0, str(ROOT / 'analysis/image-push'))
import test_native_image_drawer_arm as previous
from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_BLOCK
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR,
    UC_CPU_ARM_CORTEX_A7, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC)

ELF = Path(os.environ.get('PANEL_FIRMWARE_ELF', ROOT / 'build/panel/panel.elf'))
previous.smooth.original.old.ELF = ELF
CTX, PIXELS, IMAGE, RECEIVE, ERROR, STOP = (previous.CTX, previous.PIXELS,
    previous.IMAGE, previous.RECEIVE, previous.ERROR, previous.STOP)
HEADER, SCRATCH, REQUEST = 0x38720000, 0x38722000, 0x38723000
HEAP, WORKER_SP, WORKER_STACK_BYTES = 0x38a00000, 0x389cff00, 16384
MAX_IMAGE_BYTES = 1048576
FIXTURES = ROOT / 'build/compression-research/direct-image-fixtures-20261008/fixtures'
ORIGINAL = (ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
ORIGINAL_SHA = '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
assert hashlib.sha256(ORIGINAL).hexdigest() == ORIGINAL_SHA
STOCK_A7 = ORIGINAL[0x8e0004:0xdd3fe4]
F = dict(previous.F, show_address=204, screen_off=144,
         return_after_ms=212, activity_ms=216, activity_valid=220)
GUARD = bytes([0xa7]) * 128
FRONTEND = os.environ.get('PANEL_TEST_FRONTEND_URL', '')
ORIGIN = os.environ.get('PANEL_TEST_FRONTEND_ORIGIN', '*')
CODEC_EVIDENCE = []
_previous_uc = previous.smooth.original.old.Uc


def a7_emulator(*args, **kwargs):
    # Unicorn fixes the CPU model on first memory operation, before the
    # historical harness reaches _install_hooks. Keep its helpers unchanged.
    uc = _previous_uc(*args, **kwargs)
    uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A7)
    uc.reg_write(UC_ARM_REG_C1_C0_2, 0xf00000)
    uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    return uc


previous.smooth.original.old.Uc = a7_emulator


def request(method='GET', path='/', fields=(), version='1.1'):
    lines = [f'{method} {path} HTTP/{version}', 'Host: panel.invalid']
    return ('\r\n'.join(lines + list(fields)) + '\r\n\r\n').encode()


def upload(payload, checksum=None, content_type='application/octet-stream'):
    fields = (() if content_type is None else ('Content-Type: ' + content_type,)) + ('Content-Length: 307216',)
    header = struct.pack('<4sHHII', b'VIMG', 480, 320, len(payload),
                         previous.fnv(payload) if checksum is None else checksum)
    return request('POST', '/api/image', fields), header, payload


class Machine(previous.Machine):
    def __init__(self, fail_allocation=0, **options):
        self.ip_family = 2
        self.ip_queries = 0
        self.receive_calls = []
        self.send_calls = []
        self.format_calls = []
        self.send_delay = 0
        self.before_receive = None
        self.lock_fail_calls = set()
        self.lock_calls = 0
        self.file_calls = []
        self.heap_live = {}
        self.heap_next = HEAP
        self.heap_attempts = 0
        self.heap_fail_at = fail_allocation
        self.heap_peak = 0
        self.heap_events = []
        self.minimum_worker_sp = WORKER_SP
        self.create_calls = []
        super().__init__(**options)
        self.allocations = [HEADER]
        for address in (HEADER - 128, HEADER + 2048, PIXELS - 128,
                        RECEIVE + 307200, WORKER_SP - WORKER_STACK_BYTES - 128):
            self.uc.mem_write(address, GUARD)
        self.native_code_hash = hashlib.sha256(self.uc.mem_read(0x38000000, 0x4e0000)).hexdigest()

    def f(self, name, value=None):
        return self.field(F[name], value)

    def _graph(self):
        super()._graph()
        self.uc.mem_write(CTX + 128, bytes(20))
        self.uc.mem_write(CTX + 212, bytes(12))
        self.word(0x384ea638, 1)

    def _install_hooks(self):
        # The historical harness loads project ELF only. Native codecs require
        # the verified stock A7 first, with current allocated sections reloaded.
        self.uc.mem_write(0x38000000, STOCK_A7)
        with ELF.open('rb') as stream:
            for section in ELFFile(stream).iter_sections():
                if section['sh_flags'] & 2 and section['sh_size']:
                    self.uc.mem_write(section['sh_addr'], section.data())
        super()._install_hooks()
        self.hook(0x380051ec, lambda: self.ret(0))  # getenv OS boundary
        self.hook(0x38018c30, lambda: (_ for _ in ()).throw(AssertionError('stack protector')))
        self.uc.hook_add(UC_HOOK_BLOCK, lambda uc, address, size, data: self.observe_stack())
        for address, method in ((0x3802c900, self.file_open),
                                (0x3802954c, self.file_read),
                                (0x3802b378, self.file_write),
                                (0x3802b3ec, self.file_sync)):
            self.hook(address, method)

    def observe_stack(self):
        sp = self.uc.reg_read(UC_ARM_REG_SP)
        if WORKER_SP - 0x10000 <= sp <= WORKER_SP:
            self.minimum_worker_sp = min(self.minimum_worker_sp, sp)
            assert sp >= WORKER_SP - WORKER_STACK_BYTES, 'Worker exceeds requested16KiB stack'

    def allocate(self):
        assert not self.locks, 'Heap allocation while GUI locked'
        size = self.uc.reg_read(UC_ARM_REG_R0)
        assert 0 < size <= 2 * MAX_IMAGE_BYTES, size
        self.heap_attempts += 1
        if self.heap_attempts == self.heap_fail_at:
            self.heap_events.append({'failed': size})
            self.ret(0)
            return
        if self.allocations:
            pointer = self.allocations.pop(0)
            if not pointer:
                self.heap_events.append({'failed': size})
                self.ret(0)
                return
            assert (pointer, size) in ((HEADER, 2048), (CTX, 224), (PIXELS, 1843200))
        else:
            pointer = self.heap_next + 128
            self.heap_next = pointer + ((size + 15) & ~15) + 128
            assert self.heap_next < ERROR - 128, 'Dynamic heap overlaps errno'
        assert pointer not in self.heap_live
        self.heap_live[pointer] = size
        self.heap_peak = max(self.heap_peak, sum(self.heap_live.values()))
        self.uc.mem_write(pointer - 128, GUARD)
        self.uc.mem_write(pointer, bytes(size))
        self.uc.mem_write(pointer + size, GUARD)
        self.heap_events.append({'allocated': size})
        self.ret(pointer)

    def free(self):
        assert not self.locks, 'Heap free while GUI locked'
        pointer = self.uc.reg_read(UC_ARM_REG_R0)
        if pointer:
            size = self.heap_live.pop(pointer)
            assert bytes(self.uc.mem_read(pointer - 128, 128)) == GUARD
            assert bytes(self.uc.mem_read(pointer + size, 128)) == GUARD
            self.freed.append(pointer)
            self.heap_events.append({'freed': size})
        self.ret(0)

    def file_open(self):
        r = self.uc.reg_read
        assert not self.locks, 'File open while GUI locked'
        assert r(UC_ARM_REG_SP) % 8 == 0
        path = self.string(r(UC_ARM_REG_R0))
        assert path in ('/data/86v1-return.0', '/data/86v1-return.1')
        assert (r(UC_ARM_REG_R1), r(UC_ARM_REG_R2)) == (1, 0)
        self.file_calls.append(('open-missing', path))
        self.word(ERROR, 2)
        self.ret(-1)

    def file_getfile(self):
        raise AssertionError('Missing-only filesystem obtained a descriptor')

    def file_read(self):
        raise AssertionError('Missing-only filesystem attempted a read')

    def file_write(self):
        raise AssertionError('Missing-only filesystem attempted a write')

    def file_sync(self):
        raise AssertionError('Missing-only filesystem attempted fsync')

    def file_close(self):
        raise AssertionError('Missing-only filesystem attempted file close')

    def string(self, address):
        data = bytearray()
        while self.byte(address):
            data.append(self.byte(address))
            address += 1
            assert len(data) <= 4096
        return data.decode('ascii')

    def format(self):
        r = self.uc.reg_read
        destination, size, pattern = r(UC_ARM_REG_R0), r(UC_ARM_REG_R1), self.string(r(UC_ARM_REG_R2))
        if size != 24:
            assert not self.locks, 'HTTP response formatting while locked'
        assert r(UC_ARM_REG_SP) % 8 == 0
        args = [r(UC_ARM_REG_R3)] + [self.word(r(UC_ARM_REG_SP) + 4 * i) for i in range(10)]
        output = ''
        arg = 0
        position = 0
        while position < len(pattern):
            if pattern[position] != '%':
                output += pattern[position]
                position += 1
                continue
            kind = pattern[position + 1]
            assert kind in '%usc', pattern
            if kind == '%':
                output += '%'
            else:
                if kind == 'u':
                    output += str(args[arg])
                elif kind == 'c':
                    output += chr(args[arg] & 0xff)
                else:
                    output += self.string(args[arg])
                arg += 1
            position += 2
        self.format_calls.append((pattern, size, tuple(args[:arg])))
        self.printf_calls += 1
        if size:
            self.uc.mem_write(destination, output.encode()[:size - 1] + b'\0')
        self.ret(len(output) if self.printf_result is None else self.printf_result)

    def hook(self, address, method):
        r = self.uc.reg_read
        if address == 0x383d9420:
            return super().hook(address, self.allocate)
        if address == 0x383d93e4:
            return super().hook(address, self.free)
        if address == 0x383acc04:
            def create():
                attributes = r(UC_ARM_REG_R1)
                assert attributes and bytes(self.uc.mem_read(attributes, 16)) == struct.pack('<IIII', 0x00010064, 0, 0, WORKER_STACK_BYTES)
                assert r(UC_ARM_REG_R2) == self.symbols['bootstrap']
                assert r(UC_ARM_REG_R3) == CTX
                self.create_calls.append({'attributes': attributes, 'stack_bytes': WORKER_STACK_BYTES})
                self.ret(self.create_result)
            return super().hook(address, create)
        if address in (0x38025678, 0x38025de0):
            def descriptor():
                if r(UC_ARM_REG_R0) >= 20:
                    (self.file_getfile if address == 0x38025678 else self.file_close)()
                else:
                    method()
            return super().hook(address, descriptor)
        if address == 0x3801a418:
            return super().hook(address, self.format)
        if address == 0x38025c40:
            def ioctl():
                assert not self.locks
                assert (r(UC_ARM_REG_R0), r(UC_ARM_REG_R1)) == (11, 0x701)
                pointer = r(UC_ARM_REG_R2)
                assert pointer % 4 == 0
                assert bytes(self.uc.mem_read(pointer, 40)) == b'wlan0\0' + bytes(34)
                self.ip_queries += 1
                self.io.append('ioctl')
                if not self.ip_result:
                    self.word(pointer + 20, self.ip_family)
                    self.word(pointer + 24, self.ip_value)
                self.ret(self.ip_result)
            return super().hook(address, ioctl)
        if address in (0x38179784, 0x381798a0):
            def transfer():
                assert r(UC_ARM_REG_R0) == 12
                assert r(UC_ARM_REG_SP) % 8 == 0
                pointer, size, flags = r(UC_ARM_REG_R1), r(UC_ARM_REG_R2), r(UC_ARM_REG_R3)
                assert flags == 0x40 and size > 0
                if address == 0x38179784:
                    if self.before_receive:
                        self.before_receive(self)
                    # Six-argument recvfrom ABI: address/address-length are both null.
                    assert self.word(r(UC_ARM_REG_SP)) == self.word(r(UC_ARM_REG_SP) + 4) == 0
                    self.receive_calls.append((pointer, size, flags))
                    if HEADER <= pointer < HEADER + 2048:
                        assert pointer + size <= HEADER + 2048
                    if RECEIVE <= pointer < RECEIVE + 307200:
                        assert pointer + size <= RECEIVE + 307200
                    if HEAP <= pointer < ERROR:
                        block = next((base, length) for base, length in self.heap_live.items()
                                     if base <= pointer < base + length)
                        assert pointer + size <= block[0] + block[1]
                else:
                    self.now += self.send_delay
                    self.send_calls.append((pointer, size, flags))
                method()
            return super().hook(address, transfer)
        if address == 0x3800da2c:
            def lock():
                self.lock_calls += 1
                if self.lock_calls in self.lock_fail_calls:
                    self.ret(-1)
                else:
                    method()
            return super().hook(address, lock)
        return super().hook(address, method)

    def worker(self):
        if self.worker_saved is None:
            self.uc.reg_write(UC_ARM_REG_SP, WORKER_SP)
            self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
            self.uc.reg_write(UC_ARM_REG_R0, CTX)
            pc = self.symbols['panel_server'] | 1
        else:
            self.uc.context_restore(self.worker_saved)
            pc = self.uc.reg_read(UC_ARM_REG_PC) | 1
        self.uc.emu_start(pc, STOP, count=100000000)
        assert not self.locks
        self.worker_saved = self.uc.context_save()
        self.guards()
        return self.uc.reg_read(UC_ARM_REG_PC) == STOP

    def guards(self):
        for address in (HEADER - 128, HEADER + 2048, PIXELS - 128,
                        RECEIVE + 307200, WORKER_SP - WORKER_STACK_BYTES - 128):
            assert bytes(self.uc.mem_read(address, 128)) == GUARD, hex(address)
        for pointer, size in self.heap_live.items():
            assert bytes(self.uc.mem_read(pointer - 128, 128)) == GUARD, hex(pointer)
            assert bytes(self.uc.mem_read(pointer + size, 128)) == GUARD, hex(pointer)

    def codec_cleanup(self):
        assert self.heap_live == {HEADER: 2048}, self.heap_live
        self.guards()
        assert hashlib.sha256(self.uc.mem_read(0x38000000, 0x4e0000)).hexdigest() == self.native_code_hash

    def response(self, status, body=None, settings=False, image_capability=False):
        header, separator, received = bytes(self.sent).partition(b'\r\n\r\n')
        assert separator, (status, bytes(self.sent))
        lines = header.decode('ascii').split('\r\n')
        assert lines[0] == f'HTTP/1.1 {status} '
        fields = dict(line.split(': ', 1) for line in lines[1:])
        assert fields['Connection'] == 'close'
        assert int(fields['Content-Length']) == len(received)
        assert fields['Content-Type'] == ('application/json' if settings or image_capability else 'text/plain; charset=utf-8')
        assert fields['Cache-Control'] == 'no-store'
        assert fields['Access-Control-Allow-Origin'] == ORIGIN
        assert fields['Access-Control-Allow-Methods'] == 'GET, POST'
        assert fields['Access-Control-Allow-Headers'] == 'Content-Type'
        assert fields['Allow'] == 'GET, POST, OPTIONS'
        if body is not None:
            assert received == body
        elif status != 200:
            assert not received
        assert 12 in self.closed and not self.locks
        assert 11 not in self.closed or not self.f('alive')
        self.guards()
        return fields, received

    def exact(self, data, events, sending=False):
        self.uc.mem_write(SCRATCH, data)
        self.receives = [] if sending else list(events)
        self.sends = list(events) if sending else []
        self.uc.reg_write(UC_ARM_REG_SP, 0x389eff00)
        self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
                              (12, SCRATCH, len(data), self.now & 0xffffffff)):
            self.uc.reg_write(reg, value)
        self.word(0x389eff00, int(sending))
        pc = self.symbols['panel_exact'] | 1
        for _ in range(2000):
            self.uc.emu_start(pc, STOP, count=30000000)
            if self.uc.reg_read(UC_ARM_REG_PC) == STOP:
                break
            pc = self.uc.reg_read(UC_ARM_REG_PC) | 1
        else:
            raise AssertionError('exact transfer did not finish')
        result = self.uc.reg_read(UC_ARM_REG_R0)
        assert not self.locks
        return result


def parser_checks():
    checks = []
    cases = [
        (request(), 0),
        (b'GET / HTTP/1.0\r\n\r\n', 0),
        (request('POST', '/api/image', ('Content-Length: 307216', 'Content-Type: APPLICATION/OCTET-STREAM')), 0),
        (request('OPTIONS', '/api/image'), 0),
        (request('GET', '/api/image'), 0),
        (request('GET', '/api/settings'), 0),
        (request('OPTIONS', '/api/settings'), 0),
        (request('POST', '/api/settings', ('Content-Length: 1',)), 0),
        (request('POST', '/api/settings', ('Content-Length: 64',)), 0),
        (request('POST', '/api/settings', ('Content-Length: 65',)), 413),
        (request('POST', '/api/settings', ('Content-Length: 0',)), 400),
        (request('POST', '/api/settings'), 411),
        (request('PUT', '/api/image'), 405),
        (request('GET', '/missing'), 404),
        (request('POST', '/api/image'), 411),
        (request('POST', '/api/image', ('Content-Length: 307217',)), 0),
        (request('POST', '/api/image', ('Content-Length: 307215',)), 0),
        (request('POST', '/api/image', ('Content-Length: 1',)), 0),
        (request('POST', '/api/image', ('Content-Length: 1048576',)), 0),
        (request('POST', '/api/image', ('Content-Length: 1048577',)), 413),
        (request('POST', '/api/image', ('Content-Length: 0',)), 400),
        (request('POST', '/api/image', ('Content-Length: 1', 'Content-Encoding: identity')), 0),
        (request('POST', '/api/image', ('Content-Length: 1', 'cOnTeNt-EnCoDiNg: IDENTITY')), 0),
        (request('POST', '/api/image', ('Content-Length: 1', 'Content-Encoding: gzip')), 415),
        (request('POST', '/api/image', ('Content-Length: 1', 'Content-Encoding: deflate')), 415),
        (request('POST', '/api/image', ('Content-Length: 1', 'Content-Encoding:')), 415),
        (request('POST', '/api/image', ('Content-Length: 307216',)), 0),
        (request('POST', '/api/image', ('Content-Length: 307216', 'Content-Type: application/x-www-form-urlencoded')), 0),
        (request('POST', '/api/image', ('Content-Length: 307216', 'Content-Type: text/plain')), 0),
        (request('POST', '/api/image', ('Content-Length: 307216', 'Content-Type:')), 0),
        (request('POST', '/api/image', ('Content-Length: 307216', 'Content-Type: text/plain', 'content-type: application/octet-stream')), 0),
        (request('POST', '/api/image', ('Content-Length: 307216', 'Content-Type: a\x01b')), 400),
        (request(fields=('Expect: 100-continue',)), 417),
        (request(fields=('Transfer-Encoding: chunked',)), 400),
        (request(fields=('Content-Length: 0', 'Content-Length: 0')), 400),
        (request(fields=('Content-Length: +0',)), 400),
        (request(fields=('Content-Length: 4294967296',)), 400),
        (request(fields=('Host: duplicate.invalid',)), 400),
        (request(fields=(' Content-Length: 0',)), 400),
        (b'GET / HTTP/1.1\r\n\r\n', 400),
        (request(version='2.0'), 400),
        (request(fields=('Bad Header: x',)), 400),
        (request(fields=('X-Control: \x01',)), 400),
    ]
    m = Machine()
    for data, status in cases:
        m.uc.mem_write(SCRATCH, data)
        m.uc.mem_write(REQUEST, bytes([0x5a]) * 12)
        m.uc.mem_write(REQUEST + 12, GUARD)
        assert m.call('panel_http_header_end', SCRATCH, len(data)) == len(data)
        assert m.call('panel_http_parse', SCRATCH, len(data), REQUEST) == status
        if status:
            assert bytes(m.uc.mem_read(REQUEST, 12)) == bytes([0x5a]) * 12
        else:
            method, length, resource = struct.unpack('<III', m.uc.mem_read(REQUEST, 12))
            first = data.split(b'\r\n', 1)[0].split()
            assert method == {b'GET': 1, b'POST': 2, b'OPTIONS': 3}[first[0]]
            assert resource == {b'/': 0, b'/api/image': 1, b'/api/settings': 2}[first[1]]
            content_lengths = [line.split(b':', 1)[1].strip() for line in data.split(b'\r\n')
                               if line.split(b':', 1)[0].lower() == b'content-length']
            assert length == (int(content_lengths[0]) if content_lengths else 0)
        assert bytes(m.uc.mem_read(REQUEST + 12, 128)) == GUARD
    checks.append('Actual ARM parser accepts GET image capability and image ContentLength1..1048576, ignores Content-Type, rejects nonidentity Content-Encoding415, and preserves method/path/Host/TE/Expect/control/output-mutation boundaries')
    valid = request()
    for size in range(len(valid)):
        m.uc.mem_write(SCRATCH, valid[:size])
        assert m.call('panel_http_header_end', SCRATCH, size) == 0
    padding = 2048 - len(request(fields=('X-Padding: ',)))
    limit = request(fields=('X-Padding: ' + 'a' * padding,))
    assert len(limit) == 2048
    m.uc.mem_write(SCRATCH, limit)
    assert m.call('panel_http_parse', SCRATCH, 2048, REQUEST) == 0
    m.uc.mem_write(SCRATCH, limit[:-4] + b'a\r\n\r\n')
    assert m.call('panel_http_parse', SCRATCH, 2049, REQUEST) == 431
    checks.append('ARM header finder accepts no truncated prefix; exact2048-byte header passes and2049-byte parser input returns431 without output mutation')
    return checks


def response_checks():
    checks = []
    m = Machine().ready()
    m.transact([request()])
    fields, body = m.response(303 if FRONTEND else 200)
    assert m.allocation_sizes == [2048]
    assert m.f('ipv4') == 0x070200c0 and m.f('server_error') == 0
    if FRONTEND:
        separator = '&' if '?' in FRONTEND else '?'
        assert fields['Location'] == FRONTEND + separator + 'device=http%3A%2F%2F192.0.2.7%3A18086'
        assert not body
    else:
        assert b'Frontend URL is not configured.' in body and b'POST /api/image' in body
        assert 'Location' not in fields
    checks.append('GET uses build-configured redirect with percent-encoded endpoint query or explicit unconfigured200; exact response length/close/no-store/CORS and2048B heap verified')
    m = Machine().ready()
    m.transact([request('OPTIONS', '/api/image', ('Origin: https://frontend.invalid', 'Access-Control-Request-Method: POST'))])
    m.response(204)
    assert not m.f('image_pending') and not m.f('generation')
    checks.append('Browser OPTIONS returns204 without publishing pixels; CORS derives from configured origin rather than reflecting requester')

    m = Machine().ready().custom()
    before = tuple(m.f(name) for name in ('image', 'receive', 'image_pending', 'generation', 'displayed_generation'))
    slots = bytes(m.uc.mem_read(IMAGE, 614400))
    m.transact([request('GET', '/api/image')])
    m.response(200, b'{"formats":["png","jpeg","vimg"]}\n', image_capability=True)
    assert tuple(m.f(name) for name in ('image', 'receive', 'image_pending', 'generation', 'displayed_generation')) == before
    assert bytes(m.uc.mem_read(IMAGE, 614400)) == slots
    m.codec_cleanup()
    checks.append('GET/api/image returns exact PNG/JPEG/VIMG capability JSON with application/json, close/no-store/CORS, without image-slot/pending/generation mutation or transient allocation')

    cases = [
        (request('PUT', '/'), 405),
        (request('POST', '/api/image'), 411),
        (request('POST', '/api/image', ('Content-Length: 1048577',)), 413),
        (request('POST', '/api/image', ('Content-Length: 0',)), 400),
        (request('POST', '/api/image', ('Content-Length: 1', 'Content-Encoding: gzip')), 415),
        (request('POST', '/api/image', ('Content-Length: 307216', 'Content-Type: a\x01b')), 400),
        (request(fields=('Expect: 100-continue',)), 417),
        (request(fields=('Transfer-Encoding: identity',)), 400),
        (request(fields=('Content-Length: 0', 'content-length: 0')), 400),
        (request(fields=('Content-Length: -1',)), 400),
        (b'x' * 2048, 431),
        (request(fields=('X-Padding: ' + 'a' * 2048,)), 431),
    ]
    for data, status in cases:
        m = Machine().ready()
        m.transact([data])
        m.response(status)
        assert not m.f('image_pending') and not m.f('generation')
        assert m.f('server_error') == status
        assert len(m.receive_calls) == 1
    limit = request(fields=('X-Padding: ' + 'a' * (2048 - len(request(fields=('X-Padding: ',)))),))
    m = Machine().ready()
    m.transact([limit[:100], ('error', 4), limit[100:]], [3, ('error', 11), 5, ('error', 4), 7])
    m.response(303 if FRONTEND else 200)
    checks.append('Every HTTP rejection status is sent before body receive; overlong/nonterminated headers431 and exact2048 split header survives EINTR/partial sends/EAGAIN')

    for events in ([0], [b'GET / HTTP/1.1\r\n', 0], [('error', 5)]):
        m = Machine().ready()
        m.transact(events)
        m.response(400)
    m = Machine().ready()
    m.transact([('error', 11)] * 300)
    m.response(408)
    assert 5000 <= m.now - 1000 < 5100
    m = Machine().ready()
    m.read_delay = 1000
    m.transact([b'G'] * 40)
    m.response(408)
    assert 30000 <= m.now - 1000 < 32000
    checks.append('Header EOF/terminal error returns400; private-clock idle5s and connection-wide30s return408 even with trickle progress')
    for failure_offset, status in ((2, 503), (3, 408)):
        m = Machine().ready()
        m.fail_clock_calls.add(m.clock_calls + failure_offset)
        m.transact([request()])
        m.response(status)
    checks.append('Initial connection CLOCK failure returns503; failed header CLOCK returns408 and cannot weaken deadlines')

    for events in ([0], [('error', 5)], [('error', 11)] * 300):
        m = Machine().ready()
        m.transact([request()], events)
        assert not m.sent and 12 in m.closed
        assert not m.f('image_pending')
    for value in (-1, 2048):
        m = Machine().ready()
        m.printf_result = value
        m.transact([request()])
        assert not m.sent and not m.send_calls and 12 in m.closed
    checks.append('Response send EOF/error/idle and snprintf negative/truncated returns close client without overrun; no complete-response promise on send failure')
    return checks


def image_checks():
    checks = []
    payload = previous.frame(0x07e0)
    http, binary, data = upload(payload)
    m = Machine().ready().custom()
    before = bytes(m.uc.mem_read(IMAGE, 307200))
    # One socket chunk contains both the whole HTTP header and the VIMG prefix.
    m.transact([http + binary + data[:1000], data[1000:]], [2, ('error', 11), 4, ('error', 4)])
    m.response(202)
    assert m.f('image_pending') == 1 and m.f('image') == IMAGE
    assert bytes(m.uc.mem_read(IMAGE, 307200)) == before
    assert bytes(m.uc.mem_read(RECEIVE, 307200)) == payload
    assert m.f('generation') == 1 and m.f('displayed_generation') == 0
    m.tick(ms=0)
    assert m.f('image') == RECEIVE and m.f('receive') == IMAGE and not m.f('image_pending')
    assert m.f('generation') == m.f('displayed_generation') == 2
    assert bytes(m.uc.mem_read(PIXELS, 614400)) == struct.pack('<I', previous.rgb(0x07e0)) * 153600
    m.guards()
    checks.append('Coalesced HTTP/VIMG/body preserves cached binary bytes; FNV-valid307200B publishes owned receive slot only, then GUI atomically swaps and renders exactRGB32 without guard damage')

    for content_type in (None, 'application/x-www-form-urlencoded', 'text/plain', ''):
        http_variant, binary_variant, data_variant = upload(payload, content_type=content_type)
        m_variant = Machine().ready().custom()
        active = bytes(m_variant.uc.mem_read(IMAGE, 307200))
        m_variant.transact([http_variant + binary_variant, data_variant])
        m_variant.response(202)
        assert m_variant.f('image_pending') == 1 and m_variant.f('image') == IMAGE
        assert bytes(m_variant.uc.mem_read(IMAGE, 307200)) == active
        assert bytes(m_variant.uc.mem_read(RECEIVE, 307200)) == payload
        m_variant.tick(ms=0)
        assert m_variant.f('image') == RECEIVE and not m_variant.f('image_pending')
        assert m_variant.f('generation') == m_variant.f('displayed_generation') == 2
        assert bytes(m_variant.uc.mem_read(PIXELS, 614400)) == struct.pack('<I', previous.rgb(0x07e0)) * 153600
        m_variant.guards()
    checks.append('Absent Content-Type, curl default form type, explicit text/plain and empty type all accept the same valid VIMG payload with202; actual ARM GUI swaps and renders exact pixels only after admission')

    second = previous.frame(0x001f)
    http2, binary2, _ = upload(second)
    m.closed.clear()
    m.sent.clear()
    m.transact([http2[:5], ('error', 11), http2[5:] + binary2[:3], ('error', 4), binary2[3:15],
                binary2[15:], second[:127], ('error', 11), second[127:]])
    m.response(202)
    assert m.f('image') == RECEIVE and m.f('receive') == IMAGE
    assert bytes(m.uc.mem_read(RECEIVE, 307200)) == payload
    m.tick(ms=0)
    assert m.f('image') == IMAGE and m.f('receive') == RECEIVE and m.f('generation') == 3
    assert bytes(m.uc.mem_read(PIXELS, 614400)) == struct.pack('<I', previous.rgb(0x001f)) * 153600
    checks.append('Fragmented HTTP and split16B VIMG header survive EINTR/EAGAIN; second upload uses opposite owned slot and active first image survives until GUI admission')

    for status, invalid in ((415, b'NOPE' + binary[4:]),
                            (400, struct.pack('<4sHHII', b'VIMG', 481, 320, 307200, 0)),
                            (400, struct.pack('<4sHHII', b'VIMG', 480, 320, 307201, 0))):
        m = Machine().ready().custom()
        m.transact([http + invalid])
        m.response(status)
        assert not m.f('image_pending')
        assert bytes(m.uc.mem_read(RECEIVE, 307200)) == previous.frame(0x001f)
    m = Machine().ready().custom()
    m.transact([http + binary, previous.frame(0x001f)])
    m.response(422)
    assert not m.f('image_pending') and m.f('image') == IMAGE
    checks.append('Unknown signature415 and invalid VIMG dimensions/pixel length400 reject before body write; independently wrong FNV422 cannot replace active image')

    for length in (307215, 307217):
        m = Machine().ready().custom()
        m.transact([request('POST', '/api/image', (f'Content-Length: {length}',)) + binary])
        m.response(400)
        assert not m.f('image_pending') and m.f('generation') == 1
        m.codec_cleanup()
    checks.append('Generic parser accepts lengths around old fixed body size; VIMG handler independently rejects any encoded body length except307216 before payload mutation')

    for content_type in (None, 'application/x-www-form-urlencoded'):
        http_variant, binary_variant, _ = upload(payload, content_type=content_type)
        for status, events in (
            (415, [http_variant + b'NOPE' + binary_variant[4:]]),
            (422, [http_variant + binary_variant, previous.frame(0x001f)]),
        ):
            rejected = Machine().ready().custom()
            active = bytes(rejected.uc.mem_read(IMAGE, 307200))
            generation = rejected.f('generation')
            displayed = rejected.f('displayed_generation')
            rejected.transact(events)
            rejected.response(status)
            assert rejected.f('server_error') == status and not rejected.f('image_pending')
            assert rejected.f('image') == IMAGE and bytes(rejected.uc.mem_read(IMAGE, 307200)) == active
            assert rejected.f('generation') == generation and rejected.f('displayed_generation') == displayed
    checks.append('Ignoring absent or curl-default Content-Type does not weaken content validation: unknown signature415 and wrong FNV422 preserve active pixels, pending0 and both generation counters')

    for events in ([http + binary[:8], 0], [http + binary, data[:100], 0],
                   [http + binary, data[:100], ('error', 5)]):
        m = Machine().ready().custom()
        m.transact(events)
        m.response(400)
        assert not m.f('image_pending') and m.f('image') == IMAGE
    m = Machine().ready().custom()
    m.transact([http + binary, data[:100]] + [('error', 11)] * 300)
    m.response(400)
    assert not m.f('image_pending') and 5000 <= m.now - 1000 < 5100
    m = Machine().ready().custom()
    m.read_delay = 1000
    m.transact([http + binary] + [data[i:i + 1] for i in range(40)])
    m.response(400)
    assert not m.f('image_pending') and 30000 <= m.now - 1000 < 34000
    checks.append('Short VIMG/body, EOF/error and private-clock body idle/total deadline never publish partial image; body transfer failure400 preserves old active slot')

    m = Machine().ready().custom()
    m.f('receive', 0)
    m.transact([http + binary])
    m.response(503)
    assert not m.f('image_pending')
    m = Machine().ready().custom()
    # Startup settings publication and IP update precede receive-slot acquisition.
    m.lock_fail_calls.add(m.lock_calls + 3)
    m.transact([http + binary])
    m.response(503)
    assert not m.f('image_pending')
    checks.append('Unavailable receive slot or failed slot lock returns503 before payload receive, without lock leak or active image mutation')

    for setting in ('publication_lock', 'dead'):
        m = Machine().ready().custom()
        if setting == 'publication_lock':
            m.lock_fail_calls.add(m.lock_calls + 4)
        else:
            def stop_before_body(machine):
                if len(machine.receive_calls) == 1:
                    machine.f('alive', 0)
            m.before_receive = stop_before_body
        m.transact([http + binary, data])
        m.response(503)
        assert not m.f('image_pending') and m.f('image') == IMAGE
    m = Machine().ready().custom()
    m.fail_clock_calls.add(m.clock_calls + 5)
    m.transact([http + binary, data])
    m.response(400)
    assert not m.f('image_pending') and m.f('image') == IMAGE
    checks.append('Failed publication lock, dead owner and payload CLOCK failure preserve pending0 and active image even after receive has begun')

    m = Machine().ready().custom()
    m.now = 0xfffffff0
    m.transact([http + binary, data])
    m.response(202)
    assert m.f('image_pending')
    checks.append('UINT32 monotonic wrap retains valid HTTP upload deadline and complete-image publication')

    m = Machine().ready().custom()
    m.return_on_empty = False
    m.accepts = [12]
    m.receives = [http + binary, data[:100], ('error', 11)]
    m.worker()
    assert not m.f('image_pending') and m.f('image') == IMAGE
    m.tick(ms=0)
    assert m.f('image') == IMAGE and m.f('generation') == 1
    m.receives = [data[100:]]
    while 12 not in m.closed:
        m.worker()
    m.response(202)
    assert m.f('image_pending')
    m.tick(ms=0)
    assert m.f('image') == RECEIVE and m.f('generation') == 2
    checks.append('GUI can run while worker is paused by socketEAGAIN; incomplete receive slot stays private and only complete resumed upload is admitted')
    return checks


def encoded_request(encoded, content_type=None, declared_length=None):
    fields = [f'Content-Length: {len(encoded) if declared_length is None else declared_length}']
    if content_type is not None:
        fields.append(f'Content-Type: {content_type}')
    return request('POST', '/api/image', fields)


def encoded_events(encoded, fragmented=False, content_type=None):
    http = encoded_request(encoded, content_type)
    if fragmented:
        return [http[:7], ('error', 11), http[7:] + encoded[:3], ('error', 4),
                encoded[3:15], encoded[15:1000], ('error', 11), encoded[1000:]]
    return [http + encoded]


def expanded_pixels(reference):
    return struct.pack('<153600I', *(previous.rgb(value) for value in struct.unpack('<153600H', reference)))


def reject_encoded(name, encoded, status, events=None, fail_allocation=0):
    m = Machine(fail_allocation=fail_allocation).ready().custom()
    active = bytes(m.uc.mem_read(IMAGE, 307200))
    generation = m.f('generation'), m.f('displayed_generation')
    m.transact(encoded_events(encoded) if events is None else events)
    m.response(status)
    assert m.f('image') == IMAGE and m.f('receive') == RECEIVE and not m.f('image_pending')
    assert (m.f('generation'), m.f('displayed_generation')) == generation
    assert bytes(m.uc.mem_read(IMAGE, 307200)) == active
    assert m.f('server_error') == status
    m.codec_cleanup()
    CODEC_EVIDENCE.append({'case': name, 'status': status, 'active_preserved': True,
        'generation_preserved': True, 'transient_heap_cleanup': True,
        'heap_peak_bytes': m.heap_peak, 'allocation_attempts': m.heap_attempts,
        'worker_stack_observed_bytes': WORKER_SP - m.minimum_worker_sp})
    return m


def encoded_image_checks(formats=('png', 'jpeg')):
    checks = []
    names = {'png': ('card-original.png', 'card-rgba-alpha.png'),
             'jpeg': ('card-jpeg-q85.jpg', 'photo-jpeg-q85.jpg')}
    assert formats and set(formats) <= set(names)
    for image_format in formats:
        for fragmented, name in enumerate(names[image_format]):
            encoded = (FIXTURES / name).read_bytes()
            reference = (FIXTURES / (name + '.expected.rgb565')).read_bytes()
            m = Machine().ready().custom()
            before = bytes(m.uc.mem_read(IMAGE, 307200))
            m.transact(encoded_events(encoded, bool(fragmented),
                'application/x-www-form-urlencoded' if fragmented else None))
            m.response(202)
            assert m.f('image_pending') == 1 and m.f('image') == IMAGE
            assert m.f('generation') == 1 and m.f('displayed_generation') == 0
            assert bytes(m.uc.mem_read(IMAGE, 307200)) == before
            assert bytes(m.uc.mem_read(RECEIVE, 307200)) == reference
            m.codec_cleanup()
            m.tick(ms=0)
            assert m.f('image') == RECEIVE and m.f('receive') == IMAGE and not m.f('image_pending')
            assert m.f('generation') == m.f('displayed_generation') == 2
            assert bytes(m.uc.mem_read(PIXELS, 614400)) == expanded_pixels(reference)
            m.codec_cleanup()
            CODEC_EVIDENCE.append({'case': name, 'format': image_format,
                'transfer': 'fragmented/EAGAIN/EINTR' if fragmented else 'coalesced',
                'status': 202, 'encoded_bytes': len(encoded),
                'encoded_sha256': hashlib.sha256(encoded).hexdigest(),
                'rgb565_sha256': hashlib.sha256(reference).hexdigest(),
                'exact_inactive_rgb565': True, 'exact_gui_rgb32': True,
                'active_preserved_until_gui_swap': True, 'transient_heap_cleanup': True,
                'heap_peak_bytes': m.heap_peak, 'allocation_attempts': m.heap_attempts,
                'worker_stack_observed_bytes': WORKER_SP - m.minimum_worker_sp})
            m.f('alive', 0)
            assert m.worker() and not m.heap_live
        checks.append(f'Actual ARM HTTP→stock {image_format.upper()} decoder handles coalesced and fragmented/EAGAIN/EINTR binary input without Content-Type; exact RGB565 stays inactive until actual GUI swap/render matches full RGB32 reference; encoded/native heap frees before202')

    if 'png' in formats:
        png = (FIXTURES / 'card-original.png').read_bytes()
        bad_crc = bytearray(png)
        bad_crc[29] ^= 1
        position, idats = 8, []
        while position < len(png):
            length, kind = struct.unpack_from('>I4s', png, position)
            if kind == b'IDAT':
                idats.append((position, length))
            position += length + 12
        last_idat, idat_bytes = idats[-1]
        bad_idat_crc = bytearray(png)
        bad_idat_crc[last_idat + 8 + idat_bytes] ^= 1
        bad_adler = bytearray(png)
        bad_adler[last_idat + 8 + idat_bytes - 1] ^= 1
        struct.pack_into('>I', bad_adler, last_idat + 8 + idat_bytes,
                         zlib.crc32(bad_adler[last_idat + 4:last_idat + 8 + idat_bytes]))
        for name, malformed in (
            ('png-bad-IHDR-CRC', bytes(bad_crc)),
            ('png-bad-IDAT-CRC', bytes(bad_idat_crc)),
            ('png-bad-Adler-with-valid-chunk-CRC', bytes(bad_adler)),
            ('png-no-IEND', png[:-12]),
            ('png-truncated-IDAT', png[:len(png) // 2]),
            ('png-trailing', png + b'extra'),
            ('png-second-image', png + png),
        ):
            reject_encoded(name, malformed, 422)
        checks.append('Bad PNG IHDR/IDAT CRC, independently bad Adler with valid chunkCRC, missing IEND, truncated IDAT, trailing bytes and a concatenated second PNG return422 without active/pending/generation changes; native/encoded cleanup and guards remain intact')
        for name, fail_at in (('png-encoded-OOM', 2), ('png-native-initial-OOM', 3)):
            reject_encoded(name, png, 503, fail_allocation=fail_at)
        checks.append('Encoded-buffer allocation failure and first PNG decoder allocation failure return503, free any transient heap and preserve the old active image')
        for name, events in (
            ('png-body-EOF', [encoded_request(png) + png[:100], 0]),
            ('png-body-error', [encoded_request(png) + png[:100], ('error', 5)]),
            ('png-body-idle', [encoded_request(png) + png[:100]] + [('error', 11)] * 300),
        ):
            reject_encoded(name, png, 400, events=events)
        checks.append('PNG transport truncation, terminal error and idle deadline return400 before decoding/publication, freeing the complete-size encoded allocation and preserving active pixels')

    if 'jpeg' in formats:
        jpeg = (FIXTURES / 'card-jpeg-q85.jpg').read_bytes()
        for name, malformed in (
            ('jpeg-invalid-markers', b'\xff\xd8invalid-jpeg\xff\xd9'),
            ('jpeg-no-EOI', jpeg[:-2]),
            ('jpeg-truncated', jpeg[:len(jpeg) // 2]),
            ('jpeg-truncated-with-EOI', jpeg[:len(jpeg) // 2] + b'\xff\xd9'),
            ('jpeg-trailing', jpeg + b'extra'),
        ):
            reject_encoded(name, malformed, 422)
        checks.append('Bad JPEG markers, missing EOI, truncation including a physical EOI and trailing data return422 rather than accepting synthetic EOI/warnings; active image and generations remain unchanged')
        for name, fail_at in (('jpeg-encoded-OOM', 2), ('jpeg-native-initial-OOM', 3)):
            reject_encoded(name, jpeg, 503, fail_allocation=fail_at)
        checks.append('Encoded-buffer and first JPEG decoder allocation failures return503 with complete transient cleanup and no pending publication')

    if set(formats) == {'png', 'jpeg'}:
        m = Machine().ready().custom()
        for index, name in enumerate(('card-original.png', 'card-jpeg-q85.jpg', 'card-rgba-alpha.png')):
            encoded = (FIXTURES / name).read_bytes()
            reference = (FIXTURES / (name + '.expected.rgb565')).read_bytes()
            active, receive = m.f('image'), m.f('receive')
            before = bytes(m.uc.mem_read(active, 307200))
            generation = m.f('generation')
            m.sent.clear()
            m.closed.clear()
            m.transact(encoded_events(encoded, fragmented=bool(index & 1)))
            m.response(202)
            assert m.f('image') == active and m.f('receive') == receive and m.f('image_pending')
            assert m.f('generation') == generation
            assert bytes(m.uc.mem_read(active, 307200)) == before
            assert bytes(m.uc.mem_read(receive, 307200)) == reference
            m.codec_cleanup()
            m.tick(ms=0)
            assert m.f('image') == receive and m.f('receive') == active and not m.f('image_pending')
            assert m.f('generation') == m.f('displayed_generation') == generation + 1
            assert bytes(m.uc.mem_read(PIXELS, 614400)) == expanded_pixels(reference)
            m.codec_cleanup()
        m.f('alive', 0)
        assert m.worker() and not m.heap_live
        CODEC_EVIDENCE.append({'case': 'png-jpeg-png-same-worker', 'status': 202,
            'uploads': 3, 'exact_inactive_rgb565': True, 'exact_gui_rgb32': True,
            'active_preserved_until_gui_swap': True, 'transient_heap_cleanup': True,
            'heap_peak_bytes': m.heap_peak, 'allocation_attempts': m.heap_attempts,
            'worker_stack_observed_bytes': WORKER_SP - m.minimum_worker_sp})
        checks.append('PNG→JPEG→PNG on the same HTTP worker alternates both owned image slots, produces exact GUI frames, advances generation once per admission and leaves no decoder state or transient allocations between requests')
    return checks


def exact_checks():
    checks = []
    for sending in (False, True):
        m = Machine()
        events = [2, ('error', 11), 1, ('error', 4), 3] if sending else [b'ab', ('error', 11), b'c', ('error', 4), b'def']
        assert m.exact(b'abcdef', events, sending) == 0
        assert bytes(m.sent) == b'abcdef' if sending else bytes(m.uc.mem_read(SCRATCH, 6)) == b'abcdef'
        assert m.sleep_calls == 2
        for events in ([0], [('error', 5)], [('error', 11)] * 300):
            m = Machine()
            assert m.exact(b'ab', events, sending) == 0xffffffff
        m = Machine()
        m.clock_result = -1
        assert m.exact(b'ab', (), sending) == 0xffffffff
        assert not m.receive_calls and not m.send_calls
        m = Machine()
        m.fail_clock_calls.add(2)
        assert m.exact(b'ab', (), sending) == 0xffffffff
        m = Machine()
        if sending:
            m.send_delay = 1000
        else:
            m.read_delay = 1000
        progress = [1] * 40 if sending else [b'a'] * 40
        assert m.exact(b'a' * 40, progress, sending) == 0xffffffff
        assert 30000 <= m.now - 1000 < 32000
    checks.append('Direct actualARM exact receive/send honor six/four-argument nonblockingABI, partial progress/EAGAIN/EINTR, EOF/error/idle and both initialization/loop clock failures')
    m = Machine()
    m.receives = [1 << 20]
    assert m.call5('panel_exact', 12, SCRATCH, 3, m.now, 0) == 0xffffffff
    m = Machine()
    assert m.exact(b'', (), False) == 0
    assert not m.receive_calls and not m.send_calls
    checks.append('Native recv returning more than requested is rejected; zero-byte exact operation invokes no socket transfer')
    return checks


def server_checks():
    checks = []
    m = Machine()
    m.allocations = [CTX, PIXELS]
    m.create_result = -1
    assert m.call('broker_main', 2, 0x389d0200) == 17
    assert len(m.create_calls) == 1 and m.create_calls[0]['stack_bytes'] == WORKER_STACK_BYTES
    assert m.allocation_sizes == [224, 1843200] and m.freed == [PIXELS, CTX]
    assert not m.heap_live and m.word(0x384fc864) == 0
    checks.append('Actual ARM CREATE passes image-specific16B default pthread scheduling attributes with explicit16384B worker stack; create rejection unwinds both owned allocations')
    for setting, value, error in (('socket_result', -1, 1), ('bind_result', -1, 2), ('listen_result', -1, 2)):
        m = Machine().ready()
        setattr(m, setting, value)
        assert m.worker() and m.f('server_error') == error
        assert m.allocation_sizes == [2048] and m.freed == [HEADER]
        assert m.closed == ([] if setting == 'socket_result' else [11])
    m = Machine().ready()
    m.allocations = [0]
    assert m.worker() and m.f('server_error') == 4
    assert not m.io and not m.freed
    checks.append('Header heap/socket/bind/listen failures unwind exactly owned2048B allocation and established descriptor; GUI remains untouched')

    m = Machine().ready()
    m.return_on_empty = False
    m.worker()
    assert m.f('server_state') == 1 and m.f('server_error') == 0 and m.ip_queries == 1
    m.f('dirty', 0)
    for _ in range(10):
        m.worker()
        assert m.ip_queries == 1 and not m.f('dirty')
    m.now += 1000
    m.worker()
    assert m.ip_queries == 2 and not m.f('dirty')
    m.ip_value = 0x080200c0
    m.now += 1000
    m.worker()
    assert m.f('ipv4') == m.ip_value and m.f('dirty')
    m.f('dirty', 0)
    m.ip_result = -1
    m.now += 1000
    m.worker()
    assert not m.f('ipv4') and m.f('dirty')
    m.f('dirty', 0)
    m.worker()
    assert not m.f('dirty')
    m.ip_result = 0
    m.ip_family = 10
    m.now += 1000
    m.worker()
    assert not m.f('ipv4') and not m.f('dirty')
    m.ip_family = 2
    m.now += 1000
    m.worker()
    assert m.f('ipv4') == m.ip_value and m.f('dirty')
    m.f('image_pending', 1)
    before = len(m.io)
    m.worker()
    assert len(m.io) == before
    m.f('image_pending', 0)
    m.accepts = [-1]
    m.word(ERROR, 5)
    m.worker()
    assert m.f('server_error') == 3
    m.f('alive', 0)
    assert m.worker()
    assert m.f('server_state') == 0 and m.closed == [11] and m.freed == [HEADER]
    checks.append('Exact40B wlan0 ifreq refresh occurs outside lock initially and at nominal monotonic1s intervals; only changed address dirties GUI, stale/invalid IP clears, pending upload blocks next accept, shutdown frees header once')
    m = Machine().ready()
    m.return_on_empty = False
    m.clock_result = -1
    m.worker()
    assert not m.ip_queries and not m.f('dirty')
    m.clock_result = 0
    m.now = 0xffffff80
    m.worker()
    assert m.ip_queries == 1
    m.f('dirty', 0)
    m.now += 999 - 20
    m.worker()
    assert m.ip_queries == 1 and not m.f('dirty')
    m.now += 1
    m.ip_value = 0x090200c0
    m.worker()
    assert m.ip_queries == 2 and m.f('dirty') and m.f('ipv4') == m.ip_value
    checks.append('Failed refresh CLOCK performs no IOCTL, first subsequent valid clock retries; modulo32 wrap still enforces query deadline without dirtying unchanged IP')
    return checks


def main(formats=('png', 'jpeg')):
    checks = parser_checks() + response_checks() + image_checks() + encoded_image_checks(formats) + exact_checks() + server_checks()
    result = {'passed': True, 'hardware_operation': False, 'check_count': len(checks),
        'checks': checks, 'elf_sha256': hashlib.sha256(ELF.read_bytes()).hexdigest(),
        'test_sha256': TEST_SHA,
        'context_bytes': 224, 'header_heap_bytes': 2048, 'image_payload_bytes': 307200,
        'original_nor_sha256': ORIGINAL_SHA, 'stock_native_decoders_executed': list(formats),
        'worker_stack_requested_bytes': WORKER_STACK_BYTES, 'encoded_image_cases': CODEC_EVIDENCE,
        'configured_redirect_tested': bool(FRONTEND), 'configured_cors_tested': ORIGIN != '*',
        'limitations': 'Actual project and original PNG/JPEG ARM instructions execute; allocator/getenv/socket APIs, selected libc formatting/zeroing, locks and GUI driver boundaries are mocked. Worker stack is block-observed with a lower boundary guard on tested paths only. Real RPC timing/OS scheduling/LCD scanout/available heap/cold boot are unchecked.'}
    output = Path(os.environ.get('PANEL_TEST_OUTPUT', ROOT / 'build/reviews/direct-images-http-arm-offline-result.json'))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
