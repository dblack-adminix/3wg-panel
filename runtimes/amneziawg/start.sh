#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${AWG_CONFIG_PATH:-/opt/amnezia/awg/awg0.conf}"
INTERFACE="${AWG_INTERFACE:-$(basename "$CONFIG_PATH" .conf)}"

echo "Container startup: 3WG AmneziaWG ($INTERFACE)"

sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
sysctl -w net.ipv4.conf.all.src_valid_mark=1 >/dev/null 2>&1 || true

awg-quick down "$CONFIG_PATH" >/dev/null 2>&1 || true
awg-quick up "$CONFIG_PATH"

network="${AWG_NETWORK:-}"
if [ -z "$network" ]; then
  address="$(awk -F= 'tolower($1) ~ /^[[:space:]]*address[[:space:]]*$/ { gsub(/[[:space:]]/, "", $2); split($2, a, ","); print a[1]; exit }' "$CONFIG_PATH")"
  prefix="${address#*/}"
  network_ip="$(ipcalc -n "$address" 2>/dev/null | awk -F= '/NETWORK/ { print $2; exit }')"
  [ -n "$network_ip" ] && network="$network_ip/$prefix"
fi
[ -n "$network" ] || network="10.50.0.0/24"

iptables -C INPUT -i "$INTERFACE" -j ACCEPT 2>/dev/null || iptables -A INPUT -i "$INTERFACE" -j ACCEPT
iptables -C FORWARD -i "$INTERFACE" -j ACCEPT 2>/dev/null || iptables -A FORWARD -i "$INTERFACE" -j ACCEPT
iptables -C OUTPUT -o "$INTERFACE" -j ACCEPT 2>/dev/null || iptables -A OUTPUT -o "$INTERFACE" -j ACCEPT
iptables -C FORWARD -i "$INTERFACE" -o eth0 -s "$network" -j ACCEPT 2>/dev/null || iptables -A FORWARD -i "$INTERFACE" -o eth0 -s "$network" -j ACCEPT
iptables -C FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -t nat -C POSTROUTING -s "$network" -o eth0 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s "$network" -o eth0 -j MASQUERADE

tail -f /dev/null
