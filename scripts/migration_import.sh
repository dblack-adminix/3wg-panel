#!/usr/bin/env bash
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$BASE}"
ARCHIVE="${1:-}"
PROVISION_PROTOCOLS="${PROVISION_PROTOCOLS:-auto}"
RESTORE_BACKUPS="${RESTORE_BACKUPS:-1}"
RESTART_PANEL="${RESTART_PANEL:-1}"
IMAGE="${IMAGE:-3wg-panel:local}"
CONTAINER="${CONTAINER:-3wg-panel}"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
BIND_PORT="${BIND_PORT:-18080}"

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1"; }
load_env_file() {
  local file="$1" line key value
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ""|\#*) continue ;;
      *=*)
        key="${line%%=*}"
        value="${line#*=}"
        case "$key" in
          *[!A-Za-z0-9_]*|"") continue ;;
        esac
        export "$key=$value"
        ;;
    esac
  done < "$file"
}

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите import от root: sudo bash scripts/migration_import.sh /path/to/archive.tgz"
fi

[ -n "$ARCHIVE" ] || fail "Укажите migration archive: sudo bash scripts/migration_import.sh /path/to/archive.tgz"
[ -f "$ARCHIVE" ] || fail "Archive не найден: $ARCHIVE"
[ -d "$INSTALL_DIR" ] || fail "INSTALL_DIR не найден: $INSTALL_DIR"

need_cmd docker
need_cmd python3
need_cmd tar

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/3wg-migration-import.XXXXXX")"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

backup_existing() {
  local backup_dir="$INSTALL_DIR/backups/migration"
  local backup="$backup_dir/3wg-core.pre-migration-import.$(date +%F_%H-%M-%S).tgz"
  mkdir -p "$backup_dir"
  if [ -f "$INSTALL_DIR/.env" ] || [ -d "$INSTALL_DIR/data" ] || [ -d "$INSTALL_DIR/clients" ]; then
    say "Creating pre-import backup"
    tar -C "$INSTALL_DIR" --exclude=frontend/node_modules --exclude=frontend/dist --exclude=backups/migration -czf "$backup" .env data clients backups 2>/dev/null || true
    chmod 600 "$backup" || true
    printf 'Backup: %s\n' "$backup"
  fi
}

copy_tree_replace() {
  local src="$1" dst="$2"
  if [ -d "$src" ]; then
    rm -rf "$dst"
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

docker_container_exists() {
  docker container inspect "$1" >/dev/null 2>&1
}

ensure_protocol_containers() {
  local need_provision=0
  if [ "$PROVISION_PROTOCOLS" = "1" ]; then
    need_provision=1
  elif [ "$PROVISION_PROTOCOLS" = "auto" ]; then
    if ! docker_container_exists "${WG_CONTAINER:-}" || ! docker_container_exists "${AWG_CONTAINER:-}"; then
      need_provision=1
    fi
  fi

  if [ "$need_provision" = "1" ]; then
    say "Provisioning protocol containers"
    WG_CONTAINER="$WG_CONTAINER" \
    WG_INTERFACE="$WG_INTERFACE" \
    WG_PORT="$WG_PORT" \
    WG_NETWORK="$WG_NETWORK" \
    WG_CONFIG_PATH="$WG_CONFIG_PATH" \
    AWG_CONTAINER="$AWG_CONTAINER" \
    AWG_INTERFACE="$AWG_INTERFACE" \
    AWG_PORT="$AWG_PORT" \
    AWG_NETWORK="$AWG_NETWORK" \
    AWG_CONFIG_PATH="$AWG_CONFIG_PATH" \
    bash "$INSTALL_DIR/scripts/provision_protocols.sh"
  fi
}

restore_protocol_config() {
  local protocol="$1" container="$2" config_path="$3"
  local src="$TMP_DIR/protocols/$protocol/config.conf"
  [ -f "$src" ] || { warn "$protocol: config отсутствует в archive"; return 0; }
  [ -n "$container" ] || { warn "$protocol: container не задан"; return 0; }
  [ -n "$config_path" ] || { warn "$protocol: config path не задан"; return 0; }
  docker_container_exists "$container" || { warn "$protocol: контейнер не найден: $container"; return 0; }

  say "Restoring $protocol config into $container:$config_path"
  docker exec "$container" sh -c 'mkdir -p "$(dirname "$1")"; [ ! -f "$1" ] || cp "$1" "$1.3wg-pre-migration.$(date +%F_%H-%M-%S)"' sh "$config_path"
  docker cp "$src" "$container:$config_path"
  docker exec "$container" sh -c 'chmod 600 "$1"' sh "$config_path"
  docker restart "$container" >/dev/null
}

say "Extracting migration archive"
tar -C "$TMP_DIR" -xzf "$ARCHIVE"
[ -f "$TMP_DIR/metadata.json" ] || fail "Archive не похож на migration bundle: нет metadata.json"
[ -f "$TMP_DIR/panel/.env" ] || fail "Archive не содержит panel/.env"

say "Migration metadata"
python3 - "$TMP_DIR/metadata.json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in ("product", "created_at", "source_hostname", "version", "git_head"):
    print(f"{key}: {data.get(key, '-')}")
PY

backup_existing

say "Restoring panel files"
cp "$TMP_DIR/panel/.env" "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"
copy_tree_replace "$TMP_DIR/panel/data" "$INSTALL_DIR/data"
copy_tree_replace "$TMP_DIR/panel/clients" "$INSTALL_DIR/clients"
if [ "$RESTORE_BACKUPS" = "1" ] && [ -d "$TMP_DIR/panel/backups" ]; then
  copy_tree_replace "$TMP_DIR/panel/backups" "$INSTALL_DIR/backups"
fi
mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/clients" "$INSTALL_DIR/backups"

load_env_file "$INSTALL_DIR/.env"

CONTAINER="${PANEL_CONTAINER:-$CONTAINER}"
ensure_protocol_containers
restore_protocol_config "wireguard" "${WG_CONTAINER:-}" "${WG_CONFIG_PATH:-}"
restore_protocol_config "amneziawg" "${AWG_CONTAINER:-}" "${AWG_CONFIG_PATH:-}"

if [ "$RESTART_PANEL" = "1" ]; then
  say "Rebuilding and restarting panel"
  bash "$INSTALL_DIR/scripts/update.sh"
else
  warn "Panel restart skipped because RESTART_PANEL=0"
fi

cat <<DONE

Migration import finished.

Проверьте до переключения DNS:
- docker ps
- http://127.0.0.1:18080/health
- UDP ports: WireGuard ${WG_PORT:-?}/udp, AmneziaWG ${AWG_PORT:-?}/udp

Для незаметного переезда DNS A-запись endpoint-домена должна указывать на новый сервер.
DONE
