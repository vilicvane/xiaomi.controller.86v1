# Offline recovery-mode MCUCPU / BOOT probe

New configuration: `diagnostics/mcu-recovery-mcucpu-bootbreak-probe.cfg`.
Preparation: `analysis/persistence/prepare_recovery_mcucpu_probe.py`.
Validation: `analysis/persistence/test_recovery_mcucpu_offline.py` and
`analysis/persistence/offline-recovery-mcucpu/summary.json`.
No hardware execution or MAIN corruption experiment was performed.

## Result and scope

The new entry does not read MAIN instructions, MAIN SRAM controller table
`20003948`, opened context `2000417c`, or suspend state `200041f4`. It validates
preserved original BOOT source windows, including the header, startup copy,
primary-idle HAL source, NOR init source, controller table `0c005378`, breakpoint
`0c0104c6`, DSP reset-set closure and GLOBAL reset sequence. It derives primary
`40148000` from that checked BOOT table. Secondary `40140000` is a checked literal
only and is never accessed as a peripheral.

The existing measured pilot reset flow is retained: stop the current MCU;
bounded primary idle / readlock / controller-reset gate; five exact BOOT DSP
isolation stores; one AON MCUCPU pulse `400800a0=40`; joint reset epoch, halt and
VCATCH proof; fresh post-reset FPB; Secure Thread BOOT halt; opened BOOT context
and fresh BOOT controller table. There are no APDBG reads anywhere in this
variant. MCUCPU pulse provenance is the successful root-owned original pilot,
not an invented BOOT generic-pulse opcode match.

Once any isolation store or MCUCPU pulse may have committed, cleanup discards
the old MCU/A7 execution context and requests one GLOBAL reset
`400800a4=200`. It never replays pre-reset core state. A posted write transport
error is not retried. A GLOBAL dispatch result is not proof of a recovered
ordinary MAIN boot: root must verify a fresh connection/full-power recovery.
Before any reset mutation, a failed primary gate rolls back only temporary
debug halt/reset catch and resumes the original context.

## Offline validation

All 12 cases passed using the real Jim Tcl parser with `source`, `find`, `init`,
`adapter`, `read_memory`, `write_memory`, clock and sleep substituted before
configuration evaluation. Native adapter initialization is never invoked.

- Healthy start, explicitly invalid MAIN code/runtime, and transient SPI busy
  settling reach fresh BOOT and request one final GLOBAL cleanup.
- Invalid BOOT signature, persistent SPI busy, readlock and controller-reset
  states perform no A7 isolation, MCUCPU pulse or GLOBAL reset.
- Uncertain isolation commit, uncertain MCUCPU commit, lost debug after pulse,
  missing BOOT breakpoint and a second reset exercise conservative GLOBAL
  cleanup and suppression of old-context resume.
- Every case enforces zero MAIN reads, secondary-controller reads, APDBG reads,
  debugger NOR/RAM data writes and AIRCR writes. The model requires FPB arming
  only after its fresh reset catch.

## Limits

This variant supports a narrower class of broken-MAIN states: generic MEM-AP
and Secure invasive debug remain usable; the MCU can reach a controlled halt;
preserved BOOT signature windows are readable; the physical primary SPI clock
domain responds and its controller busy/readlock/reset flags are clear. It
removes MAIN runtime prerequisites without promising universal recovery.

Controller idle is not an independent proof of chip internal WIP/suspend.
Read-only BOOT signatures cover selected windows, not every BOOT instruction.
Bad BOOT, unavailable DAP, a blocked peripheral clock domain, persistent reset,
incompatible security/debug ownership or unresolved chip operations can still
block recovery. Original BOOT initialization can itself change NOR BP/QE status;
the debugger does not call a NOR API or program/erase Flash in this probe.

The new recovery entry has offline proof only. The earlier root pilot measured
MCUCPU reset/catch and final clean reconnect from a valid MAIN state; no target
MAIN bytes were deliberately corrupted to test this entry.
