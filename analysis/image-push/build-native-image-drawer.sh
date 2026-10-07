#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=analysis/image-push
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz -Wall -Wextra -Werror -mllvm -enable-machine-outliner=always \
  -ffreestanding -fomit-frame-pointer -fno-builtin -fno-stack-protector -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -fno-pic -fno-ident \
  -c "$out/native-image-drawer.c" -o "$out/native-image-drawer.o"
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c "$out/native-image-drawer-entry.S" -o "$out/native-image-drawer-entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -Map="$out/native-image-drawer.map" -T "$out/native-image-drawer.ld" \
  "$out/native-image-drawer-entry.o" "$out/native-image-drawer.o" -o "$out/native-image-drawer.elf"
llvm-objcopy-18 -O binary --only-section=.prefix --only-section=.start --only-section=.broker "$out/native-image-drawer.elf" "$out/native-image-drawer.bin"
llvm-objcopy-18 -O binary --only-section=.feedback "$out/native-image-drawer.elf" "$out/native-image-drawer-feedback.bin"
llvm-size-18 "$out/native-image-drawer.elf"
test -z "$(llvm-nm-18 --undefined-only "$out/native-image-drawer.elf")"
