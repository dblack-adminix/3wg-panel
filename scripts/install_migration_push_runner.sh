#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/srv/3wg-panel}"
SERVICE="${SERVICE:-3wg-panel-migration-runner}"
UNIT="/etc/systemd/system/${SERVICE}.service"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1"; }
apt_run() { DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get "$@"; }

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите от root: sudo bash scripts/install_migration_push_runner.sh"
fi

[ -d "$BASE" ] || fail "Не найден каталог проекта: $BASE"
[ -f "$BASE/scripts/migration_push_runner.py" ] || fail "Не найден $BASE/scripts/migration_push_runner.py"

need_cmd systemctl
need_cmd "$PYTHON_BIN"

if command -v apt-get >/dev/null 2>&1; then
  apt_run update
  apt_run install -y openssh-client sshpass >/dev/null
fi

mkdir -p "$BASE/run" "$BASE/backups/migration"
chmod 775 "$BASE/run"

cat > "$UNIT" <<UNIT
[Unit]
Description=3WG Core host migration push runner
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BASE
Environment=THREEWG_BASE=$BASE
Environment=THREEWG_MIGRATION_SOCKET=$BASE/run/migration-runner.sock
Environment=THREEWG_MIGRATION_LOG=$BASE/backups/migration/ui-runner.log
ExecStart=$PYTHON_BIN $BASE/scripts/migration_push_runner.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

printf '3WG Core migration push runner installed.\n'
printf 'Service: %s\n' "$SERVICE"
printf 'Socket:  %s/run/migration-runner.sock\n' "$BASE"
systemctl --no-pager --lines=20 status "$SERVICE"
