#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/srv/3wg-panel}"
if [ ! -d "$INSTALL_DIR" ] && [ -d /opt/3wg-panel ]; then
  INSTALL_DIR="/opt/3wg-panel"
fi
ENV_FILE="${ENV_FILE:-$INSTALL_DIR/.env}"

say() {
  printf '\n%s\n' "$*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

ask() {
  local label="$1"
  local default="${2:-}"
  local value
  if [ -n "$default" ]; then
    read -r -p "$label [$default]: " value
    printf '%s' "${value:-$default}"
  else
    read -r -p "$label: " value
    printf '%s' "$value"
  fi
}

env_get() {
  local key="$1"
  if [ -f "$ENV_FILE" ]; then
    sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
  fi
}

env_set() {
  local key="$1"
  local value="$2"
  local tmp
  tmp="$(mktemp)"
  if [ -f "$ENV_FILE" ]; then
    awk -v key="$key" -v value="$value" '
      BEGIN { done = 0 }
      $0 ~ "^" key "=" {
        if (!done) {
          print key "=" value
          done = 1
        }
        next
      }
      { print }
      END {
        if (!done) {
          print key "=" value
        }
      }
    ' "$ENV_FILE" > "$tmp"
  else
    printf '%s=%s\n' "$key" "$value" > "$tmp"
  fi
  install -m 600 "$tmp" "$ENV_FILE"
  rm -f "$tmp"
}

restart_panel() {
  local container
  container="$(env_get PANEL_CONTAINER)"
  container="${container:-3wg-panel}"
  if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -Fxq "$container"; then
    docker restart "$container" >/dev/null
    return
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q '^3wg-panel'; then
    systemctl restart 3wg-panel
  fi
}

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите от root: sudo bash scripts/set_endpoint_hosts.sh"
fi

mkdir -p "$(dirname "$ENV_FILE")"
if [ -f "$ENV_FILE" ]; then
  backup_dir="$INSTALL_DIR/backups/source"
  mkdir -p "$backup_dir"
  backup="$backup_dir/.env.endpoint-hosts.$(date +%Y-%m-%d_%H-%M-%S).backup"
  cp "$ENV_FILE" "$backup"
  chmod 600 "$backup"
else
  backup=""
fi

current_endpoint="$(env_get VPN_ENDPOINT_HOST)"
current_endpoint="${current_endpoint:-$(env_get ENDPOINT_HOST)}"
current_panel="$(env_get PANEL_HOST)"
current_panel="${current_panel:-$(env_get ENDPOINT_HOST)}"
current_egress="$(env_get VPN_EGRESS_IP)"

say "3WG Core endpoint settings"
panel_host="$(ask 'Panel public host / domain' "${current_panel:-$(hostname -f 2>/dev/null || hostname)}")"
vpn_endpoint_host="$(ask 'VPN endpoint host / domain' "${current_endpoint:-$panel_host}")"
vpn_egress_ip="$(ask 'VPN egress/source IP, empty = system default' "${current_egress:-}")"

[ -n "$panel_host" ] || fail "Panel host is empty"
[ -n "$vpn_endpoint_host" ] || fail "VPN endpoint host is empty"

env_set PANEL_HOST "$panel_host"
env_set ENDPOINT_HOST "$vpn_endpoint_host"
env_set VPN_ENDPOINT_HOST "$vpn_endpoint_host"
env_set VPN_EGRESS_IP "$vpn_egress_ip"

restart="${RESTART_PANEL:-1}"
if [ "$restart" = "1" ]; then
  restart_panel || fail "Не удалось перезапустить панель"
fi

cat <<DONE

3WG Core endpoint settings updated.
Env:          $ENV_FILE
Backup:       ${backup:-not created}
Panel host:   $panel_host
VPN endpoint: $vpn_endpoint_host
VPN egress IP:${vpn_egress_ip:- system default}
Restart:      $restart

Новые QR и .conf будут использовать VPN endpoint. Уже импортированные конфиги на телефонах нужно обновить/переимпортировать, если endpoint изменился.
DONE
