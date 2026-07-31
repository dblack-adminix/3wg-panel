#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/srv/3wg-panel}"
SERVICE="${SERVICE:-3wg-panel-update-runner}"
UNIT="/etc/systemd/system/${SERVICE}.service"
SOCKET_PATH="$BASE/run/update-runner.sock"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите от root: sudo bash scripts/uninstall_update_runner.sh"
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
  rm -f "$UNIT"
  systemctl daemon-reload
fi
rm -f "$SOCKET_PATH"

printf '3WG Core update runner removed.\n'
