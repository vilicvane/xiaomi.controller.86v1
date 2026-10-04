"""Build fixed two-sector A7 writer inputs; offline only, no device access."""
from pathlib import Path
import argparse
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[2]
FROZEN_HOOK_SHA = "c37ef00010de3bc59155da30e88ebd8f395797f1df684667305e7ea50490e11a"
FROZEN_PATCH_SHA = "55fbb71be4fe4abd40a245f72f303073cc5afce0288a5aa238bf35ea475af4ed"
FROZEN_NOR_SHA = "777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def words(data):
    assert len(data) % 4 == 0
    return struct.unpack("<" + "I" * (len(data) // 4), data)

def tcl_list(name, data):
    nums = words(data)
    lines = ["set " + name + " {"]
    lines.extend("    " + " ".join(str(n) for n in nums[i:i+8]) for i in range(0, len(nums), 8))
    return "\n".join(lines + ["}", ""])

STAGES = r'''
foreach bnai_name {bnai_one_call_words bnai_code_original_words bnai_code_patched_words bnai_table_original_words bnai_table_patched_words} {
    set bnai_normalized {}
    foreach bnai_value [set $bnai_name] { lappend bnai_normalized [expr {$bnai_value+0}] }
    set $bnai_name $bnai_normalized
}
proc bnai_stage_inputs {stage original_sp original_bp} {
    global bnai_one_call_words bnai_code_original_words bnai_code_patched_words bnai_table_original_words bnai_table_patched_words
    if {$original_sp & 7 || $original_sp-1024 < 0x200d3e00 || $original_sp > 0x200d5e00} { error "Unreviewed BOOT stack" }
    if {$original_bp & ~0x407c} { error "Unreviewed BP bits" }
    set base [expr {$original_sp-1024}]
    set source [expr {$base+256}]
    set payload_words {}; set payload_bytes 0
    if {$stage == "unprotect" || $stage == "reprotect"} {
        if {$original_bp == 0} { error "BP0 must skip status writes" }
        set bp 0
        if {$stage == "reprotect"} { set bp $original_bp }
        set input [list 0x00200fe9 0 $bp 0 0]
    } elseif {[regexp {^(install-code|install-table|restore-table|restore-code)-erase$} $stage all prefix]} {
        if {[string match "*-code" $prefix]} { set address 0x2892b000 } else { set address 0x28ccd000 }
        set input [list 0x00201105 0 $address 4096 0]
    } elseif {[regexp {^(install-code|install-table|restore-table|restore-code)-page-([0-9]+)$} $stage all prefix page]} {
        if {$page < 0 || $page > 15 || $page != [expr {$page+0}]} { error "Page index is not admitted0..15" }
        if {$prefix == "install-code"} { set sector $bnai_code_patched_words; set address 0x2892b000
        } elseif {$prefix == "install-table"} { set sector $bnai_table_patched_words; set address 0x28ccd000
        } elseif {$prefix == "restore-table"} { set sector $bnai_table_original_words; set address 0x28ccd000
        } else { set sector $bnai_code_original_words; set address 0x2892b000 }
        set payload_words [lrange $sector [expr {64*$page}] [expr {64*$page+63}]]
        if {[bnai_page_is_ff $payload_words]} { error "FF pages must be skipped after erase" }
        set payload_bytes 256
        set input [list 0x00201249 0 [expr {$address+256*$page}] $source 256]
    } elseif {[regexp {^invalidate-(code|table)-(i|d)$} $stage all label cache]} {
        if {$label == "code"} { set address 0x2c92b000 } else { set address 0x2cccd000 }
        set id 0
        if {$cache == "d"} { set id 1 }
        set input [list 0x00202fb5 $id $address 4096 0]
    } else { error "No arbitrary native callee/address stage admitted" }
    set canonical {}
    foreach value $input { lappend canonical [expr {$value+0}] }
    return [list image_words $bnai_one_call_words io_input_words $canonical \
        payload_address $source payload_words $payload_words payload_bytes $payload_bytes]
}
proc bnai_page_is_ff {values} {
    if {[llength $values] != 64} { error "Exact256Bpage required" }
    foreach value $values { if {$value != 0xffffffff} { return 0 } }
    return 1
}
proc bnai_verify_status {phase original_sr1 original_sr2 current_sr1 current_sr2} {
    foreach value [list $original_sr1 $original_sr2 $current_sr1 $current_sr2] {
        if {$value < 0 || $value > 255} { error "Only native single-byte status accepted" }
    }
    set original [expr {$original_sr1|($original_sr2<<8)}]
    set current [expr {$current_sr1|($current_sr2<<8)}]
    if {($original_sr1|$current_sr1)&3} { error "WIP/WEL must be clear" }
    if {$phase == "unprotected"} { set expected [expr {$original & ~0x407c}]
    } elseif {$phase == "original"} { set expected $original
    } else { error "Unreviewed stable status phase" }
    if {($current & 0xfffc) != ($expected & 0xfffc)} { error "BP/QE/stable status mismatch" }
}
'''

PUBLIC = r'''
# Public operation is exactly install|restore. Unknown/partial baseline is not public.
proc bna_app_log {line} { global bna_app_result; puts $bna_app_result $line; echo $line }
proc bna_status_stage {dir phase sr1 sr2 remove_fpb_command} {
    global bna_last_sr1 bna_last_sr2
    bna_execute_call $dir read read-status 0 $remove_fpb_command
    bnai_verify_status $phase $sr1 $sr2 $bna_last_sr1 $bna_last_sr2
    bna_app_log [format "verified_status %s SR1%02x SR2%02x" $phase $bna_last_sr1 $bna_last_sr2]
}
proc bna_verify_sector {dir label expected} {
    global bnai_code_original_words bnai_code_patched_words bnai_table_original_words bnai_table_patched_words
    if {$label == "code"} {
        set address 0x2892b000
        if {$expected != $bnai_code_original_words && $expected != $bnai_code_patched_words} { error "Unreviewed code-sector comparison source" }
    } elseif {$label == "table"} {
        set address 0x28ccd000
        if {$expected != $bnai_table_original_words && $expected != $bnai_table_patched_words} { error "Unreviewed table-sector comparison source" }
    } else { error "Unreviewed sector" }
    bna_stable_halt
    if {[bna_words $address 1024] != $expected} { error "Exact whole4K $label readback failed" }
    dump_image [file join $dir sector-$label-verified.bin] $address 4096
    bna_app_log "whole_sector_verified $label"
}
proc bna_write_sector {dir prefix words original_bp remove_fpb_command} {
    global bnai_code_original_words bnai_code_patched_words bnai_table_original_words bnai_table_patched_words
    if {$prefix == "install-code"} { set fixed_words $bnai_code_patched_words
    } elseif {$prefix == "install-table"} { set fixed_words $bnai_table_patched_words
    } elseif {$prefix == "restore-table"} { set fixed_words $bnai_table_original_words
    } elseif {$prefix == "restore-code"} { set fixed_words $bnai_code_original_words
    } else { error "Sector helper admits only exact reviewed code/table stages" }
    if {$words != $fixed_words} { error "Sector helper refuses arbitrary source data before erase" }
    bna_execute_call [file join $dir $prefix-erase] onecall $prefix-erase $original_bp $remove_fpb_command
    for {set page 0} {$page < 16} {incr page} {
        set expected_page [lrange $words [expr {64*$page}] [expr {64*$page+63}]]
        if {[bnai_page_is_ff $expected_page]} { bna_app_log "skip_FF_page $prefix $page"
        } else { bna_execute_call [file join $dir $prefix-page-$page] onecall $prefix-page-$page $original_bp $remove_fpb_command }
    }
}
proc bna_run_native_app {capture_dir mode remove_fpb_command} {
    global bna_safe_to_resume bna_app_complete bna_flash_mutation_possible bna_app_result
    global bna_last_sr1 bna_last_sr2 bnor_safe_to_resume bnor_reset_seen bnor_track_reset
    global bnai_code_original_words bnai_code_patched_words bnai_table_original_words bnai_table_patched_words
    set bna_safe_to_resume 0; set bna_app_complete 0; set bna_flash_mutation_possible 0
    if {$mode != "install" && $mode != "restore"} { error "Only reviewed install or restore accepted" }
    if {![info exists bnor_safe_to_resume] || !$bnor_safe_to_resume ||
        ![info exists bnor_reset_seen] || $bnor_reset_seen || ![info exists bnor_track_reset] || !$bnor_track_reset} {
        error "Successful same-process independent reader is required"
    }
    if {[file exists $capture_dir]} { error "New capture directory required" }
    file mkdir $capture_dir
    set bna_app_result [open [file join $capture_dir result.txt] w]
    bna_app_log "scope mode=$mode; fixedsectors92b000/ccd000 only; no automatic retry/resume"
    set operation_error [catch {
        bna_stable_halt
        if {[bna_word 0x40082008] != 0} { error "Outer verified native AON watchdog stop required" }
        bna_a7_gate held-reset-cmu-verified
        set code_before [bna_words 0x2892b000 1024]
        set table_before [bna_words 0x28ccd000 1024]
        if {$mode == "install"} {
            if {$code_before != $bnai_code_original_words || $table_before != $bnai_table_original_words} { error "Install requires both exact original sector baselines" }
        } else {
            if {($code_before != $bnai_code_original_words && $code_before != $bnai_code_patched_words) ||
                ($table_before != $bnai_table_original_words && $table_before != $bnai_table_patched_words)} { error "Restore requires exact original/patched sector baselines" }
        }
        dump_image [file join $capture_dir sector-code-before.bin] 0x2892b000 4096
        dump_image [file join $capture_dir sector-table-before.bin] 0x28ccd000 4096
        bna_execute_call [file join $capture_dir status-before] read read-status 0 $remove_fpb_command
        set original_sr1 $bna_last_sr1; set original_sr2 $bna_last_sr2
        bnai_verify_status original $original_sr1 $original_sr2 $original_sr1 $original_sr2
        set original_bp [expr {($original_sr1|($original_sr2<<8))&0x407c}]
        if {$original_bp != 0} { bna_execute_call [file join $capture_dir unprotect] onecall unprotect $original_bp $remove_fpb_command }
        bna_status_stage [file join $capture_dir status-unprotected] unprotected $original_sr1 $original_sr2 $remove_fpb_command
        if {$mode == "install"} {
            # Code exact whole4K verification must precede registry-sector erase.
            bna_write_sector $capture_dir install-code $bnai_code_patched_words $original_bp $remove_fpb_command
            bna_verify_sector $capture_dir code $bnai_code_patched_words
            bna_status_stage [file join $capture_dir status-code] unprotected $original_sr1 $original_sr2 $remove_fpb_command
            bna_write_sector $capture_dir install-table $bnai_table_patched_words $original_bp $remove_fpb_command
            set expected_code $bnai_code_patched_words; set expected_table $bnai_table_patched_words
            bna_verify_sector $capture_dir table $expected_table
        } else {
            # Original registry removes replacement entry before original code restore.
            bna_write_sector $capture_dir restore-table $bnai_table_original_words $original_bp $remove_fpb_command
            bna_verify_sector $capture_dir table $bnai_table_original_words
            bna_status_stage [file join $capture_dir status-table-restored] unprotected $original_sr1 $original_sr2 $remove_fpb_command
            bna_write_sector $capture_dir restore-code $bnai_code_original_words $original_bp $remove_fpb_command
            set expected_code $bnai_code_original_words; set expected_table $bnai_table_original_words
            bna_verify_sector $capture_dir code $expected_code
        }
        bna_status_stage [file join $capture_dir status-final-data] unprotected $original_sr1 $original_sr2 $remove_fpb_command
        if {$original_bp != 0} { bna_execute_call [file join $capture_dir reprotect] onecall reprotect $original_bp $remove_fpb_command }
        bna_status_stage [file join $capture_dir status-restored] original $original_sr1 $original_sr2 $remove_fpb_command
        foreach sector {code table} {
            foreach cache {i d} {
                set stage invalidate-$sector-$cache
                bna_execute_call [file join $capture_dir $stage] onecall $stage $original_bp $remove_fpb_command
            }
        }
        if {[bna_words 0x2892b000 1024] != $expected_code || [bna_words 0x28ccd000 1024] != $expected_table} { error "Whole sectors changed after cache invalidation" }
        bna_stable_halt; bna_a7_gate held-reset-cmu-verified
        if {[bna_word 0x40082008] != 0} { error "Stopped AON watchdog changed" }
        set bna_app_complete 1; set bna_safe_to_resume 1
        bna_app_log "app_data_protection_context_verified 1; leaveBOOT halted; outer owns finalGLOBAL"
    } operation_message]
    if {$operation_error} {
        set bna_safe_to_resume 0
        bna_app_log "operation_error $operation_message"
        bna_app_log "NO_AUTO_NEXT_STAGE_OR_RESUME; inspect physical sectors/status and closed native context"
    }
    bna_app_log "flash_mutation_possible $bna_flash_mutation_possible complete $bna_app_complete safe_to_resume $bna_safe_to_resume"
    close $bna_app_result
    if {$operation_error} { error "Fixed native app operation failed; retain halt/evidence for independent root recovery" }
    return 1
}
'''

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--patch-review", type=Path, required=True)
    p.add_argument("--code-original", type=Path, required=True)
    p.add_argument("--code-patched", type=Path, required=True)
    p.add_argument("--table-original", type=Path, required=True)
    p.add_argument("--table-patched", type=Path, required=True)
    args = p.parse_args()
    review_raw = args.patch_review.read_bytes()
    assert sha(review_raw) == FROZEN_PATCH_SHA, "Parent patch review drift"
    review = json.loads(review_raw)  # Preserve the exact parent review hash, not a mutable callback.
    assert review["firmware"]["sha256"] == FROZEN_NOR_SHA
    assert review["install_order"] == ["code", "entry"]
    assert review["restore_order"] == ["entry", "code"]
    assert int(review["sectors"]["code"]["offset"], 0) == 0x92b000
    assert int(review["sectors"]["entry"]["offset"], 0) == 0xccd000
    source = ROOT / "diagnostics/boot-nor-hook-runner.cfg"
    original_kernel = source.read_bytes()
    assert sha(original_kernel) == FROZEN_HOOK_SHA, "Frozen kernel drift"
    text = original_kernel.decode().replace("\r\n", "\n")
    kernel = text[:text.index("# ONLY public operation:")]
    kernel = kernel.replace("bnh_", "bna_").replace("bhi_", "bnai_")
    kernel = kernel.replace("boot-nor-hook-stage-inputs.cfg", "boot-nor-native-app-stage-inputs.cfg")
    kernel = kernel.replace("bna_hook_result", "bna_app_result").replace("bna_hook_complete", "bna_app_complete")
    kernel = kernel.replace("bna_run_hook", "bna_run_native_app").replace("reviewed hook sectors", "reviewed A7 app sectors")
    data = {label: getattr(args, label).read_bytes() for label in ["code_original", "code_patched", "table_original", "table_patched"]}
    assert all(len(x) == 4096 for x in data.values())
    for label, value in data.items():
        sector, state = label.split("_")
        manifest_sector = "entry" if sector == "table" else sector
        expected = review["sectors"][manifest_sector][state]
        assert expected["bytes"] == 4096 and sha(value) == expected["sha256"], "Sector bytes differ from frozen parent manifest"
    nor = (ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin").read_bytes()
    assert sha(nor) == FROZEN_NOR_SHA, "Immutable NOR drift"
    assert data["code_original"] == nor[0x92b000:0x92c000]
    assert data["table_original"] == nor[0xccd000:0xcce000]
    assert data["code_patched"][:0x2f8] == data["code_original"][:0x2f8]
    assert data["code_patched"][0x880:] == data["code_original"][0x880:]
    assert data["code_patched"] != data["code_original"]
    program = (ROOT / "analysis/display-takeover/native-counter.bin").read_bytes()
    assert len(program) == 966
    assert sha(program) == review["program"]["sha256"]
    assert review["program"]["bytes"] == 966 and review["program"]["entry"] == "0x3804b2f5"
    code = bytearray(data["code_original"])
    code[0x2f8:0x2f8+len(program)] = program
    assert bytes(code) == data["code_patched"], "Only exact linked counter may replace faclvgl bytes"
    table = bytearray(data["table_original"])
    assert struct.unpack_from("<I",table,0xcc8)[0] == 0x3818f9fd
    struct.pack_into("<I",table,0xcc8,0x3804b2f5)
    assert bytes(table) == data["table_patched"], "Only exact builtin vapp entry may differ"
    onecall = (ROOT / "analysis/persistence/boot-nor-one-call.bin").read_bytes()
    assert len(onecall) == 168
    inputs = "# Offline exact page/callee admission only, no target operations.\n"
    inputs += tcl_list("bnai_one_call_words",onecall)
    for label,value in data.items():
        inputs += tcl_list("bnai_"+label+"_words",value)
    inputs += STAGES
    input_path = ROOT / "diagnostics/boot-nor-native-app-stage-inputs.cfg"
    runner_path = ROOT / "diagnostics/boot-nor-native-app-runner.cfg"
    input_path.write_text(inputs,encoding="utf-8")
    runner_path.write_text(kernel+PUBLIC,encoding="utf-8")
    report = {
        "offline_only":True,"hardware_actions":0,"frozen":False,
        "runner":str(runner_path.relative_to(ROOT)),"runner_sha256":sha(runner_path.read_bytes()),
        "inputs":str(input_path.relative_to(ROOT)),"inputs_sha256":sha(input_path.read_bytes()),
        "kernel_source":str(source.relative_to(ROOT)),"kernel_source_sha256":FROZEN_HOOK_SHA,
        "kernel_changes":"Namespace, source filename and comments only; unchanged168B caller/closed-return/context/watchdog gates.",
        "patch_review":str(args.patch_review),"patch_review_sha256":sha(review_raw),
        "sector_sha256":{k:sha(v) for k,v in data.items()},
        "sector_files":{k:str(getattr(args,k)) for k in data},
        "public_operation":"bna_run_native_app capture_dir install|restore remove_fpb_command",
        "scope":{"code":"92b000/4096","table":"ccd000/4096","code_mutation_allowed":"Onlyfaclvglfunction92b2f8..92b880","table_mutation":"Onlyvappentrywordccdcc8:3818f9fd->3804b2f5","install_order":"codeerase/pages/whole4Kverify/status beforetableerase/pages/whole4Kverify","restore_order":"tableoriginalerase/pages/whole4Kverify/status beforecodeoriginalerase/pages/whole4Kverify"},
        "preconditions":["same-process independentBOOT readerpass","A7/WF/BTCPUheldreset","AONWDTCTRL0 atoperation/entry/prerun/final gates","exact4Kbaselines","exactfreshBOOTcode+globals+liveSPIid0table"],
        "failure_policy":"No auto retry/nextstage/reprotect/globalreset. Unclosed native execution suppresses stale core/SRAM/controller replay; retain debug halt for root recovery.",
        "partial_table_recovery":"Supervised only after freshindependentBOOT/reader/controller validation: statusbefore/unprotect/statusunprotected; bna_write_sector restore-table with exactbnai_table_original_words; whole4Kverify; status/reprotect/statusrestored; fixedtableI/Dcacheinvalidate. Public restore still refuses unknownbaselines. Noautomaticfailurewrites.",
        "status":"NativeSR1/SR2 freshphasechecks,WIP/WEL0,mask407c only,BP0skipstatuswrites,QEallotherstablebitsexactrestore",
        "cache_limit":"OnlyprovenBOOTMCUI/DcacheinvalidateonreviewedtwoNORsectors; A7 heldreset andouterGLOBALcoldstart discardA7cache.",
        "pending":"IndependentJim mocks and child review beforefreeze; nohardware execution."
    }
    path = ROOT / "analysis/persistence/boot-nor-native-app-runner-review.json"
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"runner_sha256":report["runner_sha256"],"inputs_sha256":report["inputs_sha256"],"patch_review_sha256":report["patch_review_sha256"]}))

if __name__ == "__main__":
    main()
