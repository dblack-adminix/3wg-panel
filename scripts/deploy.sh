#!/usr/bin/env bash
set -euo pipefail

BASE="/srv/3wg-panel"
APP="$BASE/app/app.py"

echo "======================================================"
echo " 3WG PANEL DEV DEPLOY"
echo "======================================================"

cd "$BASE"

echo
echo "===== UI cleanup ====="
python3 - <<'PY'
from pathlib import Path
import re

app = Path("/srv/3wg-panel/app/app.py")
text = app.read_text(encoding="utf-8")
new_text = text

# Удаляем бесполезный пункт бокового меню "Клиенты".
# В app.py сейчас есть несколько поколений темы, и пункт может быть как в одну строку,
# так и многострочным HTML-блоком. Поэтому режем именно nav-link, где текст пункта = Клиенты.
patterns = [
    r'\n[ \t]*<a\s+href="/"\s*>\s*\n[ \t]*<span\s+class="ico">.*?</span>\s*\n[ \t]*<span>Клиенты</span>\s*\n[ \t]*</a>',
    r'\n[ \t]*<a\s+href="/"><span\s+class="ico">.*?</span><span>Клиенты</span></a>',
]

removed = 0
for pattern in patterns:
    new_text, count = re.subn(pattern, "", new_text, flags=re.S)
    removed += count

if new_text != text:
    app.write_text(new_text, encoding="utf-8")
    print(f"removed redundant Clients sidebar links: {removed}")
else:
    print("no redundant Clients sidebar links found")
PY

echo
echo "===== React API patch ====="
python3 "$BASE/scripts/apply_api_patch.py"

echo
echo "===== Syntax check ====="
python3 -m py_compile "$APP"
echo "app.py syntax OK"

echo
echo "===== Backup current source ====="
mkdir -p "$BASE/backups/source"

tar -czf "$BASE/backups/source/3wg-panel-app.$(date +%F_%H-%M-%S).tgz" \
  -C "$BASE" app

echo
echo "===== Rebuild Docker image ====="
docker rm -f 3wg-panel 2>/dev/null || true
docker rmi 3wg-panel:local 2>/dev/null || true

docker build -t 3wg-panel:local "$BASE/app"

echo
echo "===== Run 3WG Panel ====="
docker run -d \
  --name 3wg-panel \
  --restart unless-stopped \
  --env-file "$BASE/.env" \
  -p 127.0.0.1:18080:18080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$BASE/data:/app/data" \
  -v "$BASE/clients:/app/clients" \
  -v "$BASE/backups:/app/backups" \
  3wg-panel:local

sleep 4

echo
echo "===== Health check ====="
docker exec 3wg-panel python - <<'PY'
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:18080/health").read().decode())
PY

echo
echo "===== Status ====="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "DONE"
