"""Run the maintained HTTP ARM ELF with native APIs mocked, without hardware.

Historical Machine helpers are imported without their result writers. Native
RPC latency, real scheduling, locks, heap availability and LCD timing are not
established by these offline instruction and ownership checks.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'analysis/image-push'))
import test_native_image_drawer_arm as previous
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR)

ELF = Path(os.environ.get('PANEL_FIRMWARE_ELF', ROOT / 'build/panel/panel.elf'))
previous.smooth.original.old.ELF = ELF
CTX, PIXELS, IMAGE, RECEIVE, ERROR, STOP = (previous.CTX, previous.PIXELS,
    previous.IMAGE, previous.RECEIVE, previous.ERROR, previous.STOP)
HEADER, SCRATCH, REQUEST = 0x38720000, 0x38722000, 0x38723000
F = dict(previous.F, show_address=204, screen_off=144)
GUARD = bytes([0xa7]) * 128
FRONTEND = os.environ.get('PANEL_TEST_FRONTEND_URL', '')
ORIGIN = os.environ.get('PANEL_TEST_FRONTEND_ORIGIN', '*')


def request(method='GET', path='/', fields=(), version='1.1'):
    lines = [f'{method} {path} HTTP/{version}', 'Host: panel.invalid']
    return ('\r\n'.join(lines + list(fields)) + '\r\n\r\n').encode()


def upload(payload, checksum=None):
    fields = ('Content-Type: application/octet-stream', 'Content-Length: 307216')
    header = struct.pack('<4sHHII', b'VIMG', 480, 320, len(payload),
                         previous.fnv(payload) if checksum is None else checksum)
    return request('POST', '/api/image', fields), header, payload


class Machine(previous.Machine):
    def __init__(self, **options):
        self.ip_family = 2
        self.ip_queries = 0
        self.receive_calls = []
        self.send_calls = []
        self.format_calls = []
        self.send_delay = 0
        self.before_receive = None
        self.lock_fail_calls = set()
        self.lock_calls = 0
        super().__init__(**options)
        self.allocations = [HEADER]
        for address in (HEADER - 128, HEADER + 2048, PIXELS - 128,
                        RECEIVE + 307200):
            self.uc.mem_write(address, GUARD)

    def f(self, name, value=None):
        return self.field(F[name], value)

    def _graph(self):
        super()._graph()
        self.uc.mem_write(CTX + 128, bytes(20))
        self.word(0x384ea638, 1)

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
            assert kind in '%us', pattern
            if kind == '%':
                output += '%'
            else:
                output += str(args[arg]) if kind == 'u' else self.string(args[arg])
                arg += 1
            position += 2
        self.format_calls.append((pattern, size, tuple(args[:arg])))
        self.printf_calls += 1
        if size:
            self.uc.mem_write(destination, output.encode()[:size - 1] + b'\0')
        self.ret(len(output) if self.printf_result is None else self.printf_result)

    def hook(self, address, method):
        r = self.uc.reg_read
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
            self.uc.reg_write(UC_ARM_REG_SP, 0x389cff00)
            self.uc.reg_write(UC_ARM_REG_LR, STOP | 1)
            self.uc.reg_write(UC_ARM_REG_R0, CTX)
            pc = self.symbols['panel_server'] | 1
        else:
            self.uc.context_restore(self.worker_saved)
            pc = self.uc.reg_read(UC_ARM_REG_PC) | 1
        self.uc.emu_start(pc, STOP, count=30000000)
        assert not self.locks
        self.worker_saved = self.uc.context_save()
        self.guards()
        return self.uc.reg_read(UC_ARM_REG_PC) == STOP

    def guards(self):
        for address in (HEADER - 128, HEADER + 2048, PIXELS - 128, RECEIVE + 307200):
            assert bytes(self.uc.mem_read(address, 128)) == GUARD, hex(address)

    def response(self, status, body=None):
        header, separator, received = bytes(self.sent).partition(b'\r\n\r\n')
        assert separator, (status, bytes(self.sent))
        lines = header.decode('ascii').split('\r\n')
        assert lines[0] == f'HTTP/1.1 {status} '
        fields = dict(line.split(': ', 1) for line in lines[1:])
        assert fields['Connection'] == 'close'
        assert int(fields['Content-Length']) == len(received)
        assert fields['Content-Type'] == 'text/plain; charset=utf-8'
        assert fields['Cache-Control'] == 'no-store'
        assert fields['Access-Control-Allow-Origin'] == ORIGIN
        assert fields['Access-Control-Allow-Methods'] == 'POST'
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
        (request('PUT', '/api/image'), 405),
        (request('GET', '/missing'), 404),
        (request('POST', '/api/image'), 411),
        (request('POST', '/api/image', ('Content-Length: 307217',)), 413),
        (request('POST', '/api/image', ('Content-Length: 307215',)), 400),
        (request('POST', '/api/image', ('Content-Length: 307216',)), 415),
        (request('POST', '/api/image', ('Content-Length: 307216', 'Content-Type: text/plain')), 415),
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
        m.uc.mem_write(REQUEST, bytes([0x5a]) * 8)
        assert m.call('panel_http_header_end', SCRATCH, len(data)) == len(data)
        assert m.call('panel_http_parse', SCRATCH, len(data), REQUEST) == status
        if status:
            assert bytes(m.uc.mem_read(REQUEST, 8)) == bytes([0x5a]) * 8
    checks.append('Actual ARM parser independently matches valid HTTP1.0/1.1 and all method/path/Host/length/type/TE/Expect/control rejection statuses')
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
        assert fields['Location'] == FRONTEND + '#device=http%3A%2F%2F192.0.2.7%3A18086'
        assert not body
    else:
        assert b'Frontend URL is not configured.' in body and b'POST /api/image' in body
        assert 'Location' not in fields
    checks.append('GET uses build-configured redirect with percent-encoded endpoint fragment or explicit unconfigured200; exact response length/close/no-store/CORS and2048B heap verified')
    m = Machine().ready()
    m.transact([request('OPTIONS', '/api/image', ('Origin: https://frontend.invalid', 'Access-Control-Request-Method: POST'))])
    m.response(204)
    assert not m.f('image_pending') and not m.f('generation')
    checks.append('Browser OPTIONS returns204 without publishing pixels; CORS derives from configured origin rather than reflecting requester')

    cases = [
        (request('PUT', '/'), 405),
        (request('GET', '/api/image'), 404),
        (request('POST', '/api/image'), 411),
        (request('POST', '/api/image', ('Content-Length: 307217',)), 413),
        (request('POST', '/api/image', ('Content-Length: 307215',)), 400),
        (request('POST', '/api/image', ('Content-Length: 307216',)), 415),
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

    for invalid in (b'NOPE' + binary[4:], struct.pack('<4sHHII', b'VIMG', 481, 320, 307200, 0),
                    struct.pack('<4sHHII', b'VIMG', 480, 320, 307201, 0)):
        m = Machine().ready().custom()
        m.transact([http + invalid])
        m.response(400)
        assert not m.f('image_pending')
        assert bytes(m.uc.mem_read(RECEIVE, 307200)) == previous.frame(0x001f)
    m = Machine().ready().custom()
    m.transact([http + binary, previous.frame(0x001f)])
    m.response(422)
    assert not m.f('image_pending') and m.f('image') == IMAGE
    checks.append('Wrong VIMG magic/dimensions/length rejects before body write; independently wrong FNV returns422 without replacing active image')

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
    # IP update is the first lock; receive-slot acquisition is the next one.
    m.lock_fail_calls.add(m.lock_calls + 2)
    m.transact([http + binary])
    m.response(503)
    assert not m.f('image_pending')
    checks.append('Unavailable receive slot or failed slot lock returns503 before payload receive, without lock leak or active image mutation')

    for setting in ('publication_lock', 'dead'):
        m = Machine().ready().custom()
        if setting == 'publication_lock':
            m.lock_fail_calls.add(m.lock_calls + 3)
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


def main():
    checks = parser_checks() + response_checks() + image_checks() + exact_checks() + server_checks()
    result = {'passed': True, 'hardware_operation': False, 'check_count': len(checks),
        'checks': checks, 'elf_sha256': hashlib.sha256(ELF.read_bytes()).hexdigest(),
        'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'context_bytes': 212, 'header_heap_bytes': 2048, 'image_payload_bytes': 307200,
        'configured_redirect_tested': bool(FRONTEND), 'configured_cors_tested': ORIGIN != '*',
        'limitations': 'Actual ARM instructions execute, but native APIs/socketRPC timing/locks/OS scheduling/LCD scanout/heap availability/cold boot are mocked or unchecked.'}
    output = ROOT / ('build/reviews/http-configured-arm-offline-result.json'
                     if FRONTEND or ORIGIN != '*' else 'firmware/tests/http-arm-offline-result.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
