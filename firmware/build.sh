#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
out=build/panel
mkdir -p "$out"
node --input-type=module - "$out/config.h" <<'JS'
import { writeFileSync } from 'node:fs';
let url = process.env.PANEL_FRONTEND_URL ?? '';
const origin = process.env.PANEL_FRONTEND_ORIGIN ?? '*';
if (url) {
  const parsed = new URL(url);
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.hash || parsed.username || parsed.password)
    throw new Error('Frontend URL must use HTTP(S), without credentials or a fragment');
  url = parsed.href;
}
if (/[\x00-\x20\x7f]/.test(origin) || /[\x00-\x1f\x7f]/.test(url))
  throw new Error('Configuration contains a control character or invalid origin');
if (origin !== '*') {
  const parsed = new URL(origin);
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.origin !== origin)
    throw new Error('Frontend origin must be * or an HTTP(S) origin');
}
if (url.length > 1024 || origin.length > 256)
  throw new Error('Frontend URL or origin exceeds the response header budget');
writeFileSync(process.argv[2], `#define PANEL_FRONTEND_URL ${JSON.stringify(url)}\n#define PANEL_FRONTEND_ORIGIN ${JSON.stringify(origin)}\n`);
JS
node firmware/tools/build-record.ts begin
for unit in ui http http-parser; do
  clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz -Wall -Wextra -Werror \
    -mllvm -enable-machine-outliner=always -ffreestanding -fomit-frame-pointer \
    -fno-builtin -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \
    -fno-pic -fno-ident -I firmware/include -include "$out/config.h" \
    -MD -MF "$out/$unit.d" -c "firmware/src/$unit.c" -o "$out/$unit.o"
done
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c firmware/ports/1.50.10/entry.S -o "$out/entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -Map="$out/panel.map" -T firmware/ports/1.50.10/panel.ld \
  "$out/entry.o" "$out/ui.o" "$out/http.o" "$out/http-parser.o" -o "$out/panel.elf"
llvm-objcopy-18 -O binary --only-section=.prefix --only-section=.start --only-section=.broker \
  "$out/panel.elf" "$out/panel.bin"
llvm-objcopy-18 -O binary --only-section=.feedback "$out/panel.elf" "$out/panel-aux.bin"
llvm-objcopy-18 -O binary --only-section=.network "$out/panel.elf" "$out/panel-net.bin"
llvm-size-18 "$out/panel.elf"
test -z "$(llvm-nm-18 --undefined-only "$out/panel.elf")"
node firmware/tools/build-record.ts complete
