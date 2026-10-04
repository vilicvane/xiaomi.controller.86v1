"""Decode already-recorded targetpreflight only; nohardware communications.

The log records28 subscriberbytes, not the full60. Persist captured28B and
explicitlyzero-pad the unused32B fordecoder admission, never claim thosezeros
are targetdata. One recordedmetadata is reused forbaseline, not raceproof.
"""
from pathlib import Path
import hashlib
import json
import struct
import urllib.request
from analyze_touch_host_ring import decode_event, decode_subscriber, harvest, count_edges

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "diagnostics/touch-counter-preflight.txt"
OUT = ROOT / "analysis/display-takeover/touch-live-preflight-offline"
OUT.mkdir(exist_ok=True)
rows = LOG.read_text().splitlines()
subscribers = {}
rings = {}
upper = None
upper_header = None
for line in rows:
    words = line.split()
    if not words:
        continue
    if words[0] == "TC_UPPER":
        upper = int(words[1], 0)
    elif words[0] == "TC_UPPER_HEADER":
        upper_header = [int(word, 0) for word in words[1:]]
    elif words[0] == "TC_SUB":
        index = int(words[1])
        address = int(words[2], 0)
        values = [int(word, 0) for word in words[3:]]
        assert len(values) == 7
        subscribers[index] = (address, struct.pack("<7I", *values))
    elif words[0].startswith("TC_RING_"):
        index = int(words[0][8:])
        values = [int(word, 0) for word in words[1:]]
        assert len(values) == 64
        rings[index] = struct.pack("<64I", *values)
assert upper == 0x38646BA0 and upper_header[0] == 8 and upper_header[7] == 0x384F50AC
sentinel = upper + 20
decoded = []
for index in sorted(subscribers):
    address, recorded = subscribers[index]
    padded = recorded + bytes(32)
    metadata = decode_subscriber(padded)
    assert metadata["external"] == 0 and metadata["head"] == metadata["tail"] == 832
    baseline = harvest(padded, rings[index], padded, None)
    assert baseline["baseline"] and not baseline["events"] and baseline["head"] == 832
    (OUT / f"sub{index}-metadata-captured28.bin").write_bytes(recorded)
    (OUT / f"sub{index}-metadata-synthetic60.bin").write_bytes(padded)
    (OUT / f"sub{index}-ring-captured256.bin").write_bytes(rings[index])
    physical_slots = [decode_event(rings[index][slot * 32:(slot + 1) * 32]) for slot in range(8)]
    # Inspectiononly:7 historicalsamples athead832 are NOT newcounterevents.
    retained = harvest(padded, rings[index], padded, (832 - 224) & 0xFFFFFFFF)
    assert len(retained["events"]) == 7
    assert count_edges(retained["events"], False) == {"added": 1, "pressed": False}
    decoded.append({"index": index, "subscriber": hex(address), "metadata": metadata,
        "captured_bytes": 28, "synthetic_unused_padding_bytes": 32,
        "baseline": baseline, "physical_slots": physical_slots,
        "historical_retained7_inspection_only": retained,
        "historical_repeated_DOWN_latch_demo": count_edges(retained["events"], False)})
addresses = [subscribers[index][0] for index in sorted(subscribers)]
assert upper_header[5] == addresses[0] + 20 and upper_header[6] == addresses[-1] + 20
for index, item in enumerate(decoded):
    assert item["metadata"]["next"] == (addresses[index + 1] + 20 if index + 1 < len(addresses) else sentinel)
    assert item["metadata"]["prev"] == (addresses[index - 1] + 20 if index > 0 else sentinel)
manifest = []
commit = "9e79ad292fd103d3b9ef737757081a3f7fbbf9a4"
for remote, name in [("include/nuttx/circbuf.h", "touch-circbuf-open-vela.h"),
                     ("libs/libc/misc/lib_circbuf.c", "touch-circbuf-open-vela.c")]:
    url = f"https://raw.githubusercontent.com/open-vela/nuttx/{commit}/{remote}"
    path = ROOT / "analysis/display-takeover/reference" / name
    if not path.exists():
        path.write_bytes(urllib.request.urlopen(url, timeout=20).read())
    manifest.append({"source": url, "path": str(path.relative_to(ROOT)),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
result = {"offline_only": True, "source_log": str(LOG.relative_to(ROOT)),
    "source_log_sha256": hashlib.sha256(LOG.read_bytes()).hexdigest(),
    "correction": "subscriber+10hex is circbuf.external, not initialized/allocatedflag;0 internallyallocated,1 externallyprovided; reject nonboolean2",
    "source_evidence": "Targetinit383d9542 storesboolinputbase beforemalloc; physicalopen38019396 setsr1=0. Officialcircbuf_init external=!!base and allocateswhenbaseNULL.",
    "primary_sources": manifest, "upper": hex(upper), "subscriber_count": len(decoded),
    "field_admission": "external0/1 separate fromsize256, nonnull8alignedbuffer,32alignedheadtail,unsigneddistance<=256 and rootvalidatedpointer/listidentity",
    "head_semantics": "832bytecursor=26 total32Bpublishedsamples, indexmod256=64; nextwriteslot2,lastcommittedslot1. Consumerheadtailboth832doesnotclear256Bcontents.",
    "atomicity_limit": "One preflight metadata/ring per subscriber; before/after reuse is only decoderbaseline validation, NOT a measured atomicdoublecapture. Last32 unusedmetadata bytes explicitlysyntheticzero, never read or inferred fromtarget.",
    "subscribers": decoded}
(OUT / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
print("Offline livepreflight comparison passed:3 external0 rings, head/tail832 bytes, baseline0new events, duplicateDOWN counted once; nohardware")
