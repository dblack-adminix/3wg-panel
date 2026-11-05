#!/usr/bin/env bash
set -euo pipefail
role="${PILOT_ROLE:?PILOT_ROLE is required}"
[[ "$role" == entry || "$role" == exit ]] || exit 2
if [[ "${PILOT_ENGINE:-wireguard}" == amneziawg ]]; then
    awg-quick up /config/wg-cascade.conf
else
    wg-quick up /config/wg-cascade.conf
fi
iptables -P FORWARD DROP
if [[ "$role" == exit ]]; then
    ip route add 10.203.0.0/24 dev wg-cascade
    iptables -A FORWARD -i wg-cascade -o eth0 -s 10.203.0.0/24 -j ACCEPT
    iptables -A FORWARD -i wg-cascade -o eth0 -s 10.254.203.1/32 -j ACCEPT
    iptables -A FORWARD -i eth0 -o wg-cascade -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    iptables -t nat -A POSTROUTING -s 10.203.0.0/24 -o eth0 -j MASQUERADE
    iptables -t nat -A POSTROUTING -s 10.254.203.1/32 -o eth0 -j MASQUERADE
else
    ip route add default dev wg-cascade table 200
    ip rule add priority 200 from 10.203.0.0/24 table 200
    ip rule add priority 201 from 10.254.203.1/32 table 200
    # No physical-uplink forwarding fallback when the exit disappears.
    iptables -A FORWARD -i wg-clients -o wg-cascade -s 10.203.0.0/24 -j ACCEPT
    iptables -A FORWARD -i wg-cascade -o wg-clients -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
fi
exec tail -f /dev/null
