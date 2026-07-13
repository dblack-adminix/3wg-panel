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
apt_run() { DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get "$@"; }
run_timeout() {
  local seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  else
    "$@"
  fi
}
node_major() { node -p "Number(process.versions.node.split('.')[0])" 2>/dev/null || printf '0'; }
node_minor() { node -p "Number(process.versions.node.split('.')[1])" 2>/dev/null || printf '0'; }
node_version_ok() {
  local major minor
  major="$(node_major)"
  minor="$(node_minor)"
  { [ "$major" -eq 20 ] && [ "$minor" -ge 19 ]; } || { [ "$major" -eq 22 ] && [ "$minor" -ge 12 ]; } || [ "$major" -gt 22 ]
}
install_node_runtime() {
  command -v apt-get >/dev/null 2>&1 || fail "Node.js $(node --version 2>/dev/null || echo 'не найден') не подходит. Автоустановка доступна только на Debian/Ubuntu с apt-get."
  say "Installing Node.js 22.x"
  local setup_script
  setup_script="$(mktemp)"
  curl -fsSL https://deb.nodesource.com/setup_22.x -o "$setup_script"
  bash "$setup_script"
  rm -f "$setup_script"
  apt_run install -y nodejs
  hash -r
}
ensure_node_runtime() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 && node_version_ok; then
    return 0
  fi
  warn "Node.js $(node --version 2>/dev/null || echo 'не найден') не подходит. Нужен Node.js >=20.19.0 или >=22.12.0."
  install_node_runtime
  command -v node >/dev/null 2>&1 || fail "Node.js не установлен после bootstrap."
  command -v npm >/dev/null 2>&1 || fail "npm не установлен после bootstrap."
  node_version_ok || fail "После установки найден $(node --version), но нужна версия >=20.19.0 или >=22.12.0."
}
install_frontend_deps() {
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
}
check_python_sources() {
  python3 -m py_compile app/app.py app/api_keys_store.py scripts/apply_api_patch.py scripts/apply_dashboard_model_patch.py
}
prepare_existing_worktree() {
  local app_status tracked_status app_backup
  app_status="$(git status --porcelain -- app/app.py || true)"
  if [ -n "$app_status" ]; then
    mkdir -p backups/install
    app_backup="backups/install/app.py.local.$(date +%F_%H-%M-%S).backup"
    warn "app/app.py содержит локальные generated-изменения. Сохраняю копию и возвращаю tracked-версию перед git pull."
    cp app/app.py "$app_backup"
    git restore app/app.py
    printf 'Source backup: %s\n' "$INSTALL_DIR/$app_backup"
  fi
  tracked_status="$(git status --porcelain --untracked-files=no)"
  if [ -n "$tracked_status" ]; then
    printf '%s\n' "$tracked_status" >&2
    fail "Есть локальные изменения в tracked-файлах. Installer не будет их перетирать автоматически."
  fi
}
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
is_local_host() {
  case "${1:-}" in
    ""|localhost|127.*|0.0.0.0|::1)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}
docker_container_exists() {
  docker container inspect "$1" >/dev/null 2>&1
}
docker_udp_port() {
  docker port "$1" 2>/dev/null | awk '$1 ~ /\/udp$/ { port=$3; sub(/^.*:/, "", port); print port; exit }'
}
find_protocol_config_path() {
  local container="$1" protocol="$2"
  case "$protocol" in
    wireguard)
      docker exec "$container" sh -c 'for f in /opt/amnezia/wireguard/*.conf /etc/wireguard/*.conf /config/*.conf; do [ -f "$f" ] && printf "%s\n" "$f" && exit 0; done; exit 1' 2>/dev/null || true
      ;;
    amneziawg)
      docker exec "$container" sh -c 'for f in /opt/amnezia/awg/*.conf /opt/amnezia/amneziawg/*.conf /etc/wireguard/*.conf /config/*.conf; do [ -f "$f" ] && printf "%s\n" "$f" && exit 0; done; exit 1' 2>/dev/null || true
      ;;
  esac
}
config_interface_name() {
  local path="$1" name
  name="${path##*/}"
  printf '%s' "${name%.conf}"
}
config_listen_port() {
  local container="$1" path="$2"
  [ -n "$path" ] || return 0
  docker exec "$container" sh -c 'awk -F= "tolower(\$1) ~ /^[[:space:]]*listenport[[:space:]]*$/ { gsub(/[[:space:]]/, \"\", \$2); print \$2; exit }" "$1"' sh "$path" 2>/dev/null || true
}
config_network_cidr() {
  local container="$1" path="$2" address
  [ -n "$path" ] || return 0
  address="$(docker exec "$container" sh -c 'awk -F= "tolower(\$1) ~ /^[[:space:]]*address[[:space:]]*$/ { gsub(/[[:space:]]/, \"\", \$2); split(\$2, a, \",\"); print a[1]; exit }" "$1"' sh "$path" 2>/dev/null || true)"
  [ -n "$address" ] || return 0
  python3 - "$address" <<'PY' 2>/dev/null || true
import ipaddress
import sys

print(ipaddress.ip_interface(sys.argv[1]).network)
PY
}
detect_or_ask() {
  local label="$1" detected="$2" fallback="$3"
  if [ -n "$detected" ]; then
    printf 'Detected %s: %s\n' "$label" "$detected" >&2
    printf '%s' "$detected"
  else
    ask "$label" "$fallback"
  fi
}
detect_protocol_settings() {
  local title="$1" protocol="$2" container="$3" default_interface="$4" default_port="$5" default_config_path="$6" default_network="$7"
  local config_path interface port network

  docker_container_exists "$container" || fail "$title container '$container' не найден. Проверьте имя контейнера через docker ps."

  config_path="$(find_protocol_config_path "$container" "$protocol" | head -n 1)"
  interface=""
  [ -n "$config_path" ] && interface="$(config_interface_name "$config_path")"
  port="$(docker_udp_port "$container")"
  [ -n "$port" ] || port="$(config_listen_port "$container" "$config_path")"
  network="$(config_network_cidr "$container" "$config_path")"

  printf '\n%s detected settings\n' "$title" >&2
  DETECTED_INTERFACE="$(detect_or_ask "$title interface" "$interface" "$default_interface")"
  DETECTED_PORT="$(detect_or_ask "$title UDP port" "$port" "$default_port")"
  DETECTED_CONFIG_PATH="$(detect_or_ask "$title config path inside container" "$config_path" "$default_config_path")"
  DETECTED_NETWORK="$(detect_or_ask "$title network CIDR" "$network" "$default_network")"
}
setup_caddy_proxy() {
  local domain="$1" upstream_host="$2" upstream_port="$3"
  local caddyfile="/etc/caddy/Caddyfile"

  if is_local_host "$domain"; then
    warn "Caddy не настроен: публичный домен не задан."
    return 0
  fi

  if ! command -v caddy >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      say "Installing Caddy"
      apt_run update
      apt_run install -y caddy
    else
      warn "Caddy не найден, а apt-get недоступен. Настройте reverse proxy вручную."
      return 0
    fi
  fi

  mkdir -p /etc/caddy
  touch "$caddyfile"
  cp "$caddyfile" "$caddyfile.3wg-backup.$(date +%F_%H-%M-%S)"

  python3 - "$caddyfile" "$domain" "$upstream_host:$upstream_port" <<'PY'
from pathlib import Path
import sys

caddyfile = Path(sys.argv[1])
domain = sys.argv[2]
upstream = sys.argv[3]
start = f"# 3wg-panel:{domain}:start"
end = f"# 3wg-panel:{domain}:end"
block = f"{start}\n{domain} {{\n    reverse_proxy {upstream}\n}}\n{end}\n"
text = caddyfile.read_text(encoding="utf-8")

if start in text and end in text:
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    text = before.rstrip() + "\n\n" + block + after.lstrip("\n")
else:
    if text and not text.endswith("\n"):
        text += "\n"
    text = text.rstrip() + "\n\n" + block

caddyfile.write_text(text, encoding="utf-8")
PY

  caddy fmt --overwrite "$caddyfile" >/dev/null 2>&1 || true
  if ! run_timeout 15s caddy validate --config "$caddyfile" >/dev/null; then
    warn "Caddyfile не прошел проверку. Конфиг сохранен: $caddyfile"
    return 0
  fi
  if command -v systemctl >/dev/null 2>&1; then
    if ! run_timeout 25s systemctl enable --now caddy; then
      warn "systemctl enable/start caddy не завершился за 25 секунд. Проверьте: systemctl status caddy"
      return 0
    fi
    if ! run_timeout 25s systemctl reload caddy; then
      warn "systemctl reload caddy не завершился успешно. Пробую restart."
      if ! run_timeout 25s systemctl restart caddy; then
        warn "Caddy не удалось перезапустить автоматически. Проверьте: systemctl status caddy && journalctl -u caddy -n 80"
        return 0
      fi
    fi
  else
    run_timeout 25s caddy reload --config "$caddyfile" || warn "Caddyfile обновлен, но Caddy не удалось перезагрузить автоматически."
  fi
}

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите installer от root: sudo bash scripts/install.sh"
fi

need_cmd git
need_cmd docker
need_cmd curl
need_cmd python3
ensure_node_runtime

say "3WG Panel installer"
REPO_URL="$(ask 'Git repository' "$REPO_URL_DEFAULT")"
BRANCH="$(ask 'Git branch/tag' "$BRANCH_DEFAULT")"
INSTALL_DIR="$(ask 'Install directory' "$INSTALL_DIR_DEFAULT")"
IMAGE="$(ask 'Docker image name' "$IMAGE_DEFAULT")"
CONTAINER="$(ask 'Docker container name' "$CONTAINER_DEFAULT")"
BIND_HOST="$(ask 'Bind host' "$BIND_HOST_DEFAULT")"
BIND_PORT="$(ask 'Bind port' "$BIND_PORT_DEFAULT")"

ENDPOINT_HOST="$(ask 'Public endpoint host / domain' "$(hostname -f 2>/dev/null || hostname)")"
CADDY_DEFAULT="0"
if [ "$BIND_HOST" = "127.0.0.1" ] && ! is_local_host "$ENDPOINT_HOST"; then
  CADDY_DEFAULT="1"
fi
SETUP_CADDY="$(ask 'Configure Caddy reverse proxy for this domain? 1=yes, 0=no' "$CADDY_DEFAULT")"
PANEL_USER="$(ask 'Panel admin username' 'admin')"
PANEL_PASSWORD="$(ask_secret 'Panel admin password, empty = auto-generate' "$(gen_secret | head -c 18)")"
SESSION_SECRET="$(gen_secret)"

PROVISION_PROTOCOLS="$(ask 'Protocol containers: 1=auto create, 0=already installed' '0')"
if [ "$PROVISION_PROTOCOLS" = "1" ]; then
  WG_CONTAINER="$(ask 'WireGuard container name' 'wireguard-wg')"
  WG_PORT="$(ask 'WireGuard UDP port' '51820')"
  WG_NETWORK="$(ask 'WireGuard network CIDR' '10.49.0.0/24')"
  AWG_CONTAINER="$(ask 'AmneziaWG container name' 'amnezia-awg2')"
  AWG_PORT="$(ask 'AmneziaWG UDP port' '443')"
  AWG_NETWORK="$(ask 'AmneziaWG network CIDR' '10.50.0.0/24')"
else
  WG_CONTAINER="$(ask 'WireGuard container name' 'amnezia-wireguard')"
  WG_PORT="51820"
  WG_NETWORK="10.8.1.0/24"
  AWG_CONTAINER="$(ask 'AmneziaWG container name' 'amnezia-awg2')"
  AWG_PORT="42300"
  AWG_NETWORK="10.8.1.0/24"
fi
DNS_SERVERS="$(ask 'Client DNS servers' '1.1.1.1, 1.0.0.1')"
HIDE_EXISTING_PEERS="$(ask 'Hide peers not created by panel? 1=yes, 0=no' '1')"

say "Preparing source"
mkdir -p "$(dirname "$INSTALL_DIR")"
if [ -d "$INSTALL_DIR/.git" ]; then
  cd "$INSTALL_DIR"
  prepare_existing_worktree
  git -C "$INSTALL_DIR" fetch --all --tags
  git -C "$INSTALL_DIR" checkout "$BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only
elif [ -e "$INSTALL_DIR" ]; then
  fail "$INSTALL_DIR уже существует, но это не git repository"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
mkdir -p data clients backups/source

if [ "$PROVISION_PROTOCOLS" = "1" ]; then
  say "Provisioning protocol containers"
  WG_CONTAINER="$WG_CONTAINER" \
  WG_PORT="$WG_PORT" \
  WG_NETWORK="$WG_NETWORK" \
  AWG_CONTAINER="$AWG_CONTAINER" \
  AWG_PORT="$AWG_PORT" \
  AWG_NETWORK="$AWG_NETWORK" \
  bash scripts/provision_protocols.sh
fi

say "Detecting protocol settings"
detect_protocol_settings "WireGuard" "wireguard" "$WG_CONTAINER" "wg0" "$WG_PORT" "/opt/amnezia/wireguard/wg0.conf" "$WG_NETWORK"
WG_INTERFACE="$DETECTED_INTERFACE"
WG_PORT="$DETECTED_PORT"
WG_CONFIG_PATH="$DETECTED_CONFIG_PATH"
WG_NETWORK="$DETECTED_NETWORK"

detect_protocol_settings "AmneziaWG" "amneziawg" "$AWG_CONTAINER" "awg0" "$AWG_PORT" "/opt/amnezia/awg/awg0.conf" "$AWG_NETWORK"
AWG_INTERFACE="$DETECTED_INTERFACE"
AWG_PORT="$DETECTED_PORT"
AWG_CONFIG_PATH="$DETECTED_CONFIG_PATH"
AWG_NETWORK="$DETECTED_NETWORK"

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
check_python_sources

say "Building React frontend"
cd frontend
install_frontend_deps
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

PANEL_URL="http://$BIND_HOST:$BIND_PORT/"
if [ "$SETUP_CADDY" = "1" ]; then
  say "Configuring Caddy reverse proxy"
  setup_caddy_proxy "$ENDPOINT_HOST" "$BIND_HOST" "$BIND_PORT"
  PANEL_URL="https://$ENDPOINT_HOST/"
fi

cat <<DONE

3WG Panel installed.
URL:      $PANEL_URL
Local:    http://$BIND_HOST:$BIND_PORT/
User:     $PANEL_USER
Password: $PANEL_PASSWORD
Path:     $INSTALL_DIR

Если домен не открывается, проверьте DNS A-запись на IP сервера и доступность портов 80/443.
DONE
