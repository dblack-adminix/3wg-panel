#!/usr/bin/env bash
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_DIR="${NODE_DIR:-/srv/3wg-node}"

WG_CONTAINER="${WG_CONTAINER:-wireguard-wg}"
WG_INTERFACE="${WG_INTERFACE:-wg0}"
WG_PORT="${WG_PORT:-51820}"
WG_NETWORK="${WG_NETWORK:-10.49.0.0/24}"
WG_CONFIG_PATH="${WG_CONFIG_PATH:-/opt/amnezia/wireguard/${WG_INTERFACE}.conf}"
WG_IMAGE="${WG_IMAGE:-3wg-wireguard-runtime:local}"

AWG_CONTAINER="${AWG_CONTAINER:-amnezia-awg2}"
AWG_INTERFACE="${AWG_INTERFACE:-awg0}"
AWG_PORT="${AWG_PORT:-443}"
AWG_NETWORK="${AWG_NETWORK:-10.50.0.0/24}"
AWG_CONFIG_PATH="${AWG_CONFIG_PATH:-/opt/amnezia/awg/${AWG_INTERFACE}.conf}"
AWG_IMAGE="${AWG_IMAGE:-3wg-amneziawg-runtime:local}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1"; }

server_address() {
  python3 - "$1" <<'PY'
import ipaddress
import sys

net = ipaddress.ip_network(sys.argv[1], strict=False)
print(f"{next(net.hosts())}/{net.prefixlen}")
PY
}

ensure_host_networking() {
  modprobe tun >/dev/null 2>&1 || true
  modprobe wireguard >/dev/null 2>&1 || true

  mkdir -p /etc/sysctl.d
  cat > /etc/sysctl.d/99-3wg-node.conf <<'EOF_SYSCTL'
net.ipv4.ip_forward=1
net.ipv4.conf.all.src_valid_mark=1
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.default.rp_filter=0
EOF_SYSCTL
  sysctl --system >/dev/null || true
}

write_backup() {
  local path="$1"
  if [ -f "$path" ]; then
    cp "$path" "$path.3wg-backup.$(date +%F_%H-%M-%S)"
  fi
}

need_cmd docker
need_cmd python3

printf '\n===== Host networking =====\n'
ensure_host_networking

printf '\n===== Build VPN runtime images =====\n'
docker build -t "$WG_IMAGE" "$BASE/runtimes/wireguard"
docker build -t "$AWG_IMAGE" "$BASE/runtimes/amneziawg"

printf '\n===== Generate server configs =====\n'
mkdir -p "$NODE_DIR/wireguard" "$NODE_DIR/awg"

WG_HOST_CONFIG="$NODE_DIR/wireguard/${WG_INTERFACE}.conf"
AWG_HOST_CONFIG="$NODE_DIR/awg/${AWG_INTERFACE}.conf"
write_backup "$WG_HOST_CONFIG"
write_backup "$AWG_HOST_CONFIG"

WG_PRIVATE_KEY="$(docker run --rm --entrypoint sh "$WG_IMAGE" -lc 'wg genkey')"
AWG_PRIVATE_KEY="$(docker run --rm --entrypoint sh "$AWG_IMAGE" -lc 'awg genkey')"
WG_ADDRESS="$(server_address "$WG_NETWORK")"
AWG_ADDRESS="$(server_address "$AWG_NETWORK")"

cat > "$WG_HOST_CONFIG" <<EOF_WGCONF
[Interface]
PrivateKey = $WG_PRIVATE_KEY
Address = $WG_ADDRESS
ListenPort = $WG_PORT
EOF_WGCONF

cat > "$AWG_HOST_CONFIG" <<EOF_AWGCONF
[Interface]
PrivateKey = $AWG_PRIVATE_KEY
Jc = ${AWG_JC:-4}
Jmin = ${AWG_JMIN:-10}
Jmax = ${AWG_JMAX:-50}
S1 = ${AWG_S1:-54}
S2 = ${AWG_S2:-15}
S3 = ${AWG_S3:-36}
S4 = ${AWG_S4:-6}
H1 = ${AWG_H1:-718013012-1127562760}
H2 = ${AWG_H2:-1324176905-1725339417}
H3 = ${AWG_H3:-1781297739-2028576119}
H4 = ${AWG_H4:-2052615782-2092742079}
Address = $AWG_ADDRESS
ListenPort = $AWG_PORT
EOF_AWGCONF

chmod 600 "$WG_HOST_CONFIG" "$AWG_HOST_CONFIG"

printf '\n===== Recreate VPN containers =====\n'
docker rm -f "$WG_CONTAINER" >/dev/null 2>&1 || true
docker rm -f "$AWG_CONTAINER" >/dev/null 2>&1 || true

docker run -d \
  --name "$WG_CONTAINER" \
  --hostname "$WG_CONTAINER" \
  --restart unless-stopped \
  --privileged \
  --cap-add NET_ADMIN \
  --cap-add SYS_MODULE \
  --sysctl net.ipv4.conf.all.src_valid_mark=1 \
  -e WG_INTERFACE="$WG_INTERFACE" \
  -e WG_CONFIG_PATH="$WG_CONFIG_PATH" \
  -e WG_NETWORK="$WG_NETWORK" \
  -p "$WG_PORT:$WG_PORT/udp" \
  -v /lib/modules:/lib/modules:ro \
  -v "$NODE_DIR/wireguard:/opt/amnezia/wireguard" \
  "$WG_IMAGE" >/dev/null

docker run -d \
  --name "$AWG_CONTAINER" \
  --hostname "$AWG_CONTAINER" \
  --restart unless-stopped \
  --privileged \
  --cap-add NET_ADMIN \
  --cap-add SYS_MODULE \
  --sysctl net.ipv4.conf.all.src_valid_mark=1 \
  -e AWG_INTERFACE="$AWG_INTERFACE" \
  -e AWG_CONFIG_PATH="$AWG_CONFIG_PATH" \
  -e AWG_NETWORK="$AWG_NETWORK" \
  -p "$AWG_PORT:$AWG_PORT/udp" \
  -v /lib/modules:/lib/modules:ro \
  -v "$NODE_DIR/awg:/opt/amnezia/awg" \
  "$AWG_IMAGE" >/dev/null

sleep 2

printf '\n===== VPN containers =====\n'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | sed -n '1,8p'

printf '\nProvisioned protocol containers.\n'
printf 'WireGuard:  %s %s/udp %s %s\n' "$WG_CONTAINER" "$WG_PORT" "$WG_CONFIG_PATH" "$WG_NETWORK"
printf 'AmneziaWG:  %s %s/udp %s %s\n' "$AWG_CONTAINER" "$AWG_PORT" "$AWG_CONFIG_PATH" "$AWG_NETWORK"
