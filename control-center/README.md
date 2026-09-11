# 3WG Control Center

Центральная панель для инвентаризации и управления серверами 3WG Core и 3WG Easy Core. Control Center не поднимает собственный VPN и не вмешивается в работу туннелей при своей недоступности.

## MVP v1

- защищённый вход владельца;
- добавление ноды по HTTPS URL и Node API Key;
- проверка ключа перед сохранением;
- шифрование Node API Key в SQLite;
- общий список Core/Easy Core;
- статусы нод и протоколов;
- версии, endpoint, пиры и ошибки связи;
- ручная синхронизация одной или всех нод.
- единая таблица пиров с поиском и фильтром по серверу;
- создание WireGuard и AmneziaWG пиров на выбранной ноде;
- включение, отключение, сброс трафика и удаление;
- централизованное скачивание `.conf` и `.vpn` без передачи Node API Key браузеру.

Очередь команд, массовые операции и миграция войдут в следующие этапы.

## Подготовка управляемой ноды

1. Откройте в 3WG Core или Easy Core раздел **API-ключи**.
2. Создайте отдельный ключ с названием `Control Center`.
3. Убедитесь, что URL панели доступен по HTTPS с центрального сервера.
4. Добавьте URL и полученный ключ в Control Center.

Пароль администратора удалённой панели не передаётся.

## Установка

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose openssl
sudo systemctl enable --now docker
git clone --branch v1.6.2 --depth 1 https://github.com/dblack-adminix/3wg-panel.git /opt/3wg-control-center
cd /opt/3wg-control-center/control-center
sudo bash install.sh
```

Сервис слушает только `127.0.0.1:18082`. Для публикации добавьте в Caddy:

```caddy
control.example.com {
    reverse_proxy 127.0.0.1:18082
}
```

После этого:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl -fsS https://control.example.com/health
```

## Обновление

```bash
cd /opt/3wg-control-center
sudo git fetch --tags
sudo git checkout v1.6.2
cd control-center
sudo docker compose up -d --build
```

Не удаляйте `control-center/.env` и `control-center/data`: там находятся ключ шифрования и база нод.

## Диагностика

```bash
cd /opt/3wg-control-center/control-center
sudo docker compose ps
sudo docker compose logs --tail 200
curl -fsS http://127.0.0.1:18082/health
```

## Безопасность

- Используйте отдельный API-ключ для каждой ноды.
- Не публикуйте Control Center без HTTPS.
- Ограничьте доступ к домену по IP или через отдельный административный VPN.
- Делайте резервные копии `.env` и каталога `data` вместе: без `NODE_ENCRYPTION_KEY` расшифровать сохранённые ключи нельзя.
- Отзыв ключа на ноде немедленно прекращает доступ Control Center к этой ноде.
