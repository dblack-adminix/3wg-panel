# Troubleshooting

## Health Check Fails

```bash
docker ps
docker logs --tail 100 3wg-panel
curl -v http://127.0.0.1:18080/health
```

Common causes:

- container is not running
- bad `.env`
- port already used
- Docker socket not mounted

## Protocol Shows Offline Or Unavailable

Check container names and interfaces:

```bash
docker ps
docker exec <container> wg show
```

For AmneziaWG, the tool name inside the container must match what the backend expects.

## QR Or Download Is Wrong

Check:

- `ENDPOINT_HOST`
- protocol UDP port
- generated client file in `clients/`
- protocol config path inside the container

## Installer Cannot Pull Git

Use HTTPS repo URL if SSH keys are not configured:

```text
https://github.com/dblack-adminix/3wg-panel.git
```

For private repositories, configure deploy keys or GitHub token access first.

## Frontend Build Fails

Check Node/npm:

```bash
node -v
npm -v
cd frontend
npm install
npm run build
```

## Database Problems

SQLite database lives at:

```text
data/panel.db
```

Back it up before manual edits.
