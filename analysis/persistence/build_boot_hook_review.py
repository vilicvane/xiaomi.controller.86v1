"""Prepare reviewable local artifacts for a two-sector MCU boot-hook test.

No device access or Flash commands. The assembled object files must have no
relocations; branch targets and changes are independently decoded below.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "analysis/wifi/python-packages"))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS

IMAGE = ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin"
data = IMAGE.read_bytes()
assert hashlib.sha256(data).hexdigest() == "777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b"
old = (ROOT / "backups/mi-panel-flash-16m-20261003.bin").read_bytes()
decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
decoder.detail = True

def instructions(raw, base):
    return [{"address": hex(i.address), "bytes": i.bytes.hex(), "mnemonic": i.mnemonic, "operands": i.op_str}
            for i in decoder.disasm(raw, base)]

stub = (OUT / "boot-hook-1.50.10.bin").read_bytes()
call = (OUT / "boot-hook-call-1.50.10.bin").read_bytes()
assert len(stub) == 32 and len(call) == 4
assert struct.unpack_from("<2I", stub, 20) == (0xe000edf8, 0x4b4f4f48)
assert stub[28:] == b"\xff" * 4
assert data[0x824400:0x824420] == b"\xff" * 32
original_call = list(decoder.disasm(data[0x150056:0x15005a], 0x0c150056))
patched_call = list(decoder.disasm(call, 0x0c150056))
stub_code = list(decoder.disasm(stub[:18], 0x0c824400))
assert len(original_call) == len(patched_call) == 1
assert original_call[0].mnemonic == patched_call[0].mnemonic == "bl"
assert original_call[0].operands[0].imm == 0x0c5d6538
assert patched_call[0].operands[0].imm == 0x0c824400
assert stub_code[-1].mnemonic == "b.w" and stub_code[-1].operands[0].imm == 0x0c5d6538
assert [i.mnemonic for i in stub_code] == ["push", "ldr", "ldr", "str", "dsb", "pop", "b.w"]
assert data[0x82433c:0x8e0000] == b"\xff" * (0x8e0000 - 0x82433c)

sector_reports = []
for base, offset, replacement in [(0x150000, 0x150056, call), (0x824000, 0x824400, stub)]:
    original = data[base:base + 0x1000]
    patched = bytearray(original)
    local_off = offset - base
    patched[local_off:local_off + len(replacement)] = replacement
    changed = [base + i for i, (a, b) in enumerate(zip(original, patched)) if a != b]
    assert all(offset <= p < offset + len(replacement) for p in changed)
    original_path = OUT / f"boot-hook-original-sector-{base:06x}.bin"
    patched_path = OUT / f"boot-hook-patched-sector-{base:06x}.bin"
    original_path.write_bytes(original)
    patched_path.write_bytes(patched)
    sector_reports.append({"NOR_offset": hex(base), "length": 4096,
                           "original": str(original_path.relative_to(ROOT)), "original_sha256": hashlib.sha256(original).hexdigest(),
                           "patched": str(patched_path.relative_to(ROOT)), "patched_sha256": hashlib.sha256(patched).hexdigest(),
                           "changed_byte_count": len(changed), "changed_byte_offsets": [hex(x) for x in changed]})

def window(offset, length):
    return {"file_offset": hex(offset), "execute_address": hex(0x0c000000 + offset),
            "instructions": instructions(data[offset:offset + length], 0x0c000000 + offset)}

partitions = []
for i, expected in enumerate(("ota_b", "ota", "ota_info", "ap", "a7", "misc_etc")):
    p = 0x6257ec + i * 0x74
    name = data[p:p+0x68].split(b"\0", 1)[0].decode("ascii")
    assert name == expected
    start, length = struct.unpack_from("<2I", data, p + 0x68)
    partitions.append({"name": name, "entry_file_offset": hex(p), "start_field": hex(start), "length_field": hex(length),
                       "unit_bytes": 0x100, "NOR_offset": hex(start * 0x100), "length_bytes": hex(length * 0x100)})

headers = []
for p in (0, 0x40000, 0xc0000, 0x150000):
    magic, security, version, reserved, info = struct.unpack_from("<IHHII", data, p)
    assert magic == 0xbe57ec1c and security == 0 and version == 4
    headers.append({"NOR_offset": hex(p), "magic": hex(magic), "security_field": security, "header_version": version,
                    "reserved": reserved, "build_info_pointer": hex(info)})

report = {
    "status": "Offline artifacts ready for review; no device read/write or execution. Persistence has not been tested.",
    "image": {"path": str(IMAGE.relative_to(ROOT)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
    "scope": "Redirect one existing MCU startup BL to a32-byte trampoline. It writes a fixed non-secret signature to DCRDR, preserves startup arguments/flags/LR, and continues the original MCU software entry. This is a persistent entry-hook proof, not complete custom firmware.",
    "boot_chain": {
        "first_stage_unchanged_from_1.48.5": data[:0x40000] == old[:0x40000],
        "first_stage_jump": "0x0c01027c chooses recovery0x40000 or0xc0000;0x0c0102b8..d4 constructs execute_alias+0x10|1 and BLX.",
        "recovery_b_entry": "0x0c040010 BL0x0c041ef0", "recovery_entry": "0x0c0c0010 BL0x0c0c1ef0",
        "normal_main_gate": "Both recovery functions check reset mode, read magic at0x28150000, compare0xbe57ec1c, call interrupt/reset preparation, then BX literal0x0c150011.",
        "prep_call": "0x0c04009c /0x0c0c009c: writes all-ones to NVIC ICER registers, clears SysTick TICKINT bit, sets SCB VTOR=0. No image CRC/hash/signature read in this complete small function.",
        "gate_limit": "The complete bounded reset-mode/main-jump path has a magic check and no full-image CRC/hash/signature call. This does not rule out earlier ROM/eFuse enforcement, another recovery path, or metadata/integrity checks elsewhere.",
        "headers": headers, "main_build_CRC32_OF_IMAGE": "0x00000000",
        "header_limit": "A zero security field and CRC placeholder do not prove unsigned-image acceptance. The header does not provide a resolved image-length/hash bound here."
    },
    "hook_location": {
        "redirect_file_offset": "0x150056", "redirect_execute_address": "0x0c150056",
        "original_instruction_bytes": data[0x150056:0x15005a].hex(), "original_destination": "0x0c5d6538",
        "new_instruction_bytes": call.hex(), "new_destination": "0x0c824400",
        "LR_preserved_at_original_destination": "0x0c15005b: BL to trampoline sets the same return address as the original BL; the trampoline never changes LR and tail-branches.",
        "startup_before_hook": "MSP=0x200d5e00, MSPLIM=0x200d51fc, CONTROL=0. Vector initialization, system initialization,0x100-byte SRAM RW copy and BSS zero complete before this BL.",
        "first_sector_padding": "No run of16 or more00/FF bytes in0x150000..0x1520b8. The apparent8-byte NOP region at0x150078 belongs to the default exception handler and is referenced by the vector table, so it is excluded.",
        "payload_file_offset": "0x824400", "payload_execute_address": "0x0c824400", "payload_slot_bytes": 32,
        "payload_sector": "0x824000", "current_main_last_nonFF": "0x82433b",
        "tail_sector_evidence": "Initial startup RW source0x824118..0x824218 and main build-info at0x824218 share this existing main-image sector.0x82433c..0x8e0000 isFF in the current backup; proposed slot lies within the already-used tail sector, not in a new unknown sector.",
        "ownership_boundary": "Current partition table places0x824400 inside ap[0x150000,0x8e0000). Current image and startup copy ranges do not consume the slot. No exact linker map was available, so a reserved post-image function or future OTA use is not categorically excluded. Any OTA can replace this test."
    },
    "trampoline": {
        "assembly": "analysis/persistence/boot-hook-1.50.10.S", "binary": "analysis/persistence/boot-hook-1.50.10.bin",
        "assembly_tool": "WSL LLVM MC thumbv8m.main-none-eabi; LLVM readobj reports zero relocations; LLVM objcopy extracted.text",
        "bytes": stub.hex(), "instructions": instructions(stub[:18], 0x0c824400),
        "marker_register": "0xe000edf8", "marker_value": "0x4b4f4f48",
        "effects": "Temporary8-byte MSP stack use; r0/r1 restored; r2-r12/LR unchanged; PUSH/LDR/STR/DSB/POP/B.W do not alter APSR. One32-bit DCRDR write. No Flash write, peripheral-clock/reset change, filesystem call, loop, or delay in the payload.",
        "argument_flag_note": "The stub preserves the original BL caller's register and APSR values, including LR. Tail B.W preserves Thumb state and uses the original destination.",
        "DCRDR_limit": "DCRDR is a debug data register, not unowned application RAM. Software write/read/restore must first be demonstrated with the established temporary RAM-program mechanism. Core-register transfers through DCRSR/DCRDR or later debugger activity overwrite it; inspect by MEM-AP without DCRSR transfers after the boot.",
        "firmware_use_check": "Exact little-endian DCRDR0xe000edf8 and CoreDebug base0xe000edf0 literals were not found in the MCU image range. Computed addresses remain possible; this negative literal search is only a clue, not proof of no firmware use."
    },
    "sectors": sector_reports,
    "rollback": {
        "complete_flash_restore_bytes": "Exactly the original4096bytes for sectors0x150000 and0x824000 from the named files, after a fresh preflight matches their original hashes. Restore whole sectors, not only the changed instruction bytes, because NOR requires erase/program granularity.",
        "patch_order_if_later_authorized_and_programming_validated": "Program and readback the payload sector first while entry remains original; then program/readback the entry sector. Restore entry sector first, then payload sector. Maintain the NOR agent's validated RAM-loader/CPU/cache/protection recovery procedure throughout.",
        "DCRDR_restore": "Restore any preserved DCRDR value after the observation; reboot alone is not asserted to restore a debugger's prior data state.",
        "boot_failure_limit": "Preserved boot/recovery bytes do not prove automatic rollback: recovery still jumps a magic-valid damaged main image. An independently working programming/restore path is required before changing either sector."
    },
    "validation_still_required": [
        "RAM-only DCRDR write/read/restore without disturbing core register state",
        "Fresh exact readback of both original sectors and current firmware fingerprint",
        "Actual NOR geometry/erase/program/protection/cache handling and restoration method established by the NOR agent",
        "No earlier secure-boot/integrity enforcement rejects the changed main image",
        "Cold-boot signature observation through MEM-AP before any DCRSR transfers, and normal original-firmware boot/user control afterward"
    ],
    "partition_table": partitions,
    "code_evidence": [window(0x1027c, 0x60), window(0x40010, 4), window(0x41ef0, 0x34), window(0x4009c, 0x28),
                      window(0xc1ef0, 0x34), window(0xc009c, 0x28), window(0x150010, 0x4a)],
    "target_operations": 0, "credential_values_or_credential_hashes_saved": False
}
(OUT / "boot-hook-review-1.50.10.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"report": "analysis/persistence/boot-hook-review-1.50.10.json", "sectors": [{"offset": x["NOR_offset"], "changed_bytes": x["changed_byte_count"]} for x in sector_reports], "trampoline_bytes": len(stub), "branch_targets_capstone_verified": True, "target_operations": 0}))
