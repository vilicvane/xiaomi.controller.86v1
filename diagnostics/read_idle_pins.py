"""Read probe-reported pin bits without selecting any pins for output."""

import json
from datetime import datetime, timezone
from pathlib import Path

import hid


probes = [
    descriptor
    for descriptor in hid.enumerate(0x0D28, 0x0204)
    if "CMSIS-DAP" in (descriptor.get("product_string") or "")
]
if len(probes) != 1:
    raise SystemExit(f"Expected one CMSIS-DAP probe, found {len(probes)}")

device = hid.device()
try:
    device.open_path(probes[0]["path"])
    # Report ID 0, DAP_SWJ_Pins 0x10, output 0, select 0, wait 0.
    # A zero select mask leaves every output unchanged. No DAP_Connect.
    written = device.write([0, 0x10] + [0] * 63)
    response = device.read(64, 1500)
    if written != 65 or len(response) < 2 or response[0] != 0x10:
        raise SystemExit(f"Invalid DAP_SWJ_Pins response: {response}")
    value = response[1]
    result = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": "DAP_SWJ_Pins",
        "pin_select_mask": 0,
        "wait_us": 0,
        "raw_state_hex": f"0x{value:02x}",
        "reported_pin_bits": {
            "TCK": (value >> 0) & 1,
            "TMS": (value >> 1) & 1,
            "TDI": (value >> 2) & 1,
            "TDO": (value >> 3) & 1,
            "nTRST": (value >> 5) & 1,
            "nRESET": (value >> 7) & 1,
        },
        "limitations": (
            "Probe implementation dependent: nanoDAP TCK may read an output latch, "
            "and disconnected pins may be in analog mode. Not a voltage measurement "
            "or target identification; DAP_Disconnect does not guarantee all pins are high impedance."
        ),
    }
    output = Path(__file__).with_name("idle-pin-states.json")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
finally:
    device.close()
