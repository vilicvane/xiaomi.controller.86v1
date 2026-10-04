"""Offline correction of logical flash id versus physical SPI naming.

No hardware imports. Preserve the explicit record of the prior wrong assumption.
"""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from audit_cold_recovery import B,offset,decode
tables=[]
for view,address in [('boot',0x20003300),('main',0x20003948)]:
    source=offset(address,view)
    raw=B[source:source+8]
    values=struct.unpack('<II',raw)
    assert values==(0x40148000,0x40140000)
    tables.append({'view':view,'RAM_address':hex(address),'file_offset':hex(source),
                   'raw_hex':raw.hex(),'logical_id0':hex(values[0]),'logical_id1':hex(values[1])})
waiters=[]
for view,address in [('boot',0x20000450),('main',0x20000790)]:
    instructions=decode(address,16,view)
    waiters.append({'view':view,'function':hex(address),'instructions':instructions,
                    'semantics':'loadcontroller=table[r0]; while(word[controller+0xc]&1)loop; no softwaretimeout',
                    'status_limit':'controllerbusy bit0 is not FlashSR1.WIP; runningFlashfetch or concurrentA7/DMA may make it1'})
record={'offline_only':True,'target_I_O_performed':0,'source_SHA256':hashlib.sha256(B).hexdigest(),
 'previous_error':{'wrong_mapping':'logicalid0=40140000/logicalid1=40148000',
                   'cause':'report label assumed public defaultphysicalcontroller naming without reading currentimage pointertable order',
                   'not_live_verified':'old report mapping and old read-runnermocks were not validated targetSPI evidence'},
 'corrected_raw_tables':tables,'wait_idle_proof':waiters,
 'root_reported_live_evidence':{'files':['diagnostics/mcu-safe-reset-metadata.txt','diagnostics/mcu-active-flash-metadata.txt'],
  'mapping':'mainRAM20003948={40148000,40140000}',
  'running_active_controller_reads':{'4014800c':'0x1053','40148034':'0x2f000'},
  'limit':'root observed4014000c stall whileoldsecondary was accessed; mapping error and correctbaseaccess are proved, internalcause ofstall not independently proved bythisaudit'},
 'precondition':'read exactliveSRAM pointertable first; derivechosenbasefromtable[id]; verifyexpectedorder; onlythenaccessperipherals',
 'runner':'diagnostics/boot-nor-read-runner.cfg nowderivesbasefromliveBOOT20003300,expectsid0=40148000; nonmatchingtable causesnoSPIaccess',
 'report_updates':['nor-programming-review.json/md','boot-nor-programming-review.json/md','hal-transplant-manifest.json',
                  'boot-nor-read-probe-review.json','boot-nor-read-runner-review.json/md'],
 'preserved_superseded_mock_examples':['mock-read-runner-success02','mock-read-runner-powerdown01','mock-read-runner-reset01','mock-read-runner-fault01']}
(OUT/'controller-mapping-correction.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'confirmed_tables':tables,'hardware_calls':0}))
