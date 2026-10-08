import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { checkEvidence, checkOwnership, cloneMock, cloneWriter, compilerHeaderCopies, freezeRelease, linkedSegments, names, NET_MOCK_CASES, CODEC_MOCK_CASES, STORE_MOCK_CASES, WRITER_MOCK_CASES, patchPages,
  prepareRelease, sha256, verifyRelease } from './release.ts';

function payload(bytes = 512) {
  const main = Buffer.alloc(bytes, 0x11);
  Buffer.from('262040427047', 'hex').copy(main);
  Buffer.from('00207047', 'hex').copy(main, 8);
  Buffer.from('00f000b8', 'hex').copy(main, 0x1ec);
  return main;
}
function pages() {
  const result = { code: Buffer.alloc(4096, 0xa3), entry: Buffer.alloc(4096, 0xb4), aux: Buffer.alloc(4096, 0xc5), net: Buffer.alloc(4096, 0xd6), codec: Buffer.alloc(4096, 0xe7), store: Buffer.alloc(4096, 0xf8) };
  result.entry.writeUInt32LE(0x3804cf3d, 0xc3c);
  for (const [offset, word] of [[0xd68, 0x38047099], [0xd7c, 0x38047849], [0xca0, 0x38047b3d]]) result.entry.writeUInt32LE(word, offset);
  result.entry.writeUInt32LE(0x38051fd1, 0xe6c);
  return result;
}
function elf(main: Buffer, aux: Buffer, net = Buffer.alloc(20, 0x22), codec = Buffer.alloc(20, 0x33), store = Buffer.alloc(20, 0x44)) {
  const sectionCount = 6, table = 52, start = table + sectionCount * 40;
  const raw = Buffer.alloc(start + main.length + aux.length + net.length + codec.length + store.length);
  Buffer.from([127, 69, 76, 70, 1, 1, 1]).copy(raw);
  raw.writeUInt16LE(40, 18); raw.writeUInt32LE(0x3804b2f5, 24);
  raw.writeUInt32LE(table, 32); raw.writeUInt16LE(40, 46); raw.writeUInt16LE(sectionCount, 48);
  for (const [index, address, offset, length] of [
    [1, 0x3804b108, start, main.length], [2, 0x3807a764, start + main.length, aux.length],
    [3, 0x3804d000, start + main.length + aux.length, net.length],
    [4, 0x38047098, start + main.length + aux.length + net.length, codec.length],
    [5, 0x38052000, start + main.length + aux.length + net.length + codec.length, store.length],
  ]) {
    const header = table + index * 40;
    raw.writeUInt32LE(1, header + 4); raw.writeUInt32LE(6, header + 8);
    raw.writeUInt32LE(address, header + 12); raw.writeUInt32LE(offset, header + 16); raw.writeUInt32LE(length, header + 20);
  }
  main.copy(raw, start); aux.copy(raw, start + main.length); net.copy(raw, start + main.length + aux.length);
  codec.copy(raw, start + main.length + aux.length + net.length);
  store.copy(raw, start + main.length + aux.length + net.length + codec.length);
  return raw;
}

test('six-page patch disables only its five diagnostics and preserves all unrelated bytes', () => {
  const original = pages(), main = payload(), aux = Buffer.alloc(19, 0xee), net = Buffer.alloc(20, 0xff), codec = Buffer.alloc(21, 0x88), store = Buffer.alloc(22, 0x99);
  const patched = patchPages(original, main, aux, net, codec, store);
  const expectedEntry = Buffer.from(original.entry);
  for (const offset of [0xc3c, 0xd68, 0xd7c, 0xca0, 0xe6c]) expectedEntry.writeUInt32LE(0x3804b109, offset);
  assert.deepEqual(patched.entry, expectedEntry);
  assert.deepEqual(patched.code.subarray(0, 0x10c), original.code.subarray(0, 0x10c));
  assert.deepEqual(patched.code.subarray(0x10c + main.length), original.code.subarray(0x10c + main.length));
  assert.deepEqual(patched.aux.subarray(0, 0x768), original.aux.subarray(0, 0x768));
  assert.deepEqual(patched.aux.subarray(0x768 + aux.length), original.aux.subarray(0x768 + aux.length));
  assert.deepEqual(patched.net.subarray(0, 4), original.net.subarray(0, 4));
  assert.deepEqual(patched.net.subarray(4 + net.length), original.net.subarray(4 + net.length));
  assert.deepEqual(patched.codec.subarray(0, 0x9c), original.codec.subarray(0, 0x9c));
  assert.deepEqual(patched.codec.subarray(0x9c + codec.length), original.codec.subarray(0x9c + codec.length));
  assert.deepEqual(patched.store.subarray(0, 4), original.store.subarray(0, 4));
  assert.deepEqual(patched.store.subarray(4 + store.length), original.store.subarray(4 + store.length));
  assert.equal(original.code[0x10c], 0xa3, 'Baseline must not be modified in place');
});
test('full capacity ends before adjacent helpers and overflow is refused', () => {
  const original = pages(), patched = patchPages(original, payload(3432), Buffer.alloc(444, 0xee), Buffer.alloc(4080, 0xff), Buffer.alloc(3348, 0x88), Buffer.alloc(3056, 0x99));
  assert.deepEqual(patched.code.subarray(0xe74), original.code.subarray(0xe74));
  assert.deepEqual(patched.aux.subarray(0x924), original.aux.subarray(0x924));
  assert.deepEqual(patched.net.subarray(0xff4), original.net.subarray(0xff4));
  assert.deepEqual(patched.codec.subarray(0xdb0), original.codec.subarray(0xdb0));
  assert.deepEqual(patched.store.subarray(0xbf4), original.store.subarray(0xbf4));
  assert.throws(() => patchPages(original, payload(3433), Buffer.alloc(444), Buffer.alloc(4080), Buffer.alloc(3348), Buffer.alloc(3056)), /containers/);
  assert.throws(() => patchPages(original, payload(3432), Buffer.alloc(445), Buffer.alloc(4080), Buffer.alloc(3348), Buffer.alloc(3056)), /containers/);
  assert.throws(() => patchPages(original, payload(), Buffer.alloc(0), Buffer.alloc(4080), Buffer.alloc(3348), Buffer.alloc(3056)), /containers/);
  assert.throws(() => patchPages(original, payload(), Buffer.alloc(444), Buffer.alloc(4081), Buffer.alloc(3348), Buffer.alloc(3056)), /containers/);
  assert.throws(() => patchPages(original, payload(), Buffer.alloc(444), Buffer.alloc(4080), Buffer.alloc(3349), Buffer.alloc(3056)), /containers/);
  assert.throws(() => patchPages(original, payload(), Buffer.alloc(444), Buffer.alloc(4080), Buffer.alloc(0), Buffer.alloc(3056)), /containers/);
  assert.throws(() => patchPages(original, payload(), Buffer.alloc(444), Buffer.alloc(4080), Buffer.alloc(3348), Buffer.alloc(3057)), /containers/);
  assert.throws(() => patchPages(original, payload(), Buffer.alloc(444), Buffer.alloc(4080), Buffer.alloc(3348), Buffer.alloc(0)), /containers/);
});
test('disabled stubs and fixed Thumb entry are mandatory', () => {
  const bad = payload(); bad[0x1ec] ^= 1;
  assert.throws(() => patchPages(pages(), bad, Buffer.alloc(4), Buffer.alloc(4), Buffer.alloc(4), Buffer.alloc(4)), /entry changed/);
  const short = pages(); short.aux = Buffer.alloc(4095);
  assert.throws(() => patchPages(short, payload(), Buffer.alloc(4), Buffer.alloc(4), Buffer.alloc(4), Buffer.alloc(4)), /Whole 4KiB/);
  const wrongBuiltin = pages(); wrongBuiltin.entry.writeUInt32LE(0x3804b109, 0xc3c);
  assert.throws(() => patchPages(wrongBuiltin, payload(), Buffer.alloc(4), Buffer.alloc(4), Buffer.alloc(4), Buffer.alloc(4)), /builtin baseline/);
  for (const offset of [0xd68, 0xd7c, 0xca0, 0xe6c]) {
    const wrong = pages(); wrong.entry.writeUInt32LE(0x3804b109, offset);
    assert.throws(() => patchPages(wrong, payload(), Buffer.alloc(4), Buffer.alloc(4), Buffer.alloc(4), Buffer.alloc(4)), /builtin baseline/);
  }
});
test('ELF spans reconstruct without a flat binary address hole', () => {
  const main = payload(), aux = Buffer.from([4, 5, 6, 7]);
  assert.deepEqual(linkedSegments(elf(main, aux)), { main, aux, net: Buffer.alloc(20, 0x22), codec: Buffer.alloc(20, 0x33), store: Buffer.alloc(20, 0x44) });
});
test('ELF rejects writable/NOBITS, wrong entry, overlap and out-of-container spans', () => {
  const pristine = elf(payload(), Buffer.alloc(4));
  for (const [offset, value, error] of [
    [24, 0x3804b2f4, /fixed-entry/], [52 + 40 + 8, 7, /Writable/],
    [52 + 40 + 4, 8, /Writable/], [52 + 80 + 12, 0x3807a920, /containers/],
    [52 + 80 + 12, 0x3804b109, /Overlapping/],
    [52 + 160 + 12, 0x38047dac, /containers/],
    [52 + 200 + 12, 0x38052bf0, /containers/],
  ] as const) {
    const bad = Buffer.from(pristine); bad.writeUInt32LE(value, offset);
    assert.throws(() => linkedSegments(bad), error);
  }
  assert.throws(() => linkedSegments(pristine.subarray(0, 60)), /section table/);
});
test('six-page writer preserves exact native caller while extending fixed dependency ordering', () => {
  const source = readFileSync(fileURLToPath(new URL('../../diagnostics/boot-nor-native-image-drawer-runner.cfg', import.meta.url)), 'utf8');
  const cloned = cloneWriter(source);
  const kernel = (text: string) => text.slice(text.indexOf('proc ' + (text.includes('proc nmr_word') ? 'nmr_' : 'nid_') + 'word'), text.indexOf('# Public operation'));
  assert.equal(kernel(cloned), names(kernel(source)));
  const net = cloned.indexOf('nmr_write_sector $capture_dir install-net'), aux = cloned.indexOf('nmr_write_sector $capture_dir install-aux');
  assert.ok(cloned.indexOf('nmr_write_sector $capture_dir install-codec') < net);
  assert.ok(cloned.indexOf('nmr_write_sector $capture_dir install-store') < cloned.indexOf('nmr_write_sector $capture_dir install-codec'));
  assert.ok(net < aux && aux < cloned.indexOf('nmr_write_sector $capture_dir install-code '));
  assert.ok(cloned.indexOf('nmr_write_sector $capture_dir restore-aux') < cloned.indexOf('nmr_write_sector $capture_dir restore-net'));
  assert.ok(cloned.indexOf('nmr_write_sector $capture_dir restore-net') < cloned.indexOf('nmr_write_sector $capture_dir restore-codec'));
  assert.ok(cloned.indexOf('nmr_write_sector $capture_dir restore-codec') < cloned.indexOf('nmr_write_sector $capture_dir restore-store'));
  assert.match(cloned, /Whole six sectors changed after cache invalidation/);
  assert.throws(() => cloneWriter(source.replace('all three exact fast-tap sector baselines', 'any baseline')), /anchor/);
  assert.equal(names('nid_safe nidi_words native-image-drawer'), 'nmr_safe nmri_words panel-maintained');
});
test('freeze evidence cannot borrow another release, omit input hashes or substitute old ELF/model', () => {
  const candidate = { inputs: { 'snapshot/panel.elf': '123' }, program: { elfSha256: '456' } } as Parameters<typeof checkEvidence>[2];
  const evidence = { role: 'arm-model', passed: true, release_manifest_sha256: '789',
    reviewed_inputs: candidate.inputs, scope: 'actual-arm', check_count: 1, elf_sha256: '456' };
  checkEvidence('arm-model', evidence, candidate, '789');
  assert.throws(() => checkEvidence('arm-model', evidence, candidate, 'other'), /candidate/);
  assert.throws(() => checkEvidence('arm-model', { ...evidence, reviewed_inputs: {} }, candidate, '789'), /exact input/);
  assert.throws(() => checkEvidence('arm-model', { ...evidence, elf_sha256: 'old' }, candidate, '789'), /current actual ELF/);
  assert.throws(() => checkEvidence('arm-model', { ...evidence, scope: 'host-only' }, candidate, '789'), /current actual ELF/);
});
test('writer mock freeze gate requires inherited coverage and all three dependency page cases distinctly', () => {
  const candidate = { inputs: {}, program: { elfSha256: '456' } } as Parameters<typeof checkEvidence>[2];
  const evidence = { role: 'writer-mock', passed: true, release_manifest_sha256: '789', reviewed_inputs: {},
    all_passed: true, cases: WRITER_MOCK_CASES.map(name => ({ case: name, passed: true })) };
  checkEvidence('writer-mock', evidence, candidate, '789');
  assert.throws(() => checkEvidence('writer-mock', { ...evidence, cases: evidence.cases.slice(1) }, candidate, '789'), /70/);
  evidence.cases[42].passed = false;
  assert.throws(() => checkEvidence('writer-mock', evidence, candidate, '789'), /70/);
  assert.equal(sha256('hello'), '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824');
});
test('new private mock contains all three dependency page model failures and independent stock rollback', () => {
  const source = readFileSync(fileURLToPath(new URL('../../analysis/persistence/test_native_image_drawer_runner_offline.py', import.meta.url)), 'utf8');
  const cloned = cloneMock(source);
  assert.match(cloned, /Network rollback is not exact stock page/);
  assert.match(cloned, /Net restored before main\/table\/aux whole verification/);
  assert.match(cloned, /Codec rollback is not exact stock page/);
  assert.match(cloned, /Codec restored before main\/table\/aux\/net whole verification/);
  assert.match(cloned, /Store rollback is not exact stock page/);
  assert.match(cloned, /Store restored before main\/table\/aux\/net\/codec whole verification/);
  for (const name of NET_MOCK_CASES) assert.ok(cloned.includes('"' + name + '"'));
  for (const name of CODEC_MOCK_CASES) assert.ok(cloned.includes('"' + name + '"'));
  for (const name of STORE_MOCK_CASES) assert.ok(cloned.includes('"' + name + '"'));
});
function ownership() {
  const stock = '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b';
  const net = { path: 'build/reviews/net-review.txt', sha256: sha256('Synthetic net ownership fixture.\n') };
  const codec = { path: 'build/reviews/codec-review.txt', sha256: sha256('Synthetic codec ownership fixture.\n') };
  const store = { path: 'build/reviews/store-review.txt', sha256: sha256('Synthetic store ownership fixture.\n') };
  return { role: 'storage-ownership-review', passed: true, firmware: '1.50.10',
    baseline_freeze_sha256: 'fa99d95a98b3abd4f3e76ce304a4d6a12623f50338d0240a6aba4b91f0a0cf61', stock_backup_sha256: stock,
    net_page_sha256: '76a994fbd3892960f43db969b4744fbb726d23feac5c24df86041398ee5d299d',
    net_offset: '0x92d000', runtime_start: '0x3804d000', runtime_end_exclusive: '0x3804dff0',
    builtin_entry_offset: '0xc3c', builtin_original_word: '0x3804cf3d', builtin_disabled_word: '0x3804b109',
    codec_page_sha256: '21c40d397e6ec14f61011544f736962470f623c91ba3bbf7a6d89d120ba23c02',
    codec_offset: '0x927000', codec_runtime_start: '0x38047098', codec_runtime_end_exclusive: '0x38047dac',
    codec_builtin_entries: [[0xd68, 0x38047099], [0xd7c, 0x38047849], [0xca0, 0x38047b3d]]
      .map(([offset, original_word]) => ({ offset, original_word, disabled_word: '0x3804b109' })),
    store_page_sha256: '6874cd0d613150d2c71c70bbf5513f83f72214304e2891f092d50e6e87d84c71',
    store_offset: '0x932000', store_runtime_start: '0x38052000', store_runtime_end_exclusive: '0x38052bf0',
    store_builtin_entry_offset: '0xe6c', store_builtin_original_word: '0x38051fd1', store_builtin_disabled_word: '0x3804b109',
    net_review: net, codec_review: codec, store_review: store,
    evidence_sha256: { 'backups/mi-panel-flash-16m-1.50.10-20261004.bin': stock,
      [net.path]: net.sha256, [codec.path]: codec.sha256, [store.path]: store.sha256 } } as Parameters<typeof checkOwnership>[0];
}
test('all three dependency pages require exact boundaries, diagnostics and distinct bound ownership evidence', () => {
  checkOwnership(ownership());
  assert.throws(() => checkOwnership({ ...ownership(), passed: false } as unknown as Parameters<typeof checkOwnership>[0]), /reviewed ownership/);
  assert.throws(() => checkOwnership({ ...ownership(), runtime_end_exclusive: '0x3804dff8' }), /reviewed ownership/);
  assert.throws(() => checkOwnership({ ...ownership(), evidence_sha256: {} }), /actual evidence/);
  assert.throws(() => checkOwnership({ ...ownership(), codec_runtime_end_exclusive: '0x38047ffc' }), /reviewed ownership/);
  assert.throws(() => checkOwnership({ ...ownership(), codec_builtin_entries: ownership().codec_builtin_entries.slice(1) }), /reviewed ownership/);
  assert.throws(() => checkOwnership({ ...ownership(), codec_review: ownership().net_review }), /distinct net, codec and store/);
  const missing = ownership(); delete missing.evidence_sha256[missing.codec_review.path];
  assert.throws(() => checkOwnership(missing), /distinct net, codec and store/);
  assert.throws(() => checkOwnership({ ...ownership(), store_runtime_end_exclusive: '0x38052bf4' }), /reviewed ownership/);
  assert.throws(() => checkOwnership({ ...ownership(), store_page_sha256: '0'.repeat(64) }), /reviewed ownership/);
  assert.throws(() => checkOwnership({ ...ownership(), store_builtin_original_word: '0x38051fd0' }), /reviewed ownership/);
  assert.throws(() => checkOwnership({ ...ownership(), store_review: ownership().codec_review }), /distinct net, codec and store/);
});
test('compiler headers retain exact complete contents and cannot escape their private snapshot directory', () => {
  const record = { headers: { '/clang/include/a.h': '123', '/clang/include/b.h': '456' },
    headerCopies: { 'build/panel/compiler-headers/a.h': '123', 'build/panel/compiler-headers/b.h': '456' } } as Parameters<typeof compilerHeaderCopies>[0];
  assert.equal(compilerHeaderCopies(record).length, 2);
  assert.throws(() => compilerHeaderCopies({ ...record, headerCopies: {} }), /all actual build headers/);
  assert.throws(() => compilerHeaderCopies({ ...record, headerCopies: { 'build/panel/compiler-headers/a.h': 'old', 'build/panel/compiler-headers/b.h': '456' } }), /all actual build headers/);
  assert.throws(() => compilerHeaderCopies({ ...record, headerCopies: { 'build/panel/compiler-headers/../../a.h': '123', 'build/panel/compiler-headers/b.h': '456' } }), /admitted snapshot/);
});
test('private candidate binds copied sources; canonical edits do not change a release and missing reviews cannot freeze', () => {
  const repository = fileURLToPath(new URL('../../', import.meta.url));
  const temporary = mkdtempSync(join(tmpdir(), 'mi-panel-release-test-'));
  function store(path: string, data: Buffer | string) {
    const target = join(temporary, path);
    mkdirSync(dirname(target), { recursive: true }); writeFileSync(target, data);
  }
  try {
    const pending = ['analysis/persistence/native-image-drawer-frozen-inputs.json'], copied = new Set<string>();
    while (pending.length) {
      const path = pending.pop()!;
      if (copied.has(path)) continue;
      copied.add(path);
      const bytes = readFileSync(join(repository, path)); store(path, bytes);
      if (path.endsWith('-frozen-inputs.json')) pending.push(...Object.keys(JSON.parse(bytes.toString()).sha256));
    }
    for (const name of ['libftdi1.dll', 'libusb-1.0.dll']) {
      const path = 'tools/xpack-openocd-0.12.0-7/bin/' + name;
      store(path, readFileSync(join(repository, path)));
    }
    const cmsisPath = 'tools/xpack-openocd-0.12.0-7/openocd/scripts/interface/cmsis-dap.cfg';
    const cmsisBytes = readFileSync(join(repository, cmsisPath));
    store(cmsisPath, cmsisBytes);
    const sourcePaths = ['firmware/build.sh', 'firmware/tools/build-record.ts', 'firmware/src/ui.c',
      'firmware/include/panel.h', 'firmware/ports/1.50.10/panel.ld', 'build/panel/config.h'];
    for (const path of sourcePaths) store(path, 'Synthetic offline release-tool fixture; not compiled device firmware.\n');
    store('firmware/tools/release.ts', readFileSync(join(repository, 'firmware/tools/release.ts')));
    store('firmware/tools/hardware.ts', 'Synthetic unit-test executor placeholder; no hardware commands.\n');
    store('firmware/tools/release.test.ts', readFileSync(join(repository, 'firmware/tools/release.test.ts')));
    store('firmware/tests/synthetic.py', '# Synthetic model fixture; not a device verification.\n');
    store('build/panel/compiler-headers/synthetic.h', 'Synthetic compiler header fixture.\n');
    const main = payload(), aux = Buffer.alloc(20, 0xdd);
    store('build/panel/panel.bin', main); store('build/panel/panel-aux.bin', aux);
    store('build/panel/panel-net.bin', Buffer.alloc(20, 0x22));
    store('build/panel/panel-codec.bin', Buffer.alloc(20, 0x33));
    store('build/panel/panel-store.bin', Buffer.alloc(20, 0x44));
    store('build/panel/panel.elf', elf(main, aux)); store('build/panel/panel.map', 'Synthetic unit-test mapping\n');
    const outputs = ['panel.bin', 'panel-aux.bin', 'panel-net.bin', 'panel-codec.bin', 'panel-store.bin', 'panel.elf', 'panel.map'].map(name => 'build/panel/' + name);
    store('build/panel/build-inputs.json', JSON.stringify({ completed: true,
      sources: Object.fromEntries(sourcePaths.map(path => [path, sha256(readFileSync(join(temporary, path)))])),
      artifacts: Object.fromEntries(outputs.map(path => [path, sha256(readFileSync(join(temporary, path)))])),
      headers: { '/synthetic/clang/synthetic.h': sha256(readFileSync(join(temporary, 'build/panel/compiler-headers/synthetic.h'))) },
      headerCopies: { 'build/panel/compiler-headers/synthetic.h': sha256(readFileSync(join(temporary, 'build/panel/compiler-headers/synthetic.h'))) } }));
    store('build/reviews/ownership.json', JSON.stringify(ownership()));
    store('build/reviews/net-review.txt', 'Synthetic net ownership fixture.\n');
    store('build/reviews/codec-review.txt', 'Synthetic codec ownership fixture.\n');
    store('build/reviews/store-review.txt', 'Synthetic store ownership fixture.\n');
    const candidate = prepareRelease(temporary, 'offline-unit-fixture', 'build/reviews/ownership.json');
    assert.equal(candidate.hardwareExecution, false);
    assert.equal(candidate.schema, 4); assert.equal(candidate.layout, 'six-page-store-v1');
    assert.deepEqual(candidate.installOrder, ['store', 'codec', 'net', 'aux', 'code', 'entry']);
    assert.deepEqual(candidate.restoreOrder, ['entry', 'code', 'aux', 'net', 'codec', 'store']);
    assert.equal(verifyRelease(temporary, 'offline-unit-fixture').frozen, false);
    const frozenVerifier = join(temporary, 'build/releases/offline-unit-fixture/snapshot/firmware/tools/release.ts');
    const command = spawnSync(process.execPath, [frozenVerifier, 'verify', 'offline-unit-fixture'], { cwd: temporary, encoding: 'utf8' });
    assert.equal(command.status, 0, 'Snapshot verifier must use the invoking repository/bundle root: ' + command.stderr);
    assert.equal(JSON.parse(command.stdout).name, 'offline-unit-fixture');
    const alias = 'build/releases/offline-unit-fixture/workspace/diagnostics/interface/cmsis-dap.cfg';
    assert.deepEqual(readFileSync(join(temporary, alias)), cmsisBytes);
    assert.deepEqual(readFileSync(join(temporary, 'build/releases/offline-unit-fixture/workspace/' + cmsisPath)), cmsisBytes);
    store(alias, Buffer.concat([cmsisBytes, Buffer.from('\n')]));
    assert.throws(() => verifyRelease(temporary, 'offline-unit-fixture'), /Input SHA mismatch/);
    store(alias, cmsisBytes);
    assert.throws(() => prepareRelease(temporary, 'offline-unit-fixture', 'build/reviews/ownership.json'), /never overwrite/);
    store('firmware/src/ui.c', 'Later canonical source edit');
    store('firmware/tests/synthetic.py', '# Later canonical model edit\n');
    verifyRelease(temporary, 'offline-unit-fixture');
    store('build/empty-evidence.json', '{}');
    assert.throws(() => freezeRelease(temporary, 'offline-unit-fixture', 'build/empty-evidence.json'), /Missing independent evidence/);
    assert.equal(existsSync(join(temporary, 'build/releases/offline-unit-fixture/freeze.json')), false);
    const snapshot = 'build/releases/offline-unit-fixture/snapshot/firmware/src/ui.c';
    store(snapshot, 'Unreviewed snapshot modification');
    assert.throws(() => verifyRelease(temporary, 'offline-unit-fixture'), /Input SHA mismatch/);
  } finally {
    assert.equal(dirname(resolve(temporary)), resolve(tmpdir()));
    assert.ok(temporary.startsWith(join(tmpdir(), 'mi-panel-release-test-')));
    rmSync(temporary, { recursive: true });
  }
});
