#!/usr/bin/env bash
set -euo pipefail

BASE="/srv/3wg-panel"
APP="$BASE/app/app.py"
FRONT="$BASE/frontend"
IMAGE="3wg-panel:local"
CONTAINER="3wg-panel"

printf '\n======================================================\n'
printf ' 3WG PANEL DEV DEPLOY - REACT FRONTEND\n'
printf '======================================================\n'

cd "$BASE"

printf '\n===== Backend/API patches =====\n'
python3 "$BASE/scripts/apply_api_patch.py"
python3 "$BASE/scripts/apply_dashboard_model_patch.py"

printf '\n===== Backend syntax check =====\n'
python3 -c "import py_compile; py_compile.compile('$APP', cfile='/tmp/3wg-panel-app.pyc', doraise=True)"

printf '\n===== Frontend build =====\n'
cd "$FRONT"
npm install
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
