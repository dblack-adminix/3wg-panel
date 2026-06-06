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

patterns = [
    r'\n[ \t]*<a\s+href="/"\s*>\s*\n[ \t]*<span\s+class="ico">.*?</span>\s*\n[ \t]*<span>Клиенты</span>\s*\n[ \t]*</a>',
    r'\n[ \t]*<a\s+href="/"><span\s+class="ico">.*?</span><span>Клиенты</span></a>',
]

removed = 0
for pattern in patterns:
    new_text, count = re.subn(pattern, "", new_text, flags=re.S)
    removed += count

for start, end in [
    ("# === 3WG REACT UI START ===", "# === 3WG REACT UI END ==="),
    ("# === 3WG SUPPLIED LOGO START ===", "# === 3WG SUPPLIED LOGO END ==="),
    ("# === 3WG SIMPLE LOGO START ===", "# === 3WG SIMPLE LOGO END ==="),
    ("# === 3WG DIRECT PNG LOGO START ===", "# === 3WG DIRECT PNG LOGO END ==="),
    ("# === 3WG ROOT LOGO START ===", "# === 3WG ROOT LOGO END ==="),
    ("# === 3WG STANDARD PNG LOGO START ===", "# === 3WG STANDARD PNG LOGO END ==="),
]:
    new_text = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n?", "", new_text, flags=re.S)

if new_text != text:
    app.write_text(new_text, encoding="utf-8")
    print(f"removed redundant Clients sidebar links: {removed}")
    print("removed generated logo/ui patch blocks if present")
else:
    print("no cleanup changes found")
PY

echo
echo "===== React API patch ====="
python3 "$BASE/scripts/apply_api_patch.py"

echo
echo "===== Dashboard model API patch ====="
python3 "$BASE/scripts/apply_dashboard_model_patch.py"

echo
echo "===== Visible classic UI patch ====="
python3 "$BASE/scripts/apply_visual_ui_patch.py"

echo
echo "===== Standard PNG logo patch ====="
python3 "$BASE/scripts/apply_standard_logo_patch.py"

echo
echo "===== Login radius patch ====="
python3 "$BASE/scripts/apply_login_radius_patch.py"

echo
echo "===== Restore classic Dockerfile ====="
cat > "$BASE/app/Dockerfile" <<'EOF'
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY static /app/static

RUN mkdir -p /app/data /app/clients/wireguard /app/clients/amneziawg /app/backups/wireguard /app/backups/amneziawg /app/static

EXPOSE 18080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18080"]
EOF

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
echo "===== Logo check ====="
python3 - <<'PY'
import hashlib
import urllib.request
for url in ['http://127.0.0.1:18080/logogrin.png', 'http://127.0.0.1:18080/login', 'http://127.0.0.1:18080/']:
    data = urllib.request.urlopen(url, timeout=10).read()
    if url.endswith('.png'):
        print(url, data[:8], hashlib.sha256(data).hexdigest())
    else:
        text = data.decode('utf-8', errors='replace')
        print(url, '/logogrin.png' in text, 'standard-title-logo' in text, 'border-radius:8px' in text)
PY

echo
echo "===== Status ====="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "DONE"
