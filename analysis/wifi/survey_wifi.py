"""Read-only Wi-Fi structure survey; never print or save credential values."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'backups' / 'mi-panel-flash-16m-20261003.bin'
OUT = Path(__file__).with_name('wifi-structure-survey.json')
data = SOURCE.read_bytes()

known_images = [(0, 0x1a000), (0x40000, 0xbf000), (0xc0000, 0x13f000),
                (0x150000, 0x7ac000), (0x8e0000, 0xe5d000)]

def image_region(offset):
    return next((f'0x{start:x}-0x{end:x}' for start, end in known_images
                 if start <= offset < end), None)

def safe_value(key, value):
    low = key.lower()
    if any(s in low for s in ('password', 'passwd', 'psk', 'phrase', 'token', 'key', 'secret', 'session')):
        return {'redacted': True, 'type': type(value).__name__,
                'length': len(value) if isinstance(value, (str, bytes, list, dict)) else None,
                'present': value not in ('', None)}
    if isinstance(value, dict):
        return {k: safe_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_value(key, v) for v in value]
    if low in ('ssid', 'bssid', 'auth', 'cmode', 'alg', 'mode', 'ip', 'netmask', 'gateway', 'dhcp', 'dns'):
        return value
    # Avoid leaking credentials hidden under unknown keys.
    if isinstance(value, str):
        return {'type': 'str', 'length': len(value)}
    return value

target_paths = []
property_keys = []
for match in re.finditer(rb'[\x20-\x7e]{4,}\x00', data):
    raw = match.group()[:-1]
    # Limit output strictly to identifiers, not arbitrary surrounding strings.
    if re.fullmatch(rb'/data/(?:miot|mico|factest|etc)/[a-zA-Z0-9_./#-]+', raw):
        if any(s in raw.lower() for s in (b'network', b'wifi', b'wapi', b'miio', b'config', b'reset', b'unlink')):
            target_paths.append({'offset': hex(match.start()), 'path': raw.decode('ascii'),
                                 'image_region': image_region(match.start())})
    elif re.fullmatch(rb'persist\.[a-zA-Z0-9_.-]+', raw):
        if any(s in raw.lower() for s in (b'ssid', b'bssid', b'wifi', b'network', b'factory_pwd', b'miio')):
            property_keys.append({'offset': hex(match.start()), 'key': raw.decode('ascii'),
                                  'image_region': image_region(match.start())})

json_candidates = []
decoder = json.JSONDecoder()
seen = set()
for keymatch in re.finditer(rb'"(?:ssid|bssid|psk|password|dhcp|netmask)"\s*:', data, re.I):
    # A candidate must be a complete valid object containing a Wi-Fi field.
    start_window = max(0, keymatch.start()-4096)
    for start in reversed([start_window+i for i, b in enumerate(data[start_window:keymatch.start()]) if b == 123]):
        if start in seen:
            continue
        seen.add(start)
        segment = data[start:start+16384].split(b'\x00', 1)[0]
        try:
            text = segment.decode('utf-8')
            obj, length = decoder.raw_decode(text)
        except (UnicodeError, ValueError):
            continue
        if not isinstance(obj, dict) or start + len(text[:length].encode()) <= keymatch.start():
            continue
        json_candidates.append({'offset': hex(start), 'length': len(text[:length].encode()),
                                'image_region': image_region(start),
                                'sanitized_object': safe_value('', obj)})

counts = {}
for term in (b'ssid', b'bssid', b'psk', b'password', b'dhcp', b'netmask', b'gateway', b'wapi.conf', b'WiFiSTA'):
    hits = [m.start() for m in re.finditer(re.escape(term), data, re.I)]
    counts[term.decode()] = {'count': len(hits),
                            'outside_known_image_regions': [hex(p) for p in hits if image_region(p) is None]}

report = {'source_name': SOURCE.name, 'source_size': len(data),
          'source_sha256': hashlib.sha256(data).hexdigest(),
          'known_image_ranges_are_heuristic': True,
          'candidate_paths_are_static_literals_not_confirmed_files': target_paths,
          'candidate_property_keys_are_static_literals_not_confirmed_records': property_keys,
          'parsed_json_candidates': json_candidates,
          'term_summary': counts,
          'credential_values_not_saved': True}
OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({'output': str(OUT), 'source_sha256': report['source_sha256'],
                  'target_path_count': len(target_paths), 'property_key_count': len(property_keys),
                  'parsed_json_candidate_count': len(json_candidates),
                  'summary': counts}, indent=2))
