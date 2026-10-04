"""Record final offline runner proof; do not rewrite any executable cfg."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "diagnostics/boot-nor-padding-runner.cfg"
REVIEW = ROOT / "analysis/persistence/boot-nor-padding-runner-review.json"
SUMMARY = ROOT / "analysis/persistence/offline-padding-runner/summary.json"
cases = json.loads(SUMMARY.read_text())["cases"]
expected_cases = {"success_bp0", "success_bp", "sector_not_ff", "reset_program", "fault_program", "programmed_mismatch",
                  "active_watchdog", "watchdog_reenabled", "initialized_config_changed", "erase_delayed", "erase_timeout"}
assert {case["case"] for case in cases} == expected_cases and all(case["passed"] for case in cases)
review = json.loads(REVIEW.read_text())
review.update({
    "sha256": hashlib.sha256(CFG.read_bytes()).hexdigest(),
    "status":f"Offline executable definitions-only library and {len(cases)} focused simulated flows validated; padding has not been executed on hardware; root hardware review/measurement still required",
    "validated_reader_hardware_evidence":"analysis/persistence/native-read-20261004-150456/result.txt",
    "offline_cases":cases,"offline_summary":str(SUMMARY.relative_to(ROOT)),
    "caller_template":{
        "onecall_file":"analysis/persistence/boot-nor-one-call.bin","bytes":168,
        "sha256":hashlib.sha256((ROOT / "analysis/persistence/boot-nor-one-call.bin").read_bytes()).hexdigest(),
        "patched_region":"Only five IO input words at128..144; exact machinecode unchanged; page payload resides+256..512",
        "read_file":"analysis/persistence/boot-nor-read-probe.bin","bytes":172,
        "sha256_read":hashlib.sha256((ROOT / "analysis/persistence/boot-nor-read-probe.bin").read_bytes()).hexdigest(),
        "native_stage_allowlist":["unprotect","program","erase_restore","reprotect","invalidate_i","invalidate_d"],
        "read_stage":"Fixed original reviewed JEDEC/pre/05/35/post caller only",
        "separability":"bnp_execute_call owns generic save/run/guard/post/restore mechanics but accepts only padding bnt_stage_inputs. A future hook needs a separately reviewed narrowly admitted mode; no current addresses broadened."},
    "context_contract":{
        "entry":"Fresh Secure privileged Thread BOOT0c0104c6 and stack200d3e00<SP<=200d5e00; same-process independentreader successful",
        "registers":"CaptureR0..R18,currentpacked20,SecureMSP26/PSP27/MSPLIM28/PSPLIM29/packed34,DCRDR,DFSR,DEMCR,DSCSR,CFSR,HFSR. KeepSP/limitsunchanged. RestoreclobberedR0..12,LR,xPSR,PC,packed20; reread all capturedselectors.",
        "memory":"Capture/write/readback/restore exact[originalSP-1024,originalSP) through200.../002...aliases, including up to232B HAL stack spills. Capturefull14,968B HAL/context before eachcall.",
        "SPI":"First validate actualBOOTRAMtable20003300 then useid0=40148000 dynamically. Gatebusy/lock; verifypost stablecommand~01fff000/divider00ff0000/lockreset300; neverTX/RXFIFO+08/+10; savedsoftwarelockonlyafterverifiedpost.",
        "BSS":"Comparefull320B context, allowonlysoftware saved-lockword20003b80 temporarily; restoreitafterpost andrequirewholecontext exactoriginal. Verifyguard/bootmodecache/timercalibration separately. Source comparison permits only proved initialized PMU/sysfreq words20003ad0/4, with independent8B before/after captures and exact two-word invariance everycall.",
        "watchdog":"Read AONWDTCTRL40082008 and require0 before context transfers and immediately before each nativeCPUrun. Root owns independently hardware-proved BOOTstop and finalGLOBAL; library performs no WDTwrites. A late active gate restores borrowed core/RAM without running a caller.",
        "timing":"Read/cache250ms; program/BP1000ms; erase5000ms. Nonhalt samples sleep5ms; count limittimeout/5+2 supplements wallclock bound. Exact BKPT/native return/SPI closure remains mandatory; timeout suppresses stale restore and later stages.",
        "unsafe":"Unexpectedreset,exception/security/faultchange,wrongBKPT/guards/return/mask,timeoutorunclosedSPI suppresses RAM/core replay and leaveshaltforouterindependent recovery.",
        "halt":"Every successfulcall returns to originalBOOTcontextbutkeepsdebughalt; entirepaddingtest has no init/reset/shutdown/mainresume."},
    "transaction_contract":{
        "sector":"Requirelivewhole4K28825000 exactlymatchesoriginalsource4096FF and persistcapturebefore mutation; neveracceptonlymarkerreadback.",
        "program":"Only256B NORTEST1+FF at28825100, compareentire4Kphaseexpected andfreshstatus.",
        "restore":"Eraseonly28825000 length1000, compareentire4KbothsourceFFandactualoriginalcapture; exactoriginalprotection/QEstatus restored then128-lineI/D invalidations2c825000/1000.",
        "protection":"originalBP=(SR1|SR2<<8)&407c. If0: no BPcaller atanyphase. Ifnonzero: set0 thenrestoreexactmask; comparestablecompositefffc andrequireWIP/WEL0throughout. NeverreplaywholeSRbyte.",
        "failure":"Marknative_flash_mutation_possiblebeforeCPUrun. Any stageerror causes bnp_safe_to_resume0 and no latererase/reprotect/caller stage; physicalsector/protection may remainchanged. Preservecaptures; outer root owns independentBOOT recovery orGLOBAL/powercycle."},
    "limitations":[
        "Mocks validate host admission/closure/restore/error ordering; real nativeHAL status/protection/timing behavior is not yet proved by this artifact.",
        "Original BOOT watchdog must remain stopped; the library rejects active CTRL but does not itself stop/feed/restart it. Root owns finalGLOBAL recovery. Poll budgets are conservative host limits, not proven flash datasheet maxima.",
        "Controller busy0/lockclear is not independent chipWIP proof; fresh05/35 readcaller provides status samples.",
        "No whole16MiB difference audit is implied by exact one-sector comparison.",
        "No hook installation/mainentry/factory/BOOT/recovery writes have been implemented or performed."
    ]
})
review["dependency_sha256"]={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in review["dependencies"]}
REVIEW.write_text(json.dumps(review,indent=2)+"\n")
print(f"Saved final padding runner SHA {review['sha256']}; {len(cases)} focused mocks passed; no target access")
