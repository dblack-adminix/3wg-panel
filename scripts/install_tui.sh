#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SCRIPT="$SCRIPT_DIR/install.sh"
INSTALL_SCRIPT_URL="${INSTALL_SCRIPT_URL:-https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/install.sh}"
WHIPTAIL_BIN="${WHIPTAIL_BIN:-whiptail}"
TITLE="3WG Installer"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cancelled() {
  printf 'Установка отменена. Изменения не применялись.\n'
  exit 0
}

ensure_whiptail() {
  if command -v "$WHIPTAIL_BIN" >/dev/null 2>&1; then
    return
  fi
  command -v apt-get >/dev/null 2>&1 || fail "Не найден whiptail. Установите пакет whiptail."
  DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get update
  DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get install -y whiptail
}

menu() {
  local prompt="$1"
  shift
  "$WHIPTAIL_BIN" --title "$TITLE" --menu "$prompt" 18 76 10 "$@" 3>&1 1>&2 2>&3 || cancelled
}

input() {
  local prompt="$1" default="${2:-}"
  "$WHIPTAIL_BIN" --title "$TITLE" --inputbox "$prompt" 10 76 "$default" 3>&1 1>&2 2>&3 || cancelled
}

password() {
  local prompt="$1"
  "$WHIPTAIL_BIN" --title "$TITLE" --passwordbox "$prompt" 10 76 3>&1 1>&2 2>&3 || cancelled
}

yesno() {
  local prompt="$1" default="${2:-yes}"
  local args=(--yesno "$prompt" 12 76)
  [ "$default" = "no" ] && args=(--defaultno "${args[@]}")
  "$WHIPTAIL_BIN" --title "$TITLE" "${args[@]}"
}

msg() {
  "$WHIPTAIL_BIN" --title "$TITLE" --msgbox "$1" 20 78
}

generate_password() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 24 | tr -d '/+=' | head -c 20
  else
    python3 -c 'import secrets; print(secrets.token_urlsafe(18))'
  fi
}

valid_host() {
  local value="$1"
  [ -n "$value" ] && [[ "$value" != *"://"* ]] && [[ "$value" != */* ]] && [[ "$value" != *" "* ]]
}

valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

backup_existing() {
  local target="$1" stamp backup items=()
  [ -d "$target" ] || return 0
  [ -e "$target/.env" ] && items+=(.env)
  [ -d "$target/data" ] && items+=(data)
  [ -d "$target/clients" ] && items+=(clients)
  [ "${#items[@]}" -gt 0 ] || return 0
  stamp="$(date +%Y-%m-%d_%H-%M-%S)"
  mkdir -p "$target/backups/install"
  backup="$target/backups/install/3wg.pre-tui-install.$stamp.tgz"
  tar -C "$target" -czf "$backup" "${items[@]}"
  printf 'Pre-install backup: %s\n' "$backup"
}

[ "${EUID:-$(id -u)}" -eq 0 ] || fail "Запустите: sudo bash scripts/install_tui.sh"
if [ ! -f "$INSTALL_SCRIPT" ]; then
  command -v curl >/dev/null 2>&1 || fail "Не найден $INSTALL_SCRIPT и curl недоступен для загрузки."
  curl -fsSL "$INSTALL_SCRIPT_URL" -o "$INSTALL_SCRIPT"
  chmod 700 "$INSTALL_SCRIPT"
fi
ensure_whiptail

edition="$(menu 'Выберите продукт' \
  core '3WG Core — полный функционал' \
  easy '3WG Easy Core — облегчённая версия')"

if [ "$edition" = "easy" ]; then
  default_dir="/opt/3wg-easy-core"
  default_image="3wg-easy-core:local"
  default_container="3wg-easy-core"
else
  default_dir="/opt/3wg-panel"
  default_image="3wg-panel:local"
  default_container="3wg-panel"
fi

install_mode="$(menu 'VPN-контейнеры' \
  create 'Создать WireGuard и AmneziaWG автоматически' \
  existing 'Использовать уже установленные контейнеры')"

panel_host="$(input 'Публичный домен панели (без https://)' "$(hostname -f 2>/dev/null || true)")"
valid_host "$panel_host" || { msg 'Некорректный домен панели.'; exit 1; }
vpn_host="$(input 'VPN endpoint: домен или IP для клиентских конфигураций' "$panel_host")"
valid_host "$vpn_host" || { msg 'Некорректный VPN endpoint.'; exit 1; }
install_dir="$(input 'Каталог установки' "$default_dir")"
bind_host="$(input 'Локальный адрес панели' '127.0.0.1')"
bind_port="$(input 'Локальный TCP-порт панели' '18080')"
valid_port "$bind_port" || { msg 'Порт панели должен быть числом от 1 до 65535.'; exit 1; }

if [ "$install_mode" = "create" ]; then
  provision=1
  wg_container="wireguard-wg"
  awg_container="amnezia-awg2"
  wg_port="$(input 'WireGuard UDP-порт' '51820')"
  awg_port="$(input 'AmneziaWG UDP-порт' '443')"
  valid_port "$wg_port" || { msg 'Некорректный WireGuard порт.'; exit 1; }
  valid_port "$awg_port" || { msg 'Некорректный AmneziaWG порт.'; exit 1; }
  wg_network="$(input 'WireGuard сеть CIDR' '10.49.0.0/24')"
  awg_network="$(input 'AmneziaWG сеть CIDR' '10.50.0.0/24')"
else
  provision=0
  wg_container="$(input 'Имя существующего WireGuard-контейнера' 'amnezia-wireguard')"
  awg_container="$(input 'Имя существующего AmneziaWG-контейнера' 'amnezia-awg2')"
  wg_port=51820
  awg_port=443
  wg_network='10.8.1.0/24'
  awg_network='10.8.1.0/24'
fi

dns_servers="$(input 'DNS для VPN-клиентов' '1.1.1.1, 1.0.0.1')"
panel_user="$(input 'Логин администратора' 'admin')"
panel_password="$(password 'Пароль администратора. Оставьте пустым для автоматической генерации.')"
[ -n "$panel_password" ] || panel_password="$(generate_password)"

setup_caddy=0
yesno "Настроить Caddy и HTTPS для $panel_host?" yes && setup_caddy=1
hide_peers=0
yesno 'Скрывать пиры, созданные вне панели?' yes && hide_peers=1
metrics=0
yesno 'Включить Prometheus /metrics?' no && metrics=1

summary="Продукт: $edition
Каталог: $install_dir
Панель: $panel_host
VPN endpoint: $vpn_host
Локальный адрес: $bind_host:$bind_port
VPN-контейнеры: $install_mode
WireGuard: $wg_container / UDP $wg_port
AmneziaWG: $awg_container / UDP $awg_port
Caddy HTTPS: $setup_caddy
Prometheus: $metrics

Перед изменением существующей установки будет создан backup.
Продолжить?"
yesno "$summary" no || cancelled

backup_existing "$install_dir"

export PANEL_EDITION="$edition"
export INSTALL_PRESET_MODE=1
export INSTALL_REPO_URL="${INSTALL_REPO_URL:-https://github.com/dblack-adminix/3wg-panel.git}"
export INSTALL_BRANCH="${INSTALL_BRANCH:-dev}"
export INSTALL_TARGET_DIR="$install_dir"
export INSTALL_IMAGE="$default_image"
export INSTALL_CONTAINER="$default_container"
export INSTALL_BIND_HOST="$bind_host"
export INSTALL_BIND_PORT="$bind_port"
export INSTALL_PANEL_HOST="$panel_host"
export INSTALL_VPN_ENDPOINT_HOST="$vpn_host"
export INSTALL_VPN_EGRESS_IP=""
export INSTALL_SETUP_CADDY="$setup_caddy"
export INSTALL_PANEL_USER="$panel_user"
export INSTALL_PANEL_PASSWORD="$panel_password"
export INSTALL_PROVISION_PROTOCOLS="$provision"
export INSTALL_WG_CONTAINER="$wg_container"
export INSTALL_WG_PORT="$wg_port"
export INSTALL_WG_NETWORK="$wg_network"
export INSTALL_AWG_CONTAINER="$awg_container"
export INSTALL_AWG_PORT="$awg_port"
export INSTALL_AWG_NETWORK="$awg_network"
export INSTALL_DNS_SERVERS="$dns_servers"
export INSTALL_HIDE_EXISTING_PEERS="$hide_peers"
export INSTALL_METRICS_ENABLED="$metrics"

if [ "${INSTALL_TUI_EXECUTE:-1}" = "0" ]; then
  printf 'TUI configuration validated; installer execution skipped.\n'
  exit 0
fi

exec bash "$INSTALL_SCRIPT"
