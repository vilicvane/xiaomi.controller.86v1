#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=analysis/display-takeover
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz -Wall -Wextra -Werror -mllvm -enable-machine-outliner=always \
  -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -fno-pic -fno-ident \
  -c "$out/native-github-card.c" -o "$out/native-github-card.o"
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c "$out/native-github-card-entry.S" -o "$out/native-github-card-entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -Map="$out/native-github-card.map" -T "$out/native-github-card.ld" \
  "$out/native-github-card-entry.o" "$out/native-github-card.o" -o "$out/native-github-card.elf"
llvm-objcopy-18 -O binary "$out/native-github-card.elf" "$out/native-github-card.bin"
llvm-size-18 "$out/native-github-card.elf"
test -z "$(llvm-nm-18 --undefined-only "$out/native-github-card.elf")"
