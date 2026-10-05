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
- Current installed UI is native GitHub tap-fast (3336-byte main + 431-byte aux BIN, 1.50.10).
  Full-page Flash/readback and warm custom-owner/phase150 state passed;
  user tap/gesture acceptance is pending and recorded separately in
  native-github-tap-fast-hardware-result.json. Mi Home controls are unchecked
  for this variant; do not borrow earlier online/control results. Complete
  power-cycle testing was skipped at the user's explicit request; do not claim it passed or ask again.
  Tap-fast main ends at 0x3804be10 and aux at 0x3807a913, preserving
  the exact tap-v1 tail bytes and adjacent helpers.
  Aux is restricted to former factory socket worker 0x3807a764..0x3807a920;
  adjacent backlight callback and JSON helper must stay intact. The whole live
  auxiliary NOR page 0x95a000 originally matched stock before tap-v1 installation.
  Its old factory startup reference was already disabled by the card entry/code.
  Tap-fast uses three full-page verification and a separate 68-input frozen writer;
  never use an older two-page writer directly against this installed triple.
  Card (3432B) layout/gestures passed, cold boot user-skipped; its inputs are immutable.
  Smooth (3368B) user motion passed; its full power-cycle was also user-skipped.
  Prior ease (3264B) user gestures, cold boot and Mi Home controls passed;
  those results do not establish the new variant's acceptance.
  First drawer (3224B) user gesture round trips passed; its cold boot is separate.
  Broker v1 (2652B) cold boot, round trips and Mi Home controls passed earlier.
  All older frozen sets remain immutable.
- Native GitHub tap-fast is separately frozen: main 3336B ends at 0x3804be10,
  aux 431B ends at 0x3807a913; both stay within the existing containers.
  Its 53 ARM groups and 68 installer mocks passed; 68 inputs are frozen.
  Context stays 184B: feedback_pending/+180 is 0=accepted/clock anchored,
  1=new count awaiting PAN, 2=accepted PAN awaiting fresh CLOCK. Feedback-only
  drawing updates rows249..269; native PAN still rotates/submits the full frame.
  The 8-sample native touch ring is unchanged and overflow has not been proven
  to cause the user's intermittent issue. Preserve all older frozen inputs.
- GitHub tap-fast restore uses
  Set-PanelNativeGitHubTapFast.ps1 and returns exact tap v1 three pages.
  Only then may Set-PanelNativeGitHubTap.ps1 restore card and its stock aux page.
- GitHub tap restore uses Set-PanelNativeGitHubTap.ps1 and returns exact card
  plus the stock auxiliary page. Only then use the two-page card writer.
  GitHub card restore uses Set-PanelNativeGitHubCard.ps1 and returns exact smooth.
  Smooth restore uses Set-PanelNativeDrawerSmooth.ps1 and returns exact ease.
  Ease restore uses Set-PanelNativeDrawerEase.ps1 and returns first drawer;
  Set-PanelNativeDrawer.ps1 then returns broker v1. Only then use
  Set-PanelNativeUiBroker.ps1 to restore stock. Do not use another
  version's writer against the installed baseline or regenerate frozen inputs.
- Drawer additionally borrows wifi_recorder worker 0x3804bc98..0x3804be70;
  its diagnostic builtin NOR 0xccdd2c is disabled. Keep shared helper at be70
  intact. This is not the Wi-Fi driver or a startup service.
- ABI offsets must be written unambiguously: LVGL state/continue are +0x12/+0x13,
  list node prev/next are +0x80/+0x84. Validate both physical and virtual touch.
