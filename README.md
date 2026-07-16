# 3WG Panel

3WG Panel — веб-панель для управления WireGuard и AmneziaWG peer'ами на серверной ноде. Backend написан на FastAPI, интерфейс — на React, развёртывание — через Docker.

## Возможности

- Управление WireGuard и AmneziaWG клиентами из одной панели.
- Генерация конфигов, QR-кодов и файлов для AmneziaVPN.
- Отображение статуса peer'ов, последнего handshake, RX/TX и состояния протоколов.
- Live-виджет трафика по интерфейсам.
- Подробные страницы истории трафика.
- Multi-user режим: суперпользователь создаёт пользователей, назначает лимит peer'ов и общий лимит трафика.
- Prometheus `/metrics`, node_exporter/cAdvisor agent и стартовый Grafana dashboard.
- Telegram-уведомления о важных событиях панели.
- Update Center: проверка версии, ссылки на changelog и безопасная подготовка UI updater.
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
- `/users` — пользователи панели, лимиты peer'ов и суммарные лимиты трафика
- `/apikeys` — API-ключи для интеграций через `X-API-Key`
- `/monitoring` — Prometheus metrics, Prometheus token и Telegram notifications
- `/updates` — проверка версии и статус host update runner
- `/backups` — ручные backup'ы и restore состояния панели
- `/tools/health` — диагностика Docker, протоколов, endpoint'ов и reverse proxy
- `/health` — health-check
- `/metrics` — Prometheus metrics endpoint, если включён в `.env`

## Требования

На целевом сервере нужны:

- Linux server, рекомендуется Debian/Ubuntu
- Docker
- Git
- Node.js `>=20.19.0` или `>=22.12.0` и npm для сборки React; installer/update умеют автоматически поставить Node.js 22.x на Debian/Ubuntu
- Python 3
- curl
- уже существующие WireGuard/AmneziaWG контейнеры или auto-create режим installer
- доступ контейнера панели к `/var/run/docker.sock`

3WG Panel может работать с уже существующими protocol-контейнерами или создать WireGuard/AmneziaWG контейнеры автоматически во время установки.

## Быстрая установка

Если репозиторий публичный, установка на новом сервере максимально простая:

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/install.sh -o /tmp/3wg-install.sh
sudo bash /tmp/3wg-install.sh
```

Installer сам спросит Git repository и branch. По умолчанию используйте:

```text
Repository: https://github.com/dblack-adminix/3wg-panel.git
Branch: dev
```

Для ручного clone-варианта:

```bash
git clone --branch dev https://github.com/dblack-adminix/3wg-panel.git /opt/3wg-panel
cd /opt/3wg-panel
sudo bash scripts/install.sh
```

Installer спросит:

- Git repository и branch/tag
- папку установки
- bind host и port
- публичный endpoint host/domain
- логин и пароль панели
- режим protocol-контейнеров: использовать уже установленные или создать автоматически
- имена WireGuard и AmneziaWG контейнеров; в auto-create режиме WireGuard по умолчанию `wireguard-wg`, AmneziaWG по умолчанию `amnezia-awg2`
- для auto-create режима: UDP ports и network CIDR; AmneziaWG по умолчанию использует `443/udp`
- DNS servers
- скрывать ли peer'ы, созданные не панелью

Подробная инструкция: [docs/INSTALL.md](docs/INSTALL.md)

## Конфигурация

Для ручной установки скопируйте `.env.example` в `.env` и измените значения. Полное описание переменных: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## Эксплуатация

- Обновление через `scripts/update.sh`, backup, restore, logs, health-check: [docs/OPERATIONS.md](docs/OPERATIONS.md)
- Мониторинг через Prometheus/Grafana: [docs/MONITORING.md](docs/MONITORING.md)
- REST API для интеграций: [docs/API.md](docs/API.md)
- API-ключи и хранение token'ов: [docs/API_KEYS.md](docs/API_KEYS.md)
- Roadmap развития: [docs/ROADMAP.md](docs/ROADMAP.md)
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
runtimes/            Docker runtime для auto-create WireGuard/AmneziaWG
scripts/deploy.sh    dev deploy script для cz-prg-01
scripts/install.sh   интерактивный production installer
scripts/provision_protocols.sh auto-create protocol containers
scripts/reset_admin_password.sh смена пароля администратора панели
scripts/install_monitoring_agent.sh node_exporter + cAdvisor для Prometheus
scripts/update.sh    production updater без перезаписи .env
monitoring/          Prometheus rules и Grafana dashboard examples
docs/                документация
.env.example         шаблон окружения
```

## Версия

Текущая версия продукта: `v1.3.51`

## Copyright

© 2026 3WG Panel. Контакты: [@vorchiks](https://t.me/vorchiks), [vitaly@goreev.ru](mailto:vitaly@goreev.ru), [3wg.ru](https://3wg.ru), [GitHub](https://github.com/dblack-adminix/3wg-panel).

WireGuard является зарегистрированным товарным знаком Jason A. Donenfeld.
