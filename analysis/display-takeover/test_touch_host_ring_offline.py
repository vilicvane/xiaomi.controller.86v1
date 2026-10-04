"""Meaningful pure-byte tests: event wrap, gaps, publication races, press latch."""
import struct
from analyze_touch_host_ring import count_edges, decode_subscriber, harvest


def metadata(head, tail=0, pointer=0x38510000, external=0):
    result = bytearray(60)
    struct.pack_into("<4I", result, 0, pointer, 256, head, tail)
    result[16] = external
    struct.pack_into("<2I", result, 20, 0x38501234, 0x38505678)
    return bytes(result)


def sample(flags, ident, stamp):
    result = bytearray(32)
    struct.pack_into("<I", result, 0, 1)
    result[8:10] = bytes([ident & 255, flags])
    struct.pack_into("<hh", result, 10, 123, 321)
    struct.pack_into("<Q", result, 24, stamp)
    return result


ring = bytearray(256)
assert decode_subscriber(metadata(0, external=0))["external"] == 0
assert decode_subscriber(metadata(0, external=1))["external"] == 1
try:
    decode_subscriber(metadata(0, external=2))
except ValueError:
    pass
else:
    raise AssertionError("A nonboolean external-buffer flag was accepted")
for cursor, flags in [(192, 0x19), (224, 0x19), (256, 0x1A), (288, 0x1C)]:
    offset = cursor % 256
    ring[offset:offset + 32] = sample(flags, cursor // 32, cursor * 100)
capture = harvest(metadata(320, 192), ring, metadata(320, 320), 192)
assert [event["flags"] for event in capture["events"]] == [0x19, 0x19, 0x1A, 0x1C]
assert count_edges(capture["events"], False) == {"added": 1, "pressed": False}
assert not capture["gap"] and capture["delta_events"] == 4
assert harvest(metadata(320, 320), ring, metadata(320, 320), 320)["events"] == []
assert harvest(metadata(320, 320), ring, metadata(320, 320), None)["baseline"]
try:
    harvest(metadata(320, 320), ring, metadata(352, 320), 320)
except ValueError:
    pass
else:
    raise AssertionError("A racing producer commit was accepted")
for cursor in range(0, 256, 32):
    ring[cursor:cursor + 32] = sample(0x19, cursor // 32, cursor * 100)
gap = harvest(metadata(256), ring, metadata(256), 0)
assert gap["gap"] and gap["omitted_at_least"] == 1 and len(gap["events"]) == 7
assert count_edges(gap["events"], False, gap=True) == {"added": 0, "pressed": None}
assert count_edges([{"flags": 4}, {"flags": 1}, {"flags": 1}, {"flags": 2}], None) == {"added": 1, "pressed": True}
wrap_ring = bytearray(256)
for cursor, flags in [(0xFFFFFFE0, 0x19), (0, 0x1C)]:
    offset = cursor % 256
    wrap_ring[offset:offset + 32] = sample(flags, cursor // 32, 100)
wrapped = harvest(metadata(32, 0xFFFFFFE0), wrap_ring, metadata(32, 32), 0xFFFFFFE0)
assert wrapped["delta_events"] == 2 and [event["flags"] for event in wrapped["events"]] == [0x19, 0x1C]
try:
    decode_subscriber(metadata(320, 0))
except ValueError:
    pass
else:
    raise AssertionError("Invalid producer-consumer distance was accepted")
print("Offline touch byte decoder: external0/1 admission/2 refusal, ringwrap, duplicateDOWN, MOVE, UP, gap, racingcommit and baseline gates passed; no hardware")
