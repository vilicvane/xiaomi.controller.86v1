"""Offline, bounded display analysis of the saved 1.50.10 image.

No target communication, target mutation, raw logs, or identity data.
"""
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("a7_peripherals", ROOT / "analysis/pinout/analyze_a7_peripherals.py")
a7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a7)
data = a7.FILE.read_bytes()
payload_len = int.from_bytes(data[0x8e0000:0x8e0004], "big")
assert payload_len == 0x4f3fe0
END = 0x8e0004 + payload_len
assert END == 0xdd3fe4

def word(raw, off):
    return struct.unpack_from("<I", raw, off)[0]

def code(name, va, length):
    off = a7.address_to_offset(va)
    assert 0x8e0004 <= off < off + length <= END
    return {"name": name, "address": hex(va), "file_offset": hex(off),
            "mode": "ARM", "instructions": a7.disassemble(data, off, length, "ARM")}

windows = [
    ("getvideoinfo", 0x383de558, 0xb4),
    ("getplaneinfo", 0x383de4a8, 0xb0),
    ("updatearea_zero_pinfo_wrapper", 0x383df474, 0x58),
    ("pandisplay_and_staging_queue", 0x383df2dc, 0x198),
    ("staging_rotation", 0x383df18c, 0x150),
    ("vblank_scanout_swap", 0x383decbc, 0x5c),
    ("driver_init", 0x383df4d0, 0x440),
    ("HAL_ARBFAST_260_rmw", 0x383e0704, 0x28),
    ("HAL_scanout_base_and_pitch", 0x383e072c, 0x48),
    ("HAL_layer_enable_and_panel_enable", 0x383e097c, 0x80),
    ("HAL_blank_color", 0x383e09fc, 0x18),
    ("HAL_pixel_format", 0x383e0aec, 0x64),
    ("HAL_frame_trig_194", 0x383e0c98, 0x20),
]
evidence = [code(*w) for w in windows]
(ROOT / "analysis/display-takeover/a7-framebuffer-code-evidence-1.50.10.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

live_path = ROOT / "backups/display-takeover/a7-fb-object.bin"
live = live_path.read_bytes()
assert len(live) == 0x104
assert word(live, 0) == 0x383de558 and word(live, 4) == 0x383de4a8
live_info = {
    "source": str(live_path.relative_to(ROOT)),
    "read_semantics": "Root captured running memory; non-atomic object snapshot, not a halt or synchronization barrier.",
    "fmt": live[0x4c], "fmt_public_name": "FB_FMT_RGB32",
    "xres": struct.unpack_from("<H", live, 0x4e)[0],
    "yres": struct.unpack_from("<H", live, 0x50)[0],
    "fbmem": hex(word(live, 0x54)), "fblen": word(live, 0x58),
    "stride": struct.unpack_from("<H", live, 0x5c)[0],
    "display": live[0x5e], "bpp": live[0x5f],
    "xres_virtual": word(live, 0x60), "yres_virtual": word(live, 0x64),
    "xoffset": word(live, 0x68), "yoffset_or_driver_repurposed_field": hex(word(live, 0x6c)),
    "queue_count": word(live, 0xf0), "frame_counter": word(live, 0xf4),
    "current_staging_slot": live[0xf8],
}
assert (live_info["fmt"], live_info["xres"], live_info["yres"], live_info["stride"], live_info["bpp"]) == (13, 480, 320, 1920, 32)
tables = {}
for name, va in [("base", 0x384bc640), ("pitch", 0x384bc620), ("size", 0x384bc630),
                 ("enable", 0x384bc650), ("position", 0x384bc660), ("zoom_size", 0x384bc670)]:
    tables[name] = {"table_address": hex(va), "four_words": [hex(x) for x in struct.unpack_from("<4I", data, a7.address_to_offset(va))]}
assert tables["base"]["four_words"] == ["0x581000f4", "0x581000c0", "0x58100208", "0x0"]
assert data[a7.address_to_offset(0x384bc684) + 13] == 4

report = {
    "scope": "Offline analysis of saved 1.50.10 NOR plus root-supplied display-only RAM/MMIO snapshots. No hardware operations performed by this script.",
    "firmware": {"path": str(a7.FILE.relative_to(ROOT)), "A7_file_range": ["0x8e0004", hex(END)],
                 "mapped_base": "0x38000000", "excluded": "Residual old firmware tail at and beyond 0xdd3fe4."},
    "driver_object": {"address": "0x384ef84c", "NOR_initial_data_offset": "0xdcf850",
                      "video_info_offset": "0x4c", "plane_info_offset": "0x54",
                      "getvideoinfo": "0x383de558", "getplaneinfo": "0x383de4a8",
                      "updatearea_semantic_wrapper": "0x383df474", "pandisplay": "0x383df2dc",
                      "initialization": "0x383df4d0", "vblank_queue_handler": "0x383dea68",
                      "vtable_limit": "Other slots are not named merely by matching the current public NuttX header; that header has conditional and newer open/close fields."},
    "live_video_plane": live_info,
    "buffer_pipeline": {
        "static_initial_dimensions": [320, 480], "logical_live_dimensions": [480, 320],
        "physical_scanout_dimensions": [320, 480], "bytes_per_pixel": 4,
        "UI_buffer_bytes": "0x96000", "UI_buffer": live_info["fbmem"],
        "relocation_path": "pandisplay pinfo+0x18 == 0xffffffff copies prior fbmem to 0x50000000 and switches gdev+0x54/+0x74; the live object is already on this path.",
        "rotation_address": "0x383df18c", "rotation_formula": "dst[(W-1-x)*H+y] = src[y*W+x], W=480, H=320, 32-bit pixels; counterclockwise 90 degrees in memory coordinates.",
        "raw_staging_base": "0x38515028", "staging_slot_step": "0x96100",
        "aligned_staging_slots": ["0x38515040", "0x385ab140"],
        "staging_clear_bytes": "0x12c200", "physical_stride": 1280,
        "queue_entries": {"base": "0x384ef91c", "step": 16, "count": 2,
                          "fields": "buffer pointer +0; original input +4; frame id +8; state byte +12; slot byte +13"},
        "vblank_swap": "0x383decc8 loads queued pointer gdev+0xd0; 0x383decd0 calls HAL base setter with layer0; setter writes 0x581000f4.",
        "pixel_order_limit": "RGB32 format, word-preserving rotation, and HAL format selector4 are confirmed; byte-channel order/alpha interpretation require pixel or register corroboration before building a multicolor image."
    },
    "HAL_register_tables": tables,
    "registers_for_minimal_read": ["0x581000f4", "0x581000fc", "0x58100104", "0x58100108", "0x58100124", "0x58100194", "0x58100210", "0x58100254", "0x58100260", "0x58100264"],
    "root_supplied_live_MMIO": {"scanout_base_0x581000f4": "0x385ab140", "scanout_pitch_low16_0x581000fc": 1280,
                                "scanout_size_0x58100104": [320, 480], "DMA_plane_enable_0x58100190_bit0": False,
                                "blankcolor_0x58100124": "0x00000000", "force_register_0x58100260": "0x08000000",
                                "graphics_control_0x58100264": "0x00000401",
                                "graphics_control_decoded": "GRA enabled bit0; format4 bits8..11, matching the current HAL format13 table entry4.",
                                "DSI_VIDEO_MODE_bit11": True,
                                "limit": "Selected values supplied by root and separately saved by root; not this script's device read."},
    "minimal_color_override": {
        "color_register": "0x58100124", "color_field_mask": "0x00ffffff", "color_setter": "0x383e09fc",
        "force_register": "0x58100260", "force_mask": "0x01000000",
        "public_definition": "reg_lcdc.h reg_260 LCD_FORCE_BLANKCOLOR=1<<24; reg_124 LCD_CFG_PN_BLANKCOLOR mask0xffffff.",
        "confirmed_setter_behavior": "Blankcolor HAL setter writes REG_124 then returns; no commit call. REG_260 HAL setter modifies bit27 only and preserves bit24.",
        "force_setter_limit": "No dedicated force-blank setter identified in the bounded current HAL/driver code. Its force behavior is a public register definition until an actual display test succeeds.",
        "planned_scope": "Root may preserve REG_124 and the original REG_260 bit24 state, write a selected RGB value into REG_124 and RMW only REG_260 bit24, allow normal A7 frames, observe, then restore REG_124 and RMW bit24 back to its prior state while preserving any other current REG_260 bits. No heap, framebuffer, DMA base, clock, DSI timing, or trigger write is needed for the first bounded attempt.",
        "submission_limit": "The public hal_dsi.c hal_lcdc_start writes REG_258=0 and comments out REG_224=0, but an equivalent start write was not identified in current bounded HAL code. Do not transplant that trigger blindly. If normal running frames do not reflect the override, restore first and diagnose the actual trigger separately.",
        "classification": "Temporary LCDC output override controlled by a RAM program; proves limited pipeline control, not complete driver takeover or a persistent custom firmware."
    },
    "custom_image_followup": {
        "requirement": "To display a custom framebuffer without racing stock updates, establish an owned buffer and stop/redirect the stock scanout queue or use a confirmed unused overlay with validated format/geometry/stride/blending. Restore queue/MMIO/buffer ownership before resuming stock rendering.",
        "not_yet_verified": ["Unused overlay setup and memory ownership", "Pixel channel/alpha ordering", "A7/MCU cross-bus write capability and instruction-side ordering", "Whether blankcolor applies immediately or at the next active scanout frame"]
    },
    "public_sources": [
        "https://github.com/openharmony/device_soc_bestechnic/blob/17f61a22388e6f2fbd8fe855b0ccb298b9a3bd45/bes2600/liteos_m/sdk/bsp/platform/hal/reg_lcdc.h",
        "https://github.com/openharmony/device_soc_bestechnic/blob/17f61a22388e6f2fbd8fe855b0ccb298b9a3bd45/bes2600/liteos_m/sdk/bsp/platform/hal/hal_dsi.c",
        "https://github.com/open-vela/nuttx/blob/dev/include/nuttx/video/fb.h"
    ],
    "evidence": "analysis/display-takeover/a7-framebuffer-code-evidence-1.50.10.json",
}
out = ROOT / "analysis/display-takeover/a7-framebuffer-1.50.10.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"report": str(out.relative_to(ROOT)), "logical_dimensions": [live_info["xres"], live_info["yres"]], "stride": live_info["stride"], "scanout_register": "0x581000f4", "force_blank_register": "0x58100260", "target_operations": 0}))
