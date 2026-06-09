# Решение проблем

## Health-check не проходит

```bash
docker ps
docker logs --tail 100 3wg-panel
curl -v http://127.0.0.1:18080/health
```

Частые причины:

- контейнер не запущен
- ошибка в `.env`
- порт уже занят
- Docker socket не примонтирован

## Protocol показывает Offline или Unavailable

Проверьте имена контейнеров и интерфейсы:

```bash
docker ps
docker exec <container> wg show
```

Для AmneziaWG tool внутри контейнера должен соответствовать тому, что ожидает backend.

## QR или download неверный

Проверьте:

- `ENDPOINT_HOST`
- UDP port протокола
- сгенерированный файл клиента в `clients/`
- путь к protocol config внутри контейнера

## Installer или curl не может скачать Git

Если команда вида `curl https://raw.githubusercontent.com/.../scripts/install.sh` возвращает `404`, скорее всего репозиторий приватный. Для приватного GitHub это нормальное поведение.

Используйте clone через SSH после настройки deploy key:

```bash
git clone --branch dev git@github.com:dblack-adminix/3wg-panel.git /opt/3wg-panel
cd /opt/3wg-panel
sudo bash scripts/install.sh
```

Если SSH-ключи не настроены, можно использовать HTTPS clone только для публичного репозитория:

```text
https://github.com/dblack-adminix/3wg-panel.git
```

Для private repositories заранее настройте deploy key, GitHub token или сделайте репозиторий публичным.

## Frontend build падает

Проверьте Node/npm:

```bash
node -v
npm -v
cd frontend
npm install
npm run build
```

## Проблемы с базой

SQLite database находится здесь:

```text
data/panel.db
```

Перед ручными изменениями обязательно сделайте backup.
