import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { basename, resolve, join } from 'node:path';

const root = resolve(import.meta.dirname, '../..');
const out = join(root, 'build/panel');
const hash = (path: string) => createHash('sha256').update(readFileSync(path)).digest('hex');
const sourcePaths = ['firmware/build.sh', 'firmware/tools/build-record.ts', 'build/panel/config.h'];
function collect(directory: string) {
  for (const item of readdirSync(join(root, directory), { withFileTypes: true })) {
    const path = `${directory}/${item.name}`;
    if (item.isDirectory()) collect(path);
    else sourcePaths.push(path);
  }
}
for (const directory of ['firmware/src', 'firmware/include', 'firmware/ports']) collect(directory);
const sources = Object.fromEntries(sourcePaths.sort().map(path => [path, hash(join(root, path))]));
const recordPath = join(out, 'build-inputs.json');
const units = ['ui', 'http', 'http-parser', 'settings', 'image-codec', 'image-store'];
function headerHashes(makefiles: string[]) {
  const dependencies = new Set<string>();
  for (const makefile of makefiles) {
    const make = makefile.replace(/\\\r?\n/g, ' ');
    const names = make.slice(make.indexOf(':') + 1).match(/(?:\\.|[^\s])+/g) ?? [];
    for (const name of names) dependencies.add(resolve(root, name.replace(/\\(.)/g, '$1')));
  }
  return Object.fromEntries([...dependencies].sort()
    .filter(path => !sourcePaths.some(source => resolve(root, source) === path))
    .map(path => [path, hash(path)]));
}
if (process.argv[2] === 'begin') {
  const tools = ['clang-18', 'llvm-objcopy-18', 'llvm-nm-18', 'tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld'];
  const toolHashes = Object.fromEntries(tools.map(tool => {
    const path = tool.includes('/') ? join(root, tool)
      : execFileSync('sh', ['-c', 'command -v "$1"', 'sh', tool], { encoding: 'utf8' }).trim();
    return [tool, { path, sha256: hash(path) }];
  }));
  const headers = headerHashes(units.map(unit => execFileSync('clang-18', [
    '--target=arm-none-eabi', '-mcpu=cortex-a7', '-mthumb', '-ffreestanding',
    '-I', 'firmware/include', '-include', 'build/panel/config.h', '-M', `firmware/src/${unit}.c`,
  ], { cwd: root, encoding: 'utf8' })));
  writeFileSync(recordPath, JSON.stringify({ completed: false, sources, tools: toolHashes, headers }, null, 2) + '\n');
} else if (process.argv[2] === 'complete') {
  const record = JSON.parse(readFileSync(recordPath, 'utf8'));
  if (JSON.stringify(record.sources) !== JSON.stringify(sources))
    throw new Error('Build inputs changed during compilation');
  for (const tool of Object.values(record.tools) as { path: string; sha256: string }[]) {
    if (hash(tool.path) !== tool.sha256) throw new Error('Build tool changed during compilation');
  }
  const headers = headerHashes(units.map(unit => readFileSync(join(out, unit + '.d'), 'utf8')));
  if (JSON.stringify(record.headers) !== JSON.stringify(headers))
    throw new Error('Compiler headers changed during compilation');
  mkdirSync(join(out, 'compiler-headers'), { recursive: true });
  record.headerCopies = {};
  for (const [path, expected] of Object.entries(headers)) {
    const relative = 'build/panel/compiler-headers/' + basename(path);
    if (record.headerCopies[relative]) throw new Error('Compiler header basenames collide');
    const bytes = readFileSync(path);
    if (createHash('sha256').update(bytes).digest('hex') !== expected)
      throw new Error('Compiler header changed while snapshotting');
    writeFileSync(join(root, relative), bytes);
    record.headerCopies[relative] = expected;
  }
  record.artifacts = Object.fromEntries(['panel.elf', 'panel.bin', 'panel-aux.bin', 'panel-net.bin', 'panel-codec.bin', 'panel-store.bin', 'panel.map']
    .map(name => [`build/panel/${name}`, hash(join(out, name))]));
  record.completed = true;
  writeFileSync(recordPath, JSON.stringify(record, null, 2) + '\n');
} else {
  throw new Error('Expected begin or complete');
}
