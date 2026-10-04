"""Read only saved firmware; isolate boot/recovery/main RAM ownership.

Addresses are decoded for the selected image, never with main's SRAM map while
examining boot or recovery. No debug/target interfaces or raw logs are imported.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/wifi/python-packages"))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_MCLASS
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_REG_PC

IMAGE = ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin"
B = IMAGE.read_bytes()
CS = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
CS.detail = True
CS.skipdata = True
VIEWS = {
    "boot": [(0x2220,0x5b58,0x200001a8),(0x5b58,0xbf04,0x20003c20),(0xbf04,0xbf70,0x34000000)],
    "recovery": [(0x42168,0xb6f7c,0x200001a8),(0xb6f7c,0xb79b8,0x200750e0),(0xb79b8,0xbcfbc,0x34000000)],
    "main": [(0x1520b8,0x15608c,0x200001a8),(0x15608c,0x17fe78,0x200042c0),(0x17fe78,0x181ed8,0x200f5f00),(0x182924,0x19be20,0x34000000)]
}

def offset(address,view):
    address &= ~1
    if 0x00200000 <= address < 0x00300000:
        address += 0x1fe00000
    for first,last,dest in VIEWS[view]:
        if dest <= address < dest+last-first:
            return first+address-dest
    for base in (0x0c000000,0x2c000000,0x28000000):
        if base <= address < base+len(B):
            return address-base
    return None

def decode(address,size,view):
    p=offset(address,view)
    if p is None:
        raise ValueError("Unmapped code address")
    result=[]
    for i in CS.disasm(B[p:p+size],address):
        record={"address":hex(i.address),"file_offset":hex(p+i.address-address),
                "bytes":i.bytes.hex(),"mnemonic":i.mnemonic,"operands":i.op_str}
        for o in i.operands if i.id else []:
            if o.type==ARM_OP_MEM and o.mem.base==ARM_REG_PC:
                pool=((i.address+4)&~3)+o.mem.disp
                pool_off=offset(pool,view)
                if pool_off is not None:
                    value=struct.unpack_from("<I",B,pool_off)[0]
                    record["literal"]={"pool":hex(pool),"value":hex(value)}
        result.append(record)
    return result

def print_window(address,size,view):
    for i in decode(address,size,view):
        lit=i.get("literal")
        note=f" ; pool{lit['pool']}={lit['value']}" if lit else ""
        print(f"{i['address']} {i['mnemonic']:9} {i['operands']}{note}")

if __name__=="__main__":
    if len(sys.argv)>1:
        print_window(int(sys.argv[1],0),int(sys.argv[2],0),sys.argv[3])
    else:
        report={"offline_only":True,"image":str(IMAGE.relative_to(ROOT)),"sha256":hashlib.sha256(B).hexdigest(),
                "ownership_views":{k:[{"file_start":hex(a),"file_end":hex(z),"ram_start":hex(d),"bytes":z-a} for a,z,d in v] for k,v in VIEWS.items()},
                "evidence_windows":[]}
        for name,address,size,view in (
            ("boot_startup_copy_and_init",0x0c00018c,0x140,"boot"),
            ("boot_before_main_nor_open_state_gate",0x0c01043c,0x94,"boot"),
            ("boot_system_init_nor_init_call",0x0c00201c,0x7c,"boot"),
            ("boot_nor_init_veneer",0x0c002148,8,"boot"),
            ("boot_nor_init_default_cfg_and_open",0x20001380,0x24,"boot"),
            ("boot_nor_open_wrapper",0x20001038,0x14,"boot"),
            ("boot_nor_open_jedec_and_context_initialization",0x20000bc0,0x520,"boot"),
            ("boot_native_jedec",0x20001cf8,0x28,"boot"),
            ("recovery_main_magic_gate_before_own_startup",0x0c041ef0,0x40,"recovery"),
            ("recovery_startup_copy_and_init",0x0c040190,0x140,"recovery")):
            report["evidence_windows"].append({"name":name,"view":view,"instructions":decode(address,size,view)})
        out=ROOT/"analysis/persistence/cold-recovery-static-evidence.json"
        out.write_text(json.dumps(report,indent=2)+"\n")
        print("Saved boot/recovery/main ownership and bounded code evidence; no target access")
