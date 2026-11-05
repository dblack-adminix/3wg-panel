#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")"
test "$(id -u)" = 0
test ! -e /opt/3wg-exit
test ! -e /usr/local/libexec/3wg-exit-agent.py
test -c /dev/net/tun
. /etc/os-release
case "$ID" in debian|ubuntu) ;; *) exit 20;; esac
python3 -c 'import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(("0.0.0.0",54443));s.close()'
if ! command -v docker >/dev/null; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io ca-certificates
fi
systemctl enable --now docker
if docker container inspect 3wg-exit >/dev/null 2>&1; then exit 21; fi
mkdir -m 700 /opt/3wg-exit
install -m 600 exit0.conf /opt/3wg-exit/exit0.conf
install -m 644 Dockerfile start.sh /opt/3wg-exit/
mkdir -p /usr/local/libexec
install -m 700 agent.py /usr/local/libexec/3wg-exit-agent.py
docker build -t 3wg-exit:managed /opt/3wg-exit
docker run -d --name 3wg-exit --restart unless-stopped --cap-add NET_ADMIN \
    --device /dev/net/tun --read-only --tmpfs /tmp --tmpfs /run \
    --sysctl net.ipv4.ip_forward=1 --sysctl net.ipv4.conf.all.rp_filter=0 \
    -p 54443:54443/udp -v /opt/3wg-exit/exit0.conf:/config/exit0.conf:ro \
    3wg-exit:managed
mkdir -p /root/.ssh
chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys
cp -p /root/.ssh/authorized_keys /opt/3wg-exit/authorized_keys.before
cat service.pub >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
docker inspect --format '{{.State.Running}}' 3wg-exit | grep -qx true
