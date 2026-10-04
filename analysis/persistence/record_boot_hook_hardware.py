"""Check saved BOOT hook evidence only. Never connect to or operate hardware.

Example:
  python record_boot_hook_hardware.py --install-capture CAPTURE \
    --install-outer-log OUTER --warm-log WARM --cold-log COLD --cold-user-confirmed

Omitted restore/cold evidence remains pending. Supplied invalid evidence fails.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'analysis/persistence'
FROZEN = {
    'diagnostics/boot-nor-hook-runner.cfg': 'c37ef00010de3bc59155da30e88ebd8f395797f1df684667305e7ea50490e11a',
    'diagnostics/boot-nor-hook-stage-inputs.cfg': 'b1b7eb14b1c72b3bb649e185d64e991d4b1567ebf04bd29d957cbf83db3502d3',
}
MARKER = 0x4b4f4f48


def digest(data):
    return hashlib.sha256(data).hexdigest()


def resolve(value):
    p = Path(value)
    return p.resolve() if p.is_absolute() else (ROOT / p).resolve()


def display(path):
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_text(path):
    return path.read_text(encoding='utf-8-sig', errors='strict')


def exact_line(text, line):
    return line in text.splitlines()


def numbers(text, prefix, count=None):
    matches = re.findall(r'^' + re.escape(prefix) + r' (.+)$', text, re.M)
    require(len(matches) == 1, f'Expected one {prefix} record')
    values = [int(v, 0) for v in matches[0].split()]
    if count is not None:
        require(len(values) == count, f'Wrong {prefix} length')
    return values


def read_blob(path, size):
    data = path.read_bytes()
    require(len(data) == size, f'Wrong byte length: {display(path)}')
    require(not data.startswith(b'MOCK'), f'Mock placeholder is not hardware evidence: {display(path)}')
    return data


def pending(reason):
    return {'status': 'pending', 'reason': reason}


def inspect_outer(path):
    require(path is not None, 'Outer log is required for completed operation')
    text = read_text(path)
    for flag in ('hook_safe_to_resume 1', 'pre_global_debug_cleanup_error 0',
                 'pre_GLOBAL_DCRDR_cleared 1', 'cleanup_global_requested 1',
                 'cleanup_dispatch_complete 1', 'fresh_process_required 1',
                 'unexpected_reset 0'):
        require(exact_line(text, flag), f'Outer missing {flag}')
    require('cleanup_retained_halt' not in text, 'Outer retained a failed caller')
    transport = re.findall(r'^cleanup_global_transport_error (\d+)$', text, re.M)
    require(transport and all(v == '0' for v in transport), 'GLOBAL transport failed/unknown')
    writes = [(m.start(), int(m.group(1), 16), int(m.group(2), 16)) for m in re.finditer(
        r'^write_possible_\d+ 0x([0-9a-f]+) 0x([0-9a-f]+)$', text, re.M | re.I)]
    clears = [pos for pos, address, value in writes if address == 0xe000edf8 and value == 0]
    resets = [pos for pos, address, value in writes if address == 0x400800a4 and value == 0x200]
    clear_tag = text.index('pre_GLOBAL_DCRDR_cleared 1')
    require(clears and resets and clears[-1] < clear_tag < resets[-1], 'DCRDR clear/GLOBAL ordering not evidenced')
    require(not any(pos > clears[-1] and address == 0xe000edf4 for pos, address, _ in writes),
            'DCRSR transfer after final DCRDR clear would invalidate marker baseline')
    return {'status': 'passed', 'log': display(path), 'sha256': digest(path.read_bytes()),
            'pre_GLOBAL_DCRDR_cleared': True, 'GLOBAL_dispatch_verified': True,
            'fresh_process_required': True,
            'cleanup_complete_note': 'cleanup_complete0 is expected: ordinary boot is checked by separate fresh MEM-AP log'}


def inspect_stage(directory):
    log_path = directory / 'result.txt'
    text = read_text(log_path)
    for line in ('scratch_restored 1', 'core_context_restored 1',
                 'context_restore_complete 1 test_error 0 cleanup_error 0',
                 'safe_to_resume_original_boot 1', 'pre_run_AON_WDT_CTRL 0x00000000'):
        require(exact_line(text, line), f'{directory.name}: missing {line}')
    require('validated_BOOT_SPI_id0_base 0x40148000 ' in text, f'{directory.name}: controller not validated')
    execution = re.findall(r'^native_execution_verified 1 stage (\S+) kind (read|onecall)$', text, re.M)
    require(len(execution) == 1, f'{directory.name}: native return/post not confirmed')
    stage, kind = execution[0]
    before = numbers(text, 'controller_before', 4)
    after = numbers(text, 'controller_after', 4)
    require(not (after[2] & 0x300), f'{directory.name}: controller lock/reset still asserted')
    require((before[0] & ~0x01fff000) == (after[0] & ~0x01fff000) and
            (before[1] & 0x00ff0000) == (after[1] & 0x00ff0000) and
            (before[2] & 0x300) == (after[2] & 0x300), f'{directory.name}: stable controller changed')
    scratch_before = read_blob(directory / 'scratch-original.bin', 1024)
    scratch_after = read_blob(directory / 'scratch-restored.bin', 1024)
    require(scratch_before == scratch_after, f'{directory.name}: borrowed SRAM differs')
    config_before = read_blob(directory / 'boot-initialized-config-before.bin', 8)
    config_after = read_blob(directory / 'boot-initialized-config-after.bin', 8)
    require(config_before == config_after, f'{directory.name}: PMU/sysfreq initialized data differs')
    running = read_blob(directory / 'scratch-after-program.bin', 1024)
    count = 10 if kind == 'read' else 9
    output = list(struct.unpack_from('<' + 'I'*count, running, 128))
    require(output == numbers(text, 'output_words', count), f'{directory.name}: binary output/log mismatch')
    oldmask = re.findall(r'^saved_regsel_14 0x([0-9a-f]+)$', text, re.M | re.I)
    require(len(oldmask) == 1, f'{directory.name}: missing original packed mask')
    primask = int(oldmask[0], 16) & 255
    guard_after = 168 if kind == 'read' else 164
    require(struct.unpack_from('<I', running, 124)[0] == 0xc0def00d and
            struct.unpack_from('<I', running, guard_after)[0] == 0x0df0dec0,
            f'{directory.name}: caller memory guards differ')
    sr = None
    if kind == 'read':
        require(output[:2] == [primask, 1] and all(output[i] == 0 for i in (2,3,4,5,6)) and
                output[7] == 0x52454144 and output[8] & 0xffffff == 0x186585,
                f'{directory.name}: JEDEC/read returns invalid')
        sr = [(output[8] >> 24) & 255, output[9] & 255]
        require(not sr[0] & 3, f'{directory.name}: WIP/WEL not clear')
        logged = re.findall(r'^JEDEC856518 SR1 0x([0-9a-f]{2}) SR2 0x([0-9a-f]{2})$', text, re.M | re.I)
        require(len(logged) == 1 and sr == [int(v,16) for v in logged[0]], f'{directory.name}: status log/binary differ')
    else:
        require(output[5:] == [primask, 1, 0, 0x43414c4c], f'{directory.name}: native return/mask invalid')
    elapsed = re.findall(r'^stop_pc 0x[0-9a-f]+ stop_xpsr 0x[0-9a-f]+ elapsed_ms (\d+)$', text, re.M | re.I)
    require(len(elapsed) == 1, f'{directory.name}: missing stop record')
    return {'directory': directory.name, 'stage': stage, 'kind': kind,
            'elapsed_ms': int(elapsed[0]), 'status_bytes': sr,
            'scratch_original_and_restored_sha256': digest(scratch_before),
            'initialized_8B_sha256': digest(config_before),
            'binary_output_and_guards_verified': True,
            'core_SPI_HAL_restored': 'asserted by completed runner readback gates; scratch/config independently byte-compared',
            'log_sha256': digest(log_path.read_bytes())}


def inspect_capture(value, mode, outer_value):
    if value is None:
        return pending(f'No {mode} capture supplied')
    capture = resolve(value)
    report = {'status': 'failed', 'capture': display(capture), 'mode': mode}
    try:
        text = read_text(capture / 'result.txt')
        require(exact_line(text, f'scope mode={mode}; fixedsectors150000/824000 only; no automatic retry/resume'), 'Wrong operation scope')
        require(exact_line(text, 'flash_mutation_possible 1 complete 1 safe_to_resume 1') and
                exact_line(text, 'hook_data_protection_context_verified 1; leaveBOOT halted; outer owns finalGLOBAL'),
                'Operation incomplete or failed')
        require('operation_error' not in text, 'Operation reported an error')
        sectors = {}
        for label, offset in [('entry',0x150000),('payload',0x824000)]:
            original = read_blob(OUT / f'boot-hook-original-sector-{offset:x}.bin', 4096)
            patched = read_blob(OUT / f'boot-hook-patched-sector-{offset:x}.bin', 4096)
            before = read_blob(capture / f'sector-{label}-before.bin', 4096)
            after = read_blob(capture / f'sector-{label}-verified.bin', 4096)
            require(before == original if mode == 'install' else before in (original,patched), f'{label}: inadmissible before baseline')
            expected = patched if mode == 'install' else original
            require(after == expected, f'{label}: whole4K after differs from exact {mode} bytes')
            sectors[label] = {'bytes':4096, 'before_sha256':digest(before), 'after_sha256':digest(after),
                              'after_expected_state':'patched' if mode == 'install' else 'original', 'exact_match':True}
        logs = {d.name: inspect_stage(d) for d in capture.iterdir() if d.is_dir()}
        require('status-before' in logs and 'status-restored' in logs, 'Missing initial/final native status')
        original_sr = logs['status-before']['status_bytes']
        require(original_sr is not None, 'Initial status is not native read evidence')
        original_composite = original_sr[0] | (original_sr[1] << 8)
        bp = original_composite & 0x407c
        expected_names = {'status-before','status-unprotected','status-final-data','status-restored',
                          'invalidate-entry-i','invalidate-entry-d','invalidate-payload-i','invalidate-payload-d'}
        if bp:
            expected_names |= {'unprotect','reprotect'}
        if mode == 'install':
            expected_names |= {'install-payload-page','status-payload','install-entry-erase'}
            expected_names |= {f'install-entry-page-{page}' for page in range(16)}
            require(text.index('whole_sector_verified payload') < text.index('whole_sector_verified entry'), 'Install verification order wrong')
        else:
            expected_names |= {'restore-entry-erase','status-entry-restored','restore-payload-erase'}
            expected_names |= {f'restore-entry-page-{page}' for page in range(16)}
            expected_names |= {f'restore-payload-page-{page}' for page in range(4)}
            require(text.index('whole_sector_verified entry') < text.index('whole_sector_verified payload'), 'Restore verification order wrong')
        require(set(logs) == expected_names, f'Native stage coverage differs: missing={sorted(expected_names-set(logs))}; extra={sorted(set(logs)-expected_names)}')
        for name, stage in logs.items():
            if name.startswith('status-'):
                require(stage['stage'] == 'read-status' and stage['kind'] == 'read', f'{name}: wrong read payload')
                sr = stage['status_bytes']
                expected = original_composite if name in ('status-before','status-restored') else original_composite & ~0x407c
                require(((sr[0]|(sr[1]<<8)) & 0xfffc) == (expected & 0xfffc), f'{name}: BP/QE/stable status mismatch')
            else:
                require(stage['stage'] == name and stage['kind'] == 'onecall', f'{name}: wrong fixed stage')
        report.update(status='passed', whole_sectors=sectors, native_calls=list(logs.values()),
                      native_call_count=len(logs), SR1_SR2_before=[hex(v) for v in original_sr],
                      BP_mask='0x407c', BP_before_after=hex(bp), BP_QE_and_all_stable_status_restored=True,
                      all_borrowed_SRAM_and_context_restored=True,
                      outer=inspect_outer(resolve(outer_value) if outer_value else None))
    except (OSError,ValueError,KeyError,IndexError,struct.error) as error:
        report.update(status='failed', reason=str(error))
    return report


def inspect_marker(value, state, cold_confirmed=False, cold=False):
    if value is None:
        return pending('No cold-start marker log supplied' if cold else 'No fresh marker log supplied')
    path = resolve(value)
    report = {'status':'failed','log':display(path),'expected_firmware_state':state}
    try:
        text = read_text(path)
        markers = list(re.finditer(r'^FIRST_DCRDR 0x([0-9a-f]{8})$', text, re.M | re.I))
        require(len(markers) == 1, 'Require exactly one FIRST_DCRDR record')
        marker = int(markers[0].group(1),16)
        require(marker == (MARKER if state == 'patched' else 0), 'Fresh first DCRDR differs from expected marker')
        labels = ['HOOK_MCU_DHCSR_DEMCR','HOOK_MCU_FAULT','HOOK_ENTRY_BYTES','HOOK_PAYLOAD_BYTES']
        for label in labels:
            require(label in text and markers[0].start() < text.index(label), f'FIRST_DCRDR was not before {label}')
        dhcsr = re.findall(r'^HOOK_MCU_DHCSR_DEMCR 0xe000edf0: ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+)\s*$', text, re.M | re.I)
        require(len(dhcsr) == 1, 'Missing four-word fresh SCS metadata')
        core = [int(v,16) for v in dhcsr[0]]
        # S_RESET_ST(bit25) is read-clear historical reset evidence on this fresh
        # post-GLOBAL/power-cycle read, not an active reset/fault. S_SLEEP is OK.
        require(not core[0] & 0x000a000f and core[2] == marker and core[3] == 0x01110000,
                'MCU halted/lockup/active debug controls or repeated DCRDR mismatch')
        faults = re.findall(r'^HOOK_MCU_FAULT 0xe000ed28: ([0-9a-f]+) ([0-9a-f]+)\s*$', text, re.M | re.I)
        require(len(faults) == 1 and all(int(v,16) == 0 for v in faults[0]), 'Fresh MCU fault flags nonzero/missing')
        entry = bytes(numbers(text,'HOOK_ENTRY_BYTES',4))
        payload = bytes(numbers(text,'HOOK_PAYLOAD_BYTES',32))
        entry_expected = read_blob(OUT/f'boot-hook-{state}-sector-150000.bin',4096)[0x56:0x5a]
        payload_expected = read_blob(OUT/f'boot-hook-{state}-sector-824000.bin',4096)[0x400:0x420]
        require(entry == entry_expected and payload == payload_expected, 'Fresh marker boot bytes differ')
        report.update(status='passed', FIRST_DCRDR=hex(marker), first_before_other_metadata=True,
                      MCU_running_default_debug_and_no_faults=True, entry_payload_bytes_exact=True,
                      DHCSR=hex(core[0]), historical_reset_seen=bool(core[0]&0x02000000),
                      sleep_seen=bool(core[0]&0x00040000),
                      sha256=digest(path.read_bytes()))
        if cold:
            report['cold_user_confirmed'] = bool(cold_confirmed)
            if not cold_confirmed:
                report.update(status='pending', reason='Marker observed; physical power cycle/user observations not confirmed')
    except (OSError,ValueError,KeyError,IndexError) as error:
        report.update(status='failed',reason=str(error))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install-capture','install-outer-log','restore-capture','restore-outer-log',
                 'warm-log','cold-log','restore-marker-log'):
        parser.add_argument('--'+name)
    parser.add_argument('--cold-user-confirmed', action='store_true',
                        help='Explicit root assertion that user confirmed physical power cycle and observed normal panel/Mi Home/control')
    parser.add_argument('--cold-user-observation', default=None)
    parser.add_argument('--user-observation-json', default=None,
                        help='Read existing user physical-cycle and post-restore observation provenance')
    parser.add_argument('--output', default='analysis/persistence/boot-hook-hardware-result.json')
    args = parser.parse_args(argv)
    bundle = {name:{'expected_sha256':expected,'actual_sha256':digest((ROOT/name).read_bytes())} for name,expected in FROZEN.items()}
    bundle_ok = all(v['expected_sha256']==v['actual_sha256'] for v in bundle.values())
    report = {'reader_only':True,'hardware_actions_performed_by_recorder':0,'firmware':'1.50.10',
              'executed_by':'root; this program only parses saved artifacts','frozen_bundle':bundle,
              'frozen_bundle_exact':bundle_ok,
              'install':inspect_capture(args.install_capture,'install',args.install_outer_log),
              'restore':inspect_capture(args.restore_capture,'restore',args.restore_outer_log),
              'warm_boot':inspect_marker(args.warm_log,'patched'),
              'cold_boot':inspect_marker(args.cold_log,'patched',args.cold_user_confirmed,True),
              'restore_boot':inspect_marker(args.restore_marker_log,'original'),
              'cold_user_observation':args.cold_user_observation,
              'limits':['Marker identifies execution of reviewed startup hook, not arbitrary custom firmware correctness.',
                        'Physical power loss and panel/Mi Home/control observations require explicit user provenance.',
                        'Saved runner logs assert core/HAL/controller readback; SRAM/config/output are independently byte-checked.',
                        'Parser never obtains fresh device state; callers supply logs from separate first-read MEM-AP sessions.']}
    report['durable_hook_validation'] = 'passed' if bundle_ok and report['install']['status']=='passed' and report['cold_boot']['status']=='passed' else 'pending'
    failed = not bundle_ok or any(report[key]['status']=='failed' for key in ('install','restore','warm_boot','cold_boot','restore_boot'))
    report['user_observations'] = pending('No user observation JSON supplied')
    if args.user_observation_json:
        observation_path = resolve(args.user_observation_json)
        try:
            observations = json.loads(read_text(observation_path))
            require(isinstance(observations,dict), 'User observations must be an object')
            if args.cold_user_confirmed:
                require(observations.get('cold_power_cycle_and_observations_confirmed_by_user') is True,
                        'Cold user confirmation flag conflicts with supplied user observation evidence')
            report['user_observations'] = {'status':'recorded','source':display(observation_path),
                                          'sha256':digest(observation_path.read_bytes()),'observations':observations}
        except (OSError,ValueError) as error:
            report['user_observations'] = {'status':'failed','reason':str(error)}
            failed = True
    post_restore_user_confirmed = report['user_observations'].get('observations',{}).get(
        'post_restore_user_observations',{}).get('normal_operation_confirmed_by_user') is True
    report['complete_experiment_validation'] = 'passed' if (not failed and
        report['durable_hook_validation']=='passed' and report['restore']['status']=='passed' and
        report['restore_boot']['status']=='passed' and post_restore_user_confirmed) else 'pending'
    report['all_supplied_evidence_passed'] = not failed
    output = resolve(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'report':display(output),'install':report['install']['status'],'restore':report['restore']['status'],
                      'warm':report['warm_boot']['status'],'cold':report['cold_boot']['status'],
                      'durable_hook_validation':report['durable_hook_validation'],'failed':failed},ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
