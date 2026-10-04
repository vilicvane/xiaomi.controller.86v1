"""Integrate the reviewed pure A7 pause and MCU renderer, offline only."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
s=(root/'diagnostics/a7-halt-resume-probe.cfg').read_text()
s=s.replace('diagnostics/a7-halt-resume-probe-result.txt','diagnostics/display-pixels-session-result.txt')
s=s.replace('set a7_test_error [catch {','''set panel_pixels_saved 0
set panel_pixels_changed_possible 0
set panel_pixels_restored 0
proc panel_restore_pixels {} {
    global panel_pixels_saved panel_pixels_changed_possible panel_pixels_restored
    global panel_pixels_dest panel_pixels_original
    if {$panel_pixels_saved && $panel_pixels_changed_possible && !$panel_pixels_restored} {
        a7_stable [a7_prsr]
        if {([a7_word 0x58050088] & 1) == 0} { error "A7 no longer halted; do not restore a stale framebuffer snapshot" }
        write_memory $panel_pixels_dest 32 $panel_pixels_original
        if {[read_memory $panel_pixels_dest 32 10240] != $panel_pixels_original} { error "Frame strip restoration mismatch" }
        dump_image backups/display-takeover/pixel-strip-restored.bin $panel_pixels_dest 40960
        set panel_pixels_restored 1
        a7_log "framebuffer_strip_restored 1"
    }
}
set a7_test_error [catch {''',1)
s=s.replace('    a7_put 0x58050090 1 a7_hrq_write_possible','''    set panel_hz [a7_word 0x384ef82c]
    set panel_wdt_value [a7_word 0x58001004]
    if {$panel_hz < 1000 || $panel_hz > 32000 || [a7_word 0x58001008] != 3 || [a7_word 0x58001010] != 0 || $panel_wdt_value < $panel_hz * 20} {
        error "Watchdog margin is insufficient for the bounded framebuffer test"
    }
    a7_log "watchdog_hz $panel_hz watchdog_value $panel_wdt_value"
    a7_put 0x58050090 1 a7_hrq_write_possible''',1)
s=s.replace('    # Immediately resume: no host sleep, framebuffer access, or core transfer.','''    set panel_pixels_dest [a7_word 0x581000f4]
    if {$panel_pixels_dest != 0x38515040 && $panel_pixels_dest != 0x385ab140} { error "Scanout pointer differs" }
    if {[a7_word 0x581000fc] != 1280 || [a7_word 0x58100104] != 0x01e00140 || [a7_word 0x58100108] != 0x01e00140 || ([a7_word 0x58100264] & 0xfff) != 0x401} {
        error "Scanout geometry/format differs"
    }
    set panel_pixels_original [read_memory $panel_pixels_dest 32 10240]
    set panel_pixels_saved 1
    dump_image backups/display-takeover/pixel-strip-original.bin $panel_pixels_dest 40960
    if {[read_memory $panel_pixels_dest 32 10240] != $panel_pixels_original || [a7_word 0x581000f4] != $panel_pixels_dest} {
        error "Display producer did not remain stable during CPU0 pause"
    }
    set panel_debug_session_active 1
    set panel_pixels_changed_possible 1
    set panel_render_ok 0
    for {set attempt 0} {$attempt < 3} {incr attempt} {
        set render_error [catch { source diagnostics/display-pixels-mcu.cfg } render_message]
        if {!$render_error} { set panel_render_ok 1; break }
        if {$render_message == "Test error after cleanup: Not in Thread mode" && $panel_restored && !$panel_cleanup_error && !$panel_started} {
            a7_log "MCU interrupt caught safely; retry $attempt"
            continue
        }
        error "MCU renderer failed: $render_message"
    }
    if {!$panel_render_ok} { error "MCU renderer stayed in interrupt context; no clean draw" }
    a7_log "MCU_pixel_renderer_completed_and_context_restored 1"
    a7_stable [a7_prsr]
    if {[a7_word 0x58001010] != 0 || [a7_word 0x58001004] < $panel_hz * 8} { error "Watchdog margin changed; immediately restore" }
    echo "PIXEL_STRIP_ACTIVE_FOR_3_SECONDS"
    sleep 3000
    panel_restore_pixels
    # Resume after exact framebuffer restoration.''',1)
s=s.replace('        set prsr [a7_prsr]\n        a7_stable $prsr\n        set dscr [a7_word 0x58050088]\n        if {$dscr & 1} { a7_mark_halted }','''        panel_restore_pixels
        set prsr [a7_prsr]
        a7_stable $prsr
        set dscr [a7_word 0x58050088]
        if {$dscr & 1} { a7_mark_halted }''',1)
s=s.replace('close $a7_result','''a7_log "pixels_saved $panel_pixels_saved pixels_changed_possible $panel_pixels_changed_possible pixels_restored $panel_pixels_restored"
close $a7_result''',1)
s=s.replace('scope CPU0 pure halt/immediate resume; only LAR/OSLAR/DRCR writes; no deliberate hold','scope A7 CPU0 pause, MCU RAM-rendered 32-row scanout strip, exact byte restore, CPU/MPU/debug restore; no Flash')
s=s.replace('A7_PURE_HALT_RESUME_AND_LOCK_RESTORE_COMPLETE','PIXEL_RENDERING_AND_RESTORATION_COMPLETE')
(root/'diagnostics/display-pixels-session.cfg').write_text(s)
print('Generated display-pixels-session.cfg')
