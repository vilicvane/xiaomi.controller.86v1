/** Sequential exact-release operations. Never retries writes, native calls or resets. */
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(process.cwd());
const hardware = join(root, 'build/hardware');
const lock = join(hardware, 'owner.lock');
const uncertain = join(hardware, 'NEEDS_INSPECTION');
const sha = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const tclPath = (path: string) => {
  if (/[{}\r\n]/.test(path)) throw new Error('Path cannot be represented safely in Tcl');
  return '{' + path.replaceAll('\\', '/') + '}';
};

async function openocd(workspace: string, cfg: string, capture: string, label: string) {
  const executable = join(workspace, 'tools/xpack-openocd-0.12.0-7/bin/openocd.exe');
  const log = join(capture, label + '.log');
  const child = spawn(executable, ['-s', 'diagnostics', '-f', cfg, '-l', log.replaceAll('\\', '/')],
    { cwd: workspace, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const chunks: Buffer[] = [];
  child.stdout.on('data', data => chunks.push(data));
  child.stderr.on('data', data => chunks.push(data));
  const status = await new Promise<number | null>((accept, reject) => {
    child.on('error', reject);
    child.on('close', accept);
  });
  writeFileSync(join(capture, label + '-console.txt'), Buffer.concat(chunks));
  if (status !== 0) throw new Error(`${label} failed (${status}); inspect ${log}. No automatic retry or reset.`);
}

async function readState(workspace: string, capture: string, label: string) {
  const cfg = join(capture, label + '.cfg');
  const commands = ['source [find swd-memory.cfg]', 'adapter speed 1000', 'init'];
  for (const page of ['92b000', 'ccd000', '95a000', '92d000'])
    commands.push(`dump_image ${tclPath(join(capture, label + '-' + page + '.bin'))} 0x28${page} 4096`);
  commands.push('set panel_context [lindex [read_memory 0x384fc864 32 1] 0]',
    'if {$panel_context>=0x38000000 && $panel_context<0x39000000 && ($panel_context&3)==0} {',
    `dump_image ${tclPath(join(capture, label + '-context.bin'))} $panel_context 224`, '}',
    'echo "PANEL_CONTEXT $panel_context"',
    'echo "PANEL_SCREEN [read_memory 0x384ea638 32 1]"',
    'echo "PANEL_TIMER [read_memory 0x384fce54 32 2]"', 'shutdown');
  writeFileSync(cfg, commands.join('\n') + '\n', { flag: 'wx' });
  await openocd(workspace, cfg, capture, label);
}

function pageHashes(capture: string, label: string) {
  return Object.fromEntries(['92b000', 'ccd000', '95a000', '92d000'].map(page => {
    const bytes = readFileSync(join(capture, label + '-' + page + '.bin'));
    if (bytes.length !== 4096) throw new Error('Incomplete page capture');
    return [parseInt(page, 16), sha(bytes)];
  }));
}

function closedOuter(text: string, mode: string) {
  if (!/^native_app_safe_to_resume 1$/m.test(text) || !/^native_app_complete 1$/m.test(text) ||
      !/^cleanup_global_transport_error 0$/m.test(text) || !/^cleanup_dispatch_complete 1$/m.test(text) ||
      !/^cleanup_global_requested 1$/m.test(text) ||
      !new RegExp(`^phase (native_app_${mode}_verified|cleanup_global_requested)$`, 'm').test(text) ||
      /^(test_error|cleanup_error) /m.test(text))
    throw new Error('Native operation did not close completely; preserve stopped state and captures.');
}

async function main() {
  const [mode, name] = process.argv.slice(2);
  if (!['check', 'install', 'restore'].includes(mode) || !name || process.argv.length !== 4)
    throw new Error('From the repository root: node firmware/tools/hardware.ts check|install|restore RELEASE');
  if (!/^[a-z0-9][a-z0-9-]{0,63}$/.test(name)) throw new Error('Invalid release name');
  if (process.platform !== 'win32') throw new Error('Hardware execution uses the frozen Windows OpenOCD runtime');
  const declared = JSON.parse(readFileSync(join(root, 'build/releases', name, 'candidate.json'), 'utf8'));
  const executor = readFileSync(fileURLToPath(import.meta.url));
  const verifier = readFileSync(new URL('./release.ts', import.meta.url));
  if (sha(executor) !== declared.inputs?.['snapshot/firmware/tools/hardware.ts'] ||
      sha(verifier) !== declared.inputs?.['snapshot/firmware/tools/release.ts'])
    throw new Error('Executor/verifier differs from this release; run its frozen snapshot executor from the repository root');
  const { verifyRelease } = await import(new URL('./release.ts', import.meta.url).href);
  const verified = verifyRelease(root, name);
  if (!verified.frozen) throw new Error('Independent reviews and freeze are required before hardware access');
  mkdirSync(hardware, { recursive: true });
  writeFileSync(lock, `${process.pid}\n`, { flag: 'wx' });
  const capture = join(hardware, mode + '-' + new Date().toISOString().replaceAll(/[:.]/g, '-') + '-' + process.pid);
  mkdirSync(capture);
  const workspace = join(verified.directory, 'workspace');
  try {
    if (mode !== 'check' && existsSync(uncertain))
      throw new Error('A previous operation needs inspection. Read-only check remains available; do not blindly retry.');
    await readState(workspace, capture, 'before');
    const before = pageHashes(capture, 'before');
    const matches = (state: 'original' | 'patched') => Object.values(verified.candidate.pages)
      .every(page => before[page.offset] === page[state + 'Sha256']);
    const original = matches('original'), patched = matches('patched');
    const summary = { release: name, candidateSha256: verified.candidateSha256, mode,
      before: { original, patched, pages: before }, hardwareMutationPossible: false, passed: mode === 'check',
      coldPowerCycle: 'skipped_by_user_request', after: null as object | null };
    writeFileSync(join(capture, 'result.json'), JSON.stringify(summary, null, 2) + '\n');
    if (mode === 'check') {
      console.log(JSON.stringify({ capture, original, patched, hardwareMutation: false }));
      return;
    }
    if (mode === 'install' ? !original : !original && !patched)
      throw new Error('Live four-page set is unknown or mixed. No reset, native call or Flash write attempted.');
    const operationCfg = join(capture, 'operation.cfg');
    const outer = join(capture, 'outer-result.txt');
    writeFileSync(operationCfg, [
      'set panel_release_verified 1', `set boot_result_path ${tclPath(outer)}`,
      `source ${tclPath(join(workspace, 'diagnostics/mcu-panel-maintained-' + mode + '-session.cfg'))}`,
    ].join('\n') + '\n', { flag: 'wx' });
    writeFileSync(uncertain, `Inspect before repeating any mutation: ${capture}\n`, { flag: 'wx' });
    summary.hardwareMutationPossible = true;
    writeFileSync(join(capture, 'result.json'), JSON.stringify(summary, null, 2) + '\n');
    console.log(`Executing ${mode}: four NOR pages 92b000/92d000/95a000/ccd000; one warm reboot. Capture: ${capture}`);
    await openocd(workspace, operationCfg, capture, 'operation');
    closedOuter(readFileSync(outer, 'utf8'), mode);
    /* A completed GLOBAL may briefly lose DP. Retry only a fresh read-only process. */
    let afterLabel = '';
    for (let attempt = 1; attempt <= 4; attempt++) {
      const label = 'after-' + attempt;
      try { await readState(workspace, capture, label); afterLabel = label; break; }
      catch (error) {
        const log = join(capture, label + '.log');
        if (attempt === 4 || !existsSync(log) ||
            !/cannot read IDR|Failed to read DPIDR|cannot read DPIDR/i.test(readFileSync(log, 'utf8'))) throw error;
        await new Promise(accept => setTimeout(accept, 1000));
      }
    }
    const after = pageHashes(capture, afterLabel);
    const state = mode === 'install' ? 'patchedSha256' : 'originalSha256';
    if (!Object.values(verified.candidate.pages).every(page => after[page.offset] === page[state]))
      throw new Error('Warm readback differs from exact release pages; inspect without replaying the writer.');
    summary.passed = true; summary.after = { pages: after };
    writeFileSync(join(capture, 'result.json'), JSON.stringify(summary, null, 2) + '\n');
    unlinkSync(uncertain);
    console.log(JSON.stringify({ capture, passed: true, fullPages: 4, warmReadback: true }));
  } finally { unlinkSync(lock); }
}

await main();
