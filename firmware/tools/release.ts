/** Offline release snapshots for this panel's exact 1.50.10 five-page patch. */
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASELINE_FREEZE = 'analysis/persistence/native-image-drawer-frozen-inputs.json';
const BASELINE_SHA = 'fa99d95a98b3abd4f3e76ce304a4d6a12623f50338d0240a6aba4b91f0a0cf61';
const BASELINE_MANIFEST = 'analysis/persistence/native-image-drawer-patch-inputs-1.50.10.json';
const CALLER_SHA = 'abed88ffa44ddd05eeb547178c981bf784f6ca492d1ecf21613af8fb3cb94c32';
const PREFIX = 'panel-maintained';
const CMSIS_CONFIG = 'tools/xpack-openocd-0.12.0-7/openocd/scripts/interface/cmsis-dap.cfg';
const CMSIS_ALIAS = 'diagnostics/interface/cmsis-dap.cfg';
const STOCK_PATH = 'backups/mi-panel-flash-16m-1.50.10-20261004.bin';
const STOCK_SHA = '777de42c53a1c95495c55b3a9a0c27f907f68ab87a9512bee6b5f4356acb695b';
const NET_PAGE_SHA = '76a994fbd3892960f43db969b4744fbb726d23feac5c24df86041398ee5d299d';
const CODEC_PAGE_SHA = '21c40d397e6ec14f61011544f736962470f623c91ba3bbf7a6d89d120ba23c02';
const PORT = {
  main: { start: 0x3804b108, end: 0x3804be70, page: 0x92b000, offset: 0x10c },
  aux: { start: 0x3807a764, end: 0x3807a920, page: 0x95a000, offset: 0x768 },
  net: { start: 0x3804d000, end: 0x3804dff0, page: 0x92d000, offset: 4 },
  codec: { start: 0x38047098, end: 0x38047dac, page: 0x927000, offset: 0x9c },
};
const ENTRY_WORDS = [[0xcc8, 0x3804b2f5], [0xebc, 0x3804b111], [0xf20, 0x3804b111],
  [0xe80, 0x3804b109], [0xd2c, 0x3804b109]];
const CODEC_ENTRY_WORDS = [[0xd68, 0x38047099], [0xd7c, 0x38047849], [0xca0, 0x38047b3d]];
const PAGE_OFFSETS = { code: 0x92b000, entry: 0xccd000, aux: 0x95a000, net: 0x92d000, codec: 0x927000 };
const EVIDENCE_ROLES = ['storage-ownership-review', 'program-review', 'writer-review', 'arm-model', 'writer-mock'];
type Hashes = Record<string, string>;
type Pages = Record<'code' | 'entry' | 'aux' | 'net' | 'codec', Buffer>;
type Inputs = Map<string, Buffer>;
type BuildRecord = { completed: boolean; sources: Hashes; artifacts: Hashes; headers: Hashes; headerCopies: Hashes };
type Ownership = {
  role: 'storage-ownership-review'; passed: true; firmware: '1.50.10'; baseline_freeze_sha256: string;
  stock_backup_sha256: string; net_page_sha256: string; net_offset: number | string;
  runtime_start: number | string; runtime_end_exclusive: number | string;
  builtin_entry_offset: number | string; builtin_original_word: number | string; builtin_disabled_word: number | string;
  codec_page_sha256: string; codec_offset: number | string;
  codec_runtime_start: number | string; codec_runtime_end_exclusive: number | string;
  codec_builtin_entries: { offset: number | string; original_word: number | string; disabled_word: number | string }[];
  net_review: { path: string; sha256: string }; codec_review: { path: string; sha256: string };
  evidence_sha256: Hashes;
};
type Candidate = {
  schema: 3; layout: 'five-page-codec-v1'; name: string; firmware: '1.50.10'; status: 'candidate'; hardwareExecution: false;
  baselineFreezeSha256: string; baselineInputs: Hashes; inputs: Hashes;
  ownership: { path: string; sha256: string };
  program: { mainBytes: number; auxBytes: number; netBytes: number; codecBytes: number; elfSha256: string };
  pages: Record<keyof Pages, { offset: number; originalSha256: string; patchedSha256: string }>;
  mockCommand: string[]; installOrder: string[]; restoreOrder: string[];
};

export const sha256 = (data: string | Uint8Array) => createHash('sha256').update(data).digest('hex');
function requireThat(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}
const decode = <T>(data: Uint8Array | string): T => JSON.parse(data.toString()) as T;
const encode = (value: unknown) => JSON.stringify(value, null, 2) + '\n';
function within(root: string, name: string) {
  const target = resolve(root, name);
  const part = relative(root, target);
  requireThat(part !== '..' && !part.startsWith('..' + (process.platform === 'win32' ? '\\' : '/')) &&
    !isAbsolute(part), `Path leaves release root: ${name}`);
  return target;
}
function read(root: string, name: string) {
  const target = within(root, name);
  within(realpathSync(root), relative(root, realpathSync(target)));
  return readFileSync(target);
}
function checked(root: string, name: string, expected: string) {
  const data = read(root, name);
  requireThat(sha256(data) === expected, `Input SHA mismatch: ${name}`);
  return data;
}
function collectBaseline(root: string) {
  const inputs: Inputs = new Map();
  const pending = [[BASELINE_FREEZE, BASELINE_SHA]];
  while (pending.length) {
    const [name, expected] = pending.pop()!;
    if (inputs.has(name)) {
      requireThat(sha256(inputs.get(name)!) === expected, `Conflicting baseline hash: ${name}`);
      continue;
    }
    const data = checked(root, name, expected);
    inputs.set(name, data);
    if (name.endsWith('-frozen-inputs.json')) {
      const catalog = decode<{ sha256: Hashes }>(data);
      requireThat(catalog.sha256 && Object.keys(catalog.sha256).length, `Empty freeze: ${name}`);
      for (const dependency of Object.entries(catalog.sha256)) pending.push(dependency);
    }
  }
  const direct = decode<{ sha256: Hashes }>(inputs.get(BASELINE_FREEZE)!);
  requireThat(Object.keys(direct.sha256).length === 93, 'Current baseline must bind exactly 93 inputs');
  const manifest = decode<{ sectors: Record<keyof Pages, { offset: string;
    patched: { path: string; bytes: number; sha256: string } }> }>(inputs.get(BASELINE_MANIFEST)!);
  const pages = {} as Pages;
  for (const label of ['code', 'entry', 'aux'] as const) {
    const item = manifest.sectors[label];
    requireThat(Number(item.offset) === PAGE_OFFSETS[label] && item.patched.bytes === 4096,
      `Unexpected baseline page layout: ${label}`);
    pages[label] = inputs.get(item.patched.path)!;
    requireThat(pages[label]?.length === 4096 && sha256(pages[label]) === item.patched.sha256,
      `Baseline manifest/page mismatch: ${label}`);
  }
  for (const [offset, expected] of ENTRY_WORDS)
    requireThat(pages.entry.readUInt32LE(offset) === expected, 'Baseline entry words changed');
  requireThat(pages.entry.readUInt32LE(0xc3c) === 0x3804cf3d, 'uorb_unit_test builtin baseline changed');
  for (const [offset, expected] of CODEC_ENTRY_WORDS)
    requireThat(pages.entry.readUInt32LE(offset) === expected, 'Fill diagnostics builtin baseline changed');
  const stock = inputs.get(STOCK_PATH)!;
  requireThat(stock?.length === 16777216 && sha256(stock) === STOCK_SHA, 'Full stock backup drift');
  pages.net = Buffer.from(stock.subarray(PAGE_OFFSETS.net, PAGE_OFFSETS.net + 4096));
  requireThat(sha256(pages.net) === NET_PAGE_SHA, 'Stock network page drift');
  pages.codec = Buffer.from(stock.subarray(PAGE_OFFSETS.codec, PAGE_OFFSETS.codec + 4096));
  requireThat(sha256(pages.codec) === CODEC_PAGE_SHA, 'Stock codec page drift');
  return { inputs, pages };
}
export function verifyBaseline(root: string) {
  const baseline = collectBaseline(root);
  callerFromStages(baseline.inputs.get('diagnostics/boot-nor-native-image-drawer-stage-inputs.cfg')!.toString('utf8'));
  return { freezeSha256: BASELINE_SHA, directInputs: 93, dependencyInputs: baseline.inputs.size,
    pages: Object.fromEntries(Object.entries(baseline.pages).map(([name, data]) => [name, sha256(data)])), hardwareExecution: false };
}

export function linkedSegments(raw: Buffer) {
  requireThat(raw.length >= 52 && raw.subarray(0, 7).equals(Buffer.from([127, 69, 76, 70, 1, 1, 1])) &&
    raw.readUInt16LE(18) === 40 && raw.readUInt32LE(24) === 0x3804b2f5, 'Expected fixed-entry ARM ELF32 LE');
  const table = raw.readUInt32LE(32), stride = raw.readUInt16LE(46), count = raw.readUInt16LE(48);
  requireThat(stride === 40 && count > 0 && table + stride * count <= raw.length, 'Truncated ELF section table');
  const spans: Record<keyof typeof PORT, { address: number; bytes: Buffer }[]> = { main: [], aux: [], net: [], codec: [] };
  for (let index = 0; index < count; index++) {
    const pos = table + index * stride;
    const kind = raw.readUInt32LE(pos + 4), flags = raw.readUInt32LE(pos + 8);
    const address = raw.readUInt32LE(pos + 12), offset = raw.readUInt32LE(pos + 16), size = raw.readUInt32LE(pos + 20);
    if (!(flags & 2) || !size) continue;
    requireThat(kind === 1 && !(flags & 1), 'Writable data/BSS is not admitted');
    const label = (Object.keys(PORT) as (keyof typeof PORT)[]).find(name =>
      address >= PORT[name].start && address + size <= PORT[name].end);
    requireThat(label && offset + size <= raw.length, 'Allocated ELF section leaves admitted containers');
    spans[label].push({ address, bytes: raw.subarray(offset, offset + size) });
  }
  const result = {} as Record<keyof typeof PORT, Buffer>;
  for (const label of Object.keys(PORT) as (keyof typeof PORT)[]) {
    const parts = spans[label].sort((a, b) => a.address - b.address), start = PORT[label].start;
    requireThat(parts.length && parts[0].address === start, `Missing ELF segment: ${label}`);
    const last = parts.at(-1)!;
    const image = Buffer.alloc(last.address + last.bytes.length - start);
    let end = start;
    for (const part of parts) {
      requireThat(part.address >= end, 'Overlapping allocated ELF sections');
      part.bytes.copy(image, part.address - start);
      end = part.address + part.bytes.length;
    }
    result[label] = image;
  }
  return result;
}
export function patchPages(original: Pages, main: Buffer, aux: Buffer, net: Buffer, codec: Buffer): Pages {
  requireThat(main.length > 0 && main.length <= PORT.main.end - PORT.main.start &&
    aux.length > 0 && aux.length <= PORT.aux.end - PORT.aux.start &&
    net.length > 0 && net.length <= PORT.net.end - PORT.net.start &&
    codec.length > 0 && codec.length <= PORT.codec.end - PORT.codec.start, 'Payload exceeds fixed five-page containers');
  requireThat(main.subarray(0, 6).equals(Buffer.from('262040427047', 'hex')) &&
    main.subarray(8, 12).equals(Buffer.from('00207047', 'hex')) &&
    main.subarray(0x1ec, 0x1f0).equals(Buffer.from('00f000b8', 'hex')), 'Fixed disabled stubs/Thumb B.W entry changed');
  requireThat(Object.values(original).every(page => page.length === 4096), 'Whole 4KiB baseline pages required');
  requireThat(original.entry.readUInt32LE(0xc3c) === 0x3804cf3d, 'uorb_unit_test builtin baseline changed');
  for (const [offset, expected] of CODEC_ENTRY_WORDS)
    requireThat(original.entry.readUInt32LE(offset) === expected, 'Fill diagnostics builtin baseline changed');
  const result = { code: Buffer.from(original.code), entry: Buffer.from(original.entry), aux: Buffer.from(original.aux),
    net: Buffer.from(original.net), codec: Buffer.from(original.codec) };
  main.copy(result.code, PORT.main.offset);
  aux.copy(result.aux, PORT.aux.offset);
  net.copy(result.net, PORT.net.offset);
  codec.copy(result.codec, PORT.codec.offset);
  result.entry.writeUInt32LE(0x3804b109, 0xc3c);
  for (const [offset] of CODEC_ENTRY_WORDS) result.entry.writeUInt32LE(0x3804b109, offset);
  return result;
}
export const names = (text: string) => text.replaceAll('\r\n', '\n')
  .replaceAll('native-image-drawer', PREFIX).replaceAll('native_image_drawer', 'panel_maintained')
  .replaceAll('nidi_', 'nmri_').replaceAll('nid_', 'nmr_');
function replaceOne(text: string, before: string, after: string) {
  requireThat(text.split(before).length === 2, `Clone anchor changed: ${before}`);
  return text.replace(before, after);
}
export function cloneWriter(text: string) {
  let result = names(text);
  const globals = '    global nmri_aux_original_words nmri_aux_patched_words';
  requireThat(result.split(globals).length === 4, 'Three fixed orchestration globals changed');
  result = result.replaceAll(globals, globals + ' nmri_net_original_words nmri_net_patched_words');
  for (const [before, after] of [
    ['allowlisted to three exact reviewed A7 app sectors', 'allowlisted to four exact reviewed A7 app sectors'],
    ['    } else { error "Unreviewed sector" }',
      '    } elseif {$label == "net"} {\n        set address 0x2892d000\n' +
      '        if {$expected != $nmri_net_original_words && $expected != $nmri_net_patched_words} { error "Unreviewed net-sector comparison source" }\n' +
      '    } else { error "Unreviewed sector" }'],
    ['    } else { error "Sector helper admits only exact reviewed code/table/aux stages" }',
      '    } elseif {$prefix == "install-net"} { set fixed_words $nmri_net_patched_words\n' +
      '    } elseif {$prefix == "restore-net"} { set fixed_words $nmri_net_original_words\n' +
      '    } else { error "Sector helper admits only exact reviewed net/code/table/aux stages" }'],
    ['fixedsectors92b000/95a000/ccd000 only', 'fixedsectors92d000/95a000/92b000/ccd000 only'],
    ['        set aux_before [nmr_words 0x2895a000 1024]',
      '        set aux_before [nmr_words 0x2895a000 1024]\n        set net_before [nmr_words 0x2892d000 1024]'],
    ['                $aux_before != $nmri_aux_original_words} { error "Install requires all three exact fast-tap sector baselines" }',
      '                $aux_before != $nmri_aux_original_words || $net_before != $nmri_net_original_words} { error "Install requires all four exact image-drawer sector baselines" }'],
    ['&& $aux_before == $nmri_aux_original_words) ||', '&& $aux_before == $nmri_aux_original_words && $net_before == $nmri_net_original_words) ||'],
    ['&& $aux_before == $nmri_aux_patched_words))}', '&& $aux_before == $nmri_aux_patched_words && $net_before == $nmri_net_patched_words))}'],
    ['Restore requires all three exact fast-tap or all three exact image-drawer sector baselines',
      'Restore requires all four exact image-drawer or all four exact maintained sector baselines'],
    ['        dump_image [file join $capture_dir sector-aux-before.bin] 0x2895a000 4096',
      '        dump_image [file join $capture_dir sector-aux-before.bin] 0x2895a000 4096\n' +
      '        dump_image [file join $capture_dir sector-net-before.bin] 0x2892d000 4096'],
    ['            # Admit and verify the complete auxiliary page before main can reference it.',
      '            # Install dependencies before any main/entry reference can point to them.\n' +
      '            nmr_write_sector $capture_dir install-net $nmri_net_patched_words $original_bp $remove_fpb_command\n' +
      '            nmr_verify_sector $capture_dir net $nmri_net_patched_words\n' +
      '            nmr_status_stage [file join $capture_dir status-net] unprotected $original_sr1 $original_sr2 $remove_fpb_command'],
    ['set expected_aux $nmri_aux_patched_words', 'set expected_aux $nmri_aux_patched_words; set expected_net $nmri_net_patched_words'],
    ['Restore fast-tap main references before returning the auxiliary slot to fast tap.',
      'Restore image-drawer main references before returning dependency slots to image drawer/stock.'],
    ['            nmr_verify_sector $capture_dir aux $nmri_aux_original_words',
      '            nmr_verify_sector $capture_dir aux $nmri_aux_original_words\n' +
      '            nmr_status_stage [file join $capture_dir status-aux-restored] unprotected $original_sr1 $original_sr2 $remove_fpb_command\n' +
      '            nmr_write_sector $capture_dir restore-net $nmri_net_original_words $original_bp $remove_fpb_command\n' +
      '            nmr_verify_sector $capture_dir net $nmri_net_original_words'],
    ['set expected_aux $nmri_aux_original_words', 'set expected_aux $nmri_aux_original_words; set expected_net $nmri_net_original_words'],
    ['foreach sector {aux code table}', 'foreach sector {net aux code table}'],
    ['[nmr_words 0x2895a000 1024] != $expected_aux} { error "Whole three sectors changed after cache invalidation" }',
      '[nmr_words 0x2895a000 1024] != $expected_aux || [nmr_words 0x2892d000 1024] != $expected_net} { error "Whole four sectors changed after cache invalidation" }'],
  ]) result = replaceOne(result, before, after);
  const dependencyGlobals = globals + ' nmri_net_original_words nmri_net_patched_words';
  requireThat(result.split(dependencyGlobals).length === 4, 'Three dependency orchestration globals changed');
  result = result.replaceAll(dependencyGlobals, dependencyGlobals + ' nmri_codec_original_words nmri_codec_patched_words');
  for (const [before, after] of [
    ['allowlisted to four exact reviewed A7 app sectors', 'allowlisted to five exact reviewed A7 app sectors'],
    ['    } else { error "Unreviewed sector" }',
      '    } elseif {$label == "codec"} {\n        set address 0x28927000\n' +
      '        if {$expected != $nmri_codec_original_words && $expected != $nmri_codec_patched_words} { error "Unreviewed codec-sector comparison source" }\n' +
      '    } else { error "Unreviewed sector" }'],
    ['    } else { error "Sector helper admits only exact reviewed net/code/table/aux stages" }',
      '    } elseif {$prefix == "install-codec"} { set fixed_words $nmri_codec_patched_words\n' +
      '    } elseif {$prefix == "restore-codec"} { set fixed_words $nmri_codec_original_words\n' +
      '    } else { error "Sector helper admits only exact reviewed codec/net/code/table/aux stages" }'],
    ['fixedsectors92d000/95a000/92b000/ccd000 only', 'fixedsectors927000/92d000/95a000/92b000/ccd000 only'],
    ['        set net_before [nmr_words 0x2892d000 1024]',
      '        set net_before [nmr_words 0x2892d000 1024]\n        set codec_before [nmr_words 0x28927000 1024]'],
    ['$net_before != $nmri_net_original_words} { error "Install requires all four exact image-drawer sector baselines" }',
      '$net_before != $nmri_net_original_words || $codec_before != $nmri_codec_original_words} { error "Install requires all five exact image-drawer/stock sector baselines" }'],
    ['&& $net_before == $nmri_net_original_words) ||', '&& $net_before == $nmri_net_original_words && $codec_before == $nmri_codec_original_words) ||'],
    ['&& $net_before == $nmri_net_patched_words))}', '&& $net_before == $nmri_net_patched_words && $codec_before == $nmri_codec_patched_words))}'],
    ['Restore requires all four exact image-drawer or all four exact maintained sector baselines',
      'Restore requires all five exact image-drawer/stock or all five exact maintained sector baselines'],
    ['        dump_image [file join $capture_dir sector-net-before.bin] 0x2892d000 4096',
      '        dump_image [file join $capture_dir sector-net-before.bin] 0x2892d000 4096\n' +
      '        dump_image [file join $capture_dir sector-codec-before.bin] 0x28927000 4096'],
    ['            # Install dependencies before any main/entry reference can point to them.',
      '            # Install dependencies before any main/entry reference can point to them.\n' +
      '            nmr_write_sector $capture_dir install-codec $nmri_codec_patched_words $original_bp $remove_fpb_command\n' +
      '            nmr_verify_sector $capture_dir codec $nmri_codec_patched_words\n' +
      '            nmr_status_stage [file join $capture_dir status-codec] unprotected $original_sr1 $original_sr2 $remove_fpb_command'],
    ['set expected_net $nmri_net_patched_words', 'set expected_net $nmri_net_patched_words; set expected_codec $nmri_codec_patched_words'],
    ['            nmr_verify_sector $capture_dir net $nmri_net_original_words',
      '            nmr_verify_sector $capture_dir net $nmri_net_original_words\n' +
      '            nmr_status_stage [file join $capture_dir status-net-restored] unprotected $original_sr1 $original_sr2 $remove_fpb_command\n' +
      '            nmr_write_sector $capture_dir restore-codec $nmri_codec_original_words $original_bp $remove_fpb_command\n' +
      '            nmr_verify_sector $capture_dir codec $nmri_codec_original_words'],
    ['set expected_net $nmri_net_original_words', 'set expected_net $nmri_net_original_words; set expected_codec $nmri_codec_original_words'],
    ['foreach sector {net aux code table}', 'foreach sector {codec net aux code table}'],
    ['[nmr_words 0x2892d000 1024] != $expected_net} { error "Whole four sectors changed after cache invalidation" }',
      '[nmr_words 0x2892d000 1024] != $expected_net || [nmr_words 0x28927000 1024] != $expected_codec} { error "Whole five sectors changed after cache invalidation" }'],
  ]) result = replaceOne(result, before, after);
  return result;
}
function cloneStages(tail: string) {
  let result = names(tail);
  for (const [before, after] of [
    ['nmri_aux_original_words nmri_aux_patched_words}', 'nmri_aux_original_words nmri_aux_patched_words nmri_net_original_words nmri_net_patched_words}'],
    ['nmri_aux_original_words nmri_aux_patched_words\n', 'nmri_aux_original_words nmri_aux_patched_words nmri_net_original_words nmri_net_patched_words\n'],
    ['        } else { set address 0x28ccd000 }', '        } elseif {[string match "*-net" $prefix]} { set address 0x2892d000\n        } else { set address 0x28ccd000 }'],
    ['        } else { set sector $nmri_aux_original_words; set address 0x2895a000 }',
      '        } elseif {$prefix == "restore-aux"} { set sector $nmri_aux_original_words; set address 0x2895a000\n' +
      '        } elseif {$prefix == "install-net"} { set sector $nmri_net_patched_words; set address 0x2892d000\n' +
      '        } else { set sector $nmri_net_original_words; set address 0x2892d000 }'],
    ['        } else { set address 0x2cccd000 }', '        } elseif {$label == "net"} { set address 0x2c92d000\n        } else { set address 0x2cccd000 }'],
    ['^invalidate-(code|table|aux)-(i|d)$', '^invalidate-(code|table|aux|net)-(i|d)$'],
  ]) result = replaceOne(result, before, after);
  const prefixes = 'install-code|install-table|install-aux|restore-table|restore-code|restore-aux';
  requireThat(result.split(prefixes).length === 3, 'Exactly two erase/page prefix whitelists required');
  result = result.replaceAll(prefixes, prefixes + '|install-net|restore-net');
  for (const [before, after] of [
    ['nmri_net_original_words nmri_net_patched_words}', 'nmri_net_original_words nmri_net_patched_words nmri_codec_original_words nmri_codec_patched_words}'],
    ['nmri_net_original_words nmri_net_patched_words\n', 'nmri_net_original_words nmri_net_patched_words nmri_codec_original_words nmri_codec_patched_words\n'],
    ['        } else { set address 0x28ccd000 }', '        } elseif {[string match "*-codec" $prefix]} { set address 0x28927000\n        } else { set address 0x28ccd000 }'],
    ['        } else { set sector $nmri_net_original_words; set address 0x2892d000 }',
      '        } elseif {$prefix == "restore-net"} { set sector $nmri_net_original_words; set address 0x2892d000\n' +
      '        } elseif {$prefix == "install-codec"} { set sector $nmri_codec_patched_words; set address 0x28927000\n' +
      '        } else { set sector $nmri_codec_original_words; set address 0x28927000 }'],
    ['        } else { set address 0x2cccd000 }', '        } elseif {$label == "codec"} { set address 0x2c927000\n        } else { set address 0x2cccd000 }'],
    ['^invalidate-(code|table|aux|net)-(i|d)$', '^invalidate-(code|table|aux|net|codec)-(i|d)$'],
  ]) result = replaceOne(result, before, after);
  const allPrefixes = prefixes + '|install-net|restore-net';
  requireThat(result.split(allPrefixes).length === 3, 'Exactly two dependency erase/page prefix whitelists required');
  return result.replaceAll(allPrefixes, allPrefixes + '|install-codec|restore-codec');
}
function tclWords(name: string, bytes: Buffer) {
  requireThat(bytes.length % 4 === 0, 'Tcl words need aligned input');
  const lines = [`set ${name} {`];
  for (let offset = 0; offset < bytes.length; offset += 32) {
    const words = [];
    for (let pos = offset; pos < Math.min(offset + 32, bytes.length); pos += 4)
      words.push('0x' + bytes.readUInt32LE(pos).toString(16).padStart(8, '0'));
    lines.push('    ' + words.join(' '));
  }
  return lines.join('\n') + '\n}\n';
}
function callerFromStages(text: string) {
  const match = text.match(/set nidi_one_call_words \{([^}]+)\}/);
  requireThat(match, 'Frozen caller words missing');
  const words = match[1].trim().split(/\s+/).map(Number), bytes = Buffer.alloc(words.length * 4);
  words.forEach((value, index) => bytes.writeUInt32LE(value, index * 4));
  requireThat(bytes.length === 168 && sha256(bytes) === CALLER_SHA, 'Reviewed 168B caller drift');
  return bytes;
}
export const NET_MOCK_CASES = ['baseline_net_mismatch', 'restore_baseline_net_mismatch',
  'mixed_image_triple_maintained_net', 'mixed_maintained_triple_stock_net', 'install_net_only',
  'net_native_error', 'restore_net_native_error', 'net_erase_native_error', 'net_erase_timeout',
  'net_program_timeout', 'net_whole_readback_mismatch', 'net_qe_changed', 'net_wip_status',
  'net_protection_changed', 'net_posted_transport_timeout_wip1', 'net_reset', 'net_fault',
  'net_invalidate_native_error', 'net_changed_after_invalidation', 'net_page16_refusal',
  'net_wrong_source_refusal', 'net_arbitrary_stage_refusal', 'net_erase_delayed'];
export const CODEC_MOCK_CASES = ['baseline_codec_mismatch', 'restore_baseline_codec_mismatch',
  'mixed_image_four_maintained_codec', 'mixed_maintained_four_stock_codec', 'install_codec_only',
  'codec_native_error', 'restore_codec_native_error', 'codec_erase_native_error', 'codec_erase_timeout',
  'codec_program_timeout', 'codec_whole_readback_mismatch', 'codec_qe_changed', 'codec_wip_status',
  'codec_protection_changed', 'codec_posted_transport_timeout_wip1', 'codec_reset', 'codec_fault',
  'codec_invalidate_native_error', 'codec_changed_after_invalidation', 'codec_page16_refusal',
  'codec_wrong_source_refusal', 'codec_arbitrary_stage_refusal', 'codec_erase_delayed'];
export const WRITER_MOCK_CASES = [
  'install_bp0', 'install_bp7c', 'restore_bp0', 'restore_bp7c', 'restore_fast_tap_baseline',
  'baseline_table_mismatch', 'baseline_code_mismatch', 'restore_baseline_table_mismatch', 'restore_baseline_code_mismatch',
  'reset_code', 'fault_code', 'native_error_code', 'posted_transport_timeout_wip1', 'code_whole_readback_mismatch',
  'qe_changed_code', 'wip_status_code', 'active_watchdog', 'watchdog_reenabled', 'initialized_config_changed',
  'erase_delayed', 'erase_timeout', 'program_timeout', 'read_timeout', 'arbitrary_callee', 'arbitrary_mode',
  'arbitrary_stage', 'arbitrary_helper_prefix', 'arbitrary_helper_words', 'partial_table_fixed_restore',
  'install_image_drawer_baseline', 'tap_v1_baseline_code', 'tap_v1_baseline_pair', 'card_baseline_code', 'card_baseline_pair',
  'stock_aux_baseline', 'smooth_baseline_code', 'smooth_baseline_pair', 'ease_baseline_code', 'ease_baseline_pair',
  'first_drawer_baseline_code', 'first_drawer_baseline_pair', 'broker_baseline_code', 'broker_baseline_table',
  'broker_baseline_pair', 'stock_baseline_code', 'stock_baseline_table', 'stock_baseline_pair',
  'counter_baseline_code', 'counter_baseline_table', 'counter_baseline_pair', 'baseline_aux_mismatch',
  'restore_baseline_aux_mismatch', 'mixed_image_code_fast_aux', 'mixed_fast_code_image_aux', 'install_image_aux_only',
  'aux_reset', 'aux_fault', 'aux_native_error', 'aux_program_timeout', 'aux_erase_timeout',
  'aux_whole_readback_mismatch', 'aux_qe_changed', 'aux_wip_status', 'restore_aux_native_error', 'table_native_error',
  'aux_invalidate_native_error', 'aux_changed_after_invalidation', 'aux_page16_refusal', 'aux_wrong_source_refusal',
  'aux_arbitrary_stage_refusal', ...NET_MOCK_CASES, ...CODEC_MOCK_CASES,
];

// A private extension of the frozen independent Jim model. Exact anchors refuse drift;
// native actions remain simulated from r0..r3 and exact raw full-page fixtures.
export function cloneMock(text: string) {
  let mock = names(text);
  const change = (before: string, after: string) => { mock = replaceOne(mock, before, after); };
  change('previous = (ROOT / f"analysis/persistence/native-github-tap-fast-patched-sector-{offset:x}.bin").read_bytes()',
    'previous = (ROOT / f"analysis/persistence/native-image-drawer-patched-sector-{offset:x}.bin").read_bytes()');
  mock = mock.replaceAll('rollback is not the exact frozen fast-tap triple', 'rollback is not the exact frozen image-drawer triple');
  const triples = '[("table", 0xccd000), ("code", 0x92b000), ("aux", 0x95a000)]';
  // Only the initial independent fixture loop includes net; the rollback fixture
  // loop separately binds original net to the stock full backup below.
  change('for label, offset in ' + triples + ':\n    for state',
    'for label, offset in [("table", 0xccd000), ("code", 0x92b000), ("aux", 0x95a000), ("net", 0x92d000)]:\n    for state');
  change('source = (ROOT / "analysis/persistence/mock_boot_read_runner.tcl").read_text()',
    'stock_net = (ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin").read_bytes()[0x92d000:0x92e000]\n' +
    'assert fixture["net", "original"] == stock_net, "Network rollback is not exact stock page"\n' +
    'source = (ROOT / "analysis/persistence/mock_boot_read_runner.tcl").read_text()');
  change('nmri_aux_patched_words $mock_aux_patched]', 'nmri_aux_patched_words $mock_aux_patched nmri_net_original_words $mock_net_original nmri_net_patched_words $mock_net_patched]');
  change('table 0x28ccd000 code 0x2892b000 aux 0x2895a000}', 'table 0x28ccd000 code 0x2892b000 aux 0x2895a000 net 0x2892d000}');
  change('set mock_aux_programmed 0', 'set mock_aux_programmed 0\nset mock_net_erased 0\nset mock_net_programmed 0\nset mock_net_verified 0\nset mock_net_original_verified 0\nset mock_aux_original_verified 0');
  change('if {$mock_mode == "active_watchdog"}', String.raw`
if {$mock_mode in {baseline_net_mismatch restore_baseline_net_mismatch}} {
    set mock_mem([expr {0x2892dffc}]) [expr {$mock_mem([expr {0x2892dffc}]) ^ 1}]
}
if {$mock_mode in {mixed_image_triple_maintained_net mixed_maintained_triple_stock_net install_net_only}} {
    if {$mock_mode != "install_net_only"} { set mock_flow restore }
    set mixed_state original
    if {$mock_mode == "mixed_maintained_triple_stock_net"} { set mixed_state patched }
    foreach {label address} {table 0x28ccd000 code 0x2892b000 aux 0x2895a000} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {$address+4*$i}]) [lindex [set [format "mock_%s_%s" $label $mixed_state]] $i] }
    }
    set mixed_net patched
    if {$mock_mode == "mixed_maintained_triple_stock_net"} { set mixed_net original }
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x2892d000+4*$i}]) [lindex [set [format "mock_net_%s" $mixed_net]] $i] }
}
if {$mock_mode == "active_watchdog"}`);
  change('    return $result\n}\'\'\', 1)', String.raw`
    if {$count == 1024 && $address == 0x2892d000 && $::mock_net_erased && $result == $::mock_net_patched} {
        set ::mock_net_verified 1
        lappend ::mock_order verify_net_4k
    }
    if {$count == 1024 && $address == 0x2892d000 && $::mock_net_erased && $result == $::mock_net_original} {
        set ::mock_net_original_verified 1
        lappend ::mock_order verify_original_net_4k
    }
    if {$count == 1024 && $address == 0x2895a000 && $::mock_aux_erased && $result == $::mock_aux_original} {
        set ::mock_aux_original_verified 1
        lappend ::mock_order verify_original_aux_4k
    }
    return $result
}''', 1)`);
  change('                            } else { error "Arbitrary NOR program address" }', String.raw`
                            } elseif {$arg1 >= 0x2892d000 && $arg1 < 0x2892e000 && $::mock_flow in {install restore}} {
                                if {!$::mock_net_erased} { error "Net programmed without erase" }
                                if {$::mock_flow == "restore" && (!$::mock_table_restored_verified || !$::mock_code_original_verified || !$::mock_aux_original_verified)} { error "Net restored before main/table/aux whole verification" }
                                set page [expr {($arg1-0x2892d000)/256}]
                                if {$::mock_flow == "install"} { set wanted $::mock_net_patched } else { set wanted $::mock_net_original }
                                set tag program_net_$page
                            } else { error "Arbitrary NOR program address" }`);
  change('                            if {$tag == "program_aux_0"} {', String.raw`
                            if {$tag == "program_net_0"} {
                                set ::mock_net_programmed 1
                                if {$mock_mode in {net_native_error restore_net_native_error}} { set ret 7; set ::mock_failed_run 1 }
                                if {$mock_mode == "net_program_timeout"} { set ::mock_delay_remaining 400; set ::mock_failed_run 1 }
                                if {$mock_mode == "net_posted_transport_timeout_wip1"} { set ::mock_sr1 1; set ::mock_posted_transport_pending 1 }
                            }
                            if {$tag == "program_net_15"} {
                                if {$mock_mode == "net_whole_readback_mismatch"} { set mock_mem([expr {0x2892dffc}]) [expr {$mock_mem([expr {0x2892dffc}]) ^ 1}] }
                                if {$mock_mode == "net_qe_changed"} { set ::mock_sr2 0 }
                                if {$mock_mode == "net_wip_status"} { set ::mock_sr1 1 }
                                if {$mock_mode == "net_protection_changed"} { set ::mock_sr1 4 }
                            }
                            if {$tag == "program_aux_0"} {`);
  change('                                if {$::mock_flow == "install" && ($::mock_code_erased || $::mock_table_erased)} { error "Aux install after main/entry erase" }',
    '                                if {$::mock_flow == "install" && (!$::mock_net_verified || $::mock_code_erased || $::mock_table_erased)} { error "Aux install before net verify or after main/entry erase" }');
  change('                            } else { error "Arbitrary NOR erase address" }', String.raw`
                            } elseif {$arg1 == 0x2892d000 && $::mock_flow in {install restore}} {
                                if {$::mock_flow == "install" && ($::mock_aux_erased || $::mock_code_erased || $::mock_table_erased)} { error "Net install after dependent-page erase" }
                                if {$::mock_flow == "restore" && (!$::mock_table_restored_verified || !$::mock_code_original_verified || !$::mock_aux_original_verified)} { error "Net restore before main/table/aux original verification" }
                                if {$::mock_net_erased} { error "Repeated net erase" }
                                set ::mock_net_erased 1
                                set tag erase_net
                            } else { error "Arbitrary NOR erase address" }`);
  change('                            if {$mock_mode == "erase_delayed" && $tag == "erase_code"}',
    '                            if {$mock_mode == "net_erase_native_error" && $tag == "erase_net"} { set ret 7; set ::mock_failed_run 1 }\n' +
    '                            if {$mock_mode == "net_erase_timeout" && $tag == "erase_net"} { set ::mock_delay_remaining 2000; set ::mock_failed_run 1 }\n' +
    '                            if {$mock_mode == "net_erase_delayed" && $tag == "erase_net"} { set ::mock_delay_remaining 60 }\n' +
    '                            if {$mock_mode == "erase_delayed" && $tag == "erase_code"}');
  change('($arg1 != 0x2cccd000 && $arg1 != 0x2c92b000 && $arg1 != 0x2c95a000)',
    '($arg1 != 0x2cccd000 && $arg1 != 0x2c92b000 && $arg1 != 0x2c95a000 && $arg1 != 0x2c92d000)');
  change('                            set tag [format "invalidate_%08x_%d" $arg1 $arg0]',
    '                            if {$arg1 == 0x2c92d000 && $mock_mode == "net_invalidate_native_error"} { set ret 7; set ::mock_failed_run 1 }\n' +
    '                            if {$arg1 == 0x2cccd000 && $arg0 == 1 && $mock_mode == "net_changed_after_invalidation"} { set mock_mem([expr {0x2892dffc}]) [expr {$mock_mem([expr {0x2892dffc}]) ^ 1}] }\n' +
    '                            set tag [format "invalidate_%08x_%d" $arg1 $arg0]');
  change('                if {$::mock_aux_programmed && $mock_mode == "aux_reset"}',
    '                if {$::mock_net_programmed && $mock_mode == "net_reset"} { set mock_mem($addr) 0x0213000b; set ::mock_failed_run 1 }\n' +
    '                if {$::mock_net_programmed && $mock_mode == "net_fault"} { set mock_mem([expr {0xe000ed28}]) 1; set mock_regs(16) 0x01000003; set ::mock_failed_run 1 }\n' +
    '                if {$::mock_aux_programmed && $mock_mode == "aux_reset"}');
  change('$address in {0x28ccd000 0x2892b000 0x2895a000}', '$address in {0x28ccd000 0x2892b000 0x2895a000 0x2892d000}');
  change('if {$mock_mode == "aux_page16_refusal"} {', String.raw`
if {$mock_mode == "net_page16_refusal"} {
    file mkdir $panel_maintained_mock_output
    set mock_error [catch {nmr_execute_call [file join $panel_maintained_mock_output refused] onecall install-net-page-16 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "net_wrong_source_refusal"} {
    set wrong [lreplace $nmri_net_patched_words 0 0 0xffffffff]
    set mock_error [catch {nmr_write_sector $panel_maintained_mock_output install-net $wrong 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "net_arbitrary_stage_refusal"} {
    file mkdir $panel_maintained_mock_output
    set mock_error [catch {nmr_execute_call [file join $panel_maintained_mock_output refused] onecall install-net-page-0-other 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "aux_page16_refusal"} {`);
  change('set install_aux [mock_sector_mutations aux patched]',
    'set install_net [mock_sector_mutations net patched]\nset restore_net [mock_sector_mutations net original]\n' +
    'set install_aux [concat $install_net [mock_sector_mutations aux patched]]');
  change('erase_delayed partial_table_fixed_restore}}]', 'erase_delayed net_erase_delayed partial_table_fixed_restore}}]');
  change('set final_aux $mock_aux_patched\n        set expected_mutations [concat $install_aux',
    'set final_aux $mock_aux_patched; set final_net $mock_net_patched\n        set expected_mutations [concat $install_aux');
  change('set final_aux $mock_aux_original\n        set expected_mutations [concat $restore_table $restore_code $restore_aux]',
    'set final_aux $mock_aux_original; set final_net $mock_net_original\n        set expected_mutations [concat $restore_table $restore_code $restore_aux $restore_net]');
  change('set final_aux $mock_aux_patched\n        set expected_mutations $restore_table',
    'set final_aux $mock_aux_patched; set final_net $mock_net_original\n        set expected_mutations $restore_table');
  change('0x2895a000 $final_aux]', '0x2895a000 $final_aux 0x2892d000 $final_net]');
  change('{invalidate_2c95a000_0 invalidate_2c95a000_1', '{invalidate_2c92d000_0 invalidate_2c92d000_1 invalidate_2c95a000_0 invalidate_2c95a000_1');
  change('if {$mock_mode == "erase_delayed" && ($mock_delayed_samples', 'if {$mock_mode in {erase_delayed net_erase_delayed} && ($mock_delayed_samples');
  const refusals = NET_MOCK_CASES.filter(name => name.includes('baseline') || name.startsWith('mixed_') ||
    name === 'install_net_only' || name.endsWith('_refusal'));
  change('if {$mock_mode in {baseline_table_mismatch ', 'if {$mock_mode in {' + refusals.join(' ') + ' baseline_table_mismatch ');
  change('$mock_mutation_calls != {erase_aux program_aux_0}', '$mock_mutation_calls != [concat $install_net {erase_aux program_aux_0}]');
  change('set wanted {erase_aux}', 'set wanted [concat $install_net erase_aux]');
  change('    } elseif {$mock_mode in {aux_reset aux_fault aux_native_error aux_program_timeout}} {', String.raw`
    } elseif {$mock_mode in {net_reset net_fault net_native_error net_program_timeout net_posted_transport_timeout_wip1 net_erase_native_error net_erase_timeout}} {
        set wanted {erase_net program_net_0}
        if {$mock_mode in {net_erase_native_error net_erase_timeout}} { set wanted {erase_net} }
        if {$mock_mutation_calls != $wanted || !$mock_failed_run || $mock_stale_replay || !$nmr_flash_mutation_possible} { error "Unclosed net execution admitted later mutation/stale replay" }
        if {$mock_regs(15) == 0x0c0104c6 || $mock_mem($mock_scratch_base) == 0xab000000} { error "Stale net PC/scratch replayed" }
        if {$mock_mode == "net_program_timeout" && ($mock_virtual_ms != 1000 || $mock_delayed_samples < 201)} { error "Net program budget not1000ms" }
        if {$mock_mode == "net_erase_timeout" && ($mock_virtual_ms != 5000 || $mock_delayed_samples < 1001)} { error "Net erase budget not5000ms" }
    } elseif {$mock_mode in {net_whole_readback_mismatch net_qe_changed net_wip_status net_protection_changed}} {
        if {$mock_mutation_calls != $install_net || !$nmr_flash_mutation_possible} { error "Net verification/status failure admitted aux/code/table erase" }
        mock_assert_original_context
    } elseif {$mock_mode == "restore_net_native_error"} {
        if {$mock_mutation_calls != [concat $restore_table $restore_code $restore_aux {erase_net program_net_0}] || !$mock_aux_original_verified || !$mock_code_original_verified || !$mock_table_restored_verified || !$mock_failed_run || $mock_stale_replay} { error "Restore net error admitted wrong order or stale replay" }
    } elseif {$mock_mode in {net_invalidate_native_error net_changed_after_invalidation}} {
        if {$mock_mutation_calls != [concat $install_aux $install_code $install_table]} { error "Net cache closure performed unexpected mutation" }
        if {$mock_mode == "net_invalidate_native_error" && (!$mock_failed_run || $mock_stale_replay)} { error "Unclosed net cache call replayed context" }
        if {$mock_mode == "net_changed_after_invalidation"} { mock_assert_original_context }
    } elseif {$mock_mode in {aux_reset aux_fault aux_native_error aux_program_timeout}} {`);
  change('hashes = {str(p.relative_to(ROOT)):', 'cases += ' + JSON.stringify(NET_MOCK_CASES) + '\n' +
    'assert len(cases) == 93 and set(cases) == set(' + JSON.stringify(WRITER_MOCK_CASES) + '), "Four-page mock coverage drift"\n' +
    'hashes = {str(p.relative_to(ROOT)):');
  mock = mock.replaceAll('panel_maintained_three_page_writer.py', 'panel-maintained-writer-derivation.json')
    .replaceAll('Three-page', 'Four-page').replaceAll('three-page', 'four-page').replaceAll('All three I/D', 'All four I/D')
    .replaceAll('original fixture means exact frozen fast-tap triple;', 'original fixture means exact frozen image-drawer triple plus stock network page;');
  change('("net", 0x92d000)]:\n    for state', '("net", 0x92d000), ("codec", 0x927000)]:\n    for state');
  change('source = (ROOT / "analysis/persistence/mock_boot_read_runner.tcl").read_text()',
    'stock_codec = (ROOT / "backups/mi-panel-flash-16m-1.50.10-20261004.bin").read_bytes()[0x927000:0x928000]\n' +
    'assert fixture["codec", "original"] == stock_codec, "Codec rollback is not exact stock page"\n' +
    'source = (ROOT / "analysis/persistence/mock_boot_read_runner.tcl").read_text()');
  change('nmri_net_patched_words $mock_net_patched]', 'nmri_net_patched_words $mock_net_patched nmri_codec_original_words $mock_codec_original nmri_codec_patched_words $mock_codec_patched]');
  change('aux 0x2895a000 net 0x2892d000}', 'aux 0x2895a000 net 0x2892d000 codec 0x28927000}');
  change('set mock_net_erased 0', 'set mock_codec_erased 0\nset mock_codec_programmed 0\nset mock_codec_verified 0\nset mock_net_erased 0');
  change('if {$mock_mode == "active_watchdog"}', String.raw`
if {$mock_mode in {baseline_codec_mismatch restore_baseline_codec_mismatch}} {
    set mock_mem([expr {0x28927ffc}]) [expr {$mock_mem([expr {0x28927ffc}]) ^ 1}]
}
if {$mock_mode in {mixed_image_four_maintained_codec mixed_maintained_four_stock_codec install_codec_only}} {
    if {$mock_mode != "install_codec_only"} { set mock_flow restore }
    set mixed_state original
    if {$mock_mode == "mixed_maintained_four_stock_codec"} { set mixed_state patched }
    foreach {label address} {table 0x28ccd000 code 0x2892b000 aux 0x2895a000 net 0x2892d000} {
        for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {$address+4*$i}]) [lindex [set [format "mock_%s_%s" $label $mixed_state]] $i] }
    }
    set mixed_codec patched
    if {$mock_mode == "mixed_maintained_four_stock_codec"} { set mixed_codec original }
    for {set i 0} {$i < 1024} {incr i} { set mock_mem([expr {0x28927000+4*$i}]) [lindex [set [format "mock_codec_%s" $mixed_codec]] $i] }
}
if {$mock_mode == "active_watchdog"}`);
  change('    return $result\n}\'\'\', 1)', String.raw`
    if {$count == 1024 && $address == 0x28927000 && $::mock_codec_erased && $result == $::mock_codec_patched} {
        set ::mock_codec_verified 1
        lappend ::mock_order verify_codec_4k
    }
    return $result
}''', 1)`);
  change('                            } else { error "Arbitrary NOR program address" }', String.raw`
                            } elseif {$arg1 >= 0x28927000 && $arg1 < 0x28928000 && $::mock_flow in {install restore}} {
                                if {!$::mock_codec_erased} { error "Codec programmed without erase" }
                                if {$::mock_flow == "restore" && (!$::mock_table_restored_verified || !$::mock_code_original_verified || !$::mock_aux_original_verified || !$::mock_net_original_verified)} { error "Codec restored before main/table/aux/net whole verification" }
                                set page [expr {($arg1-0x28927000)/256}]
                                if {$::mock_flow == "install"} { set wanted $::mock_codec_patched } else { set wanted $::mock_codec_original }
                                set tag program_codec_$page
                            } else { error "Arbitrary NOR program address" }`);
  change('                            if {$tag == "program_net_0"} {', String.raw`
                            if {$tag == "program_codec_0"} {
                                set ::mock_codec_programmed 1
                                if {$mock_mode in {codec_native_error restore_codec_native_error}} { set ret 7; set ::mock_failed_run 1 }
                                if {$mock_mode == "codec_program_timeout"} { set ::mock_delay_remaining 400; set ::mock_failed_run 1 }
                                if {$mock_mode == "codec_posted_transport_timeout_wip1"} { set ::mock_sr1 1; set ::mock_posted_transport_pending 1 }
                            }
                            if {$tag == "program_codec_15"} {
                                if {$mock_mode == "codec_whole_readback_mismatch"} { set mock_mem([expr {0x28927ffc}]) [expr {$mock_mem([expr {0x28927ffc}]) ^ 1}] }
                                if {$mock_mode == "codec_qe_changed"} { set ::mock_sr2 0 }
                                if {$mock_mode == "codec_wip_status"} { set ::mock_sr1 1 }
                                if {$mock_mode == "codec_protection_changed"} { set ::mock_sr1 4 }
                            }
                            if {$tag == "program_net_0"} {`);
  change('if {!$::mock_net_erased} { error "Net programmed without erase" }',
    'if {!$::mock_net_erased} { error "Net programmed without erase" }\n' +
    '                                if {$::mock_flow == "install" && !$::mock_codec_verified} { error "Net programmed before codec whole verification" }');
  change('if {$::mock_flow == "install" && ($::mock_aux_erased || $::mock_code_erased || $::mock_table_erased)} { error "Net install after dependent-page erase" }',
    'if {$::mock_flow == "install" && (!$::mock_codec_verified || $::mock_aux_erased || $::mock_code_erased || $::mock_table_erased)} { error "Net install before codec verify or after dependent-page erase" }');
  change('                            } else { error "Arbitrary NOR erase address" }', String.raw`
                            } elseif {$arg1 == 0x28927000 && $::mock_flow in {install restore}} {
                                if {$::mock_flow == "install" && ($::mock_net_erased || $::mock_aux_erased || $::mock_code_erased || $::mock_table_erased)} { error "Codec install after dependent-page erase" }
                                if {$::mock_flow == "restore" && (!$::mock_table_restored_verified || !$::mock_code_original_verified || !$::mock_aux_original_verified || !$::mock_net_original_verified)} { error "Codec restore before main/table/aux/net original verification" }
                                if {$::mock_codec_erased} { error "Repeated codec erase" }
                                set ::mock_codec_erased 1
                                set tag erase_codec
                            } else { error "Arbitrary NOR erase address" }`);
  change('                            if {$mock_mode == "erase_delayed" && $tag == "erase_code"}',
    '                            if {$mock_mode == "codec_erase_native_error" && $tag == "erase_codec"} { set ret 7; set ::mock_failed_run 1 }\n' +
    '                            if {$mock_mode == "codec_erase_timeout" && $tag == "erase_codec"} { set ::mock_delay_remaining 2000; set ::mock_failed_run 1 }\n' +
    '                            if {$mock_mode == "codec_erase_delayed" && $tag == "erase_codec"} { set ::mock_delay_remaining 60 }\n' +
    '                            if {$mock_mode == "erase_delayed" && $tag == "erase_code"}');
  change('&& $arg1 != 0x2c92d000)', '&& $arg1 != 0x2c92d000 && $arg1 != 0x2c927000)');
  change('                            set tag [format "invalidate_%08x_%d" $arg1 $arg0]',
    '                            if {$arg1 == 0x2c927000 && $mock_mode == "codec_invalidate_native_error"} { set ret 7; set ::mock_failed_run 1 }\n' +
    '                            if {$arg1 == 0x2cccd000 && $arg0 == 1 && $mock_mode == "codec_changed_after_invalidation"} { set mock_mem([expr {0x28927ffc}]) [expr {$mock_mem([expr {0x28927ffc}]) ^ 1}] }\n' +
    '                            set tag [format "invalidate_%08x_%d" $arg1 $arg0]');
  change('                if {$::mock_net_programmed && $mock_mode == "net_reset"}',
    '                if {$::mock_codec_programmed && $mock_mode == "codec_reset"} { set mock_mem($addr) 0x0213000b; set ::mock_failed_run 1 }\n' +
    '                if {$::mock_codec_programmed && $mock_mode == "codec_fault"} { set mock_mem([expr {0xe000ed28}]) 1; set mock_regs(16) 0x01000003; set ::mock_failed_run 1 }\n' +
    '                if {$::mock_net_programmed && $mock_mode == "net_reset"}');
  change('$address in {0x28ccd000 0x2892b000 0x2895a000 0x2892d000}', '$address in {0x28ccd000 0x2892b000 0x2895a000 0x2892d000 0x28927000}');
  change('if {$mock_mode == "net_page16_refusal"} {', String.raw`
if {$mock_mode == "codec_page16_refusal"} {
    file mkdir $panel_maintained_mock_output
    set mock_error [catch {nmr_execute_call [file join $panel_maintained_mock_output refused] onecall install-codec-page-16 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "codec_wrong_source_refusal"} {
    set wrong [lreplace $nmri_codec_patched_words 0 0 0xffffffff]
    set mock_error [catch {nmr_write_sector $panel_maintained_mock_output install-codec $wrong 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "codec_arbitrary_stage_refusal"} {
    file mkdir $panel_maintained_mock_output
    set mock_error [catch {nmr_execute_call [file join $panel_maintained_mock_output refused] onecall install-codec-page-0-other 0 mock_remove_fpb} mock_message]
} elseif {$mock_mode == "net_page16_refusal"} {`);
  change('set install_net [mock_sector_mutations net patched]',
    'set install_codec [mock_sector_mutations codec patched]\nset restore_codec [mock_sector_mutations codec original]\n' +
    'set install_net [concat $install_codec [mock_sector_mutations net patched]]');
  change('net_erase_delayed partial_table_fixed_restore}}]', 'net_erase_delayed codec_erase_delayed partial_table_fixed_restore}}]');
  change('set final_net $mock_net_patched\n        set expected_mutations', 'set final_net $mock_net_patched; set final_codec $mock_codec_patched\n        set expected_mutations');
  // Both normal restore and the separately supervised table-only case keep exact codec stock bytes.
  mock = mock.replaceAll('set final_net $mock_net_original\n        set expected_mutations', 'set final_net $mock_net_original; set final_codec $mock_codec_original\n        set expected_mutations');
  change('[concat $restore_table $restore_code $restore_aux $restore_net]', '[concat $restore_table $restore_code $restore_aux $restore_net $restore_codec]');
  change('0x2892d000 $final_net]', '0x2892d000 $final_net 0x28927000 $final_codec]');
  change('{invalidate_2c92d000_0 invalidate_2c92d000_1', '{invalidate_2c927000_0 invalidate_2c927000_1 invalidate_2c92d000_0 invalidate_2c92d000_1');
  change('if {$mock_mode in {erase_delayed net_erase_delayed} &&', 'if {$mock_mode in {erase_delayed net_erase_delayed codec_erase_delayed} &&');
  const codecRefusals = CODEC_MOCK_CASES.filter(name => name.includes('baseline') || name.startsWith('mixed_') ||
    name === 'install_codec_only' || name.endsWith('_refusal'));
  const netRefusalHead = 'if {$mock_mode in {baseline_net_mismatch restore_baseline_net_mismatch mixed_image_triple_maintained_net';
  change(netRefusalHead, 'if {$mock_mode in {' + codecRefusals.join(' ') + ' baseline_net_mismatch restore_baseline_net_mismatch mixed_image_triple_maintained_net');
  change('set wanted {erase_net program_net_0}', 'set wanted [concat $install_codec {erase_net program_net_0}]');
  change('{ set wanted {erase_net} }', '{ set wanted [concat $install_codec erase_net] }');
  change('    } elseif {$mock_mode in {net_reset net_fault net_native_error net_program_timeout net_posted_transport_timeout_wip1 net_erase_native_error net_erase_timeout}} {', String.raw`
    } elseif {$mock_mode in {codec_reset codec_fault codec_native_error codec_program_timeout codec_posted_transport_timeout_wip1 codec_erase_native_error codec_erase_timeout}} {
        set wanted {erase_codec program_codec_0}
        if {$mock_mode in {codec_erase_native_error codec_erase_timeout}} { set wanted {erase_codec} }
        if {$mock_mutation_calls != $wanted || !$mock_failed_run || $mock_stale_replay || !$nmr_flash_mutation_possible} { error "Unclosed codec execution admitted later mutation/stale replay" }
        if {$mock_regs(15) == 0x0c0104c6 || $mock_mem($mock_scratch_base) == 0xab000000} { error "Stale codec PC/scratch replayed" }
        if {$mock_mode == "codec_program_timeout" && ($mock_virtual_ms != 1000 || $mock_delayed_samples < 201)} { error "Codec program budget not1000ms" }
        if {$mock_mode == "codec_erase_timeout" && ($mock_virtual_ms != 5000 || $mock_delayed_samples < 1001)} { error "Codec erase budget not5000ms" }
    } elseif {$mock_mode in {codec_whole_readback_mismatch codec_qe_changed codec_wip_status codec_protection_changed}} {
        if {$mock_mutation_calls != $install_codec || !$nmr_flash_mutation_possible} { error "Codec verification/status failure admitted net/aux/code/table erase" }
        mock_assert_original_context
    } elseif {$mock_mode == "restore_codec_native_error"} {
        if {$mock_mutation_calls != [concat $restore_table $restore_code $restore_aux $restore_net {erase_codec program_codec_0}] || !$mock_net_original_verified || !$mock_aux_original_verified || !$mock_code_original_verified || !$mock_table_restored_verified || !$mock_failed_run || $mock_stale_replay} { error "Restore codec error admitted wrong order or stale replay" }
    } elseif {$mock_mode in {codec_invalidate_native_error codec_changed_after_invalidation}} {
        if {$mock_mutation_calls != [concat $install_aux $install_code $install_table]} { error "Codec cache closure performed unexpected mutation" }
        if {$mock_mode == "codec_invalidate_native_error" && (!$mock_failed_run || $mock_stale_replay)} { error "Unclosed codec cache call replayed context" }
        if {$mock_mode == "codec_changed_after_invalidation"} { mock_assert_original_context }
    } elseif {$mock_mode in {net_reset net_fault net_native_error net_program_timeout net_posted_transport_timeout_wip1 net_erase_native_error net_erase_timeout}} {`);
  change('assert len(cases) == 93', 'cases += ' + JSON.stringify(CODEC_MOCK_CASES) + '\nassert len(cases) == 116');
  mock = mock.replaceAll('Four-page', 'Five-page').replaceAll('four-page', 'five-page').replaceAll('All four I/D', 'All five I/D')
    .replaceAll('plus stock network page;', 'plus stock network and codec pages;');
  return mock;
}
function writerArtifacts(baseline: Inputs, original: Pages, patched: Pages) {
  const raw = (path: string) => baseline.get(path)!.toString('utf8');
  const stage = raw('diagnostics/boot-nor-native-image-drawer-stage-inputs.cfg');
  const marker = stage.indexOf('foreach nidi_name ');
  requireThat(marker >= 0, 'Complete frozen stage preamble missing');
  let inputs = '# Private candidate; exact image-drawer rollback; no hardware actions.\n';
  inputs += tclWords('nmri_one_call_words', callerFromStages(stage));
  for (const [label, page] of [['code', 'code'], ['table', 'entry'], ['aux', 'aux'], ['net', 'net'], ['codec', 'codec']] as const)
    for (const [state, pages] of [['original', original], ['patched', patched]] as const)
      inputs += tclWords(`nmri_${label}_${state}_words`, pages[page]);
  inputs += cloneStages(stage.slice(marker));
  const result: Inputs = new Map([
    [`workspace/diagnostics/boot-nor-${PREFIX}-stage-inputs.cfg`, Buffer.from(inputs)],
    [`workspace/diagnostics/boot-nor-${PREFIX}-runner.cfg`, Buffer.from(cloneWriter(raw('diagnostics/boot-nor-native-image-drawer-runner.cfg')))],
  ]);
  for (const mode of ['install', 'restore']) {
    const session = names(raw(`diagnostics/mcu-native-image-drawer-${mode}-session.cfg`));
    requireThat(session.includes('($boot_app_entered && (!$nmr_safe_to_resume || !$nmr_app_complete))') &&
      session.includes('automatic GLOBAL suppressed'), 'Outer completion/closed-return guard missing');
    const guard = '# No execute command exists in this offline release tool.\n' +
      'if {![info exists panel_release_verified] || !$panel_release_verified} { error "Candidate session requires an independently verified frozen executor" }\n';
    result.set(`workspace/diagnostics/mcu-${PREFIX}-${mode}-session.cfg`, Buffer.from(guard + session));
  }
  result.set('workspace/analysis/persistence/test_panel_maintained_runner_offline.py',
    Buffer.from(cloneMock(raw('analysis/persistence/test_native_image_drawer_runner_offline.py'))));
  result.set('workspace/analysis/persistence/panel-maintained-writer-derivation.json', Buffer.from(encode({
    layout: 'five-page-codec-v1', generator: 'firmware/tools/release.ts',
    originalRunnerSha256: sha256(baseline.get('diagnostics/boot-nor-native-image-drawer-runner.cfg')!),
    originalStagesSha256: sha256(baseline.get('diagnostics/boot-nor-native-image-drawer-stage-inputs.cfg')!),
    originalMockSha256: sha256(baseline.get('analysis/persistence/test_native_image_drawer_runner_offline.py')!),
    callerSha256: CALLER_SHA, pageOffsets: PAGE_OFFSETS, containers: PORT,
    installOrder: ['codec', 'net', 'aux', 'code', 'entry'], restoreOrder: ['entry', 'code', 'aux', 'net', 'codec'],
  })));
  return result;
}
function sourceFiles(root: string, name: string): string[] {
  return readdirSync(within(root, name), { withFileTypes: true }).flatMap(item => {
    const path = name + '/' + item.name;
    requireThat(!item.isSymbolicLink(), `Snapshot source must not be a symlink: ${path}`);
    return item.isDirectory() ? sourceFiles(root, path) : [path];
  });
}
function sourcePaths(root: string) {
  return ['firmware/build.sh', 'firmware/tools/build-record.ts', ...['firmware/src', 'firmware/include', 'firmware/ports/1.50.10']
    .flatMap(name => sourceFiles(root, name)), 'build/panel/config.h'].sort();
}
function reviewPaths(root: string) {
  const tests = sourceFiles(root, 'firmware/tests').filter(path => /\.(py|c|sh)$/.test(path));
  requireThat(tests.length > 0, 'Maintained ARM/host test sources must be included in the review snapshot');
  return ['firmware/tools/release.test.ts', ...tests].sort();
}
function hashes(inputs: Inputs): Hashes {
  return Object.fromEntries([...inputs].sort(([a], [b]) => a.localeCompare(b)).map(([name, bytes]) => [name, sha256(bytes)]));
}
function releasePath(root: string, name: string) {
  requireThat(/^[a-z0-9][a-z0-9-]{0,63}$/.test(name), 'Use a unique lowercase release name (1..64 characters)');
  return within(root, 'build/releases/' + name);
}
export function checkOwnership(ownership: Ownership) {
  requireThat(ownership.role === 'storage-ownership-review' && ownership.passed === true &&
    ownership.firmware === '1.50.10' && ownership.baseline_freeze_sha256 === BASELINE_SHA &&
    ownership.stock_backup_sha256 === STOCK_SHA && ownership.net_page_sha256 === NET_PAGE_SHA &&
    Number(ownership.net_offset) === PORT.net.page && Number(ownership.runtime_start) === PORT.net.start &&
    Number(ownership.runtime_end_exclusive) === PORT.net.end && Number(ownership.builtin_entry_offset) === 0xc3c &&
    Number(ownership.builtin_original_word) === 0x3804cf3d && Number(ownership.builtin_disabled_word) === 0x3804b109 &&
    ownership.codec_page_sha256 === CODEC_PAGE_SHA && Number(ownership.codec_offset) === PORT.codec.page &&
    Number(ownership.codec_runtime_start) === PORT.codec.start && Number(ownership.codec_runtime_end_exclusive) === PORT.codec.end &&
    ownership.codec_builtin_entries?.length === CODEC_ENTRY_WORDS.length && CODEC_ENTRY_WORDS.every(([offset, word]) =>
      ownership.codec_builtin_entries.filter(entry => Number(entry.offset) === offset && Number(entry.original_word) === word &&
        Number(entry.disabled_word) === 0x3804b109).length === 1),
    'Explicit reviewed ownership metadata for both exact dependency pages is required');
  requireThat(ownership.evidence_sha256 && Object.keys(ownership.evidence_sha256).length > 0 &&
    ownership.evidence_sha256[STOCK_PATH] === STOCK_SHA, 'Ownership review must bind actual evidence and full stock backup');
  const reviews = [ownership.net_review, ownership.codec_review];
  requireThat(reviews.every(review => review?.path && review.path !== STOCK_PATH && /^[0-9a-f]{64}$/.test(review.sha256) &&
    ownership.evidence_sha256[review.path] === review.sha256) && reviews[0].path !== reviews[1].path &&
    reviews[0].sha256 !== reviews[1].sha256, 'Ownership review must bind distinct net and codec evidence');
}
export function compilerHeaderCopies(record: BuildRecord) {
  const original = Object.values(record.headers ?? {}), copies = Object.entries(record.headerCopies ?? {});
  requireThat(original.length > 0 && copies.length === original.length &&
    encode([...original].sort()) === encode(copies.map(([, digest]) => digest).sort()),
    'Compiler header copies must bind all actual build headers exactly');
  for (const [path] of copies) requireThat(path.startsWith('build/panel/compiler-headers/') &&
    !path.includes('..') && !path.includes('\\') && path.length > 'build/panel/compiler-headers/'.length,
    'Compiler header copy leaves the admitted snapshot directory');
  return copies;
}
export function prepareRelease(root: string, name: string, ownershipPath: string) {
  const directory = releasePath(root, name);
  requireThat(!existsSync(directory), 'Release exists; use a new name, never overwrite a snapshot');
  const baseline = collectBaseline(root);
  requireThat(ownershipPath, 'Prepare requires an explicit ownership review JSON path');
  const ownershipBytes = read(root, ownershipPath), ownership = decode<Ownership>(ownershipBytes);
  checkOwnership(ownership);
  const main = read(root, 'build/panel/panel.bin'), aux = read(root, 'build/panel/panel-aux.bin'),
    net = read(root, 'build/panel/panel-net.bin'), codec = read(root, 'build/panel/panel-codec.bin');
  const patched = patchPages(baseline.pages, main, aux, net, codec);
  const elf = read(root, 'build/panel/panel.elf'), linked = linkedSegments(elf);
  requireThat(main.equals(linked.main) && aux.equals(linked.aux) && net.equals(linked.net) && codec.equals(linked.codec), 'BIN does not reconstruct exact allocated ELF spans');
  const sources = sourcePaths(root), outputs = ['panel.bin', 'panel-aux.bin', 'panel-net.bin', 'panel-codec.bin', 'panel.elf', 'panel.map']
    .map(name => 'build/panel/' + name);
  const provenancePath = 'build/panel/build-inputs.json';
  const provenance = decode<BuildRecord>(read(root, provenancePath));
  requireThat(provenance.completed === true && provenance.sources && provenance.artifacts, 'Missing completed build-time provenance');
  const buildHashes = { ...provenance.sources, ...provenance.artifacts };
  const inputs: Inputs = new Map();
  for (const [path, expected] of compilerHeaderCopies(provenance))
    inputs.set('snapshot/' + path, checked(root, path, expected));
  const copiedOwnership = 'snapshot/reviews/storage-ownership.json';
  inputs.set(copiedOwnership, ownershipBytes);
  for (const [path, expected] of Object.entries(ownership.evidence_sha256))
    inputs.set('ownership-inputs/' + path, checked(root, path, expected));
  for (const path of [...sources, ...outputs]) {
    requireThat(buildHashes[path], `Build provenance does not bind ${path}`);
    inputs.set('snapshot/' + path, checked(root, path, buildHashes[path]));
  }
  for (const [path, expected] of Object.entries(provenance.sources)) {
    requireThat(path.startsWith('firmware/') || path === 'build/panel/config.h', `Unexpected build source path: ${path}`);
    inputs.set('snapshot/' + path, checked(root, path, expected));
  }
  inputs.set('snapshot/' + provenancePath, read(root, provenancePath));
  inputs.set('snapshot/firmware/tools/release.ts', read(root, 'firmware/tools/release.ts'));
  inputs.set('snapshot/firmware/tools/hardware.ts', read(root, 'firmware/tools/hardware.ts'));
  // Test/model sources are reviewed inputs, not asserted to be compiled program sources.
  for (const path of reviewPaths(root)) inputs.set('snapshot/' + path, read(root, path));
  for (const [path, data] of baseline.inputs) inputs.set('workspace/' + path, data);
  for (const filename of ['libftdi1.dll', 'libusb-1.0.dll']) {
    const path = 'tools/xpack-openocd-0.12.0-7/bin/' + filename;
    inputs.set('workspace/' + path, read(root, path));
  }
  // OpenOCD's package-native script tree differs from its -s diagnostics lookup.
  // Preserve vendor bytes and bind the explicit alias used by swd-dap.cfg.
  const cmsisConfig = read(root, CMSIS_CONFIG);
  inputs.set('workspace/' + CMSIS_CONFIG, cmsisConfig);
  inputs.set('workspace/' + CMSIS_ALIAS, cmsisConfig);
  for (const label of Object.keys(PAGE_OFFSETS) as (keyof Pages)[])
    for (const [state, pages] of [['original', baseline.pages], ['patched', patched]] as const)
      inputs.set(`workspace/analysis/persistence/${PREFIX}-${state}-sector-${PAGE_OFFSETS[label].toString(16)}.bin`, pages[label]);
  for (const item of writerArtifacts(baseline.inputs, baseline.pages, patched)) inputs.set(...item);
  const candidate: Candidate = {
    schema: 3, layout: 'five-page-codec-v1', name, firmware: '1.50.10', status: 'candidate', hardwareExecution: false,
    baselineFreezeSha256: BASELINE_SHA, baselineInputs: hashes(baseline.inputs), inputs: hashes(inputs),
    ownership: { path: copiedOwnership, sha256: sha256(ownershipBytes) },
    program: { mainBytes: main.length, auxBytes: aux.length, netBytes: net.length, codecBytes: codec.length, elfSha256: sha256(elf) },
    pages: Object.fromEntries((Object.keys(PAGE_OFFSETS) as (keyof Pages)[]).map(label => [label, {
      offset: PAGE_OFFSETS[label], originalSha256: sha256(baseline.pages[label]), patchedSha256: sha256(patched[label]),
    }])) as Candidate['pages'],
    mockCommand: ['python', '-X', 'utf8', 'analysis/persistence/test_panel_maintained_runner_offline.py'],
    installOrder: ['codec', 'net', 'aux', 'code', 'entry'], restoreOrder: ['entry', 'code', 'aux', 'net', 'codec'],
  };
  mkdirSync(dirname(directory), { recursive: true });
  within(realpathSync(root), relative(root, realpathSync(dirname(directory))));
  mkdirSync(directory);
  for (const [path, bytes] of inputs) {
    const destination = within(directory, path);
    mkdirSync(dirname(destination), { recursive: true });
    writeFileSync(destination, bytes, { flag: 'wx' });
  }
  writeFileSync(join(directory, 'candidate.json'), encode(candidate), { flag: 'wx' });
  verifyRelease(root, name);
  return candidate;
}
export function verifyRelease(root: string, name: string) {
  const directory = releasePath(root, name), raw = read(directory, 'candidate.json');
  const candidate = decode<Candidate>(raw);
  requireThat(candidate.schema === 3 && candidate.layout === 'five-page-codec-v1' && candidate.status === 'candidate' && !candidate.hardwareExecution &&
    candidate.name === name && candidate.firmware === '1.50.10' && candidate.baselineFreezeSha256 === BASELINE_SHA,
    'Not an offline five-page candidate');
  const baseline = collectBaseline(root);
  requireThat(encode(candidate.baselineInputs) === encode(hashes(baseline.inputs)), 'Baseline dependency closure changed');
  for (const [path, data] of baseline.inputs) {
    const copied = 'workspace/' + path;
    requireThat(candidate.inputs[copied] === sha256(data) && read(directory, copied).equals(data),
      `Snapshot omitted/changed immutable baseline input: ${path}`);
  }
  for (const [path, expected] of Object.entries(candidate.inputs)) checked(directory, path, expected);
  const cmsisVendor = 'workspace/' + CMSIS_CONFIG, cmsisAlias = 'workspace/' + CMSIS_ALIAS;
  requireThat(candidate.inputs[cmsisVendor] && candidate.inputs[cmsisVendor] === candidate.inputs[cmsisAlias] &&
    read(directory, cmsisVendor).equals(read(directory, cmsisAlias)),
    'CMSIS-DAP package dependency and diagnostics alias must bind identical exact vendor bytes');
  requireThat(candidate.ownership.path === 'snapshot/reviews/storage-ownership.json' &&
    candidate.inputs[candidate.ownership.path] === candidate.ownership.sha256, 'Ownership metadata omitted/changed');
  const ownership = decode<Ownership>(checked(directory, candidate.ownership.path, candidate.ownership.sha256));
  checkOwnership(ownership);
  for (const [path, expected] of Object.entries(ownership.evidence_sha256)) {
    requireThat(candidate.inputs['ownership-inputs/' + path] === expected, 'Ownership evidence omitted/changed');
    checked(directory, 'ownership-inputs/' + path, expected);
  }
  const snapshot = join(directory, 'snapshot');
  const buildRecord = decode<BuildRecord>(read(snapshot, 'build/panel/build-inputs.json'));
  requireThat(buildRecord.completed === true && buildRecord.sources && buildRecord.artifacts, 'Snapshot build is incomplete');
  requireThat(candidate.inputs['snapshot/firmware/tools/hardware.ts'], 'Snapshot must bind its separately reviewed hardware executor');
  for (const path of reviewPaths(snapshot)) requireThat(candidate.inputs['snapshot/' + path],
    `Snapshot must bind the maintained model/test source: ${path}`);
  for (const [path, expected] of compilerHeaderCopies(buildRecord)) {
    requireThat(candidate.inputs['snapshot/' + path] === expected, 'Snapshot compiler header omitted/changed');
    checked(snapshot, path, expected);
  }
  const buildHashes = { ...buildRecord.sources, ...buildRecord.artifacts };
  for (const path of [...sourcePaths(snapshot), ...['panel.bin', 'panel-aux.bin', 'panel-net.bin', 'panel-codec.bin', 'panel.elf', 'panel.map']
    .map(name => 'build/panel/' + name)]) {
    requireThat(buildHashes[path] && candidate.inputs['snapshot/' + path] === buildHashes[path],
      `Snapshot build provenance does not bind ${path}`);
    checked(snapshot, path, buildHashes[path]);
  }
  for (const [path, expected] of Object.entries(buildRecord.sources)) {
    requireThat(candidate.inputs['snapshot/' + path] === expected, `Snapshot omitted build source: ${path}`);
    checked(snapshot, path, expected);
  }
  const main = read(directory, 'snapshot/build/panel/panel.bin'), aux = read(directory, 'snapshot/build/panel/panel-aux.bin'),
    net = read(directory, 'snapshot/build/panel/panel-net.bin'), codec = read(directory, 'snapshot/build/panel/panel-codec.bin');
  const linked = linkedSegments(read(directory, 'snapshot/build/panel/panel.elf'));
  requireThat(main.equals(linked.main) && aux.equals(linked.aux) && net.equals(linked.net) && codec.equals(linked.codec) && main.length === candidate.program.mainBytes &&
    aux.length === candidate.program.auxBytes && net.length === candidate.program.netBytes && codec.length === candidate.program.codecBytes && candidate.program.elfSha256 ===
      sha256(read(directory, 'snapshot/build/panel/panel.elf')), 'Snapshot program drift');
  const patched = patchPages(baseline.pages, main, aux, net, codec);
  for (const label of Object.keys(PAGE_OFFSETS) as (keyof Pages)[]) {
    const description = candidate.pages[label];
    requireThat(description.offset === PAGE_OFFSETS[label] && description.originalSha256 === sha256(baseline.pages[label]) &&
      description.patchedSha256 === sha256(patched[label]), `Page metadata drift: ${label}`);
    for (const [state, pages] of [['original', baseline.pages], ['patched', patched]] as const) {
      const path = `workspace/analysis/persistence/${PREFIX}-${state}-sector-${PAGE_OFFSETS[label].toString(16)}.bin`;
      requireThat(read(directory, path).equals(pages[label]), `Whole page differs: ${path}`);
    }
  }
  for (const [path, expected] of writerArtifacts(baseline.inputs, baseline.pages, patched))
    requireThat(read(directory, path).equals(expected), `Writer/session normalization drift: ${path}`);
  requireThat(encode(candidate.installOrder) === encode(['codec', 'net', 'aux', 'code', 'entry']) &&
    encode(candidate.restoreOrder) === encode(['entry', 'code', 'aux', 'net', 'codec']), 'Fixed phase order changed');
  if (existsSync(join(directory, 'freeze.json'))) {
    const freeze = decode<{ schema: number; hardwareExecution: boolean; candidateSha256: string; sha256: Hashes }>(read(directory, 'freeze.json'));
    requireThat(freeze.schema === 1 && freeze.hardwareExecution === false && freeze.candidateSha256 === sha256(raw), 'Frozen candidate drift');
    const expectedInputs = { ...candidate.inputs, 'candidate.json': sha256(raw) };
    const evidenceDigests = new Set<string>();
    for (const role of EVIDENCE_ROLES) {
      const path = `evidence/${role}.json`, artifact = read(directory, path), digest = sha256(artifact);
      requireThat(!evidenceDigests.has(digest), 'Independent evidence roles share an artifact');
      evidenceDigests.add(digest);
      checkEvidence(role, decode<Evidence>(artifact), candidate, sha256(raw));
      expectedInputs[path] = digest;
    }
    requireThat(Object.keys(freeze.sha256).length === Object.keys(expectedInputs).length &&
      Object.entries(expectedInputs).every(([path, expected]) => freeze.sha256[path] === expected), 'Frozen input coverage is incomplete');
    for (const [path, expected] of Object.entries(freeze.sha256)) checked(directory, path, expected);
  }
  return { candidate, directory, candidateSha256: sha256(raw), frozen: existsSync(join(directory, 'freeze.json')) };
}

type Evidence = { role: string; passed: boolean; release_manifest_sha256: string; reviewed_inputs: Hashes;
  elf_sha256?: string; scope?: string; check_count?: number; all_passed?: boolean; cases?: { case: string; passed: boolean }[];
  ownership_sha256?: string };
export function checkEvidence(role: string, evidence: Evidence, candidate: Candidate, digest: string) {
  requireThat(evidence.role === role && evidence.passed === true && evidence.release_manifest_sha256 === digest,
    `Evidence does not bind this candidate: ${role}`);
  for (const [path, expected] of Object.entries(candidate.inputs))
    requireThat(evidence.reviewed_inputs?.[path] === expected, `Evidence missing exact input ${path}: ${role}`);
  if (role === 'arm-model') requireThat(evidence.scope === 'actual-arm' && (evidence.check_count ?? 0) > 0 &&
    evidence.elf_sha256 === candidate.program.elfSha256, 'ARM evidence must use current actual ELF');
  if (role === 'storage-ownership-review') requireThat(evidence.ownership_sha256 === candidate.ownership.sha256,
    'Storage evidence must bind the candidate ownership review');
  if (role === 'writer-mock') {
    const cases = evidence.cases ?? [], names = new Set(cases.map(item => item.case));
    requireThat(evidence.all_passed === true && cases.length === WRITER_MOCK_CASES.length && names.size === cases.length &&
      cases.every(item => item.passed === true) && WRITER_MOCK_CASES.every(name => names.has(name)),
      'All 70 inherited, 23 net and 23 codec writer mock cases must pass distinctly');
  }
}
export function freezeRelease(root: string, name: string, evidencePath: string) {
  const verified = verifyRelease(root, name);
  requireThat(!verified.frozen, 'Freeze is immutable; do not overwrite it');
  const approvals = decode<Record<string, { path: string; sha256: string }>>(read(root, evidencePath));
  const artifacts = new Map<string, Buffer>();
  const seen = new Set<string>();
  for (const role of EVIDENCE_ROLES) {
    const reference = approvals[role];
    requireThat(reference?.path && reference.sha256, `Missing independent evidence: ${role}`);
    const raw = checked(root, reference.path, reference.sha256);
    requireThat(!seen.has(reference.sha256), 'Independent roles cannot share the same evidence artifact');
    seen.add(reference.sha256);
    checkEvidence(role, decode<Evidence>(raw), verified.candidate, verified.candidateSha256);
    artifacts.set(`evidence/${role}.json`, raw);
  }
  const frozenInputs = { ...verified.candidate.inputs, 'candidate.json': verified.candidateSha256 };
  mkdirSync(join(verified.directory, 'evidence'));
  for (const [path, data] of artifacts) {
    writeFileSync(join(verified.directory, path), data, { flag: 'wx' });
    frozenInputs[path] = sha256(data);
  }
  verifyRelease(root, name);
  writeFileSync(join(verified.directory, 'freeze.json'), encode({ schema: 1, hardwareExecution: false,
    candidateSha256: verified.candidateSha256, sha256: frozenInputs,
    note: 'Binds completed independent review/model/mock evidence; does not authorize hardware or supply an executor.' }), { flag: 'wx' });
  return verifyRelease(root, name);
}
function main() {
  const [command, name, evidence] = process.argv.slice(2), root = resolve(process.cwd());
  if (command === 'baseline' && !name) { console.log(encode(verifyBaseline(root))); return; }
  requireThat(name && (command === 'verify' && !evidence || (command === 'prepare' || command === 'freeze') && evidence) &&
    process.argv.length <= (command === 'verify' ? 4 : 5),
    'Usage: node firmware/tools/release.ts baseline; prepare NAME OWNERSHIP.json; verify NAME; freeze NAME EVIDENCE.json (offline only)');
  const result = command === 'prepare' ? prepareRelease(root, name, evidence) : command === 'verify' ? verifyRelease(root, name) :
    freezeRelease(root, name, evidence);
  const summary = command === 'prepare' ? { name, candidate: 'build/releases/' + name + '/candidate.json',
    program: (result as Candidate).program, frozen: false, hardwareExecution: false } :
    { name, directory: (result as ReturnType<typeof verifyRelease>).directory,
      candidateSha256: (result as ReturnType<typeof verifyRelease>).candidateSha256,
      frozen: (result as ReturnType<typeof verifyRelease>).frozen, hardwareExecution: false };
  console.log(encode(summary));
}
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(); } catch (error) { console.error((error as Error).message); process.exitCode = 1; }
}
