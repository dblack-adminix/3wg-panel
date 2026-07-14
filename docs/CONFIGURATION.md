# Конфигурация

3WG Panel настраивается через `.env`.

## Основные переменные

| Переменная | Пример | Описание |
| --- | --- | --- |
| `PANEL_USER` | `admin` | Логин для входа в панель |
| `PANEL_PASSWORD` | `change-me` | Пароль для входа в панель |
| `PANEL_CONTAINER` | `3wg-panel` | Имя Docker-контейнера панели для self-monitoring метрик |
| `SESSION_SECRET` | random hex | Секрет для подписи session cookie |
| `ENDPOINT_HOST` | `vpn.example.com` | Хост, который попадёт в клиентские конфиги |
| `DNS_SERVERS` | `1.1.1.1, 1.0.0.1` | DNS в генерируемых конфигах |
| `HIDE_EXISTING_PEERS` | `1` | Скрывать peer'ы, созданные не через 3WG Panel |

## WireGuard

| Переменная | Пример | Описание |
| --- | --- | --- |
| `WG_CONTAINER` | `amnezia-wireguard` | Имя Docker-контейнера |
| `WG_INTERFACE` | `wg0` | Имя интерфейса внутри контейнера |
| `WG_PORT` | `51820` | Публичный UDP-порт |
| `WG_CONFIG_PATH` | `/opt/amnezia/wireguard/wg0.conf` | Путь к конфигу внутри контейнера |
| `WG_NETWORK` | `10.8.1.0/24` | Пул адресов клиентов |

## AmneziaWG

| Переменная | Пример | Описание |
| --- | --- | --- |
| `AWG_CONTAINER` | `amnezia-awg2` | Имя Docker-контейнера |
| `AWG_INTERFACE` | `awg0` | Имя интерфейса внутри контейнера |
| `AWG_PORT` | `42300` | Публичный UDP-порт |
| `AWG_CONFIG_PATH` | `/opt/amnezia/awg/awg0.conf` | Путь к конфигу внутри контейнера |
| `AWG_NETWORK` | `10.8.1.0/24` | Пул адресов клиентов |

## Пути данных

Внутри контейнера:

```text
/app/data      SQLite database
/app/clients   сгенерированные клиентские конфиги
/app/backups   backup'ы и удалённые конфиги
```

На хосте эти директории обычно находятся здесь:

```text
/opt/3wg-panel/data
/opt/3wg-panel/clients
/opt/3wg-panel/backups
```

## Prometheus metrics

| Переменная | Пример | Описание |
| --- | --- | --- |
| `METRICS_ENABLED` | `1` | Включить endpoint `/metrics` для Prometheus |
| `METRICS_REQUIRE_TOKEN` | `1` | Требовать токен для `/metrics` |
| `METRICS_TOKEN` | long random token | Bearer token для Prometheus |

Проверка:

```bash
curl -fsS \
  -H 'Authorization: Bearer <METRICS_TOKEN>' \
  http://127.0.0.1:18080/metrics | head
```

Подробно: [MONITORING.md](MONITORING.md)

## Примечания

- Если WireGuard и AmneziaWG используют один CIDR, убедитесь, что это действительно соответствует вашей сетевой схеме.
- `ENDPOINT_HOST` должен быть доменом или IP, доступным клиентам из Интернета.
- Не открывайте `/metrics`, `node_exporter` и `cAdvisor` в публичный интернет без firewall/private VPN.
- Никогда не коммитьте `.env` в Git.
