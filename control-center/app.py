import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Cookie, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response


BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("CONTROL_DB", "/app/data/control.db"))
USER = os.getenv("CONTROL_USER", "admin")
PASSWORD = os.getenv("CONTROL_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
FERNET_KEY = os.getenv("NODE_ENCRYPTION_KEY", "")
COOKIE_SECURE = os.getenv("SESSION_HTTPS_ONLY", "1") == "1"
COOKIE = "threewg_control_session"
CONTROL_VERSION = (BASE / "VERSION").read_text(encoding="utf-8").strip() if (BASE / "VERSION").exists() else "v0.0.0"

if not PASSWORD or not SESSION_SECRET or not FERNET_KEY:
    raise RuntimeError("CONTROL_PASSWORD, SESSION_SECRET and NODE_ENCRYPTION_KEY are required")

fernet = Fernet(FERNET_KEY.encode())
app = FastAPI(title="3WG Control Center", docs_url=None, redoc_url=None)


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        conn.execute('''CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1, session_version INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS tenant_nodes (
            node_id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL)''')
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                api_key_enc TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                last_sync_at INTEGER,
                last_ok_at INTEGER,
                last_error TEXT NOT NULL DEFAULT '',
                snapshot TEXT NOT NULL DEFAULT '{}'
            )
        """)


init_db()


def control_password_hash():
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='admin_password_hash'").fetchone()
    return row['value'] if row else ''


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 200_000).hex()
    return salt + '$' + digest


def valid_password(password, stored=None):
    stored = control_password_hash() if stored is None else stored
    if not stored:
        return secrets.compare_digest(password.encode(), PASSWORD.encode())
    try:
        salt, _ = stored.split('$', 1)
        return secrets.compare_digest(hash_password(password, salt), stored)
    except ValueError:
        return False


def sign_session(expires):
    body = f"{USER}:{expires}"
    sig = hmac.new((SESSION_SECRET + control_password_hash()).encode(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{body}:{sig}".encode()).decode()


def authenticated(token):
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        username, expires, signature = raw.split(":", 2)
        body = f"{username}:{expires}"
        expected = hmac.new((SESSION_SECRET + control_password_hash()).encode(), body.encode(), hashlib.sha256).hexdigest()
        return username == USER and int(expires) > int(time.time()) and hmac.compare_digest(signature, expected)
    except Exception:
        return False


def require_auth(token):
    if not token or not authenticated(token):
        raise HTTPException(401, "Unauthorized")


def tenant_session(row, expires):
    body = f"tenant:{row['id']}:{row['session_version']}:{expires}"
    signature = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f'{body}:{signature}'.encode()).decode()


def session_tenant(token):
    try:
        raw = base64.urlsafe_b64decode((token or '').encode()).decode()
        role, tenant_id, version, expires, signature = raw.split(':')
        body = ':'.join((role, tenant_id, version, expires))
        expected = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        if role != 'tenant' or int(expires) <= int(time.time()) or not hmac.compare_digest(signature, expected):
            return None
        with db() as conn:
            row = conn.execute('SELECT * FROM tenants WHERE id=? AND enabled=1', (int(tenant_id),)).fetchone()
        return row if row and row['session_version'] == int(version) else None
    except (ValueError, UnicodeError, TypeError):
        return None


def require_node_access(token, node_id):
    if authenticated(token or ''):
        return
    tenant = session_tenant(token)
    if not tenant:
        raise HTTPException(401, 'Unauthorized')
    with db() as conn:
        assigned = conn.execute('SELECT 1 FROM tenant_nodes WHERE tenant_id=? AND node_id=?', (tenant['id'], node_id)).fetchone()
    if not assigned:
        raise HTTPException(404, 'Нода не найдена')


def clean_url(value):
    url = str(value or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(400, "Укажите публичный HTTPS URL ноды")
    return url


def version_tuple(value):
    parts = str(value or "").lstrip("v").split(".")
    try:
        return tuple(int(part) for part in parts[:3]) if len(parts) >= 3 else (0, 0, 0)
    except ValueError:
        return (0, 0, 0)


def node_request(url, key, path, timeout=12, method="GET", payload=None, raw=False):
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url + path, data=body, method=method, headers={"X-API-Key": key, "Accept": "*/*" if raw else "application/json", "Content-Type": "application/json", "User-Agent": "3WG-Control-Center/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            return (content, response.headers.get("Content-Type", "application/octet-stream"), response.headers.get("Content-Disposition")) if raw else json.loads(content.decode())
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            error = json.loads(exc.read(4096).decode())
            value = error.get('error') or error.get('detail')
            if isinstance(value, str):
                detail = ': ' + value[:350]
        except (ValueError, UnicodeError, AttributeError):
            pass
        raise RuntimeError(f"HTTP {exc.code} для {path}{detail}") from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def sync_node(row):
    now = int(time.time())
    try:
        key = fernet.decrypt(row["api_key_enc"].encode()).decode()
        dashboard = node_request(row["url"], key, "/api/dashboard")
        version = node_request(row["url"], key, "/api/version")
        snapshot = {
            "edition": version.get("edition") or ("easy" if dashboard.get("title") == "3WG Easy Core" else "core"),
            "panel_host": dashboard.get("panel_host"),
            "endpoint_host": dashboard.get("endpoint_host"),
            "version": version.get("current") or version.get("version") or "—",
            "protocols": dashboard.get("protocols") or [],
            "peers": dashboard.get("peers") or [],
            "cards": dashboard.get("cards") or [],
        }
        with db() as conn:
            conn.execute("UPDATE nodes SET last_sync_at=?, last_ok_at=?, last_error='', snapshot=? WHERE id=?", (now, now, json.dumps(snapshot), row["id"]))
        return True
    except (RuntimeError, InvalidToken) as exc:
        with db() as conn:
            conn.execute("UPDATE nodes SET last_sync_at=?, last_error=? WHERE id=?", (now, str(exc)[:300], row["id"]))
        return False


def public_node(row):
    try:
        snapshot = json.loads(row["snapshot"] or "{}")
    except json.JSONDecodeError:
        snapshot = {}
    return {
        "id": row["id"], "name": row["name"], "url": row["url"], "region": row["region"],
        "tags": [x.strip() for x in row["tags"].split(",") if x.strip()],
        "created_at": row["created_at"], "last_sync_at": row["last_sync_at"],
        "last_ok_at": row["last_ok_at"], "last_error": row["last_error"], "snapshot": snapshot,
    }


def get_node(node_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Нода не найдена")
    return row


def node_key(row):
    try:
        return fernet.decrypt(row["api_key_enc"].encode()).decode()
    except InvalidToken as exc:
        raise HTTPException(500, "Не удалось расшифровать ключ ноды") from exc


async def execute_node(node_id, path, method="POST", payload=None):
    row = get_node(node_id)
    try:
        result = await asyncio.to_thread(node_request, row["url"], node_key(row), path, 200 if path.startswith('/api/routing/bypass') else 30, method, payload)
    except RuntimeError as exc:
        raise HTTPException(502, f"Ошибка ноды: {exc}") from exc
    await asyncio.to_thread(sync_node, row)
    return result


MANAGEMENT_READ_PATHS = {
    "bypass-sources": "/api/routing/bypass/sources",
    "bypass": "/api/routing/bypass",
    "network": "/api/node/network",
    "status": "/api/node/status",
    "diagnostics": "/api/node/diagnostics",
    "users": "/api/users",
    "monitoring": "/api/monitoring",
    "p2p": "/api/p2p-guard",
    "updates": "/api/update/status",
    "audit": "/api/audit?limit=50",
    "backups": "/api/backups",
    "migration": "/api/migration",
}

MANAGEMENT_ACTIONS = {
    "bypass-sources-refresh": ("/api/routing/bypass/sources?refresh=true", "GET"),
    "bypass-update": ("/api/routing/bypass", "PATCH"),
    "network-preview": ("/api/node/network/preview", "POST"),
    "network-apply": ("/api/node/network/apply", "POST"),
    "network-confirm": ("/api/node/network/confirm", "POST"),
    "network-rollback": ("/api/node/network/rollback", "POST"),
    "backup-create": ("/api/backups", "POST"),
    "backup-delete": ("/api/backups/{item}", "DELETE"),
    "backup-restore": ("/api/backups/{item}/restore", "POST"),
    "p2p-apply": ("/api/p2p-guard/apply", "POST"),
    "p2p-update": ("/api/p2p-guard", "PATCH"),
    "update-run": ("/api/update/run", "POST"),
    "user-create": ("/api/users", "POST"),
    "user-update": ("/api/users/{item}", "PATCH"),
    "user-delete": ("/api/users/{item}", "DELETE"),
    "monitoring-update": ("/api/monitoring", "PATCH"),
    "monitoring-token-create": ("/api/monitoring/token", "POST"),
    "monitoring-token-delete": ("/api/monitoring/token/{item}", "DELETE"),
    "protocol-port": ("/api/node/protocols/{item}/port", "PATCH"),
    "migration-export": ("/api/migration/export", "POST"),
    "migration-delete": ("/api/migration/{item}", "DELETE"),
    "migration-push": ("/api/migration/push", "POST"),
}


@app.get("/health")
def health():
    return {"status": "ok", "service": "3wg-control-center"}


@app.get("/logo.png")
def logo():
    return FileResponse(BASE / "static" / "logo.png")


@app.get("/core.css")
def core_styles():
    return FileResponse(BASE / "static" / "core.css", media_type="text/css", headers={"Cache-Control": "no-cache"})


@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    expires = int(time.time()) + 12 * 3600
    username, password = str(data.get('username', '')), str(data.get('password', ''))
    if len(username) > 100 or len(password) > 1024:
        raise HTTPException(401, 'Неверный логин или пароль')
    if secrets.compare_digest(username.encode(), USER.encode()) and valid_password(password):
        token, role = sign_session(expires), 'admin'
    else:
        with db() as conn:
            row = conn.execute('SELECT * FROM tenants WHERE username=? AND enabled=1', (username,)).fetchone()
        # Perform a password derivation even for unknown accounts.
        valid = valid_password(password, row['password_hash'] if row else 'invalid$invalid')
        if not row or not valid:
            raise HTTPException(401, 'Неверный логин или пароль')
        token, role = tenant_session(row, expires), 'tenant'
    response = JSONResponse({"ok": True, 'role': role})
    response.set_cookie(COOKIE, token, max_age=12 * 3600, httponly=True, secure=COOKIE_SECURE, samesite="strict")
    return response


@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE)
    return response


@app.post('/api/account/password')
async def change_control_password(request: Request, threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    data = await request.json()
    old, new = str(data.get('current_password', '')), str(data.get('new_password', ''))
    if not valid_password(old):
        raise HTTPException(400, 'Текущий пароль неверен')
    if len(new) < 12 or len(new) > 1024 or new == old or new != data.get('confirm_password'):
        raise HTTPException(400, 'Подтвердите новый пароль длиной от 12 до 1024 символов')
    hashed = hash_password(new)
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT value FROM settings WHERE key='admin_password_hash'").fetchone()
        if not valid_password(old, row['value'] if row else ''):
            raise HTTPException(409, 'Пароль уже изменён. Войдите заново.')
        conn.execute("INSERT INTO settings(key,value) VALUES('admin_password_hash',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (hashed,))
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE)
    return response


@app.get("/api/state")
async def state(threewg_control_session: str | None = Cookie(default=None)):
    tenant = session_tenant(threewg_control_session)
    if not tenant:
        require_auth(threewg_control_session)
    with db() as conn:
        if tenant:
            rows = conn.execute('SELECT n.* FROM nodes n JOIN tenant_nodes t ON t.node_id=n.id WHERE t.tenant_id=? ORDER BY n.name', (tenant['id'],)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM nodes ORDER BY name COLLATE NOCASE").fetchall()
    nodes = [public_node(row) for row in rows]
    if tenant:
        safe_peer_fields = {'id', 'name', 'protocol', 'protocol_title', 'ip_cidr', 'enabled', 'online', 'status', 'rx_bytes', 'tx_bytes', 'traffic_rx', 'traffic_tx', 'expires_at', 'traffic_limit_bytes'}
        nodes = [{'id': n['id'], 'name': n['name'], 'last_sync_at': n['last_sync_at'],
                  'last_ok_at': n['last_ok_at'], 'last_error': 'Нет связи с нодой' if n['last_error'] else '',
                  'snapshot': {'peers': [{k:v for k,v in p.items() if k in safe_peer_fields} for p in n['snapshot'].get('peers', [])]}} for n in nodes]
    return {"ok": True, 'role': 'tenant' if tenant else 'admin', 'name': tenant['name'] if tenant else USER, "nodes": nodes, "summary": {
        "nodes": len(nodes),
        "online": sum(1 for n in nodes if n["last_ok_at"] and not n["last_error"]),
        "peers": sum(len(n["snapshot"].get("peers", [])) for n in nodes),
        "protocols": sum(sum(1 for p in n["snapshot"].get("protocols", []) if p.get("available")) for n in nodes),
    }}


@app.post("/api/nodes")
async def add_node(request: Request, threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    data = await request.json()
    name = str(data.get("name", "")).strip()[:80]
    key = str(data.get("api_key", "")).strip()
    url = clean_url(data.get("url"))
    if not name or not key:
        raise HTTPException(400, "Название и Node API Key обязательны")
    try:
        await asyncio.to_thread(node_request, url, key, "/api/dashboard")
    except RuntimeError as exc:
        raise HTTPException(400, f"Нода не прошла проверку: {exc}") from exc
    try:
        with db() as conn:
            cur = conn.execute("INSERT INTO nodes(name,url,api_key_enc,region,tags,created_at) VALUES(?,?,?,?,?,?)", (name, url, fernet.encrypt(key.encode()).decode(), str(data.get("region", "")).strip()[:80], str(data.get("tags", "")).strip()[:200], int(time.time())))
            node_id = cur.lastrowid
            row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Эта нода уже добавлена") from exc
    await asyncio.to_thread(sync_node, row)
    return {"ok": True, "id": node_id}


@app.post("/api/nodes/{node_id}/sync")
async def sync(node_id: int, threewg_control_session: str | None = Cookie(default=None)):
    require_node_access(threewg_control_session, node_id)
    with db() as conn:
        row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Нода не найдена")
    ok = await asyncio.to_thread(sync_node, row)
    return {"ok": ok}


@app.post("/api/sync")
async def sync_all(threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    with db() as conn:
        rows = conn.execute("SELECT * FROM nodes").fetchall()
    results = await asyncio.gather(*(asyncio.to_thread(sync_node, row) for row in rows))
    return {"ok": all(results), "synced": sum(results), "total": len(results)}


@app.delete("/api/nodes/{node_id}")
def delete_node(node_id: int, threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    with db() as conn:
        deleted = conn.execute("DELETE FROM nodes WHERE id=?", (node_id,)).rowcount
    if not deleted:
        raise HTTPException(404, "Нода не найдена")
    return {"ok": True}


@app.patch("/api/nodes/{node_id}")
async def edit_node(node_id: int, request: Request, threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    row = get_node(node_id)
    data = await request.json()
    name = str(data.get('name', row['name'])).strip()[:80]
    if not name:
        raise HTTPException(400, 'Название обязательно')
    url = clean_url(data.get('url', row['url']))
    key = str(data.get('api_key') or '').strip()
    if url != row['url'] or key:
        try:
            await asyncio.to_thread(node_request, url, key or node_key(row), '/api/dashboard')
        except RuntimeError as exc:
            raise HTTPException(400, f'Подключение не прошло проверку: {exc}') from exc
    encrypted = fernet.encrypt(key.encode()).decode() if key else row['api_key_enc']
    try:
        with db() as conn:
            conn.execute('UPDATE nodes SET name=?,url=?,api_key_enc=?,region=?,tags=? WHERE id=?',
                         (name, url, encrypted, str(data.get('region', row['region'])).strip()[:80],
                          str(data.get('tags', row['tags'])).strip()[:200], node_id))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Этот адрес уже используется другой нодой') from exc
    return {'ok': True}


@app.get("/api/nodes/{node_id}/manage/{section}")
async def management_section(node_id: int, section: str, threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    path = MANAGEMENT_READ_PATHS.get(section)
    if not path:
        raise HTTPException(404, "Раздел управления не найден")
    row = get_node(node_id)
    try:
        result = await asyncio.to_thread(node_request, row["url"], node_key(row), path, 60 if section == 'bypass-sources' else 30)
        if section == "updates" and isinstance(result, dict):
            version = result.get("version") or {}
            reported_latest = version.get("latest")
            if version_tuple(CONTROL_VERSION) > version_tuple(reported_latest):
                version["latest"] = CONTROL_VERSION
                version["state"] = "outdated" if version_tuple(version.get("current")) < version_tuple(CONTROL_VERSION) else "latest"
                version["source"] = "control-center"
                result["version"] = version
        return result
    except RuntimeError as exc:
        raise HTTPException(502, f"Ошибка ноды: {exc}") from exc


@app.post("/api/nodes/{node_id}/manage/action/{action}")
async def management_action(node_id: int, action: str, request: Request, threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    target = MANAGEMENT_ACTIONS.get(action)
    if not target:
        raise HTTPException(404, "Операция управления не найдена")
    data = await request.json()
    path = target[0]
    if "{item}" in path:
        item = str(data.pop("item", "")).strip()
        if not item or "/" in item or "\\" in item or item in {".", ".."}:
            raise HTTPException(400, "Некорректный идентификатор объекта")
        path = path.format(item=quote(item, safe=""))
    return await execute_node(node_id, path, method=target[1], payload=data)


@app.get("/api/nodes/{node_id}/manage/download/{kind}/{name}")
async def management_download(node_id: int, kind: str, name: str, threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    if kind not in {"backup", "migration"} or not name or "/" in name or "\\" in name:
        raise HTTPException(400, "Некорректный файл")
    path = f"/api/{'backups' if kind == 'backup' else 'migration'}/{quote(name, safe='')}/download"
    row = get_node(node_id)
    try:
        body, content_type, disposition = await asyncio.to_thread(node_request, row["url"], node_key(row), path, 60, "GET", None, True)
    except RuntimeError as exc:
        raise HTTPException(502, f"Ошибка ноды: {exc}") from exc
    headers = {"Content-Disposition": disposition} if disposition else {"Content-Disposition": f'attachment; filename="{name}"'}
    return Response(body, media_type=content_type, headers=headers)


@app.post("/api/nodes/{node_id}/peers")
async def create_peer(node_id: int, request: Request, threewg_control_session: str | None = Cookie(default=None)):
    require_node_access(threewg_control_session, node_id)
    data = await request.json()
    return await execute_node(node_id, "/api/peers", payload={
        "name": str(data.get("name", "")).strip()[:100],
        "protocols": [p for p in data.get("protocols", []) if p in {"wireguard", "amneziawg"}],
        "expires_at": data.get("expires_at"),
        "traffic_limit_bytes": data.get("traffic_limit_bytes", 0),
    })


@app.post("/api/nodes/{node_id}/peers/{peer_id}/{action}")
async def peer_action(node_id: int, peer_id: int, action: str, threewg_control_session: str | None = Cookie(default=None)):
    require_node_access(threewg_control_session, node_id)
    if action not in {"enable", "disable", "traffic-reset"}:
        raise HTTPException(400, "Недопустимое действие")
    return await execute_node(node_id, f"/api/peers/{peer_id}/{action}")


@app.delete("/api/nodes/{node_id}/peers/{peer_id}")
async def delete_peer(node_id: int, peer_id: int, threewg_control_session: str | None = Cookie(default=None)):
    require_node_access(threewg_control_session, node_id)
    return await execute_node(node_id, f"/api/peers/{peer_id}", method="DELETE")


@app.get("/api/nodes/{node_id}/peers/{peer_id}/download/{kind}")
async def download_peer(node_id: int, peer_id: int, kind: str, threewg_control_session: str | None = Cookie(default=None)):
    require_node_access(threewg_control_session, node_id)
    paths = {"conf": f"/client/{peer_id}/download", "vpn": f"/client/{peer_id}/download-vpn", "qr": f"/client/{peer_id}/qr/native/download", "qr-vpn": f"/client/{peer_id}/qr/amnezia-vpn/download"}
    if kind not in paths:
        raise HTTPException(400, "Неизвестный формат")
    row = get_node(node_id)
    try:
        body, content_type, disposition = await asyncio.to_thread(node_request, row["url"], node_key(row), paths[kind], 30, "GET", None, True)
    except RuntimeError as exc:
        raise HTTPException(502, f"Ошибка ноды: {exc}") from exc
    headers = {"Content-Disposition": disposition} if disposition else {}
    return Response(body, media_type=content_type, headers=headers)


@app.get('/api/tenants')
async def list_tenants(threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    with db() as conn:
        tenants = [dict(row) for row in conn.execute('SELECT id,name,username,enabled,created_at FROM tenants ORDER BY name')]
        assignments = conn.execute('SELECT tenant_id,node_id FROM tenant_nodes').fetchall()
    for tenant in tenants:
        tenant['node_ids'] = [r['node_id'] for r in assignments if r['tenant_id'] == tenant['id']]
    return {'tenants': tenants}


async def save_tenant(request, token, tenant_id=None):
    require_auth(token)
    data = await request.json()
    name, username, password = str(data.get('name', '')).strip(), str(data.get('username', '')).strip(), str(data.get('password', ''))
    node_ids = data.get('node_ids', [])
    if not name or len(name) > 100 or not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', username) or username.casefold() == USER.casefold():
        raise HTTPException(400, 'Укажите имя и уникальный логин из 3–64 латинских букв, цифр, точек, дефисов или подчёркиваний')
    if (not tenant_id or password) and not 12 <= len(password) <= 1024:
        raise HTTPException(400, 'Пароль должен содержать от 12 до 1024 символов')
    if not isinstance(node_ids, list) or len(node_ids) > 1000 or any(type(n) is not int or n < 1 for n in node_ids):
        raise HTTPException(400, 'Некорректные ноды')
    if type(data.get('enabled', True)) is not bool:
        raise HTTPException(400, 'Некорректное состояние клиента')
    hashed = hash_password(password) if password else None
    try:
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for node_id in set(node_ids):
                if not conn.execute('SELECT 1 FROM nodes WHERE id=?', (node_id,)).fetchone():
                    raise HTTPException(400, 'Нода не найдена')
                owner = conn.execute('SELECT tenant_id FROM tenant_nodes WHERE node_id=?', (node_id,)).fetchone()
                if owner and owner['tenant_id'] != tenant_id:
                    raise HTTPException(409, 'Нода уже назначена другому клиенту')
            if tenant_id:
                old = conn.execute('SELECT * FROM tenants WHERE id=?', (tenant_id,)).fetchone()
                if not old:
                    raise HTTPException(404, 'Клиент не найден')
                conn.execute('UPDATE tenants SET name=?,username=?,password_hash=?,enabled=?,session_version=session_version+1 WHERE id=?', (name, username, hashed or old['password_hash'], int(data.get('enabled', True)), tenant_id))
            else:
                tenant_id = conn.execute('INSERT INTO tenants(name,username,password_hash,enabled,created_at) VALUES(?,?,?,?,?)', (name, username, hashed, int(data.get('enabled', True)), int(time.time()))).lastrowid
            conn.execute('DELETE FROM tenant_nodes WHERE tenant_id=?', (tenant_id,))
            conn.executemany('INSERT INTO tenant_nodes(node_id,tenant_id) VALUES(?,?)', [(n,tenant_id) for n in set(node_ids)])
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Этот логин уже занят') from exc
    return {'ok': True, 'id': tenant_id}


@app.post('/api/tenants')
async def add_tenant(request: Request, threewg_control_session: str | None = Cookie(default=None)):
    return await save_tenant(request, threewg_control_session)


@app.patch('/api/tenants/{tenant_id}')
async def update_tenant(tenant_id: int, request: Request, threewg_control_session: str | None = Cookie(default=None)):
    return await save_tenant(request, threewg_control_session, tenant_id)


@app.get('/workspaces')
@app.get('/easy')
def workspace_frontend():
    return FileResponse(BASE / 'static' / 'workspaces.html', headers={'Cache-Control':'no-store'})


from exit_nodes import register as register_exit_nodes
register_exit_nodes(app, db, require_auth, fernet, SESSION_SECRET)


@app.get("/{path:path}")
def frontend(path: str):
    return FileResponse(BASE / "static" / "index.html", headers={"Cache-Control": "no-store"})
