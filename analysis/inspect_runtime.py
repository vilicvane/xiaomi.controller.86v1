"""Inspect local RAM snapshots; only print structural and redacted findings."""
import collections
import hashlib
import json
import re
import struct
from pathlib import Path

root = Path(__file__).resolve().parents[1]
inputs = [
    ("mi-panel-sram-20261003.bin", 0x20000000),
    ("mi-panel-psram-first1m-20261003.bin", 0x34000000),
]
reports = []
capacity = 131072 - 8


def redact(text):
    text = re.sub(r"(?i)([?&](?:k|token|auth|key|code|ticket)=)[^&\s\"'\\]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:password|passphrase|psk|token|ot_key|secret|psm_token)\s*[\"']?\s*[:=]\s*[\"']?)[^\r\n,}\"']+",
                  r"\1[REDACTED]", text)
    text = re.sub(r"(?i)([\"'](?:password|passphrase|psk|token|ot_key|secret|psm_token)[\"']\s*:\s*[\"'])[^\"']*",
                  r"\1[REDACTED]", text)
    return text


for name, base in inputs:
    data = (root / "backups" / name).read_bytes()
    counts = collections.Counter(data)
    report = {"file": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
              "zero_fraction": round(counts[0] / len(data), 4),
              "ramlog_candidates": [], "network_string_addresses": []}
    for match in re.finditer(re.escape(struct.pack("<I", 0x12345678)), data):
        offset = match.start()
        if offset % 4 or offset + 8 > len(data):
            continue
        head = struct.unpack_from("<I", data, offset + 4)[0]
        available = len(data) - offset - 8
        sample = data[offset + 8:offset + 8 + min(1024, available)]
        printable = sum(value in (9, 10, 13) or 32 <= value < 127 for value in sample) / max(1, len(sample))
        candidate = {"address": hex(base + offset), "offset": hex(offset), "head": head,
                     "following_text_fraction": round(printable, 3), "full_buffer_in_snapshot": available >= capacity}
        if 0 < head < 0x10000000 and printable > 0.8 and available >= capacity:
            buffer = data[offset + 8:offset + 8 + capacity]
            content = buffer[:head] if head <= capacity else buffer[head % capacity:] + buffer[:head % capacity]
            decoded = content.decode("utf-8", errors="replace")
            filename = root / "analysis" / f"ramlog-{base + offset:08x}.log"
            filename.write_text(decoded, encoding="utf-8")
            redacted = filename.with_name(filename.stem + "-redacted.log")
            redacted.write_text(redact(decoded), encoding="utf-8")
            candidate["log_path"] = str(filename)
            candidate["redacted_log_path"] = str(redacted)
        report["ramlog_candidates"].append(candidate)
    for match in re.finditer(rb"[\x20-\x7e]{8,}", data):
        text = match.group().decode("ascii")
        if re.search(r"(?i)wifi|wlan|ssid|dhcp|wapi|network\.password|config_reset|miot/network", text):
            report["network_string_addresses"].append({"address": hex(base + match.start()),
                                                        "length": len(text), "text": redact(text)[:300]})
    reports.append(report)

(root / "analysis/runtime-inspection.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
print(json.dumps([{key: value for key, value in report.items() if key != "network_string_addresses"}
                  | {"network_string_count": len(report["network_string_addresses"])} for report in reports], indent=2))
