"""Summarize a local Flash backup; this script has no hardware access."""

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path


def flash_offset(address, size):
    for base in (0x28000000, 0x2C000000, 0x0C000000):
        if base <= address < base + size:
            return address - base
    return None


def build_fields(data, offset):
    text = data[offset:offset + 4096].split(b"\x00", 1)[0]
    if b"CHIP=" not in text[:64]:
        return None
    fields = {}
    for line in text.decode("ascii", errors="replace").splitlines():
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
        if match:
            fields[match[1]] = match[2]
    return fields or None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--expected-size", type=lambda value: int(value, 0), default=0x1000000)
    args = parser.parse_args()
    data = args.image.read_bytes()
    if len(data) != args.expected_size:
        raise SystemExit(f"Incomplete backup: {len(data)} bytes, expected {args.expected_size}")

    boot_headers = []
    magic = struct.pack("<I", 0xBE57EC1C)
    position = 0
    while (position := data.find(magic, position)) != -1:
        if position + 16 <= len(data):
            _, security, version, reserved, pointer = struct.unpack_from("<IHHII", data, position)
            offset = flash_offset(pointer, len(data))
            fields = build_fields(data, offset) if offset is not None else None
            if fields:
                boot_headers.append({
                    "flash_offset": f"0x{position:08x}",
                    "security_field": security,
                    "header_version": version,
                    "reserved": f"0x{reserved:08x}",
                    "build_info_address": f"0x{pointer:08x}",
                    "build_info": fields,
                })
        position += 4

    build_blocks = []
    for match in re.finditer(rb"(?:^|\n)CHIP=", data):
        offset = match.start()
        fields = build_fields(data, offset)
        if fields:
            build_blocks.append({"flash_offset": f"0x{offset:08x}", "fields": fields})

    markers = {}
    for marker in (b"littlefs", b"spiffs", b"smartfs", b"wapi.conf", b"/data/", b"nvrecord", b"miio"):
        offsets = [f"0x{match.start():08x}" for match in re.finditer(re.escape(marker), data, re.IGNORECASE)]
        if offsets:
            markers[marker.decode()] = {"count": len(offsets), "first_offsets": offsets[:8]}

    head = Path(__file__).with_name("flash-head-4k.bin").read_bytes()
    build_sample = Path(__file__).with_name("boot-build-info-1k.bin").read_bytes()
    report = {
        "image": str(args.image.resolve()),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "matches_earlier_flash_head": data[:len(head)] == head,
        "matches_earlier_boot_build_info": data[0x19AC4:0x19AC4 + len(build_sample)] == build_sample,
        "boot_headers": boot_headers,
        "build_blocks": build_blocks,
        "storage_string_markers": markers,
        "limits": "String markers are clues, not proven partitions or live Wi-Fi settings. Backup was read while the firmware ran.",
    }
    output = args.image.with_suffix(".json")
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
