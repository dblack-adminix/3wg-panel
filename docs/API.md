# REST API 3WG Core

Документ описывает внешний JSON API панели для интеграций: личного кабинета, биллинга, управляющего портала, automation scripts и мониторинга.

Если нужна только выдача и хранение API-ключей, см. [API_KEYS.md](API_KEYS.md).

## Базовые правила

- API доступен по тому же host, что и web-панель.
- Все ответы, кроме скачивания файлов и raw config, возвращаются как JSON.
- Для интеграций используйте HTTPS URL панели.
- Для локальной проверки на сервере можно использовать `http://127.0.0.1:18080`.
- API-key передаётся в header `X-API-Key`.
- API-key работает как admin integration key.
- Web session cookie используется UI, внешним системам лучше использовать `X-API-Key`.

```bash
BASE_URL="https://panel.example.com"
API_KEY="вставьте_token"
```

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/auth/me"
```

## Авторизация

### API-key

Создаётся в UI: `/apikeys`.

Header:

```http
X-API-Key: <token>
```

Token показывается один раз при создании. В базе хранится только hash.

Важно: текущая модель без granular scopes. Делайте отдельный ключ на каждую интеграцию и храните его как production secret.

### Cookie session

Используется web-интерфейсом:

```http
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

Для внешних интеграций cookie session не рекомендуется.

## Коды ошибок

Типовой error response:

```json
{
  "ok": false,
  "detail": "Описание ошибки"
}
```

Частые HTTP-коды:

- `400` — некорректный payload.
- `401` — нет авторизации.
- `403` — недостаточно прав.
- `404` — объект не найден или скрыт правами доступа.
- `409` — конфликт состояния, например истёк срок peer или лимит исчерпан.
- `500` — ошибка операции на сервере или внутри protocol container.

## Health и версия

### Health

`/health` не требует API-key и нужен для reverse proxy, uptime monitor и deploy checks.

```bash
curl -fsS "$BASE_URL/health"
```

Ответ:

```json
{"status":"ok"}
```

### Версия

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/version"
```

## Dashboard

### Получить dashboard

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/dashboard"
```

Возвращает:

- user;
- quota;
- cards;
- protocols;
- categories;
- peers;
- traffic/status данные для UI.

`/api/ui/dashboard` возвращает тот же dashboard payload и оставлен для совместимости UI.

## Peer API

Peer — это клиентский config в WireGuard или AmneziaWG.

### Получить список peer'ов

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers"
```

Обычный пользователь видит только свои peer'ы. Admin/API-key видит все.

### Создать peer

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "client-01",
    "protocols": ["amneziawg"],
    "category_id": null,
    "expires_at": null,
    "traffic_limit_bytes": 0
  }' \
  "$BASE_URL/api/peers"
```

Поля:

- `name` — имя клиента, обязательно.
- `protocols` — массив: `wireguard`, `amneziawg`.
- `category_id` — категория, только admin.
- `expires_at` — Unix timestamp срока действия, только admin.
- `traffic_limit_bytes` — лимит трафика peer, только admin.

Создать WireGuard и AmneziaWG одновременно:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"client-02","protocols":["wireguard","amneziawg"]}' \
  "$BASE_URL/api/peers"
```

### Получить peer

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123"
```

### Изменить peer

Доступно admin/API-key.

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "category_id": 1,
    "expires_at": null,
    "traffic_limit_bytes": 107374182400,
    "note": "Комментарий администратора"
  }' \
  "$BASE_URL/api/peers/123"
```

### Включить peer

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123/enable"
```

### Отключить peer

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123/disable"
```

### Сбросить счётчик трафика peer

Доступно admin/API-key.

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123/traffic-reset"
```

### Удалить peer

```bash
curl -fsS \
  -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123"
```

### Скачать raw config

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123/config"
```

Ответ — `text/plain`.

### Диагностика peer

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123/diagnostics"
```

## Категории

Категории доступны только admin/API-key.

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/categories"
```

Создать:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Limited"}' \
  "$BASE_URL/api/categories"
```

Переименовать:

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"VIP"}' \
  "$BASE_URL/api/categories/1"
```

Удалить:

```bash
curl -fsS \
  -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/categories/1"
```

При удалении категории peer'ы не удаляются, а переходят в `Без категории`.

## Пользователи панели

Доступно только admin/API-key.

### Список пользователей

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/users"
```

### Создать пользователя

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "client-admin",
    "password": "change-me-strong",
    "role": "user",
    "peer_limit": 3,
    "traffic_limit_bytes": 107374182400
  }' \
  "$BASE_URL/api/users"
```

Поля:

- `role`: `user` или `admin`.
- `peer_limit`: сколько peer'ов может создать пользователь.
- `traffic_limit_bytes`: общий лимит трафика пользователя.

### Изменить пользователя

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"peer_limit":5,"enabled":true}' \
  "$BASE_URL/api/users/2"
```

Сменить пароль:

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"password":"new-strong-password"}' \
  "$BASE_URL/api/users/2"
```

### Удалить пользователя

```bash
curl -fsS \
  -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/users/2"
```

Peer'ы удаляемого пользователя переходят администратору.

## Node, статусы и диагностика

### Protocol status

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/node/protocols"
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/node/status"
```

Ответ содержит `fornex_vpn_ports` — список UDP/TCP портов, которые Fornex указывает как доступные для VPN. Для WireGuard не используйте `51820`, если сервер стоит у Fornex: этот порт не входит в разрешённый список. Практичный вариант для WireGuard — один из портов диапазона `1116-1150`, например `1144/udp`, если он свободен. Для AmneziaWG обычно оставляйте `443/udp`.

### Сменить UDP-порт протокола

Доступно только администратору. Панель проверяет, что порт свободен, делает backup protocol config, меняет `ListenPort`, пересоздаёт protocol-контейнер с новым UDP mapping и обновляет `.env`.

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"port":1144,"confirm":"PORT"}' \
  "$BASE_URL/api/node/protocols/wireguard/port"
```

Разрешённые Fornex VPN ports:

```text
20, 21, 53, 80, 88, 110, 123, 143, 389, 443, 464, 500,
587, 636, 749, 853, 993, 995, 1116-1150, 1863,
3074-3079, 3268, 3269, 3283, 3306, 3389, 3478-3480,
3658, 3689, 3724, 4000, 4379, 4380, 4398, 4500, 5165,
5222, 5223, 5228-5230, 5235-5236, 5269, 5280
```

### Node diagnostics

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/node/diagnostics"
```

### System status

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/node/system"
```

### System history

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/node/system/history?hours=24"
```

## Traffic API

История трафика по protocol interface:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/traffic/history?protocol=amneziawg&days=30"
```

Параметры:

- `protocol`: `wireguard` или `amneziawg`.
- `days`: количество дней, обычно `30`.

## Tools API

### Ping

Ping с host namespace панели:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target":"1.1.1.1","count":4}' \
  "$BASE_URL/api/tools/ping"
```

Ping из protocol container:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target":"10.8.1.10","count":4,"protocol":"amneziawg"}' \
  "$BASE_URL/api/tools/ping"
```

### Traceroute

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target":"1.1.1.1","max_hops":20}' \
  "$BASE_URL/api/tools/traceroute"
```

## Backup API

Доступно admin/API-key.

Список:

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/backups"
```

Создать backup:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/backups"
```

Настроить auto backup:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"interval_hours":24,"keep_last":7}' \
  "$BASE_URL/api/backups/auto"
```

Создать auto backup сразу и сохранить настройки:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"interval_hours":24,"keep_last":7,"run_now":true}' \
  "$BASE_URL/api/backups/auto"
```

Скачать:

```bash
curl -fL \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/backups/backup-name.tgz/download" \
  -o backup-name.tgz
```

Удалить backup:

```bash
curl -fsS \
  -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/backups/backup-name.tgz"
```

Restore:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"confirm":"RESTORE"}' \
  "$BASE_URL/api/backups/backup-name.tgz/restore"
```

Restore создаёт pre-restore backup перед заменой `data/` и `clients/`.

## Migration API

Доступно admin/API-key. Migration bundle предназначен для переезда на другой сервер и содержит секреты: `.env`, server private keys и protocol config'и. Храните его как пароль администратора.

Список:

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/migration"
```

Создать bundle:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"include_backups":false}' \
  "$BASE_URL/api/migration/export"
```

Скачать:

```bash
curl -fL \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/migration/3wg-core.migration.node.example.2026-08-05_12-00-00.tgz/download" \
  -o migration.tgz
```

Удалить:

```bash
curl -fsS \
  -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/migration/3wg-core.migration.node.example.2026-08-05_12-00-00.tgz"
```

Статус host runner для автопереноса:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/migration/push"
```

Подготовить новый сервер и загрузить bundle:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "archive":"3wg-core.migration.node.example.2026-08-05_12-00-00.tgz",
    "host":"new-node.example",
    "port":22,
    "user":"root",
    "auth_method":"password",
    "password":"SSH_PASSWORD",
    "install_dir":"/opt/3wg-panel",
    "repo_url":"https://github.com/dblack-adminix/3wg-panel.git",
    "branch":"dev",
    "confirm":"MIGRATE"
  }' \
  "$BASE_URL/api/migration/push"
```

Для `auth_method:"key"` передайте `private_key` вместо `password`. SSH password/private key не сохраняются в базе и не попадают в audit context.

Этот endpoint не запускает import автоматически. Он только готовит проект на новом сервере и копирует archive. Команду для ручного import runner вернёт в job log.

Import выполняется на новом сервере root-скриптом:

```bash
cd /opt/3wg-panel
sudo bash scripts/migration_import.sh /path/to/migration.tgz
```

## Audit API

Доступно admin/API-key.

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/audit?limit=100"
```

Фильтры:

- `limit`: `1..500`.
- `action`: например `peer.create`.
- `actor`: username.
- `object_type`: например `peer`, `panel_user`, `backup`.

## Monitoring API

Управление Prometheus `/metrics` доступно admin/API-key.

Получить состояние:

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/monitoring"
```

Включить `/metrics`:

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true}' \
  "$BASE_URL/api/monitoring"
```

Создать или перевыпустить Prometheus token:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/monitoring/token"
```

Удалить token:

```bash
curl -fsS \
  -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/monitoring/token"
```

Сам `/metrics` обычно защищается header:

```http
Authorization: Bearer <prometheus_token>
```

## P2P Guard API

Доступно admin/API-key. Управляет BitTorrent/P2P фильтрацией внутри VPN-контейнеров.

Получить состояние:

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/p2p-guard"
```

Включить soft режим:

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"mode":"soft"}' \
  "$BASE_URL/api/p2p-guard"
```

Включить strict режим:

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"mode":"strict","allow_udp_ports":"53,123,443"}' \
  "$BASE_URL/api/p2p-guard"
```

Повторно применить текущие правила после перезапуска protocol-контейнеров:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/p2p-guard/apply"
```

## Telegram API

Доступно admin/API-key.

Получить настройки:

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/telegram"
```

Сохранить настройки:

```bash
curl -fsS \
  -X PATCH \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "bot_token": "123456:ABC",
    "chat_id": "-1001234567890"
  }' \
  "$BASE_URL/api/telegram"
```

Отправить тест:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/telegram/test"
```

## Update API

Доступно admin/API-key. Используйте осторожно: update запускает host runner.

Статус:

```bash
curl -fsS -H "X-API-Key: $API_KEY" "$BASE_URL/api/update/status"
```

Запуск:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"confirm":"UPDATE"}' \
  "$BASE_URL/api/update/run"
```

Точное значение `confirm` берите из `/api/update/status` → `runner.confirm_text`.

## Безопасность интеграций

- Не храните API-key в git.
- Не передавайте API-key в query string.
- Используйте HTTPS.
- Делайте отдельный API-key на каждую систему.
- Удаляйте ключ при компрометации или увольнении ответственного.
- Не используйте API-key панели как Prometheus token. Для `/metrics` есть отдельный token.
- Логи внешней системы не должны печатать headers.

## Минимальный пример интеграции

Создать peer и получить его config:

```bash
created="$(
  curl -fsS \
    -X POST \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"name":"demo-phone","protocols":["amneziawg"]}' \
    "$BASE_URL/api/peers"
)"

peer_id="$(printf '%s' "$created" | jq -r '.created_ids[0]')"

curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/$peer_id/config" \
  -o "demo-phone.conf"
```
