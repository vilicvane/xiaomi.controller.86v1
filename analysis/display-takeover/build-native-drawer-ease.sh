#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=analysis/display-takeover
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz -Wall -Wextra -Werror -mllvm -enable-machine-outliner=always \
  -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -fno-pic -fno-ident \
  -c "$out/native-drawer-ease.c" -o "$out/native-drawer-ease.o"
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c "$out/native-drawer-ease-entry.S" -o "$out/native-drawer-ease-entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -Map="$out/native-drawer-ease.map" -T "$out/native-drawer-ease.ld" \
  "$out/native-drawer-ease-entry.o" "$out/native-drawer-ease.o" -o "$out/native-drawer-ease.elf"
llvm-objcopy-18 -O binary "$out/native-drawer-ease.elf" "$out/native-drawer-ease.bin"
llvm-size-18 "$out/native-drawer-ease.elf"
test -z "$(llvm-nm-18 --undefined-only "$out/native-drawer-ease.elf")"
