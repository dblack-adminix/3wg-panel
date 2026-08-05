# Переезд на другой сервер

Этот сценарий нужен, когда старую VPN-ноду нужно аннулировать, а пользователей перенести на новый сервер так, чтобы им не пришлось пересоздавать конфиги.

## Главный принцип

Клиентский config содержит две критичные вещи:

- `Endpoint = домен:порт`
- `PublicKey` сервера

Чтобы переезд был незаметным для пользователей, на новом сервере должны сохраниться:

- тот же endpoint-домен;
- те же UDP-порты WireGuard/AmneziaWG;
- те же server private keys в protocol config'ах;
- те же peer-секции;
- та же база панели `data/panel.db`;
- директория `clients/`.

После этого достаточно переписать DNS A-запись домена на новый IP. Клиенты продолжат подключаться к тому же домену и тому же server public key.

## Что делает migration bundle

`scripts/migration_export.sh` собирает переносимый архив:

- `.env`;
- `data/`;
- `clients/`;
- server-side config WireGuard из VPN-контейнера;
- server-side config AmneziaWG из VPN-контейнера;
- `metadata.json` с версией, hostname и git commit.

По умолчанию обычные backup-архивы из `backups/` не включаются, чтобы bundle не раздувался. Если нужно перенести и историю backup'ов:

```bash
sudo INCLUDE_BACKUPS=1 bash scripts/migration_export.sh
```

## 1. На старом сервере

```bash
cd /opt/3wg-panel
sudo bash scripts/update.sh
sudo bash scripts/migration_export.sh
```

Скрипт покажет путь к архиву, например:

```text
/opt/3wg-panel/backups/migration/3wg-core.migration.nl-ams-02.nodax.eu.2026-08-05_12-00-00.tgz
```

Скопируйте этот файл на новый сервер любым безопасным способом.

## 2. Подготовьте новый сервер

На новом сервере поставьте 3WG Core из GitHub. Можно ставить на тот же branch/tag, что был на старом сервере, или на более новую версию.

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/install.sh -o /tmp/3wg-install.sh
sudo bash /tmp/3wg-install.sh
```

Если это чистый сервер и protocol-контейнеров ещё нет, в installer можно выбрать auto-create. Import всё равно перезапишет server configs из migration bundle.

Важно:

- endpoint host вводите тот же домен, который был у пользователей;
- UDP-порты лучше оставить теми же;
- если домен ещё указывает на старый сервер, это нормально: сначала проверяем новый сервер локально, потом переключаем DNS.

## 3. На новом сервере

```bash
cd /opt/3wg-panel
sudo bash scripts/migration_import.sh /path/to/3wg-core.migration.<old-host>.<date>.tgz
```

Import:

- создаст pre-import backup текущего состояния;
- восстановит `.env`, `data/`, `clients/`;
- если protocol-контейнеров нет, попробует создать их через `scripts/provision_protocols.sh`;
- запишет старые server configs в новые protocol-контейнеры;
- перезапустит protocol-контейнеры;
- запустит `scripts/update.sh`, чтобы пересобрать и поднять панель.

## 4. Проверка до переключения DNS

На новом сервере:

```bash
curl -fsS http://127.0.0.1:18080/health
docker ps
docker exec amnezia-wireguard wg show
docker exec amnezia-awg2 awg show
```

Проверьте, что:

- панель открывается;
- peer'ы видны;
- WireGuard/AmneziaWG контейнеры running;
- UDP-порты опубликованы наружу;
- `Endpoint host` в панели совпадает со старым доменом.

## 5. Переключение

1. Уменьшите TTL DNS заранее, например до `60` секунд.
2. На старом сервере сделайте финальный export.
3. На новом сервере сделайте import финального archive.
4. Перепишите A-запись домена на IP нового сервера.
5. Подождите обновления DNS.
6. Проверьте подключения клиентов и трафик в панели.

## Важные ограничения

- Если изменится UDP-порт, пользователи со старыми config'ами не подключатся.
- Если потерять server private key, старые клиентские config'и перестанут работать.
- Если endpoint был IP-адресом, а не доменом, незаметного переезда не получится: клиентам нужно будет обновить config.
- Если на старом сервере после export создавались новые peer'ы, нужно сделать новый export/import перед финальным DNS switch.
- DNS propagation не мгновенный. Поэтому лучше заранее поставить маленький TTL.

## Rollback

Если после переключения что-то пошло не так:

1. Верните DNS A-запись на старый IP.
2. На новом сервере используйте pre-import backup из `backups/migration/`.
3. Разберите проблему с protocol config или портами.

Старый сервер лучше не удалять минимум несколько часов после успешного переключения.
