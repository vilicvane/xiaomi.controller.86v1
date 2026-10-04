"""Offline BOOT init normal closure audit. Does not import hardware or execute firmware.
Reports unresolved/external edges; stack bounds exclude their code and errors.
Only output boot-independent-init-nor-closure files.
"""
"""Read-only instruction CFG audit of the exact 1.50.10 NOR image.

This deliberately records assert/stack-failure edges separately, and resolves
the active 85-65-18 chip callback only from the independently verified table.
No target/hardware API is imported.  Stack results exclude exception frames.
"""
from pathlib import Path
import json, struct, sys
BOOT=True
if BOOT:
 from audit_cold_recovery import B,CS,offset
 def off(address):return offset(address,'boot')
else:
 from probe_nor import B,CS,off
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC, ARM_REG_SP

OUT=Path('analysis/persistence')
NO_SUSPEND=True
ERRORS={0x20003908:'trace/assert error path to Flash',
        0x20003920:'stack failure path to Flash',
        0x20003938:'assert failure path to Flash'}
# Firmware indirect calls/tails whose active target has been table-verified.
INDIRECT={0x200019ae:0x20002900,0x200027b4:0x20002900}
if BOOT:
 ERRORS={0x200032e0:'trace/assert error path to Flash',
         0x20002658:'stack failure path to trace/assert',
         0x200032f0:'assert failure path to Flash'}
 INDIRECT={0x20001672:0x200024f4,0x20002380:0x200024f4,0x200023a8:0x200024f4}
memo={}

def h(x):return hex(x)
def instruction(pc):
 p=off(pc)
 if p is None:return None
 return next(CS.disasm(B[p:p+4],pc,count=1),None)

def one(start):
 if start in memo:return memo[start]
 result={'entry':h(start),'calls':[], 'abnormal_edges':[], 'unresolved':[],
         'flash_literals':[], 'literal_targets':[], 'instructions':[],
         'max_local_stack_bytes':0}
 memo[start]=result
 queue=[(start,0)];visited=set();calls={};seen_lit=set()
 while queue:
  pc,depth=queue.pop()
  if (pc,depth) in visited:continue
  visited.add((pc,depth))
  if len(visited)>6000 or depth<0 or depth>4096:
   result['unresolved'].append({'pc':h(pc),'reason':'CFG limit or inconsistent SP','depth':depth});continue
  i=instruction(pc)
  if i is None or not i.id:
   result['unresolved'].append({'pc':h(pc),'reason':'not an instruction'});continue
  if not 0x20000000<=pc<0x20100000:
   result['unresolved'].append({'pc':h(pc),'reason':'non SRAM instruction'});continue
  result['instructions'].append(h(pc))
  result['max_local_stack_bytes']=max(result['max_local_stack_bytes'],depth)
  for o in i.operands:
   if o.type==ARM_OP_MEM and o.mem.base==ARM_REG_PC:
    lit=((pc+4)&~3)+o.mem.disp;p=off(lit)
    if p is not None:
     value=struct.unpack_from('<I',B,p)[0]
     if lit not in seen_lit:
      seen_lit.add(lit);item={'instruction':h(pc),'pool':h(lit),'value':h(value)}
      result['literal_targets'].append(item)
      if any(base<=value<base+len(B) for base in (0x0c000000,0x08000000,0x28000000,0x2c000000)):
       result['flash_literals'].append(item)
  mnemonic=i.mnemonic.split('.')[0]
  if mnemonic.startswith('push') or mnemonic=='stmdb' and i.operands[0].type==ARM_OP_REG and i.operands[0].reg==ARM_REG_SP:
   depth+=4*sum(o.type==ARM_OP_REG for o in i.operands)
   if mnemonic=='stmdb':depth-=4
  elif mnemonic in ('sub','add') and len(i.operands)>=2 and i.operands[0].type==ARM_OP_REG and i.operands[0].reg==ARM_REG_SP and i.operands[-1].type==ARM_OP_IMM:
   depth+=i.operands[-1].imm*(1 if mnemonic=='sub' else -1)
  result['max_local_stack_bytes']=max(result['max_local_stack_bytes'],depth)
  nxt=pc+i.size
  if NO_SUSPEND and pc==(0x2000199a if BOOT else 0x20001d26):
   # All selected public HAL entries force suspend=0.  Protection/status
   # write_reg also invokes WIP_wait with r1=0.  Thus r7 is zero here.
   queue.append((0x2000198c if BOOT else 0x20001d18,depth));continue
  if mnemonic=='bl' or mnemonic=='blx':
   target=next((o.imm&~1 for o in i.operands if o.type==ARM_OP_IMM),INDIRECT.get(pc))
   if target in ERRORS:
    result['abnormal_edges'].append({'pc':h(pc),'target':h(target),'reason':ERRORS[target]})
    # These edges are excluded from the asserted valid-arguments path only.
   elif target is None:
    result['unresolved'].append({'pc':h(pc),'reason':'indirect call','instruction':i.op_str})
   else:calls[(pc,target)]=depth
   queue.append((nxt,depth));continue
  # Terminal return instructions; conditional returns keep fall-through.
  conditional=i.cc not in (0,15)
  if mnemonic.startswith('pop'):
   terminal=any(o.type==ARM_OP_REG and o.reg==ARM_REG_PC for o in i.operands)
   depth-=4*sum(o.type==ARM_OP_REG for o in i.operands)
   if terminal:
    if conditional:queue.append((nxt,depth))
    continue
  if mnemonic.startswith('ldr') and i.operands[0].type==ARM_OP_REG and i.operands[0].reg==ARM_REG_PC:
   if not (len(i.operands)>1 and i.operands[1].type==ARM_OP_MEM and i.operands[1].mem.base==ARM_REG_SP):
    result['unresolved'].append({'pc':h(pc),'reason':'indirect PC load'})
   if conditional:queue.append((nxt,depth))
   continue
  if mnemonic.startswith('bx'):
   if i.op_str!='lr':
    target=INDIRECT.get(pc)
    if target is None:result['unresolved'].append({'pc':h(pc),'reason':'indirect tail','instruction':i.op_str})
    else:queue.append((target,depth))
   if conditional:queue.append((nxt,depth))
   continue
  if mnemonic in ('b','beq','bne','bhs','blo','bmi','bpl','bvs','bvc','bhi','bls','bge','blt','bgt','ble','bal','cbz','cbnz'):
   target=next((o.imm&~1 for o in reversed(i.operands) if o.type==ARM_OP_IMM),None)
   if target is not None:
    if target in ERRORS:result['abnormal_edges'].append({'pc':h(pc),'target':h(target),'reason':ERRORS[target]})
    else:queue.append((target,depth))
    if mnemonic!='b' or conditional:queue.append((nxt,depth))
    continue
  queue.append((nxt,depth))
 result['calls']=[{'instruction':h(pc),'target':h(target),'caller_stack_bytes':depth} for (pc,target),depth in sorted(calls.items())]
 result['instructions']=sorted(set(result['instructions']),key=lambda s:int(s,16))
 for (pc,target),depth in list(calls.items()):one(target)
 return result

def tree(entry,seen=None):
 seen=set() if seen is None else seen
 if entry in seen:return set()
 seen.add(entry);r=memo[entry];out={entry}
 for c in r['calls']:out|=tree(int(c['target'],16),seen)
 return out

def peak(entry,path=()):
 if entry in path:raise ValueError('recursive call cycle')
 r=memo[entry];n=r['max_local_stack_bytes']
 for c in r['calls']:
  n=max(n,c['caller_stack_bytes']+peak(int(c['target'],16),path+(entry,)))
 return n


import hashlib
roots={'native_init':0x20001380,'open_wrapper':0x20001038,'open_internal':0x20000bc0,'controller_stop':0x20000946,'mode_setup':0x20002014,'read_mode':0x20001ab4,'flash_clock_veneer':0x200032f8}
for root in roots.values():one(root)
summary={}
for name,entry in roots.items():
 closure=tree(entry)
 try:stack=peak(entry)
 except ValueError:stack=None
 summary[name]={'entry':h(entry),'closure':list(map(h,sorted(closure))),
 'partial_maximum_stack_bytes_excluding_unknown_external_errors_interrupts':stack,
 'flash_literals':[x for f in closure for x in memo[f]['flash_literals']],
 'abnormal_edges':[x for f in closure for x in memo[f]['abnormal_edges']],
 'unresolved':[x for f in closure for x in memo[f]['unresolved']]}
report={'offline_only':True,'source_sha256':hashlib.sha256(B).hexdigest(),'roots':summary,
 'functions':{h(k):v for k,v in sorted(memo.items())},'indirect_resolution':{h(k):h(v) for k,v in INDIRECT.items()},
 'caveat':'Conservative branch graph. Known stack/assert error veneers excluded. Unknown indirect PC loads, external functions and missing code prevent complete stack or SRAM-only proof. suspend=0 specialization applies only where callers force it.'}
Path('analysis/persistence/boot-independent-init-nor-closure.json').write_text(json.dumps(report,indent=2)+'\n')
for name,r in summary.items():print(name,'functions',len(r['closure']),'partial_stack',r['partial_maximum_stack_bytes_excluding_unknown_external_errors_interrupts'],'Flash literals',len(r['flash_literals']),'unresolved',r['unresolved'])
