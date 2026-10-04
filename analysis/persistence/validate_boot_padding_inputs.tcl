# Pure offline metadata validators; no adapter/init or device API is configured.
source diagnostics/boot-nor-padding-stage-inputs.cfg
set task_sp 0x200d5d80
foreach bp {0 0x7c 0x407c} {
    foreach stage {program erase_restore invalidate_i invalidate_d} {
        array set task_spec [bnt_stage_inputs $stage $task_sp $bp]
        if {$task_spec(data_base) != $task_sp-1024 || $task_spec(payload_address)+256 != $task_sp-512 ||
            [llength $task_spec(image_words)] != 42 || [llength $task_spec(payload_words)] != 64 ||
            $task_spec(bkpt_offset) != 46 || $task_spec(output_words) != 9} {
            error "Placement/image metadata mismatch"
        }
        if {$stage == "program" && $task_spec(io_input_words) != [list 0x00201249 0 0x28825100 $task_spec(payload_address) 0x100]} {
            # Compare numeric element values, not hex versus decimal spelling.
            foreach a $task_spec(io_input_words) b [list 0x00201249 0 0x28825100 $task_spec(payload_address) 0x100] {
                if {$a != $b} { error "Program scope differs" }
            }
        }
    }
    if {$bp == 0} {
        foreach stage {unprotect reprotect} {
            if {![catch {bnt_stage_inputs $stage $task_sp $bp}]} { error "BP0 admitted unnecessary protection mutation" }
        }
    } else {
        array set task_u [bnt_stage_inputs unprotect $task_sp $bp]
        array set task_r [bnt_stage_inputs reprotect $task_sp $bp]
        if {[lindex $task_u(io_input_words) 2] != 0 || [lindex $task_r(io_input_words) 2] != $bp} { error "BP restoration scope differs" }
    }
}
foreach inputs [list [list arbitrary $task_sp 0] [list program 0x200d4000 0] [list program 0x200d5d84 0] [list program $task_sp 0x80]] {
    if {![catch {eval bnt_stage_inputs $inputs}]} { error "Invalid stage/stack/BP input admitted" }
}
if {![bnt_verify_sector before $bnt_original_sector_words] || ![bnt_verify_sector programmed $bnt_programmed_sector_words] ||
    ![bnt_verify_sector restored $bnt_original_sector_words]} { error "Valid whole-sector verification failed" }
set task_wrong [lreplace $bnt_original_sector_words 500 500 0]
if {![catch {bnt_verify_sector restored $task_wrong}]} { error "Sector damage was not rejected" }
if {![bnt_verify_status unprotected 0x7c 2 0 2] || ![bnt_verify_status restored 0x7c 2 0x7c 2] ||
    ![bnt_verify_status unprotected 0x7c 0x42 0 2]} { error "Valid BP/QE verification failed" }
foreach args {{restored 0x7c 2 0x7c 0} {unprotected 0x7c 2 1 2} {restored 1 2 0 2} {unprotected 0x7c 2 0x40 2}} {
    if {![catch {eval bnt_verify_status $args}]} { error "Bad stable status/WIP/WEL was not rejected" }
}
echo "OFFLINE_PADDING_INPUTS_PASS; device_I/O=0; automatic_execution=0"
shutdown
