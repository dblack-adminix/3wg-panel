#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR_DEFAULT="/opt/3wg-panel"
BRANCH_DEFAULT="dev"
IMAGE_DEFAULT="3wg-panel:local"
CONTAINER_DEFAULT="3wg-panel"
BIND_HOST_DEFAULT="127.0.0.1"
BIND_PORT_DEFAULT="18080"

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Не найдено: $1. Установите $1 и запустите скрипт снова."; }
prepare_git_worktree() {
  local app_status tracked_status app_backup

  app_status="$(git status --porcelain -- app/app.py || true)"
  if [ -n "$app_status" ]; then
    app_backup="backups/update/app.py.local.$(date +%F_%H-%M-%S).backup"
    warn "app/app.py содержит локальные generated-изменения. Сохраняю копию и возвращаю tracked-версию перед git pull."
    cp app/app.py "$app_backup"
    git restore app/app.py
    printf 'Source backup: %s\n' "$INSTALL_DIR/$app_backup"
  fi

  tracked_status="$(git status --porcelain --untracked-files=no)"
  if [ -n "$tracked_status" ]; then
    printf '%s\n' "$tracked_status" >&2
    fail "Есть локальные изменения в tracked-файлах. Updater не будет их перетирать автоматически."
  fi
}

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  fail "Запустите updater от root: sudo bash scripts/update.sh"
fi

need_cmd git
need_cmd docker
need_cmd npm
need_cmd curl
need_cmd python3

INSTALL_DIR="${INSTALL_DIR:-$INSTALL_DIR_DEFAULT}"
BRANCH="${BRANCH:-$BRANCH_DEFAULT}"
IMAGE="${IMAGE:-$IMAGE_DEFAULT}"
CONTAINER="${CONTAINER:-$CONTAINER_DEFAULT}"
BIND_HOST="${BIND_HOST:-$BIND_HOST_DEFAULT}"
BIND_PORT="${BIND_PORT:-$BIND_PORT_DEFAULT}"

[ -d "$INSTALL_DIR/.git" ] || fail "$INSTALL_DIR не является git repository. Укажите INSTALL_DIR=/path/to/3wg-panel"
[ -f "$INSTALL_DIR/.env" ] || fail "Не найден $INSTALL_DIR/.env. Сначала выполните install.sh"

cd "$INSTALL_DIR"
mkdir -p backups/update
BACKUP="backups/update/3wg-panel.update.$(date +%F_%H-%M-%S).tgz"

say "Creating backup"
tar --exclude=frontend/node_modules --exclude=frontend/dist --exclude=backups/update -czf "$BACKUP" .env data clients backups || fail "Backup failed"
printf 'Backup: %s\n' "$INSTALL_DIR/$BACKUP"

say "Updating source"
prepare_git_worktree
git fetch --all --tags
git checkout "$BRANCH"
git pull --ff-only

say "Applying backend API patches"
python3 scripts/apply_api_patch.py
python3 scripts/apply_dashboard_model_patch.py
python3 -c "import py_compile; py_compile.compile('app/app.py', cfile='/tmp/3wg-panel-app.pyc', doraise=True)"

say "Building React frontend"
cd frontend
npm install
npm run build
cd "$INSTALL_DIR"

say "Building Docker image"
docker build -f app/Dockerfile -t "$IMAGE" .

say "Recreating container"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --env-file "$INSTALL_DIR/.env" \
  -p "$BIND_HOST:$BIND_PORT:18080" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$INSTALL_DIR/data:/app/data" \
  -v "$INSTALL_DIR/clients:/app/clients" \
  -v "$INSTALL_DIR/backups:/app/backups" \
  "$IMAGE" >/dev/null

say "Health check"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://$BIND_HOST:$BIND_PORT/health"; then
    printf '\n'
    break
  fi
  if [ "$i" = 10 ]; then
    docker logs --tail 80 "$CONTAINER" >&2 || true
    fail "Health check failed. Backup is available at $INSTALL_DIR/$BACKUP"
  fi
  sleep 2
done

cat <<DONE

3WG Panel updated successfully.
Branch/tag: $BRANCH
Image:      $IMAGE
Container:  $CONTAINER
URL:        http://$BIND_HOST:$BIND_PORT/
Backup:     $INSTALL_DIR/$BACKUP
DONE
