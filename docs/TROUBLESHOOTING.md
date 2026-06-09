# Решение проблем

## Health-check не проходит

```bash
docker ps
docker logs --tail 100 3wg-panel
curl -v http://127.0.0.1:18080/health
```

Частые причины:

- контейнер не запущен
- ошибка в `.env`
- порт уже занят
- Docker socket не примонтирован

## Protocol показывает Offline или Unavailable

Проверьте имена контейнеров и интерфейсы:

```bash
docker ps
docker exec <container> wg show
```

Для AmneziaWG tool внутри контейнера должен соответствовать тому, что ожидает backend.

## QR или download неверный

Проверьте:

- `ENDPOINT_HOST`
- UDP port протокола
- сгенерированный файл клиента в `clients/`
- путь к protocol config внутри контейнера

## Installer или curl не может скачать Git

Если команда вида `curl https://raw.githubusercontent.com/.../scripts/install.sh` возвращает `404`, скорее всего репозиторий приватный. Для приватного GitHub это нормальное поведение.

Если `git clone git@github.com:...` падает с ошибкой:

```text
Permission denied (publickey).
fatal: Could not read from remote repository.
```

значит на сервере нет SSH-ключа, которому GitHub разрешает читать этот repository.

Создайте deploy key на сервере:

```bash
ssh-keygen -t ed25519 -C "3wg-panel-bright-violet" -f ~/.ssh/3wg_panel_deploy -N ""
cat ~/.ssh/3wg_panel_deploy.pub
```

Добавьте public key в GitHub:

```text
Repository -> Settings -> Deploy keys -> Add deploy key
```

Добавьте SSH config:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/3wg_panel_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T git@github.com || true
```

После этого повторите clone:

```bash
git clone --branch dev git@github.com:dblack-adminix/3wg-panel.git /opt/3wg-panel
cd /opt/3wg-panel
sudo bash scripts/install.sh
```

HTTPS clone без токена работает только для публичного репозитория. Для private repository используйте deploy key или GitHub token.

## Frontend build падает

Проверьте Node/npm:

```bash
node -v
npm -v
cd frontend
npm install
npm run build
```

## Проблемы с базой

SQLite database находится здесь:

```text
data/panel.db
```

Перед ручными изменениями обязательно сделайте backup.
