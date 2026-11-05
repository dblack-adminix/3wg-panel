#!/bin/sh
set -eu
awg-quick up /config/exit0.conf
iptables -P FORWARD DROP
iptables -A FORWARD -i exit0 -o eth0 -s 10.203.0.0/16 -j ACCEPT
iptables -A FORWARD -i eth0 -o exit0 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -t nat -A POSTROUTING -s 10.203.0.0/16 -o eth0 -j MASQUERADE
exec tail -f /dev/null
