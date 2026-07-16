# Эксплуатация

## Health-check

```bash
curl -fsS http://127.0.0.1:18080/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## Логи

```bash
docker logs -f 3wg-panel
```

## Restart

```bash
docker restart 3wg-panel
```

## Смена пароля администратора

Если вход в панель не работает или пароль потерян, используйте скрипт сброса. Он обновит `PANEL_USER`, `PANEL_PASSWORD`, пересоздаст `SESSION_SECRET`, сохранит backup `.env` и пересоздаст контейнер `3wg-panel`, чтобы Docker перечитал свежий `.env`.

Сгенерировать новый пароль автоматически:

```bash
cd /opt/3wg-panel
sudo bash scripts/reset_admin_password.sh --user admin
```

Задать пароль вручную:

```bash
cd /opt/3wg-panel
sudo bash scripts/reset_admin_password.sh --user admin --password 'new-strong-password'
```

Если на старой установке такого скрипта ещё нет, скачайте свежую версию напрямую:

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/reset_admin_password.sh -o /tmp/3wg-reset-password.sh
sudo INSTALL_DIR=/opt/3wg-panel bash /tmp/3wg-reset-password.sh --user admin
```

После смены пароля старые browser cookies станут недействительными. Откройте страницу входа заново и войдите новым паролем.

## Обновление

Для обычного production-обновления используйте отдельный updater:

```bash
cd /opt/3wg-panel
sudo bash scripts/update.sh
```

Если сервер был установлен раньше и локальный `scripts/update.sh` ещё старый, сначала запустите свежий updater напрямую из GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/update.sh -o /tmp/3wg-update.sh
sudo bash /tmp/3wg-update.sh
```

Этот вариант нужен именно для старых установок: свежий updater сам зайдёт в `/opt/3wg-panel`, сделает backup, обновит исходники и уже после этого в проекте появится новый `scripts/update.sh`.

## Upgrade до v1.2.0

Версия `v1.2.0` добавляет multi-user режим: суперпользователь создаёт пользователей панели, задаёт лимит peer'ов, а обычный пользователь видит урезанный интерфейс и управляет только своими peer'ами в пределах лимита. Также включает изменения ветки `v1.1.x`: проверку версии через GitHub tags, non-interactive apt-установку Node.js/Caddy, timeout для Caddy validate/reload/start и отключение HTTP/3 в Caddy для схемы `443/tcp` web + `443/udp` AmneziaWG.

Для уже установленного сервера используйте свежий updater:

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/update.sh -o /tmp/3wg-update.sh
sudo bash /tmp/3wg-update.sh
```

Что важно:

- updater делает backup перед обновлением;
- `.env` не перезаписывается;
- уже существующие WireGuard/AmneziaWG контейнеры не пересоздаются;
- auto-create режим включается только при новом запуске `scripts/install.sh` с выбором `Protocol containers: 1=auto create`;
- уже созданные клиентские `.conf` файлы не переписываются автоматически;
- новые клиентские `.conf` будут создаваться уже с `MTU = 1420`.
- существующие peer'ы после upgrade остаются административными; новые peer'ы обычных пользователей будут привязаны к их аккаунтам.

После upgrade проверьте:

```bash
curl -fsS http://127.0.0.1:18080/health
docker ps
```

Если хотите обновляться не с плавающей ветки `dev`, а с фиксированного релиза, используйте tag:

```bash
sudo BRANCH=v1.3.0 INSTALL_DIR=/opt/3wg-panel bash /tmp/3wg-update.sh
```

По умолчанию updater использует:

```text
INSTALL_DIR=/opt/3wg-panel
BRANCH=dev
IMAGE=3wg-panel:local
CONTAINER=3wg-panel
BIND_HOST=127.0.0.1
BIND_PORT=18080
```

Можно переопределить значения через переменные окружения:

```bash
sudo BRANCH=v1.3.0 INSTALL_DIR=/opt/3wg-panel bash scripts/update.sh
```

Updater делает backup, проверяет локальные изменения, обновляет Git, применяет backend patches, проверяет Python-модули, устанавливает frontend-зависимости через `npm ci`, собирает React, пересобирает Docker image, пересоздаёт контейнер и выполняет health-check.

Если в рабочей копии есть локальные изменения в tracked-файлах, updater остановится и не будет их перетирать. Сгенерированные изменения `app/app.py` он предварительно сохраняет в `backups/update/` и возвращает tracked-версию перед `git pull`.

Если нужно заново пройти вопросы установки и перегенерировать `.env`, используйте `scripts/install.sh`.

## Update Center из web UI

Страница `/updates` не запускает shell-команды внутри Docker-контейнера панели. Для этого используется отдельный host-side systemd runner:

```bash
cd /opt/3wg-panel
sudo BASE=/opt/3wg-panel bash scripts/install_update_runner.sh
```

Runner слушает Unix socket:

```text
/opt/3wg-panel/run/update-runner.sock
```

Контейнер панели получает этот socket как `/app/run/update-runner.sock`. Поэтому в `.env` достаточно оставить:

```env
UPDATE_RUNNER_ENABLED=1
UPDATE_RUNNER_SOCKET=/app/run/update-runner.sock
```

Проверка:

```bash
systemctl status 3wg-panel-update-runner --no-pager
ls -l /opt/3wg-panel/run/update-runner.sock
docker exec 3wg-panel ls -l /app/run/update-runner.sock
```

Удалить runner:

```bash
cd /opt/3wg-panel
sudo BASE=/opt/3wg-panel bash scripts/uninstall_update_runner.sh
```

## Upgrade до v1.3.0

Версия `v1.3.0` добавляет основу мониторинга под Prometheus/Grafana:

- endpoint `/metrics` в формате Prometheus;
- `scripts/install_monitoring_agent.sh` для `node_exporter` и `cAdvisor`;
- `monitoring/prometheus.example.yml`;
- `monitoring/alert-rules.example.yml`;
- стартовый Grafana dashboard `monitoring/grafana-dashboard-3wg-node.json`;
- документацию [MONITORING.md](MONITORING.md).

После обновления `/metrics` выключен, пока вы явно не включите его в `.env`:

```env
METRICS_ENABLED=1
METRICS_REQUIRE_TOKEN=1
METRICS_TOKEN=<long-random-token>
```

Затем пересоздайте контейнер панели через updater:

```bash
cd /opt/3wg-panel
sudo bash scripts/update.sh
```

Monitoring-agent ставится отдельно:

```bash
cd /opt/3wg-panel
sudo bash scripts/install_monitoring_agent.sh
```

## Backup

### Через web UI

Страница `/backups` позволяет суперпользователю:

- создать ручной backup состояния панели;
- включить auto backup по расписанию;
- задать интервал auto backup и сколько auto-архивов хранить;
- скачать `.tgz` архив;
- удалить старый архив с подтверждением;
- выполнить restore с обязательным подтверждением `RESTORE`.

UI backup сохраняет:

- `data/`
- `clients/`

Перед restore панель автоматически создаёт pre-restore backup в `/app/backups/manual`.

Auto backup создаёт файлы вида `3wg-panel.auto.<date>.tgz` в `/app/backups/manual`. Ротация удаляет только старые auto backup'ы сверх указанного лимита, ручные и pre-restore архивы не трогает.

Важно: `.env` через web UI не архивируется. Это сделано специально, чтобы web-контейнер не читал production secrets. Для полного серверного backup используйте shell-вариант ниже.

### Через shell

Останавливать контейнер обычно не обязательно, но лучше делать backup в момент низкой нагрузки.

```bash
cd /opt/3wg-panel
mkdir -p backups/manual
tar -czf backups/manual/3wg-panel.$(date +%F_%H-%M-%S).tgz data clients backups .env
```

Что важно сохранять:

- `.env`
- `data/panel.db`
- `clients/`
- `backups/`

## Restore

```bash
cd /opt/3wg-panel
docker rm -f 3wg-panel
# распакуйте backup в /opt/3wg-panel
sudo bash scripts/install.sh
```

## История трафика

История трафика хранится в SQLite table `traffic_snapshots`. Она начинает накапливаться только после включения этой функции. Старую месячную статистику восстановить нельзя, если snapshots раньше не собирались.

## Monitoring agent

Для Prometheus/Grafana на VPN-ноде можно поставить `node_exporter` и `cAdvisor`:

```bash
cd /opt/3wg-panel
sudo bash scripts/install_monitoring_agent.sh
```

По умолчанию агент слушает только `127.0.0.1`. Для приватного monitoring-интерфейса:

```bash
sudo MONITORING_BIND_HOST=10.10.0.15 bash scripts/install_monitoring_agent.sh
```

Удаление:

```bash
cd /opt/3wg-panel
sudo bash scripts/uninstall_monitoring_agent.sh
```

Подробно: [MONITORING.md](MONITORING.md)

## API-ключи

Страница `/apikeys` позволяет создать ключ для внешних интеграций. Ключ передаётся в API через HTTP header:

```text
X-API-Key: <token>
```

Токен показывается только один раз при создании. В SQLite хранится только hash ключа, prefix/suffix для отображения и время последнего использования.

Подробная документация по API-ключам, endpoint'ам и примерам интеграции: [API_KEYS.md](API_KEYS.md)

## Release flow

Рекомендуемый порядок релиза:

```bash
git checkout dev
git pull
git tag v1.3.0
git push origin v1.3.0
```

Для production-серверов лучше ставить tag, а не плавающую ветку.
