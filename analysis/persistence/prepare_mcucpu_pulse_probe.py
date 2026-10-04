"""Prepare one scoped MCUCPU pulse pilot; offline only, never run target actions."""
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
image = (ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin").read_bytes()
source = (ROOT / "diagnostics/mcu-cmu-active-flash-bootbreak-probe.cfg").read_text()
source = source.replace("diagnostics/mcu-cmu-active-flash-bootbreak-result.txt", "diagnostics/mcu-mcucpu-pulse-bootbreak-result.txt")
source = source.replace("# One direct AON-CMU GLOBAL hard reset, reset catch, then one FPB v2 breakpoint.",
    "# One MCUCPU-only AON pulse after actual-firmware DSP reset isolation.\n# Finally one GLOBAL reset whenever isolation/pulse may have committed.\n# No old MCU/A7 context resume; fresh OpenOCD process must verify normal boot.")
source = source.replace("# A reset intentionally discards the old application execution context.",
    "# A reset intentionally discards the old application execution context.\n# No native NOR API/data writes; original BOOT may alter NOR status/protection.\n# Do not claim the whole chip's NOR configuration stays read-only.")
source = source.replace('set boot_reset_possible 0', 'set boot_reset_possible 0\nset boot_a7_reset_possible 0\nset boot_cleanup_global_requested 0\nset boot_cleanup_global_transport_error 0\nset boot_cleanup_dispatch_complete 0\nset boot_fresh_process_required 0')
source = source.replace('Reset occurred before intended global write', 'Reset occurred before intended MCUCPU pulse')
source = source.replace('no global reset issued', 'no MCUCPU pulse issued')
source = source.replace('scope one direct AON400800a4=0x200 GLOBAL hard reset; reset catch and FPB boot stop; no debugger NOR/RAM/core-register data writes',
    'scope verified DSP reset_set isolation + one MCUCPU pulse400800a0=40; resetcatch/FPB observation only; finalGLOBAL400800a4=200 if isolation/pulsepossible; no native NORAPI/datawrites; BOOT normal NORconfiguration may change')

preflight = '''    # Match both actual firmware isolation closures and the entire MAIN generic
    # reset_pulse selector/store sequence before any target control mutation.
    # MAIN enum0x89 = AON_A7base0x83 +6 => value0x40 at AON+0xa0.
'''
for name, address, size in (("main_dsp_reset_set", 0x0c5cb498, 0x30),
                            ("boot_dsp_reset_set", 0x0c012a54, 0x30),
                            ("main_reset_pulse", 0x0c5caa68, 0x9c)):
    expected = struct.unpack_from("<" + "I" * (size//4), image, address-0x0c000000)
    preflight += f'    set expected_{name} {{' + " ".join(f"0x{v:08x}" for v in expected) + '}\n'
    preflight += f'    set actual_{name} [read_memory 0x{address:08x} 32 {size//4}]\n'
    preflight += f'''    if {{[llength $actual_{name}] != [llength $expected_{name}]}} {{ error "Incomplete {name} instruction read" }}
    foreach actual $actual_{name} expected $expected_{name} {{
        if {{[expr {{$actual + 0}}] != [expr {{$expected + 0}}]}} {{ error "Actual {name} opcodes/literals differ" }}
    }}
'''
anchor = '    # Validate physical controller ownership from the actual SRAM table and'
assert anchor in source
source = source.replace(anchor, preflight + anchor)

begin = source.index('    # NOR/boot instruction words below were matched to actual1.50.10 backup:')
end = source.index('    set boot_caught_status [boot_wait_reset_catch 1000]', begin)
isolation = '''    set boot_phase "dsp_reset_isolation"
    # Exactly the actual MAIN0c5cb498 and BOOT0c012a54 reset_set closure.
    # Mark commit possible before EACH store; no prior A7 context is replayed.
    foreach {address value} {
        0x400800a4 0x00000003
        0x40000044 0x1c000000
        0x40000114 0x00041fef
        0x40000160 0x0000009f
        0x40000034 0x00000400
    } { boot_put $address $value boot_a7_reset_possible }
    # APDBG was reset. NEVER touch A7 PRSR/DSCR/CoreSight after isolation.
    # Only always-on/MCU CMU status is used to confirm the reset boundary.
    set isolated_aon [boot_word 0x400800a4]
    set isolated_oreset [boot_word 0x40000044]
    set isolated_xreset [boot_word 0x40000114]
    set isolated_apreset [boot_word 0x40000160]
    set isolated_hreset [boot_word 0x40000034]
    boot_log [format "isolated_reset_status aon%08x o%08x x%08x ap%08x h%08x" $isolated_aon $isolated_oreset $isolated_xreset $isolated_apreset $isolated_hreset]
    if {($isolated_aon & 3) || ($isolated_oreset & 0x1c000000) || ($isolated_xreset & 0x41fef) || ($isolated_apreset & 0x9f) || ($isolated_hreset & 0x400)} {
        error "A7 reset_set status did not confirm asserted isolation"
    }
    boot_stable_halt
    if {$boot_reset_seen} { error "MCU unexpectedly reset during A7 isolation" }
    set isolation_idle [boot_wait_active_spi_idle $boot_active_controller 200]
    set isolation_lock [boot_word [expr {$boot_active_controller + 0x34}]]
    if {($isolation_idle & 1) || ($isolation_lock & 0x100)} { error "Primary SPI not settled after isolation" }
    boot_log [format "isolated_nor_status 0x%08x readlock 0x%08x" $isolation_idle $isolation_lock]
    set boot_phase "mcucpu_pulse_requested"
    # Do not retry after a transport error: a posted pulse may have committed.
    set reset_write_error [catch { boot_put 0x400800a0 0x40 boot_reset_possible } reset_write_message]
    boot_log "mcucpu_pulse_transport_error $reset_write_error"
'''
source = source[:begin] + isolation + source[end:]
source = source.replace('pre_global_nor_status', 'pre_isolation_nor_status')

a7start = source.index('    # A7 may be reset/off before its boot image is launched.')
a7end = source.index('    boot_stable_halt', a7start)
source = source[:a7start] + '''    # A7 debug domain was reset: no PRSR/DSCR reads are permitted.
    set boot_stop_aon [boot_word 0x400800a4]
    boot_log [format "boot_a7_reset_aon_status 0x%08x" $boot_stop_aon]
    if {$boot_stop_aon & 2} { error "A7CPU reset is not held at the independent BOOT stop" }
    boot_log "boot_a7_debug_reads_skipped APDBG_reset"
''' + source[a7end:]

cleanup_start = source.index('# Finally: remove temporary debug mechanisms and continue original firmware.')
cleanup_end = source.index('foreach name {reset_possible reset_seen', cleanup_start)
old_cleanup = source[cleanup_start:cleanup_end]
standard_start = old_cleanup.index('    if {$boot_saved &&')
standard_end = old_cleanup.index('    set boot_cleanup_complete 1')
standard = old_cleanup[standard_start:standard_end]
cleanup = '''# Finally: if isolation or pulse may have committed, discard all old MCU/A7
# context and request one known GLOBAL reset regardless of the test outcome.
# Only a verified fresh BOOT halt permits removing our temporary FPB/catch.
# Uncertain/lost-link failure goes straight to independent GLOBAL recovery.
# The cached DAP can disappear after GLOBAL; root must verify with a NEW process.
set boot_cleanup_error [catch {
    if {$boot_a7_reset_possible || $boot_reset_possible} {
        # Remove our comparator before GLOBAL after a verified fresh BOOT halt.
        # Do not replay old MCU/A7 context; cleanup error still permits GLOBAL.
        if {$boot_break_hit && !$boot_unexpected_reset} {
            set debug_cleanup_error [catch {
                boot_stable_halt
                boot_remove_fpb
                boot_remove_catch
            } debug_cleanup_message]
            boot_log "pre_global_debug_cleanup_error $debug_cleanup_error"
            if {$debug_cleanup_error} { boot_log "pre_global_debug_cleanup_message $debug_cleanup_message" }
        }
        set boot_fresh_process_required 1
        set boot_phase "cleanup_global_requested"
        set boot_cleanup_global_transport_error [catch {
            boot_put 0x400800a4 0x200 boot_cleanup_global_requested
        } global_message]
        boot_log "cleanup_global_transport_error $boot_cleanup_global_transport_error"
        if {$boot_cleanup_global_transport_error} {
            boot_log "cleanup_global_transport_message $global_message"
            error "GLOBAL recovery write may have committed; fresh process/full power cycle verification required"
        }
        set boot_cleanup_dispatch_complete 1
        # Not a claim of ordinary main boot or final cleanup verification.
        set boot_cleanup_complete 0
    } else {
        # No A7/CPU reset mutation: ordinary temporary-debug rollback only.
''' + standard + '''        set boot_cleanup_complete 1
        set boot_cleanup_dispatch_complete 1
    }
} boot_cleanup_message]
'''
source = source[:cleanup_start] + cleanup + source[cleanup_end:]
source = source.replace('foreach name {reset_possible reset_seen reset_caught break_hit unexpected_reset resumed cleanup_complete write_count phase}',
    'foreach name {a7_reset_possible reset_possible reset_seen reset_caught break_hit unexpected_reset resumed cleanup_global_requested cleanup_global_transport_error cleanup_dispatch_complete fresh_process_required cleanup_complete write_count phase}')
source = source.replace('echo "Verified CMU reset catch/boot breakpoint; original firmware resumed; no debugger NOR command"',
    'echo "MCUCPU pulse pilot completed; if GLOBALrequested, root must verify ordinary main boot in a fresh OpenOCD process"')
out = ROOT / "diagnostics/mcu-mcucpu-pulse-bootbreak-probe.cfg"
out.write_text(source)
assert "0x58050314" not in source and "0x58050088" not in source
assert source.count('boot_put 0x400800a0 0x40') == 1
assert source.count('boot_put 0x400800a4 0x200') == 1
print("Prepared one MCUCPU pulse/isolation pilot; no hardware; finalGLOBAL dispatch requires fresh verification")
