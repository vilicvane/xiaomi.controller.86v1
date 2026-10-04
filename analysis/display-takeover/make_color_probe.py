"""Build an integer-only MCU LCDC probe from the already validated runner."""
from pathlib import Path
import sys, json, hashlib, struct

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'analysis/wifi/python-packages'))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

code = bytes.fromhex('0160116819431160bff34f8f55befee7')
instructions = list(Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(code, 0))
assert [(x.mnemonic, x.op_str) for x in instructions] == [
    ('str', 'r1, [r0]'), ('ldr', 'r1, [r2]'), ('orrs', 'r1, r3'),
    ('str', 'r1, [r2]'), ('dsb', 'sy'), ('bkpt', '#0x55'), ('b', '#0xe')]
out = root / 'analysis/display-takeover'
(out / 'color-probe.bin').write_bytes(code)
(out / 'color-probe.S').write_text(''' .syntax unified
.thumb
.global color_probe
color_probe:
    str r1, [r0]
    ldr r1, [r2]
    orrs r1, r3
    str r1, [r2]
    dsb sy
    bkpt #0x55
1:  b 1b
''', encoding='utf-8')
(out / 'color-probe.json').write_text(json.dumps({
    'bytes':len(code), 'sha256':hashlib.sha256(code).hexdigest(),
    'scope':'MCU RAM program writes LCDC PN_BLANKCOLOR and FORCE_BLANKCOLOR bit24 only. A7 remains running. No framebuffer, Flash, clocks, reset, IRQ, or PWM writes.',
    'register_inputs':{'r0':'0x58100124','r1':'0x0000ff00','r2':'0x58100260','r3':'0x01000000'},
    'instructions':[{'offset':x.address,'mnemonic':x.mnemonic,'operands':x.op_str} for x in instructions],
    'rollback':'Restore PN_BLANKCOLOR original value; restore only original bit24 in REG260, retaining other current bits. Scratch bytes and CPU context restored immediately after execution.'
},indent=2)+'\n',encoding='utf-8')

s = (root / 'diagnostics/ram-exec-minimal.cfg').read_text()
s = s.replace('# User-authorized 16-byte MCU RAM program. No reset, Flash or peripheral access.', '# User-authorized MCU RAM display program. Two LCDC configuration writes; no reset or Flash.')
s = s.replace('diagnostics/ram-exec-minimal-result.txt','diagnostics/display-color-probe-result.txt')
s = s.replace('backups/ram-execution/', 'backups/display-takeover/color-probe-')
s = s.replace('scope MCU-only 16-byte RAM program; no stack/FPU/peripheral/Flash access', 'scope MCU RAM display output test; LCDC124 and260bit24 only; no stack/FPU/Flash')
s = s.replace('set panel_test_error [catch {', '''set panel_color_original [panel_word 0x58100124]
set panel_control_original [panel_word 0x58100260]
set panel_display_requested 0
# Prepare exact rollback before any target register modification.
set panel_restore_file [open "diagnostics/display-color-restore.cfg" w]
puts $panel_restore_file {source [find swd-memory.cfg]}
puts $panel_restore_file {adapter speed 1000}
puts $panel_restore_file {init}
puts $panel_restore_file [format {write_memory 0x58100124 32 {0x%08x}} $panel_color_original]
puts $panel_restore_file {set control [lindex [read_memory 0x58100260 32 1] 0]}
puts $panel_restore_file [format {write_memory 0x58100260 32 [list [expr {($control & ~0x01000000) | 0x%08x}]]} [expr {$panel_control_original & 0x01000000}]]
puts $panel_restore_file {echo "RESTORED_COLOR [bes.mem mdw 0x58100124 1]"}
puts $panel_restore_file {echo "RESTORED_CONTROL [bes.mem mdw 0x58100260 1]"}
puts $panel_restore_file {shutdown}
close $panel_restore_file
puts $panel_result [format "original_color 0x%08x" $panel_color_original]
puts $panel_result [format "original_control 0x%08x" $panel_control_original]
set panel_test_error [catch {''')
s = s.replace('0x212a 0x2217 0x1889 0x6001 0x4051 0x6041 0xbe55 0xe7fe', '0x6001 0x6811 0x4319 0x6011 0xf3bf 0x8f4f 0xbe55 0xe7fe')
s = s.replace('{8490 8727 6281 24577 16465 24641 48725 59390}', '{24577 26641 17177 24593 62399 36687 48725 59390}')
s = s.replace('panel_core_write 0 $panel_output', '''panel_core_write 0 0x58100124
    panel_core_write 1 0x0000ff00
    panel_core_write 2 0x58100260
    panel_core_write 3 0x01000000''')
s = s.replace('set panel_started 1', 'set panel_display_requested 1\n    set panel_started 1')
s = s.replace('set panel_output_words [panel_numbers [read_memory $panel_output 32 2]]', 'set panel_output_words [list [expr {[panel_word 0x58100124] + 0}] [expr {[panel_word 0x58100260] & 0x01000000}]]')
s = s.replace('if {$panel_output_words != {65 86}} { error "RAM arithmetic results differ" }', 'if {$panel_output_words != {65280 16777216}} { error "LCDC output control readback differs" }')
s = s.replace('echo "RAM_PROGRAM_OUTPUT 65 86"', 'echo "RAM_PROGRAM_LCDC_COLOR_SET"')
s = s.replace('foreach selector {0 1 2 16 15}', 'foreach selector {0 1 2 3 16 15}')
s = s.replace('puts $panel_result "restore_complete $panel_restored"', '''# Failure rollback touches only the two explicitly modified output fields.
if {$panel_test_error || $panel_cleanup_error} {
    if {$panel_display_requested} {
        panel_put 0x58100124 $panel_color_original
        set control [panel_word 0x58100260]
        panel_put 0x58100260 [expr {($control & ~0x01000000) | ($panel_control_original & 0x01000000)}]
        puts $panel_result "display_rolled_back_on_error 1"
    }
}
puts $panel_result "restore_complete $panel_restored"''')
s = s.replace('RAM_EXECUTION_AND_RESTORE_COMPLETE', 'RAM_DISPLAY_EXECUTION_AND_CORE_RESTORE_COMPLETE')
(root / 'diagnostics/display-color-probe.cfg').write_text(s,encoding='utf-8')
print(json.dumps({'code_bytes':len(code),'instructions':len(instructions),'config':'diagnostics/display-color-probe.cfg'}))
