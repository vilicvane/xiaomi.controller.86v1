"""Fixed three-page extension to the immutable card caller; offline text only.

No native callee or scratch ABI changes. This changes public orchestration and
adds only the exact 0x95a000 auxiliary page to the bounded stage allowlist.
"""


def replace_once(text, old, new):
    assert text.count(old) == 1, 'Reviewed three-page source anchor drift: ' + old[:72]
    return text.replace(old, new, 1)


def stages(old):
    text = old.replace('bnai_', 'ngti_')
    text = text.replace('ngti_table_patched_words', 'ngti_table_patched_words ngti_aux_original_words ngti_aux_patched_words', 2)
    text = text.replace('(install-code|install-table|restore-table|restore-code)', '(install-code|install-table|install-aux|restore-table|restore-code|restore-aux)')
    text = replace_once(text,
        'if {[string match "*-code" $prefix]} { set address 0x2892b000 } else { set address 0x28ccd000 }',
        'if {[string match "*-code" $prefix]} { set address 0x2892b000\n        } elseif {[string match "*-aux" $prefix]} { set address 0x2895a000\n        } else { set address 0x28ccd000 }')
    text = replace_once(text,
        '} else { set sector $ngti_code_original_words; set address 0x2892b000 }',
        '} elseif {$prefix == "restore-code"} { set sector $ngti_code_original_words; set address 0x2892b000\n        } elseif {$prefix == "install-aux"} { set sector $ngti_aux_patched_words; set address 0x2895a000\n        } else { set sector $ngti_aux_original_words; set address 0x2895a000 }')
    text = text.replace('^invalidate-(code|table)-(i|d)$', '^invalidate-(code|table|aux)-(i|d)$')
    text = replace_once(text,
        'if {$label == "code"} { set address 0x2c92b000 } else { set address 0x2cccd000 }',
        'if {$label == "code"} { set address 0x2c92b000\n        } elseif {$label == "aux"} { set address 0x2c95a000\n        } else { set address 0x2cccd000 }')
    return text


PUBLIC = r'''
proc ngt_verify_sector {dir label expected} {
    global ngti_code_original_words ngti_code_patched_words ngti_table_original_words ngti_table_patched_words
    global ngti_aux_original_words ngti_aux_patched_words
    if {$label == "code"} {
        set address 0x2892b000
        if {$expected != $ngti_code_original_words && $expected != $ngti_code_patched_words} { error "Unreviewed code-sector comparison source" }
    } elseif {$label == "table"} {
        set address 0x28ccd000
        if {$expected != $ngti_table_original_words && $expected != $ngti_table_patched_words} { error "Unreviewed table-sector comparison source" }
    } elseif {$label == "aux"} {
        set address 0x2895a000
        if {$expected != $ngti_aux_original_words && $expected != $ngti_aux_patched_words} { error "Unreviewed aux-sector comparison source" }
    } else { error "Unreviewed sector" }
    ngt_stable_halt
    if {[ngt_words $address 1024] != $expected} { error "Exact whole4K $label readback failed" }
    dump_image [file join $dir sector-$label-verified.bin] $address 4096
    ngt_app_log "whole_sector_verified $label"
}
proc ngt_write_sector {dir prefix words original_bp remove_fpb_command} {
    global ngti_code_original_words ngti_code_patched_words ngti_table_original_words ngti_table_patched_words
    global ngti_aux_original_words ngti_aux_patched_words
    if {$prefix == "install-code"} { set fixed_words $ngti_code_patched_words
    } elseif {$prefix == "install-table"} { set fixed_words $ngti_table_patched_words
    } elseif {$prefix == "install-aux"} { set fixed_words $ngti_aux_patched_words
    } elseif {$prefix == "restore-table"} { set fixed_words $ngti_table_original_words
    } elseif {$prefix == "restore-code"} { set fixed_words $ngti_code_original_words
    } elseif {$prefix == "restore-aux"} { set fixed_words $ngti_aux_original_words
    } else { error "Sector helper admits only exact reviewed code/table/aux stages" }
    if {$words != $fixed_words} { error "Sector helper refuses arbitrary source data before erase" }
    ngt_execute_call [file join $dir $prefix-erase] onecall $prefix-erase $original_bp $remove_fpb_command
    for {set page 0} {$page < 16} {incr page} {
        set expected_page [lrange $words [expr {64*$page}] [expr {64*$page+63}]]
        if {[ngti_page_is_ff $expected_page]} { ngt_app_log "skip_FF_page $prefix $page"
        } else { ngt_execute_call [file join $dir $prefix-page-$page] onecall $prefix-page-$page $original_bp $remove_fpb_command }
    }
}
proc ngt_run_native_github_tap {capture_dir mode remove_fpb_command} {
    global ngt_safe_to_resume ngt_app_complete ngt_flash_mutation_possible ngt_app_result
    global ngt_last_sr1 ngt_last_sr2 bnor_safe_to_resume bnor_reset_seen bnor_track_reset
    global ngti_code_original_words ngti_code_patched_words ngti_table_original_words ngti_table_patched_words
    global ngti_aux_original_words ngti_aux_patched_words
    set ngt_safe_to_resume 0; set ngt_app_complete 0; set ngt_flash_mutation_possible 0
    if {$mode != "install" && $mode != "restore"} { error "Only reviewed install or restore accepted" }
    if {![info exists bnor_safe_to_resume] || !$bnor_safe_to_resume ||
        ![info exists bnor_reset_seen] || $bnor_reset_seen || ![info exists bnor_track_reset] || !$bnor_track_reset} {
        error "Successful same-process independent reader is required"
    }
    if {[file exists $capture_dir]} { error "New capture directory required" }
    file mkdir $capture_dir
    set ngt_app_result [open [file join $capture_dir result.txt] w]
    ngt_app_log "scope mode=$mode; fixedsectors92b000/95a000/ccd000 only; no automatic retry/resume"
    set operation_error [catch {
        ngt_stable_halt
        if {[ngt_word 0x40082008] != 0} { error "Outer verified native AON watchdog stop required" }
        ngt_a7_gate held-reset-cmu-verified
        set code_before [ngt_words 0x2892b000 1024]
        set table_before [ngt_words 0x28ccd000 1024]
        set aux_before [ngt_words 0x2895a000 1024]
        if {$mode == "install"} {
            if {$code_before != $ngti_code_original_words || $table_before != $ngti_table_original_words ||
                $aux_before != $ngti_aux_original_words} { error "Install requires all three exact card-v1 sector baselines" }
        } else {
            if {!(($code_before == $ngti_code_original_words && $table_before == $ngti_table_original_words && $aux_before == $ngti_aux_original_words) ||
                ($code_before == $ngti_code_patched_words && $table_before == $ngti_table_patched_words && $aux_before == $ngti_aux_patched_words))} {
                error "Restore requires all three exact card-v1 or all three exact github-tap sector baselines"
            }
        }
        dump_image [file join $capture_dir sector-code-before.bin] 0x2892b000 4096
        dump_image [file join $capture_dir sector-table-before.bin] 0x28ccd000 4096
        dump_image [file join $capture_dir sector-aux-before.bin] 0x2895a000 4096
        ngt_execute_call [file join $capture_dir status-before] read read-status 0 $remove_fpb_command
        set original_sr1 $ngt_last_sr1; set original_sr2 $ngt_last_sr2
        ngti_verify_status original $original_sr1 $original_sr2 $original_sr1 $original_sr2
        set original_bp [expr {($original_sr1|($original_sr2<<8))&0x407c}]
        if {$original_bp != 0} { ngt_execute_call [file join $capture_dir unprotect] onecall unprotect $original_bp $remove_fpb_command }
        ngt_status_stage [file join $capture_dir status-unprotected] unprotected $original_sr1 $original_sr2 $remove_fpb_command
        if {$mode == "install"} {
            # Admit and verify the complete auxiliary page before main can reference it.
            ngt_write_sector $capture_dir install-aux $ngti_aux_patched_words $original_bp $remove_fpb_command
            ngt_verify_sector $capture_dir aux $ngti_aux_patched_words
            ngt_status_stage [file join $capture_dir status-aux] unprotected $original_sr1 $original_sr2 $remove_fpb_command
            ngt_write_sector $capture_dir install-code $ngti_code_patched_words $original_bp $remove_fpb_command
            ngt_verify_sector $capture_dir code $ngti_code_patched_words
            ngt_status_stage [file join $capture_dir status-code] unprotected $original_sr1 $original_sr2 $remove_fpb_command
            ngt_write_sector $capture_dir install-table $ngti_table_patched_words $original_bp $remove_fpb_command
            ngt_verify_sector $capture_dir table $ngti_table_patched_words
            set expected_code $ngti_code_patched_words; set expected_table $ngti_table_patched_words; set expected_aux $ngti_aux_patched_words
        } else {
            ngt_write_sector $capture_dir restore-table $ngti_table_original_words $original_bp $remove_fpb_command
            ngt_verify_sector $capture_dir table $ngti_table_original_words
            ngt_status_stage [file join $capture_dir status-table-restored] unprotected $original_sr1 $original_sr2 $remove_fpb_command
            # Remove all main references before returning the auxiliary slot to stock.
            ngt_write_sector $capture_dir restore-code $ngti_code_original_words $original_bp $remove_fpb_command
            ngt_verify_sector $capture_dir code $ngti_code_original_words
            ngt_status_stage [file join $capture_dir status-code-restored] unprotected $original_sr1 $original_sr2 $remove_fpb_command
            ngt_write_sector $capture_dir restore-aux $ngti_aux_original_words $original_bp $remove_fpb_command
            ngt_verify_sector $capture_dir aux $ngti_aux_original_words
            set expected_code $ngti_code_original_words; set expected_table $ngti_table_original_words; set expected_aux $ngti_aux_original_words
        }
        ngt_status_stage [file join $capture_dir status-final-data] unprotected $original_sr1 $original_sr2 $remove_fpb_command
        if {$original_bp != 0} { ngt_execute_call [file join $capture_dir reprotect] onecall reprotect $original_bp $remove_fpb_command }
        ngt_status_stage [file join $capture_dir status-restored] original $original_sr1 $original_sr2 $remove_fpb_command
        foreach sector {aux code table} {
            foreach cache {i d} {
                set stage invalidate-$sector-$cache
                ngt_execute_call [file join $capture_dir $stage] onecall $stage $original_bp $remove_fpb_command
            }
        }
        if {[ngt_words 0x2892b000 1024] != $expected_code || [ngt_words 0x28ccd000 1024] != $expected_table ||
            [ngt_words 0x2895a000 1024] != $expected_aux} { error "Whole three sectors changed after cache invalidation" }
        ngt_stable_halt; ngt_a7_gate held-reset-cmu-verified
        if {[ngt_word 0x40082008] != 0} { error "Stopped AON watchdog changed" }
        set ngt_app_complete 1; set ngt_safe_to_resume 1
        ngt_app_log "app_data_protection_context_verified 1; leaveBOOT halted; outer owns finalGLOBAL"
    } operation_message]
    if {$operation_error} {
        set ngt_safe_to_resume 0
        ngt_app_log "operation_error $operation_message"
        ngt_app_log "NO_AUTO_NEXT_STAGE_OR_RESUME; inspect physical sectors/status and closed native context"
    }
    ngt_app_log "flash_mutation_possible $ngt_flash_mutation_possible complete $ngt_app_complete safe_to_resume $ngt_safe_to_resume"
    close $ngt_app_result
    if {$operation_error} { error "Fixed native app operation failed; retain halt/evidence for independent root recovery" }
    return 1
}
'''


def writer(old):
    prefix = old[:old.index('proc ngc_verify_sector')]
    prefix = prefix.replace('ngc_', 'ngt_').replace('ngci_', 'ngti_').replace('native-github-card', 'native-github-tap')
    prefix = prefix.replace('ngt_run_native_github_card', 'ngt_run_native_github_tap')
    prefix = prefix.replace('two exact reviewed A7 app sectors', 'three exact reviewed A7 app sectors')
    return prefix + PUBLIC
