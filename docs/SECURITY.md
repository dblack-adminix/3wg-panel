# Безопасность

## Как лучше публиковать панель

Рекомендуемый вариант — держать 3WG Panel на localhost и отдавать наружу только через HTTPS reverse proxy:

```text
127.0.0.1:18080 -> Caddy/Nginx -> Internet
```

Не открывайте панель напрямую на `0.0.0.0`, если точно не понимаете последствия.

## Пароли и secrets

- Используйте сильный `PANEL_PASSWORD`.
- Используйте случайный `SESSION_SECRET`.
- Держите `.env` с правами `600`.
- Не коммитьте `.env` в Git.

## Docker socket

Панели нужен `/var/run/docker.sock`, чтобы смотреть protocol-контейнеры и выполнять команды внутри них. Это высокий уровень доступа. Запускайте панель только на доверенных серверах и защищайте вход в web UI.

## Firewall checklist

Открывайте только необходимое:

- TCP 80/443 для reverse proxy
- UDP ports WireGuard/AmneziaWG
- SSH только с доверенных адресов

Не публикуйте наружу SQLite, Docker API и внутренний порт панели.

## HTTPS

Используйте Caddy или Nginx с Let's Encrypt. Пример Caddy:

```caddy
panel.example.com {
    reverse_proxy 127.0.0.1:18080
}
```
