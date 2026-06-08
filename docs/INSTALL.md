# Установка

Этот документ описывает установку 3WG Panel с GitHub на Linux-сервер.

## 1. Подготовьте сервер

Установите необходимые пакеты:

```bash
sudo apt update
sudo apt install -y git curl python3 nodejs npm docker.io
sudo systemctl enable --now docker
```

Проверьте, что protocol-контейнеры уже существуют:

```bash
docker ps
```

Перед запуском installer желательно знать:

- публичный домен или endpoint host
- логин и пароль панели
- WireGuard container name, interface, UDP port, config path, CIDR
- AmneziaWG container name, interface, UDP port, config path, CIDR

## 2. Запустите installer

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/install.sh -o /tmp/3wg-install.sh
sudo bash /tmp/3wg-install.sh
```

У большинства вопросов есть значения по умолчанию. Если значение подходит, нажмите Enter.

Рекомендуемая папка установки:

```text
/opt/3wg-panel
```

Рекомендуемый bind address при работе за reverse proxy:

```text
127.0.0.1:18080
```

## 3. Что делает installer

Installer выполняет:

1. проверку нужных команд
2. clone или update Git repository
3. опрос настроек установки
4. создание `.env`
5. применение backend API patches
6. сборку React frontend
7. сборку Docker image `3wg-panel:local`
8. пересоздание контейнера `3wg-panel`
9. проверку `/health`
10. вывод URL, логина и пароля

Для последующих обновлений используйте `scripts/update.sh`, чтобы не перезаписывать `.env`.

## 4. Ручная установка

Ручной вариант полезен для отладки:

```bash
git clone --branch dev https://github.com/dblack-adminix/3wg-panel.git /opt/3wg-panel
cd /opt/3wg-panel
cp .env.example .env
nano .env
python3 scripts/apply_api_patch.py
python3 scripts/apply_dashboard_model_patch.py
cd frontend
npm install
npm run build
cd ..
docker build -f app/Dockerfile -t 3wg-panel:local .
docker rm -f 3wg-panel 2>/dev/null || true
docker run -d   --name 3wg-panel   --restart unless-stopped   --env-file /opt/3wg-panel/.env   -p 127.0.0.1:18080:18080   -v /var/run/docker.sock:/var/run/docker.sock   -v /opt/3wg-panel/data:/app/data   -v /opt/3wg-panel/clients:/app/clients   -v /opt/3wg-panel/backups:/app/backups   3wg-panel:local
curl -fsS http://127.0.0.1:18080/health
```

## 5. HTTPS через Caddy

Пример Caddyfile:

```caddy
panel.example.com {
    reverse_proxy 127.0.0.1:18080
}
```

После настройки DNS Caddy сам выпустит HTTPS-сертификат.

## 6. Первый вход

Откройте URL, который напечатал installer, и войдите в панель.

Сразу проверьте:

- `/health` возвращает OK
- карточки протоколов показывают ожидаемое состояние
- создание тестового клиента работает
- QR и download-кнопки работают
