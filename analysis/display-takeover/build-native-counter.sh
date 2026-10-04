#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=analysis/display-takeover
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz \
  -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -fno-pic -fno-ident \
  -c "$out/native-counter.c" -o "$out/native-counter.o"
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c "$out/native-counter-entry.S" -o "$out/native-counter-entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -T "$out/native-counter.ld" "$out/native-counter-entry.o" \
  "$out/native-counter.o" -o "$out/native-counter.elf"
llvm-objcopy-18 -O binary "$out/native-counter.elf" "$out/native-counter.bin"
llvm-size-18 "$out/native-counter.elf"
if [ -n "$(llvm-nm-18 --undefined-only "$out/native-counter.elf")" ]; then
  echo 'Unexpected unresolved symbols' >&2
  exit 1
fi
