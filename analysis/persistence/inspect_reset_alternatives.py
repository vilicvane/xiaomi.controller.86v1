"""Offline bounded alternatives to GLOBAL reset; no target interfaces."""
from pathlib import Path
import io
import json
import struct
import sys
import urllib.request

from audit_cold_recovery import ROOT, B, decode, offset, CS
sys.path.insert(0, str(ROOT / "analysis/persistence/python-packages"))
from elftools.elf.elffile import ELFFile
from capstone.arm import ARM_OP_MEM, ARM_OP_REG, ARM_OP_IMM, ARM_REG_PC

REF = ROOT / "analysis/persistence/reference"
base = "https://raw.githubusercontent.com/openharmony/device_soc_bestechnic/17f61a22388e6f2fbd8fe855b0ccb298b9a3bd45/bes2600/liteos_m/sdk/bsp/platform/hal/"
header = REF / "hal_bootmode.h"
if not header.exists():
    header.write_bytes(urllib.request.urlopen(base + "hal_bootmode.h", timeout=20).read())

archive = (REF / "libbest2600w_liteos.a").read_bytes()
assert archive[:8] == b"!<arch>\n"
members = []
pos = 8
names = b""
while pos + 60 <= len(archive):
    head = archive[pos:pos+60]
    size = int(head[48:58])
    name = head[:16].decode().strip()
    payload = archive[pos+60:pos+60+size]
    if name == "//":
        names = payload
    elif name.startswith("/") and name[1:].isdigit():
        first = int(name[1:])
        name = names[first:names.find(b"/\n", first)].decode()
    else:
        name = name.rstrip("/")
    if payload.startswith(b"\x7fELF"):
        elf = ELFFile(io.BytesIO(payload))
        symtab = elf.get_section_by_name(".symtab")
        if symtab:
            relevant = [s for s in symtab.iter_symbols() if s.name.startswith("hal_sw_bootmode") or s.name == "hal_cmu_get_bootmode_addr"]
            if relevant:
                symbols = []
                for s in relevant:
                    sec = elf.get_section(s["st_shndx"]) if isinstance(s["st_shndx"], int) else None
                    symbols.append({"name": s.name, "size": s["st_size"], "section": sec.name if sec else s["st_shndx"],
                                    "bytes": sec.data()[(s["st_value"] & ~1):(s["st_value"] & ~1)+s["st_size"]].hex() if sec else None})
                members.append({"member": name, "symbols": symbols})
    pos += 60 + size + (size & 1)

candidates = []
calls = []
call_targets = {"boot": {0x0c001e40:"bootmode_get",0x0c001e50:"bootmode_set",0x0c001e70:"bootmode_clear"},
                "main": {0x0c151dd0:"bootmode_get",0x0c151de0:"bootmode_set",0x0c151e00:"bootmode_clear",0x0c5caa68:"reset_pulse"}}
for view, first, last in (("boot", 0, 0x1a000), ("main", 0x150000, 0x825000)):
    for start, end, mapped in [(first, last, 0x0c000000+first)] + [(a,z,d) for a,z,d in __import__('audit_cold_recovery').VIEWS[view][:2]]:
        previous = []
        for ins in CS.disasm(B[start:end], mapped):
            if not ins.id:
                previous = []
                continue
            if ins.mnemonic in ("bl", "b.w") and ins.operands and ins.operands[0].type == ARM_OP_IMM:
                target = ins.operands[0].imm
                if target in call_targets[view]:
                    begin = previous[-16].address if len(previous)>=16 else previous[0].address
                    calls.append({"view":view,"address":hex(ins.address),"target":hex(target),"role":call_targets[view][target],
                                  "instructions":decode(begin,ins.address-begin+ins.size+0x18,view)})
            if ins.mnemonic.startswith("ldr") and len(ins.operands) >= 2:
                dst, mem = ins.operands[:2]
                if mem.type == ARM_OP_MEM and mem.mem.base == ARM_REG_PC:
                    pool = ((ins.address+4)&~3) + mem.mem.disp
                    p = offset(pool, view)
                    if p is not None:
                        value = struct.unpack_from("<I", B, p)[0]
                        if value == 0x40080038:
                            candidates.append({"view": view, "address": hex(ins.address), "direct_bootmode_literal": True,
                                               "instructions": decode(ins.address, 0x20, view)})
            if ins.mnemonic.startswith(("str", "ldr")) and len(ins.operands) >= 2:
                mem = ins.operands[1]
                if mem.type == ARM_OP_MEM and mem.mem.disp == 0x38:
                    for old in reversed(previous[-16:]):
                        if old.mnemonic == "ldr" and len(old.operands) >= 2 and old.operands[0].type == ARM_OP_REG and old.operands[0].reg == mem.mem.base:
                            load = old.operands[1]
                            if load.type == ARM_OP_MEM and load.mem.base == ARM_REG_PC:
                                pool = ((old.address+4)&~3)+load.mem.disp
                                p = offset(pool,view)
                                if p is not None and struct.unpack_from("<I",B,p)[0] == 0x40080000:
                                    begin = previous[-16].address if len(previous)>=16 else previous[0].address
                                    candidates.append({"view":view,"address":hex(ins.address),"aon_bootmode_offset":True,
                                                       "instructions":decode(begin,ins.address-begin+ins.size+8,view)})
                                    break
            previous.append(ins)
            previous = previous[-16:]

out = ROOT / "analysis/persistence/reset-alternative-static-evidence.json"
out.write_text(json.dumps({"offline_only":True,"bootmode_header":str(header.relative_to(ROOT)),
                          "bootmode_header_url":base+"hal_bootmode.h", "sdk_symbols":members,
                          "current_firmware_bootmode_candidates":candidates,"current_firmware_bootmode_calls":calls,
                          "main_reset_pulse":decode(0x0c5caa68,0x9c,"main"),
                          "boot_reset_set":decode(0x0c0122a0,0x70,"boot"),
                          "boot_reset_clear":decode(0x0c012310,0x90,"boot")},indent=2)+"\n")
print(f"Saved bounded reset/BOOTMODE evidence: {len(candidates)} firmware candidates, {len(members)} public SDK symbol members; no target access")
for item in candidates:
    print(item["view"], item["address"], "BOOTMODE")
for member in members:
    print("SDK member", member["member"], [s["name"] for s in member["symbols"]])
print("Targeted BOOTMODE/reset_pulse call sites",len(calls))
for item in calls:
    if item["role"] in ("bootmode_set", "reset_pulse"):
        print(item["view"],item["address"],item["role"])
