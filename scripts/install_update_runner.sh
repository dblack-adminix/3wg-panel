#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/srv/3wg-panel}"
SERVICE="${SERVICE:-3wg-panel-update-runner}"
UNIT="/etc/systemd/system/${SERVICE}.service"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
SOCKET_PATH="${SOCKET_PATH:-$BASE/run/update-runner.sock}"
UPDATE_SCRIPT="${UPDATE_SCRIPT:-$BASE/scripts/update.sh}"
LOG_PATH="${LOG_PATH:-$BASE/backups/update/ui-runner.log}"
DESCRIPTION="${DESCRIPTION:-3WG Core host update runner}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1"; }

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите от root: sudo bash scripts/install_update_runner.sh"
fi

[ -d "$BASE" ] || fail "Не найден каталог проекта: $BASE"
[ -f "$BASE/scripts/update_runner.py" ] || fail "Не найден $BASE/scripts/update_runner.py"
[ -f "$UPDATE_SCRIPT" ] || fail "Не найден $UPDATE_SCRIPT"

need_cmd systemctl
need_cmd "$PYTHON_BIN"

mkdir -p "$(dirname "$SOCKET_PATH")" "$(dirname "$LOG_PATH")"
chmod 775 "$(dirname "$SOCKET_PATH")"

cat > "$UNIT" <<UNIT
[Unit]
Description=$DESCRIPTION
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BASE
Environment=THREEWG_BASE=$BASE
Environment=THREEWG_UPDATE_SOCKET=$SOCKET_PATH
Environment=THREEWG_UPDATE_SCRIPT=$UPDATE_SCRIPT
Environment=THREEWG_UPDATE_LOG=$LOG_PATH
ExecStart=$PYTHON_BIN $BASE/scripts/update_runner.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
if [ "${THREEWG_UPDATE_RUNNER_ACTIVE:-0}" = "1" ]; then
  systemctl start "$SERVICE" >/dev/null 2>&1 || true
else
  systemctl restart "$SERVICE"
fi

printf '3WG Core update runner installed.\n'
printf 'Service: %s\n' "$SERVICE"
printf 'Socket:  %s\n' "$SOCKET_PATH"
systemctl --no-pager --lines=20 status "$SERVICE"
