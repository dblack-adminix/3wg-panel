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
apt_run() { DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get "$@"; }
node_major() { node -p "Number(process.versions.node.split('.')[0])" 2>/dev/null || printf '0'; }
node_minor() { node -p "Number(process.versions.node.split('.')[1])" 2>/dev/null || printf '0'; }
node_version_ok() {
  local major minor
  major="$(node_major)"
  minor="$(node_minor)"
  { [ "$major" -eq 20 ] && [ "$minor" -ge 19 ]; } || { [ "$major" -eq 22 ] && [ "$minor" -ge 12 ]; } || [ "$major" -gt 22 ]
}
install_node_runtime() {
  command -v apt-get >/dev/null 2>&1 || fail "Node.js $(node --version 2>/dev/null || echo 'не найден') не подходит. Автоустановка доступна только на Debian/Ubuntu с apt-get."
  say "Installing Node.js 22.x"
  local setup_script
  setup_script="$(mktemp)"
  curl -fsSL https://deb.nodesource.com/setup_22.x -o "$setup_script"
  bash "$setup_script"
  rm -f "$setup_script"
  apt_run install -y nodejs
  hash -r
}
ensure_node_runtime() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 && node_version_ok; then
    return 0
  fi
  warn "Node.js $(node --version 2>/dev/null || echo 'не найден') не подходит. Нужен Node.js >=20.19.0 или >=22.12.0."
  install_node_runtime
  command -v node >/dev/null 2>&1 || fail "Node.js не установлен после bootstrap."
  command -v npm >/dev/null 2>&1 || fail "npm не установлен после bootstrap."
  node_version_ok || fail "После установки найден $(node --version), но нужна версия >=20.19.0 или >=22.12.0."
}
install_frontend_deps() {
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
}
verify_frontend_deps() {
  local i
  for i in 1 2 3 4 5; do
    if node -e "require.resolve('react'); require.resolve('react-dom/client'); require.resolve('vite')" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "Frontend dependencies are not ready after npm install"
}
build_frontend() {
  local i
  for i in 1 2 3; do
    if npm run build; then
      return 0
    fi
    printf 'Frontend build failed, retrying (%s/3)...\n' "$i" >&2
    verify_frontend_deps
    sleep 2
  done
  fail "Frontend build failed after retries"
}
remove_existing_container() {
  local i old_name
  docker update --restart=no "$CONTAINER" >/dev/null 2>&1 || true
  docker stop "$CONTAINER" >/dev/null 2>&1 || true
  docker rm "$CONTAINER" >/dev/null 2>&1 || true
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if ! docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER"; then
      return 0
    fi
    sleep 1
  done
  old_name="${CONTAINER}-old-$(date +%s)"
  docker rename "$CONTAINER" "$old_name" >/dev/null 2>&1 || true
  docker rm -f "$old_name" >/dev/null 2>&1 || true
  if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER"; then
    fail "Container name is still busy: $CONTAINER"
  fi
}
check_python_sources() {
  python3 -m py_compile app/app.py app/api_keys_store.py scripts/apply_api_patch.py scripts/apply_dashboard_model_patch.py scripts/update_runner.py
}
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
need_cmd curl
need_cmd python3
ensure_node_runtime

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
check_python_sources

say "Building React frontend"
cd frontend
install_frontend_deps
verify_frontend_deps
build_frontend
cd "$INSTALL_DIR"

say "Building Docker image"
docker build -f app/Dockerfile -t "$IMAGE" .

say "Installing update runner"
if command -v systemctl >/dev/null 2>&1; then
  BASE="$INSTALL_DIR" bash scripts/install_update_runner.sh
else
  warn "systemctl не найден, update runner не установлен"
fi

say "Recreating container"
mkdir -p "$INSTALL_DIR/run"
remove_existing_container
docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --env-file "$INSTALL_DIR/.env" \
  -p "$BIND_HOST:$BIND_PORT:18080" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$INSTALL_DIR/data:/app/data" \
  -v "$INSTALL_DIR/clients:/app/clients" \
  -v "$INSTALL_DIR/backups:/app/backups" \
  -v "$INSTALL_DIR/run:/app/run" \
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
