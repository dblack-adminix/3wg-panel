#!/usr/bin/env bash
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE"
command -v docker >/dev/null || { echo "Docker не установлен" >&2; exit 1; }
docker compose version >/dev/null || { echo "Docker Compose plugin не установлен" >&2; exit 1; }

read -r -p "Control Center username [admin]: " user
user="${user:-admin}"
read -r -s -p "Control Center password [generate]: " password
echo
password="${password:-$(openssl rand -base64 24 | tr -d '\n')}"
session_secret="$(openssl rand -hex 32)"
fernet_key="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"

if [ -f .env ]; then
  cp .env ".env.backup.$(date +%F-%H%M%S)"
fi
umask 077
printf 'CONTROL_USER=%s\nCONTROL_PASSWORD=%s\nSESSION_SECRET=%s\nNODE_ENCRYPTION_KEY=%s\nCONTROL_DB=/app/data/control.db\nSESSION_HTTPS_ONLY=1\n' \
  "$user" "$password" "$session_secret" "$fernet_key" > .env
mkdir -p data
docker compose up -d --build

echo
echo "3WG Control Center запущен на http://127.0.0.1:18082"
echo "User: $user"
echo "Password: $password"
echo "Настройте HTTPS reverse proxy перед внешним доступом."
