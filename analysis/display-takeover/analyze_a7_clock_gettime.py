"""Exact saved 1.50.10 clock ABI evidence; no target communication."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/pinout"))
import analyze_a7_peripherals as a

b = a.FILE.read_bytes()
digest = hashlib.sha256(b).hexdigest()
assert digest == "777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b"
assert b[0xcca08c:0xcca08c + len(b"clock/clock_gettime.c")] == b"clock/clock_gettime.c"
windows = {
    "clock_gettime": (0x38004c38, 0xe4),
    "monotonic_backend": (0x38003180, 0xbc),
    "existing_native_caller": (0x3834f444, 0x3a),
}
report = {
    "scope": "Offline exact 1.50.10 NOR analysis only; no hardware or payload edits.",
    "firmware_sha256": digest,
    "entry_Thumb": "0x38004c39",
    "ABI": "int clock_gettime(int clock_id, struct timespec *out); r0=id,r1=out. Success0, error-1 with errno.",
    "timespec": {"size": 16, "alignment": 8, "seconds_signed64_offset": 0,
                 "nanoseconds_signed32_offset": 8, "padding_offset": 12},
    "clock_id_for_elapsed_time": 1,
    "identity_evidence": "NULL-out assertion at38004cfa..4d06 references clock/clock_gettime.c at383ea088; existing native caller at3834f478 calls this entry.",
    "monotonic_evidence": "38004c4e..54 selects ids4 or1;38004c82..88 passes out directly to backend38003180. ID0 instead calls same backend then adds realtime offset384f52b8 at38004c8c..cf6.",
    "storage_evidence": "Backend380031c8 stores64-bitseconds atout+0 and380031cc storesnanoseconds atout+8; wrapper realtime branch alsostrd+str at38004cf2/cf6.",
    "milliseconds_expression": "(uint32_t)ts.seconds * UINT32_C(1000) + (uint32_t)ts.nanoseconds / UINT32_C(1000000)",
    "caller_requirement": "Pass a16-byte,8-bytealigned owned stack object. Check return0 and0<=nanoseconds<1000000000. Castseconds before multiply to avoid64-bit arithmetic helpers. On failure cancel/block gesture instead of adding20 nominal milliseconds.",
    "limits": "This proves exact native ABI and elapsed-time path, not target execution by the proposed broker. IDs1and4 have equivalent paths in this image; no newer SDK ABI is assumed.",
    "instruction_evidence": {
        name: a.disassemble(b, a.address_to_offset(va), size, "Thumb")
        for name, (va, size) in windows.items()
    },
}
out = ROOT / "analysis/display-takeover/a7-clock-gettime-abi-1.50.10.json"
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"output": str(out.relative_to(ROOT)),
                  "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                  "entry_Thumb": report["entry_Thumb"], "clock_id": 1}))
