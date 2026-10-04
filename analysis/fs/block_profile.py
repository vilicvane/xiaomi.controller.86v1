from pathlib import Path
from collections import Counter
import math,json,struct,re
d=(Path(__file__).resolve().parents[2]/'backups/mi-panel-flash-16m-20261003.bin').read_bytes()
out=[]
for off in range(0,len(d),65536):
 b=d[off:off+65536];c=Counter(b)
 ent=-sum(n/len(b)*math.log2(n/len(b)) for n in c.values())
 row={'offset':hex(off),'entropy':round(ent,3),'ff_percent':round(c[255]/len(b)*100,2),'zero_percent':round(c[0]/len(b)*100,2),'ascii_percent':round(sum(32<=x<127 for x in b)/len(b)*100,2)}
 if b!=b'\xff'*len(b):out.append(row)
(Path(__file__).parent/'block-profile.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps([r for r in out if int(r['offset'],16)>=0x780000 or r['offset']=='0x5c0000'],indent=2))
# Binary layout near interesting regions: output only numeric structure fields.
print('REGION STRUCTURE')
for off in [0x150000,0x5c0000,0x8e0000]:
 vals=struct.unpack_from('<8I',d,off)
 print(hex(off),[hex(v) for v in vals])
