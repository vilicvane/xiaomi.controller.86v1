#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=analysis/display-takeover
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz -Wall -Wextra -Werror -mllvm -enable-machine-outliner=always \
  -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -fno-pic -fno-ident \
  -c "$out/native-github-tap.c" -o "$out/native-github-tap.o"
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c "$out/native-github-tap-entry.S" -o "$out/native-github-tap-entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -Map="$out/native-github-tap.map" -T "$out/native-github-tap.ld" \
  "$out/native-github-tap-entry.o" "$out/native-github-tap.o" -o "$out/native-github-tap.elf"
llvm-objcopy-18 -O binary --only-section=.prefix --only-section=.start --only-section=.broker "$out/native-github-tap.elf" "$out/native-github-tap.bin"
llvm-objcopy-18 -O binary --only-section=.feedback "$out/native-github-tap.elf" "$out/native-github-tap-feedback.bin"
llvm-size-18 "$out/native-github-tap.elf"
test -z "$(llvm-nm-18 --undefined-only "$out/native-github-tap.elf")"
