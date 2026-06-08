# 3WG Panel

3WG Panel is a web panel for managing WireGuard and AmneziaWG peers on a node. The backend is FastAPI, the UI is React, and deployment is Docker-based.

## What It Does

- Manages WireGuard and AmneziaWG clients from one panel.
- Generates configs, QR codes, and AmneziaVPN-compatible files.
- Shows peer status, latest handshake, RX/TX counters, and protocol health.
- Includes live interface traffic and detailed traffic history pages.
- Stores panel state in SQLite and keeps generated client files on persistent volumes.
- Ships with an interactive installer for GitHub-based deployments.

## Screens And Routes

- `/` - main dashboard
- `/client/<id>` - client config, QR codes, downloads
- `/status/wireguard` - WireGuard status page
- `/status/amneziawg` - AmneziaWG status page
- `/traffic/wireguard` - WireGuard traffic history
- `/traffic/amneziawg` - AmneziaWG traffic history
- `/health` - health check

## Requirements

On the target server:

- Linux server, Debian/Ubuntu recommended
- Docker
- Git
- Node.js/npm, used to build React during install
- Python 3
- curl
- Existing WireGuard and/or AmneziaWG containers reachable through Docker
- Access to `/var/run/docker.sock` from the panel container

3WG Panel does not install WireGuard or AmneziaWG by itself. It manages existing protocol containers.

## Quick Install

On a new server run:

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/install.sh -o /tmp/3wg-install.sh
sudo bash /tmp/3wg-install.sh
```

The installer asks for:

- Git repository and branch/tag
- install directory, default `/opt/3wg-panel`
- bind host and port, default `127.0.0.1:18080`
- public endpoint host/domain
- panel username/password
- WireGuard container/interface/port/config/network
- AmneziaWG container/interface/port/config/network
- DNS servers
- whether to hide peers not created by the panel

Detailed installation guide: [docs/INSTALL.md](docs/INSTALL.md)

## Configuration

Copy and edit `.env.example` if installing manually. Full variable reference: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## Operations

- Backup, update, logs, health checks: [docs/OPERATIONS.md](docs/OPERATIONS.md)
- Security and reverse proxy notes: [docs/SECURITY.md](docs/SECURITY.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Development Deploy On The Current Node

The existing dev node uses:

```bash
bash /srv/3wg-panel/scripts/deploy.sh
```

That script is intentionally node-specific. For new servers, use `scripts/install.sh`.

## Project Layout

```text
app/                 FastAPI backend and static assets
frontend/            React frontend source
scripts/deploy.sh    dev deploy script for cz-prg-01
scripts/install.sh   interactive production installer
docs/                documentation
.env.example         environment template
```

## Version

Current UI version: `v1.0.0`

## Copyright

Copyright 2026 3WG Panel. Contacts: [@vorchiks](https://t.me/vorchiks), [vitaly@goreev.ru](mailto:vitaly@goreev.ru), [3wg.ru](https://3wg.ru).

WireGuard is a registered trademark of Jason A. Donenfeld.
