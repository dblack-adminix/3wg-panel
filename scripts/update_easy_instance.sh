#!/usr/bin/env bash
set -euo pipefail

BASE="${INSTALL_DIR:-/srv/3wg-panel}"
CONTAINER="${EASY_CONTAINER:-3wg-easy-preview}"
IMAGE="${EASY_IMAGE:-3wg-easy-preview:local}"
STATE_DIR="${EASY_STATE_DIR:-/srv/3wg-easy-preview}"
BIND_HOST="${EASY_BIND_HOST:-127.0.0.1}"
BIND_PORT="${EASY_BIND_PORT:-18081}"
BRANCH="${BRANCH:-dev}"

cd "$BASE"
git status --porcelain --untracked-files=no | grep -q . && { echo "Tracked source has local changes" >&2; exit 1; }
git fetch --all --tags
git checkout "$BRANCH"
git pull --ff-only
docker build -f easy-core/Dockerfile -t "$IMAGE" .

mapfile -t current_env < <(docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}')
env_args=()
for item in "${current_env[@]}"; do
  [ -n "$item" ] || continue
  case "$item" in UPDATE_RUNNER_ENABLED=*) continue ;; esac
  env_args+=(--env "$item")
done
env_args+=(--env UPDATE_RUNNER_ENABLED=1)

old="${CONTAINER}-old-$(date +%s)"
docker stop "$CONTAINER" >/dev/null
docker rename "$CONTAINER" "$old"
docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  -p "$BIND_HOST:$BIND_PORT:18080" \
  "${env_args[@]}" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$STATE_DIR/data:/app/data" \
  -v "$STATE_DIR/clients:/app/clients" \
  -v "$STATE_DIR/backups:/app/backups" \
  -v "$STATE_DIR/run:/app/run" \
  "$IMAGE" >/dev/null

for _ in $(seq 1 30); do
  curl -fsS "http://$BIND_HOST:$BIND_PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://$BIND_HOST:$BIND_PORT/health" >/dev/null
docker rm "$old" >/dev/null
echo "Easy Core instance updated: $CONTAINER"
