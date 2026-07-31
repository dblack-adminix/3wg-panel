#!/usr/bin/env bash
set -euo pipefail

NODE_EXPORTER_IMAGE="${NODE_EXPORTER_IMAGE:-prom/node-exporter:v1.8.2}"
CADVISOR_IMAGE="${CADVISOR_IMAGE:-gcr.io/cadvisor/cadvisor:v0.49.1}"
NODE_EXPORTER_CONTAINER="${NODE_EXPORTER_CONTAINER:-3wg-node-exporter}"
CADVISOR_CONTAINER="${CADVISOR_CONTAINER:-3wg-cadvisor}"
MONITORING_BIND_HOST="${MONITORING_BIND_HOST:-127.0.0.1}"
NODE_EXPORTER_PORT="${NODE_EXPORTER_PORT:-9100}"
CADVISOR_PORT="${CADVISOR_PORT:-8080}"

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1"; }

need_cmd docker

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите от root: sudo bash scripts/install_monitoring_agent.sh"
fi

say "Installing 3WG monitoring agent"
printf 'Bind host:     %s\n' "$MONITORING_BIND_HOST"
printf 'node_exporter: %s:%s\n' "$MONITORING_BIND_HOST" "$NODE_EXPORTER_PORT"
printf 'cAdvisor:      %s:%s\n' "$MONITORING_BIND_HOST" "$CADVISOR_PORT"

if [ "$MONITORING_BIND_HOST" = "0.0.0.0" ]; then
  warn "Метрики будут слушать на всех интерфейсах. Ограничьте доступ firewall'ом или приватной сетью."
fi

say "Starting node_exporter"
docker rm -f "$NODE_EXPORTER_CONTAINER" >/dev/null 2>&1 || true
docker run -d \
  --name "$NODE_EXPORTER_CONTAINER" \
  --restart unless-stopped \
  --pid host \
  -p "$MONITORING_BIND_HOST:$NODE_EXPORTER_PORT:9100" \
  -v /:/host:ro,rslave \
  "$NODE_EXPORTER_IMAGE" \
  --path.rootfs=/host >/dev/null

say "Starting cAdvisor"
docker rm -f "$CADVISOR_CONTAINER" >/dev/null 2>&1 || true
CADVISOR_KMSG_ARGS=()
if [ -e /dev/kmsg ]; then
  CADVISOR_KMSG_ARGS=(--device /dev/kmsg)
fi
docker run -d \
  --name "$CADVISOR_CONTAINER" \
  --restart unless-stopped \
  -p "$MONITORING_BIND_HOST:$CADVISOR_PORT:8080" \
  -v /:/rootfs:ro \
  -v /var/run:/var/run:ro \
  -v /sys:/sys:ro \
  -v /var/lib/docker/:/var/lib/docker:ro \
  -v /dev/disk/:/dev/disk:ro \
  --privileged \
  "${CADVISOR_KMSG_ARGS[@]}" \
  "$CADVISOR_IMAGE" >/dev/null

say "Health checks"
for target in \
  "node_exporter http://$MONITORING_BIND_HOST:$NODE_EXPORTER_PORT/metrics" \
  "cAdvisor http://$MONITORING_BIND_HOST:$CADVISOR_PORT/metrics"
do
  name="${target%% *}"
  url="${target#* }"
  if curl -fsS --max-time 5 "$url" >/dev/null; then
    printf '%s OK\n' "$name"
  else
    warn "$name не ответил на $url. Проверьте docker logs."
  fi
done

cat <<DONE

Monitoring agent installed.

Containers:
  $NODE_EXPORTER_CONTAINER
  $CADVISOR_CONTAINER

Prometheus targets on this node:
  node_exporter: $MONITORING_BIND_HOST:$NODE_EXPORTER_PORT
  cAdvisor:      $MONITORING_BIND_HOST:$CADVISOR_PORT
  3WG Core:     panel-host:18080/metrics

For remote Prometheus prefer private IP/VPN or firewall allowlist.
DONE
