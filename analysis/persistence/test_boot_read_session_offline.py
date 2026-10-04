"""Verify composed outer reset cleanup when the native reader fails/succeeds."""
from pathlib import Path
import json
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
template = (ROOT / "analysis/persistence/test_recovery_mcucpu_offline.py").read_text()
template = template[:template.index('\nCASES = {')].replace(
    'diagnostics/mcu-recovery-mcucpu-bootbreak-probe.cfg',
    'diagnostics/mcu-boot-native-read-session.cfg')
ns = {"__file__": str(ROOT / "analysis/persistence/test_recovery_mcucpu_offline.py")}
exec(compile(template, "<outer-session-model>", "exec"), ns)
harness = ns['HARNESS'].replace(
    'proc find {path} { if {$path != "swd-memory.cfg"} { error "Forbidden find" }; return $path }',
    'proc find {path} { if {$path ni {swd-memory.cfg boot-nor-read-runner.cfg boot-watchdog-stop.cfg}} { error "Forbidden find" }; return $path }')
harness = harness.replace(
    'proc source {path} { if {$path != "swd-memory.cfg"} { error "Forbidden source" } }',
    '''proc source {path} {
    if {$path == "boot-watchdog-stop.cfg"} { sim_source diagnostics/boot-watchdog-stop.cfg; return }
    if {$path ni {swd-memory.cfg boot-nor-read-runner.cfg}} { error "Forbidden source" }
}
proc bnor_run_read_probe {dir policy remove_command} {
    if {$policy != "held-reset-cmu-verified" || $::sim_mode != "boot_hit"} { error "Invalid composed entry" }
    eval $remove_command
    if {$::sim_wdt_ctrl != 0 || $::sim_wdt_flag != 0 || $::sim_wdt_lock != 1} { error "Reader ran before verified watchdog stop" }
    if {$::sim_case == "native_failure"} {
        set ::bnor_safe_to_resume 0
        error "Simulated unclosed reader, retain halt"
    }
    set ::bnor_safe_to_resume 1
    return 1
}''')
out = ROOT / 'analysis/persistence/offline-native-read-session'
seed = 'set sim_wdt_ctrl 3\nset sim_wdt_flag 0\nset sim_wdt_lock 1\n'
image = (ROOT / 'backups/mi-panel-flash-16m-1.50.10-20261004.bin').read_bytes()
for addr in [0x0c012ff8, 0x0c012ffc] + list(range(0x0c013040,0x0c013074,4)):
    seed += f'set sim_boot_words({addr}) {struct.unpack_from("<I",image,addr-0x0c000000)[0]}\n'
harness = harness.replace('proc read_memory {address width count} {',seed+'proc read_memory {address width count} {')
harness = harness.replace('        0xe000ed00 { set value 0x630f1321 }', '''        0x0c012ff8 { set value 0x40082000 }
        0x0c012ffc { set value 0x1acce551 }
        0x40082008 { set value $::sim_wdt_ctrl }
        0x40082c00 { set value $::sim_wdt_lock }
        0x2000b010 { set value $::sim_wdt_flag }
        0x40082000 - 0x40082004 - 0x40082010 - 0x40082014 - 0x40080000 - 0x40080088 - 0x4000003c { set value 0 }
        0xe000ed00 { set value 0x630f1321 }''')
harness = harness.replace('        0xe0002000 {\n', '''        0x40082c00 { set ::sim_wdt_lock $value }
        0x40082008 {
            if {$::sim_wdt_lock != 0x1acce551 || $value != 0} { error "Unexpected watchdog control write" }
            set ::sim_wdt_ctrl 0
            if {$::sim_case == "watchdog_commit_error"} { error "Posted watchdog stop committed before AP error" }
        }
        0x2000b010 { set ::sim_wdt_flag $value }
        0xe0002000 {
''')
out.mkdir(exist_ok=True)
reports = []
for case in ('native_success', 'native_failure', 'watchdog_commit_error'):
    result = out / f'{case}-result.txt'
    state = out / f'{case}-state.txt'
    cfg = out / f'{case}-harness.cfg'
    cfg.write_text(f'set sim_case {{{case}}}\nset sim_cfg {{{ns["CFG"].as_posix()}}}\nset sim_summary {{{state.as_posix()}}}\nset boot_result_path {{{result.as_posix()}}}\n' + harness)
    run = subprocess.run([str(ns['EXE']), '-f', str(cfg)], cwd=ROOT,
        capture_output=True, text=True, timeout=10)
    (out / f'{case}-host.txt').write_text(run.stdout+run.stderr)
    values = dict(line.split(' ',1) for line in state.read_text().splitlines())
    evidence = dict(line.split(' ',1) for line in result.read_text().splitlines() if ' ' in line)
    failed = case != 'native_success'
    assert int(values['status']) == int(failed), values
    assert int(values['global_count']) == int(case != 'native_failure'), values
    assert int(evidence['break_hit']) == 1 and evidence['resumed'] == '0', evidence
    if case == 'native_failure':
        assert values['mode'] == 'boot_hit' and int(values['controls']) == 3
        assert evidence['cleanup_retained_halt'].startswith('native_reader_failed')
        assert not values['writes'].split()[-1].startswith('0x400800a4:0x00000200')
    reports.append({'case':case, 'passed':True, 'global_dispatch':case != 'native_failure',
        'retained_halt_on_failure':case == 'native_failure'})
(out / 'summary.json').write_text(json.dumps({'offline_only':True,'cases':reports},indent=2)+'\n')
print('Composed outer cleanup passed success/failure models; no target access')
