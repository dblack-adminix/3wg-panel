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
python3 - <<'PY'
from pathlib import Path
import re

app_path = Path('/srv/3wg-panel/app/app.py')
text = app_path.read_text(encoding='utf-8')
START = '# === 3WG STANDARD PNG LOGO START ==='
END = '# === 3WG STANDARD PNG LOGO END ==='

text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S)

block = r'''
# === 3WG STANDARD PNG LOGO START ===
@app.get('/logogrin.png')
def logogrin_png():
    logo_path = APP_DIR / 'static' / 'logogrin.png'
    if not logo_path.exists():
        raise HTTPException(status_code=404, detail='Logo not found')
    return FileResponse(
        logo_path,
        media_type='image/png',
        headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'},
    )


def standard_logo_img(width: str, height: str) -> str:
    return (
        '<img src="/logogrin.png" alt="3WG" '
        'style="display:block!important;'
        f'width:{width}!important;height:{height}!important;'
        'max-width:none!important;max-height:none!important;'
        'object-fit:contain!important;opacity:1!important;visibility:visible!important;'
        'background:transparent!important">'
    )


try:
    _login_html_before_standard_logo = login_html

    def login_html(*args, **kwargs) -> str:
        doc = _login_html_before_standard_logo(*args, **kwargs)
        login_logo = (
            '<div id="standard-login-logo" class="logo" style="height:62px;margin:0 0 10px 0;'
            'display:flex!important;align-items:center!important;justify-content:flex-start!important;'
            'background:transparent!important;overflow:visible!important">'
            + standard_logo_img('195px', '50px') +
            '</div>'
        )
        new_doc = re.sub(r'<div class="logo"[^>]*>.*?</div>', login_logo, doc, count=1, flags=re.S)
        if new_doc == doc and 'standard-login-logo' not in doc:
            new_doc = doc.replace(
                '<div class="badge">SECURE NODE PANEL</div>',
                '<div class="badge">SECURE NODE PANEL</div>' + login_logo,
                1,
            )
        return new_doc
except NameError:
    pass


try:
    _page_before_standard_logo = page

    def page(title: str, body: str) -> str:
        doc = _page_before_standard_logo(title, body)
        sidebar_logo = (
            '<div class="neo-brand" id="standard-sidebar-logo" '
            'style="display:flex!important;align-items:center!important;justify-content:flex-start!important;'
            'min-height:58px!important;padding:0 0 18px!important;margin:0 0 18px!important;'
            'border-bottom:1px dashed rgba(64,82,106,.55)!important;'
            'background:transparent!important;overflow:visible!important">'
            + standard_logo_img('178px', '46px') +
            '</div>'
        )
        doc = re.sub(
            r'<div class="neo-brand"[^>]*id="[^"]*sidebar-logo[^"]*"[^>]*>.*?</div>',
            sidebar_logo,
            doc,
            count=1,
            flags=re.S,
        )
        doc = re.sub(
            r'<div class="neo-brand">\s*<div class="neo-logo">3</div>\s*<div>\s*<div class="neo-brand-title">3WG</div>\s*<div class="neo-brand-sub">NODE PANEL</div>\s*</div>\s*</div>',
            sidebar_logo,
            doc,
            count=1,
            flags=re.S,
        )
        # Маленький логотип рядом с заголовком 3WG Panel убираем полностью.
        doc = re.sub(
            r'<div class="neo-title-icon"[^>]*>.*?</div>\s*',
            '',
            doc,
            count=1,
            flags=re.S,
        )
        return doc
except NameError:
    pass
# === 3WG STANDARD PNG LOGO END ===
'''.strip() + '\n'

app_path.write_text(text.rstrip() + '\n\n' + block, encoding='utf-8')
print('standard PNG logo route patched; small header logo removed')
PY

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
import urllib.request
for url in ['http://127.0.0.1:18080/logogrin.png', 'http://127.0.0.1:18080/login', 'http://127.0.0.1:18080/']:
    data = urllib.request.urlopen(url, timeout=10).read()
    if url.endswith('.png'):
        print(url, data[:8])
    else:
        text = data.decode('utf-8', errors='replace')
        print(url, '/logogrin.png' in text, 'standard-title-logo' in text)
PY

echo
echo "===== Status ====="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "DONE"
