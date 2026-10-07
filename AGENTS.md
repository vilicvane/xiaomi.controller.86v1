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
- Current installed UI is maintained-http-four-page-20261007-d, specific to this exact 1.50.10 image.
  Candidate SHA aba4a3e5021af175a3d6cd9dc90eac4559154d34711b647bbc8a48043ce5d9fe;
  380-input freeze SHA 3af60edcb71636fbe227237f7c7f8b23d4135571b2e45651583665d4466a2632.
  Main/aux/net BIN sizes are 2946/236/2948 B, ending at 0x3804bc8a/0x3807a850/0x3804db84.
  Main/aux are exact previous-c bytes; context/containers/ownership and four-page ordering unchanged.
  Content-Type is ignored; fixed Content-Length, VIMG and FNV remain required.
  GET root returns 303 to the temporary computer LAN development page on 5173 with device fragment.
  Actual URL is private in the frozen config; keep local addresses outside Git. Development server must
  remain available on that address/port. CORS stays wildcard for LAN and loopback development origins.
  Fresh 24 UI + 23 configured HTTP actual ARM groups, 93 writer mocks, 261 host HTTP checks and 12 release tests passed.
  The old c frozen restore first returned exact image drawer three pages plus stock net, with four-page/native
  closure and warm readback. Then d installed using its own frozen executor; complete four-page/native
  closure, GLOBAL and fresh warm readback passed. Do not install a new release directly over d.
  Windows Chrome followed actual 303, populated endpoint and uploaded default GitHub VIMG without Content-Type:
  HTTP 202, 307216B, FNV/button success; actual curl without -H returned 202. Bad FNV 422 and bad magic 400 passed.
  Fresh runtime generation/displayed_generation=2, pending0, server1 and active GUI; no LCD scanout claim.
  Public semantic result is firmware/releases/maintained-http-20261007-d.json.
  Current d user confirmed default GitHub image display and external phone-to-development-server redirect.
  Gesture/doubletap/sleep-wake/MiHome observations remain pending; old c observations are historical,
  even with identical UI BINs.
  Cloud HTTPS browser-to-LAN remains unverified. Cold power-cycle is explicitly user-skipped, do not ask again.
  Use d's frozen snapshot/firmware/tools/hardware.ts and adjacent verifier. Restore d to exact image drawer
  plus stock net before any historical writer. d's own hardware restore is not tested; c's successful restore
  is separately recorded in d upgrade evidence. NEEDS_INSPECTION still means preserve the stopped state.
- Previous maintained UI was maintained-http-four-page-20261007-c, specific to this exact 1.50.10 image.
  Candidate SHA e76bac29f5b74fdadf126996e1ad4c959daeb6309c5020276eeb33745500e17f;
  380-input freeze SHA 48fefb3bdc5d269b8e32f1d5e976935d6aa24397a181b2d14a2cd7dddc59ef14.
  Main/aux/net BIN sizes are 2946/236/3004 B, ending at 0x3804bc8a/0x3807a850/0x3804dbbc.
  Main and aux containers stay unchanged. Extra reviewed network container is
  0x3804d000..0x3804dff0 inside uorb_unit_test; preserve first 4 B/last 12 B of NOR page 0x92d000.
  Its builtin entry word at entry page +0xc3c is disabled from 0x3804cf3d to 0x3804b109.
  Four full pages, native/cache/context closure, final GLOBAL and fresh warm runtime passed.
  24 actual ARM UI groups, 21 default HTTP groups, 21 configured HTTP groups,
  93 current writer mocks and 12 release tests passed; these are not hardware UI acceptance.
  Public semantic result is firmware/releases/maintained-http-20261007.json.
  GET/200 instructions, OPTIONS/204 CORS, wrong body POST/400, full image POST/202
  and invalid FNV POST/422 passed. Rejection preserved generation/displayed_generation=1,
  pending=0/server=1; server_error=422 means last rejected HTTP status, not worker failure.
  User doubletap and stock sleep-wake observations passed on 2026-10-07.
  User image/swipe/key3-removal/MiHome observations remain pending; do not infer them from that report.
  HTTP 18086 has no legacy raw TCP/VACK compatibility. Frontend URL is blank; configured 303
  was tested only in a separate ARM model. Local HTTP frontend-to-LAN upload passed in Windows Chrome;
  see web/browser-verification-20261007.json. Cloud HTTPS-browser-to-LAN remains unverified.
  Context remains 212 B: doubletap state +128, screen_off +144, show_address +204;
  image/receive +176/+180, pending +184, generation +188/+192, server +196/+200, IPv4 +208.
  Do not interpret these with historical key3/reserved or tap-fast feedback semantics.
  Images remain RAM-only; program is persistent. Off observation requests custom owner
  without touching backlight; complete off/on between GUI polls can be missed. First wake
  contact is excluded from doubletap until UP, but swipes remain allowed.
  Use this release's frozen snapshot/firmware/tools/hardware.ts and adjacent verifier.
  Install net→aux→code→entry; restore entry→code→aux→net, all A7/WF/BT held reset until closed.
  Restore exact image drawer three pages plus stock network page BEFORE using historical writers.
  This release's hardware restore later passed during the d upgrade; its original result remains unchanged.
  NEEDS_INSPECTION means preserve stopped state;
  never automatically retry, clear its marker, or replay a native call. Offline freeze/mock is not hardware permission.
  Cold power-cycle remains explicitly user-skipped; do not ask again or borrow historical results.
  Canonical firmware/ source may evolve, but snapshots and all historical inputs remain immutable.
- Historical native image drawer was installed before the maintained release (3416-byte main + 424-byte aux BIN, 1.50.10).
  Its 93-input freeze is fa99d95a98b3abd4f3e76ce304a4d6a12623f50338d0240a6aba4b91f0a0cf61.
  33 ARM groups, 12 independent focused ARM groups and 70 writer mocks passed.
  Main ends at 0x3804be60, aux at 0x3807a90c; existing containers and adjacent helpers preserved.
  Exact fast-tap triple was the installation baseline; three full pages and warm
  MCU/GUI/server state passed. Context is 212B, image/receive +176/+180,
  image_pending +184, generation/displayed_generation +188/+192, server_state/error
  +196/+200, unused reserved +204, IPv4 network bytes +208. These are NOT fast-tap feedback slots.
  TCP18086 receives fixed480x320 RGB565 images with FNV/VACK; images are RAM-only,
  program is persistent. Two complete uploads, address/both image display, swipe/key3
  roundtrips and Mi Home online/control passed; user observations are separately
  recorded in native-image-drawer-hardware-result.json. Fresh runtime after roundtrips
  showed generation/displayed_generation2, pending0, server1/error0 and active GUI.
  Do not promise every rejection ACK: initial invalid header and client half-close
  lacked complete ACK; idle took10.038 wall seconds. Native RPCs are not strictly bounded.
  For this historical image triple, restore ONLY with Set-PanelNativeImageDrawer.ps1 to exact fast-tap first; never
  apply a historical writer directly against the image triple. Cold power-cycle
  remains explicitly user-skipped; do not ask again or borrow old cloud results.
  Native fonts are only static feasibility; never reinitialize shared GUI FreeType/cache.
- Historical UI before native image drawer was native GitHub tap-fast (3336-byte main + 431-byte aux BIN, 1.50.10).
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
