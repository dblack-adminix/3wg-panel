#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Python syntax =="
python3 -m py_compile app/app.py scripts/apply_api_patch.py scripts/apply_dashboard_model_patch.py

echo "== Frontend build =="
npm --prefix frontend run build

echo "== Local health =="
if curl -fsS --max-time 5 http://127.0.0.1:18080/health >/tmp/3wg-smoke-health.json; then
  cat /tmp/3wg-smoke-health.json
  printf '\n'
else
  echo "Panel is not reachable on 127.0.0.1:18080; skipping runtime health."
fi
