import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Cookie, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse


BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("CONTROL_DB", "/app/data/control.db"))
USER = os.getenv("CONTROL_USER", "admin")
PASSWORD = os.getenv("CONTROL_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
FERNET_KEY = os.getenv("NODE_ENCRYPTION_KEY", "")
COOKIE_SECURE = os.getenv("SESSION_HTTPS_ONLY", "1") == "1"
COOKIE = "threewg_control_session"

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


def sign_session(expires):
    body = f"{USER}:{expires}"
    sig = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{body}:{sig}".encode()).decode()


def authenticated(token):
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        username, expires, signature = raw.split(":", 2)
        body = f"{username}:{expires}"
        expected = hmac.new(SESSION_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
        return username == USER and int(expires) > int(time.time()) and hmac.compare_digest(signature, expected)
    except Exception:
        return False


def require_auth(token):
    if not token or not authenticated(token):
        raise HTTPException(401, "Unauthorized")


def clean_url(value):
    url = str(value or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(400, "Укажите публичный HTTPS URL ноды")
    return url


def node_request(url, key, path, timeout=12):
    request = urllib.request.Request(url + path, headers={"X-API-Key": key, "Accept": "application/json", "User-Agent": "3WG-Control-Center/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} для {path}") from exc
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


@app.get("/health")
def health():
    return {"status": "ok", "service": "3wg-control-center"}


@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    if not secrets.compare_digest(str(data.get("username", "")), USER) or not secrets.compare_digest(str(data.get("password", "")), PASSWORD):
        raise HTTPException(401, "Неверный логин или пароль")
    expires = int(time.time()) + 12 * 3600
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, sign_session(expires), max_age=12 * 3600, httponly=True, secure=COOKIE_SECURE, samesite="strict")
    return response


@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE)
    return response


@app.get("/api/state")
async def state(threewg_control_session: str | None = Cookie(default=None)):
    require_auth(threewg_control_session)
    with db() as conn:
        rows = conn.execute("SELECT * FROM nodes ORDER BY name COLLATE NOCASE").fetchall()
    nodes = [public_node(row) for row in rows]
    return {"ok": True, "nodes": nodes, "summary": {
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
    require_auth(threewg_control_session)
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


@app.get("/{path:path}")
def frontend(path: str):
    return FileResponse(BASE / "static" / "index.html", headers={"Cache-Control": "no-store"})
