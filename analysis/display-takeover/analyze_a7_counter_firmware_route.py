"""Offline counter-app entry/container and private framebuffer ABI evidence.

Uses only saved 1.50.10 NOR and the already captured display object.
No target API, hardware access, credential data, or image modification.
"""
import hashlib
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis/display-takeover"
spec = importlib.util.spec_from_file_location("a7", ROOT / "analysis/pinout/analyze_a7_peripherals.py")
a7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a7)
image = a7.FILE.read_bytes()
SHA = "777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b"
assert hashlib.sha256(image).hexdigest() == SHA
length = int.from_bytes(image[0x8e0000:0x8e0004], "big")
END = a7.START + length
assert length == 0x4f3fe0 and END == 0xdd3fe4


def words(va, count):
    return struct.unpack_from("<" + "I" * count, image, a7.address_to_offset(va))


def code(name, va, size, mode="Thumb"):
    off = a7.address_to_offset(va)
    assert a7.START <= off < off + size <= END
    return {"name": name, "address": hex(va), "file_offset": hex(off), "mode": mode,
            "bytes_sha256": hashlib.sha256(image[off:off + size]).hexdigest(),
            "instructions": a7.disassemble(image, off, size, mode)}


def string(va):
    off = a7.address_to_offset(va)
    end = image.index(b"\0", off, min(off + 256, END))
    return image[off:end].decode("ascii")


vapp = words(0x383edcb8, 5)
factory = words(0x383edeac, 5)
assert vapp == (0x383ed9f4, 100, 0x20000, 0x3818f9fd, 0)
assert factory == (0x383edaf0, 100, 0x8000, 0x3804b2f5, 0)
assert string(vapp[0]) == "vapp" and string(factory[0]) == "faclvgl"

# Verify current A7 rcS against NOR itself, not merely an old extraction path.
rcs_off, rcs_len = 0xcce6e4, 2115
rcs = image[rcs_off:rcs_off + rcs_len]
rcs_path = OUT / "romfs-1.50.10/image-00cce4f4/init.d/rcS"
assert rcs == rcs_path.read_bytes()
rcs_text = rcs.decode("utf-8")
startup_lines = []
for number, line in enumerate(rcs_text.splitlines(), 1):
    if any(x in line for x in ("showlogo ", "pns &", "panel_apps &", "midess_adv &",
                              "panel_fb_switch ", "vapp ", "faclvgl &")):
        startup_lines.append({"line": number, "text": line.strip()})

# Conservative bounded container reference scan; mixed ARM/Thumb candidates
# must be validated in their real ISA. Linear ARM scanning through Thumb code
# produces false BL/B matches, which remain documented rather than omitted.
LO, HI = 0x3804b2f4, 0x3804b87c
targets = {va: f"faclvgl_main+{hex(va - LO)}" for va in range(LO, HI, 2)}
direct = a7.find_direct_calls(image, END, targets, include_jumps=True)
external = [x for x in direct if not LO <= int(x["address"], 16) < HI]
assert external and all(x["mode"] == "ARM" for x in external)
false_windows = [code("ARM_scan_false_positive_Thumb_context", int(x["address"], 16) - 4, 16)
                 for x in external]
pointer_refs = []
for off in range(a7.START, END - 3, 4):
    ptr = struct.unpack_from("<I", image, off)[0]
    if LO <= (ptr & ~1) < HI:
        pointer_refs.append({"file_offset": hex(off), "address": hex(a7.offset_to_address(off)),
                             "pointer": hex(ptr)})
assert pointer_refs == [{"file_offset": "0xccdebc", "address": "0x383edeb8", "pointer": "0x3804b2f5"}]
mov_refs = a7.find_xrefs(image, END, {**targets, **{va | 1: name for va, name in targets.items()}})
external_mov = [x for x in mov_refs if not LO <= a7.offset_to_address(int(x["movw_offset"], 16)) < HI]
assert not external_mov
short_refs = []
for va in range(LO - 2048, HI + 2048, 2):
    if LO <= va < HI:
        continue
    half = struct.unpack_from("<H", image, a7.address_to_offset(va))[0]
    if half & 0xf800 == 0xe000:
        immediate = half & 0x7ff
        immediate -= 0x800 if immediate & 0x400 else 0
    elif half & 0xf000 == 0xd000 and half & 0x0f00 < 0x0e00:
        immediate = half & 255
        immediate -= 256 if immediate & 128 else 0
    else:
        continue
    target = va + 4 + (immediate << 1)
    if LO <= target < HI:
        short_refs.append({"address": hex(va), "target": hex(target)})
assert not short_refs

live_path = ROOT / "backups/display-takeover/a7-fb-object.bin"
live = live_path.read_bytes()
plane = struct.unpack_from("<IIHBB4I", live, 0x54)
assert plane == (0x50000000, 614400, 1920, 0, 32, 480, 320, 0, 0)
assert words(0x384ef84c, 2) == (0x383de558, 0x383de4a8)

windows = [
    code("vapp_task_entry", 0x3818f9fc, 0x170),
    code("faclvgl_container_and_next_prologue", LO, HI - LO + 8),
    code("physical_input_setup_and_worker", 0x38006570, 0x54),
    code("framebuffer_registration_then_nsh_spawn", 0x380065f0, 0x120),
    code("board_framebuffer_init_branch", 0x3800727c, 0x3e),
    code("panel_fb_switch_one_shot_migration", 0x38048d74, 0x2b4),
    code("getvideoinfo", 0x383de558, 0xb4, "ARM"),
    code("getplaneinfo", 0x383de4a8, 0xb0, "ARM"),
    code("pandisplay_source_rotate_queue_and_special_migration", 0x383df2dc, 0x198, "ARM"),
    code("vblank_staging_swap_and_source_token", 0x383decbc, 0x5c, "ARM"),
    code("free_staging_slot", 0x383de804, 0xe4, "ARM"),
    code("driver_initialized_flag_entry", 0x383df4d0, 0x60, "ARM"),
    code("driver_initialized_flag_completion", 0x383df804, 0xb8, "ARM"),
    code("nanosleep_timespec_12B", 0x38042130, 0x128),
] + false_windows
evidence_path = OUT / "a7-counter-firmware-route-code-evidence-1.50.10.json"
evidence_path.write_text(json.dumps(windows, indent=2), encoding="utf-8")

report = {
    "scope": "Offline saved-binary evidence only; no hardware read/write or persistent patch executed by this analysis.",
    "firmware": {"path": str(a7.FILE.relative_to(ROOT)), "sha256": SHA,
                 "payload_file_start": hex(a7.START), "payload_file_end_exclusive": hex(END),
                 "payload_runtime_base": "0x38000000", "payload_length": hex(length),
                 "limit": "Do not extend copy length: initialized payload ends 384f3fe0; nearby rounded BSS begins 384f4000."},
    "normal_entry": {
        "command": "vapp", "descriptor": "0x383edcb8", "entry_pointer_address": "0x383edcc4",
        "entry_pointer_file_offset": "0xccdcc8", "original_callable": "0x3818f9fd",
        "abi": "int main(int argc, char **argv); Thumb; called as an ordinary builtin task",
        "priority": 100, "stack_bytes": 131072,
        "replacement_candidate": "Replace descriptor entry only with 3804b2f5 after replacing the entire original faclvgl_main container with the compiled counter main; ignore argc/argv. Original vapp JS/UI entry is not invoked.",
    },
    "code_container": {
        "original_command": "faclvgl", "range": [hex(LO), hex(HI)], "size_bytes": HI - LO,
        "file_range": [hex(a7.address_to_offset(LO)), hex(a7.address_to_offset(HI))],
        "next_function_prologue": hex(HI), "instruction_set": "Thumb",
        "aligned_pointer_refs": pointer_refs, "external_Thumb_direct_long_branches": [],
        "external_short_branch_candidates": short_refs, "external_MOVW_MOVT_refs": external_mov,
        "discarded_wrong_ISA_ARM_candidates": external,
        "confidence_limit": "Reference scans and complete function/next-prologue disassembly identify a replacement candidate, not a proof against every computed indirect pointer. Only faclvgl's builtin entry has a stored pointer into this bounded region. Replacing this container also replaces factory faclvgl behavior; leave factory files/boot logic intact.",
        "capacity_gate": "Whole linked code, rodata, literal pools and alignment must fit 1416 bytes; no original internal helper is retained. Exact original bytes/sector backups and hashes remain mandatory for parent installer/revert.",
    },
    "driver_startup": {
        "current_rcS": {"file": str(rcs_path.relative_to(ROOT)), "NOR_data_offset": hex(rcs_off),
                        "length": rcs_len, "sha256": hashlib.sha256(rcs).hexdigest(), "lines": startup_lines},
        "board_physical_input": "3800657a registers physical lower driver; 380065b2 starts worker 380211b9 before NSH creation.",
        "board_fb_initialization": "380072b2 calls ARM driver init383df4d0, then branches back380065f0 for getter/registration. 380066e4 subsequently creates NSH task which executes rcS.",
        "initialized_flag": {"address": "0x38641232", "expected": 1,
                             "evidence": "383df4e0 reads flag;383df8a8/8ac writes byte1 only after setup."},
        "migration_command": "panel_fb_switch waits for property/timeout, calls ioctl2816 with source=-1 once, closes fd and returns before rcS invokes vapp. It is not a continuing display producer.",
        "direct_callback_precondition": "At the normal vapp entry, board framebuffer registration/init and the synchronous panel_fb_switch have already run. Query/validate initialized flag, video/plane geometry, vtable callback addresses. No extra fb open, LVGL init, repeated driver init or second source=-1 relocation is needed for direct callbacks.",
        "normal_services": "Keep A7 scheduling, touch worker, interrupts/vblank and existing rcS services active. Do not halt A7 for the counter loop.",
    },
    "framebuffer_ABI": {
        "object": "0x384ef84c", "instruction_set": "ARM (even callable addresses; invoke with interworking BLX)",
        "getvideoinfo": {"callable": "0x383de558", "signature": "int(gdev*, uint8_t video[8])", "success": 0,
                         "fields": {"fmt": "u8+0", "xres": "u16+2", "yres": "u16+4", "nplanes": "u8+6"}},
        "getplaneinfo": {"callable": "0x383de4a8", "signature": "int(gdev*, unsigned planeno=0, uint8_t plane[28])", "success": 0},
        "plane_layout": [
            {"name": "fbmem", "offset": 0, "type": "u32 pointer"},
            {"name": "fblen", "offset": 4, "type": "u32"},
            {"name": "stride", "offset": 8, "type": "u16"},
            {"name": "display", "offset": 10, "type": "u8"},
            {"name": "bpp", "offset": 11, "type": "u8"},
            {"name": "xres_virtual", "offset": 12, "type": "u32"},
            {"name": "yres_virtual", "offset": 16, "type": "u32"},
            {"name": "xoffset", "offset": 20, "type": "u32"},
            {"name": "private_source_pointer / nominal yoffset", "offset": 24, "type": "u32"}],
        "captured_geometry": {"fmt": 13, "width": 480, "height": 320, "bpp": 32,
                              "stride": 1920, "fblen": 614400, "snapshot": str(live_path.relative_to(ROOT))},
        "pandisplay": {"callable": "0x383df2dc", "signature": "int(gdev*, const uint8_t plane[28])",
                       "success": 0, "busy_or_queue_failure": -1,
                       "source_0": "Use current gdev+54 logical buffer",
                       "source_ffffffff": "Special one-time relocation: memcpy old fbmem to50000000, free old fbmem, update globals; never pass for custom owned source",
                       "source_nonzero_other": "Treat +24 as actual readable pointer to614400 logical pixels; synchronously rotate480x320 into reserved staging slot, then queue that slot",
                       "field_limit": "The actual PAN implementation does not read caller fbmem/stride/dimensions to select/layout source; it hardcodes480x320. Keep the queried fields and set +24=ownedbuffer; +0 may also match ownedbuffer for a consistent description.",
                       "lifetime": "Rotation reads source synchronously before PAN returns. Vblank scans staging, not malloc source; queued +4/source token is copied to gdev+6c on presentation. Keep malloc buffer alive for entire app; there is no source-free operation in normal PAN path.",
                       "retry": "If return-1, keep dirty flag and owned buffer, nanosleep10ms then retry; do not busy-spin or increment count again. Successful enqueue does not mean the frame is already visible.",
                       "staging": "Two reserved rotated buffers; vblank frees prior displayed slot. Only one app task modifies its own source and calls PAN, so render does not race its synchronous copy."},
        "ioctl_numbers_target_only": {"GETVIDEO": "0x2801", "GETPLANE": "0x2802", "PAN": "0x2816",
                                      "limit": "Target's historical private ABI; current public headers use different values. Direct callbacks bypass this mismatch."},
    },
    "normal_task_calls": {
        "malloc": {"callable": "0x383d9421", "signature": "void*(uint32_t bytes)", "size": 614400},
        "nanosleep": {"callable": "0x38042131", "signature": "int(const void *req12B, void *rem_or_NULL)",
                      "req_layout": "signed seconds64@0; signed nanoseconds32@8; [0,0,10000000] words for10ms", "rem": 0,
                      "limit": "Shell usleep38022871 is argc/argv command main, not a callable POSIX usleep(usec)."},
        "open": {"callable": "0x3802c901", "path": "/dev/input0", "flags": "0x41 (target readonly1|nonblock40)"},
        "fd_to_file": {"callable": "0x38025679", "signature": "int(fd, void **out_file)"},
        "file_read": {"callable": "0x3802954d", "signature": "ssize_t(file*, void *buffer, uint32_t count32)",
                      "event_length": 32, "negative_EAGAIN": -11},
        "input_event": {"npoints": "u32@0", "id": "u8@8", "flags": "u8@9", "xy": "i16@10/12", "timestamp_us": "u64@24",
                        "flags": {"DOWN": 1, "MOVE": 2, "UP": 4, "ID_VALID": 8, "POS_VALID": 16},
                        "counting": "Use pressed latch: UP clears it; DOWN/MOVE only increment on released-to-pressed. Repeated DOWN while held is emitted by actual worker and must not increase counter."},
        "source": "analysis/display-takeover/a7-scheduled-counter-app-review-1.50.10.json and analysis/pinout/a7-touch-input-route-1.50.10.json",
    },
    "minimal_program_flow": [
        "Normal builtin task enters replacement main; validate framebuffer initialized/ABI and obtain queried video/plane.",
        "Allocate614400-byte source; validate nonNULL and geometry480x320/32bpp/stride1920. Set private source field+24 to owned pointer; keep allocation until process lifetime ends.",
        "Open physical input0 readonly|nonblock; resolve file pointer. Draw vilicvane +0 in owned RGB32 buffer with monochrome0/ffffffff pixels (channel ordering does not affect these colors).",
        "Submit native PAN; preserve dirty/retry state. Read32-byte events, use pressed latch and redraw only when counter changes; sleep10ms per loop, keeping touch/vblank OS alive.",
        "On any setup failure, return a documented error without touching driver/global queue ownership. Native task runs in normal task context; no new pthread or debug register injection is needed."],
    "evidence": str(evidence_path.relative_to(ROOT)),
}
report_path = OUT / "a7-counter-firmware-route-1.50.10.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"report": str(report_path.relative_to(ROOT)), "container_bytes": HI - LO,
                  "entry_file_offset": "0xccdcc8", "plane_bytes": 28, "private_source_offset": 24,
                  "current_rcS_verified": True, "target_operations": 0}))
