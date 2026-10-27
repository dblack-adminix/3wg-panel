#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

output="$(
  WHIPTAIL_BIN="$ROOT/tests/mock_whiptail.sh" \
  MOCK_INSTALL_DIR="$work/panel-dry-run" \
  INSTALL_TUI_EXECUTE=0 \
  bash "$ROOT/scripts/install_tui.sh"
)"

grep -Fq 'TUI configuration validated' <<<"$output"

output="$(
  WHIPTAIL_BIN="$ROOT/tests/mock_whiptail.sh" \
  MOCK_INSTALL_DIR="$work/panel" \
  INSTALL_SCRIPT="$ROOT/tests/mock_installer.sh" \
  INSTALL_RESULT_ROOT="$work/result" \
  bash "$ROOT/scripts/install_tui.sh"
)"

credentials="$work/result/3wg-vpn.example.com-credentials.txt"
log_file="$(find "$work/panel/backups/install" -type f -name '3wg-install.*.log' -print -quit)"
grep -Fq '3WG installed successfully' <<<"$output"
test -s "$credentials"
grep -Eq '^Password: .+' "$credentials"
test -s "$log_file"
grep -Fq 'Configuring Caddy reverse proxy' "$log_file"

printf 'install TUI dry-run and progress flow: ok\n'
