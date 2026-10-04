"""Validate hook failure suppression and clearing stale DCRDR before boot."""
from pathlib import Path
import subprocess
import json

ROOT=Path(__file__).resolve().parents[2]
template=(ROOT/'analysis/persistence/test_boot_read_session_offline.py').read_text()
template=template[:template.index('\nreports = []')].replace(
    'diagnostics/mcu-boot-native-read-session.cfg','diagnostics/mcu-boot-hook-install-session.cfg')
ns={'__file__':str(ROOT/'analysis/persistence/test_boot_read_session_offline.py')}
exec(compile(template,'<hook-outer-model>','exec'),ns)
harness=ns['harness'].replace('boot-nor-read-runner.cfg boot-watchdog-stop.cfg}',
    'boot-nor-read-runner.cfg boot-watchdog-stop.cfg boot-nor-hook-runner.cfg}')
harness=harness.replace('swd-memory.cfg boot-nor-read-runner.cfg}',
    'swd-memory.cfg boot-nor-read-runner.cfg boot-nor-hook-runner.cfg}')
harness=harness.replace('proc bnor_run_read_probe', '''proc bnh_run_hook {dir mode remove_command} {
    if {$mode != "install" || !$::bnor_safe_to_resume || $::sim_wdt_ctrl != 0 || $::sim_mode != "boot_hit"} { error "Invalid hook entry" }
    if {$::sim_case == "hook_failure"} {
        set ::bnh_safe_to_resume 0
        error "Simulated unclosed hook caller"
    }
    set ::bnh_safe_to_resume 1
    set ::sim_dcrdr 0x4b4f4f48
    return 1
}
proc bnor_run_read_probe''')
out=ROOT/'analysis/persistence/offline-hook-session'
out.mkdir(exist_ok=True)
reports=[]
for case in ('hook_success','hook_failure'):
    result=out/f'{case}-result.txt'
    state=out/f'{case}-state.txt'
    cfg=out/f'{case}-harness.cfg'
    cfg.write_text(f'set sim_case {{{case}}}\nset sim_cfg {{{ns["ns"]["CFG"].as_posix()}}}\nset sim_summary {{{state.as_posix()}}}\nset boot_result_path {{{result.as_posix()}}}\n'+harness)
    run=subprocess.run([str(ns['ns']['EXE']),'-f',str(cfg)],cwd=ROOT,capture_output=True,text=True,timeout=10)
    (out/f'{case}-host.txt').write_text(run.stdout+run.stderr)
    values=dict(line.split(' ',1) for line in state.read_text().splitlines())
    failed=case=='hook_failure'
    assert int(values['status'])==int(failed),values
    assert int(values['global_count'])==int(not failed),values
    if failed:
        assert values['mode']=='boot_hit' and int(values['controls'])==3,values
    else:
        writes=values['writes'].split()
        assert writes[-2:] == ['0xe000edf8:0x00000000','0x400800a4:0x00000200'],writes
        assert int(values['dcrdr'])==0,values
    reports.append({'case':case,'passed':True,'failed_hook_suppresses_GLOBAL':failed,
        'stale_marker_cleared_before_GLOBAL':not failed})
(out/'summary.json').write_text(json.dumps({'offline_only':True,'cases':reports},indent=2)+'\n')
print('Hook outer cleanup/marker-clear verified; no hardware')
