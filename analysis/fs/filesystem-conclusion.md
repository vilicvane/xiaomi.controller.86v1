# Offline filesystem identification

Source: `backups/mi-panel-flash-16m-20261003.bin` (16,777,216 bytes).

SHA-256: `5f4f06293b81da5e4ab2bc2f2c24aeb357b0dc7be7498194e1ed244ea88986c1`.

## Confirmed evidence

The root agent extracted checksum-valid ROMFS images. The audio-side startup
script at `analysis/romfs/image-00d42d54/init.d/rcS` contains:

```
mkgpt read /dev/mmcsd0
...
mkgpt write /dev/mmcsd0 font:10M misc:8M app:20M data:49M recovery:4M recovery_b:4M factory:16M
...
fsckexfat -y -v /dev/data
mount -t fatfs /dev/data /data
```

The `mkgpt write` is only the fallback when the existing GPT does not pass its
CRC check. These sizes describe the firmware's recovery/default layout, not a
live verified partition table. The actual writable `/data` filesystem is on the
audio core's SD/MMC block device (`/dev/mmcsd0`), not inside the currently backed
up 16 MiB NOR image. The main MCU obtains `/data` through RPMsgFS, as found by the
root agent in its startup script. FATFS is confirmed as the intended mount
driver; exFAT is suggested by the explicit checker, but the existing boot sector
must be read to determine its actual FAT variant.

## Scan limits and negative findings

The standalone scan did not identify an actual FAT boot sector, SQLite database,
littlefs metadata superblock, SMARTFS/SPIFFS filesystem, or UnQLite database
header in this NOR image. Some names appear only in compiled code strings;
`persist.db`, `wapi.conf`, `kvdb`, and `littlefs` hits are not directory entries.

The large region at 0x8e0000 starts with ARM exception vector instructions and
contains the audio program image, rather than a writable filesystem. The `kvdb`
hit at 0x5c0004 is inside a compiled command string table. The source image
contains factory/manufacturing metadata near the end, which was not published.

Therefore no current `/data` directory listing or Wi-Fi configuration can be
extracted from this NOR backup. This does not demonstrate that the Wi-Fi
configuration is missing: its backing medium has not been imaged. Erasing a NOR
region to clear Wi-Fi is not justified by these findings.

## Next read-only evidence

Obtain `/dev/mmcsd0` GPT and the `/dev/data` boot sector through a documented
read-only block/filesystem path on the audio side, or identify and image its
physical SD/MMC/eMMC storage. Once obtained, use the GPT extent and FAT/exFAT
metadata to list and extract `/data/etc/wapi.conf` and `/data/persist.db` without
changing them. Avoid running the startup script: it includes fsck with automatic
repair and a GPT reinitialization fallback.

All work here was offline. The backup was not modified and no HID/debugger or
hardware operation was performed.
