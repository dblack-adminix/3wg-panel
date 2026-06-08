# Operations

## Health Check

```bash
curl -fsS http://127.0.0.1:18080/health
```

Expected output:

```json
{"status":"ok"}
```

## Logs

```bash
docker logs -f 3wg-panel
```

## Restart

```bash
docker restart 3wg-panel
```

## Update From Git

For installer-based deployments:

```bash
cd /opt/3wg-panel
git fetch --all --tags
git checkout dev
git pull --ff-only
sudo bash scripts/install.sh
```

The installer will keep the same directory, rebuild frontend/image, recreate the container, and perform a health check.

## Backup

Stop is not required for a basic SQLite/file backup, but doing it during low traffic is cleaner.

```bash
cd /opt/3wg-panel
mkdir -p backups/manual
tar -czf backups/manual/3wg-panel.$(date +%F_%H-%M-%S).tgz data clients backups .env
```

Recommended files to back up:

- `.env`
- `data/panel.db`
- `clients/`
- `backups/`

## Restore

```bash
cd /opt/3wg-panel
docker rm -f 3wg-panel
# unpack backup into /opt/3wg-panel
sudo bash scripts/install.sh
```

## Traffic History

Traffic history is stored in SQLite table `traffic_snapshots`. It starts accumulating from the moment the feature is deployed. Old monthly data cannot be reconstructed if snapshots were not collected before.

## Release Flow

Recommended release flow:

```bash
git checkout dev
git pull
git tag v1.0.0
git push origin v1.0.0
```

For production servers, install a tag instead of a moving branch when stability matters.
