#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="$(
  WHIPTAIL_BIN="$ROOT/tests/mock_whiptail.sh" \
  INSTALL_TUI_EXECUTE=0 \
  bash "$ROOT/scripts/install_tui.sh"
)"

grep -Fq 'TUI configuration validated' <<<"$output"
printf 'install TUI flow: ok\n'
