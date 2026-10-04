# Offline original BOOT NOR init closure review

Source: `backups/mi-panel-flash-16m-1.50.10-20261004.bin`, SHA256 `777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b`. No hardware or device-memory access.

## Result

- Native `20001380` is not a fully SRAM-contained initializer: its call at `20001386` reaches SRAM veneer `200032f8`, which loads PC from `200032fc` = Thumb `0c000d61` in Flash, with frequency argument 104 MHz.
- Direct `20001038` open wrapper forces reset=0 / init=1; after resolving active-chip indirect call `20002380` to `002024f5` (cfg offset +18), its 82-function normal closure is SRAM code, with no unresolved code calls and a conservative maximum stack of 272 B. Internal `20000bc0` requires 256 B. These bounds exclude assert/stack-failure Flash paths, interrupts/faults and external native clock code.
- Stock open is not read-only: for chip `85 65 18`, 16 MiB, `20000b2c` returns BP composite `007c`; `2000236c` passes type3 to `200024f4`, causing `06` WREN followed by `01` and `31` status writes. This is the nonvolatile status route, unlike the existing type4 / `50` probe. QE type1 in selected callback uses volatile `50`, not `06`.

## Initialization requirements

Restore BOOT source file `[2220,5b58)` to `[200001a8,20003ae0)` (14648 B), including all code/tables, guard `20003a58=deadbeef`, timer calibration `20003adc=24000000`, default cfg `20003400={208000000,104000000,7503f,7}`. Clear BSS `[20003ae0,20003c20)` (320 B). This contains ctx, chip index, mode, divider, lock and timing metadata referenced by the normal closure; do not substitute main-owned SRAM contents.

Controller table `20003300` raw bytes `0080144000001440` means logical id0=`40148000`, id1=`40140000`. Active JEDEC selects index15 / slot `200036d0` / cfg `2000382c` / callback `002024f5`; these depend on real native ID detection during open and must be verified afterward.

Native controller stop `20000946` calls `20002d64` and polls decreasing counter `40002004`. Release-power-down `20001744` calls `20002d78` and polls `40003004` using calibration `20003adc`. Both counters and the controller/CMU clock domain must be independently initialized and verified; unclocked counters or a busy controller can trap these loops without a software timeout.

Default flags7 enable calibration: mode1 reads `28000000` first word and compares magic `be57ec1c`; mode2 reads 48 B at `28019a64` and compares SRAM reference `2000372c`. Both are preserved BOOT data, not modified main sectors. The `0c65d3ff` literal at `20000b84` is frequency threshold 208 MHz minus1, a conservative Flash-address-range false positive, not a code/data dereference.

## Feasible selective path and blockers

A direct open can avoid the native Flash clock veneer after independent CMU/controller/timer setup, but its stock BP status mutation remains. A loader requiring fully independent SRAM code and no nonvolatile status writes must implement/bypass that clock setup and type3 BP initialization, then separately verify JEDEC, selected cfg, mode, divider, geometry and mapped/uncached reads. This review does not prove such a modified initializer safe and does not produce or execute it.

Debugger halt-at-BOOT is not required by this static closure itself; correct original SRAM restoration, controller ownership, IRQ/security/stack setup, timer initialization and preserved BOOT calibration data are runtime prerequisites. The parent independently owns the external clock/system/timer initializer audit.
