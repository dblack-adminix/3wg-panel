#!/usr/bin/env bash
set -euo pipefail

BASE="/srv/3wg-panel"
APP="$BASE/app/app.py"
FRONT="$BASE/frontend"
IMAGE="3wg-panel:local"
CONTAINER="3wg-panel"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
node_major() { node -p "Number(process.versions.node.split('.')[0])" 2>/dev/null || printf '0'; }
node_minor() { node -p "Number(process.versions.node.split('.')[1])" 2>/dev/null || printf '0'; }
check_node_version() {
  local major minor
  major="$(node_major)"
  minor="$(node_minor)"
  if [ "$major" -lt 20 ] || { [ "$major" -eq 20 ] && [ "$minor" -lt 19 ]; }; then
    fail "Node.js $(node --version) слишком старый. Нужен Node.js >=20.19.0 или >=22.12.0 для сборки frontend."
  fi
}
install_frontend_deps() {
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
}
check_python_sources() {
  python3 -m py_compile "$APP" "$BASE/app/api_keys_store.py" "$BASE/scripts/apply_api_patch.py" "$BASE/scripts/apply_dashboard_model_patch.py"
}

printf '\n======================================================\n'
printf ' 3WG PANEL DEV DEPLOY - REACT FRONTEND\n'
printf '======================================================\n'

cd "$BASE"
check_node_version

printf '\n===== Backend/API patches =====\n'
python3 "$BASE/scripts/apply_api_patch.py"
python3 "$BASE/scripts/apply_dashboard_model_patch.py"

printf '\n===== Backend syntax check =====\n'
check_python_sources

printf '\n===== Frontend build =====\n'
cd "$FRONT"
install_frontend_deps
npm run build
cd "$BASE"

printf '\n===== Backup current source =====\n'
mkdir -p "$BASE/backups/source"
tar --exclude=frontend/node_modules -czf "$BASE/backups/source/3wg-panel-app.$(date +%F_%H-%M-%S).tgz" -C "$BASE" app scripts frontend docker-compose.yml

printf '\n===== Build Docker image =====\n'
docker build -f "$BASE/app/Dockerfile" -t "$IMAGE" "$BASE"

printf '\n===== Recreate 3WG Panel container =====\n'
docker rm -f "$CONTAINER" 2>/dev/null || true
docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --env-file "$BASE/.env" \
  -p 127.0.0.1:18080:18080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$BASE/data:/app/data" \
  -v "$BASE/clients:/app/clients" \
  -v "$BASE/backups:/app/backups" \
  "$IMAGE"

printf '\n===== Health check =====\n'
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:18080/health; then
    printf '\n'
    break
  fi
  if [ "$i" = 10 ]; then
    printf 'Health check failed after %s attempts\n' "$i" >&2
    docker logs --tail 80 "$CONTAINER" >&2 || true
    exit 1
  fi
  sleep 2
done

printf '\n===== React asset check =====\n'
curl -fsSI http://127.0.0.1:18080/logogrin.png | sed -n '1,8p'
curl -fsS http://127.0.0.1:18080/ | grep -q '<div id="root"></div>'
printf 'React index OK\n'

printf '\n===== Status =====\n'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | sed -n '1,5p'

printf '\nDONE\n'
