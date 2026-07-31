#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/srv/3wg-panel}"
SERVICE="${SERVICE:-3wg-panel-update-runner}"
UNIT="/etc/systemd/system/${SERVICE}.service"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1"; }

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите от root: sudo bash scripts/install_update_runner.sh"
fi

[ -d "$BASE" ] || fail "Не найден каталог проекта: $BASE"
[ -f "$BASE/scripts/update_runner.py" ] || fail "Не найден $BASE/scripts/update_runner.py"
[ -f "$BASE/scripts/update.sh" ] || fail "Не найден $BASE/scripts/update.sh"

need_cmd systemctl
need_cmd "$PYTHON_BIN"

mkdir -p "$BASE/run" "$BASE/backups/update"
chmod 775 "$BASE/run"

cat > "$UNIT" <<UNIT
[Unit]
Description=3WG Core host update runner
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BASE
Environment=THREEWG_BASE=$BASE
Environment=THREEWG_UPDATE_SOCKET=$BASE/run/update-runner.sock
Environment=THREEWG_UPDATE_SCRIPT=$BASE/scripts/update.sh
Environment=THREEWG_UPDATE_LOG=$BASE/backups/update/ui-runner.log
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
printf 'Socket:  %s/run/update-runner.sock\n' "$BASE"
systemctl --no-pager --lines=20 status "$SERVICE"
