"""Offline current-firmware touch-ring evidence and pure captured-byte decoder.

No adapter or hardware APIs. Dynamic addresses must be admitted by the caller's
separately validated live RAM ranges, never by a guessed memory-map extent.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/pinout"))
import analyze_a7_peripherals as a


def decode_subscriber(raw):
    if len(raw) != 60:
        raise ValueError("Subscriber capture must be exactly60 bytes")
    buffer, size, head, tail = struct.unpack_from("<4I", raw)
    # Offset16 is circbuf.external, not an allocation/initialization flag.
    # circbuf_init stores !!input_base BEFORE allocating when base isNULL:
    # physicaltouch open passesNULL, so its internallyowned ring has0.
    if size != 256 or raw[16] not in (0, 1) or not buffer or buffer & 7:
        raise ValueError("Not the proved8x32-byte ring with a valid external-buffer boolean")
    if head % 32 or tail % 32 or (head - tail) & 0xFFFFFFFF > 256:
        raise ValueError("Ring cursors inconsistent with exact32-byte events")
    return {"buffer": buffer, "size": size, "head": head, "tail": tail,
            "external": raw[16],
            "allocated": raw[16],  # Legacy dictionarykey only; value isexternal.
            "next": struct.unpack_from("<I", raw, 20)[0],
            "prev": struct.unpack_from("<I", raw, 24)[0]}


def decode_event(raw):
    if len(raw) != 32 or struct.unpack_from("<I", raw)[0] != 1:
        raise ValueError("Expected exact one-point32-byte event")
    return {"npoints": 1, "id": raw[8], "flags": raw[9],
            "x": struct.unpack_from("<h", raw, 10)[0],
            "y": struct.unpack_from("<h", raw, 12)[0],
            "timestamp_us_raw": struct.unpack_from("<Q", raw, 24)[0]}


def harvest(before_raw, ring_raw, after_raw, last_head):
    """Return stable recently committed events without altering consumer tail.

    The caller must validate upper/list/pointer identity around both captures.
    We reserve the oldest of8 slots against an in-progress producer overwrite.
    First attachment establishes a baseline and returns no historical events.
    """
    before, after = decode_subscriber(before_raw), decode_subscriber(after_raw)
    if len(ring_raw) != 256:
        raise ValueError("Read exactly256 bytes from the admitted buffer pointer")
    for key in ("buffer", "size", "head", "external", "next", "prev"):
        if before[key] != after[key]:
            raise ValueError("Metadata changed during snapshot: retry without advancing host cursor")
    head = after["head"]
    if last_head is None:
        return {"head": head, "delta_events": 0, "gap": False,
                "omitted_at_least": 0, "baseline": True, "events": []}
    delta = (head - last_head) & 0xFFFFFFFF
    if delta % 32:
        raise ValueError("Epoch/cursor mismatch")
    count = delta // 32
    retained = min(count, 7)
    events = []
    for distance in range(retained, 0, -1):
        cursor = (head - distance * 32) & 0xFFFFFFFF
        offset = cursor % 256
        event = decode_event(ring_raw[offset:offset + 32])
        event["producer_cursor_end"] = (cursor + 32) & 0xFFFFFFFF
        events.append(event)
    return {"head": head, "delta_events": count, "gap": count > 7,
            "omitted_at_least": max(0, count - 7), "baseline": False, "events": events}


def count_edges(events, pressed, gap=False):
    """pressed=None means unsynchronized; only a witnessedUP rearms counting.

    The physical driver can publish repeatedDOWN for changed coordinates;
    neither DOWN-bit occurrences nor changing8-bit pointID equal new taps.
    """
    if gap:
        pressed = None
    added = 0
    for event in events:
        flags = event["flags"]
        if flags & 4:
            pressed = False
        elif flags & 3:
            if pressed is False:
                added += 1
                pressed = True
            # After a gap or initial attach, stay unknown until a witnessedUP.
    return {"added": added, "pressed": pressed}


def build_report():
    data = a.FILE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b"
    windows = [
        ("physical_worker", 0x380211B8, 0x3E4),
        ("publisher_fanout", 0x380144F0, 0x8C),
        ("subscriber_open", 0x38019360, 0xBC),
        ("ring_initialize", 0x383D9514, 0x94),
        ("ring_write_commit", 0x383D9A7C, 0xE4),
        ("ring_read_tail_commit", 0x383D9848, 0x78),
        ("upper_initialize", 0x383AE02C, 0x7C),
    ]
    evidence = [{"name": name, "address": hex(addr), "mode": "Thumb",
                 "instructions": a.disassemble(data, a.address_to_offset(addr), size, "Thumb")}
                for name, addr, size in windows]
    report = {
        "firmware": "1.50.10", "offline_only": True,
        "image_sha256": hashlib.sha256(data).hexdigest(),
        "recommendation": "Keep A7 OS, touch IRQ/I2C and physicalworker running. Host reads existing physicalsubscriber ring without VFS calls or consumption; updates the admitted overlay separately.",
        "physical_driver": {"base": "0x384f5068", "lower_half": "0x384f50ac",
            "upper_pointer_slot": "0x384f50b0", "last_id": "base+0x38",
            "last_state": "base+0x39:1 contact,4 release; not finalsample flags",
            "last_xy_signed16": ["base+0x3c", "base+0x3e"],
            "publish_id_counter_byte": "0x384fb04c; increments every emitted candidate, wraps256, not contactID or atomic sequence",
            "sample_storage": "32B event is onworker stack at r7+0x28 until publisher copies it; no permanent global fullsample established",
            "publication": "0x380213ae -> touch_event0x380144f0"},
        "upper_layout": {"bytes": 32, "capacity_u8_offset": 0, "capacity_expected": 8,
            "next_u32_offset": 20, "prev_u32_offset": 24, "lower_u32_offset": 28,
            "lower_expected": "0x384f50ac", "sentinel": "upper+0x14",
            "traversal": "node=*u32(upper+0x18); while node!=sentinel: subscriber=node-0x14, then node=*u32(subscriber+0x18). Bound traversal and verify reciprocallinks plus sameupper around capture."},
        "subscriber_layout": {"bytes": 60,
            "buffer_ptr_u32": 0, "buffer_size_u32": 4, "producer_head_u32": 8,
            "consumer_tail_u32": 12, "external_buffer_bool_u8": 16,
            "external_semantics": "0 internalallocation,1 callerprovidedbuffer. Both valid; notaninitflag. Physicalopen passesbaseNULL soactual0 isexpected. decode_subscriber retainslegacy allocated dictionarykey asalias only.",
            "next_u32": 20, "prev_u32": 24, "size_expected": 256,
            "cursor_semantics": "Unsignedmonotonic bytecursors, modulo256 toindex data. Publisher commits head+=32 after copy; overflowadvances tail. GUIread advances tail only; bytesremain until overwritten.",
            "size_proof": "open0x38019386..39a:32+(maxpoints1-1)*24, multipliedby uppercapacity8; circbufinitialize0x383d9514 storesbuffer/size/head0/tail0"},
        "event_abi": {"bytes": 32, "endian": "little", "npoints_u32": 0,
            "id_u8": 8, "flags_u8": 9, "x_i16": 10, "y_i16": 12,
            "timestamp_u64": 24, "timestamp_unit": "microseconds; clocksource/epoch notproved; never use as sole sequence",
            "flags": {"DOWN": 1, "MOVE": 2, "UP": 4, "ID_VALID": 8, "POS_VALID": 16},
            "observed_publisher": "contact0x19, MOVEcase0x1a, release0x1c or0x0c. points>0 branch setsstate1 evenwithchangedcoordinates, so repeatedDOWN needpressedlatch.",
            "counter": "Count only knownreleased(false)->contact(flags&3), then awaitUP(flags&4). Initialattach/gap setspressedunknown unless independentlystablephysicalstate4 provesreleased (state1 provespressed). WitnessUP before counting whenunknown. IgnoreMOVE/repeatedDOWN whilepressed; do not treat IDchange as newtap."},
        "host_capture_protocol": [
            "Validate upperpointer in independently admitted live RAM extent; readupper32B, capacity8 and lower384f50ac. If listempty noeventsavailable; do notcreate subscriber via debugABI.",
            "Validate existinglistnode/subscriber60B and reciprocallinks within admittedRAM; buffernonzeroaligned8,size256,externalbool0or1,head/tailmultiple32, unsigned(head-tail)<=256. Do not guess entirePSRAM extent from a genericmap.",
            "Record headerbefore, read full256Bbuffer, record headerafter and upper/listidentity. Accept only buffer,size,external,head,next,prev unchanged; consumer tail mayadvance. If identity/headchanges retry and retainprevioushosthead.",
            "Initial stablecapture establishesbaselinehead; no historicalcount. Stablephysicalstate4 mayinitializepressedfalse, state1 true; otherwiseunknown. Forlatercaptures delta=(head-lasthead)&ffffffff mustmultiple32; cursorreset/changedallocation startsnew epoch.",
            "Harvest recent min(delta/32,7) eventslots at(cursor%256), chronologicalorder. Reserve oldestslot against producer's in-progress overwrite. delta>=256 means definiteinsufficient8-slotretention; conservative gap alsoatdelta224+32. Mark omittedatleast max(0,delta/32-7), don'tclaimexactcount.",
            "Useproducer cursor, notGUI tail or timestamp, to avoiddoublecount. tail advances do notconsume thishost cursor. Aftergap pressedunknown and onlyUP rearms; sampleID/timestamp support diagnostics notcontactidentity.",
            "KeepA7 running throughout inputreads. No write tohead/tail/list/mutex/subscriber and noI2C reset/reregister. A7pause wouldstopIRQworker andpreventnewring events."],
        "native_vfs_alternative": {
            "open_thumb": "0x3802c901", "open_abi": "int open(constchar*path,intflags,...); r0path,r1flags0x41 =>fd or-1/errno",
            "getfile_thumb": "0x38025679", "getfile_abi": "int fs_getfilep(intfd,structfile**out); r0fd,r1out;0success,negativeerrno",
            "read_thumb": "0x3802954d", "read_abi": "ssize_t file_read(structfile*file,void*buf,size_tlen); r0file,r1buf,r2=32; nbytes/negativeerrno",
            "path": "/dev/input0", "flags": "readpermissionbit0=1 plus NONBLOCKbit6=0x40 directlyproved in target; do notuse currentLinux-ABI master constants",
            "limits": "Requiresvalid A7 task/fd/OS synchronization andcache/privilegecontext; do notcall fromMCU, haltedA7 arbitrarycontext or ISR. Hostringroute avoids allnative calls."},
        "mcu_raw_i2c_alternative": {
            "routing": "TLSC6x, rawtransferaddrfield2e,400kHz,I2C0/P2_0/P2_1, IRQP0_6, resetP0_7 alreadyproved",
            "not_qualified": "GenericpublicmapI2C0=40005000 alone doesnotprove MCU busmaster accessibility, retainedA7clock, idletransactionstate or securemapping. No reviewed bounded MCU poll driver withstatus/error/recovery/cache/IRQclosure exists inthisartifact.",
            "recommendation": "RetainnormalA7physicalinputservice; avoidpause+rawI2C replacement forminimalcounter"},
        "limits": ["Saved-image evidenceonly; liveupper/subscriber pointers andevents notobserved bythisagent.",
            "An8-slotring cannotguarantee no missedtouches underarbitraryhostlag; reportgaps and do notinfer hiddenpressedges.",
            "HostMEMAP visibility ofA7CPUwritebackcached heapdata isnotqualified solelybythissourceanalysis. Prove actualhead/state/eventchanges duringlivehuman touches before relyingoncounter; do notflush arbitraryA7cache orhaltinputservice here.",
            "Doublemetadata alone doesnotlocktheproducer; retaining7 of8 slots avoidsoldestslot currentoverwrite whileheadstable, providedexactsinglepublisher32B path andpointeridentity remainvalid."],
        "evidence": evidence,
    }
    path = ROOT / "analysis/display-takeover/touch-host-ring-1.50.10.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Saved offline physical touch ring layout and host capture protocol; no target access")


if __name__ == "__main__":
    build_report()
