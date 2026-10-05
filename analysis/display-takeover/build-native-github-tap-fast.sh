#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=analysis/display-takeover
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz -Wall -Wextra -Werror -mllvm -enable-machine-outliner=always \
  -ffreestanding -fomit-frame-pointer -fno-builtin -fno-stack-protector -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -fno-pic -fno-ident \
  -c "$out/native-github-tap-fast.c" -o "$out/native-github-tap-fast.o"
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c "$out/native-github-tap-fast-entry.S" -o "$out/native-github-tap-fast-entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -Map="$out/native-github-tap-fast.map" -T "$out/native-github-tap-fast.ld" \
  "$out/native-github-tap-fast-entry.o" "$out/native-github-tap-fast.o" -o "$out/native-github-tap-fast.elf"
llvm-objcopy-18 -O binary --only-section=.prefix --only-section=.start --only-section=.broker "$out/native-github-tap-fast.elf" "$out/native-github-tap-fast.bin"
llvm-objcopy-18 -O binary --only-section=.feedback "$out/native-github-tap-fast.elf" "$out/native-github-tap-fast-feedback.bin"
llvm-size-18 "$out/native-github-tap-fast.elf"
test -z "$(llvm-nm-18 --undefined-only "$out/native-github-tap-fast.elf")"
