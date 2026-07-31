# API-ключи 3WG Core

API-ключи нужны для внешних интеграций: скриптов, биллинга, портала клиентов, автоматизации выдачи peer'ов и мониторинга состояния панели.

Полное описание REST API, endpoint'ов и payload'ов: [API.md](API.md).

Ключ передаётся в HTTP header:

```http
X-API-Key: <token>
```

Сам token показывается только один раз при создании на странице `/apikeys`. В SQLite хранится только hash, prefix/suffix для отображения и служебные поля. Если token потерян, его нужно удалить и создать новый.

## Создание ключа

1. Войдите в панель как super admin.
2. Откройте `/apikeys`.
3. Укажите понятное имя интеграции.
4. Нажмите `Создать ключ`.
5. Скопируйте token сразу после создания и сохраните в secret storage.

## Права API-ключа

Текущая модель прав: API-ключ работает как admin integration key.

Через `X-API-Key` можно обращаться к основным JSON API панели, включая:

- чтение dashboard;
- чтение списка peer'ов;
- создание peer'ов;
- изменение peer'ов;
- включение/отключение peer'ов;
- удаление peer'ов;
- чтение статуса node/protocols;
- чтение истории трафика;
- запуск диагностических tools;
- управление пользователями панели;
- изменение monitoring settings.

Управление самими API-ключами через API-ключ запрещено. Endpoint'ы `/api/apikeys` доступны только через web cookie session администратора, чтобы украденный integration key не мог создавать новые ключи.

Важно: сейчас у API-ключа нет granular scopes. Выпускайте отдельный ключ на каждую интеграцию и считайте его высокопривилегированным секретом. Scoped API keys запланированы в roadmap.

## Базовый URL

Для локальной проверки на сервере:

```bash
BASE_URL="http://127.0.0.1:18080"
API_KEY="вставьте_token"
```

Для внешней интеграции используйте HTTPS URL панели:

```bash
BASE_URL="https://panel.example.com"
API_KEY="вставьте_token"
```

## Примеры curl

Проверить текущего пользователя API:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/auth/me"
```

Получить dashboard:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/dashboard"
```

Получить список peer'ов:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers"
```

Создать AmneziaWG peer:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"client-01","protocols":["amneziawg"],"category_id":null}' \
  "$BASE_URL/api/peers"
```

Создать WireGuard и AmneziaWG peer одновременно:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"client-02","protocols":["wireguard","amneziawg"]}' \
  "$BASE_URL/api/peers"
```

Отключить peer:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123/disable"
```

Включить peer:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123/enable"
```

Удалить peer:

```bash
curl -fsS \
  -X DELETE \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123"
```

Получить конфиг peer:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/peers/123/config"
```

Получить статус протоколов:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/node/status"
```

Получить System Status:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/node/system"
```

Получить историю трафика:

```bash
curl -fsS \
  -H "X-API-Key: $API_KEY" \
  "$BASE_URL/api/traffic/history?protocol=amneziawg&days=30"
```

Запустить ping из панели:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target":"1.1.1.1","count":4}' \
  "$BASE_URL/api/tools/ping"
```

Запустить ping из protocol-контейнера:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target":"10.8.1.10","count":4,"protocol":"amneziawg"}' \
  "$BASE_URL/api/tools/ping"
```

Запустить traceroute:

```bash
curl -fsS \
  -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target":"1.1.1.1","max_hops":20}' \
  "$BASE_URL/api/tools/traceroute"
```

## Endpoint'ы

Доступны через `X-API-Key`:

```text
GET    /api/auth/me
POST   /api/auth/logout
GET    /api/version
GET    /api/dashboard
GET    /api/ui/dashboard
GET    /api/node/protocols
GET    /api/node/status
GET    /api/node/diagnostics
GET    /api/node/system
GET    /api/node/system/history
GET    /api/peers
POST   /api/peers
GET    /api/peers/{client_id}
PATCH  /api/peers/{client_id}
GET    /api/peers/{client_id}/config
GET    /api/peers/{client_id}/diagnostics
POST   /api/peers/{client_id}/enable
POST   /api/peers/{client_id}/disable
DELETE /api/peers/{client_id}
GET    /api/categories
POST   /api/categories
PATCH  /api/categories/{category_id}
DELETE /api/categories/{category_id}
GET    /api/traffic/history
GET    /api/backups
POST   /api/backups
GET    /api/backups/{name}/download
POST   /api/backups/{name}/restore
POST   /api/tools/ping
POST   /api/tools/traceroute
GET    /api/users
POST   /api/users
PATCH  /api/users/{user_id}
DELETE /api/users/{user_id}
GET    /api/monitoring
PATCH  /api/monitoring
POST   /api/monitoring/token
DELETE /api/monitoring/token
GET    /api/telegram
PATCH  /api/telegram
POST   /api/telegram/test
GET    /api/update/status
POST   /api/update/run
```

Для пользователей поле `traffic_limit_bytes` задаёт общий лимит трафика в байтах по всем peer'ам этого аккаунта. Если значение `0`, лимит отключён. В ответе `/api/users` поле `traffic_limit` показывает использовано, осталось, процент заполнения и флаг `exceeded`.

Для peer'ов `PATCH /api/peers/{client_id}` поддерживает поля `category_id`, `expires_at`, `traffic_limit_bytes` и `note`. `note` хранит короткую административную заметку до 500 символов.

Telegram notifications настраиваются через `/monitoring` или API `/api/telegram`. В ответах bot token не раскрывается, показывается только suffix. Уведомления уходят при создании, включении, отключении и удалении peer'ов, создании backup, истечении срока peer и превышении traffic limit.

Update Center доступен через `/updates`. `POST /api/update/run` запускает updater только через host-side Unix socket runner. Контейнер панели подключается к `/app/run/update-runner.sock`, а сам runner на хосте выполняет `scripts/update.sh`. Перед запуском создаётся backup `pre-ui-update`.

Только через web session администратора:

```text
GET    /api/apikeys
POST   /api/apikeys
DELETE /api/apikeys/{key_id}
```

## Безопасность

- Не передавайте token через query string.
- Не храните token в Git.
- Для production используйте HTTPS.
- Создавайте отдельный API-key на каждую интеграцию.
- Удаляйте ключ сразу, если интеграция больше не нужна.
- При подозрении на компрометацию удалите ключ и создайте новый.
- Ограничьте доступ к панели firewall'ом или reverse proxy rules, если интеграция работает с фиксированного IP.

## Типичный сценарий интеграции

1. Биллинг создаёт пользователя или заказ у себя.
2. Биллинг вызывает `POST /api/peers`.
3. 3WG Core создаёт peer в protocol-контейнере.
4. Биллинг получает JSON с id, protocol, IP, ссылками на config/QR.
5. Клиент получает конфиг через портал или Telegram bot.
6. Биллинг периодически проверяет `/api/peers` или `/api/traffic/history`.
7. При окончании подписки биллинг вызывает `/api/peers/{id}/disable`.
