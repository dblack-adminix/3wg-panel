# Конфигурация

3WG Core настраивается через `.env`.

## Основные переменные

| Переменная | Пример | Описание |
| --- | --- | --- |
| `PANEL_USER` | `admin` | Логин для входа в панель |
| `PANEL_PASSWORD` | `change-me` | Пароль для входа в панель |
| `PANEL_CONTAINER` | `3wg-panel` | Имя Docker-контейнера панели для self-monitoring метрик |
| `SESSION_SECRET` | random hex | Секрет для подписи session cookie |
| `PANEL_HOST` | `panel.example.com` | Публичный web-хост панели |
| `ENDPOINT_HOST` | `vpn.example.com` | Legacy fallback для старых установок. Если `VPN_ENDPOINT_HOST` не задан, используется как VPN endpoint |
| `VPN_ENDPOINT_HOST` | `vpn.example.com` | Хост/IP, который попадёт в клиентские конфиги и QR |
| `VPN_EGRESS_IP` | `176.98.186.189` | Опциональный сменяемый исходящий IP для схем с policy routing/SNAT. Сейчас хранится как настройка, firewall автоматически не меняется |
| `DNS_SERVERS` | `1.1.1.1, 1.0.0.1` | DNS в генерируемых конфигах |
| `HIDE_EXISTING_PEERS` | `1` | Скрывать peer'ы, созданные не через 3WG Core |

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
- `VPN_ENDPOINT_HOST` должен быть доменом или IP, доступным клиентам из Интернета. Для обычной ноды он может совпадать с `PANEL_HOST`.
- Не открывайте `/metrics`, `node_exporter` и `cAdvisor` в публичный интернет без firewall/private VPN.
- Никогда не коммитьте `.env` в Git.

## Смена VPN IP через отдельный endpoint

На некоторых серверах используется два публичных IP:

- основной IP для панели и обслуживания сервера
- сменяемый IP, на который указывает DNS-запись VPN endpoint

В этом случае задайте:

```env
PANEL_HOST=cz-prg-01.nodax.eu
ENDPOINT_HOST=wg-fxc01.wire3.ru
VPN_ENDPOINT_HOST=wg-fxc01.wire3.ru
VPN_EGRESS_IP=176.98.186.189
```

Клиентские `.conf`, QR и AmneziaVPN payload будут получать endpoint из `VPN_ENDPOINT_HOST`. Если IP меняется, достаточно обновить DNS `A`-запись этого домена и выпускать новые конфиги уже с тем же доменным endpoint.

Важно:

- Docker-порты должны слушать `0.0.0.0:<udp-port>`, тогда контейнеры примут входящие подключения на оба IP.
- DNS TTL для сменяемого endpoint лучше держать низким.
- `VPN_EGRESS_IP` пока не включает SNAT автоматически. Если нужно, чтобы весь исходящий VPN-трафик выходил именно через второй IP, это нужно настраивать отдельными host firewall/routing правилами.
