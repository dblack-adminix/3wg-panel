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

## Обновление

Для обычного production-обновления используйте отдельный updater:

```bash
cd /opt/3wg-panel
sudo bash scripts/update.sh
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
sudo BRANCH=v1.0.0 INSTALL_DIR=/opt/3wg-panel bash scripts/update.sh
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
git tag v1.0.0
git push origin v1.0.0
```

Для production-серверов лучше ставить tag, а не плавающую ветку.
