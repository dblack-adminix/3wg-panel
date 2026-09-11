# 3WG Easy Core

3WG Easy Core — упрощённая редакция 3WG Core для одного администратора и одного VPN-сервера. Редакции используют общую кодовую базу, формат базы и конфигураций.

## Что входит

- Пиры WireGuard и AmneziaWG, QR-коды и скачивание конфигов.
- Срок действия и лимит трафика.
- Статусы протоколов и краткий мониторинг.
- Ручные резервные копии и восстановление.
- API-ключи, интеграции, Telegram и P2P Guard.
- Обновление панели из веб-интерфейса.

В Easy Core нет пользовательских кабинетов и ролей, страницы аудита, мастера миграции, сетевых инструментов и расписания backup. Вход разрешён только владельцу из `PANEL_USER` и `PANEL_PASSWORD`.

> Не подключайте Core и Easy Core к одним VPN-контейнерам одновременно: обе панели могут изменять общие конфигурации.

## Требования

- Debian или Ubuntu и root-доступ;
- домен с A-записью на IP сервера;
- TCP `80/443` для панели;
- выбранные UDP-порты VPN.

Остальные зависимости установщик проверяет и устанавливает сам.

## Установка на новый сервер

Используйте стабильный тег:

```bash
sudo apt update
sudo apt install -y git
git clone --branch v1.6.5 --depth 1 https://github.com/dblack-adminix/3wg-panel.git /tmp/3wg-panel
cd /tmp/3wg-panel
sudo bash easy-core/install.sh
```

Рекомендуемые ответы:

```text
Git repository: https://github.com/dblack-adminix/3wg-panel.git
Git branch/tag: v1.6.5
Install directory: /opt/3wg-easy-core
Docker image name: 3wg-easy-core:local
Docker container name: 3wg-easy-core
Bind host: 127.0.0.1
Bind port: 18080
Panel public host / domain: vpn.example.com
VPN endpoint host / domain: vpn.example.com
VPN egress/source IP: [пусто для системного IP]
Configure Caddy reverse proxy: 1
Panel admin username: admin
Panel admin password: [пароль или пусто для генерации]
Protocol containers: 1
```

Замените `vpn.example.com` реальным доменом. Сгенерированный пароль выводится в конце установки — сохраните его сразу. В auto-create режиме рекомендуется `443/udp` для AmneziaWG, если порт разрешён провайдером. Он не конфликтует с HTTPS на `443/tcp`.

Проверка:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
curl -fsS http://127.0.0.1:18080/health
curl -I https://vpn.example.com/
```

## Существующие VPN-контейнеры

Узнайте точные имена:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
```

В установщике выберите:

```text
Protocol containers: 0
WireGuard container name: [точное имя WireGuard-контейнера]
AmneziaWG container name: [точное имя AmneziaWG-контейнера]
```

Установщик определит сети, порты и пути конфигураций. При неверном имени установка остановится сообщением «контейнер не найден».

## Сервер с двумя IP

- `Panel public host / domain` — домен веб-панели.
- `VPN endpoint host / domain` — домен в клиентских конфигах.
- `VPN egress/source IP` — второй IP, если VPN должен выходить именно через него.

Если отдельный исходящий IP не нужен, последнее поле оставьте пустым. После замены IP обновите DNS и выполните:

```bash
sudo bash /opt/3wg-easy-core/scripts/set_endpoint_hosts.sh
```

Строки приглашений вроде `Panel public host / domain:` вводятся внутри запущенного скрипта и не являются командами shell.

## Замена установленной 3WG Core на Easy Core

Сценарий сохраняет базу, пиры и клиентские файлы на том же сервере. VPN-контейнеры пересоздавать не нужно.

### 1. Резервная копия

```bash
cd /opt/3wg-panel
sudo tar -C /opt/3wg-panel -czf /root/3wg-core-before-easy-$(date +%F-%H%M).tar.gz data clients backups .env
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
```

Запишите имена WireGuard и AmneziaWG контейнеров.

### 2. Остановите только старую панель

```bash
docker update --restart=no 3wg-panel
docker stop 3wg-panel
```

VPN-контейнеры не останавливайте: действующие туннели продолжат работать.

### 3. Установите Easy Core

```bash
git clone --branch v1.6.5 --depth 1 https://github.com/dblack-adminix/3wg-panel.git /tmp/3wg-panel-easy
cd /tmp/3wg-panel-easy
sudo bash easy-core/install.sh
```

Укажите прежний домен, каталог `/opt/3wg-easy-core`, контейнер `3wg-easy-core`, bind `127.0.0.1:18080` и `Protocol containers: 0`. Затем введите записанные имена VPN-контейнеров.

### 4. Перенесите данные

```bash
docker stop 3wg-easy-core
sudo mv /opt/3wg-easy-core/data /opt/3wg-easy-core/data.empty
sudo mv /opt/3wg-easy-core/clients /opt/3wg-easy-core/clients.empty
sudo mkdir -p /opt/3wg-easy-core/data /opt/3wg-easy-core/clients
sudo cp -a /opt/3wg-panel/data/. /opt/3wg-easy-core/data/
sudo cp -a /opt/3wg-panel/clients/. /opt/3wg-easy-core/clients/
docker start 3wg-easy-core
```

Логин владельца и серверные параметры берутся из нового `.env`; пиры, лимиты, категории и API-ключи — из перенесённой базы.

### 5. Проверка и завершение

```bash
curl -fsS http://127.0.0.1:18080/health
docker logs --tail 100 3wg-easy-core
```

Проверьте список пиров, QR-коды, скачивание конфигов, оба протокола и создание тестового пира. После успешной проверки старый контейнер можно удалить командой `docker rm 3wg-panel`. Каталог `/opt/3wg-panel` и архив пока сохраните.

### Откат

```bash
docker update --restart=no 3wg-easy-core
docker stop 3wg-easy-core
docker start 3wg-panel
docker update --restart=unless-stopped 3wg-panel
curl -fsS http://127.0.0.1:18080/health
```

Если старый контейнер уже удалён, переустановите Core и восстановите `data` и `clients` из архива.

## Обновление

```bash
cd /opt/3wg-easy-core
sudo INSTALL_DIR=/opt/3wg-easy-core bash scripts/update.sh
```

`PANEL_EDITION=easy` в `.env` гарантирует сборку интерфейса Easy Core. Обновление также доступно на странице «Обновления», если установлен host runner.

## Сброс пароля

```bash
sudo INSTALL_DIR=/opt/3wg-easy-core bash /opt/3wg-easy-core/scripts/reset_admin_password.sh
```

## Ручная Compose-сборка

```bash
cd /path/to/3wg-panel
cp easy-core/.env.example easy-core/.env
chmod 600 easy-core/.env
docker compose -f easy-core/compose.yaml up -d --build
```

Заполните `easy-core/.env`: задайте `PANEL_PASSWORD`, `SESSION_SECRET`, домены и параметры существующих VPN-контейнеров. Compose слушает `127.0.0.1:18081` и не устанавливает Caddy или host runner.

## Основные пути

| Назначение | Путь |
|---|---|
| Установка | `/opt/3wg-easy-core` |
| Настройки | `/opt/3wg-easy-core/.env` |
| База | `/opt/3wg-easy-core/data` |
| Конфиги клиентов | `/opt/3wg-easy-core/clients` |
| Резервные копии | `/opt/3wg-easy-core/backups` |

## Диагностика

```bash
docker ps -a
docker logs --tail 200 3wg-easy-core
curl -v http://127.0.0.1:18080/health
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl status caddy --no-pager
```

Если локальный `/health` работает, а домен нет, проверяйте DNS, Caddy и TCP `80/443`. Если панель работает, а VPN нет — UDP-порт, firewall, имя и логи VPN-контейнера.

## Переезд на другой сервер

Замена редакции и перенос VPN на новый сервер — разные операции. Easy Core не содержит веб-мастера миграции. При ручном переносе необходимо сохранить домен endpoint, ключи, сети, порты, базу и клиентские файлы, а DNS переключать только после проверки нового сервера.
