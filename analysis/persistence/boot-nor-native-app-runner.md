# Fixed native counter writer

Checkpoint update, 2026-10-04: this document originally described offline
preparation. Fixed-sector installation and rollback have since passed on the
panel; `native-counter-hardware-result.json` records the exact scope. Pink passed
a full power cycle; current white passed warm boot and whole-sector readback.
Current white patch-manifest SHA is
`55fbb71be4fe4abd40a245f72f303073cc5afce0288a5aa238bf35ea475af4ed`.

No device connection, `init`, reset, resume or automatic operation occurs when
the library is sourced. Root owns hardware and the independent recovery session.
Public entry is `bna_run_native_app capture_dir install|restore remove_fpb_command`.
Outer GLOBAL is admitted only when **both** `bna_app_complete` and
`bna_safe_to_resume` are 1. An intermediate native call may set safe=1 while the
whole operation remains incomplete, so safe alone is insufficient.

Only NOR sectors `92b000` and `ccd000`, each 4096 bytes, are admitted. The original
sectors must equal the exact saved original 1.50.10 16MiB NOR image. Code changes
only the 966-byte linked program at `92b2f8` within the exclusive faclvgl function;
the table changes only `ccdcc8` from Thumb3818f9fd to Thumb3804b2f5. Factory
faclvgl GUI behavior is replaced as well. Remaining sector bytes and all data
partitions are preserved. Binary length and A7 load length/BSS are unchanged.

Install checks both full original sectors before status writes. It unprotects
only original BP mask407c if nonzero, verifies SR1/SR2, erases/writes all non-FF
code pages, verifies all4096 code bytes and status, then erases/writes table and
verifies all4096 bytes. Restore admits only exact original/patched per-sector
baselines, restores and verifies the table first, then the code. Both modes
restore BP/QE/all stable SR bits, run the proven BOOT MCU I/D cache invalidation
for each fixed sector, and recheck both sectors. A7 is held reset throughout;
the outer GLOBAL cold-start discards its cached state.

The native call kernel is copied from the hardware-validated frozen
boot-nor-hook-runner c37ef00010de3bc59155da30e88ebd8f395797f1df684667305e7ea50490e11a.
Only namespaces, input-source filename and descriptive comments/log-channel
names change. All gates retain original BOOT SRAM equality with six independently
proved initialized-word exclusions, runtime equality for those words, full BSS
snapshot, live logical SPI id0=40148000, active callback, suspended state, source
page, held A7/WF/BT reset, secure debug halt, exact caller and payload dual-alias
readback, unchanged stack/limits and saved 1024 bytes, WDT CTRL0 at entry and
immediately before execution, exact BKPT/native return, closed hardware post,
status, faults and full core/SRAM restoration. Budgets are 5000ms erase,
1000ms program/protection/cache and250ms read. A timeout/fault/reset/posted
transport failure never admits another stage or stale context replay.

## Supervised partial table recovery

This is an explicit root-only recovery route, not a third public operation or an
automatic failure action. If a table erase/program was partly committed, public
restore must refuse the unknown baseline. Root first establishes a **fresh**
independent original BOOT breakpoint, held-reset CMU evidence, watchdog stop,
successful bnor reader and native-closed/controller state. Root retains the
original pre-install protection/status values from the saved evidence. It then
opens a new bna_app_result log and explicitly performs the following fixed stages:

1. `bna_execute_call ... read read-status 0 ...`; inspect current WIP/WEL0 and
   compare all stable status bits to the appropriate known original/unprotected
   state using `bnai_verify_status`.
2. If current BP nonzero, `onecall unprotect original_bp`; fresh status must prove
   the exact unprotected stable state.
3. `bna_write_sector ... restore-table $bnai_table_original_words original_bp ...`.
   This helper refuses any other prefix/data before erase. Its stage calculation
   fixes erase at28ccd000 and each original 256-byte table page. Verify all4096
   original table bytes with `bna_verify_sector ... table ...`.
4. Explicit fresh status, restore the original BP if required, fresh exact original
   status, then only `invalidate-table-i` and `invalidate-table-d`; reread4096 bytes.
5. Root reviews all calls, context restoration and complete protection evidence.
   This helper does not mark whole-app complete or automatically authorize GLOBAL.

No arbitrary native callee, address, source data or erase length is accepted.
Unknown code baseline is preserved by this table-only recovery, so the original
normal vapp startup can be selected before a separately reviewed full code restore.
Do not restore an old SR counter, lock word or core context after an unclosed run.

## Evidence status

The initial pink build preserved patch-manifest SHA
7a0c2469773a34415e9bdf70dc8faf637f16ed79737a82f090210a4ab1e73d08;
it is historical evidence, not the current white manifest listed above.
The review JSON records exact whole-sector and source hashes. Pure Jim mocks
simulate register transfers, native callee arguments and independent raw sectors;
they do not emulate ARM instructions and cannot demonstrate hardware cold boot.
Hardware operations remain root-owned and sequential; their completed results
are recorded separately from the mock evidence.
