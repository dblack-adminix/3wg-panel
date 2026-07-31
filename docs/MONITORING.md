# Мониторинг 3WG Core под Grafana

Рекомендуемая схема: Grafana и Prometheus стоят на отдельном центральном сервере, а каждая VPN-нода только отдаёт метрики.

```text
VPN-нода:
  3wg-panel /metrics
  node_exporter :9100
  cAdvisor :8080

Monitoring-сервер:
  Prometheus
  Grafana
  Alertmanager
```

## Что мониторится

3WG Core отдаёт Prometheus endpoint `/metrics`:

- версия панели и endpoint host;
- количество клиентов, включённых/отключённых peer'ов;
- пользователи и категории панели;
- доступность WireGuard/AmneziaWG;
- статус protocol-контейнеров;
- live peer count, online peer count;
- RX/TX bytes по протоколам;
- UDP listen port;
- ошибки сбора статуса.

`node_exporter` отдаёт метрики VPS:

- CPU;
- RAM/swap;
- disk/filesystem;
- network interfaces;
- uptime/system metrics.

`cAdvisor` отдаёт метрики Docker:

- CPU/RAM контейнеров;
- container restart/status;
- network/disk I/O контейнеров.

## Включение `/metrics` в 3WG Core через веб-интерфейс

Откройте панель под администратором:

```text
/monitoring
```

На странице можно:

- включить или выключить `/metrics`;
- создать Prometheus token;
- перевыпустить token;
- скопировать token сразу после генерации.

Plaintext token показывается только один раз. В SQLite хранится только hash.

После генерации используйте token в `prometheus.yml` как Bearer token.

## Включение `/metrics` через `.env`

В `.env` на VPN-ноде добавьте:

```env
METRICS_ENABLED=1
METRICS_REQUIRE_TOKEN=1
METRICS_TOKEN=замените-на-длинный-random-token
```

После изменения `.env` пересоздайте контейнер панели:

```bash
cd /opt/3wg-panel
sudo bash scripts/update.sh
```

Или, если это dev-нода:

```bash
sudo bash /srv/3wg-panel/scripts/deploy.sh
```

Проверка локально:

```bash
curl -fsS \
  -H 'Authorization: Bearer замените-на-длинный-random-token' \
  http://127.0.0.1:18080/metrics | head
```

Если `METRICS_ENABLED=0`, endpoint вернёт `404`.
Если токен не передан или неверный, endpoint вернёт `401`.

## Установка monitoring-agent на VPN-ноду

Агент ставит два Docker-контейнера:

- `3wg-node-exporter`;
- `3wg-cadvisor`.

По умолчанию они слушают только `127.0.0.1`, чтобы не открыть метрики наружу случайно.

```bash
cd /opt/3wg-panel
sudo bash scripts/install_monitoring_agent.sh
```

Если Prometheus будет ходить по приватному IP/VPN-интерфейсу:

```bash
cd /opt/3wg-panel
sudo MONITORING_BIND_HOST=10.10.0.15 bash scripts/install_monitoring_agent.sh
```

Если временно нужно слушать на всех интерфейсах:

```bash
sudo MONITORING_BIND_HOST=0.0.0.0 bash scripts/install_monitoring_agent.sh
```

В этом случае обязательно ограничьте доступ firewall'ом только с IP monitoring-сервера.

Удаление агента:

```bash
cd /opt/3wg-panel
sudo bash scripts/uninstall_monitoring_agent.sh
```

## Prometheus на центральном сервере

В репозитории есть пример:

```text
monitoring/prometheus.example.yml
monitoring/alert-rules.example.yml
```

Минимальный scrape для одной ноды:

```yaml
scrape_configs:
  - job_name: 3wg-panel
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials: CHANGE_ME_METRICS_TOKEN
    static_configs:
      - targets:
          - cz-prg-01.nodax.eu:18080
        labels:
          node: cz-prg-01
          role: vpn-node

  - job_name: node-exporter
    static_configs:
      - targets:
          - cz-prg-01.nodax.eu:9100
        labels:
          node: cz-prg-01

  - job_name: cadvisor
    static_configs:
      - targets:
          - cz-prg-01.nodax.eu:8080
        labels:
          node: cz-prg-01
```

Лучше использовать не публичный IP, а приватную сеть между monitoring-сервером и VPN-нодами.

## Grafana

В репозитории есть стартовый dashboard:

```text
monitoring/grafana-dashboard-3wg-node.json
```

Импорт:

1. Grafana → Dashboards → New → Import.
2. Загрузите JSON.
3. Выберите Prometheus datasource.
4. В переменной `node` выберите нужную VPN-ноду.

Dashboard показывает:

- доступность 3WG Core;
- количество клиентов;
- online peer'ы;
- CPU/RAM VPS;
- RX/TX по WireGuard/AmneziaWG;
- статус важных Docker-контейнеров.

## Безопасность

Не открывайте `/metrics`, `:9100` и `:8080` в публичный интернет без ограничений.

Рекомендуемые варианты:

- приватная WireGuard-сеть между monitoring-сервером и VPN-нодами;
- firewall allowlist только на IP monitoring-сервера;
- reverse proxy с auth для `/metrics`;
- отдельный management interface.

Минимум для публичного сервера:

```text
METRICS_REQUIRE_TOKEN=1
METRICS_TOKEN=<long-random-token>
firewall: allow only monitoring-server-ip to 18080/9100/8080
```

## Основные метрики 3WG

```text
threewg_panel_build_info
threewg_panel_clients_total
threewg_panel_clients_enabled
threewg_panel_clients_disabled
threewg_panel_users_total
threewg_panel_protocol_available
threewg_panel_protocol_container_running
threewg_panel_protocol_peers_total
threewg_panel_protocol_peers_online
threewg_panel_protocol_rx_bytes
threewg_panel_protocol_tx_bytes
threewg_panel_protocol_listen_port
threewg_panel_protocol_error
threewg_panel_docker_container_running
```
