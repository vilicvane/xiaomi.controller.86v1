"""Independent fixed-native_image_drawer Jim model. No adapter, init, or target connection.

Only reads source and immutable binary fixtures; creates this task's new mock
outputs. Native callees are simulated from actual r0..r3 and scratch contents,
not by replacing the runner's stage/orchestration procedures.
"""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "tools/xpack-openocd-0.12.0-7/bin/openocd.exe"
OUT = ROOT / "analysis/persistence/offline-native-image-drawer-runner"
OUT.mkdir(exist_ok=True)
run_index = 1
while (OUT / f"run-{run_index}").exists():
    run_index += 1
RUN = OUT / f"run-{run_index}"
RUN.mkdir()

def wordlist(data):
    return " ".join(map(str, struct.unpack("<" + "I" * (len(data) // 4), data)))

fixture = {}
seed = []
for label, offset in [("table", 0xccd000), ("code", 0x92b000), ("aux", 0x95a000)]:
    for state in ["original", "patched"]:
        path = ROOT / f"analysis/persistence/native-image-drawer-{state}-sector-{offset:x}.bin"
        data = path.read_bytes()
        assert len(data) == 4096
        fixture[label, state] = data
        seed.append(f"set mock_{label}_{state} {{{wordlist(data)}}}")
for label, offset in [("table", 0xccd000), ("code", 0x92b000)]:
    data = (ROOT / f"analysis/display-takeover/native-counter-patched-sector-{offset:x}.bin").read_bytes()
    assert len(data) == 4096
    seed.append(f"set mock_counter_{label} {{{wordlist(data)}}}")
    stock = (ROOT / f"analysis/display-takeover/native-ui-broker-original-sector-{offset:x}.bin").read_bytes()
    assert len(stock) == 4096
    seed.append(f"set mock_stock_{label} {{{wordlist(stock)}}}")
    broker = (ROOT / f"analysis/display-takeover/native-ui-broker-patched-sector-{offset:x}.bin").read_bytes()
    assert len(broker) == 4096
    seed.append(f"set mock_broker_{label} {{{wordlist(broker)}}}")
    first_drawer = (ROOT / f"analysis/persistence/native-drawer-patched-sector-{offset:x}.bin").read_bytes()
    assert len(first_drawer) == 4096
    seed.append(f"set mock_first_drawer_{label} {{{wordlist(first_drawer)}}}")
    ease = (ROOT / f"analysis/persistence/native-drawer-ease-patched-sector-{offset:x}.bin").read_bytes()
    assert len(ease) == 4096
    seed.append(f"set mock_ease_{label} {{{wordlist(ease)}}}")
    smooth = (ROOT / f"analysis/persistence/native-drawer-smooth-patched-sector-{offset:x}.bin").read_bytes()
    assert len(smooth) == 4096
    seed.append(f"set mock_smooth_{label} {{{wordlist(smooth)}}}")
for label, offset in [("table", 0xccd000), ("code", 0x92b000), ("aux", 0x95a000)]:
    previous = (ROOT / f"analysis/persistence/native-github-tap-fast-patched-sector-{offset:x}.bin").read_bytes()
    assert previous == fixture[label, "original"], "Image-drawer rollback is not the exact frozen fast-tap triple"
    if label != "aux":
        tap_v1 = (ROOT / f"analysis/persistence/native-github-tap-patched-sector-{offset:x}.bin").read_bytes()
        assert len(tap_v1) == 4096
        seed.append(f"set mock_tap_v1_{label} {{{wordlist(tap_v1)}}}")
        card = (ROOT / f"analysis/persistence/native-github-card-patched-sector-{offset:x}.bin").read_bytes()
        assert len(card) == 4096
        seed.append(f"set mock_card_{label} {{{wordlist(card)}}}")
    else:
        stock_aux = (ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin").read_bytes()[offset:offset+4096]
        seed.append(f"set mock_stock_aux {{{wordlist(stock_aux)}}}")
source = (ROOT / "analysis/persistence/mock_boot_read_runner.tcl").read_text()
model = source[:source.index("set mock_error [catch {bnor_run_read_probe")]
model = model.replace("source diagnostics/boot-nor-read-runner.cfg", "source diagnostics/boot-nor-native-image-drawer-runner.cfg")
model = model.replace("set mock_mode $bnor_mock_mode", "set mock_mode $native_image_drawer_mock_mode\nset bnor_safe_to_resume 1\nset bnor_reset_seen 0\nset bnor_track_reset 1")
extra = "\n".join(seed) + r'''
foreach {name wanted} [list nidi_table_original_words $mock_table_original nidi_table_patched_words $mock_table_patched nidi_code_original_words $mock_code_original nidi_code_patched_words $mock_code_patched nidi_aux_original_words $mock_aux_original nidi_aux_patched_words $mock_aux_patched] {
    set normalized {}
    foreach number [set $name] { lappend normalized [expr {$number+0}] }
    if {$normalized != $wanted} { error "Runner fixture differs from independent raw binary $name" }
}
set mock_flow install
if {[string match "restore_*" $mock_mode]} { set mock_flow restore }
set mock_seed_state original
if {$mock_flow == "restore"} { set mock_seed_state patched }
if {$mock_mode == "restore_fast_tap_baseline"} { set mock_seed_state original }
foreach {label address} {table 0x28ccd000 code 0x2892b000 aux 0x2895a000} {
    set wanted [set mock_${label}_${mock_seed_state}]
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {$address+4*$i}]) [lindex $wanted $i] }
}
set mock_mem([expr {0x400800a4}]) 0x24d
set mock_mem([expr {0x40082008}]) 0
set mock_sr1 0
set mock_sr2 2
if {[string match "*bp7c" $mock_mode]} { set mock_sr1 0x7c }
set mock_original_sr1 $mock_sr1
set mock_original_sr2 $mock_sr2
set mock_wdt_reads 0
set mock_mutation_calls {}
set mock_calls {}
set mock_order {}
set mock_code_programmed 0
set mock_posted_transport_pending 0
set mock_table_erased 0
set mock_code_erased 0
set mock_code_verified 0
set mock_table_restored_verified 0
set mock_code_original_verified 0
set mock_aux_erased 0
set mock_aux_verified 0
set mock_aux_programmed 0
set mock_failed_run 0
set mock_stale_replay 0
set mock_delay_remaining 0
set mock_delayed_samples 0
set mock_virtual_ms 0
if {$mock_mode == "install_image_drawer_baseline"} {
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_code_patched $i] }
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_table_patched $i] }
}
if {$mock_mode in {tap_v1_baseline_code tap_v1_baseline_pair}} {
    set mock_flow restore
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_tap_v1_code $i] }
    if {$mock_mode == "tap_v1_baseline_pair"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_tap_v1_table $i] }
    }
}
if {$mock_mode in {card_baseline_code card_baseline_pair}} {
    set mock_flow restore
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_card_code $i] }
    if {$mock_mode == "card_baseline_pair"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_card_table $i] }
    }
}
if {$mock_mode == "stock_aux_baseline"} {
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2895a000+4*$i}]) [lindex $mock_stock_aux $i] }
}
if {$mock_mode in {smooth_baseline_code smooth_baseline_pair}} {
    set mock_flow restore
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_smooth_code $i] }
    if {$mock_mode == "smooth_baseline_pair"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_smooth_table $i] }
    }
}
if {$mock_mode in {ease_baseline_code ease_baseline_pair}} {
    set mock_flow restore
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_ease_code $i] }
    if {$mock_mode == "ease_baseline_pair"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_ease_table $i] }
    }
}
if {$mock_mode in {first_drawer_baseline_code first_drawer_baseline_pair}} {
    set mock_flow restore
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_first_drawer_code $i] }
    if {$mock_mode == "first_drawer_baseline_pair"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_first_drawer_table $i] }
    }
}
if {$mock_mode in {broker_baseline_code broker_baseline_table broker_baseline_pair}} {
    set mock_flow restore
    if {$mock_mode != "broker_baseline_table"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_broker_code $i] }
    }
    if {$mock_mode != "broker_baseline_code"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_broker_table $i] }
    }
}
if {$mock_mode in {stock_baseline_code stock_baseline_table stock_baseline_pair}} {
    set mock_flow restore
    if {$mock_mode != "stock_baseline_table"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_stock_code $i] }
    }
    if {$mock_mode != "stock_baseline_code"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_stock_table $i] }
    }
}
if {$mock_mode in {counter_baseline_code counter_baseline_table counter_baseline_pair}} {
    set mock_flow restore
    if {$mock_mode != "counter_baseline_table"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_counter_code $i] }
    }
    if {$mock_mode != "counter_baseline_code"} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) [lindex $mock_counter_table $i] }
    }
}
if {$mock_mode == "install_image_drawer_baseline"} {
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2895a000+4*$i}]) [lindex $mock_aux_patched $i] }
}
if {$mock_mode in {baseline_aux_mismatch restore_baseline_aux_mismatch}} {
    set mock_mem([expr {0x2895affc}]) [expr {$mock_mem([expr {0x2895affc}]) ^ 1}]
}
if {$mock_mode == "mixed_image_code_fast_aux"} {
    set mock_flow restore
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_code_patched $i] }
}
if {$mock_mode in {mixed_fast_code_image_aux install_image_aux_only}} {
    if {$mock_mode != "install_image_aux_only"} { set mock_flow restore }
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2895a000+4*$i}]) [lindex $mock_aux_patched $i] }
}
if {$mock_mode == "active_watchdog"} { set mock_mem([expr {0x40082008}]) 3 }
if {$mock_mode == "baseline_table_mismatch"} { set mock_mem([expr {0x28ccdffc}]) [expr {$mock_mem([expr {0x28ccdffc}]) ^ 1}] }
if {$mock_mode in {baseline_code_mismatch restore_baseline_code_mismatch}} { set mock_mem([expr {0x2892bffc}]) [expr {$mock_mem([expr {0x2892bffc}]) ^ 1}] }
if {$mock_mode == "restore_baseline_table_mismatch"} { set mock_mem([expr {0x28ccdffc}]) [expr {$mock_mem([expr {0x28ccdffc}]) ^ 1}] }
if {$mock_mode == "partial_table_fixed_restore"} {
    set mock_flow partial
    set mock_sr1 0x7c
    set mock_original_sr1 $mock_sr1
    for {set i 0} {$i < 128} {incr i} { set mock_mem([expr {0x28ccd000+4*$i}]) 0xffffffff }
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892b000+4*$i}]) [lindex $mock_code_patched $i]; set mock_mem([expr {0x2895a000+4*$i}]) [lindex $mock_aux_patched $i] }
}
rename clock mock_host_clock
proc clock {subcommand} {
    if {$subcommand == "milliseconds"} { return $::mock_virtual_ms }
    return [mock_host_clock $subcommand]
}
rename sleep mock_host_sleep
proc sleep {ms} { incr ::mock_virtual_ms $ms }
'''
model = model.replace("set mock_saved_regs [array get mock_regs]", extra + "\nset mock_saved_regs [array get mock_regs]")
model = model.replace('    if {$bits != 32} { error "Mock only supports32bit reads" }', r'''
    if {$address >= 0x58000000 && $address < 0x59000000} { error "Forbidden APDBG read" }
    if {$address == 0x40082008} {
        incr ::mock_wdt_reads
        if {$mock_mode == "watchdog_reenabled" && $::mock_wdt_reads == 3} { set mock_mem([expr {0x40082008}]) 3 }
    }
    if {$address == 0xe000edf0 && $::mock_delay_remaining > 0} {
        incr ::mock_delay_remaining -1
        incr ::mock_delayed_samples
        return {0x00110009}
    }
    if {$::mock_posted_transport_pending && $address == 0x40148004} {
        set ::mock_posted_transport_pending 0
        set ::mock_failed_run 1
        error "Simulated post-return SPI snapshot transport timeout with NOR WIP1"
    }
    if {$bits != 32} { error "Mock only supports32bit reads" }
''')
model = model.replace("    return $result\n}", r'''
    if {$count == 1024 && $address == 0x2892b000 && $::mock_code_programmed && $result == $::mock_code_patched} {
        set ::mock_code_verified 1
        lappend ::mock_order verify_code_4k
    }
    if {$count == 1024 && $address == 0x28ccd000 && $::mock_table_erased && $result == $::mock_table_original} {
        set ::mock_table_restored_verified 1
        lappend ::mock_order verify_original_table_4k
    }
    if {$count == 1024 && $address == 0x2895a000 && $::mock_aux_erased && $result == $::mock_aux_patched} {
        set ::mock_aux_verified 1
        lappend ::mock_order verify_aux_4k
    }
    if {$count == 1024 && $address == 0x2892b000 && $::mock_code_erased && $result == $::mock_code_original} {
        set ::mock_code_original_verified 1
        lappend ::mock_order verify_original_code_4k
    }
    return $result
}''', 1)
start = model.index("            if {($value & 15) == 9} {")
end = model.index("        } else { set mock_mem($addr) $value }", start)
native = r'''
            if {($value & 15) == 9} {
                incr mock_exec
                set base $mock_scratch_base
                set callee $mock_mem([expr {$base+128}])
                set ret 0
                if {$callee == 0} {
                    lappend ::mock_calls read
                    lappend ::mock_order status_read
                    set mock_mem([expr {$base+128}]) 0
                    set mock_mem([expr {$base+132}]) 1
                    foreach off {136 140 144 148 152} { set mock_mem([expr {$base+$off}]) 0 }
                    set mock_mem([expr {$base+156}]) 0x52454144
                    set mock_mem([expr {$base+160}]) [expr {0x186585 | ($::mock_sr1<<24)}]
                    set mock_mem([expr {$base+164}]) $::mock_sr2
                    set pc_offset 94
                    if {$mock_mode == "read_timeout"} { set ::mock_delay_remaining 100; set ::mock_failed_run 1 }
                } else {
                    set arg0 $mock_mem([expr {$base+132}])
                    set arg1 $mock_mem([expr {$base+136}])
                    set arg2 $mock_mem([expr {$base+140}])
                    set arg3 $mock_mem([expr {$base+144}])
                    switch [format "0x%08x" $callee] {
                        0x00200fe9 {
                            if {$arg0 != 0 || $arg2 != 0 || $arg3 != 0 || $arg1 & ~0x407c ||
                                ($arg1 != 0 && $arg1 != (($::mock_original_sr1|($::mock_original_sr2<<8))&0x407c))} { error "Bad admitted BP arguments" }
                            set tag unprotect
                            if {$arg1 != 0} { set tag reprotect }
                            lappend ::mock_mutation_calls $tag
                            set composite [expr {(($::mock_sr1|($::mock_sr2<<8)) & ~0x407c) | $arg1}]
                            set ::mock_sr1 [expr {$composite&255}]
                            set ::mock_sr2 [expr {($composite>>8)&255}]
                        }
                        0x00201249 {
                            if {$arg0 != 0 || $arg2 != $base+256 || $arg3 != 256 || $arg1 & 255} { error "Bad admitted page ABI" }
                            if {($::mock_sr1|($::mock_sr2<<8))&0x407c} { error "NOR program while protected" }
                            if {$arg1 >= 0x28ccd000 && $arg1 < 0x28cce000} {
                                if {!$::mock_table_erased} { error "Table programmed without erase" }
                                set page [expr {($arg1-0x28ccd000)/256}]
                                if {$::mock_flow == "install"} { set wanted $::mock_table_patched } else { set wanted $::mock_table_original }
                                set tag program_table_$page
                            } elseif {$arg1 >= 0x2892b000 && $arg1 < 0x2892c000 && $::mock_flow in {install restore}} {
                                if {!$::mock_code_erased} { error "Code programmed without erase" }
                                if {$::mock_flow == "restore" && !$::mock_table_restored_verified} { error "Code restore before original table whole verify" }
                                set page [expr {($arg1-0x2892b000)/256}]
                                if {$::mock_flow == "install"} { set wanted $::mock_code_patched } else { set wanted $::mock_code_original }
                                set tag program_code_$page
                            } elseif {$arg1 >= 0x2895a000 && $arg1 < 0x2895b000 && $::mock_flow in {install restore}} {
                                if {!$::mock_aux_erased} { error "Aux programmed without erase" }
                                if {$::mock_flow == "restore" && !$::mock_code_original_verified} { error "Aux restore before original main whole verify" }
                                set page [expr {($arg1-0x2895a000)/256}]
                                if {$::mock_flow == "install"} { set wanted $::mock_aux_patched } else { set wanted $::mock_aux_original }
                                set tag program_aux_$page
                            } else { error "Arbitrary NOR program address" }
                            set expected [lrange $wanted [expr {$page*64}] [expr {$page*64+63}]]
                            set actual {}
                            for {set j 0} {$j < 64} {incr j} { lappend actual $mock_mem([expr {$arg2+4*$j}]) }
                            if {$actual != $expected} { error "Native scratch payload differs from independent exact binary page" }
                            lappend ::mock_mutation_calls $tag
                            for {set j 0} {$j < 64} {incr j} {
                                set old $mock_mem([expr {$arg1+4*$j}])
                                set new [lindex $expected $j]
                                if {($old & $new) != $new} { error "NOR 0-to-1 program without erase" }
                                set mock_mem([expr {$arg1+4*$j}]) [expr {$old & $new}]
                            }
                            if {$tag == "program_aux_0"} {
                                set ::mock_aux_programmed 1
                                if {$mock_mode in {aux_native_error restore_aux_native_error}} { set ret 7; set ::mock_failed_run 1 }
                                if {$mock_mode == "aux_program_timeout"} { set ::mock_delay_remaining 400; set ::mock_failed_run 1 }
                            }
                            if {$tag == "program_aux_15"} {
                                if {$mock_mode == "aux_whole_readback_mismatch"} { set mock_mem([expr {0x2895affc}]) [expr {$mock_mem([expr {0x2895affc}]) ^ 1}] }
                                if {$mock_mode == "aux_qe_changed"} { set ::mock_sr2 0 }
                                if {$mock_mode == "aux_wip_status"} { set ::mock_sr1 1 }
                            }
                            if {$tag == "program_table_0" && $mock_mode == "table_native_error"} { set ret 7; set ::mock_failed_run 1 }
                            if {$tag == "program_code_0"} {
                                set ::mock_code_programmed 1
                                if {$mock_mode == "native_error_code"} { set ret 7; set ::mock_failed_run 1 }
                                if {$mock_mode == "program_timeout"} { set ::mock_delay_remaining 400; set ::mock_failed_run 1 }
                                if {$mock_mode == "posted_transport_timeout_wip1"} { set ::mock_sr1 1; set ::mock_posted_transport_pending 1 }
                            }
                            if {$tag == "program_code_15"} {
                                if {$mock_mode == "code_whole_readback_mismatch"} { set mock_mem([expr {0x2892bffc}]) [expr {$mock_mem([expr {0x2892bffc}]) ^ 1}] }
                                if {$mock_mode == "qe_changed_code"} { set ::mock_sr2 0 }
                                if {$mock_mode == "wip_status_code"} { set ::mock_sr1 1 }
                            }
                        }
                        0x00201105 {
                            if {$arg0 != 0 || $arg2 != 4096 || $arg3 != 0 || $arg1 & 4095} { error "Bad admitted erase ABI" }
                            if {($::mock_sr1|($::mock_sr2<<8))&0x407c} { error "NOR erase while protected" }
                            if {$arg1 == 0x28ccd000} {
                                if {$::mock_flow == "install" && !$::mock_code_verified} { error "Table erased before exact whole code readback" }
                                if {$::mock_table_erased} { error "Repeated table erase" }
                                set ::mock_table_erased 1
                                set tag erase_table
                            } elseif {$arg1 == 0x2892b000 && $::mock_flow in {install restore}} {
                                if {$::mock_flow == "restore" && !$::mock_table_restored_verified} { error "Code erased before original table whole readback" }
                                if {$::mock_flow == "install" && !$::mock_aux_verified} { error "Main erased before complete auxiliary verification" }
                                if {$::mock_code_erased} { error "Repeated code erase" }
                                set ::mock_code_erased 1
                                set tag erase_code
                            } elseif {$arg1 == 0x2895a000 && $::mock_flow in {install restore}} {
                                if {$::mock_flow == "install" && ($::mock_code_erased || $::mock_table_erased)} { error "Aux install after main/entry erase" }
                                if {$::mock_flow == "restore" && (!$::mock_code_original_verified || !$::mock_table_restored_verified)} { error "Aux restore before original main and entry full readback" }
                                if {$::mock_aux_erased} { error "Repeated auxiliary erase" }
                                set ::mock_aux_erased 1
                                set tag erase_aux
                            } else { error "Arbitrary NOR erase address" }
                            lappend ::mock_mutation_calls $tag
                            for {set j 0} {$j < 1024} {incr j} { set mock_mem([expr {$arg1+4*$j}]) 0xffffffff }
                            if {$mock_mode == "erase_delayed" && $tag == "erase_code"} { set ::mock_delay_remaining 60 }
                            if {($mock_mode == "erase_timeout" && $tag == "erase_code") || ($mock_mode == "aux_erase_timeout" && $tag == "erase_aux")} { set ::mock_delay_remaining 2000; set ::mock_failed_run 1 }
                        }
                        0x00202fb5 {
                            if {$arg0 < 0 || $arg0 > 1 || ($arg1 != 0x2cccd000 && $arg1 != 0x2c92b000 && $arg1 != 0x2c95a000) || $arg2 != 4096 || $arg3 != 0} { error "Bad scoped cache ABI" }
                            set tag [format "invalidate_%08x_%d" $arg1 $arg0]
                            if {$arg1 == 0x2c95a000 && $mock_mode == "aux_invalidate_native_error"} { set ret 7; set ::mock_failed_run 1 }
                            if {$arg1 == 0x2cccd000 && $arg0 == 1 && $mock_mode == "aux_changed_after_invalidation"} { set mock_mem([expr {0x2895affc}]) [expr {$mock_mem([expr {0x2895affc}]) ^ 1}] }
                        }
                        default { error "Arbitrary callee not admitted" }
                    }
                    lappend ::mock_calls $tag
                    lappend ::mock_order $tag
                    set mock_mem([expr {$base+148}]) 0
                    set mock_mem([expr {$base+152}]) 1
                    set mock_mem([expr {$base+156}]) $ret
                    set mock_mem([expr {$base+160}]) 0x43414c4c
                    set pc_offset 46
                }
                set mock_mem([expr {0x20003b80}]) 0
                set mock_regs(15) [expr {$base-0x1fe00000+$pc_offset}]
                foreach sel {0 1 2 3 4 5 7 14} { set mock_regs($sel) [expr {0x200000+$sel}] }
                set mock_regs(20) 1
                set mock_regs(34) 1
                set mock_mem($addr) 0x0013000b
                set mock_mem([expr {0xe000ed30}]) 2
                for {set j 198} {$j < 256} {incr j} { set mock_mem([expr {$base+4*$j}]) [expr {0xbb000000+$j}] }
                if {$::mock_code_programmed && $mock_mode == "reset_code"} { set mock_mem($addr) 0x0213000b; set ::mock_failed_run 1 }
                if {$::mock_code_programmed && $mock_mode == "fault_code"} { set mock_mem([expr {0xe000ed28}]) 1; set mock_regs(16) 0x01000003; set ::mock_failed_run 1 }
                if {$::mock_aux_programmed && $mock_mode == "aux_reset"} { set mock_mem($addr) 0x0213000b; set ::mock_failed_run 1 }
                if {$::mock_aux_programmed && $mock_mode == "aux_fault"} { set mock_mem([expr {0xe000ed28}]) 1; set mock_regs(16) 0x01000003; set ::mock_failed_run 1 }
                if {$mock_mode == "initialized_config_changed"} { set mock_mem([expr {0x20003ad4}]) 0x00001605 }
            }
'''
model = model[:start] + native + model[end:]
model = model.replace("    set i 0\n    foreach value $values {", r'''
    if {$::mock_failed_run && ($address == $mock_scratch_base || $address == 0x20003b80)} { set ::mock_stale_replay 1; error "Stale RAM/lock replay after unsafe native run" }
    if {$::mock_failed_run && $address == 0xe000edf4 && ([lindex $values 0]&0x10000)} { set ::mock_stale_replay 1; error "Stale core replay after unsafe native run" }
    if {$address >= 0x58000000 && $address < 0x59000000} { error "Forbidden APDBG write" }
    if {$address >= 0x40140000 && $address < 0x40141000} { error "Forbidden secondary SPI write" }
    set i 0
    foreach value $values {''')
model = model.replace("if {$address < 0x20000000 || $address >= 0x20100000}",
    "if {!(($address >= 0x20000000 && $address < 0x20100000) || ($address in {0x28ccd000 0x2892b000 0x2895a000} && $size == 4096))}")

checks = r'''
proc mock_assert_original_context {} {
    global mock_saved_regs mock_regs mock_mem mock_scratch_base
    array set wanted $mock_saved_regs
    foreach sel [array names wanted] { if {$mock_regs($sel) != $wanted($sel)} { error "Core restore mismatch $sel" } }
    for {set i 0} {$i < 256} {incr i} { if {$mock_mem([expr {$mock_scratch_base+4*$i}]) != 0xab000000+$i} { error "Whole 1024B borrowed RAM not restored" } }
    if {$mock_mem([expr {0xe000edf8}]) != 0x11223344 || ($mock_mem([expr {0xe000edf0}])&15) != 3} { error "Original DCRDR/halted controls not restored" }
}
proc mock_partial_restore {} {
    global native_image_drawer_mock_output mock_original_sr1 mock_original_sr2 nid_last_sr1 nid_last_sr2 nidi_table_original_words nid_app_result
    file mkdir $native_image_drawer_mock_output
    set nid_app_result [open [file join $native_image_drawer_mock_output supervised-result.txt] w]
    set bp [expr {($mock_original_sr1|($mock_original_sr2<<8))&0x407c}]
    nid_execute_call [file join $native_image_drawer_mock_output status-before] read read-status 0 mock_remove_fpb
    nidi_verify_status original $mock_original_sr1 $mock_original_sr2 $nid_last_sr1 $nid_last_sr2
    nid_execute_call [file join $native_image_drawer_mock_output unprotect] onecall unprotect $bp mock_remove_fpb
    nid_status_stage [file join $native_image_drawer_mock_output status-unprotected] unprotected $mock_original_sr1 $mock_original_sr2 mock_remove_fpb
    nid_write_sector $native_image_drawer_mock_output restore-table $nidi_table_original_words $bp mock_remove_fpb
    nid_verify_sector $native_image_drawer_mock_output table $nidi_table_original_words
    nid_execute_call [file join $native_image_drawer_mock_output reprotect] onecall reprotect $bp mock_remove_fpb
    nid_status_stage [file join $native_image_drawer_mock_output status-restored] original $mock_original_sr1 $mock_original_sr2 mock_remove_fpb
    foreach cache {i d} { nid_execute_call [file join $native_image_drawer_mock_output invalidate-table-$cache] onecall invalidate-table-$cache $bp mock_remove_fpb }
    close $nid_app_result
}
if {$mock_mode == "aux_page16_refusal"} {
    file mkdir $native_image_drawer_mock_output
    set mock_error [catch {nid_execute_call [file join $native_image_drawer_mock_output refused] onecall install-aux-page-16 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "aux_wrong_source_refusal"} {
    set wrong [lreplace $nidi_aux_patched_words 0 0 0xffffffff]
    set mock_error [catch {nid_write_sector $native_image_drawer_mock_output install-aux $wrong 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "aux_arbitrary_stage_refusal"} {
    file mkdir $native_image_drawer_mock_output
    set mock_error [catch {nid_execute_call [file join $native_image_drawer_mock_output refused] onecall install-aux-page-0-other 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "arbitrary_callee"} {
    file mkdir $native_image_drawer_mock_output
    set mock_error [catch {nid_execute_call [file join $native_image_drawer_mock_output refused] onecall native-callee-00201381 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "arbitrary_mode"} {
    set mock_error [catch {nid_run_native_image_drawer $native_image_drawer_mock_output program mock_remove_fpb} mock_message]
} elseif {$mock_mode == "arbitrary_stage"} {
    file mkdir $native_image_drawer_mock_output
    set mock_error [catch {nid_execute_call [file join $native_image_drawer_mock_output refused] onecall arbitrary-28825100 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "arbitrary_helper_prefix"} {
    set mock_error [catch {nid_write_sector $native_image_drawer_mock_output arbitrary-28825100 $nidi_table_original_words 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "arbitrary_helper_words"} {
    set wrong [lreplace $nidi_table_original_words 0 0 0xffffffff]
    set mock_error [catch {nid_write_sector $native_image_drawer_mock_output restore-table $wrong 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "partial_table_fixed_restore"} {
    set mock_error [catch {mock_partial_restore} mock_message]
} else {
    set mock_error [catch {nid_run_native_image_drawer $native_image_drawer_mock_output $mock_flow mock_remove_fpb} mock_message]
}
set mock_operation_log ""
if {[file exists [file join $native_image_drawer_mock_output result.txt]]} {
    set f [open [file join $native_image_drawer_mock_output result.txt] r]
    set mock_operation_log [read $f]
    close $f
}
proc mock_sector_mutations {label state} {
    set raw [set ::mock_${label}_${state}]
    set tags [list erase_$label]
    for {set page 0} {$page < 16} {incr page} {
        set ff 1
        foreach word [lrange $raw [expr {$page*64}] [expr {$page*64+63}]] { if {$word != 0xffffffff} { set ff 0 } }
        if {!$ff} { lappend tags program_${label}_$page }
    }
    return $tags
}
set install_aux [mock_sector_mutations aux patched]
set install_code [mock_sector_mutations code patched]
set install_table [mock_sector_mutations table patched]
set restore_aux [mock_sector_mutations aux original]
set restore_code [mock_sector_mutations code original]
set restore_table [mock_sector_mutations table original]
set mock_success [expr {$mock_mode in {install_bp0 install_bp7c restore_bp0 restore_bp7c restore_fast_tap_baseline erase_delayed partial_table_fixed_restore}}]
if {$mock_success} {
    if {$mock_error || !$nid_safe_to_resume || !$nid_flash_mutation_possible} { error "Fixed native tap success failed: $mock_message" }
    mock_assert_original_context
    if {$mock_sr1 != $mock_original_sr1 || $mock_sr2 != $mock_original_sr2} { error "BP/QE/full stable status not restored" }
    if {$mock_flow == "install"} {
        set final_table $mock_table_patched; set final_code $mock_code_patched; set final_aux $mock_aux_patched
        set expected_mutations [concat $install_aux $install_code $install_table]
    } elseif {$mock_flow == "restore"} {
        set final_table $mock_table_original; set final_code $mock_code_original; set final_aux $mock_aux_original
        set expected_mutations [concat $restore_table $restore_code $restore_aux]
    } else {
        set final_table $mock_table_original; set final_code $mock_code_patched; set final_aux $mock_aux_patched
        set expected_mutations $restore_table
    }
    if {$mock_original_sr1 & 0x7c} { set expected_mutations [concat unprotect $expected_mutations reprotect] }
    if {$mock_mutation_calls != $expected_mutations} { error "Three-page mutation order/count differs: $mock_mutation_calls" }
    foreach {address wanted} [list 0x28ccd000 $final_table 0x2892b000 $final_code 0x2895a000 $final_aux] {
        for {set i 0} {$i < 1024} {incr i} {
            if {$mock_mem([expr {$address+4*$i}]) != [lindex $wanted $i]} { error [format "Independent full page %08x word%d differs" $address $i] }
        }
    }
    if {$mock_flow != "partial"} {
        if {!$nid_app_complete} { error "Final complete flag missing" }
        set invalidations {}
        foreach tag $mock_calls { if {[string match invalidate_* $tag]} { lappend invalidations $tag } }
        if {$invalidations != {invalidate_2c95a000_0 invalidate_2c95a000_1 invalidate_2c92b000_0 invalidate_2c92b000_1 invalidate_2cccd000_0 invalidate_2cccd000_1}} { error "All three I/D cache closures missing or out of order" }
    }
    if {$mock_mode == "erase_delayed" && ($mock_delayed_samples != 60 || $mock_virtual_ms < 300)} { error "5000ms erase budget failed slow success" }
} else {
    if {!$mock_error || $nid_safe_to_resume || $nid_app_complete} { error "Failure did not leave operation unsafe/incomplete: $mock_message" }
    if {$mock_mode in {baseline_table_mismatch baseline_code_mismatch restore_baseline_table_mismatch restore_baseline_code_mismatch baseline_aux_mismatch restore_baseline_aux_mismatch mixed_image_code_fast_aux mixed_fast_code_image_aux install_image_aux_only active_watchdog watchdog_reenabled arbitrary_callee arbitrary_mode arbitrary_stage arbitrary_helper_prefix arbitrary_helper_words aux_page16_refusal aux_wrong_source_refusal aux_arbitrary_stage_refusal install_image_drawer_baseline tap_v1_baseline_code tap_v1_baseline_pair card_baseline_code card_baseline_pair stock_aux_baseline smooth_baseline_code smooth_baseline_pair ease_baseline_code ease_baseline_pair first_drawer_baseline_code first_drawer_baseline_pair broker_baseline_code broker_baseline_table broker_baseline_pair stock_baseline_code stock_baseline_table stock_baseline_pair counter_baseline_code counter_baseline_table counter_baseline_pair}} {
        if {$mock_exec || [llength $mock_mutation_calls] || $nid_flash_mutation_possible} { error "Refusal admitted native execution/mutation: $mock_calls" }
        mock_assert_original_context
        if {[string match "*baseline*mismatch" $mock_mode] && (![string match "*sector baselines*" $mock_operation_log] || $mock_wdt_reads != 1)} { error "Wrong three-page baseline refusal gate" }
        if {$mock_mode == "active_watchdog" && (![string match "*Outer verified native AON watchdog stop required*" $mock_operation_log] || $mock_wdt_reads != 1)} { error "Wrong active watchdog refusal gate" }
        if {$mock_mode == "watchdog_reenabled" && $mock_wdt_reads != 3} { error "Watchdog did not reject immediately before native execution" }
    } elseif {$mock_mode in {aux_reset aux_fault aux_native_error aux_program_timeout}} {
        if {$mock_mutation_calls != {erase_aux program_aux_0} || !$mock_failed_run || $mock_stale_replay || !$nid_flash_mutation_possible} { error "Unclosed aux execution followed by later mutation/stale replay" }
        if {$mock_regs(15) == 0x0c0104c6 || $mock_mem($mock_scratch_base) == 0xab000000} { error "Stale aux PC/scratch replayed" }
        if {$mock_mode == "aux_program_timeout" && $mock_virtual_ms != 1000} { error "Aux program timeout not1000ms" }
    } elseif {$mock_mode in {reset_code fault_code native_error_code posted_transport_timeout_wip1}} {
        if {$mock_mutation_calls != [concat $install_aux {erase_code program_code_0}] || !$mock_failed_run || $mock_stale_replay || !$nid_flash_mutation_possible} { error "Unclosed main execution followed by entry mutation/stale replay" }
        if {$mock_regs(15) == 0x0c0104c6 || $mock_mem($mock_scratch_base) == 0xab000000} { error "Stale main PC/scratch replayed" }
    } elseif {$mock_mode in {erase_timeout aux_erase_timeout}} {
        set wanted {erase_aux}
        if {$mock_mode == "erase_timeout"} { set wanted [concat $install_aux erase_code] }
        if {$mock_mutation_calls != $wanted || !$mock_failed_run || $mock_stale_replay || $mock_virtual_ms != 5000 || $mock_delayed_samples < 1001} { error "Erase timeout unsafe or not5000ms" }
    } elseif {$mock_mode == "program_timeout"} {
        if {$mock_mutation_calls != [concat $install_aux {erase_code program_code_0}] || !$mock_failed_run || $mock_stale_replay || $mock_virtual_ms != 1000 || $mock_delayed_samples < 201} { error "Program timeout unsafe or not1000ms" }
    } elseif {$mock_mode == "read_timeout"} {
        if {[llength $mock_mutation_calls] || !$mock_failed_run || $mock_stale_replay || $mock_virtual_ms != 250 || $mock_delayed_samples < 51} { error "Read timeout unsafe or not250ms" }
    } elseif {$mock_mode in {aux_whole_readback_mismatch aux_qe_changed aux_wip_status}} {
        if {$mock_mutation_calls != $install_aux || !$nid_flash_mutation_possible} { error "Aux readback/status failure allowed main or entry erase" }
        mock_assert_original_context
    } elseif {$mock_mode in {code_whole_readback_mismatch qe_changed_code wip_status_code}} {
        if {$mock_mutation_calls != [concat $install_aux $install_code] || !$nid_flash_mutation_possible} { error "Main readback/status failure allowed entry erase" }
        mock_assert_original_context
    } elseif {$mock_mode == "restore_aux_native_error"} {
        if {$mock_mutation_calls != [concat $restore_table $restore_code {erase_aux program_aux_0}] || !$mock_code_original_verified || !$mock_failed_run || $mock_stale_replay} { error "Restore aux failure not isolated after original main/entry verification" }
    } elseif {$mock_mode == "table_native_error"} {
        if {$mock_mutation_calls != [concat $install_aux $install_code {erase_table program_table_0}] || !$mock_failed_run || $mock_stale_replay} { error "Entry failure allowed stale replay/later mutation" }
    } elseif {$mock_mode in {aux_invalidate_native_error aux_changed_after_invalidation}} {
        if {$mock_mutation_calls != [concat $install_aux $install_code $install_table]} { error "Cache closure failure performed unexpected mutation" }
        if {$mock_mode == "aux_invalidate_native_error" && (!$mock_failed_run || $mock_stale_replay)} { error "Unclosed auxiliary cache call replayed stale context" }
        if {$mock_mode == "aux_changed_after_invalidation"} { mock_assert_original_context }
    } elseif {$mock_mode == "initialized_config_changed"} {
        if {$mock_exec != 1 || [llength $mock_mutation_calls] || $nid_flash_mutation_possible} { error "Initialized data drift did not stop before NOR mutation" }
        mock_assert_original_context
    } else { error "Unknown mock case" }
}
if {$mock_apdbg_reads != 0} { error "A7 isolation violated" }
if {![file exists $native_image_drawer_mock_output]} { file mkdir $native_image_drawer_mock_output }
set f [open [file join $native_image_drawer_mock_output mock-summary.txt] w]
foreach name {mode error message mutation_calls calls order exec stale_replay wdt_reads delayed_samples virtual_ms} { puts $f "$name [set mock_$name]" }
puts $f "safe_to_resume $nid_safe_to_resume"
puts $f "complete $nid_app_complete"
puts $f "mutation_possible $nid_flash_mutation_possible"
close $f
echo "MOCK_ONLY_PASS $mock_mode"
shutdown
'''

cases = ["install_bp0", "install_bp7c", "restore_bp0", "restore_bp7c", "restore_fast_tap_baseline", "baseline_table_mismatch", "baseline_code_mismatch", "restore_baseline_table_mismatch", "restore_baseline_code_mismatch",
         "reset_code", "fault_code", "native_error_code", "posted_transport_timeout_wip1", "code_whole_readback_mismatch", "qe_changed_code", "wip_status_code",
         "active_watchdog", "watchdog_reenabled", "initialized_config_changed", "erase_delayed", "erase_timeout", "program_timeout", "read_timeout",
         "arbitrary_callee", "arbitrary_mode", "arbitrary_stage", "arbitrary_helper_prefix", "arbitrary_helper_words", "partial_table_fixed_restore", "install_image_drawer_baseline", "tap_v1_baseline_code", "tap_v1_baseline_pair", "card_baseline_code", "card_baseline_pair", "stock_aux_baseline", "smooth_baseline_code", "smooth_baseline_pair", "ease_baseline_code", "ease_baseline_pair", "first_drawer_baseline_code", "first_drawer_baseline_pair", "broker_baseline_code", "broker_baseline_table", "broker_baseline_pair", "stock_baseline_code", "stock_baseline_table", "stock_baseline_pair", "counter_baseline_code", "counter_baseline_table", "counter_baseline_pair"]
cases += ["baseline_aux_mismatch", "restore_baseline_aux_mismatch", "mixed_image_code_fast_aux", "mixed_fast_code_image_aux", "install_image_aux_only",
          "aux_reset", "aux_fault", "aux_native_error", "aux_program_timeout", "aux_erase_timeout", "aux_whole_readback_mismatch", "aux_qe_changed", "aux_wip_status",
          "restore_aux_native_error", "table_native_error", "aux_invalidate_native_error", "aux_changed_after_invalidation",
          "aux_page16_refusal", "aux_wrong_source_refusal", "aux_arbitrary_stage_refusal"]
hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
          [ROOT / "diagnostics/boot-nor-native-image-drawer-runner.cfg", ROOT / "diagnostics/boot-nor-native-image-drawer-stage-inputs.cfg", ROOT / "analysis/persistence/native_image_drawer_three_page_writer.py", Path(__file__)]}

def run_case(case):
    case_dir = RUN / case
    harness = RUN / f"{case}-harness.cfg"
    prefix = f"set native_image_drawer_mock_mode {{{case}}}\nset native_image_drawer_mock_output {{{case_dir.as_posix()}}}\n"
    # These commands can never reach a real target even if a reviewed library regresses.
    prefix += 'foreach dangerous {init adapter reset halt resume load_image flash} {\n    if {[llength [info commands $dangerous]]} { rename $dangerous mock_real_$dangerous }\n    proc $dangerous args { error "Hardware/API use forbidden in offline mock" }\n}\n'
    harness.write_text(prefix + model + checks, encoding="utf-8")
    result = subprocess.run([str(EXE), "-f", str(harness)], cwd=ROOT, capture_output=True, text=True, timeout=30)
    log = result.stdout + result.stderr
    (RUN / f"{case}-host.txt").write_text(log, encoding="utf-8")
    passed = f"MOCK_ONLY_PASS {case}" in log
    return {"case": case, "passed": passed, "evidence": str((case_dir / "mock-summary.txt").relative_to(ROOT)),
            "host_log": str((RUN / f"{case}-host.txt").relative_to(ROOT))}

with ThreadPoolExecutor(max_workers=4) as pool:
    reports = list(pool.map(run_case, cases))
summary = {"scope": "Offline Jim mocks only; no adapter/init/target connection, no device memory access", "source_sha256": hashes,
           "independent_sector_sha256": {f"{label}_{state}": hashlib.sha256(data).hexdigest() for (label, state), data in fixture.items()},
           "cases": reports, "all_passed": all(r["passed"] for r in reports),
           "limits": ["Native ARM instruction execution is simulated, not CPU-emulated", "Cold boot acceptance and physical recovery are not demonstrated by this test",
                      "original fixture means exact frozen fast-tap triple; image/fast/tap/card/smooth/ease/first-drawer entry pages remain byte-for-byte identical, so the code page identifies the accepted variant",
                      "Partial table uses fixed supervised helper after model fresh-reader/controller provenance, not expanded public mode"]}
(RUN / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
(OUT / "latest-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
failed = [r["case"] for r in reports if not r["passed"]]
print(f"Fixed native image-drawer offline mocks: {len(reports) - len(failed)}/{len(reports)} passed; output={RUN.relative_to(ROOT)}")
if failed:
    raise RuntimeError("Failed cases: " + ", ".join(failed))
