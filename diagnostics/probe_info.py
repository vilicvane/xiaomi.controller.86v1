"""Read CMSIS-DAP USB metadata without connecting to the target interface."""

import json
from datetime import datetime, timezone
from pathlib import Path

import hid


def read_info(device, info_id):
    # HID report ID 0 followed by DAP_Info (0x00), its ID and padding.
    packet = [0, 0, info_id] + [0] * 62
    if device.write(packet) != len(packet):
        raise RuntimeError("Incomplete USB HID write")
    response = device.read(64, 1500)
    if len(response) < 2 or response[0] != 0:
        raise RuntimeError(f"Invalid DAP_Info response: {response}")
    length = response[1]
    if len(response) < length + 2:
        raise RuntimeError(f"Truncated DAP_Info response: {response}")
    return bytes(response[2 : length + 2])


def main():
    results = []
    for descriptor in hid.enumerate(0x0D28, 0x0204):
        if "CMSIS-DAP" not in (descriptor.get("product_string") or ""):
            continue
        result = {
            "manufacturer": descriptor.get("manufacturer_string"),
            "product": descriptor.get("product_string"),
            "usb_interface": descriptor.get("interface_number"),
            "queries": {},
        }
        device = hid.device()
        try:
            device.open_path(descriptor["path"])
            for name, info_id in (
                ("vendor", 0x01),
                ("product", 0x02),
                ("firmware_version", 0x04),
                ("capabilities", 0xF0),
                ("packet_count", 0xFE),
                ("packet_size", 0xFF),
            ):
                payload = read_info(device, info_id)
                entry = {"payload_hex": payload.hex()}
                if info_id < 0xF0:
                    entry["value"] = payload.rstrip(b"\0").decode("utf-8", "replace")
                else:
                    value = int.from_bytes(payload, "little") if payload else None
                    entry["value"] = value
                    if info_id == 0xF0 and value is not None:
                        entry["swd_supported"] = bool(value & 1)
                        entry["jtag_supported"] = bool(value & 2)
                result["queries"][name] = entry
        except Exception as error:
            result["error"] = str(error)
        finally:
            device.close()
        results.append(result)
    report = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "commands_sent": "DAP_Info only; no DAP_Connect or target commands",
        "probes": results,
    }
    output = Path(__file__).with_name("probe-info.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
