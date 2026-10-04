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
- Current installed UI is the native drawer ease (3264-byte BIN, 1.50.10).
  Full-page Flash/readback and live custom-owner/GUI state passed. User gesture
  and full power-cycle observations are recorded separately in
  native-drawer-ease-hardware-result.json; do not infer them from earlier results.
  First drawer (3224B) user gesture round trips passed; its cold boot is separate.
  Broker v1 (2652B) cold boot, round trips and Mi Home controls passed earlier.
  Both older frozen sets remain immutable.
- Ease restore uses Set-PanelNativeDrawerEase.ps1 and returns first drawer;
  Set-PanelNativeDrawer.ps1 then returns broker v1. Only then use
  Set-PanelNativeUiBroker.ps1 to restore stock. Do not use another
  version's writer against the installed baseline or regenerate frozen inputs.
- Drawer additionally borrows wifi_recorder worker 0x3804bc98..0x3804be70;
  its diagnostic builtin NOR 0xccdd2c is disabled. Keep shared helper at be70
  intact. This is not the Wi-Fi driver or a startup service.
- ABI offsets must be written unambiguously: LVGL state/continue are +0x12/+0x13,
  list node prev/next are +0x80/+0x84. Validate both physical and virtual touch.
