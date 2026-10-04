"""Decode saved BEST2003 IOMUX snapshots. This script never accesses the target."""

import csv
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis" / "pinout"
REF = json.loads((OUT / "public-pinmux-reference.json").read_text(encoding="utf-8"))
FILES = [ROOT / "backups" / "pinout-registers-1.50.10" / name
         for name in ("iomux-before.bin", "iomux-after.bin")]
DATA = [p.read_bytes() for p in FILES]
assert all(len(b) == 0x98 for b in DATA)
assert DATA[0] == DATA[1], "Snapshots changed; inspect before combining observations."


def word(offset):
    return struct.unpack_from("<I", DATA[0], offset)[0]


SPECIAL = {2: "UART_RTS_CTS_SPECIAL", 12: "BTDM_SPECIAL",
           13: "WIFI_FEM_SPECIAL", 14: "TEST_PORT", 15: "GPIO"}
pins = []
for pin in REF["pins"]:
    n = pin["pin_enum"]
    offset = 4 + 4 * (n // 8)
    shift = 4 * (n % 8)
    mux = (word(offset) >> shift) & 15
    ordinary = [a for a in pin["alternate_functions"] if a["mux_register_value"] == mux]
    if n in (0, 1) and mux == 7:
        function = ("SWDIO_TMS", "SWCLK_TCK")[n]
        evidence = "Dedicated hal_iomux_set_jtag route; SWD access confirmed."
    elif mux in SPECIAL:
        function = SPECIAL[mux]
        evidence = "Special hardware mux selector in first-party BEST2003 HAL."
    else:
        function = ordinary[0]["function"].removeprefix("HAL_IOMUX_FUNC_") if ordinary else "UNDECODED"
        evidence = "32x11 pin-function table matches the 1.50.10 MCU binary exactly."
    pu, pd = bool(word(0x2C) & (1 << n)), bool(word(0x30) & (1 << n))
    pins.append({"pin": pin["pin"], "gpio_number": n,
                 "register_address": f"0x{0x40086000 + offset:08x}",
                 "register_word": f"0x{word(offset):08x}", "nibble_shift": shift,
                 "hardware_mux": mux, "function": function,
                 "pullup": pu, "pulldown": pd,
                 "pull": "both" if pu and pd else "up" if pu else "down" if pd else "none",
                 "evidence": evidence})

report = {
    "firmware_version": "1.50.10",
    "scope": "Decode two saved running-target read-only IOMUX captures; no hardware access in this script.",
    "base_address": "0x40086000", "byte_length": 0x98,
    "snapshots": [{"file": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(b).hexdigest()}
                  for p, b in zip(FILES, DATA)],
    "snapshots_identical": True,
    "source_repository": REF["source_repository"], "source_tree_sha": REF["source_tree_sha"],
    "register_words": {f"0x{offset:03x}": f"0x{word(offset):08x}" for offset in range(0, 0x98, 4)},
    "reg050": {"value": f"0x{word(0x50):08x}",
               "GPIO_I2C_MODE": bool(word(0x50) & 1),
               "I2C0_M_SEL_GPIO": bool(word(0x50) & 2),
               "I2C1_M_SEL_GPIO": bool(word(0x50) & 16),
               "I2C2_M_SEL_GPIO": bool(word(0x50) & 32)},
    "pins": pins,
    "limits": ["Logical GPIO bank/bit numbers are not physical BGA balls or test-pad locations.",
               "Configured mux does not prove a physical device is connected or currently transferring data.",
               "GPIO direction and input/output levels are not present in this IOMUX capture.",
               "Equal sequential running-target snapshots are stable observations, not an atomic whole-system snapshot.",
               "VIO configuration does not establish a measured pin voltage.",
               "Dedicated DSI, power, analog and Flash pins are outside this ordinary 32-GPIO map."]}
(OUT / "live-iomux-1.50.10.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
with (OUT / "live-iomux-1.50.10.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(pins[0]))
    w.writeheader()
    w.writerows(pins)
print(f"Decoded {len(pins)} logical pins from two identical read-only captures.")
