"""Create static Tcl comparison constants from the unchanged verified backup.

Pure offline data generation: no OpenOCD, target, HID or debug imports.
"""
from pathlib import Path
import hashlib, json, struct
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
image = (ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
assert hashlib.sha256(image).hexdigest() == '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b'
probe = (OUT / 'boot-nor-read-probe.bin').read_bytes()
assert hashlib.sha256(probe).hexdigest() == '66f71a5755a13af4f01010f6b8ca6e0e6fb352a350813e387a9aff4089898fd8'
def words(data):
    return struct.unpack('<' + 'I' * (len(data)//4), data)
sections = {
    'bnor_expected_boot_words': image[0x2220:0x5b58],
    'bnor_expected_probe_words': probe,
    'bnor_expected_nor_page_words': image[:256],
}
lines = ['# Generated offline by build_boot_runner_data.py; no target commands.']
for name, data in sections.items():
    values = words(data)
    lines.append('set ' + name + ' {')
    for i in range(0, len(values), 8):
        lines.append('    ' + ' '.join(str(v) for v in values[i:i+8]))
    lines.append('}')
target = OUT / 'boot-nor-read-runner-data.cfg'
target.write_text('\n'.join(lines) + '\n', encoding='ascii')
review = {
    'offline_only': True,
    'target_calls_performed': 0,
    'definitions_only_library': 'diagnostics/boot-nor-read-runner.cfg',
    'static_constants_file': str(target.relative_to(ROOT)),
    'static_constants_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
    'source_image_sha256': hashlib.sha256(image).hexdigest(),
    'comparison_sizes': {name: len(data) for name,data in sections.items()},
    'boot_mutable_words_excluded_from_source_comparison': ['0x20003a58','0x20003acc','0x20003ad0','0x20003ad4','0x20003ad8','0x20003adc'],
    'boot_mutable_words_independently_compared_before_after': {
        '0x20003a58': 'runtime stack guard',
        '0x20003acc': 'bootmode cache: system_init0c000286 calls0c001e40; helper reads40080038 & ~0xf;0c00028c stores cache; sourceinitial0',
        '0x20003ad0': 'PMU modebyte0:0c000f9a/9bc;PMUrequestcachebytes1/2/3:20002722/2744/27dc; dedicated8Bcapturebefore/after andfullwordequality',
        '0x20003ad4': 'PMUrequestcachebytes4/5:20002816/283e;sysfreqrequesterbyte6:0c01314c/164/19c;byte7minfreqreadbysysfreqsetter;dedicated8Bcapturebefore/after andfullwordequality',
        '0x20003ad8': 'slow timer frequency: BOOT wrapper0c002066 callsveneer->20002e7c;20002de8 measuresfrequency andwrites20002e46/2e4e; sourceinitial16000',
        '0x20003adc': 'runtime timer frequency calibration',
    },
    'static_source_comparison_limit': 'Six proven initialized words excluded. Actualpreflight20261004-144643 sourcecomparisonfoundonly3acc/3ad0/3ad4/3ad8 differences. Furtherdifferences stillabortbefore RAM execution and requireexactwriter evidence.',
    'secure_DCRSR_selectors': {'MSP':26, 'PSP':27, 'MSPLIM':28, 'PSPLIM':29, 'packed_special':34, 'current_packed_special':20},
    'selector_reference': 'C:/Utilities/openocd-0.12.0/src/target/armv7m.h:53-64',
    'signature': 'bnor_run_read_probe capture_dir a7_policy remove_fpb_command',
    'a7_policy': ['halted','powerdown-verified (requires independent outer CMU/power proof)',
                  'held-reset-cmu-verified (requires outer DSP isolation plus fresh original BOOT capture; no APDBG reads)'],
    'held_reset_cmu_gate': {
        'policy': 'held-reset-cmu-verified',
        'entry_provenance': 'outer CPU pilot verified exact original MAIN/BOOT DSP isolation closure, fresh reset catch and SecureThread PC0c0104c6; this library does not perform isolation/reset',
        'mandatory_held_field': 'AON400800a4 bit1 mustbe0 on both samples and finalread;0 meansA7CPU reset asserted',
        'sample_fields_and_masks': {'0x400800a4':'0x3','0x40000044':'0x1c000000',
                                  '0x40000114':'0x41fef','0x40000160':'0x9f','0x40000034':'0x400'},
        'stability': 'two masked samples must match within each gate; full raw words are logged, not required identical to historical values',
        'why_preisolation_masks_not_required_zero': 'BOOTsysteminit0c0002b6 calls0c012a84, clearingAP/X/O/H bank reset masks and AONbit0 while holdingCPUbit1',
        'parent_reported_boot_capture': {'aon':'0x24d','apreset':'0xff','oreset':'0x3c038319','hreset':'0x83fbfe3b'},
        'forbidden_addresses': 'allA7APDBG/CoreSight; specifically58050314PRSR and58050088DSCR',
        'outer_completion': 'verifiedsuccessful session closes withGLOBAL reset intooriginalFW; reader failure preserves halt forroot review; neverresume discardedoldA7/MAINcontext',
        'limits': 'CPU reset-state gate alone doesnot prove allbusmasters/DMAidle or fullcoldrestore; depends on outer isolation/freshBOOT provenance and existing SPIidle/readlock gates',
    },
    'outer_driver_obligation': 'never unconditionally resume on error; only resume after bnor_safe_to_resume==1; runner itself never resumes original boot; held-reset-cmu-verified verifiedsuccess closeswithGLOBALreset, failure retains halted forroot; nooldMAIN/A7 replay',
    'preflight_snapshot': {'file':'capture_dir/boot-hal-context-preflight.bin','address':'0x200001a8','bytes':14968,
                           'ordering':'after verifiedoriginalBOOThalt/corestate, before first static-source comparison, withstablehalt checksarounddump',
                           'purpose':'collect allsource-vs-runtime differences offline in onecapture; mismatch still abortsbefore RAMscratch execution/SPIregisteraccess'},
    'device_write_scope': ['temporary borrowed1024B SRAM','all clobbered integer registers, xPSR, PRIMASK restored','DCRSR/DCRDR transfers','DHCSR mask/run/halt','outer-owned temporary FPB removal','restore saved software lock20003b80 after confirmed post','clear only newly introduced DFSR events'],
    'NOR_mutation_commands': [],
    'failure_policy': 'unexpected reset/exception/fault or incomplete SPI keeps halted, never replays stale core/RAM/controller; ordinary validation failure after confirmed post restores caller but still suppresses outer resume',
    'execution_status': 'nativeSPI/RAMprobe notexecuted; freshBOOTcapture andexactwatchdogstop independentlyverifiedbyroot; nextreader remainsrootowned',
    'controller_mapping_correction': {
        'previous_wrong_assumption': 'logicalid0=40140000 in old reports/mocks; these were not hardware-verified controller mappings',
        'actual_source': 'BOOTtableRAM20003300 sourcefile5378 contains {40148000,40140000}; mainRAM20003948 source155858 matches',
        'runner_gate': 'firstvalidate liveBOOTRAMtable then setdynamicbnor_spi_base; no SPI register access beforehand',
        'expected_id0': '0x40148000',
        'old_mock_evidence': 'success02/powerdown01/reset01/fault01 mock an incorrect controller mapping and are retained as superseded simulation evidence',
        'new_mock_paths': ['analysis/persistence/mock-read-runner-success07/result.txt',
                          'analysis/persistence/mock-read-runner-powerdown06/result.txt',
                          'analysis/persistence/mock-read-runner-reset06/result.txt',
                          'analysis/persistence/mock-read-runner-fault06/result.txt'],
    },
    'offline_validation': {
        'library_parse': 'OpenOCD/Jim source only, no adapter/init: passed',
        'mock_success': 'normal completion restores all captured registers,1024B RAM,DCRDR and original halted controls: passed',
        'mock_powerdown': 'same restoration; powered-off DSCR reads prohibited by mock: passed',
        'mock_reset': 'reset during caller suppresses resume and forbids stale RAM/PC replay: passed',
        'mock_fault': 'fault/exception during caller suppresses resume and forbids stale RAM/PC replay: passed',
        'mock_wrong_table': 'wrong liveBOOT controller pointer table rejected before any SPI read: passed',
        'mock_bootmode_changed': 'initialized nonzero cache accepted; changes during caller rejected and suppress outer resume: passed',
        'mock_held_reset_success': 'actualpilotAON24d accepted without anyAPDBGreads; allcallerstate restored: passed',
        'mock_held_reset_released_entry': 'CPUbit1 releasedfirstgate rejectedbeforeRAMexecution: passed',
        'mock_held_reset_released_prestart': 'firstgate passes;CPUbit1 releasedatsecondgate rejectedbeforeexecution, temporaryRAM/core restored: passed',
        'mock_held_reset_released_post': 'CPUbit1 releasedaftercompletedread rejected, safe_to_resume0: passed',
        'mock_held_reset_bank_changed': 'withinmaskCMUstate change acrosssamples rejected: passed',
        'mock_initialized_config_changed': 'runtimePMUconfig accepted;8Bbefore/aftercaptures andpostcallmutation rejection suppress outerresume: passed',
        'mock_source_mismatch': 'fullpreflight14968Bdump requestedbefore sourcecomparison mismatch; noSPIaccess/RAMexecution: passed',
        'controller_comparison_masks': {'base+0x04':'~0x01fff000 stable read/command fields',
                                       'base+0x14':'0x00ff0000 divider only',
                                       'base+0x34':'0x300 lock/reset only',
                                       'base+0x3c':'record dynamic status, no whole-word equality'},
        'mock_paths': ['analysis/persistence/mock-read-runner-success07/result.txt',
                       'analysis/persistence/mock-read-runner-powerdown06/result.txt',
                       'analysis/persistence/mock-read-runner-reset06/result.txt',
                       'analysis/persistence/mock-read-runner-fault06/result.txt',
                       'analysis/persistence/mock-read-runner-table-mismatch05/result.txt',
                       'analysis/persistence/mock-read-runner-bootmode-changed04/result.txt',
                       'analysis/persistence/mock-read-runner-held-reset-success03/result.txt',
                       'analysis/persistence/mock-read-runner-held-reset-released-entry03/result.txt',
                       'analysis/persistence/mock-read-runner-held-reset-released-prestart03/result.txt',
                       'analysis/persistence/mock-read-runner-held-reset-released-post03/result.txt',
                       'analysis/persistence/mock-read-runner-held-reset-bank-changed04/result.txt',
                       'analysis/persistence/mock-read-runner-source-mismatch02/result.txt',
                       'analysis/persistence/mock-read-runner-initialized-config-changed01/result.txt'],
        'preliminary_fixture_results': 'held-reset-01 andbank-changed02 retained as superseded fixture evidence; hexadecimal variable normalization andwithinmask mutation were corrected before finalnegativecounts passed',
        'limits': 'simulation validates host flow only; does not prove BOOT reachability, real SPI values/controller timings or cold recovery',
    },
}
review['runner_sha256'] = hashlib.sha256((ROOT/'diagnostics/boot-nor-read-runner.cfg').read_bytes()).hexdigest()
(OUT/'boot-nor-read-runner-review.json').write_text(json.dumps(review, indent=2) + '\n')
print(json.dumps({'generated':str(target.relative_to(ROOT)),'size':target.stat().st_size,'comparison_sizes':review['comparison_sizes']}))
