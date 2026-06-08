# Security Notes

## Recommended Exposure

Bind 3WG Panel to localhost and expose it through HTTPS reverse proxy:

```text
127.0.0.1:18080 -> Caddy/Nginx -> Internet
```

Avoid binding the panel directly to `0.0.0.0` unless you know exactly what you are doing.

## Passwords And Secrets

- Use a strong `PANEL_PASSWORD`.
- Use a random `SESSION_SECRET`.
- Keep `.env` mode `600`.
- Do not commit `.env`.

## Docker Socket

The panel needs `/var/run/docker.sock` to inspect and execute commands in protocol containers. This is powerful access. Run the panel only on servers you trust and protect the web login.

## Firewall Checklist

Open only what you need:

- TCP 80/443 for reverse proxy
- WireGuard/AmneziaWG UDP ports
- SSH from trusted addresses

Do not expose SQLite, Docker API, or internal panel port publicly.

## HTTPS

Use Caddy or Nginx with Let's Encrypt. Caddy example:

```caddy
panel.example.com {
    reverse_proxy 127.0.0.1:18080
}
```
