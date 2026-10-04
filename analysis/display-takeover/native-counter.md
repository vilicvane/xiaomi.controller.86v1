# Device-native persistent counter, exact firmware 1.50.10

This prototype is compiled ARM code executed as a normal A7 NuttX task. It owns
its pixel buffer, submits frames through the firmware framebuffer driver and
reads the physical touch device itself. No PC drawing or input loop is involved.
Each released-to-pressed transition increments the counter once. A reboot starts
at `vilicvane +0`.

The normal boot command remains `vapp app/com.xiaomi.smartpanel`, but its builtin
entry pointer is redirected to this program. Original vapp code remains available
as a setup-failure fallback. The factory `faclvgl` demo function's 1416-byte code
container holds this 966-byte prototype; factory demo behavior is also replaced.
The A7 image copy length, initialized data and BSS boundaries remain unchanged.

The two changed NOR sectors are 0x92b000 and 0xccd000. Exact original/patched
4096-byte images and hashes are in `native-counter-patch-inputs-1.50.10.json`.
Only 966 code bytes at file 0x92b2f8 and the four-byte builtin entry at 0xccdcc8
are changed. Actual erase/program operations preserve every other sector byte.

## Run or restore

From the workspace PowerShell terminal, with panel and nanoDAP connected:

```powershell
.\scripts\Set-PanelNativeCounter.ps1 -Mode install
.\scripts\Set-PanelNativeCounter.ps1 -Mode restore
```

Installation replaces the normal panel UI. The program continues across power
cycles without the debugger. Restore reinstalls both exact original sectors and
restarts the normal firmware. This fixed installer checks frozen inputs and known
whole-sector baselines; do not use it against another firmware version or an
unexamined partial-write state.

## What this establishes for custom firmware

- A persistent, compiler-built native entry in the normal boot path.
- Autonomous display submission with OS scheduling and vblank alive.
- Autonomous physical touch input with correct press/release behavior.
- A measured installation and rollback path preserving original device data.

It currently reuses the original NuttX OS, board initialization, framebuffer and
touch drivers, plus the MCU-side services. It is not a complete independently
built replacement firmware. Future work can use these verified driver semantics
to port display/input into a reproducible firmware build and allocate a proper
application image instead of this small factory-demo container.

Adding a lock screen or another page to the original Xiaomi application is a
separate route. Its startup command is known, but an extension API and application
page format have not been established. The prototype does not validate such an
API; it validates replacing that UI with our own code.

## Evidence

To rebuild the prototype with the workspace-local linker and existing WSL LLVM18:

```powershell
wsl.exe -d Ubuntu -- bash /mnt/c/Users/vilicvane/Projects/vilicvane/mi-panel/analysis/display-takeover/build-native-counter.sh
python analysis/display-takeover/prepare_native_counter_sectors.py
```

Rebuilding is offline and does not write the panel. A changed program requires a
new reviewed installer input set; the frozen installer refuses changed artifacts.

`native-counter-independent-review-1.50.10.json` records the first pink version's
entry, ABI, bounds and original loader audit. Its authenticated original artifacts
are preserved under `../persistence/native-counter-pink-reviewed/`.
`native-counter-white-independent-review-1.50.10.json` audits the current white
version: exactly one four-byte color instruction changed, with identical entry,
layout, input logic and every other binary byte. The original linker-alignment error was
caught before device writes; the four-byte Thumb wrapper now fixes the binary
origin at 0x3804b2f4 while preserving the main function's eight-byte alignment.

`../persistence/boot-nor-native-app-runner-review.json` and
`../persistence/offline-native-app-runner/run-4/summary.json` record 28 independent
offline writer checks. Real install/readback evidence is saved separately under
`../persistence/native-counter-install-session-*`. Screen, touch and full-power
boot results require physical observation; offline tests alone do not prove them.
