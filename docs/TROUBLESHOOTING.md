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

- `VPN_ENDPOINT_HOST`
- legacy `ENDPOINT_HOST`, если `VPN_ENDPOINT_HOST` не задан
- UDP port протокола
- сгенерированный файл клиента в `clients/`
- путь к protocol config внутри контейнера

Если панель открывается по одному домену, а VPN-клиенты должны подключаться через второй сменяемый IP, настройте:

```env
PANEL_HOST=panel.example.com
VPN_ENDPOINT_HOST=wg-fxc01.wire3.ru
ENDPOINT_HOST=wg-fxc01.wire3.ru
```

После смены второго IP обновите DNS `A`-запись `VPN_ENDPOINT_HOST`.

## Installer или Git не может скачать репозиторий

Если `curl https://raw.githubusercontent.com/.../scripts/install.sh` возвращает `404`, проверьте:

- репозиторий действительно публичный;
- branch `dev` существует;
- файл `scripts/install.sh` есть в этой ветке;
- URL написан без опечаток.

Для публичного репозитория рабочая команда такая:

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/install.sh -o /tmp/3wg-install.sh
sudo bash /tmp/3wg-install.sh
```

Если репозиторий всё-таки приватный, используйте SSH deploy key или GitHub token. Ошибка вида:

```text
Permission denied (publickey).
fatal: Could not read from remote repository.
```

означает, что серверу не разрешён доступ к приватному GitHub repository.

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
