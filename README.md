# 3WG Panel

3WG Panel — веб-панель для управления WireGuard и AmneziaWG peer'ами на серверной ноде. Backend написан на FastAPI, интерфейс — на React, развёртывание — через Docker.

## Возможности

- Управление WireGuard и AmneziaWG клиентами из одной панели.
- Генерация конфигов, QR-кодов и файлов для AmneziaVPN.
- Отображение статуса peer'ов, последнего handshake, RX/TX и состояния протоколов.
- Live-виджет трафика по интерфейсам.
- Подробные страницы истории трафика.
- Хранение состояния панели в SQLite.
- Постоянные volume'ы для базы, клиентов и backup'ов.
- Интерактивный installer для развёртывания с GitHub.

## Основные страницы

- `/` — главная панель
- `/client/<id>` — конфиг клиента, QR-коды, скачивание файлов
- `/status/wireguard` — статус WireGuard
- `/status/amneziawg` — статус AmneziaWG
- `/traffic/wireguard` — история трафика WireGuard
- `/traffic/amneziawg` — история трафика AmneziaWG
- `/health` — health-check

## Требования

На целевом сервере нужны:

- Linux server, рекомендуется Debian/Ubuntu
- Docker
- Git
- Node.js/npm для сборки React
- Python 3
- curl
- уже существующие WireGuard и/или AmneziaWG контейнеры
- доступ контейнера панели к `/var/run/docker.sock`

3WG Panel не устанавливает WireGuard или AmneziaWG самостоятельно. Панель управляет уже существующими protocol-контейнерами.

## Быстрая установка

Если репозиторий приватный, сначала настройте SSH deploy key на новом сервере:

```bash
ssh-keygen -t ed25519 -C "3wg-panel-bright-violet" -f ~/.ssh/3wg_panel_deploy -N ""
cat ~/.ssh/3wg_panel_deploy.pub
```

Скопируйте public key в GitHub: `Repository -> Settings -> Deploy keys -> Add deploy key`. Для установки достаточно read-only доступа. Затем добавьте SSH config:

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

После этого на новом сервере:

```bash
git clone --branch dev git@github.com:dblack-adminix/3wg-panel.git /opt/3wg-panel
cd /opt/3wg-panel
sudo bash scripts/install.sh
```

Если репозиторий публичный, можно использовать HTTPS clone:

```bash
git clone --branch dev https://github.com/dblack-adminix/3wg-panel.git /opt/3wg-panel
cd /opt/3wg-panel
sudo bash scripts/install.sh
```

Прямой `curl` с `raw.githubusercontent.com` для приватного репозитория вернёт `404`, это нормальное поведение GitHub.

Installer спросит:

- Git repository и branch/tag
- папку установки
- bind host и port
- публичный endpoint host/domain
- логин и пароль панели
- параметры WireGuard: container, interface, port, config path, network
- параметры AmneziaWG: container, interface, port, config path, network
- DNS servers
- скрывать ли peer'ы, созданные не панелью

Подробная инструкция: [docs/INSTALL.md](docs/INSTALL.md)

## Конфигурация

Для ручной установки скопируйте `.env.example` в `.env` и измените значения. Полное описание переменных: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## Эксплуатация

- Обновление через `scripts/update.sh`, backup, restore, logs, health-check: [docs/OPERATIONS.md](docs/OPERATIONS.md)
- Безопасность и reverse proxy: [docs/SECURITY.md](docs/SECURITY.md)
- Решение проблем: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Dev deploy на текущей ноде

Текущая dev-нода использует:

```bash
bash /srv/3wg-panel/scripts/deploy.sh
```

Этот скрипт специально привязан к dev-серверу. Для новых серверов используйте `scripts/install.sh`.

## Структура проекта

```text
app/                 FastAPI backend и static assets
frontend/            React frontend source
scripts/deploy.sh    dev deploy script для cz-prg-01
scripts/install.sh   интерактивный production installer
scripts/update.sh    production updater без перезаписи .env
docs/                документация
.env.example         шаблон окружения
```

## Версия

Текущая версия UI: `v1.0.0`

## Copyright

© 2026 3WG Panel. Контакты: [@vorchiks](https://t.me/vorchiks), [vitaly@goreev.ru](mailto:vitaly@goreev.ru), [3wg.ru](https://3wg.ru).

WireGuard является зарегистрированным товарным знаком Jason A. Donenfeld.
