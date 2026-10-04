# Working on this panel

- Read `docs/engineering-notes.md` and `docs/development.md` before hardware work.
- Treat addresses, ABI and frozen inputs as specific to this panel's 1.50.10 image.
  Check the saved hashes and current state; do not apply a historical experiment
  to another firmware or an unknown partial-write baseline.
- Keep hardware operations sequential and owned by one agent. Offline analysis
  can be delegated; concurrent OpenOCD or native calls cannot.
- Preserve backups, raw captures, credentials and vendor toolchains outside Git.
  `.gitignore` admits reviewed evidence explicitly. Check staged content before
  committing; do not force-add device dumps or generated firmware-word arrays.
- Frozen install/restore inputs must keep their exact bytes. Do not reformat them,
  rerun generators casually, or treat offline mocks as hardware verification.
- The live NOR logical controller 0 is `0x40148000`, after verifying the live
  pointer table. Do not access the unused `0x40140000` controller: it has caused
  a bus lock requiring complete power removal.
- After any uncertain native call, preserve the stopped state and evidence.
  Do not blindly retry, resume, reset, or replay old CPU/SRAM context.
- Current installed UI is the white native counter. The current goal is physical
  key 3 triple-click switching without reboot; no switching implementation has
  been validated at this checkpoint. Preserve that distinction in reporting.
