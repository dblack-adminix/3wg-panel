# Установка

Этот документ описывает установку 3WG Panel с GitHub на Linux-сервер. Installer поддерживает два режима: подключиться к уже установленным WireGuard/AmneziaWG контейнерам или создать protocol-контейнеры автоматически.

## 1. Подготовьте сервер

Установите необходимые пакеты:

```bash
sudo apt update
sudo apt install -y git curl python3 nodejs npm docker.io
sudo systemctl enable --now docker
```

Для frontend-сборки нужен Node.js `>=20.19.0` или `>=22.12.0`. Если на Debian/Ubuntu найден старый Node.js, installer автоматически подключит NodeSource и установит Node.js 22.x.

Если protocol-контейнеры уже существуют, проверьте их имена:

```bash
docker ps
```

Перед запуском installer желательно знать:

- публичный домен или endpoint host
- логин и пароль панели
- хотите ли вы создать WireGuard/AmneziaWG контейнеры автоматически или подключиться к уже установленным
- если контейнеры уже установлены: их имена из `docker ps`
- если контейнеры создаёт installer: UDP-порты и сети, которые хотите использовать

## 2. Запустите installer

Если репозиторий публичный, скачайте installer напрямую:

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/install.sh -o /tmp/3wg-install.sh
sudo bash /tmp/3wg-install.sh
```

Installer спросит Git repository и branch. Значения по умолчанию:

```text
Git repository: https://github.com/dblack-adminix/3wg-panel.git
Git branch/tag: dev
```

Что здесь выбирать:

- `Git repository` — адрес репозитория, откуда installer будет брать код панели. Для обычной установки оставьте значение по умолчанию и просто нажмите Enter.
- Используйте HTTPS-адрес `https://github.com/dblack-adminix/3wg-panel.git`, если репозиторий публичный. Это проще для серверов без SSH-ключей GitHub.
- SSH-адрес вида `git@github.com:...` используйте только если на сервере уже настроен deploy key или ваш GitHub SSH-key.
- `Git branch/tag` — ветка или tag, который нужно установить. Сейчас рабочая ветка проекта — `dev`, поэтому для актуальной версии оставьте `dev` и нажмите Enter.
- Когда появится стабильный релиз, вместо `dev` можно будет указать tag, например `v1.0.0`, чтобы сервер не подтягивал текущие dev-изменения.
- Если вы форкнули проект, укажите свой `Git repository`, а branch/tag выберите тот, из которого хотите ставить панель.

Пример обычной установки: на оба вопроса нажмите Enter.

```text
3WG Panel installer
Git repository [https://github.com/dblack-adminix/3wg-panel.git]:
Git branch/tag [dev]:
```

## 3. Поля installer: что вводить

Если в квадратных скобках уже стоит подходящее значение, просто нажимайте Enter. Вводить нужно только то, что отличается на вашем сервере.

| Поле | Что вводить | Пример | Когда оставить Enter |
| --- | --- | --- | --- |
| `Git repository` | HTTPS или SSH адрес Git-репозитория с кодом панели. | `https://github.com/dblack-adminix/3wg-panel.git` | Для обычной установки из основного публичного репозитория. |
| `Git branch/tag` | Ветка или tag, который нужно установить. | `dev` | Сейчас основная рабочая ветка — `dev`, её и оставляем. |
| `Install directory` | Папка на сервере, куда будет установлен проект. | `/opt/3wg-panel` | Почти всегда оставляем `/opt/3wg-panel`. |
| `Docker image name` | Имя Docker image, который соберёт installer. | `3wg-panel:local` | Если на сервере одна панель. |
| `Docker container name` | Имя контейнера панели. | `3wg-panel` | Если на сервере одна панель. |
| `Bind host` | На каком IP слушать HTTP-панель. | `127.0.0.1` | Если панель будет открываться через Caddy/Nginx и HTTPS. |
| `Bind port` | Локальный TCP-порт панели. | `18080` | Если порт свободен. |
| `Public endpoint host / domain` | Публичный домен или hostname сервера. Он попадёт в клиентские конфиги как endpoint. | `nl-ams-02.nodax.eu` | Только если предложенное имя уже правильное. |
| `Configure Caddy reverse proxy for this domain? 1=yes, 0=no` | Настраивать ли HTTPS через Caddy автоматически. | `1` | Ставьте `1`, если домен уже указывает на сервер и хотите открыть панель по HTTPS. |
| `Panel admin username` | Логин администратора панели. | `admin` | Если устраивает логин `admin`. |
| `Panel admin password, empty = auto-generate` | Пароль администратора. Можно оставить пустым, installer сгенерирует сам. | `MyStrongPassword` | Для авто-пароля нажмите Enter. Installer покажет пароль в конце. |
| `Protocol containers: 1=auto create, 0=already installed` | Выбор режима protocol-контейнеров. `0` — контейнеры уже созданы, `1` — installer создаст WireGuard и AmneziaWG сам. | `1` | Если контейнеры уже поставлены через AmneziaVPN app, оставьте `0`. |
| `WireGuard container name` | Имя Docker-контейнера WireGuard. В auto-create режиме контейнер будет создан с этим именем. | `wireguard-wg` | В auto-create режиме оставьте `wireguard-wg`; в existing режиме введите имя из `docker ps`. |
| `WireGuard UDP port` | Только для auto-create режима. UDP-порт WireGuard наружу. | `51820` | Если порт свободен и подходит. |
| `WireGuard network CIDR` | Только для auto-create режима. Сеть WireGuard клиентов. Сервер получит первый IP, клиенты начнутся со второго. | `10.49.0.0/24` | Если сеть не конфликтует с другими VPN/локальными сетями. |
| `AmneziaWG container name` | Имя Docker-контейнера AmneziaWG. В auto-create режиме контейнер будет создан с этим именем. | `amnezia-awg2` | Обычно оставляем `amnezia-awg2`. |
| `AmneziaWG UDP port` | Только для auto-create режима. UDP-порт AmneziaWG наружу. | `443` | Рекомендуется `443/udp`: нестандартные порты чаще обнаруживаются DPI. |
| `AmneziaWG network CIDR` | Только для auto-create режима. Сеть AmneziaWG клиентов. Сервер получит первый IP, клиенты начнутся со второго. | `10.50.0.0/24` | Если сеть не конфликтует с другими VPN/локальными сетями. |
| `Client DNS servers` | DNS, которые будут прописываться в клиентские конфиги. | `1.1.1.1, 1.0.0.1` | Если Cloudflare DNS подходит. |
| `Hide peers not created by panel? 1=yes, 0=no` | Скрывать ли peer’ы, которые были созданы не через 3WG Panel. | `1` | Для чистой таблицы оставьте `1`. Поставьте `0`, если хотите видеть все peer’ы из контейнеров. |

В existing режиме после ввода имён контейнеров installer автоматически проверит:

- published UDP port через Docker
- путь к `.conf` внутри контейнера
- имя interface из имени `.conf`, например `wg0.conf` -> `wg0`
- network CIDR из строки `Address` в `[Interface]`

Если какое-то значение не удалось определить, installer спросит только это конкретное поле и подставит безопасный default.

В auto-create режиме installer:

- соберёт runtime image для WireGuard из `runtimes/wireguard`
- соберёт runtime image для AmneziaWG из `runtimes/amneziawg`
- создаст серверные ключи
- создаст `wg0.conf` и `awg0.conf`
- включит host sysctl для forwarding
- пересоздаст protocol-контейнеры
- затем сам прочитает их реальные настройки и запишет их в `.env`

AmneziaWG в auto-create режиме создаётся с маскировкой:

```ini
Jc = 120
Jmin = 50
Jmax = 1000
S1 = 86
S2 = 14
H1 = 1
H2 = 2
H3 = 3
H4 = 4
I1 = 0
I2 = 0
I3 = 0
I4 = 0
I5 = 0
```

Самое важное при установке на новой ноде:

- `Public endpoint host / domain` должен быть доменом или IP именно этой ноды.
- `container name` должен совпадать с именем контейнера из `docker ps`, иначе панель не сможет управлять peer’ами.
- Убедитесь, что в `docker ps` у protocol-контейнеров опубликованы UDP-порты. Эти порты попадут в клиентские конфиги.

Альтернативно можно сначала клонировать репозиторий:

```bash
git clone --branch dev https://github.com/dblack-adminix/3wg-panel.git /opt/3wg-panel
cd /opt/3wg-panel
sudo bash scripts/install.sh
```

Если указан публичный домен и bind host оставлен `127.0.0.1`, installer предложит настроить Caddy:

```text
Configure Caddy reverse proxy for this domain? 1=yes, 0=no [1]:
```

При выборе `1` installer установит Caddy через `apt-get`, добавит managed-блок в `/etc/caddy/Caddyfile` и направит домен на локальную панель `127.0.0.1:18080`.

Перед этим проверьте, что:

- DNS `A`-запись домена указывает на публичный IP сервера
- порты `80/tcp` и `443/tcp` открыты в firewall/provider security group
- домен уже резолвится снаружи

## 4. Что делает installer

Installer выполняет:

1. проверку нужных команд
2. clone или update Git repository
3. опрос настроек установки
4. при выборе auto-create — создание WireGuard/AmneziaWG runtime containers
5. autodetect protocol-настроек
6. создание `.env`
7. применение backend API patches
8. установку frontend-зависимостей через `npm ci` при наличии `package-lock.json`
9. сборку React frontend
10. сборку Docker image `3wg-panel:local`
11. пересоздание контейнера `3wg-panel`
12. проверку `/health`
13. опциональную настройку Caddy reverse proxy
14. вывод URL, логина и пароля

Для последующих обновлений используйте `scripts/update.sh`, чтобы не перезаписывать `.env`.

## 5. Ручная установка

Ручной вариант полезен для отладки:

```bash
git clone --branch dev https://github.com/dblack-adminix/3wg-panel.git /opt/3wg-panel
cd /opt/3wg-panel
cp .env.example .env
nano .env
python3 scripts/apply_api_patch.py
python3 scripts/apply_dashboard_model_patch.py
cd frontend
npm ci
npm run build
cd ..
docker build -f app/Dockerfile -t 3wg-panel:local .
docker rm -f 3wg-panel 2>/dev/null || true
docker run -d   --name 3wg-panel   --restart unless-stopped   --env-file /opt/3wg-panel/.env   -p 127.0.0.1:18080:18080   -v /var/run/docker.sock:/var/run/docker.sock   -v /opt/3wg-panel/data:/app/data   -v /opt/3wg-panel/clients:/app/clients   -v /opt/3wg-panel/backups:/app/backups   3wg-panel:local
curl -fsS http://127.0.0.1:18080/health
```

## 6. HTTPS через Caddy

Если Caddy не включали в installer, его можно настроить вручную. Пример Caddyfile:

```caddy
panel.example.com {
    reverse_proxy 127.0.0.1:18080
}
```

После настройки DNS Caddy сам выпустит HTTPS-сертификат.

Важно: `ping` не является проверкой доступности панели. ICMP может быть закрыт. Проверяйте именно HTTP/HTTPS:

```bash
curl -I http://panel.example.com/
curl -I https://panel.example.com/
```

## 7. Первый вход

Откройте URL, который напечатал installer, и войдите в панель.

Сразу проверьте:

- `/health` возвращает OK
- карточки протоколов показывают ожидаемое состояние
- создание тестового клиента работает
- QR и download-кнопки работают
