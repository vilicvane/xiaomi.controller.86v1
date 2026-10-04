#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=analysis/display-takeover
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb -Oz \
  -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables \
  -fno-asynchronous-unwind-tables -fno-pic -fno-ident \
  -c "$out/native-ui-broker.c" -o "$out/native-ui-broker.o"
clang-18 --target=arm-none-eabi -mcpu=cortex-a7 -mthumb \
  -c "$out/native-ui-broker-entry.S" -o "$out/native-ui-broker-entry.o"
tools/a7-llvm/extracted/usr/lib/llvm-18/bin/ld.lld \
  -Map="$out/native-ui-broker.map" -T "$out/native-ui-broker.ld" \
  "$out/native-ui-broker-entry.o" "$out/native-ui-broker.o" -o "$out/native-ui-broker.elf"
llvm-objcopy-18 -O binary "$out/native-ui-broker.elf" "$out/native-ui-broker.bin"
llvm-size-18 "$out/native-ui-broker.elf"
test -z "$(llvm-nm-18 --undefined-only "$out/native-ui-broker.elf")"
