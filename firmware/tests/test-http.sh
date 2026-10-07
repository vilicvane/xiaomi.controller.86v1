#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=firmware/build/tests
mkdir -p "$out"
clang-18 -std=c11 -Wall -Wextra -Werror -g -fsanitize=address,undefined \
  -Ifirmware/include firmware/src/http-parser.c firmware/tests/http-test.c \
  -o "$out/http-test"
"$out/http-test"
