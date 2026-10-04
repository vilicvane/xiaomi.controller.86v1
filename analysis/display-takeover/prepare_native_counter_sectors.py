"""Build exact original/patched sectors for the reviewed 1.50.10 task entry."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/display-takeover'
image_path = ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin'
image = image_path.read_bytes()
digest = lambda data: hashlib.sha256(data).hexdigest()
assert len(image) == 0x1000000
assert digest(image) == '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
code_path = OUT / 'native-counter.bin'
code = code_path.read_bytes()
assert 0 < len(code) <= 0x588
elf = (OUT / 'native-counter.elf').read_bytes()
assert elf[:7] == b'\x7fELF\x01\x01\x01'
assert struct.unpack_from('<I', elf, 24)[0] == 0x3804b2f5
shoff = struct.unpack_from('<I', elf, 32)[0]
shentsize, shnum = struct.unpack_from('<HH', elf, 46)
allocated = []
for index in range(shnum):
    header = struct.unpack_from('<10I', elf, shoff + index*shentsize)
    _, kind, flags, address, offset, size, *_ = header
    if flags & 2:
        assert kind == 1 and not flags & 1  # only read-only PROGBITS, no data/BSS
        allocated.append((address, elf[offset:offset+size]))
allocated.sort()
assert allocated[0][0] == 0x3804b2f4
actual = bytearray()
for address, data in allocated:
    assert address == 0x3804b2f4 + len(actual)
    actual.extend(data)
assert bytes(actual) == code  # raw binary has identical linked addresses
assert struct.unpack_from('<I', image, 0xccdcc8)[0] == 0x3818f9fd
sectors = {}
for name, offset, patch_offset, patch in (
    ('code', 0x92b000, 0x2f8, code),
    ('entry', 0xccd000, 0xcc8, struct.pack('<I', 0x3804b2f5)),
):
    original = image[offset:offset+4096]
    patched = bytearray(original)
    patched[patch_offset:patch_offset+len(patch)] = patch
    sectors[name] = {'offset': hex(offset), 'patch_offset': hex(patch_offset), 'patch_bytes': len(patch)}
    for state, data in (('original', original), ('patched', bytes(patched))):
        path = OUT / f'native-counter-{state}-sector-{offset:x}.bin'
        path.write_bytes(data)
        sectors[name][state] = {'path': str(path.relative_to(ROOT)), 'sha256': digest(data), 'bytes': len(data)}
    assert patched[:patch_offset] == original[:patch_offset]
    assert patched[patch_offset+len(patch):] == original[patch_offset+len(patch):]
result = {
    'firmware': {'path': str(image_path.relative_to(ROOT)), 'sha256': digest(image)},
    'program': {'path': str(code_path.relative_to(ROOT)), 'sha256': digest(code), 'bytes': len(code),
                'entry': '0x3804b2f5', 'container_bytes': 1416},
    'scope': 'Replace factory faclvgl main container and normal vapp builtin entry; two exact NOR sectors only. Preserve original vapp implementation and all other bytes.',
    'install_order': ['code', 'entry'], 'restore_order': ['entry', 'code'], 'sectors': sectors,
}
path = OUT / 'native-counter-patch-inputs-1.50.10.json'
path.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({'manifest': str(path), 'sha256': digest(path.read_bytes()), 'code_bytes': len(code)}, indent=2))
