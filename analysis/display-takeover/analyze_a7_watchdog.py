"""Bounded static watchdog xrefs in saved firmware; no hardware/log access."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/pinout"))
from analyze_a7_peripherals import FILE, START, BASE, find_xrefs, find_direct_calls, disassemble, offset_to_address, address_to_offset
import struct

data = FILE.read_bytes()
end = START + int.from_bytes(data[START-4:START], "big")
targets = {address: name for address, name in (
    (0x58001000, "DSP_WDT_BASE"), (0x58001004, "DSP_WDT_VALUE"),
    (0x58001008, "DSP_WDT_CONTROL"), (0x58001010, "DSP_WDT_RIS"),
    (0x4000011c, "CMU_DSP_DIV"), (0x40082000, "AON_WDT_BASE"))}
strings = []
cursor = START
while cursor < end:
    finish = data.find(b"\0", cursor, min(cursor+512, end))
    if finish < 0:
        cursor += 512
        continue
    chunk = data[cursor:finish]
    if 5 <= len(chunk) <= 160 and all(32 <= v < 127 for v in chunk):
        low = chunk.lower()
        if any(term in low for term in (b"hal_wdt", b"watchdog", b"wdt_start", b"wdt_set_timeout", b"wdt_ping")):
            text = chunk.decode("ascii")
            # Only code symbol/file labels; exclude arbitrary formatted logs.
            if "%" not in text:
                address = offset_to_address(cursor)
                strings.append({"file_offset": hex(cursor), "address": hex(address), "label": text})
                targets[address] = text
    cursor = finish+1
hits = find_xrefs(data, end, targets)
windows = []
for hit in hits:
    position = int(hit["movw_offset"], 16)
    begin = max(START, position-48)
    if hit["mode"] == "ARM":
        begin -= begin % 4
    windows.append({"xref": hit, "instructions": disassemble(data, begin, 192, hit["mode"])})
report = {"scope": "Only saved A7 firmware static code/safe symbol labels; no hardware or raw logs",
          "image": str(FILE.relative_to(ROOT)), "sha256": hashlib.sha256(data).hexdigest(),
          "effective_a7_end_exclusive": hex(end), "safe_symbol_labels": strings,
          "candidate_xrefs": windows,
          "limitation": "MOVW/MOVT xrefs require instruction/data-flow validation; mere presence is not proof of a live watchdog instance or timeout."}
functions = {0x383d7244: "hal_wdt_start_matched_register_sequence",
             0x383d72b8: "hal_wdt_stop_matched_register_sequence",
             0x383d7300: "hal_wdt_ping_matched_register_sequence",
             0x383d7364: "hal_wdt_set_timeout_matched_arithmetic",
             0x383d73b4: "hal_wdt_get_timeleft_matched_arithmetic"}
report["validated_function_entries"] = {name: hex(address) for address, name in functions.items()}
report["validated_function_callers"] = find_direct_calls(data, end, functions, include_jumps=True)
report["validated_windows"] = [
    {"name": name, "file_offset": hex(offset), "mode": mode,
     "instructions": disassemble(data, offset, size, mode)}
    for name, offset, size, mode in (
        ("WDT_start_stop_ping_set_timeout_get_timeleft", 0xcb7248, 0x1cc, "ARM"),
        ("runtime_tick_frequency_calibration_write_and_getter", 0xcaee44, 0x100, "ARM"),
        ("NuttX_lower_watchdog_start_stop_timeout_ms_conversion", 0x8e39e4, 0x164, "Thumb"))]
report["runtime_frequency_word"] = {
    "address": "0x384ef82c", "size": 4,
    "initial_word_in_payload": hex(struct.unpack_from("<I", data, address_to_offset(0x384ef82c))[0]),
    "getter": "0x383ceee0", "units": "ticks per second as used by HAL timeout multiplication and milliseconds conversion",
    "write_cross_reference": "0x383cee84 strls r1,[r3] and0x383cee8c strhi r2,[r3], where r3=0x384ef82c; calibrated value is capped at0x7d00=32000",
    "limitation": "Initialized16000 is not live frequency. Firmware calibration writes this word. Hardware integration can only be corroborated by live clock selector/countdown observation."}
out = ROOT / "analysis/display-takeover/a7-watchdog-static-xrefs.json"
out.write_text(json.dumps(report, indent=2) + "\n")
print(f"Bounded A7 watchdog candidate code windows: {len(windows)}; safe symbols: {len(strings)}")
