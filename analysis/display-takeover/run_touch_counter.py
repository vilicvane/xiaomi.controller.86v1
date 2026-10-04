"""Temporary host-assisted screen counter. Only admitted framebuffer pixels change.

The A7 physical touch driver and stock GUI remain running. The host observes
existing input rings, never consumes them or calls native OS functions.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import socket
import statistics
import struct
import subprocess
import time

from analyze_touch_host_ring import count_edges, decode_subscriber, harvest

ROOT = Path(__file__).resolve().parents[2]
SLOTS = (0x38515040, 0x385AB140)
UPPER = 0x38646BA0
# Exact live pairs admitted by touch-counter-preflight.txt, not a guessed heap.
SUBSCRIBERS = {0x3872D080: 0x38655380, 0x38715740: 0x38655020, 0x387106E0: 0x38655140}
FONT = {
    ' ': ('00000',)*7,
    'v': ('00000','00000','10001','10001','10001','01010','00100'),
    'i': ('00100','00000','01100','00100','00100','00100','01110'),
    'l': ('01100','00100','00100','00100','00100','00100','01110'),
    'c': ('00000','00000','01111','10000','10000','10000','01111'),
    'a': ('00000','00000','01110','00001','01111','10001','01111'),
    'n': ('00000','00000','11110','10001','10001','10001','10001'),
    'e': ('00000','00000','01110','10001','11111','10000','01111'),
    '+': ('00000','00100','00100','11111','00100','00100','00000'),
    '0': ('01110','10001','10011','10101','11001','10001','01110'),
    '1': ('00100','01100','00100','00100','00100','00100','01110'),
    '2': ('01110','10001','00001','00010','00100','01000','11111'),
    '3': ('11110','00001','00001','01110','00001','00001','11110'),
    '4': ('00010','00110','01010','10010','11111','00010','00010'),
    '5': ('11111','10000','10000','11110','00001','00001','11110'),
    '6': ('01110','10000','10000','11110','10001','10001','01110'),
    '7': ('11111','00001','00010','00100','01000','01000','01000'),
    '8': ('01110','10001','10001','01110','10001','10001','01110'),
    '9': ('01110','10001','10001','01111','00001','00001','01110'),
}


def render_rows(count):
    if not 0 <= count <= 9999:
        raise ValueError('Counter exceeds four digit test limit')
    logical = [[0xFF101010]*280 for _ in range(32)]
    for ci, char in enumerate(f'vilicvane +{count}'):
        for gy, pattern in enumerate(FONT[char]):
            for gx, value in enumerate(pattern):
                if value == '1':
                    for dy in range(3):
                        for dx in range(3):
                            logical[5+gy*3+dy][5+ci*18+gx*3+dx] = 0xFFFF00FF
    # Existing firmware's rotation: physical[(479-x)*320+y]=logical[y*480+x].
    return [[logical[col][279-row] for col in range(32)] for row in range(280)]


class EpochLost(RuntimeError):
    pass


class Link:
    def __init__(self, sock):
        self.sock = sock
        self.pending = b''
        self.timings = []

    def call(self, command):
        started = time.monotonic()
        self.sock.sendall(command.encode('ascii')+b'\x1a')
        while b'\x1a' not in self.pending:
            block = self.sock.recv(65536)
            if not block:
                raise RuntimeError('OpenOCD closed the local connection')
            self.pending += block
        reply, self.pending = self.pending.split(b'\x1a', 1)
        self.timings.append((time.monotonic()-started)*1000)
        return reply.decode('utf-8').strip()

    def read(self, address, words):
        reply = self.call(f'read_memory 0x{address:x} 32 {words}')
        values = reply.split()
        if len(values) != words or any(not re.fullmatch(r'(?:0x[0-9a-fA-F]+|[0-9]+)', v) for v in values):
            raise RuntimeError(f'Incomplete MEM-AP read at 0x{address:x}: {reply[:180]}')
        return [int(v, 0) for v in values]

    def raw(self, address, byte_count):
        return struct.pack('<'+'I'*(byte_count//4), *self.read(address, byte_count//4))

    def read_rows(self, base, first, count):
        reply = self.call(f'tc_read_rows 0x{base:x} {first} {count}')
        values = reply.split()
        if len(values) != count*32 or any(not re.fullmatch(r'(?:0x[0-9a-fA-F]+|[0-9]+)', v) for v in values):
            raise RuntimeError('Incomplete bounded pixel rectangle read')
        words = [int(v, 0) for v in values]
        return [words[i:i+32] for i in range(0, len(words), 32)]

    def write_rows(self, base, first, rows):
        values = ' '.join(hex(word) for row in rows for word in row)
        reply = self.call(f'tc_rows 0x{base:x} {first} {len(rows)} {{{values}}}')
        if 'PIXEL_EPOCH_OR_GEOMETRY_CHANGED' in reply:
            raise EpochLost('Pixel server observed a power or geometry change; discard old snapshots')
        if reply != 'OK':
            raise RuntimeError('Pixel write did not complete: '+reply[:180])


class Counter:
    def __init__(self, link, capture):
        self.link, self.capture = link, capture
        self.count, self.events, self.retries = 0, [], 0
        self.render_updates, self.observed_counts = [], {}
        self.pressed = None
        self.last_head = None
        self.sub = None
        self.original, self.last_pixels, self.possible = {}, {}, set()
        self.alive = True

    def gate(self):
        prsr = self.link.read(0x58050314, 1)[0]
        if not prsr & 1 or prsr & 0x54:
            self.alive = False
            raise RuntimeError('A7 power/reset event; discard old pixel snapshots')
        geometry = self.link.read(0x581000F4, 6)
        if geometry[0] not in SLOTS or geometry[2] != 1280 or geometry[4:6] != [0x01E00140]*2:
            self.alive = False
            raise RuntimeError('Display scanout geometry changed')
        if self.link.read(0x58100264, 1)[0] & 0xFFF != 0x401:
            self.alive = False
            raise RuntimeError('Display format changed')

    def identity(self):
        if self.link.read(0x384F50B0, 1)[0] != UPPER:
            raise RuntimeError('Physical touch upper allocation changed; rerun preflight')
        upper = self.link.read(UPPER, 8)
        if upper[0] & 255 != 8 or upper[7] != 0x384F50AC:
            raise RuntimeError('Physical upper-half identity differs')
        sentinel, node, prior = UPPER+20, upper[5], UPPER+20
        nodes = []
        for _ in range(4):
            if node == sentinel:
                break
            sub = node-20
            if sub not in SUBSCRIBERS:
                raise RuntimeError('Unadmitted subscriber allocation')
            header = self.link.raw(sub, 60)
            meta = decode_subscriber(header)
            if meta['buffer'] != SUBSCRIBERS[sub] or meta['prev'] != prior:
                raise RuntimeError('Physical input ring/list identity changed')
            nodes.append(sub)
            prior, node = node, meta['next']
        if node != sentinel or upper[6] != prior or not nodes:
            raise RuntimeError('Physical input subscriber list is inconsistent')
        if self.sub is None:
            self.sub = nodes[0]
        if self.sub not in nodes:
            raise RuntimeError('Observed physical input subscriber closed')

    def baseline(self):
        self.identity()
        first = decode_subscriber(self.link.raw(self.sub, 60))
        state = self.link.read(0x384F50A0, 1)[0] >> 8 & 255
        after = decode_subscriber(self.link.raw(self.sub, 60))
        if first['head'] != after['head']:
            raise RuntimeError('Touch changed during initial baseline; lift finger and retry')
        self.last_head = after['head']
        self.pressed = {1: True, 4: False}.get(state)

    def poll(self):
        before = self.link.raw(self.sub, 60)
        meta = decode_subscriber(before)
        if meta['buffer'] != SUBSCRIBERS[self.sub]:
            raise RuntimeError('Input ring allocation changed')
        if meta['head'] == self.last_head:
            return
        ring = self.link.raw(meta['buffer'], 256)
        ring_again = self.link.raw(meta['buffer'], 256)
        after = self.link.raw(self.sub, 60)
        if ring != ring_again:
            self.retries += 1
            return
        try:
            result = harvest(before, ring, after, self.last_head)
        except ValueError as error:
            if 'Metadata changed' in str(error):
                self.retries += 1
                return
            raise
        if result['gap']:
            raise RuntimeError('Touch event buffer was overwritten; stopped rather than display an inaccurate count')
        edge = count_edges(result['events'], self.pressed)
        self.pressed, self.last_head = edge['pressed'], result['head']
        self.count += edge['added']
        self.events.extend(result['events'])
        if edge['added']:
            self.observed_counts[self.count] = time.monotonic()
            print(f'vilicvane +{self.count}', flush=True)

    @staticmethod
    def address(base, row):
        return base+(100+row)*1280+144*4

    def backup(self):
        for base in SLOTS:
            rows = [row for first in range(0, 280, 8) for row in self.link.read_rows(base, first, 8)]
            self.original[base] = rows
            self.last_pixels[base] = [None]*280
            (self.capture/f'pixels-{base:x}-original.bin').write_bytes(struct.pack('<8960I', *[v for row in rows for v in row]))

    def draw(self, active=True, full=True):
        started = time.monotonic()
        rows = render_rows(self.count)
        rendered_count = self.count
        for base in SLOTS:
            dirty = list(range(280)) if full else [r for r in range(280) if self.last_pixels[base][r] != rows[r]]
            batches = []
            for row in dirty:
                if batches and len(batches[-1]) < 8 and row == batches[-1][-1]+1:
                    batches[-1].append(row)
                else:
                    batches.append([row])
            for indices in batches:
                if active:
                    self.poll()
                    # Give a newly observed press priority over background repaint.
                    if self.count != rendered_count:
                        return rendered_count
                first = indices[0]
                batch = [rows[row] for row in indices]
                current_rows = self.link.read_rows(base, first, len(batch))
                for i in range(len(batch)):
                    row = first+i
                    current = current_rows[i]
                    previous = self.last_pixels[base][row]
                    if previous is not None:
                        self.original[base][row] = [old if now == ours else now for old, now, ours in zip(self.original[base][row], current, previous)]
                    else:
                        self.original[base][row] = current
                    self.possible.add((base, row))  # Posted write may commit before error.
                    self.last_pixels[base][row] = batch[i]
                # tc_rows independently gates live power/geometry before EVERY batch.
                self.link.write_rows(base, first, batch)
        completed = time.monotonic()
        self.render_updates.append({'count': rendered_count, 'full_repaint': full,
            'draw_ms': (completed-started)*1000,
            'after_host_touch_ms': (completed-self.observed_counts[rendered_count])*1000
                if rendered_count in self.observed_counts else None})
        return rendered_count

    def restore(self):
        if not self.possible:
            return {'status': 'no_pixels_changed'}
        if not self.alive:
            return {'status': 'discarded_after_power_or_geometry_change'}
        self.gate()
        restored, preserved = 0, 0
        for base in SLOTS:
            for first in range(0, 280, 8):
                touched = [row for row in range(first, first+8) if (base, row) in self.possible]
                if not touched:
                    continue
                batch = []
                current_rows = self.link.read_rows(base, first, 8)
                for row in range(first, first+8):
                    current = current_rows[row-first]
                    if (base, row) in self.possible:
                        ours, original = self.last_pixels[base][row], self.original[base][row]
                        new = [old if now == own else now for old, now, own in zip(original, current, ours)]
                        restored += sum(now == own for now, own in zip(current, ours))
                        preserved += sum(now != own for now, own in zip(current, ours))
                    else:
                        new = current
                    batch.append(new)
                if len(touched) == 8:
                    self.link.write_rows(base, first, batch)
                else:
                    for row in touched:
                        self.link.write_rows(base, row, [batch[row-first]])
            (self.capture/f'pixels-{base:x}-latest-baseline.bin').write_bytes(
                struct.pack('<8960I', *[v for row in self.original[base] for v in row]))
        return {'status': 'overlay_removed', 'own_pixels_restored': restored, 'GUI_updates_preserved': preserved,
                'limit': 'Stock GUI stays active; pixel reads/writes are not an atomic compositor transaction'}


def run(args):
    capture = ROOT/'analysis/display-takeover'/('manual-touch-counter-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    capture.mkdir()
    probe = ROOT/'tools/xpack-openocd-0.12.0-7/bin/openocd.exe'
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    output = open(capture/'openocd-console.txt', 'w', encoding='utf-8')
    process = subprocess.Popen([str(probe), '-s', 'diagnostics', '-c', 'bindto 127.0.0.1',
        '-c', f'tcl_port {port}', '-c', 'telnet_port disabled', '-c', 'gdb_port disabled',
        '-f', 'diagnostics/touch-counter-host.cfg', '-l', (capture/'openocd.txt').as_posix()], cwd=ROOT,
        stdout=output, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    connection, counter, link = None, None, None
    report = {'scope': 'Host-assisted counter, read-only physical touch rings; RAM pixels in two fixed rectangles only',
              'CPU_halt_or_injection': False, 'Flash_writes': False, 'stock_GUI_receives_touches': True,
              'reset_detection_limit': 'A7 debug locks stay set; sticky power history is not a reset counter. Live power/reset/halt and allocation/display identities are gated.'}
    failed = False
    try:
        deadline = time.monotonic()+12
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('OpenOCD exited before local server started')
            try:
                connection = socket.create_connection(('127.0.0.1', port), timeout=1)
                break
            except OSError:
                time.sleep(.1)
        if connection is None:
            raise RuntimeError('Local OpenOCD connection did not start')
        connection.settimeout(5)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        link = Link(connection)
        # Locked PRSR retains sticky PU/PD history; inspect live fields only.
        initial_power = link.read(0x58050314, 1)[0]
        if not initial_power & 1 or initial_power & 0x44:
            raise RuntimeError('A7 is not in the qualified running power state')
        counter = Counter(link, capture)
        counter.gate()
        counter.identity()
        if args.read_only:
            check_rows = link.read_rows(SLOTS[0], 0, 8)
            report['bounded_pixel_read_verified'] = len(check_rows) == 8 and all(len(row) == 32 for row in check_rows)
            counter.baseline()
            deadline = time.monotonic()+args.seconds
            print('READ_ONLY_TOUCH_OBSERVER_READY', flush=True)
            while time.monotonic() < deadline:
                counter.poll()
                counter.gate()
                time.sleep(.02)
        else:
            counter.backup()
            counter.draw(active=False)
            counter.baseline()
            print(f'COUNTER_READY: vilicvane +0. Tap blank areas for {args.seconds} seconds.', flush=True)
            deadline = time.monotonic()+args.seconds
            next_full_draw, drawn = time.monotonic()+2, 0
            while time.monotonic() < deadline:
                counter.poll()
                counter.gate()
                if counter.count != drawn:
                    drawn = counter.draw(full=False)
                elif time.monotonic() >= next_full_draw:
                    drawn = counter.draw(full=True)
                    next_full_draw = time.monotonic()+2
                time.sleep(.02)
    except (Exception, KeyboardInterrupt) as error:
        failed = True
        if counter is not None and isinstance(error, EpochLost):
            counter.alive = False
        report['error'] = str(error) or 'Interrupted'
        print('TEST_STOPPED: '+report['error'], flush=True)
    finally:
        if counter is not None:
            try:
                report['restoration'] = counter.restore()
            except Exception as error:
                if isinstance(error, EpochLost):
                    counter.alive = False
                failed = True
                report['restoration'] = {'status': 'failed', 'error': str(error)}
            report.update(count=counter.count, physical_events=counter.events, snapshot_retries=counter.retries,
                          render_updates=counter.render_updates)
        if link is not None and link.timings:
            report['RPC_ms'] = {'calls': len(link.timings), 'median': statistics.median(link.timings),
                                'max': max(link.timings), 'total': sum(link.timings)}
        if connection is not None:
            try:
                Link(connection).call('shutdown')
            except (OSError, RuntimeError):
                pass
            connection.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        output.close()
        report['passed'] = not failed
        (capture/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('Evidence saved: '+str(capture), flush=True)
    return int(failed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--read-only', action='store_true')
    parsed = parser.parse_args()
    if not 2 <= parsed.seconds <= 180:
        parser.error('Use 2..180 seconds for this temporary test')
    raise SystemExit(run(parsed))
