# Pure Jim/Tcl simulation. No adapter config, init, or target connection exists.
source diagnostics/boot-nor-read-runner.cfg
set mock_mode $bnor_mock_mode
array set mock_mem {}
array set mock_regs {}
for {set i 0} {$i < [llength $bnor_expected_boot_words]} {incr i} {
    set mock_mem([expr {0x200001a8+4*$i}]) [lindex $bnor_expected_boot_words $i]
}
for {set i 0} {$i < 80} {incr i} { set mock_mem([expr {0x20003ae0+4*$i}]) 0 }
foreach {address value} {0x20003ae0 0x18658501 0x20003af8 0x1000000 0x20003afc 0x100 0x20003b78 0x000f0000
    0x20003acc 0x00010000
    0x20003ad0 0x18050603 0x20003ad4 0x00001604
    0x20003ad8 0x00004000
    0xe000ed00 0x630f1321 0xe000edf0 0x00130003 0xe000edf8 0x11223344 0xe000ed30 2
    0xe000ed28 0 0xe000ed2c 0 0xe000edfc 0x01110000 0xe000ee08 0x00030000
    0x40148004 0x0000000b 0x40148014 0x00304000 0x40148034 0 0x4014803c 1 0x4014800c 0
    0x58050314 0x11 0x58050088 0x01000001} {
    set mock_mem([expr {$address+0}]) [expr {$value+0}]
}
for {set i 0} {$i < 64} {incr i} { set mock_mem([expr {0x28000000+4*$i}]) [lindex $bnor_expected_nor_page_words $i] }
for {set i 0} {$i < 8} {incr i} { set mock_mem([expr {0xe0002008+4*$i}]) 0 }
foreach sel {0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 20 26 27 28 29 34} { set mock_regs($sel) [expr {0x1000+$sel}] }
foreach {sel value} {13 0x200d5d80 17 0x200d5d80 26 0x200d5d80 18 0 27 0 28 0x200d3e00 29 0 20 0 34 0 15 0x0c0104c6 16 0x61000000} {
    set mock_regs($sel) [expr {$value+0}]
}
set mock_scratch_base [expr {$mock_regs(13)-1024}]
for {set i 0} {$i < 256} {incr i} { set mock_mem([expr {$mock_scratch_base+4*$i}]) [expr {0xab000000+$i}] }
set mock_saved_regs [array get mock_regs]
set mock_writes 0
set mock_exec 0
set mock_fpb_remove_called 0
set mock_spi_reads 0
set mock_apdbg_reads 0
set mock_cmu_reads 0
set mock_a7_policy halted
if {$mock_mode == "powerdown"} {
    set mock_mem([expr {0x58050314}]) 0
    set mock_a7_policy powerdown-verified
}
if {[string match "held_reset_*" $mock_mode]} {
    set mock_a7_policy held-reset-cmu-verified
    # Captured BOOT values release A7 domain/peripheral banks while CPUbit1=0.
    foreach {address value} {
        0x400800a4 0x24d 0x40000044 0x3c038319
        0x40000114 0x000fffff 0x40000160 0xff 0x40000034 0x83fbfe3b
    } { set mock_mem([expr {$address+0}]) [expr {$value+0}] }
    if {$mock_mode == "held_reset_released_entry"} { set mock_mem([expr {0x400800a4}]) 0x24f }
}
if {$mock_mode == "source_mismatch"} {
    set mock_mem([expr {0x200003fc}]) [expr {$mock_mem([expr {0x200003fc}]) ^ 1}]
}
if {$mock_mode == "table_mismatch"} {
    set mock_mem([expr {0x20003300}]) 0x40140000
    set mock_mem([expr {0x20003304}]) 0x40148000
}
proc mock_remove_fpb {} { global mock_fpb_remove_called; set mock_fpb_remove_called 1 }
proc mock_addr {address} {
    if {$address >= 0x00200000 && $address < 0x00300000} { return [expr {$address+0x1fe00000}] }
    return [expr {$address+0}]
}
proc read_memory {address bits count} {
    global mock_mem mock_mode mock_spi_reads mock_apdbg_reads mock_cmu_reads
    if {$address >= 0x58000000 && $address < 0x58100000} {
        incr mock_apdbg_reads
        if {[string match "held_reset_*" $mock_mode]} {
            error "Mock detected forbidden APDBG access after DSP isolation"
        }
    }
    if {$address == 0x400800a4 || $address == 0x40000044 || $address == 0x40000114 ||
        $address == 0x40000160 || $address == 0x40000034} {
        incr mock_cmu_reads
        if {$mock_mode == "held_reset_released_prestart" && $mock_cmu_reads == 12} {
            set mock_mem([expr {0x400800a4}]) 0x24f
        }
        if {$mock_mode == "held_reset_bank_changed" && $mock_cmu_reads == 7} {
            set mock_mem([expr {0x40000044}]) [expr {$mock_mem([expr {0x40000044}]) ^ 0x04000000}]
        }
    }
    if {$address >= 0x40140000 && $address < 0x40141000} { error "Mock detected inactive logical-id1 SPI access" }
    if {$address >= 0x40148000 && $address < 0x40149000} { incr mock_spi_reads }
    if {$mock_mode == "powerdown" && $address == 0x58050088} { error "Mock detected forbidden powered-off DSCR access" }
    if {$bits != 32} { error "Mock only supports32bit reads" }
    set result {}
    for {set i 0} {$i < $count} {incr i} {
        set addr [mock_addr [expr {$address+4*$i}]]
        if {![info exists mock_mem($addr)]} { error [format "Unexpected mock read %08x" $addr] }
        lappend result $mock_mem($addr)
    }
    return $result
}
proc write_memory {address bits values} {
    global mock_mem mock_regs mock_writes mock_mode mock_exec mock_scratch_base
    if {$bits != 32} { error "Mock only supports32bit writes" }
    set i 0
    foreach value $values {
        set addr [mock_addr [expr {$address+4*$i}]]
        set value [expr {$value+0}]
        incr mock_writes
        # NOR mutation is forbidden even in the simulated implementation.
        if {$addr >= 0x28000000 && $addr < 0x29000000} { error "Mock detected forbidden Flash data write" }
        if {$addr == 0xe000edf4} {
            set selector [expr {$value & 127}]
            if {$value & 0x10000} {
                set mock_regs($selector) $mock_mem([expr {0xe000edf8}])
                if {$selector == 20} { set mock_regs(34) $mock_regs(20) }
            } else { set mock_mem([expr {0xe000edf8}]) $mock_regs($selector) }
        } elseif {$addr == 0xe000ed30} {
            set mock_mem($addr) [expr {$mock_mem($addr) & ~$value}]
        } elseif {$addr == 0xe000edf0} {
            set mock_mem($addr) [expr {0x00130000 | ($value & 15)}]
            if {($value & 15) == 9} {
                set mock_exec 1
                set base $mock_scratch_base
                set mock_mem([expr {$base+128}]) 0
                set mock_mem([expr {$base+132}]) 1
                foreach off {136 140 144 148 152} { set mock_mem([expr {$base+$off}]) 0 }
                set mock_mem([expr {$base+156}]) 0x52454144
                set mock_mem([expr {$base+160}]) 0x7c186585
                set mock_mem([expr {$base+164}]) 2
                set mock_mem([expr {0x20003b80}]) 0
                set mock_regs(15) [expr {$base-0x1fe00000+94}]
                foreach sel {0 1 2 3 4 5 7 14} { set mock_regs($sel) [expr {0x200000+$sel}] }
                set mock_regs(20) 1
                set mock_regs(34) 1
                set mock_mem($addr) 0x0013000b
                set mock_mem([expr {0xe000ed30}]) 2
                if {$mock_mode == "reset"} { set mock_mem($addr) 0x0213000b }
                if {$mock_mode == "fault"} { set mock_mem([expr {0xe000ed28}]) 1; set mock_regs(16) 0x01000003 }
                if {$mock_mode == "bootmode_changed"} { set mock_mem([expr {0x20003acc}]) 0x00020000 }
                if {$mock_mode == "initialized_config_changed"} { set mock_mem([expr {0x20003ad4}]) 0x00001605 }
                if {$mock_mode == "held_reset_released_post"} { set mock_mem([expr {0x400800a4}]) 0x24f }
            }
        } else { set mock_mem($addr) $value }
        incr i
    }
}
proc dump_image {path address size} {
    # Caller only requests SRAM evidence. Produce a clearly labelled mock marker.
    if {$address < 0x20000000 || $address >= 0x20100000} { error "Unexpected simulated dump range" }
    set f [open $path w]
    puts $f "MOCK ONLY: not target memory, address=$address, bytes=$size"
    close $f
}
set mock_error [catch {bnor_run_read_probe $bnor_mock_output $mock_a7_policy mock_remove_fpb} mock_message]
if {$mock_mode == "success" || $mock_mode == "powerdown" || $mock_mode == "held_reset_success"} {
    if {$mock_error || !$bnor_safe_to_resume || !$mock_fpb_remove_called || !$mock_exec} { error "Mock success execution failed: $mock_message" }
    array set wanted $mock_saved_regs
    foreach sel [array names wanted] {
        if {$mock_regs($sel) != $wanted($sel)} { error "Mock core restore failed for $sel" }
    }
    for {set i 0} {$i < 256} {incr i} {
        if {$mock_mem([expr {$mock_scratch_base+4*$i}]) != 0xab000000+$i} { error "Mock RAM restore failed" }
    }
    if {$mock_mem([expr {0xe000edf8}]) != 0x11223344 || ($mock_mem([expr {0xe000edf0}]) & 15) != 3} { error "Mock debug state restore failed" }
} elseif {$mock_mode == "reset" || $mock_mode == "fault"} {
    if {!$mock_error || $bnor_safe_to_resume || !$mock_exec} { error "Mock failed to suppress resume on $mock_mode" }
    if {$mock_regs(15) == 0x0c0104c6} { error "Mock incorrectly replayed BOOT PC after $mock_mode" }
    if {$mock_mem($mock_scratch_base) == 0xab000000} { error "Mock incorrectly restored stale RAM after $mock_mode" }
    if {($mock_mem([expr {0xe000edf0}]) & 2) == 0} { error "Mock did not request halt on $mock_mode" }
} elseif {$mock_mode == "held_reset_released_entry" || $mock_mode == "held_reset_bank_changed" ||
          $mock_mode == "held_reset_released_prestart"} {
    if {!$mock_error || $bnor_safe_to_resume || $mock_exec} { error "Mock failed to reject held-reset entry evidence before executing RAM" }
    if {($mock_mode == "held_reset_released_entry" && $mock_cmu_reads != 1) ||
        ($mock_mode == "held_reset_bank_changed" && $mock_cmu_reads != 10) ||
        ($mock_mode == "held_reset_released_prestart" && $mock_cmu_reads != 12)} {
        error "Held-reset mock rejected at an unintended gate/read count"
    }
    for {set i 0} {$i < 256} {incr i} {
        if {$mock_mem([expr {$mock_scratch_base+4*$i}]) != 0xab000000+$i} { error "Held-reset rejection failed scratch restoration" }
    }
} elseif {$mock_mode == "held_reset_released_post"} {
    if {!$mock_error || $bnor_safe_to_resume || !$mock_exec || $mock_regs(15) != 0x0c0104c6} {
        error "Mock failed to reject released A7CPU after completed read while restoring caller"
    }
} elseif {$mock_mode == "bootmode_changed" || $mock_mode == "initialized_config_changed"} {
    if {!$mock_error || $bnor_safe_to_resume || !$mock_exec || $mock_regs(15) != 0x0c0104c6} {
        error "Mock failed to reject bootmode cache mutation while restoring closed caller context"
    }
} elseif {$mock_mode == "source_mismatch"} {
    if {!$mock_error || $bnor_safe_to_resume || $mock_exec || $mock_spi_reads ||
        ![file exists [file join $bnor_mock_output boot-hal-context-preflight.bin]]} {
        error "Mock failed to preserve full preflight image before rejecting source mismatch"
    }
} elseif {$mock_mode == "table_mismatch"} {
    if {!$mock_error || $bnor_safe_to_resume || $mock_exec || $mock_spi_reads} {
        error "Mock failed to reject wrong live table before any SPI access"
    }
} else { error "Unknown mock mode" }
if {$mock_a7_policy == "held-reset-cmu-verified" && $mock_apdbg_reads != 0} { error "Held-reset policy attempted APDBG reads" }
echo "MOCK_ONLY_PASS $mock_mode writes=$mock_writes NOR_writes=0"
shutdown
