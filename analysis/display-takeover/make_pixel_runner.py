"""Generate the bounded MCU renderer runner; never accesses hardware."""
from pathlib import Path
import json, struct

root = Path(__file__).resolve().parents[2]
meta_path = root / 'analysis/display-takeover/pixel-renderer.json'
meta = json.loads(meta_path.read_text())
code = bytes.fromhex(meta['code_hex'])
assert len(code) <= 64 and len(code) % 2 == 0
bkpt = int(meta['bkpt_offset'])
assert code[bkpt:bkpt+2] == b'\x55\xbe'
s = (root / 'diagnostics/ram-exec-minimal.cfg').read_text()
def replace(old, new):
    global s
    assert s.count(old) == 1, (old, s.count(old))
    s = s.replace(old,new)

replace('source [find swd-memory.cfg]\nadapter speed 1000\ninit', '''if {![info exists panel_debug_session_active] || ![info exists panel_pixels_dest]} { error "Pixel runner requires preserved A7 session and validated scanout destination" }
if {$panel_pixels_dest != 0x38515040 && $panel_pixels_dest != 0x385ab140} { error "Unexpected pixel destination" }
if {([lindex [read_memory 0x58050088 32 1] 0] & 1) == 0} { error "A7 must remain halted" }''')
s = s.replace('diagnostics/ram-exec-minimal-result.txt','diagnostics/display-pixels-mcu-result.txt')
s = s.replace('backups/ram-execution/', 'backups/display-takeover/pixels-')
s = s.replace('MCU-only 16-byte RAM program; no stack/FPU/peripheral/Flash access', 'MCU framebuffer renderer; 40960 scanout bytes; temporary privileged MPU write grant; no Flash/reset/stack/FPU')
replace('set panel_test_error [catch {', '''set panel_mpu_saved 0
set panel_mpu_changed 0
set panel_test_error [catch {''')
replace('set panel_cached_base [expr {($panel_sp - 64) & ~31}]','set panel_cached_base [expr {($panel_sp - 128) & ~31}]')
replace('set panel_output [expr {$panel_data_base + 32}]','set panel_output [expr {$panel_data_base + 64}]')
s = s.replace('read_memory $panel_data_base 32 16','read_memory $panel_data_base 32 32').replace('read_memory $panel_exec_base 32 16','read_memory $panel_exec_base 32 32')
s = s.replace('$panel_data_base 64','$panel_data_base 128')
replace('write_memory $panel_data_base 16 {0x212a 0x2217 0x1889 0x6001 0x4051 0x6041 0xbe55 0xe7fe}',
    'write_memory $panel_data_base 16 {'+' '.join(hex(x) for x in struct.unpack('<'+'H'*(len(code)//2),code))+'}')
replace('set panel_code [panel_numbers [read_memory $panel_exec_base 16 8]]',f'set panel_code [panel_numbers [read_memory $panel_exec_base 16 {len(code)//2}]]')
replace('if {$panel_code != {8490 8727 6281 24577 16465 24641 48725 59390}} { error "RAM code readback failed" }',
    'if {$panel_code != {'+' '.join(str(x) for x in struct.unpack('<'+'H'*(len(code)//2),code))+'}} { error "RAM code readback failed" }')
replace('set panel_registers_changed 1\n    panel_core_write 0 $panel_output', '''# Only the reviewed region may change; other MPU regions stay unchanged.
    if {[panel_word 0xe000ed94] != 5} { error "MPU control differs" }
    set panel_original_rnr [panel_word 0xe000ed98]
    set panel_mpu_saved 1
    panel_put 0xe000ed98 5
    set panel_original_rbar [panel_word 0xe000ed9c]
    set panel_original_rlar [panel_word 0xe000eda0]
    if {$panel_original_rbar != 0x38000007 || $panel_original_rlar != 0x39efffe9} { error "A7 NC MPU region differs" }
    set panel_mpu_changed 1
    panel_put 0xe000ed9c 0x38000001
    if {[panel_word 0xe000ed9c] != 0x38000001} { error "MPU grant readback failed" }
    set panel_registers_changed 1
    panel_core_write 0 $panel_pixels_dest
    panel_core_write 1 10240
    panel_core_write 2 0xffff00ff
    panel_core_write 3 $panel_original_rbar
    panel_core_write 4 0xe000ed9c''')
replace('set panel_output_words [panel_numbers [read_memory $panel_output 32 2]]', '''set panel_output_words [list [expr {[panel_word $panel_pixels_dest]+0}] [expr {[panel_word [expr {$panel_pixels_dest+40956}]]+0}]]
    puts $panel_result [format "renderer_mpu_restored 0x%08x" [panel_word 0xe000ed9c]]''')
replace('$panel_exec_base + 12', f'$panel_exec_base + {bkpt}')
replace('if {$panel_output_words != {65 86}} { error "RAM arithmetic results differ" }', '''if {$panel_output_words != {4294902015 4294902015}} { error "Pixel endpoints differ" }
    if {[panel_core_read 0] != $panel_pixels_dest+40960 || [panel_core_read 1] != 0} { error "Renderer pixel-count endpoints differ" }
    if {[panel_word 0xe000ed9c] != $panel_original_rbar} { error "Renderer did not restore MPU permissions" }''')
replace('echo "RAM_PROGRAM_OUTPUT 65 86"', 'echo "RAM_PROGRAM_PIXEL_STRIP_RENDERED"')
replace('if {$panel_scratch_changed && $panel_scratch_saved} {', '''if {$panel_mpu_saved && $panel_mpu_changed} {
            panel_put 0xe000ed98 5
            # Finish the reviewed CPU synchronization path if the draw did not.
            set current_pc [panel_core_read 15]
            if {!$panel_started || $current_pc != $panel_exec_base+32 || [panel_word 0xe000ed9c] != $panel_original_rbar} {
                set panel_registers_changed 1
                panel_core_write 3 $panel_original_rbar
                panel_core_write 4 0xe000ed9c
                panel_core_write 16 [expr {($panel_xpsr & ~0x0600fc00) | 0x01000000}]
                panel_core_write 15 [expr {$panel_exec_base+18}]
                set panel_started 1
                panel_put 0xe000edf0 0xa05f0009
                panel_require_halt
                if {([panel_core_read 16] & 0x1ff) || [panel_core_read 15] != $panel_exec_base+32 ||
                    [panel_word 0xe000ed28] != $panel_original_cfsr || [panel_word 0xe000ed2c] != $panel_original_hfsr ||
                    [panel_word 0xe000ed9c] != $panel_original_rbar || $panel_reset_seen} {
                    set panel_safe_context 0
                    error "MPU restore-only CPU synchronization failed; keep MCU halted"
                }
                puts $panel_result "mpu_restore_only_cpu_sync 1"
            }
        }
        if {$panel_mpu_saved} {
            panel_put 0xe000ed98 5
            if {$panel_mpu_changed} {
                panel_put 0xe000ed9c $panel_original_rbar
                if {[panel_word 0xe000ed9c] != $panel_original_rbar || [panel_word 0xe000eda0] != $panel_original_rlar} { error "MPU region restore differs" }
            }
            panel_put 0xe000ed98 $panel_original_rnr
            if {[panel_word 0xe000ed98] != $panel_original_rnr} { error "MPU selector restoration differs" }
            puts $panel_result "mpu_restored 1"
        }
        if {$panel_scratch_changed && $panel_scratch_saved} {''')
replace('foreach selector {0 1 2 16 15}', 'foreach selector {0 1 2 3 4 16 15}')
replace('shutdown\n', '# Outer A7 session owns shutdown.\n')
s = s.replace('# User-authorized 16-byte MCU RAM program. No reset, Flash or peripheral access.', '# User-authorized MCU pixel rendering; only bounded scanout stores and MPU permissions.')
(root / 'diagnostics/display-pixels-mcu.cfg').write_text(s)
print(json.dumps({'code_bytes':len(code),'bkpt_offset':bkpt,'file':'diagnostics/display-pixels-mcu.cfg'}))
