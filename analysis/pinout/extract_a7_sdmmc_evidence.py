"""Read-only, bounded extraction of the A7 SDMMC pin initialization evidence.

Reads only the named NOR image and the public pinmux reference. No hardware,
runtime logs, or other backups are read. Writes this script's own JSON report.
"""

import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/wifi/python-packages"))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_IMM

NOR = ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin"
REPORT = ROOT / "analysis/pinout/a7-sdmmc-evidence.json"
data = NOR.read_bytes()
reference = json.loads((ROOT / "analysis/pinout/public-pinmux-reference.json").read_text())
SEGMENT_HEADER = 0x8E0000
PAYLOAD = SEGMENT_HEADER + 4
BASE = 0x38000000
length = struct.unpack_from(">I", data, SEGMENT_HEADER)[0]
assert length == 0x4F3FE0


def offset(address):
    return PAYLOAD + address - BASE


def instructions(start, end, thumb=False):
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM)
    md.detail = True
    return list(md.disasm(data[offset(start):offset(end)], start))


def snippet(start, end, thumb=False):
    return {
        "mode": "Thumb" if thumb else "ARM",
        "start_va": hex(start),
        "start_nor_offset": hex(offset(start)),
        "bytes": data[offset(start):offset(end)].hex(),
        "instructions": [
            {"va": hex(i.address), "nor_offset": hex(offset(i.address)),
             "mnemonic": i.mnemonic, "operands": i.op_str}
            for i in instructions(start, end, thumb)
        ],
    }


def branch_at(address, target, thumb=False):
    i = instructions(address, address + 4, thumb)[0]
    assert i.mnemonic in ("b", "bl", "blx")
    assert i.operands[0].type == ARM_OP_IMM
    assert i.operands[0].imm == target
    return {"caller_va": hex(address), "caller_nor_offset": hex(offset(address)),
            "mode": "Thumb" if thumb else "ARM", "instruction": i.mnemonic,
            "target_va": hex(target)}


def c_string(address):
    start = offset(address)
    return data[start:data.index(b"\0", start, start + 160)].decode("ascii")


ARRAY = 0x384BB5DC
expected = [(11, 55), (10, 56), (12, 57), (13, 58), (8, 59), (9, 60)]
array_bytes = b"".join(bytes([pin, function, 0, 0]) for pin, function in expected)
assert data[offset(ARRAY):offset(ARRAY) + len(array_bytes)] == array_bytes
assert data.find(array_bytes, PAYLOAD, PAYLOAD + length) == offset(ARRAY)
pin_names = {v: k.removeprefix("HAL_IOMUX_PIN_")
             for k, v in reference["enums"]["HAL_IOMUX_PIN_T"].items()
             if k.startswith("HAL_IOMUX_PIN_P") and k != "HAL_IOMUX_PIN_NUM"}
function_names = {v: k.removeprefix("HAL_IOMUX_FUNC_")
                  for k, v in reference["enums"]["HAL_IOMUX_FUNCTION_T"].items()}

helper = instructions(0x383D780C, 0x383D781C)
assert [(i.mnemonic, i.op_str) for i in helper[:3]] == [
    ("movw", "r0, #0xb5dc"), ("mov", "r1, #6"), ("movt", "r0, #0x384b")]

chain = [
    branch_at(0x38005712, 0x383D3590, True),
    branch_at(0x383D3590, 0x383D2368),
    branch_at(0x383D2640, 0x383D780C),
    branch_at(0x383D7818, 0x383D76E4),
]
reset_calls = [branch_at(0x380044CC, 0x383D3590, True),
               branch_at(0x380045B4, 0x383D3590, True)]

report = {
    "scope": "Offline static analysis of this NOR image only; bounded, not exhaustive.",
    "input": {"path": str(NOR), "size": len(data),
              "sha256": hashlib.sha256(data).hexdigest()},
    "a7_mapping": {"header_nor_offset": hex(SEGMENT_HEADER),
                   "header_big_endian_payload_length": hex(length),
                   "payload_nor_offset": hex(PAYLOAD), "payload_va": hex(BASE),
                   "payload_end_nor_offset_exclusive": hex(PAYLOAD + length),
                   "validation": "All reported code, strings and pin array are inside this payload."},
    "finding": "The SDMMC controller-0 initialization path calls a helper that passes the six-entry array below to compact HAL pinmap initialization.",
    "pin_array": {"va": hex(ARRAY), "nor_offset": hex(offset(ARRAY)),
                  "entry_count": 6, "entry_bytes": 4, "raw_hex": array_bytes.hex(),
                  "entries": [
                      {"array_index": i, "pin_enum": pin, "pin": pin_names[pin],
                       "function_enum": function, "function": function_names[function],
                       "voltage_enum": 0, "voltage_field": "HAL_IOMUX_PIN_VOLTAGE_VIO",
                       "pull_enum": 0, "pull_field": "HAL_IOMUX_PIN_NOPULL"}
                      for i, (pin, function) in enumerate(expected)]},
    "call_chain": chain,
    "identification": {
        "open_wrapper_va": "0x383d3590",
        "host_config_va": "0x383d2368",
        "pinmux_helper_va": "0x383d780c",
        "compact_pinmap_init_va": "0x383d76e4",
        "diagnostics": [{"va": hex(a), "nor_offset": hex(offset(a)), "string": c_string(a)}
                        for a in [0x383EB068, 0x383E9EEC, 0x383E9F08,
                                  0x383E9F3C, 0x384BA9A4, 0x383EA30C]],
        "reset_path_open_calls": reset_calls,
        "reasoning": [
            "The same ARM wrapper called by the initialization path is called by the Thumb try_sw_reset function alongside explicit hal_sdmmc_open result diagnostics.",
            "The ARM host configuration body references the hal_sdmmc_host_device_cfg diagnostic name, writes controller base 0x40110000, and branches to the pinmux helper only for its controller-id argument equal to zero.",
            "The Thumb call at 0x38005712 explicitly sets r0=0 at 0x38005710 and passes its stack configuration via r1=r7+0x14.",
            "That stack configuration contains raw word fields [1, 48000000, 4]; the ARM body consumes offset 4 as the frequency value and offset 8 as a bus-width byte, comparing width to 8 and defaulting zero width to 4.",
            "The helper materializes r0=0x384bb5dc, sets r1=6, then branches to the initializer. The initializer loads pin and function bytes with an index shifted by two and applies function and pull configuration; this proves the compiled map stride is four bytes.",
            "The six pin/function values exactly match the public BEST2003 hal_iomux_set_sdmmc helper. The conclusion rests on the NOR array plus actual calls, not on public routing alone."
        ],
    },
    "code_evidence": {
        "controller_zero_open_and_stack_configuration": snippet(0x380056B4, 0x3800571C, True),
        "host_config_entry_and_controller_base": snippet(0x383D2368, 0x383D242C),
        "host_config_controller_zero_pinmux_branch": snippet(0x383D2628, 0x383D264C),
        "host_config_alternate_clock_path_rejoins_pinmux": snippet(0x383D2EF0, 0x383D2EFC),
        "pinmux_helper": snippet(0x383D780C, 0x383D781C),
        "compact_pinmap_initializer": snippet(0x383D76E4, 0x383D7774),
        "open_wrapper": snippet(0x383D3590, 0x383D3594),
        "try_sw_reset_open_and_diagnostic": snippet(0x380044C0, 0x380044EA, True),
    },
    "public_reference": {
        "repo_tree_sha": reference["source_tree_sha"],
        "helper_file": "analysis/pinout/reference/hal_iomux_best2003.c",
        "helper_lines": [1770, 1781],
        "helper_url": "https://github.com/openharmony/device_soc_bestechnic/blob/master/bes2600/liteos_m/sdk/bsp/platform/hal/best2003/hal_iomux_best2003.c#L1770",
        "enum_file": "analysis/pinout/reference/hal_iomux_best2003.h",
        "struct_file": "analysis/pinout/reference/hal_iomux.h",
        "note": "Public source enums are interpreted as byte-sized in this image because of observed ldrb/stride-four code, irrespective of the source compiler enum-size settings."
    },
    "limitations": [
        "This establishes firmware-selected logical GPIO routing on a reachable controller-0 SDMMC initialization path; it does not observe execution on hardware.",
        "It does not map the GPIOs to this board's test pads, connectors, traces or physical BGA balls.",
        "VIO is the array's voltage-domain enum; this analysis does not measure the rail voltage or prove a voltage switch occurred.",
        "The generic helper array also occurs at NOR 0xe1dbd8 outside the length-delimited A7 payload. That duplicate is not used as evidence for this call chain."
    ],
}
for group in report["code_evidence"].values():
    assert PAYLOAD <= int(group["start_nor_offset"], 16) < PAYLOAD + length
REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"report": str(REPORT), "input_sha256": report["input"]["sha256"],
                  "pins": [(x["function"], x["pin"]) for x in report["pin_array"]["entries"]],
                  "call_chain": chain}, indent=2))
