# Device-side image drawer, 1.50.10

This is a separately reviewed persistent program for this panel's exact 1.50.10
image. It replaces the GitHub tap demo with a TCP image receiver and preserves
the original drawer gestures, third-key triple click, and GUI input/display
ownership transaction. The original application continues running. It is not a
standalone replacement of NuttX, board initialization, or the MCU services.

## Receiving an image

The default dark gray drawer displays the IPv4 address and port queried by the
device, for example `192.168.1.23:18086`. The program queries `wlan0` using the
verified 40-byte `ifreq` ABI and `SIOCGIFADDR=0x701`. Until an address is available
it displays `0.0.0.0:18086`; zero is not an upload destination. The first nonzero
address is cached for this run; DHCP changes after that are not refreshed.
Once an image is accepted, the full drawer contains that image instead of the
address. There is no HTTP endpoint or browser upload page in this version.

```powershell
python -X utf8 analysis/image-push/push_panel_image.py PANEL_IP --pattern
python -X utf8 analysis/image-push/push_panel_image.py PANEL_IP --image picture.png
```

Replace `PANEL_IP` with the address shown on the panel. PNG/JPEG conversion uses
Pillow on the computer (`python -m pip install Pillow`); the generated test
pattern and `--raw` require only the Python standard library. Images are converted
to 480x320 little-endian RGB565. `--fit contain` preserves aspect ratio with dark
margins, `--fit cover` crops, and `--fit stretch` fills the canvas.

Each TCP connection contains one 16-byte header followed by exactly 307200 bytes:

| Offset | Field |
| --- | --- |
| 0 | ASCII `VIMG` |
| 4 | Little-endian u16 width, 480 |
| 6 | Little-endian u16 height, 320 |
| 8 | Little-endian u32 payload length, 307200 |
| 12 | Little-endian u32 FNV-1a checksum over the payload |

The 8-byte reply is ASCII `VACK` followed by a little-endian u32 status:
0 means accepted for GUI consumption, 1 means invalid/truncated/rejected input,
2 means a checksum mismatch or inability to publish after receiving the payload.
An ACK is not a measurement of LCD scanout.
FNV detects transmission/content mistakes; it does not authenticate the sender.
This prototype listens on the panel's LAN interfaces without authentication.

Accepted images stay in owned RAM. Reboot resets the default drawer and discards
the image. The installed program persists, but this version does not write
images to `/data` or Flash. That avoids inventing disk durability from the
static filesystem mount evidence.

## GUI and network ownership

The GUI task retains the existing physical and virtual touch interception,
smooth drawer animation, frame-queue gate, and publisher-locked final owner
commit. Swiping up returns to the original UI; pulling down from its top edge
reveals the image, and the third physical key still switches by triple click.
Tapping an image does not count stars or execute another action.

One 1843200-byte owned allocation contains an RGB32 canvas, an original-screen
snapshot, and two RGB565 image slots. Allocation or worker-creation failure
before original-app startup frees the owned allocation and falls back to stock.
The slots swap under the broker mutex only when the native frame queue is empty
and no gesture/overlay is active. Socket reads happen outside that mutex into
the inactive slot. A partial or corrupt upload never replaces the visible image.
The RGB565 slots are not submitted directly to PAN; the GUI composes into its
owned RGB32 canvas. Published allocations remain alive if the original entry
returns, so retained callbacks and the worker cannot dereference freed memory.

The worker uses nonblocking sockets and `MSG_DONTWAIT` on accepted reads/writes,
handles partial I/O, and polls EAGAIN/EINTR. Receive processing permits 5 seconds
without progress and 30 seconds total, using an independent monotonic clock;
ACK sending starts a separate deadline. Native RPMsg request/response and mutex
waits themselves are not proven to have a strict time bound. These calls stay
out of the GUI callback, but the firmware still relies on the original network
service. One connection is serviced at a time; a pending image waits for the GUI
before the worker accepts another upload.

## Code and recovery boundaries

The new program uses only the existing bounded spans
`0x3804b108..0x3804be70` and `0x3807a764..0x3807a920` (exclusive ends). The shared
helper at `be70`, backlight callback at `a920`, and JSON helper at `ae28` retain
their original current-baseline bytes. It does not activate the original
factory UDP server or borrow the rest of its enclosing thread.

The installer starts from the exact frozen GitHub tap-fast three pages and
verifies all three complete pages. It installs auxiliary, main, then entry;
restore reverses the references by restoring entry, main, then auxiliary.
Unknown or mixed triples are refused. Restore returns exact tap-fast, after
which the existing version-specific restore chain applies. Frozen code,
inputs, and earlier results are immutable. The 168-byte BOOT native caller,
fresh halted context, state restoration, full-page readback, and safe-to-resume
gate are preserved from the reviewed writer.

```powershell
python -X utf8 analysis/persistence/run_native_image_drawer_firmware.py install
.\scripts\Set-PanelNativeImageDrawer.ps1 -Mode restore
```

The first command without `--execute` only checks frozen local inputs and never
accesses the device. The restore command performs the hardware restore and one
ordinary reboot. Original images, raw captures, generated firmware-word arrays,
BIN/ELF files, and credentials remain outside Git.

## Built-in fonts

The exact-image boot script mounts `/dev/font` as ROMFS at `/font` when the device
exists, and the original application uses `/font/MiSansW_Regular.ttf` via LVGL/FreeType.
The font is on MMC, outside the 16 MiB NOR backup. The current file's readability
and usable font API have not been tested on hardware. The native glyph callbacks
share font/cache state, so reuse requires coordination with the original GUI;
they must not be called arbitrarily from the network worker. This version uses
private small digit glyphs for its address and already-rasterized incoming
images. It neither copies the vendor TTF into Git nor claims a completed native
font adapter. Evidence is in `font-resource-feasibility-1.50.10.json`.

## Validation scope

Program models, independent review, installer mocks, and live acceptance are
separate records. Model/mock success does not establish real LCD timing,
network service health, Mi Home controls, or complete power-cycle recovery.
Complete power-cycle testing remains skipped at the user's explicit request
and will not be requested again. Live image transfer, address display, and
gesture observations belong in the new hardware result, not older UI records.
