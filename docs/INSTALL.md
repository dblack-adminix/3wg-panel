# Installation Guide

This guide describes installing 3WG Panel from GitHub onto a Linux server.

## 1. Prepare The Server

Install the required packages:

```bash
sudo apt update
sudo apt install -y git curl python3 nodejs npm docker.io
sudo systemctl enable --now docker
```

Make sure the protocol containers already exist:

```bash
docker ps
```

You should know these values before running the installer:

- public domain or endpoint host
- panel admin login and password
- WireGuard container name, interface, UDP port, config path, CIDR
- AmneziaWG container name, interface, UDP port, config path, CIDR

## 2. Run The Installer

```bash
curl -fsSL https://raw.githubusercontent.com/dblack-adminix/3wg-panel/dev/scripts/install.sh -o /tmp/3wg-install.sh
sudo bash /tmp/3wg-install.sh
```

Default values are safe for a typical local install. Press Enter to accept a default.

Recommended install directory:

```text
/opt/3wg-panel
```

Recommended bind address behind a reverse proxy:

```text
127.0.0.1:18080
```

## 3. What The Installer Does

The installer:

1. checks required commands
2. clones or updates the Git repository
3. asks for deployment settings
4. creates `.env`
5. applies backend API patches
6. builds the React frontend
7. builds Docker image `3wg-panel:local`
8. recreates container `3wg-panel`
9. checks `/health`
10. prints the panel URL and credentials

## 4. Manual Install

Manual install is useful for debugging:

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

## 5. HTTPS With Caddy

Example Caddyfile:

```caddy
panel.example.com {
    reverse_proxy 127.0.0.1:18080
}
```

After DNS points to the server, Caddy will issue HTTPS automatically.

## 6. First Login

Open the URL printed by the installer and log in using the generated or provided credentials.

Immediately verify:

- `/health` is OK
- both protocol status cards show expected state
- creating a test client works
- QR and download buttons work
