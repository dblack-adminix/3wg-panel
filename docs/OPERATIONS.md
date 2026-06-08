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

## Обновление из Git

Для установок через installer:

```bash
cd /opt/3wg-panel
git fetch --all --tags
git checkout dev
git pull --ff-only
sudo bash scripts/install.sh
```

Installer использует ту же директорию, пересобирает frontend/image, пересоздаёт контейнер и делает health-check.

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

## Release flow

Рекомендуемый порядок релиза:

```bash
git checkout dev
git pull
git tag v1.0.0
git push origin v1.0.0
```

Для production-серверов лучше ставить tag, а не плавающую ветку.
