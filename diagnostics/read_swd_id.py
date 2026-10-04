"""Switch the debug interface to SWD and read DPIDR, without CPU/Flash access."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import hid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("swd-id-read.json"))
    parser.add_argument("--dormant", action="store_true", help="Use the standard dormant activation sequence")
    args = parser.parse_args()
    descriptors = [
        item
        for item in hid.enumerate(0x0D28, 0x0204)
        if "CMSIS-DAP" in (item.get("product_string") or "")
    ]
    if len(descriptors) != 1:
        raise SystemExit(f"Expected one CMSIS-DAP probe, found {len(descriptors)}")
    report = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "clock_hz": 10000,
        "interface_selection": "dormant-to-SWD" if args.dormant else "JTAG-to-SWD",
        "scope": "SWD interface switch and DP DPIDR read only; no ABORT, CTRL/STAT, CPU or Flash writes",
        "transactions": [],
    }
    device = hid.device()
    opened = False

    def exchange(name, command):
        if len(command) > 64:
            raise RuntimeError("Command exceeds HID packet size")
        packet = [0] + command + [0] * (64 - len(command))
        if device.write(packet) != 65:
            raise RuntimeError(f"Incomplete HID write: {name}")
        response = device.read(64, 1500)
        entry = {
            "name": name,
            "request_hex": bytes(command).hex(),
            "response_prefix_hex": bytes(response[:12]).hex(),
        }
        report["transactions"].append(entry)
        if not response or response[0] != command[0]:
            raise RuntimeError(f"Invalid response for {name}: {response[:12]}")
        return response

    def check_ok(name, command):
        response = exchange(name, command)
        if len(response) < 2 or response[1] != 0:
            raise RuntimeError(f"Probe rejected {name}: {response[:12]}")

    def sequence(name, data, bit_count):
        check_ok(name, [0x12, bit_count] + list(data))

    try:
        device.open_path(descriptors[0]["path"])
        opened = True
        response = exchange("DAP_Connect(SWD)", [0x02, 0x01])
        if len(response) < 2 or response[1] != 1:
            raise RuntimeError(f"Probe did not select SWD: {response[:12]}")
        check_ok("DAP_SWJ_Clock", [0x11] + list((10000).to_bytes(4, "little")))
        # No idle cycles; bounded WAIT retries; no match retries.
        check_ok("DAP_TransferConfigure", [0x04, 0, 100, 0, 0, 0])
        check_ok("DAP_SWD_Configure", [0x13, 0])
        if args.dormant:
            # OpenOCD src/jtag/swd.h: JTAG-to-dormant, then dormant-to-SWD.
            # These select the debug protocol without accessing target memory.
            sequence("JTAG-to-dormant select", bytes.fromhex("ff75777767"), 40)
            activation = bytes.fromhex(
                "ff92f30962952d8586e9afdde3a20ebc19a0f1"
            ) + b"\xff" * 8 + b"\x00"
            sequence("Dormant-to-SWD select and line reset", activation, 224)
        else:
            sequence("Initial line reset", b"\xff" * 7, 56)
            sequence("JTAG-to-SWD select", b"\x9e\xe7", 16)
            sequence("SWD line reset", b"\xff" * 7, 56)
            sequence("SWD idle", b"\x00", 8)
        # DAP index 0, one transfer, DP read at address 0 (DPIDR).
        response = exchange("DP DPIDR read", [0x05, 0, 1, 0x02])
        if len(response) < 3:
            raise RuntimeError("Truncated DAP_Transfer response")
        report["transfer_count"] = response[1]
        report["transfer_response_hex"] = f"0x{response[2]:02x}"
        report["acknowledgement"] = {1: "OK", 2: "WAIT", 4: "FAULT", 7: "NO_ACK"}.get(response[2] & 7, "INVALID")
        if response[1] == 1 and response[2] == 1 and len(response) >= 7:
            dpidr = int.from_bytes(bytes(response[3:7]), "little")
            report["dpidr_hex"] = f"0x{dpidr:08x}"
            report["valid_dpidr"] = dpidr not in (0, 0xFFFFFFFF) and bool(dpidr & 1)
        else:
            report["valid_dpidr"] = False
    except Exception as error:
        report["error"] = str(error)
    finally:
        if opened:
            try:
                check_ok("DAP_Disconnect", [0x03])
                report["disconnect_acknowledged"] = True
            except Exception as error:
                report["disconnect_error"] = str(error)
        device.close()
        output = args.output
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
