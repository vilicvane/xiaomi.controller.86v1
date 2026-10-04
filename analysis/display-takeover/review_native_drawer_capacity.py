"""Bounded offline drawer capacity review of exact saved 1.50.10 NOR.

No target connection, image edits, frozen-input regeneration or credentials.
The output describes static evidence, not hardware validation.
"""
import hashlib
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis/display-takeover"
spec = importlib.util.spec_from_file_location("a7", ROOT / "analysis/pinout/analyze_a7_peripherals.py")
a7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a7)
image = a7.FILE.read_bytes()
IMAGE_SHA = "777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b"
assert hashlib.sha256(image).hexdigest() == IMAGE_SHA
END = 0xdd3fe4
LO, HI = 0x3804bc98, 0x3804be70
targets = {va: f"wifi_recorder_worker+{va-LO:#x}" for va in range(LO, HI, 2)}

direct = [hit for hit in a7.find_direct_calls(image, END, targets, include_jumps=True)
          if not LO <= int(hit["address"], 16) < HI]
assert [(hit["mode"], hit["address"]) for hit in direct] == [
    ("ARM", "0x3801c190"), ("ARM", "0x38033a00"), ("ARM", "0x380448fc")]
mov = [hit for hit in a7.find_xrefs(image, END, {**targets, **{va | 1: name for va, name in targets.items()}})
       if not LO <= a7.offset_to_address(int(hit["movw_offset"], 16)) < HI]
assert [(hit["mode"], hit["movw_offset"], hit["pointer"]) for hit in mov] == [
    ("Thumb", "0x928c8c", "0x3804bc99"), ("Thumb", "0x928d0c", "0x3804bc99")]
pointers = []
for offset in range(a7.START, END - 3, 4):
    value = struct.unpack_from("<I", image, offset)[0]
    if LO <= (value & ~1) < HI:
        pointers.append({"offset": hex(offset), "value": hex(value)})
assert pointers == []
descriptor = struct.unpack_from("<5I", image, 0xccdd20)
assert descriptor == (0x383eda24, 100, 0x14000, 0x38048c41, 0)
assert image[a7.address_to_offset(descriptor[0]):a7.address_to_offset(descriptor[0])+14] == b"wifi_recorder\0"
rcs = image[0xcce6e4:0xccef27]
assert b"wifi_recorder" not in rcs
assert image.find(b"wifi_recorder", a7.START, END) == 0xccda28
assert image.find(b"wifi_recorder", 0xccda29, END) == -1

def window(address, size):
    return a7.disassemble(image, a7.address_to_offset(address), size, "Thumb")

inputs = ["native-drawer.c", "native-drawer.ld", "native-drawer-entry.S", "native-drawer.bin",
          "native-drawer.elf", "drawer-gesture.h", "key3-gesture.h", "build-native-drawer.sh"]
hashes = {f"analysis/display-takeover/{name}": hashlib.sha256((OUT/name).read_bytes()).hexdigest()
          for name in inputs}
raw_size = (OUT/"native-drawer.bin").stat().st_size
assert 0x3804b108 + raw_size <= HI
assert "0x3804be70" in (OUT/"native-drawer.ld").read_text() or "0xb78" in (OUT/"native-drawer.ld").read_text()
report = {
    "scope": "Independent offline exact-image capacity and source-level interaction review. No hardware access or installation; not dynamic verification.",
    "firmware_sha256": IMAGE_SHA,
    "reviewed_inputs": hashes,
    "capacity": {
        "original_broker_range": ["0x3804b108", "0x3804bc98"],
        "additional_function": "wifi_recorder pthread worker",
        "additional_range": [hex(LO), hex(HI)],
        "additional_bytes": HI-LO,
        "additional_NOR_range": [hex(a7.address_to_offset(LO)), hex(a7.address_to_offset(HI))],
        "extended_range": ["0x3804b108", hex(HI)],
        "extended_bytes": HI-0x3804b108,
        "BIN_bytes": raw_size,
        "BIN_runtime_end": hex(0x3804b108+raw_size),
        "remaining_bytes": HI-0x3804b108-raw_size,
        "NOR_sector": "0x92b000..0x92c000",
        "qualification": "Disable wifi_recorder builtin before any normal startup can call its overwritten pthread worker. Preserve neighboring shared helper from runtime3804be70 / NOR92be74 onward.",
    },
    "worker_entry_references": mov,
    "worker_literal_references": pointers,
    "direct_branch_candidates": direct,
    "ARM_false_positive_resolution": {
        "0x3801c190": "Actual Thumb ITNE/CMPNE; not ARM BHS.",
        "0x38033a00": "Actual Thumb STR/CMP; not ARM BLHS.",
        "0x380448fc": "Actual Thumb ADDS followed by first half of ADD.W; not ARM BL.",
    },
    "builtin_disable": {
        "descriptor_NOR": "0xccdd20",
        "descriptor_original_words": [hex(value) for value in descriptor],
        "entry_NOR": "0xccdd2c",
        "entry_runtime": "0x383edd28",
        "original_callable": "0x38048c41",
        "required_new_callable": "0x3804b109",
        "stub_behavior": "Existing shared negative diagnostic stub returns -38.",
        "startup_rcS_uses": 0,
        "A7_name_occurrences": 1,
        "lost_functionality": "The optional wifi_recorder shell diagnostic cannot start. Wi-Fi services/drivers and shared neighboring messaging helpers are preserved.",
    },
    "source_review": {
        "bootstrap": "A short-lived native pthread only waits for GUI timer hook installation, then exits; it does not own a touch subscription or draw pixels.",
        "physical_classification": "Class-checked GUI file.inode.private upper pointer compared to live physical handle WORD384f50b0; list order is not assumed.",
        "decoder_ABI": "GUI x32/y32 +0/+4, state byte+0x12, continue byte+0x13. Raw original decoder always runs to drain original subscriber.",
        "captured_contact": "Physical top-band contact is captured from initial DOWN and retained through eventual UP, including horizontal cancellation. Stock contact starting outside top band stays unclaimed. A delivered virtual press blocks new stock capture.",
        "animation_contacts": "New contacts while snap animation is active are fully suppressed until original decoder reports their UP; final release/ring gate prevents their replay into the next owner.",
        "key_start": "Key-requested animation starts after two GUI release scans and raw physical release. Undelivered queued contacts are suppressed whole; already delivered press prevents animation start.",
        "handoff": "Only the final owner commit uses the distinct touch upper publisher mutexes. It checks both GUI rings, both decoder release states, raw physical release and native display queue zero; no obsolete third subscriber exists.",
        "composition": "Background captured in GUI thread after original TIMER completes and old display queue is empty. Stock PAN and UPDATEAREA are suppressed during overlay. Separate long-lived snapshot and compositor allocations prevent normal stock repaint from altering animation background.",
        "native_source": "Native PAN rotates/copies synchronously before publishing native staging queue; source allocation remains alive. Compositor is rewritten only with queue count zero.",
        "tap": "Counter increments on completed unmoved contact; upward dismiss and horizontal drags do not accidentally count as taps.",
        "legacy_guards": "Fixed 1.50.10 format, buffer identity, callback identity, closed timer and original-once/main lifetime guards remain; no native queue or staging metadata is modified.",
    },
    "code_windows": {
        "worker_start": window(LO, 40),
        "worker_end_and_next_function": window(HI-16, 32),
        "creator_thread0": window(0x38048c74, 52),
        "creator_threadsN": window(0x38048cf8, 52),
        "false_positive_3801c190": window(0x3801c188, 24),
        "false_positive_38033a00": window(0x380339f8, 24),
        "false_positive_380448fc": window(0x380448f4, 24),
    },
    "limits": [
        "Syntactic incoming-pointer/branch scans do not prove absence of every arbitrary computed pointer.",
        "Static GUI-thread snapshot placement does not prove all possible mmap writers or DMA producers are serialized.",
        "Physical top-edge coordinate correspondence, animation latency, gesture feel and full cold-boot recovery require hardware/user verification.",
        "Capacity/source review is bound to listed input hashes; rebuild or source edit invalidates that association.",
    ],
}
(OUT/"native-drawer-independent-review-1.50.10.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"worker_bytes": HI-LO, "total_capacity": HI-0x3804b108, "BIN_bytes": raw_size,
                  "remaining_bytes": report["capacity"]["remaining_bytes"], "review": "native-drawer-independent-review-1.50.10.json"}))
