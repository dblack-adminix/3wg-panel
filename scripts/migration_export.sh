#!/usr/bin/env bash
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$BASE}"
OUT_DIR="${OUT_DIR:-$INSTALL_DIR/backups/migration}"
TIMESTAMP="$(date +%F_%H-%M-%S)"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
ARCHIVE_DEFAULT="$OUT_DIR/3wg-core.migration.${HOSTNAME_FQDN}.${TIMESTAMP}.tgz"
ARCHIVE="${1:-$ARCHIVE_DEFAULT}"
INCLUDE_BACKUPS="${INCLUDE_BACKUPS:-0}"

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
  fail "Запустите export от root: sudo bash scripts/migration_export.sh"
fi

need_cmd docker
need_cmd python3
need_cmd tar

[ -d "$INSTALL_DIR" ] || fail "INSTALL_DIR не найден: $INSTALL_DIR"
[ -f "$INSTALL_DIR/.env" ] || fail "Не найден $INSTALL_DIR/.env"

mkdir -p "$OUT_DIR"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/3wg-migration-export.XXXXXX")"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

copy_dir_if_exists() {
  local src="$1" dst="$2"
  if [ -d "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

copy_protocol_config() {
  local protocol="$1" container="$2" config_path="$3"
  local dst="$TMP_DIR/protocols/$protocol/config.conf"
  mkdir -p "$(dirname "$dst")"
  if [ -z "$container" ] || [ -z "$config_path" ]; then
    warn "$protocol: container/config path не задан в .env"
    return 0
  fi
  if ! docker container inspect "$container" >/dev/null 2>&1; then
    warn "$protocol: контейнер не найден: $container"
    return 0
  fi
  if docker cp "$container:$config_path" "$dst" >/dev/null 2>&1; then
    chmod 600 "$dst"
    printf '%s\n' "$config_path" > "$TMP_DIR/protocols/$protocol/config_path.txt"
    printf '%s\n' "$container" > "$TMP_DIR/protocols/$protocol/container.txt"
  else
    warn "$protocol: не удалось скопировать $container:$config_path"
  fi
}

say "Preparing migration bundle"
load_env_file "$INSTALL_DIR/.env"

mkdir -p "$TMP_DIR/panel" "$TMP_DIR/protocols"
cp "$INSTALL_DIR/.env" "$TMP_DIR/panel/.env"
copy_dir_if_exists "$INSTALL_DIR/data" "$TMP_DIR/panel/data"
copy_dir_if_exists "$INSTALL_DIR/clients" "$TMP_DIR/panel/clients"
if [ "$INCLUDE_BACKUPS" = "1" ]; then
  copy_dir_if_exists "$INSTALL_DIR/backups" "$TMP_DIR/panel/backups"
fi

copy_protocol_config "wireguard" "${WG_CONTAINER:-}" "${WG_CONFIG_PATH:-}"
copy_protocol_config "amneziawg" "${AWG_CONTAINER:-}" "${AWG_CONFIG_PATH:-}"

python3 - "$TMP_DIR/metadata.json" "$INSTALL_DIR" "$HOSTNAME_FQDN" "$INCLUDE_BACKUPS" <<'PY'
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

metadata_path = Path(sys.argv[1])
install_dir = sys.argv[2]
hostname = sys.argv[3]
include_backups = sys.argv[4] == "1"

def run(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"unavailable: {exc}"

payload = {
    "product": "3WG Core",
    "kind": "migration-bundle",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "source_hostname": hostname,
    "install_dir": install_dir,
    "include_backups": include_backups,
    "version": run(["bash", "-lc", f"cat {install_dir}/VERSION 2>/dev/null || true"]),
    "git_head": run(["bash", "-lc", f"git -C {install_dir} rev-parse HEAD 2>/dev/null || true"]),
    "kernel": platform.release(),
    "docker_ps": run(["docker", "ps", "--format", "{{.Names}} {{.Image}} {{.Status}} {{.Ports}}"]),
}
metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

python3 - "$TMP_DIR/SHA256SUMS" "$TMP_DIR" <<'PY'
import hashlib
import sys
from pathlib import Path

out = Path(sys.argv[1])
root = Path(sys.argv[2])
lines = []
for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    lines.append(f"{digest}  {path.relative_to(root)}")
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

say "Creating archive"
mkdir -p "$(dirname "$ARCHIVE")"
tar -C "$TMP_DIR" -czf "$ARCHIVE" .
chmod 600 "$ARCHIVE"

cat <<DONE

Migration bundle created.
Archive: $ARCHIVE

Что внутри:
- .env панели
- data/ с SQLite базой
- clients/ с клиентскими config/QR payload
- server-side WireGuard/AmneziaWG config из VPN-контейнеров

Для полного переноса на новый сервер скопируйте archive туда и запустите:
sudo bash scripts/migration_import.sh /path/to/$(basename "$ARCHIVE")
DONE
