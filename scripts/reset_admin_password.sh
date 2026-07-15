#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="${ENV_FILE:-$INSTALL_DIR/.env}"
CONTAINER="${CONTAINER:-3wg-panel}"
PANEL_USER_VALUE="${PANEL_USER:-admin}"
PANEL_PASSWORD_VALUE="${PANEL_PASSWORD:-}"
RESTART_CONTAINER="${RESTART_CONTAINER:-1}"

usage() {
  cat <<'EOF'
Usage:
  sudo bash scripts/reset_admin_password.sh [options]

Options:
  --user USER             Set panel admin username. Default: admin
  --password PASSWORD     Set panel admin password.
  --password-file PATH    Read panel admin password from file.
  --no-restart            Do not recreate Docker container after .env update.
  -h, --help              Show this help.

Environment:
  INSTALL_DIR=/opt/3wg-panel
  ENV_FILE=/opt/3wg-panel/.env
  CONTAINER=3wg-panel
  PANEL_USER=admin
  PANEL_PASSWORD=secret
  RESTART_CONTAINER=1

If no password is provided, a strong random password is generated and printed once.
EOF
}

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --user)
      [ "${2:-}" ] || fail "--user требует значение"
      PANEL_USER_VALUE="$2"
      shift 2
      ;;
    --password)
      [ "${2:-}" ] || fail "--password требует значение"
      PANEL_PASSWORD_VALUE="$2"
      shift 2
      ;;
    --password-file)
      [ "${2:-}" ] || fail "--password-file требует путь"
      [ -f "$2" ] || fail "Файл пароля не найден: $2"
      PANEL_PASSWORD_VALUE="$(tr -d '\r\n' < "$2")"
      shift 2
      ;;
    --no-restart)
      RESTART_CONTAINER=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Неизвестный аргумент: $1"
      ;;
  esac
done

[ "${EUID:-$(id -u)}" -eq 0 ] || fail "Запустите от root: sudo bash scripts/reset_admin_password.sh"
[ -f "$ENV_FILE" ] || fail "Не найден .env: $ENV_FILE"

need_cmd python3

if [ -z "$PANEL_PASSWORD_VALUE" ]; then
  if command -v openssl >/dev/null 2>&1; then
    PANEL_PASSWORD_VALUE="$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-24)"
  else
    PANEL_PASSWORD_VALUE="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24)[:24])
PY
)"
  fi
  GENERATED_PASSWORD=1
else
  GENERATED_PASSWORD=0
fi

[ -n "$PANEL_USER_VALUE" ] || fail "PANEL_USER не может быть пустым"
[ -n "$PANEL_PASSWORD_VALUE" ] || fail "PANEL_PASSWORD не может быть пустым"

mkdir -p "$INSTALL_DIR/backups/source"
BACKUP="$INSTALL_DIR/backups/source/.env.password-reset.$(date +%F_%H-%M-%S).backup"
cp "$ENV_FILE" "$BACKUP"

SESSION_SECRET_VALUE="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"

tmp_file="$(mktemp)"
python3 - "$ENV_FILE" "$tmp_file" "$PANEL_USER_VALUE" "$PANEL_PASSWORD_VALUE" "$SESSION_SECRET_VALUE" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
updates = {
    "PANEL_USER": sys.argv[3],
    "PANEL_PASSWORD": sys.argv[4],
    "SESSION_SECRET": sys.argv[5],
}

lines = src.read_text(encoding="utf-8").splitlines()
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)

if out and out[-1].strip():
    out.append("")
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")

dst.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY

cat "$tmp_file" > "$ENV_FILE"
rm -f "$tmp_file"
chmod 600 "$ENV_FILE"

if [ "$RESTART_CONTAINER" = "1" ]; then
  need_cmd docker
  if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER"; then
    image="$(docker inspect "$CONTAINER" --format '{{.Config.Image}}')"
    mkdir -p "$INSTALL_DIR/run"
    docker rm -f "$CONTAINER" >/dev/null
    docker run -d \
      --name "$CONTAINER" \
      --restart unless-stopped \
      --env-file "$ENV_FILE" \
      -p 127.0.0.1:18080:18080 \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -v "$INSTALL_DIR/data:/app/data" \
      -v "$INSTALL_DIR/clients:/app/clients" \
      -v "$INSTALL_DIR/backups:/app/backups" \
      -v "$INSTALL_DIR/run:/app/run" \
      "$image" >/dev/null
  else
    printf 'Container %s not found, .env updated without container recreate.\n' "$CONTAINER" >&2
  fi
fi

cat <<EOF
3WG Panel admin credentials updated.
Env:      $ENV_FILE
Backup:   $BACKUP
User:     $PANEL_USER_VALUE
Password: $PANEL_PASSWORD_VALUE
Recreate: $RESTART_CONTAINER
EOF

if [ "$GENERATED_PASSWORD" = "1" ]; then
  printf '\nPassword was generated automatically. Save it now.\n'
fi
