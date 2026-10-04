#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
test_bin=$(mktemp /tmp/mi-panel-drawer-gesture.XXXXXX)
trap 'rm -f "$test_bin"' EXIT HUP INT TERM
clang-18 -std=c11 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  analysis/display-takeover/test-drawer-gesture.c -o "$test_bin"
"$test_bin"
