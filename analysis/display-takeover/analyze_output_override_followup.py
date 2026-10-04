"""Offline follow-up to the unsuccessful forced-blank display test."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("a7", ROOT / "analysis/pinout/analyze_a7_peripherals.py")
a7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a7)
data = a7.FILE.read_bytes()
assert int.from_bytes(data[0x8e0000:0x8e0004], "big") == 0x4f3fe0
windows = [
    ("DSI_initialization_and_BIST_control", 0x383e0524, 0x1b4),
    ("framebuffer_setblank", 0x383de734, 0xd0),
    ("LCDC_layer_enable", 0x383e097c, 0x20),
    ("LCDC_blank_color", 0x383e09fc, 0x18),
    ("LCDC_FRAME_TRIG", 0x383e0c98, 0x20),
    ("LCDC_vblank_base_swap", 0x383decbc, 0x5c),
]
evidence = [{"name": name, "address": hex(va), "file_offset": hex(a7.address_to_offset(va)), "mode": "ARM",
             "instructions": a7.disassemble(data, a7.address_to_offset(va), length, "ARM")}
            for name, va, length in windows]
calls = a7.find_direct_calls(data, 0xdd3fe4, {0x383e0c98: "FRAME_TRIG", 0x383e097c: "layer enable"}, True)
report = {
    "scope": "Offline current-1.50.10 firmware analysis. Root-reported experiment observation is recorded, not independently reproduced by this agent. No target access.",
    "unsuccessful_forced_blank_test": {
        "root_observation": "MCU RAM stub succeeded; LCDC REG124 became0x0000ff00 and REG260 became0x09000000. Values persisted after approximately20seconds. Touch woke the panel and the original UI appeared without a green output. Color and bit24 were restored to0 and0x08000000.",
        "established": ["Transport and MCU program can modify and preserve these LCDC registers", "Public FORCE_BLANKCOLOR bit alone did not replace the active panel image under the tested configuration"],
        "not_established": ["That FORCE_BLANKCOLOR controls this exact active PN/GRA/video route", "That a commit pulse would make this bit effective", "That the frame was lost or backlight was the only cause", "That a complete display driver was taken over"],
        "cause_boundary": "Public register names supply no implementation timing/route specification. Current firmware uses GRA layer0 and DSI video; no force-blank setter is used in identified HAL code. Route applicability, silicon/register revision differences, and latching remain alternatives, not a diagnosed cause."
    },
    "LCDC_without_framebuffer_alternative": {
        "candidate": "REG124 background color plus temporary disabling of GRA at REG264 bit0",
        "setblank_call_chain": "fb vtable+0x20 -> 0x383de734 -> 0x383e097c with layer0 and enable=!blank; table0x384bc650 maps layer0 to0x58100264",
        "normal_vblank_behavior": "0x383decc8 loads queue entry buffer;0x383decd0 calls the base setter. It updates REG0F4 without calling layer-enable or FRAME_TRIG.",
        "limit": "Disabling the active GRA layer is verified control behavior. Whether the panel then displays PN blankcolor is not verified. Preserve prior bit0, retain other control bits and stock frame production; restore bit0 after a bounded visible test.",
        "FRAME_TRIG_calls": calls,
        "do_not_assume_commit": "Current direct-call scan finds FRAME_TRIG only in initialization. Public hal_lcdc_start writes REG258=0 but that equivalent current function has not been identified. Do not add a trigger solely from old public example code."
    },
    "DSI_test_pattern_candidate": {
        "base": "0x58005000", "register": "0x58005048", "current_value_root_read": "0x4b400001",
        "fields": {"BIST_enable": {"bit": 3, "mask": "0x00000008"},
                   "pattern": {"shift": 4, "mask": "0x00000070"},
                   "color_bar_width": {"shift": 8, "mask": "0x000fff00"},
                   "HSYNC_delay": {"shift": 20, "mask": "0xfff00000"}},
        "current_field_decode": {"BIST_enabled": False, "pattern": 0, "color_bar_width": 0, "HSYNC_delay": "0x4b4"},
        "current_firmware_evidence": [
            "0x383e059c..0x383e05a8 reads REG048 and clears bit3",
            "0x383e05c4..0x383e05dc clears width then temporarily sets0x100",
            "0x383e0674..0x383e0688 preserves low8bits and HSYNC delay but clears width via0xfff000ff mask; sets bit0"
        ],
        "public_evidence": "reg_dsi.h reg48 defines VIDEO_BIST_EN, VIDEO_BIST_PATTERN and COLOR_BAR_WIDTH; public hal_dsi_start also clears BIST in video mode.",
        "example_bounded_configuration": {"requested_change_mask": "0x000fff08", "nonzero_width": "0x40", "new_value_if_original_matches": "0x4b404009",
                                          "restore": "RMW only original BIST-enable and width fields back; preserve other current bits. Leave VIDEO_MODE, pixel packet dtype, timing, clocks and panel DCS state unchanged."},
        "limits": ["Official pattern-number enum/example was not found", "Pattern0 plus width0 cannot be claimed to produce useful visible output", "Width0x40 is within the defined field and avoids zero-width ambiguity, but its visible color sequence and BIST output on this board remain experimental", "This is an output-generator test, not an independently owned custom image or driver replacement"]
    },
    "ST7797_and_command_mode": {
        "manufacturer_document": "Sitronix ST7797 v1.6,2020/12, hosted PDF mirror; same-chip documentation, exact panel revision unverified.",
        "source": "https://admin.osptek.com/uploads/ST_7797_SPEC_V1_6_1_328549b1c4.pdf",
        "local": "analysis/display-takeover/reference/ST7797-v1.6.pdf",
        "pages": [7, 158, 159],
        "confirmed_document_characteristics": "Features specify no full display RAM, a MIPI video interface, and limited1bpp two-color idle storage with compressed picture size below4KiB. The command table nevertheless includes RAMWR2Ch and WRMEMC3Ch.",
        "implication": "Presence of RAMWR alone does not prove full-color command-mode framebuffer retention. Do not replace ongoing video with a one-shot full-color DCS memory write on this evidence.",
        "preferred_image_path": "Keep existing DSI video, panel initialization and LCDC scanout clocks running; establish a validated A7 producer pause, preserve an actual owned scanout region, present test pixels through the existing video DMA, restore bytes/control then resume.",
        "halt_caveats": "A7 debug halt only stops the producer after confirmed invasive-debug access. It does not imply cache-coherent MCU writes, a drained frame queue, or that peripheral scanout continues. These must be verified before the custom staging test."
    },
    "code_evidence": evidence,
    "target_operations": 0
}
out = ROOT / "analysis/display-takeover/output-override-followup-1.50.10.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"report": str(out.relative_to(ROOT)), "BIST_candidate": "0x58005048", "nonzero_width_configuration": "0x4b404009", "FRAME_TRIG_identified_direct_calls": len([x for x in calls if x["target"] == "FRAME_TRIG"]), "target_operations": 0}))
