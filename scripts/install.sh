#!/usr/bin/env bash
set -euo pipefail

REPO_URL_DEFAULT="https://github.com/dblack-adminix/3wg-panel.git"
BRANCH_DEFAULT="dev"
INSTALL_DIR_DEFAULT="/opt/3wg-panel"
IMAGE_DEFAULT="3wg-panel:local"
CONTAINER_DEFAULT="3wg-panel"
BIND_HOST_DEFAULT="127.0.0.1"
BIND_PORT_DEFAULT="18080"

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1. Установите $1 и запустите скрипт снова."; }
ask() {
  local prompt="$1" default="${2:-}" value
  if [ -n "$default" ]; then
    read -r -p "$prompt [$default]: " value
    printf '%s' "${value:-$default}"
  else
    read -r -p "$prompt: " value
    printf '%s' "$value"
  fi
}
ask_secret() {
  local prompt="$1" default="${2:-}" value
  if [ -n "$default" ]; then
    read -r -s -p "$prompt [auto]: " value
    printf '\n' >&2
    printf '%s' "${value:-$default}"
  else
    read -r -s -p "$prompt: " value
    printf '\n' >&2
    printf '%s' "$value"
  fi
}
gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  fi
}

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите installer от root: sudo bash scripts/install.sh"
fi

need_cmd git
need_cmd docker
need_cmd npm
need_cmd curl
need_cmd python3

say "3WG Panel installer"
REPO_URL="$(ask 'Git repository' "$REPO_URL_DEFAULT")"
BRANCH="$(ask 'Git branch/tag' "$BRANCH_DEFAULT")"
INSTALL_DIR="$(ask 'Install directory' "$INSTALL_DIR_DEFAULT")"
IMAGE="$(ask 'Docker image name' "$IMAGE_DEFAULT")"
CONTAINER="$(ask 'Docker container name' "$CONTAINER_DEFAULT")"
BIND_HOST="$(ask 'Bind host' "$BIND_HOST_DEFAULT")"
BIND_PORT="$(ask 'Bind port' "$BIND_PORT_DEFAULT")"

ENDPOINT_HOST="$(ask 'Public endpoint host / domain' "$(hostname -f 2>/dev/null || hostname)")"
PANEL_USER="$(ask 'Panel admin username' 'admin')"
PANEL_PASSWORD="$(ask_secret 'Panel admin password, empty = auto-generate' "$(gen_secret | head -c 18)")"
SESSION_SECRET="$(gen_secret)"

WG_CONTAINER="$(ask 'WireGuard container name' 'amnezia-wireguard')"
WG_INTERFACE="$(ask 'WireGuard interface' 'wg0')"
WG_PORT="$(ask 'WireGuard UDP port' '51820')"
WG_CONFIG_PATH="$(ask 'WireGuard config path inside container' '/opt/amnezia/wireguard/wg0.conf')"
WG_NETWORK="$(ask 'WireGuard network CIDR' '10.8.1.0/24')"

AWG_CONTAINER="$(ask 'AmneziaWG container name' 'amnezia-awg2')"
AWG_INTERFACE="$(ask 'AmneziaWG interface' 'awg0')"
AWG_PORT="$(ask 'AmneziaWG UDP port' '42300')"
AWG_CONFIG_PATH="$(ask 'AmneziaWG config path inside container' '/opt/amnezia/awg/awg0.conf')"
AWG_NETWORK="$(ask 'AmneziaWG network CIDR' '10.8.1.0/24')"
DNS_SERVERS="$(ask 'Client DNS servers' '1.1.1.1, 1.0.0.1')"
HIDE_EXISTING_PEERS="$(ask 'Hide peers not created by panel? 1=yes, 0=no' '1')"

say "Preparing source"
mkdir -p "$(dirname "$INSTALL_DIR")"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" fetch --all --tags
  git -C "$INSTALL_DIR" checkout "$BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only || warn "Не удалось сделать fast-forward pull. Проверьте локальные изменения в $INSTALL_DIR."
elif [ -e "$INSTALL_DIR" ]; then
  fail "$INSTALL_DIR уже существует, но это не git repository"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
mkdir -p data clients backups/source

if [ -f .env ]; then
  cp .env "backups/source/.env.$(date +%F_%H-%M-%S).backup"
fi

cat > .env <<ENV
PANEL_USER=$PANEL_USER
PANEL_PASSWORD=$PANEL_PASSWORD

ENDPOINT_HOST=$ENDPOINT_HOST

WG_CONTAINER=$WG_CONTAINER
WG_INTERFACE=$WG_INTERFACE
WG_PORT=$WG_PORT
WG_CONFIG_PATH=$WG_CONFIG_PATH
WG_NETWORK=$WG_NETWORK

AWG_CONTAINER=$AWG_CONTAINER
AWG_INTERFACE=$AWG_INTERFACE
AWG_PORT=$AWG_PORT
AWG_CONFIG_PATH=$AWG_CONFIG_PATH
AWG_NETWORK=$AWG_NETWORK

DNS_SERVERS=$DNS_SERVERS
SESSION_SECRET=$SESSION_SECRET
HIDE_EXISTING_PEERS=$HIDE_EXISTING_PEERS
ENV
chmod 600 .env

say "Applying backend API patches"
python3 scripts/apply_api_patch.py
python3 scripts/apply_dashboard_model_patch.py
python3 -c "import py_compile; py_compile.compile('app/app.py', cfile='/tmp/3wg-panel-app.pyc', doraise=True)"

say "Building React frontend"
cd frontend
npm install
npm run build
cd "$INSTALL_DIR"

say "Building Docker image"
docker build -f app/Dockerfile -t "$IMAGE" .

say "Recreating container"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --env-file "$INSTALL_DIR/.env" \
  -p "$BIND_HOST:$BIND_PORT:18080" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$INSTALL_DIR/data:/app/data" \
  -v "$INSTALL_DIR/clients:/app/clients" \
  -v "$INSTALL_DIR/backups:/app/backups" \
  "$IMAGE" >/dev/null

say "Health check"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://$BIND_HOST:$BIND_PORT/health"; then
    printf '\n'
    break
  fi
  if [ "$i" = 10 ]; then
    docker logs --tail 80 "$CONTAINER" >&2 || true
    fail "Health check failed"
  fi
  sleep 2
done

cat <<DONE

3WG Panel installed.
URL:      http://$BIND_HOST:$BIND_PORT/
User:     $PANEL_USER
Password: $PANEL_PASSWORD
Path:     $INSTALL_DIR

Для HTTPS поставьте Caddy/Nginx перед $BIND_HOST:$BIND_PORT.
DONE
