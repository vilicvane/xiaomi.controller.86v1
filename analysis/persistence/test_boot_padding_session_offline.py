"""Verify padding failures cannot trigger outer reset or stale-context resume."""
from pathlib import Path
import subprocess
import json

ROOT=Path(__file__).resolve().parents[2]
template=(ROOT/'analysis/persistence/test_boot_read_session_offline.py').read_text()
template=template[:template.index('\nreports = []')].replace(
    'diagnostics/mcu-boot-native-read-session.cfg','diagnostics/mcu-boot-padding-session.cfg')
ns={'__file__':str(ROOT/'analysis/persistence/test_boot_read_session_offline.py')}
exec(compile(template,'<padding-outer-model>','exec'),ns)
harness=ns['harness'].replace('boot-nor-read-runner.cfg boot-watchdog-stop.cfg}',
    'boot-nor-read-runner.cfg boot-watchdog-stop.cfg boot-nor-padding-runner.cfg}')
harness=harness.replace('swd-memory.cfg boot-nor-read-runner.cfg}',
    'swd-memory.cfg boot-nor-read-runner.cfg boot-nor-padding-runner.cfg}')
harness=harness.replace('proc bnor_run_read_probe', '''proc bnp_run_padding_test {dir remove_command} {
    if {!$::bnor_safe_to_resume || $::sim_wdt_ctrl != 0 || $::sim_mode != "boot_hit"} { error "Invalid padding entry" }
    if {$::sim_case == "padding_failure"} {
        set ::bnp_safe_to_resume 0
        error "Simulated unclosed padding caller"
    }
    set ::bnp_safe_to_resume 1
    return 1
}
proc bnor_run_read_probe''')
out=ROOT/'analysis/persistence/offline-padding-session'
out.mkdir(exist_ok=True)
reports=[]
for case in ('padding_success','padding_failure'):
    result=out/f'{case}-result.txt'
    state=out/f'{case}-state.txt'
    cfg=out/f'{case}-harness.cfg'
    cfg.write_text(f'set sim_case {{{case}}}\nset sim_cfg {{{ns["ns"]["CFG"].as_posix()}}}\nset sim_summary {{{state.as_posix()}}}\nset boot_result_path {{{result.as_posix()}}}\n'+harness)
    run=subprocess.run([str(ns['ns']['EXE']),'-f',str(cfg)],cwd=ROOT,capture_output=True,text=True,timeout=10)
    (out/f'{case}-host.txt').write_text(run.stdout+run.stderr)
    values=dict(line.split(' ',1) for line in state.read_text().splitlines())
    failed=case=='padding_failure'
    assert int(values['status'])==int(failed),values
    assert int(values['global_count'])==int(not failed),values
    if failed:
        assert values['mode']=='boot_hit' and int(values['controls'])==3,values
    reports.append({'case':case,'passed':True,'failed_padding_suppresses_GLOBAL':failed})
(out/'summary.json').write_text(json.dumps({'offline_only':True,'cases':reports},indent=2)+'\n')
print('Padding outer success/failure cleanup verified; no hardware')
