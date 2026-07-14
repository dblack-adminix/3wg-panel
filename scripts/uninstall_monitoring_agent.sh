#!/usr/bin/env bash
set -euo pipefail

NODE_EXPORTER_CONTAINER="${NODE_EXPORTER_CONTAINER:-3wg-node-exporter}"
CADVISOR_CONTAINER="${CADVISOR_CONTAINER:-3wg-cadvisor}"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  printf 'Запустите от root: sudo bash scripts/uninstall_monitoring_agent.sh\n' >&2
  exit 1
fi

docker rm -f "$NODE_EXPORTER_CONTAINER" >/dev/null 2>&1 || true
docker rm -f "$CADVISOR_CONTAINER" >/dev/null 2>&1 || true

printf '3WG monitoring agent removed.\n'
