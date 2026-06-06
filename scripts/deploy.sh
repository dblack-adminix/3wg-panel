#!/usr/bin/env bash
set -euo pipefail

BASE="/srv/3wg-panel"
APP="$BASE/app/app.py"

echo "======================================================"
echo " 3WG PANEL DEV DEPLOY"
echo "======================================================"

cd "$BASE"

echo
echo "===== Syntax check ====="
python3 -m py_compile "$APP"
echo "app.py syntax OK"

echo
echo "===== Backup current source ====="
mkdir -p "$BASE/backups/source"

tar -czf "$BASE/backups/source/3wg-panel-app.$(date +%F_%H-%M-%S).tgz" \
  -C "$BASE" app

echo
echo "===== Rebuild Docker image ====="
docker rm -f 3wg-panel 2>/dev/null || true
docker rmi 3wg-panel:local 2>/dev/null || true

docker build -t 3wg-panel:local "$BASE/app"

echo
echo "===== Run 3WG Panel ====="
docker run -d \
  --name 3wg-panel \
  --restart unless-stopped \
  --env-file "$BASE/.env" \
  -p 127.0.0.1:18080:18080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$BASE/data:/app/data" \
  -v "$BASE/clients:/app/clients" \
  -v "$BASE/backups:/app/backups" \
  3wg-panel:local

sleep 4

echo
echo "===== Health check ====="
docker exec 3wg-panel python - <<'PY'
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:18080/health").read().decode())
PY

echo
echo "===== Status ====="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "DONE"
