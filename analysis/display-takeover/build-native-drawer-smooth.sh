#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=analysis/display-takeover
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz -Wall -Wextra -Werror -mllvm -enable-machine-outliner=always \
  -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -fno-pic -fno-ident \
  -c "$out/native-drawer-smooth.c" -o "$out/native-drawer-smooth.o"
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c "$out/native-drawer-smooth-entry.S" -o "$out/native-drawer-smooth-entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -Map="$out/native-drawer-smooth.map" -T "$out/native-drawer-smooth.ld" \
  "$out/native-drawer-smooth-entry.o" "$out/native-drawer-smooth.o" -o "$out/native-drawer-smooth.elf"
llvm-objcopy-18 -O binary "$out/native-drawer-smooth.elf" "$out/native-drawer-smooth.bin"
llvm-size-18 "$out/native-drawer-smooth.elf"
test -z "$(llvm-nm-18 --undefined-only "$out/native-drawer-smooth.elf")"
