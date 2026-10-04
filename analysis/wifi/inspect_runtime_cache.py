"""Read known MiIO cache fields; save only safe values and credential lengths."""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / 'backups' / 'mi-panel-psram-first1m-20261003.bin'
data = SOURCE.read_bytes()
base = 0x34000000
global_offset = 0x2e658
report = {'source': SOURCE.name, 'sha256': hashlib.sha256(data).hexdigest(),
          'miio_struct_address': hex(base+global_offset),
          'field_layout_evidence': 'Flash file offsets 0x25d0d6..0x25d138 read namespace network using string getter into these buffers',
          'fields': {}}
for name, offset, capacity, secret in [('ssid', 0x2f, 0x21, False),
                                      ('password', 0x50, 0x41, True),
                                      ('ssid_5g', 0x91, 0x21, False),
                                      ('password_5g', 0xb2, 0x41, True)]:
    raw = data[global_offset+offset:global_offset+offset+capacity]
    value = raw.split(b'\0', 1)[0]
    field = {'address': hex(base+global_offset+offset), 'length_bytes': len(value),
             'nul_terminated': b'\0' in raw, 'present': bool(value)}
    if secret:
        field['value'] = '[redacted]'
    else:
        try:
            text = value.decode('utf-8')
            field['value'] = text if all(c.isprintable() for c in text) else '[non-printable]'
        except UnicodeError:
            field['value'] = '[not valid UTF-8]'
    report['fields'][name] = field
markers = ['wifi_connected', 'wifi_connecting', 'cloud_trying', 'cloud_connected',
           'sta_mode', 'dhcp failed', 'NOT same with the orignal', 'ssid get failed',
           'the input password is too long', 'the input ssid is too long']
report['marker_addresses'] = {s: [hex(base+m.start()) for m in re.finditer(re.escape(s.encode()), data)]
                              for s in markers}
report['private_ipv4_unattributed_candidates'] = sorted(set(m.group().decode() for m in re.finditer(
    rb'(?<![\w.])(?:192\.168\.[0-9]{1,3}\.[0-9]{1,3}|10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3})(?![\w.])', data)))
report['limits'] = 'Caches and heap fragments from a running, non-atomic RAM snapshot; no temporal ordering or proof of currently active network. The device was not halted or reset. Missing markers do not rule out past errors.'
report['credential_values_not_saved'] = True
out = HERE / 'runtime-wifi-cache.json'
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(report, indent=2, ensure_ascii=False))
