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

## Upgrade до v1.1.4

Версия `v1.1.4` добавляет проверку актуальности версии через GitHub tags в интерфейсе панели, переводит apt-установку Node.js/Caddy в non-interactive режим для Debian/Ubuntu и ограничивает Caddy validate/reload/start по времени, чтобы installer не зависал на настройке reverse proxy. Также включает изменения `v1.1.0`: auto-create режим для WireGuard/AmneziaWG runtime-контейнеров, AmneziaWG профиль маскировки, `443/udp` как рекомендуемый порт AmneziaWG для новых auto-create установок и `MTU = 1420` в новых клиентских конфигах.

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

После upgrade проверьте:

```bash
curl -fsS http://127.0.0.1:18080/health
docker ps
```

Если хотите обновляться не с плавающей ветки `dev`, а с фиксированного релиза, используйте tag:

```bash
sudo BRANCH=v1.1.4 INSTALL_DIR=/opt/3wg-panel bash /tmp/3wg-update.sh
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
sudo BRANCH=v1.1.4 INSTALL_DIR=/opt/3wg-panel bash scripts/update.sh
```

Updater делает backup, проверяет локальные изменения, обновляет Git, применяет backend patches, проверяет Python-модули, устанавливает frontend-зависимости через `npm ci`, собирает React, пересобирает Docker image, пересоздаёт контейнер и выполняет health-check.

Если в рабочей копии есть локальные изменения в tracked-файлах, updater остановится и не будет их перетирать. Сгенерированные изменения `app/app.py` он предварительно сохраняет в `backups/update/` и возвращает tracked-версию перед `git pull`.

Если нужно заново пройти вопросы установки и перегенерировать `.env`, используйте `scripts/install.sh`.

## Backup

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

## API-ключи

Страница `/apikeys` позволяет создать ключ для внешних интеграций. Ключ передаётся в API через HTTP header:

```text
X-API-Key: <token>
```

Токен показывается только один раз при создании. В SQLite хранится только hash ключа, prefix/suffix для отображения и время последнего использования.

## Release flow

Рекомендуемый порядок релиза:

```bash
git checkout dev
git pull
git tag v1.1.4
git push origin v1.1.4
```

Для production-серверов лучше ставить tag, а не плавающую ветку.
