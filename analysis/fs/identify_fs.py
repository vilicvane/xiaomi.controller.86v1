from pathlib import Path
import hashlib, json, struct, collections, zlib

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'backups/mi-panel-flash-16m-20261003.bin'
d = SOURCE.read_bytes()
signatures = {
    'littlefs': b'littlefs', 'SQLite': b'SQLite format 3\0',
    'FAT12': b'FAT12   ', 'FAT16': b'FAT16   ', 'FAT32': b'FAT32   ',
    'exFAT': b'EXFAT   ', 'GPT':b'EFI PART',
    'UnQLite_header':b'unqlite\xdb\x7c\x27\x12',
    'UnQLite_code':b'unqlite', 'SMART':b'SMRT',
    'SPIFFS': b'SPIFFS', 'smartfs': b'smartfs', 'SMARTFS': b'SMARTFS',
    'persist.db': b'persist.db', 'wapi.conf': b'wapi.conf',
    'kvdb': b'kvdb', 'KVDB': b'KVDB', 'kvs': b'kvs',
    'romfs': b'-rom1fs-', 'UBIFS': struct.pack('<I',0x06101831),
    'SquashFS': b'hsqs', 'jffs2-le': b'\x85\x19',
    'YAFFS': b'yaffs', 'FLDB': b'FLDB', 'TSDB': b'TSDB',
}
out = {'size': len(d), 'sha256':hashlib.sha256(d).hexdigest(), 'signatures':{}}
for name,needle in signatures.items():
    hits=[]; start=0
    while (pos:=d.find(needle,start))>=0:
        hits.append(hex(pos)); start=pos+1
    out['signatures'][name] = hits[:200]
    if len(hits)>200:out['signatures'][name].append(f'... {len(hits)} total')

# Find non-erased runs in the upper flash; generated output reports locations only.
runs=[]; active=None
for off in range(0,len(d),4096):
    block=d[off:off+4096]
    used=block!=b'\xff'*len(block)
    if used and active is None:active=off
    if not used and active is not None:
        runs.append([hex(active),hex(off)]);active=None
if active is not None:runs.append([hex(active),hex(len(d))])
out['non_erased_4k_runs']=runs

# Candidate FAT boot sectors, excluding coincidental code strings.
boots=[]
for off in range(0,len(d)-512+1,512):
    b=d[off:off+512]
    bps=struct.unpack_from('<H',b,11)[0]
    spc=b[13];reserved=struct.unpack_from('<H',b,14)[0]
    if b[-2:]==b'\x55\xaa' and bps in (512,1024,2048,4096) and spc in (1,2,4,8,16,32,64,128) and reserved and b[16] in (1,2):
        boots.append({'offset':hex(off),'bps':bps,'spc':spc,'reserved':reserved,'fats':b[16], 'root_entries':struct.unpack_from('<H',b,17)[0], 'total_sectors16':struct.unpack_from('<H',b,19)[0], 'total_sectors32':struct.unpack_from('<I',b,32)[0]})
out['fat_boot_candidates']=boots
# exFAT and GPT use different headers from classic FAT. Validate numeric layout
# and CRC rather than treating embedded driver strings as formatted partitions.
exfat=[];gpts=[]
for p in range(0,len(d)-512,512):
 b=d[p:p+512]
 if b[3:11]==b'EXFAT   ' and b[510:512]==b'\x55\xaa' and b[11:64]==b'\0'*53 and 9<=b[108]<=12 and b[110] in (1,2):
  exfat.append({'offset':hex(p),'bytes_per_sector':1<<b[108],'sectors_per_cluster':1<<b[109],'volume_sectors':struct.unpack_from('<Q',b,72)[0],'fat_offset':struct.unpack_from('<I',b,80)[0],'cluster_heap_offset':struct.unpack_from('<I',b,88)[0]})
 if b[:8]==b'EFI PART':
  hs,crc=struct.unpack_from('<II',b,12)
  if 92<=hs<=512:
   h=bytearray(b[:hs]);h[16:20]=b'\0'*4
   if zlib.crc32(h)==crc:gpts.append({'offset':hex(p),'header_size':hs,'header_crc_valid':True})
out['exfat_boot_candidates']=exfat
out['valid_gpt_headers']=gpts
text=json.dumps(out,indent=2)
(Path(__file__).parent/'fs-signatures.json').write_text(text,encoding='utf-8')
print(text)
