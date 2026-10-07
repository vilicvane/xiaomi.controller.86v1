"""Execute maintained UI ARM instructions with native APIs mocked; no hardware.

Uses historical model helpers without invoking their result writers. The model
does not establish native RPC timing, SMP, LCD scanout, backlight or cold boot.
"""
from pathlib import Path
import array
import hashlib
import json
import os
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis/image-push'))
import test_native_image_drawer_arm as image

ELF = Path(os.environ.get('PANEL_FIRMWARE_ELF',ROOT/'build/panel/panel.elf'))
image.smooth.original.old.ELF = ELF
CTX, PIXELS, IMAGE, RECEIVE = image.CTX, image.PIXELS, image.IMAGE, image.RECEIVE
SCREEN = 0x384ea638
F = dict(image.F,taps=128,screen_off=144,show_address=204)


class Machine(image.Machine):
    def f(self,name,value=None): return self.field(F[name],value)

    def _graph(self):
        super()._graph()
        self.uc.mem_write(CTX+128,bytes(20))
        self.word(SCREEN,1)

    def click(self,hold=60,gap=80,index=None,x=200,y=100):
        index=self.physical_index if index is None else index
        self.now+=gap
        self.contact(index,True,x=x,y=y)
        self.now+=hold
        self.contact(index,False,x=-1,y=-1)
        return self.f('show_address')


def tap_checks():
    checks=[]
    for physical in (0,1):
        m=Machine(physical=physical).ready().custom()
        assert not m.click()
        assert m.click()==1
        assert not m.byte(CTX+140)
        assert m.click()==1
        assert m.click()==0
        assert not m.f('count') and not m.f('overlay')
    checks.append('Both physical orders consume short tap pairs exactly once; triple tap cannot toggle twice and count staysunused')

    for bad in ('hold','gap','distance','move','virtual','clock'):
        m=Machine().ready().custom();m.click()
        if bad=='hold':m.click(hold=301)
        elif bad=='gap':m.click(gap=351)
        elif bad=='distance':m.click(x=233)
        elif bad=='virtual':m.click(index=1-m.physical_index)
        elif bad=='clock':m.clock_result=-1;m.click();m.clock_result=0
        else:
            m.contact(m.physical_index,True,x=200,y=100)
            m.contact(m.physical_index,True,x=220,y=100)
            m.contact(m.physical_index,False)
        assert not m.f('show_address'),bad
        if bad in ('hold','move','clock'):
            assert not m.byte(CTX+140),bad
    checks.append('Long hold, expired pair, distant second contact, drag, virtual input and clock failure never form a doubletap')

    m=Machine().ready().custom();m.now=0xffffff80
    assert not m.click(hold=20,gap=0)
    assert m.click(hold=20,gap=150)==1
    m=Machine().ready().custom();m.click();m.f('wanted',0);m.settle()
    m.f('wanted',1);m.settle();assert not m.click()
    checks.append('Modulo32 monotonic wrap formsvalid pair; owner roundtrip cancels prior waiting tap')

    for owner in (0,1):
        m=Machine().ready()
        if owner:m.custom()
        for _ in range(3):
            for _ in range(5):m.tick(gpio=0x0c000000)
            for _ in range(5):m.tick(gpio=0x0e000000)
        assert m.f('mode')==owner and m.f('wanted')==owner
    checks.append('Third physical GPIO triple click no longer changes either owner')
    return checks


def rendering_checks():
    checks=[]
    m=Machine().ready().custom()
    source=bytes(m.uc.mem_read(IMAGE,307200));m.f('dirty',1);m.tick(ms=0)
    assert m.f('displayed_generation')==1
    assert m.word(PIXELS)==image.rgb(0xf800)
    m.click();m.click();m.tick(ms=0)
    assert m.f('generation')==1 and m.f('show_address')==1
    assert m.word(PIXELS)==0xff101010
    assert bytes(m.uc.mem_read(IMAGE,307200))==source
    m.f('image_pending',1);m.tick(ms=0)
    assert m.f('generation')==2 and m.f('displayed_generation')==1
    assert m.f('show_address')==1 and m.f('image')==RECEIVE
    m.click();m.click();m.pan_result=-1;m.tick(ms=0)
    assert m.f('dirty') and m.f('displayed_generation')==1
    m.pan_result=0;m.tick(ms=0)
    assert m.word(PIXELS)==image.rgb(0x001f) and m.f('displayed_generation')==2
    checks.append('Address view keepsimage generation/activeRGB565 intact; upload acceptsnewslot whilehidden; laterimagePAN advancesdisplayedgeneration and failedPAN retainsdirty')

    # Keep address rendering inside the custom cover and snapshot below it.
    m=Machine();m.f('show_address',1);m.f('generation',3)
    snapshot=array.array('I',(0xff000000|(i*123)&0xffffff for i in range(153600))).tobytes()
    m.uc.mem_write(PIXELS+614400,snapshot)
    guard=bytes([0xa7])*128;m.uc.mem_write(PIXELS-128,guard)
    for cover in range(321):
        m.f('cover',cover);m.call('compose',CTX)
        expected=struct.pack('<I',0xff101010)*(cover*480)+snapshot[cover*1920:]
        assert bytes(m.uc.mem_read(PIXELS,614400))==expected,cover
        assert bytes(m.uc.mem_read(PIXELS-128,128))==guard
    checks.append('Address pagecompose clips all321 cover positions exactly and preserves source/snapshot/guard bounds')
    return checks


def idle_checks():
    checks=[]
    m=Machine().ready();m.word(SCREEN,0);m.tick(ms=0);m.settle()
    assert m.f('mode')==1 and m.f('wanted')==1 and m.word(SCREEN)==0
    m.word(SCREEN,1);m.tick(ms=0);assert m.f('mode')==1
    m.contact(m.physical_index,True,y=300);m.contact(m.physical_index,True,y=180)
    m.contact(m.physical_index,False);m.settle()
    assert m.f('mode')==0 and not m.f('screen_off') and not m.f('show_address')
    checks.append('Off requests custom without writing screen flag; first wake contact cannot count as a tap but may still dismiss the drawer by upward swipe')

    m=Machine().ready().custom();m.click();m.f('wanted',0);m.start(custom=True)
    m.tick(ms=30);before=m.f('shown');m.word(SCREEN,0);m.tick(ms=0)
    assert m.f('target')==320 and m.field(image.FROM)==before
    m.settle();assert m.f('mode')==1 and not m.byte(CTX+140)
    checks.append('Off reversesclosinganimation fromlast accepted pose and clearspendingtap')

    m=Machine().ready().custom();m.click();assert m.byte(CTX+140)
    m.word(SCREEN,0);m.tick(ms=0);assert not m.byte(CTX+140)
    assert m.f('mode')==1 and m.word(SCREEN)==0
    checks.append('Off cancels awaitingdoubletap evenwhen customalreadyownsdisplay')

    for poll_before in (False,True):
        for up_again in (0,1):
            m=Machine().ready().custom();m.word(SCREEN,0);m.tick(ms=0)
            m.word(SCREEN,1)
            if poll_before:m.tick(ms=0)
            m.contact(m.physical_index,True)
            m.now+=60
            m.contact(m.physical_index,False,again=up_again)
            assert not m.f('screen_off') and not m.byte(CTX+140)
            assert not m.click() and m.click()==1
    checks.append('Observed off excludes first physical wake contact from double tap through UP, independent of on-poll ordering and UP continue flag; two fresh taps then toggle')

    m=Machine().ready();m.word(SCREEN,0);m.tick(ms=0)
    assert m.f('overlay')
    m.word(SCREEN,1);m.tick(ms=0)
    m.contact(m.physical_index,True);m.contact(m.physical_index,False)
    m.settle();assert not m.f('screen_off') and not m.f('show_address')
    assert not m.click() and m.click()==1
    checks.append('Wakecontact swallowedbyopeninganimation stillclearstapbarrier afterphysicalUP')

    m=Machine().ready();m.word(SCREEN,0);m.word(SCREEN,1);m.tick(ms=0)
    assert m.f('mode')==0 and m.f('wanted')==0
    checks.append('Off-on pulse whollybetween GUI polls is explicitlyunobservable; modeldoesnotclaim eventhook or guaranteed wakefirstframe')

    for busy in ('physical','virtual','queue','raw'):
        m=Machine().ready();m.word(SCREEN,0)
        if busy=='queue':m.word(0x384ef93c,1)
        elif busy=='raw':m.byte(0x384f50a1,1)
        else:
            i=m.physical_index if busy=='physical' else 1-m.physical_index
            m.contact(i,True,y=100)
        for _ in range(12):m.tick()
        assert m.f('mode')==0,busy
        m.release();m.word(0x384ef93c,0);m.byte(0x384f50a1,0);m.tick();m.settle()
        assert m.f('mode')==1,busy
    checks.append('Off cannot bypass physical/virtual held contacts, rawpressed or displayqueue; releasingbusycondition permitsnormalhandoff')
    return checks


def ownership_checks():
    checks=[]
    for physical in (0,1):
        m=Machine(physical=physical,cached_held=True)
        m.tick();assert m.f('ready') and m.byte(CTX+156)
        assert m.contact(physical,True,x=100,y=0)[18]==1
        assert not m.f('overlay') and not m.byte(CTX+140)
        m.release();assert not m.byte(CTX+156)
    checks.append('Both physicalorders retainbootheldcontact guard withoutinventinginitialtap or topedgecapture')

    for invalid in ('publisher','callback','mmap'):
        m=Machine()
        if invalid=='publisher':m.word(0x384f50b0,0x3870b200)
        elif invalid=='callback':m.word(image.DRIVERS[0]+4,0x3806ab79)
        else:m.word(0x384ef8a0,0x50000004)
        m.tick();assert not m.f('ready'),invalid
        assert m.word(image.DRIVERS[1]+4)==0x3806ab75
        assert m.word(0x384ef87c)==0x383df2dc and m.word(0x384ef854)==0x383df474
    checks.append('Unknownpublisher/callback/mmap failsGUIsetup withoutpublishingpartialdisplay or touchhooks')

    m=Machine().ready();virtual=1-m.physical_index
    m.contact(virtual,True)
    assert m.contact(m.physical_index,True,y=0)[18]==1
    assert not m.f('overlay')
    m.contact(m.physical_index,False);m.contact(virtual,False)
    checks.append('Virtualalreadyheld blocksnewphysicaltopedgecapture andpreservesstockcontact completeness')

    for queued in (0,1):
        m=Machine().ready().custom();m.f('wanted',0)
        m.word(image.SUBS[queued]+8,32)
        assert m.call('handoff',CTX)==0xffffffff and m.f('mode')==1
        m.word(image.SUBS[queued]+12,32)
        assert m.call('handoff',CTX)==0 and m.f('mode')==0
        assert ('lock',image.UPPERS[0]+4) in m.lock_history
        assert ('lock',image.UPPERS[1]+4) in m.lock_history
    checks.append('Handoffstilllocksbothpublishers andrefusespendingphysicalorvirtualsubscriber ring beforeownercommit')

    m=Machine().ready().custom();m.f('wanted',0)
    for address in (0x384f50a1,0x384ef93c,CTX+156):
        if address==0x384ef93c:m.word(address,1)
        else:m.byte(address,1)
        assert m.call('handoff',CTX)==0xffffffff and m.f('mode')==1
        if address==0x384ef93c:m.word(address,0)
        else:m.byte(address,0)
    assert m.call('handoff',CTX)==0 and m.f('mode')==0
    checks.append('Rawpressed, framequeue andactivegesture independentlyprotectfinalhandoff')

    m=Machine().ready();m.f('overlay',1);m.word(image.PLANE+24,0)
    before=len(m.frames);m.call('pan',0x384ef84c,image.PLANE)
    m.call('area',0x384ef84c,image.PLANE)
    assert len(m.frames)==before and not m.area_calls
    m.f('overlay',0);m.call('pan',0x384ef84c,image.PLANE)
    m.call('area',0x384ef84c,image.PLANE)
    assert m.frames[-1]==0 and m.area_calls==1
    m.word(image.PLANE+24,0xffffffff);before=len(m.frames)
    assert m.call('pan',0x384ef84c,image.PLANE)==0xffffffff and len(m.frames)==before
    checks.append('PANandUPDATEAREA proxies preserve suppression, stockdelegation andrelocationsource sentinelrejection')

    for allocations,create,frees in [([CTX,PIXELS],0,[]),([0],0,[]),
                                      ([CTX,0],0,[CTX]),([CTX,PIXELS],-1,[PIXELS,CTX])]:
        m=Machine();m.allocations=list(allocations);m.create_result=create
        assert m.call('broker_main',2,0x389d0200)==17 and m.original_calls==1
        assert m.freed==frees
        assert m.allocation_sizes==([212,1843200] if len(allocations)>1 else [212])
    checks.append('Originalentryruns once; context/frameheap or workercreationfailuresunwindonlyunpublishedownedallocations')

    for invalid in ('dead','type','closed','fd','foreign'):
        m=Machine().ready();m.word(0x384fce58,0x3806a93d)
        if invalid=='dead':m.f('alive',0)
        elif invalid=='type':m.byte(0x384fce30,12)
        elif invalid=='closed':m.word(0x384fce54,3)
        elif invalid=='fd':m.word(0x384fce20,0xffffffff)
        else:m.word(0x384fce58,0x3806a941)
        before=m.word(0x384fce58);m.call('arm_timer',CTX)
        assert m.word(0x384fce58)==before
    checks.append('Timerhook CAS neverresurrectsdead/closing/invalidtimer oroverwritesforeigncallback')
    return checks


def main():
    checks=tap_checks()+rendering_checks()+idle_checks()+ownership_checks()
    result={'passed':True,'hardware_operation':False,'check_count':len(checks),
            'checks':checks,'elf_sha256':hashlib.sha256(ELF.read_bytes()).hexdigest(),
            'context_bytes':212,'limitations':'Native locks/RPC/display/backlight/OS scheduling are mocked; no LCD timing, cold boot or live idle guarantee.'}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
