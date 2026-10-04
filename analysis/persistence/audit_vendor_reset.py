"""Offline vendor global-reset cross-check; only saved NOR/public small headers."""
from collections import deque
from pathlib import Path
import hashlib
import json
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/persistence"))
import audit_cold_recovery as n
from capstone.arm import ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC

REF = ROOT / "analysis/persistence/reference"
BASE = "https://raw.githubusercontent.com/openharmony/device_soc_bestechnic/17f61a22388e6f2fbd8fe855b0ccb298b9a3bd45/bes2600/liteos_m/sdk/bsp/platform/hal/best2003/"
manifest = []
for filename in ("hal_cmu_best2003.h", "reg_aoncmu_best2003.h"):
    path = REF / filename
    if not path.exists():
        with urllib.request.urlopen(BASE + filename, timeout=20) as response:
            path.write_bytes(response.read())
    manifest.append({"url": BASE + filename, "local": str(path.relative_to(ROOT)),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
(REF / "reset-source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

# Inspect real Thumb instruction operands and their PC-relative source literals,
# not arbitrary occurrences of peripheral-looking bytes or strings.
candidates = []
for view, first, last in (("boot", 0, 0x1a000), ("main", 0x150000, 0x825000)):
    regions = [(first, last, 0x0c000000 + first)] + n.VIEWS[view][:2]
    for file_first, file_last, mapped in regions:
        previous = deque(maxlen=18)
        for ins in n.CS.disasm(n.B[file_first:file_last], mapped):
            if not ins.id:
                previous.clear()
                continue
            if ins.mnemonic.startswith("str") and len(ins.operands) >= 2 and ins.operands[1].type == ARM_OP_MEM:
                mem = ins.operands[1].mem
                for old in reversed(previous):
                    if old.mnemonic != "ldr" or len(old.operands) < 2:
                        continue
                    dest, load = old.operands[0], old.operands[1]
                    if dest.type != ARM_OP_REG or dest.reg != mem.base or load.type != ARM_OP_MEM or load.mem.base != ARM_REG_PC:
                        continue
                    pool = ((old.address + 4) & ~3) + load.mem.disp
                    off = n.offset(pool, view)
                    if off is None:
                        continue
                    base = int.from_bytes(n.B[off:off+4], "little")
                    effective = base + mem.disp
                    if effective not in (0x400800a0, 0x400800a4, 0x400800a8, 0x4000003c):
                        continue
                    start = previous[0].address
                    candidates.append({"view": view, "store_address": hex(ins.address),
                        "file": hex(file_first+ins.address-mapped), "effective_peripheral": hex(effective),
                        "base_literal": hex(base), "code_window": n.decode(start, ins.address-start+ins.size+12, view)})
                    break
            previous.append(ins)
report = {"offline_only": True, "image": str(n.IMAGE.relative_to(ROOT)),
          "sha256": hashlib.sha256(n.B).hexdigest(), "public_sources": manifest,
          "candidates": candidates}
out = ROOT / "analysis/persistence/vendor-reset-static-evidence.json"
out.write_text(json.dumps(report, indent=2) + "\n")
print(f"Saved offline reset register instruction candidates: {len(candidates)}")
for candidate in candidates:
    print(candidate["view"], candidate["store_address"], candidate["effective_peripheral"])
