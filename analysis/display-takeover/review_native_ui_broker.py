"""Focused offline ELF/raw layout review for this panel's new UI broker.

Does not generate payload/installer inputs or communicate with the target.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "analysis/display-takeover"
sys.path.insert(0, str(ROOT / "analysis/pinout"))
import analyze_a7_peripherals as a

def sha(b):
    return hashlib.sha256(b).hexdigest()

def zstr(b, pos):
    return b[pos:b.index(0, pos)].decode("ascii")

e = (DIR / "native-ui-broker.elf").read_bytes()
raw = (DIR / "native-ui-broker.bin").read_bytes()
assert e[:7] == b"\x7fELF\x01\x01\x01"
entry = struct.unpack_from("<I", e, 24)[0]
shoff = struct.unpack_from("<I", e, 32)[0]
shsize, count, strindex = struct.unpack_from("<HHH", e, 46)
assert shsize == 40
headers = [struct.unpack_from("<10I", e, shoff + i*shsize) for i in range(count)]
strings = headers[strindex]
names = e[strings[4]:strings[4]+strings[5]]
sections = [{"name": zstr(names,h[0]), "type": h[1], "flags": h[2],
             "address": h[3], "offset": h[4], "size": h[5], "link": h[6],
             "align": h[8], "entrysize": h[9]} for h in headers]
allocated = [s for s in sections if s["flags"] & 2 and s["size"]]
assert all(s["type"] == 1 and not s["flags"] & 1 for s in allocated)
base = min(s["address"] for s in allocated)
end = max(s["address"] + s["size"] for s in allocated)
assert base == 0x3804b108 and end <= 0x3804bc98
expected = bytearray(end-base)
for s in allocated:
    expected[s["address"]-base:s["address"]-base+s["size"]] = e[s["offset"]:s["offset"]+s["size"]]
assert bytes(expected) == raw
symbols = {}
undefined = []
for s in sections:
    if s["type"] != 2:
        continue
    st = headers[s["link"]]
    snames = e[st[4]:st[4]+st[5]]
    assert s["entrysize"] == 16
    for p in range(s["offset"], s["offset"]+s["size"], 16):
        name, value, size, info, _, index = struct.unpack_from("<IIIBBH", e, p)
        if name == 0:
            continue
        name = zstr(snames, name)
        if index == 0:
            undefined.append(name)
        if info & 15 in (1,2):
            symbols[name] = {"value": hex(value), "size": size, "kind": info & 15}
assert not undefined
assert entry == int(symbols["broker_start"]["value"],16) == 0x3804b2f5
assert raw[:12] == bytes.fromhex("26204042704700bf00207047")
branch = a.Cs(a.CS_ARCH_ARM, a.CS_MODE_THUMB | a.CS_MODE_LITTLE_ENDIAN)
instruction = list(branch.disasm(raw[0x1ec:0x1f0],0x3804b2f4))
assert len(instruction) == 1 and instruction[0].mnemonic == "b.w"
assert instruction[0].op_str == "#0x3804b2f8"
assert int(symbols["broker_main"]["value"],16) == 0x3804b2f9
def prologue_stack_bytes(name):
    start = int(symbols[name]["value"],16) & ~1
    total = 0
    for ins in branch.disasm(raw[start-base:start-base+32],start):
        if ins.mnemonic in ("bl","blx"):
            break
        if ins.mnemonic.startswith("push"):
            total += 4 * len(ins.op_str.strip("{}").split(","))
        elif ins.mnemonic.startswith("sub") and ins.op_str.startswith("sp, #"):
            total += int(ins.op_str.split("#")[1],0)
        elif ins.mnemonic.startswith("str") and "[sp, #-4]!" in ins.op_str:
            total += 4
    return total
nor = a.FILE.read_bytes()
assert sha(nor) == "777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b"
registry = [
    ("vapp",0xccdcc8,0x3818f9fd,0x3804b2f5),
    ("showlogo",0xccdf20,0x3804b87d,0x3804b111),
    ("faclvgl",0xccdebc,0x3804b2f5,0x3804b111),
    ("ntpcstatus",0xccde80,0x3804b109,0x3804b109),
]
for _, offset, original, _ in registry:
    assert struct.unpack_from("<I",nor,offset)[0] == original
sources = ["native-ui-broker.c", "native-ui-broker.ld", "native-ui-broker-entry.S",
           "native-ui-broker.elf", "native-ui-broker.bin", "key3-gesture.h"]
refs = ["key3-gesture-offline-result.json", "a7-clock-gettime-abi-1.50.10.json",
        "a7-signal-action-abi-review-1.50.10.json", "startup-broker-abi-container-review-1.50.10.json",
        "a7-broker-extra-container-review-1.50.10.json", "ui-background-broker-review-1.50.10.json"]
report = {
    "scope": "Independent offline exact1.50.10 broker layout/entry/clock/GPIO/startup review. No hardware, payload or frozen-input edits. Does not approve unreviewed installer inputs.",
    "firmware_sha256": sha(nor),
    "reviewed_inputs": {n:sha((DIR/n).read_bytes()) for n in sources},
    "evidence_refs": {n:sha((DIR/n).read_bytes()) for n in refs},
    "layout": {"entry_Thumb":hex(entry),"raw_bin_bytes":len(raw),
               "allocated_section_bytes":sum(s["size"] for s in allocated),
               "raw_range_exclusive":[hex(base),hex(end)],
               "approved_container_range_exclusive":["0x3804b108","0x3804bc98"],
               "unused_container_tail_bytes":0x3804bc98-end,
               "raw_equals_ELF_allocated_sections_with_zero_gaps":True,
               "writable_allocated_sections":[],"undefined_symbols":[],
               "sections":allocated,"symbols":symbols,
               "compiled_prologue_stack_bytes":{n:prologue_stack_bytes(n) for n in ("worker","paint","timer","broker_main")}},
    "entry_checks": {"branch_bytes":raw[0x1ec:0x1f0].hex(),
                     "branch":"ThumbB.W3804b2f4->3804b2f8, not main atnon-entryhalfword",
                     "ntpcstatus":"Thumb3804b109 returns-38; existingregistrypointer preserved",
                     "showlogo":"Thumb3804b111 returns0; requiresregistryentrychange before overwrittenoriginalshowlogocanexecute"},
    "required_registry_values": [{"name":n,"NOR_offset":hex(o),"A7_address":hex(a.offset_to_address(o)),
        "original_Thumb":hex(old),"new_Thumb":hex(new),"new_bytes":struct.pack("<I",new).hex()}
        for n,o,old,new in registry],
    "intentional_effects": ["Originalshowlogo builtin isdisabledincludingnormalstartupbootlogo. Physicalboardframebufferinitialization andlaterpanel_fb_switch remainownedby originalstartup, notshowlogo.",
                            "ntpcstatus diagnostic now returns-38; NTP daemon code outside the container is untouched.",
                            "faclvgl factory diagnostic entry must become the same success no-op as showlogo; preserving its original b2f5 entry would allow a second broker launch.",
                            "Originalvappbody3818f9fd ispreservedandcalledexactlyoncebybroker; originalJS/businessservicescontinuetorunwhilecustommodefiltersGUIframe/touch."],
    "C_review": {"ctx":"Heapstate only; private384fc864 pointerpublishedbeforepthread_create withDMB; separatectx.tid outputavoidsclobberingpointer.",
                 "startup":"Workeropensindependentnonblockinginput0fd, obtainsfile*, initializesowned614400Bcanvas/paint beforeitsfirstarm_timer publication. Parentdoesnotpublishtimerproxy.",
                 "thread":"NULLpthreadattrdefault4096Bstack; compiledprologueframes recordedunderlayout, before nativecalldepths. Fullnativecalldepthisnotstaticallyboundedhere.",
                 "clock":"CLOCKThumb38004c39,id1;16B8-alignedtimespec;seconds castto32bitsbefore1000multiply,nanosecondsdivide1000000; codechecksreturn0,cancelsgestureonfailure.",
                 "GPIO":"Rawreadonly40081050 isalsoactualA7ARMHALgetteraddress, notjustMCUdebugalias; P3_1bit25active-low, otherkeysbits26/27cancelgesture.",
                 "admission":"GUI-thread installation takes broker mutex and requires exactly two native touch callbacks, original PAN/AREA slots, cleared one-shot migration flag, matching GUI mmap/defaultfbmem50000000, fblen614400, format13, 480x320 video, stride1920 and bpp32.",
                 "gesture":"Sharedreviewedheader implements40msdebounce,600msreleasedshorttap,500msgap; nofalsecountfromrepeatrelease; actualmonotonicelapsedtime.",
                 "pixels":"Countmaxuint32 needs10digits plus11prefix chars:21charsfits22Btext; renderx/yremainwithin480x320;whiteglyphffffffff.",
                 "exit":"Wrapperdoesnotchange signals or stop/destroy/reenteroriginal;alive0 thenrestoresstaticPAN/AREA underbrokermutex;ctx/canvasarenotfreed. Pollinterval20ms isnotahardthreadexitdeadline.",
                 "resource_failure":"Allocation/createfailuresfallbacktooriginal;workerinputfailureleavesoriginalunhooked but retainsheapallocation. No automaticretry/restart."},
    "GPIO_instruction_evidence": a.disassemble(nor,a.address_to_offset(0x383d49f8),0x28,"ARM"),
    "limits": ["Hardwarehotswitchroundtrip, publisherfreeze/PANlockinteractions, GUIcompleteframeonreturn andinputfilteringremainruntimevalidationrequirements.",
               "Thisreportcheckscompiledlayoutanddeclaredregistryvalues; rootmustindependentlycomparewholenewtwo-sectorinputsandinstallbaseline.",
               "Originalapplicationexit/signalhandlerlifecycleproblemisunchanged; retainedallocationspreventnewallocationUAFbutdonotrepairoriginalframeworkteardown.",
               "The raw GPIO watcher does not suppress original MCU key notifications. The user reports key3 currently unbound; adding a stock binding later can still trigger its original action on each tap."],
}
out = DIR / "native-ui-broker-independent-review-1.50.10.json"
out.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"report":str(out.relative_to(ROOT)),"report_sha256":sha(out.read_bytes()),
                  "bin_sha256":sha(raw),"raw_bytes":len(raw),"end_exclusive":hex(end)}))
