import base64
import html
import hashlib
import hmac
import io
import ipaddress
import json
import os
import re
import secrets
import shlex
import sqlite3
import socket
import struct
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

import docker
import qrcode
from api_keys_store import create_api_key, delete_api_key, init_api_keys, list_api_keys, valid_api_key
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials


APP_DIR = Path("/app")
DATA_DIR = APP_DIR / "data"
CLIENTS_DIR = APP_DIR / "clients"
BACKUPS_DIR = APP_DIR / "backups"
DB_PATH = DATA_DIR / "panel.db"
AUTO_BACKUP_INTERVALS = (1, 6, 12, 24, 48, 168)
AUTO_BACKUP_DEFAULTS = {
    "enabled": False,
    "interval_hours": 24,
    "keep_last": 7,
    "last_run_at": 0,
}
AUTO_BACKUP_LOCK = threading.Lock()
AUTO_BACKUP_THREAD_STARTED = False

PANEL_USER = os.getenv("PANEL_USER", "admin")
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "admin")
ENDPOINT_HOST = os.getenv("ENDPOINT_HOST", "cz-prg-01.nodax.eu")
PANEL_HOST = os.getenv("PANEL_HOST", ENDPOINT_HOST).strip() or ENDPOINT_HOST
VPN_ENDPOINT_HOST = os.getenv("VPN_ENDPOINT_HOST", ENDPOINT_HOST).strip() or ENDPOINT_HOST
VPN_EGRESS_IP = os.getenv("VPN_EGRESS_IP", "").strip()
DNS_SERVERS = os.getenv("DNS_SERVERS", "1.1.1.1, 1.0.0.1")
SESSION_SECRET = os.getenv("SESSION_SECRET", PANEL_PASSWORD + ENDPOINT_HOST)
SESSION_COOKIE = "3wg_session"
SESSION_VERSION = "v2"
RUNTIME_CACHE = {}
RUNTIME_CACHE_TTL_SECONDS = float(os.getenv("RUNTIME_CACHE_TTL_SECONDS", "3"))
PORT_CACHE_TTL_SECONDS = float(os.getenv("PORT_CACHE_TTL_SECONDS", "30"))
VERSION_FILE = APP_DIR / "VERSION"
APP_VERSION = os.getenv("APP_VERSION", VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "v1.3.0")
VERSION_REPOSITORY = os.getenv("VERSION_REPOSITORY", "dblack-adminix/3wg-panel")
VERSION_CHECK_URL = os.getenv("VERSION_CHECK_URL", f"https://api.github.com/repos/{VERSION_REPOSITORY}/tags")
VERSION_CHECK_TTL_SECONDS = float(os.getenv("VERSION_CHECK_TTL_SECONDS", "3600"))
VERSION_CACHE = {"checked_at": 0.0, "payload": None}
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "0") == "1"
METRICS_REQUIRE_TOKEN = os.getenv("METRICS_REQUIRE_TOKEN", "1") == "1"
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "0") == "1"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
UPDATE_RUNNER_ENABLED = os.getenv("UPDATE_RUNNER_ENABLED", "1") == "1"
UPDATE_RUNNER_SOCKET = os.getenv("UPDATE_RUNNER_SOCKET", "/app/run/update-runner.sock")
MIGRATION_RUNNER_ENABLED = os.getenv("MIGRATION_RUNNER_ENABLED", "1") == "1"
MIGRATION_RUNNER_SOCKET = os.getenv("MIGRATION_RUNNER_SOCKET", "/app/run/migration-runner.sock")
PANEL_CONTAINER = os.getenv("PANEL_CONTAINER", "3wg-panel")
FORNEX_VPN_PORTS = (
    "20, 21, 53, 80, 88, 110, 123, 143, 389, 443, 464, 500, "
    "587, 636, 749, 853, 993, 995, 1116-1150, 1863, "
    "3074-3079, 3268, 3269, 3283, 3306, 3389, 3478-3480, "
    "3658, 3689, 3724, 4000, 4379, 4380, 4398, 4500, 5165, "
    "5222, 5223, 5228-5230, 5235-5236, 5269, 5280"
)

PROTOCOLS = {
    "wireguard": {
        "title": "WireGuard",
        "container": os.getenv("WG_CONTAINER", "amnezia-wireguard"),
        "interface": os.getenv("WG_INTERFACE", "wg0"),
        "tool": "wg",
        "port": os.getenv("WG_PORT", "38129"),
        "config_path": os.getenv("WG_CONFIG_PATH", "/opt/amnezia/wireguard/wg0.conf"),
        "network": os.getenv("WG_NETWORK", "10.8.1.0/24"),
        "client_dir": CLIENTS_DIR / "wireguard",
        "backup_dir": BACKUPS_DIR / "wireguard",
    },
    "amneziawg": {
        "title": "AmneziaWG",
        "container": os.getenv("AWG_CONTAINER", "amnezia-awg2"),
        "interface": os.getenv("AWG_INTERFACE", "awg0"),
        "tool": "awg",
        "port": os.getenv("AWG_PORT", "42300"),
        "config_path": os.getenv("AWG_CONFIG_PATH", "/opt/amnezia/awg/awg0.conf"),
        "network": os.getenv("AWG_NETWORK", "10.8.1.0/24"),
        "client_dir": CLIENTS_DIR / "amneziawg",
        "backup_dir": BACKUPS_DIR / "amneziawg",
    },
}

AWG_MASK = {
    "Jc": "4",
    "Jmin": "10",
    "Jmax": "50",
    "S1": "54",
    "S2": "15",
    "S3": "36",
    "S4": "6",
    "H1": "718013012-1127562760",
    "H2": "1324176905-1725339417",
    "H3": "1781297739-2028576119",
    "H4": "2052615782-2092742079",
}

# Важно: для мобильного AmneziaWG убираем <r 2>, оставляем чистый <b ...>
AWG_I1_NATIVE = "<b 0x858000010001000000000669636c6f756403636f6d0000010001c00c000100010000105a00044d583737>"

app = FastAPI(title="3WG Core")
security = HTTPBasic(auto_error=False)



def make_session_token() -> str:
    msg = f"{PANEL_USER}:{PANEL_PASSWORD}".encode("utf-8")
    key = SESSION_SECRET.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def password_verify(password: str, stored: str) -> bool:
    try:
        algo, salt, expected = str(stored or "").split("$", 2)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    return secrets.compare_digest(password_hash(password, salt), stored)


def make_user_session(username: str, role: str) -> str:
    payload = f"{SESSION_VERSION}:{username}:{role}"
    sig = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_user_session(token: str) -> dict | None:
    parts = str(token or "").split(":")
    if len(parts) != 4 or parts[0] != SESSION_VERSION:
        return None
    payload = ":".join(parts[:3])
    sig = hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not secrets.compare_digest(sig, parts[3]):
        return None
    username, role = parts[1], parts[2]
    if username == PANEL_USER and role == "admin":
        return admin_user()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM panel_users WHERE username = ? AND enabled = 1",
            (username,),
        ).fetchone()
    if row and row["expires_at"] and int(row["expires_at"]) <= int(time.time()):
        return None
    return user_payload(row) if row else None


def admin_user() -> dict:
    return {
        "id": None,
        "username": PANEL_USER,
        "role": "admin",
        "peer_limit": None,
        "expires_at": None,
        "expiration": api_expiration_payload(None, True),
        "enabled": True,
        "is_admin": True,
        "is_env_admin": True,
    }


def user_payload(row) -> dict:
    traffic_limit_bytes = int(row["traffic_limit_bytes"]) if "traffic_limit_bytes" in row.keys() and row["traffic_limit_bytes"] else 0
    expires_at = int(row["expires_at"]) if "expires_at" in row.keys() and row["expires_at"] else None
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "role": row["role"],
        "peer_limit": int(row["peer_limit"]),
        "expires_at": expires_at,
        "expiration": api_expiration_payload(expires_at, bool(row["enabled"])),
        "traffic_limit_bytes": traffic_limit_bytes,
        "traffic_limit": api_user_traffic_limit_payload(int(row["id"]), traffic_limit_bytes),
        "enabled": bool(row["enabled"]),
        "created_at": int(row["created_at"]),
        "is_admin": row["role"] == "admin",
        "is_env_admin": False,
    }


def authenticate_user(username: str, password: str) -> dict | None:
    if secrets.compare_digest(username, PANEL_USER) and secrets.compare_digest(password, PANEL_PASSWORD):
        return admin_user()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM panel_users WHERE username = ? AND enabled = 1",
            (username,),
        ).fetchone()
    if row and row["expires_at"] and int(row["expires_at"]) <= int(time.time()):
        return None
    if row and password_verify(password, row["password_hash"]):
        return user_payload(row)
    return None


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", str(value or ""))
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def fetch_latest_version() -> dict:
    req = urllib.request.Request(
        VERSION_CHECK_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"3wg-panel/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(req, timeout=4) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tags = []
    for item in data if isinstance(data, list) else []:
        name = str(item.get("name", "")).strip()
        if version_tuple(name) != (0, 0, 0):
            tags.append(name)

    if not tags:
        raise RuntimeError("GitHub tags response does not contain semantic versions")

    latest = max(tags, key=version_tuple)
    current_tuple = version_tuple(APP_VERSION)
    latest_tuple = version_tuple(latest)
    if current_tuple < latest_tuple:
        state = "outdated"
    elif current_tuple > latest_tuple:
        state = "ahead"
    else:
        state = "latest"

    return {
        "ok": True,
        "current": APP_VERSION,
        "latest": latest,
        "state": state,
        "repository": VERSION_REPOSITORY,
        "checked_at": int(time.time()),
    }


def cached_version_status() -> dict:
    now = time.time()
    cached = VERSION_CACHE.get("payload")
    if cached and now - float(VERSION_CACHE.get("checked_at", 0)) < VERSION_CHECK_TTL_SECONDS:
        return cached

    try:
        payload = fetch_latest_version()
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "ok": False,
            "current": APP_VERSION,
            "latest": None,
            "state": "unknown",
            "repository": VERSION_REPOSITORY,
            "checked_at": int(now),
            "error": str(exc),
        }

    VERSION_CACHE["checked_at"] = now
    VERSION_CACHE["payload"] = payload
    return payload


def github_web_repository_url(repo: str | None = None) -> str:
    value = str(repo or VERSION_REPOSITORY or "").strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://github.com/{value.lstrip('/')}"


def update_runner_request(command: str, **extra) -> dict:
    payload = {"command": command, **extra}
    sock_path = Path(UPDATE_RUNNER_SOCKET)
    if not UPDATE_RUNNER_ENABLED:
        raise RuntimeError("UI update runner disabled")
    if not sock_path.exists():
        raise RuntimeError(f"Update runner socket not found: {UPDATE_RUNNER_SOCKET}")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5)
    try:
        client.connect(str(sock_path))
        client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    finally:
        client.close()
    if not data:
        raise RuntimeError("Update runner returned empty response")
    response = json.loads(data.decode("utf-8"))
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "Update runner error"))
    return response


def update_runner_status() -> dict | None:
    try:
        return update_runner_request("status")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return None


def empty_update_job() -> dict:
    return {"running": False, "started_at": None, "finished_at": None, "exit_code": None, "log": []}


def update_runner_payload() -> dict:
    sock_path = Path(UPDATE_RUNNER_SOCKET)
    exists = sock_path.exists()
    status = update_runner_status() if UPDATE_RUNNER_ENABLED and exists else None
    runner = status.get("runner") if status else {}
    script_exists = bool(runner.get("script_exists")) if runner else False
    can_run = bool(UPDATE_RUNNER_ENABLED and exists and script_exists)
    if not UPDATE_RUNNER_ENABLED:
        reason = "UI update runner disabled"
    elif not exists:
        reason = f"Runner socket not found: {UPDATE_RUNNER_SOCKET}"
    elif not status:
        reason = "Runner socket is not responding"
    elif not script_exists:
        reason = f"Update script not found: {runner.get('update_script') or 'unknown'}"
    else:
        reason = "ready"
    return {
        "enabled": UPDATE_RUNNER_ENABLED,
        "path": runner.get("update_script") or UPDATE_RUNNER_SOCKET,
        "socket": UPDATE_RUNNER_SOCKET,
        "base": runner.get("base"),
        "log_path": runner.get("log_path"),
        "pid": runner.get("pid"),
        "exists": exists,
        "can_run": can_run,
        "reason": reason,
        "confirm_text": "UPDATE",
    }


def update_job_payload() -> dict:
    status = update_runner_status()
    if status and isinstance(status.get("job"), dict):
        job = status["job"]
        return {
            "running": bool(job.get("running")),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "exit_code": job.get("exit_code"),
            "log": list(job.get("log") or [])[-240:],
        }
    return empty_update_job()


def migration_runner_request(command: str, **extra) -> dict:
    payload = {"command": command, **extra}
    sock_path = Path(MIGRATION_RUNNER_SOCKET)
    if not MIGRATION_RUNNER_ENABLED:
        raise RuntimeError("Migration runner disabled")
    if not sock_path.exists():
        raise RuntimeError(f"Migration runner socket not found: {MIGRATION_RUNNER_SOCKET}")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5)
    try:
        client.connect(str(sock_path))
        client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    finally:
        client.close()
    if not data:
        raise RuntimeError("Migration runner returned empty response")
    response = json.loads(data.decode("utf-8"))
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "Migration runner error"))
    return response


def migration_runner_status() -> dict | None:
    try:
        return migration_runner_request("status")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return None


def empty_migration_job() -> dict:
    return {"running": False, "started_at": None, "finished_at": None, "exit_code": None, "log": []}


def migration_runner_payload() -> dict:
    sock_path = Path(MIGRATION_RUNNER_SOCKET)
    exists = sock_path.exists()
    status = migration_runner_status() if MIGRATION_RUNNER_ENABLED and exists else None
    runner = status.get("runner") if status else {}
    can_run = bool(MIGRATION_RUNNER_ENABLED and exists and status)
    if not MIGRATION_RUNNER_ENABLED:
        reason = "Migration runner disabled"
    elif not exists:
        reason = f"Migration runner socket not found: {MIGRATION_RUNNER_SOCKET}"
    elif not status:
        reason = "Migration runner is not responding"
    else:
        reason = "ready"
    return {
        "enabled": MIGRATION_RUNNER_ENABLED,
        "socket": MIGRATION_RUNNER_SOCKET,
        "base": runner.get("base"),
        "log_path": runner.get("log_path"),
        "pid": runner.get("pid"),
        "sshpass": bool(runner.get("sshpass")),
        "exists": exists,
        "can_run": can_run,
        "reason": reason,
        "confirm_text": "MIGRATE",
    }


def migration_job_payload() -> dict:
    status = migration_runner_status()
    if status and isinstance(status.get("job"), dict):
        job = status["job"]
        return {
            "running": bool(job.get("running")),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "exit_code": job.get("exit_code"),
            "log": list(job.get("log") or [])[-240:],
        }
    return empty_migration_job()


def update_status_payload() -> dict:
    version = cached_version_status()
    latest = version.get("latest")
    current = version.get("current") or APP_VERSION
    repo = github_web_repository_url(version.get("repository") or VERSION_REPOSITORY)
    return {
        "ok": True,
        "version": version,
        "runner": update_runner_payload(),
        "job": update_job_payload(),
        "links": {
            "repository": repo,
            "tags": f"{repo}/tags",
            "compare": f"{repo}/compare/{current}...{latest}" if latest else None,
            "changelog": f"{repo}/releases/tag/{latest}" if latest else None,
        },
    }


def auth(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    cookie_token = request.cookies.get(SESSION_COOKIE)

    session_user = verify_user_session(cookie_token or "")
    if session_user:
        return session_user["username"]

    if cookie_token and secrets.compare_digest(cookie_token, make_session_token()):
        return PANEL_USER

    if credentials is not None:
        login_user = authenticate_user(credentials.username, credentials.password)
        if login_user:
            return credentials.username

    raise HTTPException(
        status_code=303,
        detail="Login required",
        headers={"Location": "/login"},
    )


def login_html(error: str = "") -> str:
    err = ""
    if error:
        err = f'<div class="login-error">{html.escape(error)}</div>'

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>3WG Core Login</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  --bg:#070b12;
  --card:#101827;
  --line:#283247;
  --text:#e9eefc;
  --muted:#8d9ab0;
  --orange:#ff8c00;
  --green:#c8ff00;
  --red:#ff5b6c;
}}
*{{box-sizing:border-box}}
body{{
  margin:0;
  min-height:100vh;
  display:flex;
  align-items:center;
  justify-content:center;
  background:
    radial-gradient(circle at 20% 20%, rgba(39,217,255,.12), transparent 28%),
    radial-gradient(circle at 80% 70%, rgba(200,255,0,.09), transparent 28%),
    var(--bg);
  color:var(--text);
  font-family:Inter,Arial,sans-serif;
}}
.login-card{{
  width:100%;
  max-width:430px;
  background:linear-gradient(180deg,#121b2a,#0d141f);
  border:1px solid var(--line);
  border-radius:24px;
  padding:30px;
  box-shadow:0 30px 120px rgba(0,0,0,.55);
}}
.logo{{
  font-size:30px;
  font-weight:900;
  letter-spacing:.08em;
  margin-bottom:8px;
}}
.sub{{
  color:var(--muted);
  margin-bottom:26px;
}}
label{{
  display:block;
  color:#b8c4d6;
  margin:16px 0 8px;
  font-weight:700;
}}
input{{
  width:100%;
  padding:14px 15px;
  border-radius:14px;
  border:1px solid #344052;
  background:#080e17;
  color:#fff;
  font-size:16px;
  outline:none;
}}
input:focus{{
  border-color:var(--orange);
}}
button{{
  width:100%;
  margin-top:22px;
  padding:14px 16px;
  border:0;
  border-radius:14px;
  background:var(--orange);
  color:#111;
  font-weight:900;
  font-size:16px;
  cursor:pointer;
}}
.login-error{{
  background:rgba(255,91,108,.1);
  border:1px solid rgba(255,91,108,.45);
  color:#ff9aa5;
  border-radius:14px;
  padding:12px;
  margin-bottom:16px;
}}
.footer{{
  margin-top:20px;
  color:var(--muted);
  font-size:13px;
  text-align:center;
}}
.badge{{
  display:inline-block;
  color:var(--green);
  border:1px solid rgba(200,255,0,.4);
  background:rgba(200,255,0,.08);
  padding:5px 9px;
  border-radius:999px;
  font-size:12px;
  font-weight:900;
  margin-bottom:18px;
}}
</style>
<link rel="stylesheet" href="/theme.css?v=3">
</head>
<body>
  <form class="login-card" method="post" action="/login">
    <div class="badge">3WG CORE</div>
    <div class="logo">3WG Core</div>
    <div class="sub">Централизованная платформа управления WireGuard и AmneziaWG</div>
    {err}
    <label>Логин</label>
    <input name="username" autocomplete="username" autofocus required>
    <label>Пароль</label>
    <input name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Войти</button>
    <div class="footer">cz-prg-01.nodax.eu</div>
  </form>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(login_html())


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    login_user = authenticate_user(username, password)
    if not login_user:
        return HTMLResponse(login_html("Неверный логин или пароль"), status_code=401)

    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE,
        make_user_session(login_user["username"], login_user["role"]),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp

def dc():
    return docker.from_env()


def proto(protocol: str):
    if protocol not in PROTOCOLS:
        raise HTTPException(status_code=404, detail="Unknown protocol")
    return PROTOCOLS[protocol]


def exec_c(container_name: str, cmd, check=True) -> str:
    c = dc().containers.get(container_name)
    res = c.exec_run(cmd, demux=True)

    out = b""
    err = b""

    if isinstance(res.output, tuple):
        out = res.output[0] or b""
        err = res.output[1] or b""
    else:
        out = res.output or b""

    stdout = out.decode("utf-8", errors="replace")
    stderr = err.decode("utf-8", errors="replace")

    if check and res.exit_code != 0:
        raise RuntimeError(
            f"Container: {container_name}\n"
            f"CMD: {cmd}\n"
            f"EXIT: {res.exit_code}\n\n"
            f"STDOUT:\n{stdout}\n\n"
            f"STDERR:\n{stderr}"
        )

    return stdout.strip()


def sh(container_name: str, script: str, check=True) -> str:
    return exec_c(container_name, ["sh", "-lc", script], check=check)


def cache_value(key, ttl: float, loader):
    now = time.monotonic()
    item = RUNTIME_CACHE.get(key)
    if item and item["expires"] > now:
        return item["value"]

    value = loader()
    RUNTIME_CACHE[key] = {"expires": now + ttl, "value": value}
    return value


def runtime_cache_clear():
    RUNTIME_CACHE.clear()


def interface_listen_port(protocol: str) -> str:
    def load():
        p = proto(protocol)
        try:
            port = exec_c(p["container"], [p["tool"], "show", p["interface"], "listen-port"], check=True)
            if port.strip().isdigit():
                return port.strip()
        except Exception:
            pass
        return str(p["port"])

    return cache_value(("listen_port", protocol), PORT_CACHE_TTL_SECONDS, load)


def docker_published_udp_port(protocol: str) -> str:
    def load():
        p = proto(protocol)
        fallback_port = str(p["port"])
        internal_port = interface_listen_port(protocol)

        try:
            container = dc().containers.get(p["container"])
            ports = (container.attrs.get("NetworkSettings") or {}).get("Ports") or {}
        except Exception:
            return internal_port or fallback_port

        candidates = []
        for port in (internal_port, fallback_port):
            key = f"{port}/udp"
            bindings = ports.get(key) or []
            for binding in bindings:
                host_port = str((binding or {}).get("HostPort") or "").strip()
                if host_port:
                    return host_port

        for key, bindings in ports.items():
            if not str(key).endswith("/udp"):
                continue
            for binding in bindings or []:
                host_port = str((binding or {}).get("HostPort") or "").strip()
                if host_port and host_port not in candidates:
                    candidates.append(host_port)

        if len(candidates) == 1:
            return candidates[0]
        return internal_port or fallback_port

    return cache_value(("published_udp_port", protocol), PORT_CACHE_TTL_SECONDS, load)


def client_endpoint(protocol: str) -> str:
    return f"{VPN_ENDPOINT_HOST}:{docker_published_udp_port(protocol)}"


def valid_udp_port(value) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некорректный UDP порт")
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Некорректный UDP порт")
    return port


def env_key_for_protocol_port(protocol: str) -> str:
    return "WG_PORT" if protocol == "wireguard" else "AWG_PORT"


def env_file_path() -> Path:
    candidates = [Path("/srv/3wg-panel/.env"), APP_DIR / ".env"]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def update_env_port(protocol: str, port: int) -> bool:
    path = env_file_path()
    if not path.exists():
        return False
    key = env_key_for_protocol_port(protocol)
    text = path.read_text(encoding="utf-8")
    line = f"{key}={port}"
    if re.search(rf"^{re.escape(key)}=.*$", text, flags=re.M):
        text = re.sub(rf"^{re.escape(key)}=.*$", line, text, flags=re.M)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    backup = BACKUPS_DIR / "source" / f".env.port-change.{time.strftime('%Y%m%d_%H%M%S')}.backup"
    backup.parent.mkdir(parents=True, exist_ok=True)
    try:
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        backup.chmod(0o600)
    except Exception:
        pass
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return True


def docker_udp_port_owner(port: int) -> str | None:
    target = str(port)
    try:
        containers = dc().containers.list(all=True)
    except Exception:
        return None
    for container in containers:
        ports = (container.attrs.get("NetworkSettings") or {}).get("Ports") or {}
        for key, bindings in ports.items():
            if not str(key).endswith("/udp"):
                continue
            for binding in bindings or []:
                if str((binding or {}).get("HostPort") or "").strip() == target:
                    return container.name
    return None


def host_udp_port_owner(port: int) -> str | None:
    try:
        result = subprocess.run(
            ["ss", "-H", "-lunp"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    marker = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[4]
        if not (local.endswith(marker) or local.endswith(f"{marker}]") or f"{marker} " in line):
            continue
        match = re.search(r'users:\(\("([^"]+)"', line)
        if match:
            return match.group(1)
        return "system"
    return None


def ensure_udp_port_available(protocol: str, port: int) -> None:
    owner = docker_udp_port_owner(port)
    current_container = proto(protocol)["container"]
    if owner and owner != current_container:
        raise HTTPException(status_code=409, detail=f"UDP порт {port} уже занят контейнером {owner}")
    host_owner = host_udp_port_owner(port)
    if host_owner and host_owner != "docker-proxy":
        raise HTTPException(status_code=409, detail=f"UDP порт {port} уже занят процессом {host_owner}")


def docker_port_conflict_detail(error: Exception, port: int) -> str | None:
    text = str(error)
    lowered = text.lower()
    if "address already in use" not in lowered and "port is already allocated" not in lowered:
        return None
    if port == 443:
        return "UDP порт 443 уже занят на сервере. Обычно его занимает Caddy/HTTP3. Освободите 443/udp или выберите другой порт из списка."
    return f"UDP порт {port} уже занят на сервере. Освободите порт или выберите другой UDP порт."


def set_container_listen_port(protocol: str, port: int) -> None:
    p = proto(protocol)
    backup_config(protocol)
    script = (
        f"path={shlex.quote(p['config_path'])}\n"
        f"line='ListenPort = {port}'\n"
        f"if grep -Eq '^[[:space:]]*ListenPort[[:space:]]*=' \"$path\"; then\n"
        f"  sed -i -E \"s|^[[:space:]]*ListenPort[[:space:]]*=.*$|$line|\" \"$path\"\n"
        f"else\n"
        f"  printf '\\n%s\\n' \"$line\" >> \"$path\"\n"
        f"fi\n"
    )
    sh(p["container"], script)


def protocol_config_with_listen_port(text: str, port: int) -> str:
    line = f"ListenPort = {port}"
    if re.search(r"^\s*ListenPort\s*=.*$", text, flags=re.M):
        return re.sub(r"^\s*ListenPort\s*=.*$", line, text, flags=re.M)
    return text.rstrip() + "\n" + line + "\n"


def put_container_text_file(container, path: str, text: str, mode: int = 0o600) -> None:
    target = Path(path)
    base = target.parent.parent if len(target.parts) >= 3 else target.parent
    arc_dir = target.parent.name
    arc_name = f"{arc_dir}/{target.name}" if base != target.parent else target.name
    data = io.BytesIO()
    payload = text.encode("utf-8")
    with tarfile.open(fileobj=data, mode="w") as tar:
        if base != target.parent:
            dir_info = tarfile.TarInfo(arc_dir)
            dir_info.type = tarfile.DIRTYPE
            dir_info.mode = 0o700
            dir_info.mtime = int(time.time())
            tar.addfile(dir_info)
        info = tarfile.TarInfo(arc_name)
        info.size = len(payload)
        info.mode = mode
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(payload))
    data.seek(0)
    container.put_archive(str(base), data.read())


def protocol_autostart_script(protocol: str) -> str:
    p = proto(protocol)
    tool = shlex.quote(p["tool"])
    quick = shlex.quote(f"{p['tool']}-quick")
    iface = shlex.quote(p["interface"])
    config_path = shlex.quote(p["config_path"])
    return (
        "#!/bin/sh\n"
        f"if command -v {tool} >/dev/null 2>&1 && command -v {quick} >/dev/null 2>&1; then\n"
        f"  if ! {tool} show {iface} >/dev/null 2>&1; then\n"
        f"    {quick} up {config_path} || true\n"
        "  fi\n"
        "fi\n"
        "if [ -x /opt/amnezia/3wg-p2p-guard.sh ]; then\n"
        "  /opt/amnezia/3wg-p2p-guard.sh || true\n"
        "fi\n"
        "tail -f /dev/null\n"
    )


def ensure_protocol_autostart(protocol: str) -> None:
    p = proto(protocol)
    put_container_text_file(dc().containers.get(p["container"]), "/opt/amnezia/start.sh", protocol_autostart_script(protocol), mode=0o755)


def activate_protocol_interface(protocol: str) -> None:
    p = proto(protocol)
    try:
        exec_c(p["container"], [p["tool"], "show", p["interface"]], check=True)
        return
    except Exception:
        pass
    sh(p["container"], f"{shlex.quote(p['tool'] + '-quick')} up {shlex.quote(p['config_path'])}", check=False)
    exec_c(p["container"], [p["tool"], "show", p["interface"]], check=True)


def recreate_protocol_container(protocol: str, port: int, config_text: str) -> None:
    p = proto(protocol)
    docker_client = dc()
    old = docker_client.containers.get(p["container"])
    attrs = old.attrs
    config = attrs.get("Config") or {}
    host_config = attrs.get("HostConfig") or {}
    image = config.get("Image") or (old.image.tags[0] if old.image.tags else old.image.id)
    env = list(config.get("Env") or [])
    binds = list(host_config.get("Binds") or [])
    cap_add = host_config.get("CapAdd") or []
    sysctls = host_config.get("Sysctls") or {}
    restart_name = (host_config.get("RestartPolicy") or {}).get("Name") or "unless-stopped"
    command = config.get("Cmd")
    entrypoint = config.get("Entrypoint")
    labels = config.get("Labels") or {}
    privileged = bool(host_config.get("Privileged"))
    security_opt = host_config.get("SecurityOpt") or None
    temp_name = f"{p['container']}-port-{int(time.time())}"
    new_container = docker_client.containers.create(
        image,
        name=temp_name,
        environment=env,
        command=command,
        entrypoint=entrypoint,
        labels=labels,
        volumes=binds,
        ports={f"{port}/udp": port},
        cap_add=cap_add,
        sysctls=sysctls,
        restart_policy={"Name": restart_name},
        privileged=privileged,
        security_opt=security_opt,
    )
    try:
        put_container_text_file(new_container, p["config_path"], config_text)
        put_container_text_file(new_container, "/opt/amnezia/start.sh", protocol_autostart_script(protocol), mode=0o755)
        new_container.start()
        activate_protocol_interface_by_container(protocol, new_container.name)
    except Exception as e:
        try:
            new_container.remove(force=True)
        except Exception:
            pass
        detail = docker_port_conflict_detail(e, port)
        if detail:
            raise HTTPException(status_code=409, detail=detail)
        raise

    old.stop(timeout=10)
    old.remove()
    new_container.reload()
    new_container.rename(p["container"])


def activate_protocol_interface_by_container(protocol: str, container_name: str) -> None:
    p = proto(protocol)
    try:
        exec_c(container_name, [p["tool"], "show", p["interface"]], check=True)
        return
    except Exception:
        pass
    sh(container_name, f"{shlex.quote(p['tool'] + '-quick')} up {shlex.quote(p['config_path'])}", check=False)
    exec_c(container_name, [p["tool"], "show", p["interface"]], check=True)


def change_protocol_port(protocol: str, port: int) -> dict:
    p = proto(protocol)
    ensure_udp_port_available(protocol, port)
    current = int(docker_published_udp_port(protocol))
    if port == current:
        return {"changed": False, "protocol": protocol, "port": port, "state": api_protocol_state(protocol)}
    original_config = exec_c(p["container"], ["sh", "-lc", f"cat {shlex.quote(p['config_path'])}"], check=True)
    backup_config(protocol)
    next_config = protocol_config_with_listen_port(original_config, port)
    recreate_protocol_container(protocol, port, next_config)
    update_env_port(protocol, port)
    runtime_cache_clear()
    return {"changed": True, "protocol": protocol, "old_port": current, "port": port, "state": api_protocol_state(protocol)}


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for p in PROTOCOLS.values():
        p["client_dir"].mkdir(parents=True, exist_ok=True)
        p["backup_dir"].mkdir(parents=True, exist_ok=True)

    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                protocol TEXT NOT NULL,
                ip_cidr TEXT NOT NULL,
                private_key TEXT NOT NULL,
                public_key TEXT NOT NULL,
                preshared_key TEXT NOT NULL,
                config_path TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL,
                UNIQUE(protocol, ip_cidr),
                UNIQUE(protocol, public_key)
            )
        """)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(clients)").fetchall()]
        if "deleted_at" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN deleted_at INTEGER NOT NULL DEFAULT 0")
        if "category_id" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN category_id INTEGER")
        if "owner_id" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN owner_id INTEGER")
        if "expires_at" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN expires_at INTEGER")
        if "traffic_limit_bytes" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN traffic_limit_bytes INTEGER NOT NULL DEFAULT 0")
        if "note" not in cols:
            conn.execute("ALTER TABLE clients ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clients_category_id ON clients(category_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clients_owner_id ON clients(owner_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clients_expires_at ON clients(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clients_traffic_limit_bytes ON clients(traffic_limit_bytes)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS panel_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                peer_limit INTEGER NOT NULL DEFAULT 1,
                traffic_limit_bytes INTEGER NOT NULL DEFAULT 0,
                expires_at INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            )
        """)
        user_cols = [r["name"] for r in conn.execute("PRAGMA table_info(panel_users)").fetchall()]
        if "traffic_limit_bytes" not in user_cols:
            conn.execute("ALTER TABLE panel_users ADD COLUMN traffic_limit_bytes INTEGER NOT NULL DEFAULT 0")
        if "expires_at" not in user_cols:
            conn.execute("ALTER TABLE panel_users ADD COLUMN expires_at INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_users_role ON panel_users(role)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_users_traffic_limit_bytes ON panel_users(traffic_limit_bytes)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_users_expires_at ON panel_users(expires_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traffic_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                protocol TEXT NOT NULL,
                interface TEXT NOT NULL,
                rx INTEGER NOT NULL,
                tx INTEGER NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traffic_snapshots_protocol_ts ON traffic_snapshots(protocol, ts)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_traffic_counters (
                client_id INTEGER PRIMARY KEY,
                protocol TEXT NOT NULL,
                public_key TEXT NOT NULL,
                rx_total INTEGER NOT NULL DEFAULT 0,
                tx_total INTEGER NOT NULL DEFAULT 0,
                last_rx INTEGER NOT NULL DEFAULT 0,
                last_tx INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_peer_traffic_counters_public_key ON peer_traffic_counters(protocol, public_key)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS panel_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                actor_id INTEGER,
                actor_username TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                action TEXT NOT NULL,
                object_type TEXT NOT NULL,
                object_id TEXT,
                object_label TEXT,
                ip TEXT,
                user_agent TEXT,
                context TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_ts ON audit_events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON audit_events(actor_username, ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_object ON audit_events(object_type, object_id, ts)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                cpu_percent REAL NOT NULL,
                memory_percent REAL NOT NULL,
                disk_percent REAL NOT NULL,
                load_one REAL NOT NULL,
                rx INTEGER NOT NULL,
                tx INTEGER NOT NULL,
                containers_running INTEGER NOT NULL,
                containers_total INTEGER NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_system_snapshots_ts ON system_snapshots(ts)")
        conn.commit()


def panel_setting_get(key: str, default: str | None = None) -> str | None:
    with db() as conn:
        row = conn.execute("SELECT value FROM panel_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def panel_setting_set(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO panel_settings(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, str(value), int(time.time())),
        )
        conn.commit()


@app.on_event("startup")
def startup():
    init_db()
    start_auto_backup_worker()


def slugify(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ._-]+", "_", value)
    value = value.strip("._-")
    return value or "client"


def genkey(protocol: str) -> str:
    p = proto(protocol)
    return exec_c(p["container"], [p["tool"], "genkey"])


def pubkey(protocol: str, private_key: str) -> str:
    p = proto(protocol)
    return sh(p["container"], f"printf '%s\\n' {shlex.quote(private_key)} | {p['tool']} pubkey")


def genpsk(protocol: str) -> str:
    p = proto(protocol)
    return exec_c(p["container"], [p["tool"], "genpsk"])


def server_pubkey(protocol: str) -> str:
    p = proto(protocol)
    return exec_c(p["container"], [p["tool"], "show", p["interface"], "public-key"])


def live_peers(protocol: str):
    def load():
        p = proto(protocol)
        out = exec_c(p["container"], [p["tool"], "show", "all", "dump"])
        peers = []

        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 8:
                continue
            if parts[0] != p["interface"]:
                continue

            allowed = parts[4]
            if "/" not in allowed:
                continue

            peers.append({
                "public_key": parts[1],
                "endpoint": parts[3],
                "allowed_ips": allowed,
                "latest_handshake": parts[5],
                "rx": parts[6],
                "tx": parts[7],
            })

        return peers

    return cache_value(("live_peers", protocol), RUNTIME_CACHE_TTL_SECONDS, load)


def server_interface_ips(protocol: str) -> set[str]:
    p = proto(protocol)
    try:
        cfg = sh(p["container"], f"cat {shlex.quote(p['config_path'])}")
    except Exception:
        return set()

    ips = set()
    for match in re.finditer(r"^Address\s*=\s*(.+?)\s*$", cfg, flags=re.M | re.I):
        for item in match.group(1).split(","):
            item = item.strip()
            if not item:
                continue
            try:
                ips.add(str(ipaddress.ip_interface(item).ip))
            except Exception:
                pass
    return ips


def used_ips(protocol: str):
    used = server_interface_ips(protocol)

    for peer in live_peers(protocol):
        allowed = peer["allowed_ips"].split(",")[0].strip()
        try:
            used.add(str(ipaddress.ip_interface(allowed).ip))
        except Exception:
            pass

    with db() as conn:
        rows = conn.execute("SELECT ip_cidr FROM clients WHERE protocol = ?", (protocol,)).fetchall()

    for row in rows:
        try:
            used.add(str(ipaddress.ip_interface(row["ip_cidr"]).ip))
        except Exception:
            pass

    return used


def next_ip(protocol: str) -> str:
    p = proto(protocol)
    net = ipaddress.ip_network(p["network"], strict=False)
    used = used_ips(protocol)

    for host in net.hosts():
        ip = str(host)
        if ip not in used:
            return f"{ip}/32"

    raise RuntimeError(f"No free IP in {p['network']}")


def backup_config(protocol: str):
    p = proto(protocol)
    content = sh(p["container"], f"cat {shlex.quote(p['config_path'])}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    path = p["backup_dir"] / f"{p['interface']}.conf.{ts}.backup"
    path.write_text(content + "\n", encoding="utf-8")
    path.chmod(0o600)


def add_peer_live(protocol: str, public_key: str, psk: str, ip_cidr: str):
    p = proto(protocol)
    script = (
        f"printf '%s\\n' {shlex.quote(psk)} > /tmp/3wg-peer.psk && "
        f"{p['tool']} set {shlex.quote(p['interface'])} "
        f"peer {shlex.quote(public_key)} "
        f"preshared-key /tmp/3wg-peer.psk "
        f"allowed-ips {shlex.quote(ip_cidr)}; "
        f"RC=$?; rm -f /tmp/3wg-peer.psk; exit $RC"
    )
    sh(p["container"], script)


def append_peer(protocol: str, name: str, public_key: str, psk: str, ip_cidr: str):
    p = proto(protocol)
    safe_name = name.replace("\n", " ").replace("\r", " ").strip()

    block = f"""

# 3WG-PANEL: {safe_name}
# created_at = {time.strftime('%Y-%m-%d %H:%M:%S')}
[Peer]
PublicKey = {public_key}
PresharedKey = {psk}
AllowedIPs = {ip_cidr}
"""

    script = f"cat >> {shlex.quote(p['config_path'])} <<'EOF_3WG_PEER'\n{block}\nEOF_3WG_PEER"
    sh(p["container"], script)




# =========================
# 3WG V2: dynamic AWG params + peer delete
# =========================

AWG_KEYS = ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4"]
AWG_I_KEYS = ["I1", "I2", "I3", "I4", "I5"]


def read_server_config(protocol: str) -> str:
    p = proto(protocol)
    return sh(p["container"], f"cat {shlex.quote(p['config_path'])}")


def write_server_config(protocol: str, text: str):
    p = proto(protocol)
    tmp = "/tmp/3wg-panel-new-config.conf"
    script = (
        f"cat > {shlex.quote(tmp)} <<'EOF_3WG_CONFIG'\n"
        f"{text.rstrip()}\n"
        f"EOF_3WG_CONFIG\n"
        f"cat {shlex.quote(tmp)} > {shlex.quote(p['config_path'])}\n"
        f"rm -f {shlex.quote(tmp)}\n"
    )
    sh(p["container"], script)


def awg_params_from_server():
    cfg = read_server_config("amneziawg")

    mask = {}
    for k in AWG_KEYS:
        m = re.search(rf"^{re.escape(k)}\s*=\s*(.+?)\s*$", cfg, flags=re.M)
        if not m:
            raise RuntimeError(f"{k} not found in AWG server config")
        mask[k] = m.group(1).strip()

    i_values = {}
    for k in AWG_I_KEYS:
        m = re.search(rf"^{re.escape(k)}\s*=\s*(.*?)\s*$", cfg, flags=re.M)
        if m and m.group(1).strip():
            i_values[k] = m.group(1).strip()

    return mask, i_values


def remove_peer_from_config_text(text: str, public_key: str) -> str:
    lines = text.splitlines()
    out = []
    i = 0
    removed = False

    while i < len(lines):
        if lines[i].strip() == "[Peer]":
            j = i + 1
            while j < len(lines) and lines[j].strip() != "[Peer]":
                j += 1

            block = "\n".join(lines[i:j])

            if re.search(r"^PublicKey\s*=\s*" + re.escape(public_key) + r"\s*$", block, flags=re.M):
                # Убираем наши служебные комментарии прямо перед peer-блоком
                while out and out[-1].strip().startswith("# 3WG-PANEL"):
                    out.pop()
                removed = True
                i = j
                continue

        out.append(lines[i])
        i += 1

    if not removed:
        return text

    return "\n".join(out).rstrip() + "\n"


def remove_peer(protocol: str, public_key: str):
    p = proto(protocol)

    backup_config(protocol)

    # Удаляем из live-интерфейса
    sh(
        p["container"],
        f"{p['tool']} set {shlex.quote(p['interface'])} peer {shlex.quote(public_key)} remove",
        check=False,
    )

    # Удаляем из server config
    old = read_server_config(protocol)
    new = remove_peer_from_config_text(old, public_key)

    if new != old:
        write_server_config(protocol, new)
    runtime_cache_clear()


def config_has_peer(protocol: str, public_key: str) -> bool:
    try:
        text = read_server_config(protocol)
    except Exception:
        return False
    return bool(re.search(r"^PublicKey\s*=\s*" + re.escape(public_key) + r"\s*$", text, flags=re.M))


def enable_peer(c):
    protocol = c["protocol"]
    public_key = c["public_key"]

    backup_config(protocol)
    add_peer_live(protocol, public_key, c["preshared_key"], c["ip_cidr"])

    if not config_has_peer(protocol, public_key):
        append_peer(protocol, c["name"], public_key, c["preshared_key"], c["ip_cidr"])

    with db() as conn:
        conn.execute("UPDATE clients SET enabled = 1 WHERE id = ?", (int(c["id"]),))
        conn.commit()
    runtime_cache_clear()


def disable_peer(c):
    remove_peer(c["protocol"], c["public_key"])
    with db() as conn:
        conn.execute("UPDATE clients SET enabled = 0 WHERE id = ?", (int(c["id"]),))
        conn.commit()
    runtime_cache_clear()


def build_client_conf(protocol: str, private_key: str, ip_cidr: str, psk: str) -> str:
    srv_pub = server_pubkey(protocol)

    text = f"""[Interface]
PrivateKey = {private_key}
"""

    if protocol == "amneziawg":
        mask, i_values = awg_params_from_server()

        for k in AWG_KEYS:
            text += f"{k} = {mask[k]}\n"

        for k in AWG_I_KEYS:
            v = i_values.get(k, "").strip()
            if v:
                text += f"{k} = {v}\n"

    text += f"""Address = {ip_cidr}
DNS = {DNS_SERVERS}
MTU = 1420
"""

    text += f"""
[Peer]
PublicKey = {srv_pub}
PresharedKey = {psk}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = {client_endpoint(protocol)}
PersistentKeepalive = 25
"""

    return text


def create_client(name: str, protocol: str, category_id: int | None = None, owner_id: int | None = None, expires_at: int | None = None, traffic_limit_bytes: int = 0) -> int:
    p = proto(protocol)

    ip_cidr = next_ip(protocol)
    private_key = genkey(protocol)
    public_key = pubkey(protocol, private_key)
    psk = genpsk(protocol)

    backup_config(protocol)
    add_peer_live(protocol, public_key, psk, ip_cidr)
    append_peer(protocol, name, public_key, psk, ip_cidr)

    conf = build_client_conf(protocol, private_key, ip_cidr, psk)

    ts = int(time.time())
    path = p["client_dir"] / f"{ts}_{slugify(name)}_{protocol}.conf"
    path.write_text(conf, encoding="utf-8")
    path.chmod(0o600)

    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO clients
            (name, protocol, ip_cidr, private_key, public_key, preshared_key, config_path, enabled, created_at, category_id, owner_id, expires_at, traffic_limit_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            """,
            (name, protocol, ip_cidr, private_key, public_key, psk, str(path), ts, category_id, owner_id, expires_at, int(traffic_limit_bytes or 0)),
        )
        conn.commit()
        runtime_cache_clear()
        return int(cur.lastrowid)


def human_bytes(v):
    try:
        n = int(v)
    except Exception:
        return v

    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    x = float(n)

    for u in units:
        if x < 1024:
            return f"{x:.2f} {u}"
        x /= 1024

    return f"{x:.2f} PiB"


def human_time(v):
    try:
        ts = int(v)
    except Exception:
        return "-"

    if ts <= 0:
        return "-"

    return time.strftime("%d/%m/%Y, %H:%M", time.localtime(ts))


def load_client(client_id: int):
    with db() as conn:
        c = conn.execute("SELECT * FROM clients WHERE id = ? AND COALESCE(deleted_at, 0) = 0", (client_id,)).fetchone()

    if not c:
        raise HTTPException(status_code=404, detail="Client not found")

    return c


def read_conf(c) -> str:
    text = Path(c["config_path"]).read_text(encoding="utf-8")
    protocol = c["protocol"]
    if protocol in PROTOCOLS:
        endpoint = client_endpoint(protocol)
        if re.search(r"^Endpoint\s*=", text, flags=re.M):
            text = re.sub(r"^Endpoint\s*=.*$", f"Endpoint = {endpoint}", text, flags=re.M)
    return text


def dns_pair():
    parts = [x.strip() for x in DNS_SERVERS.split(",") if x.strip()]
    return parts[0] if len(parts) > 0 else "", parts[1] if len(parts) > 1 else ""


def build_amnezia_vpn_payload(c) -> str:
    if c["protocol"] != "amneziawg":
        raise HTTPException(status_code=400, detail="AmneziaVPN QR is only for AmneziaWG")

    endpoint_port = docker_published_udp_port("amneziawg")
    conf_text = read_conf(c)
    ip_clean = str(ipaddress.ip_interface(c["ip_cidr"]).ip)
    dns1, dns2 = dns_pair()
    srv_pub = server_pubkey("amneziawg")
    mask, _ = awg_params_from_server()

    last_config_obj = {
        **mask,
        "client_ip": ip_clean,
        "client_priv_key": c["private_key"],
        "client_pub_key": "0",
        "psk_key": c["preshared_key"],
        "server_pub_key": srv_pub,
        "hostName": VPN_ENDPOINT_HOST,
        "port": int(endpoint_port),
        "config": conf_text,
    }

    amnezia_config = {
        "containers": [
            {
                "container": "amnezia-awg",
                "awg": {
                    "isThirdPartyConfig": True,
                    "transport_proto": "udp",
                    "port": str(endpoint_port),
                    **mask,
                    "last_config": json.dumps(last_config_obj, ensure_ascii=False),
                },
            }
        ],
        "defaultContainer": "amnezia-awg",
        "description": c["name"],
        "hostName": VPN_ENDPOINT_HOST,
        "dns1": dns1,
        "dns2": dns2,
    }

    plain = json.dumps(amnezia_config, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(plain, level=9)

    header = struct.pack(">III", 0x07C00100, len(compressed) + 4, len(plain))
    packed = header + compressed

    return base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")


def png_qr(payload: str):
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  --bg:#000000;
  --card:#111822;
  --card2:#0d131c;
  --line:#2a3441;
  --text:#dce7f5;
  --muted:#7e8ba0;
  --green:#c8ff00;
  --cyan:#27d9ff;
  --red:#ff5b6c;
  --yellow:#ff8c00;
  --orange:#ff8c00;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Arial,sans-serif}}
.wrap{{max-width:1600px;margin:0 auto;padding:28px}}
h1{{font-size:28px;margin:0 0 20px;font-weight:800;letter-spacing:.03em}}
.card{{background:linear-gradient(180deg,#121b28,#0e1520);border:1px solid var(--line);border-radius:18px;padding:20px;margin-bottom:18px;box-shadow:0 16px 50px rgba(0,0,0,.25)}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(170px,1fr));gap:14px;margin-bottom:18px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}}
.stat .n{{font-size:24px;font-weight:800;color:var(--green)}}
.stat .l{{font-size:13px;color:var(--muted);margin-top:6px}}
input[type=text]{{width:100%;max-width:460px;padding:13px 14px;border-radius:12px;border:1px solid #344052;background:#090f18;color:#fff;font-size:15px;outline:none}}
label{{margin-right:20px;color:#c9d4e5}}
button,.btn{{display:inline-block;padding:10px 15px;border-radius:12px;border:0;background:var(--orange);color:#111;font-weight:800;text-decoration:none;cursor:pointer;margin:4px 6px 4px 0}}
.btn2{{background:#1c2736;color:#dce7f5;border:1px solid #334056}}
.btn3{{background:#122d35;color:#45e6ff;border:1px solid #245260}} .btn-danger{{background:#3a1118;color:#ffb6be;border:1px solid #7a2630}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{border-bottom:1px solid var(--line);padding:13px 10px;text-align:left;vertical-align:middle;white-space:nowrap}}
th{{color:#98a6b9;font-weight:800}}
tr:hover{{background:#101927}}
code,pre{{background:#070707;color:#e9eefc;border:1px solid var(--line);border-radius:12px}}
code{{padding:3px 7px}}
pre{{padding:16px;overflow-x:auto;white-space:pre-wrap;line-height:1.45}}
.muted{{color:var(--muted)}}
.ok{{color:var(--green);font-weight:900}}
.bad{{color:var(--red);font-weight:900}}
.dot{{display:inline-block;width:12px;height:12px;border-radius:50%;background:var(--yellow);box-shadow:0 0 16px rgba(248,182,45,.5);margin-right:8px}}
.dot-green{{background:var(--green)}}
.dot-red{{background:var(--red)}}
.proto{{padding:5px 10px;border-radius:999px;background:#1d2a3b;color:#eaf4ff;font-weight:900}}
.proto-awg{{background:#102d39;color:#30dfff}}
.proto-wg{{background:#1b2d20;color:#4cff94}}
.qrgrid{{display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:18px}}
.qrbox{{background:#0c131d;border:1px solid var(--line);border-radius:18px;padding:18px}}
.qrbox img{{background:#fff;padding:14px;border-radius:14px;max-width:360px;width:100%}}
@media(max-width:900px){{.grid,.qrgrid{{grid-template-columns:1fr}} table{{font-size:12px}}}}
</style>
</head>
<body><div class="wrap">{body}</div><script src="/theme.js?v=3"></script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def index(user=Depends(auth)):
    with db() as conn:
        rows_db = conn.execute("SELECT * FROM clients WHERE COALESCE(deleted_at, 0) = 0 ORDER BY id DESC").fetchall()

    live = {}
    errors = {}

    for protocol in PROTOCOLS:
        try:
            live[protocol] = {x["public_key"]: x for x in live_peers(protocol)}
        except Exception as e:
            live[protocol] = {}
            errors[protocol] = str(e)

    known = set()
    rows = ""

    for c in rows_db:
        known.add((c["protocol"], c["public_key"]))
        p = PROTOCOLS[c["protocol"]]
        lp = live.get(c["protocol"], {}).get(c["public_key"])

        proto_class = "proto-awg" if c["protocol"] == "amneziawg" else "proto-wg"

        if lp:
            status = '<span class="dot dot-green"></span><span class="ok">ACTIVE</span>'
            endpoint = html.escape(lp["endpoint"])
            handshake = human_time(lp["latest_handshake"])
            rx = human_bytes(lp["rx"])
            tx = human_bytes(lp["tx"])
        else:
            status = '<span class="dot"></span><span class="muted">не подключался</span>'
            endpoint = "-"
            handshake = "-"
            rx = "0 B"
            tx = "0 B"

        rows += f"""
<tr>
<td>{c["id"]}</td>
<td><b>{html.escape(c["name"])}</b><br><span class="muted">создан панелью</span></td>
<td><span class="proto {proto_class}">{html.escape(p["title"])}</span></td>
<td><code>{html.escape(c["ip_cidr"])}</code></td>
<td>{status}</td>
<td>{endpoint}</td>
<td>{handshake}</td>
<td>{rx}</td>
<td>{tx}</td>
<td>
<a class="btn" href="/client/{c["id"]}">Открыть</a>
<form style="display:inline" method="post" action="/client/{c["id"]}/delete" onsubmit="return confirm('Удалить peer?')">
<button class="btn btn-danger" type="submit">Удалить</button>
</form>
</td>
</tr>
"""

    # Показываем уже существующие peer'ы в контейнерах.
    for protocol, peer_map in live.items():
        p = PROTOCOLS[protocol]
        proto_class = "proto-awg" if protocol == "amneziawg" else "proto-wg"
        for pub, lp in peer_map.items():
            if (protocol, pub) in known:
                continue

            pub_short = html.escape(pub[:12] + "..." + pub[-8:])
            endpoint = html.escape(lp["endpoint"])
            handshake = human_time(lp["latest_handshake"])
            rx = human_bytes(lp["rx"])
            tx = human_bytes(lp["tx"])

            if lp["endpoint"] != "(none)":
                status = '<span class="dot dot-green"></span><span class="ok">ACTIVE</span>'
            else:
                status = '<span class="dot"></span><span class="muted">не подключался</span>'

            rows += f"""
<tr>
<td>-</td>
<td><b>existing peer</b><br><code>{pub_short}</code></td>
<td><span class="proto {proto_class}">{html.escape(p["title"])}</span></td>
<td><code>{html.escape(lp["allowed_ips"])}</code></td>
<td>{status}</td>
<td>{endpoint}</td>
<td>{handshake}</td>
<td>{rx}</td>
<td>{tx}</td>
<td>
<form style="display:inline" method="post" action="/peer/delete" onsubmit="return confirm('Удалить existing peer?')">
<input type="hidden" name="protocol" value="{html.escape(protocol)}">
<input type="hidden" name="public_key" value="{html.escape(pub)}">
<button class="btn btn-danger" type="submit">Удалить</button>
</form>
</td>
</tr>
"""

    err_html = ""
    for k, v in errors.items():
        err_html += f"<p class='bad'>{html.escape(k)}: {html.escape(v)}</p>"

    total = len(rows_db)
    live_count = sum(1 for pm in live.values() for x in pm.values() if x["endpoint"] != "(none)")
    existing_count = sum(len(pm) for pm in live.values())

    body = f"""
<h1>3WG Core</h1>

<div class="grid">
  <div class="stat"><div class="n">{total}</div><div class="l">клиентов в панели</div></div>
  <div class="stat"><div class="n">{existing_count}</div><div class="l">peer'ов в контейнерах</div></div>
  <div class="stat"><div class="n">{live_count}</div><div class="l">сейчас в сети</div></div>
  <div class="stat"><div class="n">2</div><div class="l">протокола: WG / AWG</div></div>
</div>

<div class="card">
<h2>Создать клиента</h2>
<form method="post" action="/clients">
<p><input type="text" name="name" placeholder="Например: Ivan iPhone" required></p>
<p>
<label><input type="checkbox" name="protocol" value="wireguard" checked> WireGuard</label>
<label><input type="checkbox" name="protocol" value="amneziawg" checked> AmneziaWG с маскировкой</label>
</p>
<button type="submit">Создать peer / QR / conf</button>
</form>
<p class="muted">Endpoint host: <code>{html.escape(VPN_ENDPOINT_HOST)}</code></p>
{err_html}
</div>

<div class="card">
<h2>Клиенты</h2>
<table>
<thead>
<tr>
<th>ID</th><th>Имя пользователя</th><th>Протокол</th><th>Внутренний IP</th><th>Статус</th><th>Endpoint клиента</th><th>Последнее подключение</th><th>RX</th><th>TX</th><th></th>
</tr>
</thead>
<tbody>{rows if rows else '<tr><td colspan="10" class="muted">Пока нет клиентов</td></tr>'}</tbody>
</table>
</div>

<div class="card">
<h2>Статус</h2>
<a class="btn btn2" href="/raw/wireguard">wg show</a>
<a class="btn btn2" href="/raw/amneziawg">awg show</a>
</div>
"""
    return HTMLResponse(page("3WG Core", body))


@app.post("/clients")
async def create_clients(request: Request, user=Depends(auth)):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    protocols = form.getlist("protocol")

    if not name:
        return HTMLResponse(page("Ошибка", "<h1>Пустое имя</h1><a class='btn' href='/'>Назад</a>"), status_code=400)

    created = []

    try:
        for protocol in protocols:
            if protocol in PROTOCOLS:
                created.append(create_client(name, protocol))
    except Exception as e:
        return HTMLResponse(
            page("Ошибка", f"<h1>Ошибка создания</h1><pre>{html.escape(str(e))}</pre><a class='btn' href='/'>Назад</a>"),
            status_code=500,
        )

    if created:
        return RedirectResponse(f"/client/{created[-1]}", status_code=303)

    return RedirectResponse("/", status_code=303)


@app.get("/client/{client_id}", response_class=HTMLResponse)
def client_view(client_id: int, user=Depends(auth)):
    c = load_client(client_id)
    p = PROTOCOLS[c["protocol"]]
    conf = read_conf(c)

    qr_block = ""

    if c["protocol"] == "amneziawg":
        qr_block = f"""
<div class="qrgrid">
  <div class="qrbox">
    <h2>QR для AmneziaWG app</h2>
    <p class="muted">Native .conf. Если QR не примется — скачай .conf и импортируй файлом.</p>
    <img src="/client/{client_id}/qr/native">
    <p>
      <a class="btn" href="/client/{client_id}/download">Скачать .conf</a>
      <a class="btn btn2" href="/client/{client_id}/qr/native">Открыть QR</a>
    </p>
  </div>

  <div class="qrbox">
    <h2>QR для AmneziaVPN app</h2>
    <p class="muted">Специальный payload для AmneziaVPN. Дополнительно можно скачать .vpn ключ.</p>
    <img src="/client/{client_id}/qr/amnezia-vpn">
    <p>
      <a class="btn" href="/client/{client_id}/download-vpn">Скачать .vpn</a>
      <a class="btn btn2" href="/client/{client_id}/qr/amnezia-vpn">Открыть QR</a>
    </p>
  </div>
</div>
"""
    else:
        qr_block = f"""
<div class="qrgrid">
  <div class="qrbox">
    <h2>QR для WireGuard app</h2>
    <img src="/client/{client_id}/qr/native">
    <p>
      <a class="btn" href="/client/{client_id}/download">Скачать .conf</a>
      <a class="btn btn2" href="/client/{client_id}/qr/native">Открыть QR</a>
    </p>
  </div>
</div>
"""

    body = f"""
<h1>{html.escape(c["name"])} — {html.escape(p["title"])}</h1>

<div class="card">
<p>IP: <code>{html.escape(c["ip_cidr"])}</code></p>
<p>Endpoint: <code>{html.escape(VPN_ENDPOINT_HOST)}:{html.escape(p["port"])}</code></p>
<p>
<a class="btn btn2" href="/">Назад</a>
<a class="btn btn2" href="/raw/{c["protocol"]}">Статус протокола</a>
</p>
</div>

{qr_block}

<div class="card">
<h2>Конфиг</h2>
<pre>{html.escape(conf)}</pre>
</div>
"""
    return HTMLResponse(page(f"{c['name']} {p['title']}", body))




@app.post("/client/{client_id}/delete")
def delete_client_route(client_id: int, user=Depends(auth)):
    c = load_client(client_id)

    try:
        remove_peer(c["protocol"], c["public_key"])

        with db() as conn:
            conn.execute(
                "UPDATE clients SET enabled = 0, deleted_at = ? WHERE id = ?",
                (int(time.time()), client_id),
            )
            conn.commit()

        conf_path = Path(c["config_path"])
        if conf_path.exists():
            conf_path.rename(conf_path.with_suffix(conf_path.suffix + f".deleted.{int(time.time())}"))

    except Exception as e:
        return HTMLResponse(
            page("Ошибка удаления", f"<h1>Ошибка удаления</h1><pre>{html.escape(str(e))}</pre><a class='btn' href='/'>Назад</a>"),
            status_code=500,
        )

    return RedirectResponse("/", status_code=303)


@app.post("/peer/delete")
async def delete_existing_peer_route(request: Request, user=Depends(auth)):
    form = await request.form()
    protocol = str(form.get("protocol", ""))
    public_key = str(form.get("public_key", ""))

    if protocol not in PROTOCOLS or not public_key:
        return HTMLResponse(
            page("Ошибка", "<h1>Неверные данные</h1><a class='btn' href='/'>Назад</a>"),
            status_code=400,
        )

    try:
        remove_peer(protocol, public_key)

        with db() as conn:
            conn.execute(
                "UPDATE clients SET enabled = 0, deleted_at = ? WHERE protocol = ? AND public_key = ?",
                (int(time.time()), protocol, public_key),
            )
            conn.commit()

    except Exception as e:
        return HTMLResponse(
            page("Ошибка удаления", f"<h1>Ошибка удаления</h1><pre>{html.escape(str(e))}</pre><a class='btn' href='/'>Назад</a>"),
            status_code=500,
        )

    return RedirectResponse("/", status_code=303)


@app.get("/client/{client_id}/download")
def download(client_id: int, user=Depends(auth)):
    c = load_client(client_id)
    filename = f"{slugify(c['name'])}_{c['protocol']}.conf"
    return FileResponse(c["config_path"], filename=filename, media_type="application/octet-stream")


@app.get("/client/{client_id}/download-vpn")
def download_vpn(client_id: int, user=Depends(auth)):
    c = load_client(client_id)
    payload = build_amnezia_vpn_payload(c)
    content = "vpn://" + payload + "\n"
    filename = f"{slugify(c['name'])}_amnezia_config.vpn"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/client/{client_id}/qr/native")
def qr_native(client_id: int, user=Depends(auth)):
    c = load_client(client_id)
    return png_qr(read_conf(c))


@app.get("/client/{client_id}/qr/amnezia-vpn")
def qr_amnezia_vpn(client_id: int, user=Depends(auth)):
    c = load_client(client_id)
    payload = build_amnezia_vpn_payload(c)
    return png_qr(payload)


@app.get("/raw/{protocol}")
def raw(protocol: str, user=Depends(auth)):
    p = proto(protocol)
    out = exec_c(p["container"], [p["tool"], "show", p["interface"]])
    return PlainTextResponse(out)




# 3WG V7 QR PNG DOWNLOAD ROUTES

def png_qr_download(payload: str, filename: str):
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/client/{client_id}/qr/native/download")
def qr_native_download(client_id: int, user=Depends(auth)):
    c = load_client(client_id)
    filename = f"{slugify(c['name'])}_{c['protocol']}_qr.png"
    return png_qr_download(read_conf(c), filename)


@app.get("/client/{client_id}/qr/amnezia-vpn/download")
def qr_amnezia_vpn_download(client_id: int, user=Depends(auth)):
    c = load_client(client_id)
    payload = build_amnezia_vpn_payload(c)
    filename = f"{slugify(c['name'])}_amnezia_vpn_qr.png"
    return png_qr_download(payload, filename)


@app.get("/health")
def health():
    return {"status": "ok"}


# =========================
# 3WG PATCH: Pretty status modal
# =========================

def short_key(value: str) -> str:
    if not value or value == "-":
        return "-"
    if len(value) <= 24:
        return value
    return value[:12] + "..." + value[-8:]


def parse_show_output(raw: str):
    iface = {
        "name": "-",
        "public_key": "-",
        "listening_port": "-",
        "params": {},
    }
    peers = []
    current = None

    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue

        if s.startswith("interface:"):
            iface["name"] = s.split(":", 1)[1].strip()
            current = None
            continue

        if s.startswith("peer:"):
            current = {
                "public_key": s.split(":", 1)[1].strip(),
                "endpoint": "-",
                "allowed_ips": "-",
                "latest_handshake": "-",
                "transfer": "-",
            }
            peers.append(current)
            continue

        if current is None:
            if s.startswith("public key:"):
                iface["public_key"] = s.split(":", 1)[1].strip()
            elif s.startswith("listening port:"):
                iface["listening_port"] = s.split(":", 1)[1].strip()
            elif ":" in s:
                k, v = s.split(":", 1)
                k = k.strip()
                v = v.strip()
                if k in ["jc", "jmin", "jmax", "s1", "s2", "s3", "s4", "h1", "h2", "h3", "h4"]:
                    iface["params"][k] = v
        else:
            if s.startswith("endpoint:"):
                current["endpoint"] = s.split(":", 1)[1].strip()
            elif s.startswith("allowed ips:"):
                current["allowed_ips"] = s.split(":", 1)[1].strip()
            elif s.startswith("latest handshake:"):
                current["latest_handshake"] = s.split(":", 1)[1].strip()
            elif s.startswith("transfer:"):
                current["transfer"] = s.split(":", 1)[1].strip()

    return iface, peers


def render_pretty_status(protocol: str) -> str:
    p = proto(protocol)
    title = p["title"]
    raw = exec_c(p["container"], [p["tool"], "show", p["interface"]])
    iface, peers = parse_show_output(raw)

    param_html = ""
    if iface["params"]:
        for k, v in iface["params"].items():
            param_html += f"""
            <div class="st-mini">
              <span>{html.escape(k)}</span>
              <b>{html.escape(v)}</b>
            </div>
            """

    peer_rows = ""
    for peer in peers:
        active = peer["endpoint"] != "-"
        dot_class = "dot-green" if active else ""
        status_text = "ACTIVE" if active else "не подключался"

        peer_rows += f"""
        <tr>
          <td>
            <span class="dot {dot_class}"></span>
            <b>{status_text}</b>
          </td>
          <td><code>{html.escape(short_key(peer["public_key"]))}</code></td>
          <td><code>{html.escape(peer["allowed_ips"])}</code></td>
          <td>{html.escape(peer["endpoint"])}</td>
          <td>{html.escape(peer["latest_handshake"])}</td>
          <td>{html.escape(peer["transfer"])}</td>
        </tr>
        """

    if not peer_rows:
        peer_rows = '<tr><td colspan="6" class="muted">Peer-ов нет</td></tr>'

    return f"""
    <div class="modal-title-row">
      <div>
        <h2>{html.escape(title)} status</h2>
        <p class="muted">Команда: <code>{html.escape(p["tool"])} show {html.escape(p["interface"])}</code></p>
      </div>
      <div>
        <a class="btn btn2" target="_blank" href="/raw/{html.escape(protocol)}">Открыть raw</a>
      </div>
    </div>

    <div class="status-grid">
      <div class="st-card">
        <div class="st-label">Interface</div>
        <div class="st-value">{html.escape(iface["name"])}</div>
      </div>
      <div class="st-card">
        <div class="st-label">Port</div>
        <div class="st-value">{html.escape(iface["listening_port"])}</div>
      </div>
      <div class="st-card">
        <div class="st-label">Container</div>
        <div class="st-value">{html.escape(p["container"])}</div>
      </div>
      <div class="st-card">
        <div class="st-label">Public key</div>
        <div class="st-value"><code>{html.escape(short_key(iface["public_key"]))}</code></div>
      </div>
    </div>

    {"<div class='mask-grid'>" + param_html + "</div>" if param_html else ""}

    <h3>Peer'ы</h3>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Статус</th>
            <th>Public key</th>
            <th>Allowed IP</th>
            <th>Endpoint</th>
            <th>Handshake</th>
            <th>Transfer</th>
          </tr>
        </thead>
        <tbody>
          {peer_rows}
        </tbody>
      </table>
    </div>

    <details class="raw-box">
      <summary>Показать raw вывод</summary>
      <pre>{html.escape(raw)}</pre>
    </details>
    """


@app.get("/status/{protocol}", response_class=HTMLResponse)
def pretty_status(protocol: str, user=Depends(auth)):
    try:
        return HTMLResponse(render_pretty_status(protocol))
    except Exception as e:
        return HTMLResponse(
            f"<h2>Ошибка статуса</h2><pre>{html.escape(str(e))}</pre>",
            status_code=500,
        )


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  --bg:#000000;
  --card:#111822;
  --card2:#0d131c;
  --line:#2a3441;
  --text:#dce7f5;
  --muted:#7e8ba0;
  --green:#c8ff00;
  --cyan:#27d9ff;
  --red:#ff5b6c;
  --yellow:#ff8c00;
  --orange:#ff8c00;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Arial,sans-serif}}
.wrap{{max-width:1600px;margin:0 auto;padding:28px}}
h1{{font-size:28px;margin:0 0 20px;font-weight:800;letter-spacing:.03em}}
.card{{background:linear-gradient(180deg,#121b28,#0e1520);border:1px solid var(--line);border-radius:18px;padding:20px;margin-bottom:18px;box-shadow:0 16px 50px rgba(0,0,0,.25)}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(170px,1fr));gap:14px;margin-bottom:18px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}}
.stat .n{{font-size:24px;font-weight:800;color:var(--green)}}
.stat .l{{font-size:13px;color:var(--muted);margin-top:6px}}
input[type=text]{{width:100%;max-width:460px;padding:13px 14px;border-radius:12px;border:1px solid #344052;background:#090f18;color:#fff;font-size:15px;outline:none}}
label{{margin-right:20px;color:#c9d4e5}}
button,.btn{{display:inline-block;padding:10px 15px;border-radius:12px;border:0;background:var(--orange);color:#111;font-weight:800;text-decoration:none;cursor:pointer;margin:4px 6px 4px 0}}
.btn2{{background:#1c2736;color:#dce7f5;border:1px solid #334056}}
.btn3{{background:#122d35;color:#45e6ff;border:1px solid #245260}} .btn-danger{{background:#3a1118;color:#ffb6be;border:1px solid #7a2630}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{border-bottom:1px solid var(--line);padding:13px 10px;text-align:left;vertical-align:middle;white-space:nowrap}}
th{{color:#98a6b9;font-weight:800}}
tr:hover{{background:#101927}}
code,pre{{background:#070707;color:#e9eefc;border:1px solid var(--line);border-radius:12px}}
code{{padding:3px 7px}}
pre{{padding:16px;overflow-x:auto;white-space:pre-wrap;line-height:1.45}}
.muted{{color:var(--muted)}}
.ok{{color:var(--green);font-weight:900}}
.bad{{color:var(--red);font-weight:900}}
.dot{{display:inline-block;width:12px;height:12px;border-radius:50%;background:var(--yellow);box-shadow:0 0 16px rgba(248,182,45,.5);margin-right:8px}}
.dot-green{{background:var(--green);box-shadow:0 0 16px rgba(200,255,0,.5)}}
.dot-red{{background:var(--red)}}
.proto{{padding:5px 10px;border-radius:999px;background:#1d2a3b;color:#eaf4ff;font-weight:900}}
.proto-awg{{background:#102d39;color:#30dfff}}
.proto-wg{{background:#1b2d20;color:#4cff94}}
.qrgrid{{display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:18px}}
.qrbox{{background:#0c131d;border:1px solid var(--line);border-radius:18px;padding:18px}}
.qrbox img{{background:#fff;padding:14px;border-radius:14px;max-width:360px;width:100%}}

.modal-bg{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:9999;padding:30px;overflow:auto}}
.modal-bg.open{{display:block}}
.modal-window{{max-width:1350px;margin:20px auto;background:#0a0a0a;border:1px solid #344052;border-radius:22px;box-shadow:0 30px 100px rgba(0,0,0,.65);overflow:hidden}}
.modal-head{{display:flex;align-items:center;justify-content:space-between;padding:18px 22px;background:#111a28;border-bottom:1px solid var(--line)}}
.modal-head b{{font-size:18px}}
.modal-body{{padding:22px}}
.modal-close{{background:#263149;color:#fff;border:1px solid #3b465f;border-radius:10px;padding:8px 12px;cursor:pointer;font-weight:800}}
.modal-title-row{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:16px}}
.status-grid{{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px;margin-bottom:18px}}
.st-card{{background:#101827;border:1px solid var(--line);border-radius:16px;padding:15px}}
.st-label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}
.st-value{{font-size:17px;font-weight:900;margin-top:7px}}
.mask-grid{{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px;margin-bottom:18px}}
.st-mini{{background:#07111a;border:1px solid #263443;border-radius:12px;padding:10px}}
.st-mini span{{display:block;color:var(--muted);font-size:12px;text-transform:uppercase}}
.st-mini b{{display:block;margin-top:5px;color:var(--cyan)}}
.table-scroll{{overflow-x:auto}}
.raw-box{{margin-top:18px;background:#0a1019;border:1px solid var(--line);border-radius:14px;padding:14px}}
.raw-box summary{{cursor:pointer;font-weight:900;color:var(--cyan)}}
@media(max-width:900px){{.grid,.qrgrid,.status-grid,.mask-grid{{grid-template-columns:1fr}} table{{font-size:12px}} .modal-bg{{padding:8px}}}}
</style>
</head>
<body>
<div class="wrap">{body}</div>

<div id="statusModal" class="modal-bg">
  <div class="modal-window">
    <div class="modal-head">
      <b id="statusModalTitle">Статус</b>
      <button class="modal-close" onclick="closeStatusModal()">Закрыть</button>
    </div>
    <div id="statusModalBody" class="modal-body">
      Загрузка...
    </div>
  </div>
</div>

<script>
function closeStatusModal() {{
  document.getElementById('statusModal').classList.remove('open');
}}

async function openStatusModal(protocol) {{
  const modal = document.getElementById('statusModal');
  const body = document.getElementById('statusModalBody');
  const title = document.getElementById('statusModalTitle');

  title.textContent = protocol === 'amneziawg' ? 'awg show' : 'wg show';
  body.innerHTML = '<p class="muted">Загрузка статуса...</p>';
  modal.classList.add('open');

  try {{
    const r = await fetch('/status/' + protocol, {{cache: 'no-store'}});
    body.innerHTML = await r.text();
  }} catch (e) {{
    body.innerHTML = '<h2>Ошибка</h2><pre>' + String(e) + '</pre>';
  }}
}}

document.addEventListener('click', function(e) {{
  const a = e.target.closest('a[href^="/raw/"]');
  if (!a) return;

  e.preventDefault();

  const protocol = a.getAttribute('href').split('/raw/')[1];
  openStatusModal(protocol);
}});

document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeStatusModal();
}});

document.getElementById('statusModal').addEventListener('click', function(e) {{
  if (e.target.id === 'statusModal') closeStatusModal();
}});
</script>
</body></html>"""


# =========================
# 3WG UI THEME V3
# =========================

@app.get("/theme.css")
def theme_css():
    return PlainTextResponse(r"""
:root {
  --neo-bg: #000000;
  --neo-bg2: #0a0a0a;
  --neo-sidebar: #070707;
  --neo-card: #0d0d0d;
  --neo-card2: #111111;
  --neo-border: #262626;
  --neo-border2: #333333;
  --neo-text: #ffffff;
  --neo-muted: #999999;
  --neo-muted2: #666666;
  --neo-green: #c8ff00;
  --neo-green2: #a3d100;
  --neo-cyan: #ff8c00;
  --neo-blue: #ff8c00;
  --neo-red: #ff5b73;
  --neo-red2: #4a121d;
  --neo-yellow: #ff8c00;
  --neo-orange: #ff8c00;
  --neo-shadow: 0 18px 70px rgba(0,0,0,.38);
}

html {
  background: var(--neo-bg);
}

body {
  background:
    radial-gradient(circle at 20% -10%, rgba(255,140,0,.08), transparent 32%),
    radial-gradient(circle at 100% 0%, rgba(200,255,0,.06), transparent 28%),
    linear-gradient(180deg, #000000 0%, #0a0a0a 100%) !important;
  color: var(--neo-text) !important;
  min-height: 100vh;
}

.wrap {
  max-width: none !important;
  margin-left: 250px !important;
  padding: 22px 26px 42px !important;
}

.neo-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  width: 230px;
  background:
    linear-gradient(180deg, rgba(7,7,7,.98), rgba(5,5,5,.98)),
    radial-gradient(circle at top, rgba(255,140,0,.08), transparent 38%);
  border-right: 1px solid rgba(51,51,51,.75);
  z-index: 1000;
  padding: 18px 14px;
  box-shadow: 18px 0 60px rgba(0,0,0,.25);
}

.neo-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 6px 8px 22px;
  border-bottom: 1px dashed rgba(255,140,0,.18);
  margin-bottom: 18px;
}

.neo-brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 11px;
  display: grid;
  place-items: center;
  background: rgba(200,255,0,.1);
  color: var(--neo-green);
  border: 1px solid rgba(200,255,0,.35);
  font-weight: 900;
  box-shadow: 0 0 22px rgba(200,255,0,.12);
}

.neo-brand-title {
  font-size: 20px;
  font-weight: 900;
  letter-spacing: .04em;
}

.neo-brand-sub {
  font-size: 11px;
  color: var(--neo-muted);
  margin-top: 1px;
}

.neo-section {
  margin: 18px 8px 8px;
  color: var(--neo-muted2);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .16em;
  font-weight: 900;
}

.neo-nav a {
  display: flex;
  align-items: center;
  gap: 11px;
  min-height: 39px;
  padding: 0 12px;
  border-radius: 11px;
  color: #cccccc;
  text-decoration: none;
  font-weight: 700;
  font-size: 14px;
  margin-bottom: 4px;
  border: 1px solid transparent;
}

.neo-nav a:hover,
.neo-nav a.active {
  background: rgba(200,255,0,.08);
  border-color: rgba(200,255,0,.22);
  color: #f5ffe0;
}

.neo-nav .ico {
  width: 20px;
  color: var(--neo-cyan);
  text-align: center;
}

.neo-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.neo-title {
  display: flex;
  align-items: center;
  gap: 13px;
}

.neo-title-badge {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: rgba(255,140,0,.08);
  border: 1px solid rgba(255,140,0,.25);
  color: var(--neo-cyan);
  font-weight: 900;
}

.neo-top-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.neo-round {
  width: 39px;
  height: 39px;
  border-radius: 13px;
  display: grid;
  place-items: center;
  background: rgba(17,26,38,.86);
  border: 1px solid rgba(51,51,51,.9);
  color: var(--neo-text);
  box-shadow: 0 10px 30px rgba(0,0,0,.18);
}

h1 {
  font-size: 25px !important;
  margin: 0 0 2px !important;
  letter-spacing: .04em;
}

h2 {
  font-size: 20px !important;
  letter-spacing: .02em;
}

.card,
.stat,
.qrbox,
.st-card {
  background:
    linear-gradient(180deg, rgba(18,27,40,.94), rgba(12,19,29,.94)) !important;
  border: 1px solid rgba(51,51,51,.75) !important;
  box-shadow: var(--neo-shadow) !important;
}

.card {
  border-radius: 18px !important;
  padding: 18px !important;
}

.grid {
  gap: 12px !important;
  margin-bottom: 16px !important;
}

.stat {
  min-height: 78px;
  border-radius: 15px !important;
  position: relative;
  overflow: hidden;
}

.stat::after {
  content: "";
  position: absolute;
  inset: auto 14px 10px auto;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: rgba(200,255,0,.08);
  border: 1px solid rgba(200,255,0,.18);
}

.stat .n {
  color: var(--neo-green) !important;
  font-size: 24px !important;
  text-shadow: 0 0 18px rgba(200,255,0,.22);
}

.stat .l {
  color: var(--neo-muted) !important;
  font-size: 12px !important;
}

input[type=text],
input[type=password],
input {
  background: #09111c !important;
  border: 1px solid rgba(70,88,110,.8) !important;
  color: var(--neo-text) !important;
  border-radius: 12px !important;
  transition: .18s ease;
}

input:focus {
  border-color: rgba(255,140,0,.65) !important;
  box-shadow: 0 0 0 4px rgba(255,140,0,.08) !important;
}

button,
.btn {
  border-radius: 12px !important;
  font-weight: 900 !important;
  transition: .16s ease;
}

button:hover,
.btn:hover {
  transform: translateY(-1px);
  filter: brightness(1.06);
}

table {
  border-collapse: separate !important;
  border-spacing: 0 8px !important;
}

thead th {
  border-bottom: 0 !important;
  color: #94a6bb !important;
  font-size: 12px !important;
  text-transform: uppercase;
  letter-spacing: .04em;
}

tbody tr {
  background: rgba(7,7,7,.66);
  border: 1px solid rgba(51,51,51,.55);
}

tbody tr:hover {
  background: rgba(14,26,39,.96) !important;
}

tbody td {
  border-bottom: 1px solid rgba(51,51,51,.45) !important;
  padding: 13px 10px !important;
}

tbody td:first-child {
  border-left: 1px solid rgba(51,51,51,.45);
  border-radius: 12px 0 0 12px;
}

tbody td:last-child {
  border-right: 1px solid rgba(51,51,51,.45);
  border-radius: 0 12px 12px 0;
}

code {
  background: #070d15 !important;
  border: 1px solid rgba(51,51,51,.72) !important;
  color: #e8f3ff !important;
  border-radius: 9px !important;
}

.proto {
  border-radius: 999px !important;
  font-size: 12px;
  letter-spacing: .03em;
}

.proto-awg {
  background: rgba(255,140,0,.11) !important;
  color: #42e4ff !important;
  border: 1px solid rgba(255,140,0,.22);
}

.proto-wg {
  background: rgba(200,255,0,.11) !important;
  color: #55ffb5 !important;
  border: 1px solid rgba(200,255,0,.22);
}

.ok {
  color: var(--neo-green) !important;
}

.dot {
  width: 10px !important;
  height: 10px !important;
  vertical-align: middle;
}

.dot-green {
  background: var(--neo-green) !important;
  box-shadow: 0 0 18px rgba(200,255,0,.62) !important;
}

.btn.icon-btn,
button.icon-btn {
  width: 38px !important;
  height: 38px !important;
  padding: 0 !important;
  margin: 0 4px !important;
  display: inline-grid !important;
  place-items: center !important;
  border-radius: 13px !important;
  font-size: 17px !important;
  line-height: 1 !important;
  color: var(--neo-text) !important;
  background: rgba(26,38,54,.95) !important;
  border: 1px solid rgba(70,88,110,.82) !important;
  box-shadow: 0 8px 22px rgba(0,0,0,.22);
}

.btn.icon-open {
  color: #121820 !important;
  background: var(--neo-orange) !important;
  border-color: rgba(244,163,64,.75) !important;
}

.btn.icon-delete,
button.icon-delete {
  background: rgba(74,18,29,.95) !important;
  color: #ffd2d8 !important;
  border-color: rgba(255,91,115,.42) !important;
}

.btn.icon-status {
  background: rgba(255,140,0,.10) !important;
  color: #54e8ff !important;
  border-color: rgba(255,140,0,.28) !important;
}

form[method="post"] {
  margin: 0;
}

.card:has(table) {
  overflow-x: auto;
}

.qrgrid {
  gap: 16px !important;
}

.qrbox img {
  border-radius: 16px !important;
  box-shadow: 0 18px 60px rgba(0,0,0,.25);
}

.modal-window {
  border-radius: 20px !important;
  border: 1px solid rgba(51,51,51,.9) !important;
  background: #0a111b !important;
}

.modal-head {
  background: #111b29 !important;
}

.raw-box {
  background: rgba(7,13,21,.86) !important;
}

::-webkit-scrollbar {
  width: 9px;
  height: 9px;
}

::-webkit-scrollbar-thumb {
  background: #26364a;
  border-radius: 999px;
}

::-webkit-scrollbar-track {
  background: #08101a;
}

.neo-pulse {
  animation: neoPulse 2.2s infinite;
}

@keyframes neoPulse {
  0% { box-shadow: 0 0 0 0 rgba(200,255,0,.26); }
  70% { box-shadow: 0 0 0 9px rgba(200,255,0,0); }
  100% { box-shadow: 0 0 0 0 rgba(200,255,0,0); }
}

@media (max-width: 1000px) {
  .neo-sidebar {
    display: none;
  }

  .wrap {
    margin-left: 0 !important;
    padding: 16px !important;
  }

  .neo-topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  table {
    font-size: 12px !important;
  }
}
""", media_type="text/css")


@app.get("/theme.js")
def theme_js():
    return PlainTextResponse(r"""
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    if (!document.querySelector('.neo-sidebar')) {
      const sidebar = document.createElement('aside');
      sidebar.className = 'neo-sidebar';
      sidebar.innerHTML = `
        <div class="neo-brand">
          <div class="neo-brand-mark">3</div>
          <div>
            <div class="neo-brand-title">3WG</div>
            <div class="neo-brand-sub">CORE PLATFORM</div>
          </div>
        </div>

        <div class="neo-section">Обзор</div>
        <nav class="neo-nav">
          <a class="active" href="/"><span class="ico">⌂</span><span>Главная</span></a>
          <a href="/"><span class="ico">◉</span><span>Клиенты</span></a>
          <a href="#" data-status="wireguard"><span class="ico">≋</span><span>WG status</span></a>
          <a href="#" data-status="amneziawg"><span class="ico">✦</span><span>AWG status</span></a>
        </nav>

        <div class="neo-section">Управление</div>
        <nav class="neo-nav">
          <a href="/logout"><span class="ico">⇢</span><span>Выход</span></a>
        </nav>
      `;
      document.body.prepend(sidebar);
    }

    const wrap = document.querySelector('.wrap');
    if (wrap && !document.querySelector('.neo-topbar')) {
      const oldH1 = wrap.querySelector('h1');
      const title = oldH1 ? oldH1.textContent.trim() : '3WG Core';
      if (oldH1) oldH1.remove();

      const top = document.createElement('div');
      top.className = 'neo-topbar';
      top.innerHTML = `
        <div class="neo-title">
          <div class="neo-title-badge neo-pulse">3WG</div>
          <div>
            <h1>${title}</h1>
            <div class="muted">WireGuard & AmneziaWG Management Platform</div>
          </div>
        </div>
        <div class="neo-top-actions">
          <button class="neo-round" title="WG status" data-status="wireguard">WG</button>
          <button class="neo-round" title="AWG status" data-status="amneziawg">AWG</button>
          <a class="neo-round" title="Logout" href="/logout">⇢</a>
        </div>
      `;
      wrap.prepend(top);
    }

    function iconize() {
      document.querySelectorAll('a.btn, button.btn').forEach(function (el) {
        const text = (el.textContent || '').trim().toLowerCase();

        if (text.includes('открыть')) {
          el.classList.add('icon-btn', 'icon-open');
          el.setAttribute('title', 'Открыть');
          el.innerHTML = '↗';
        }

        if (text.includes('удалить')) {
          el.classList.add('icon-btn', 'icon-delete');
          el.setAttribute('title', 'Удалить');
          el.innerHTML = '🗑';
        }

        if (text.includes('wg show')) {
          el.classList.add('icon-btn', 'icon-status');
          el.setAttribute('title', 'WG status');
          el.innerHTML = 'WG';
        }

        if (text.includes('awg show')) {
          el.classList.add('icon-btn', 'icon-status');
          el.setAttribute('title', 'AWG status');
          el.innerHTML = 'AWG';
        }
      });

      document.querySelectorAll('button[type="submit"]').forEach(function (el) {
        const text = (el.textContent || '').trim().toLowerCase();
        if (text.includes('создать peer')) {
          el.innerHTML = '＋ Создать клиента';
        }
      });
    }

    iconize();

    document.addEventListener('click', function (e) {
      const statusBtn = e.target.closest('[data-status]');
      if (!statusBtn) return;

      e.preventDefault();
      const protocol = statusBtn.getAttribute('data-status');

      if (typeof openStatusModal === 'function') {
        openStatusModal(protocol);
      } else {
        window.location.href = '/raw/' + protocol;
      }
    });
  });
})();
""", media_type="application/javascript")


# =========================
# 3WG INLINE THEME OVERRIDE V4
# =========================

def page(title: str, body: str) -> str:
    title_esc = html.escape(title)

    try:
        clean_body = re.sub(r'^\s*<h1>.*?</h1>\s*', '', body, count=1, flags=re.S)
    except Exception:
        clean_body = body

    template = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {
  --bg:#070707;
  --bg2:#0a0a0a;
  --sidebar:#070707;
  --card:#0d0d0d;
  --card2:#0d1622;
  --line:#262626;
  --line2:#334357;
  --text:#ffffff;
  --muted:#8795aa;
  --muted2:#5f6d80;
  --green:#c8ff00;
  --cyan:#ff8c00;
  --orange:#ff8c00;
  --red:#ff5b73;
  --redbg:#4a121d;
}

* {
  box-sizing:border-box;
}

html, body {
  margin:0;
  min-height:100vh;
  background:
    radial-gradient(circle at 24% -10%, rgba(255,140,0,.10), transparent 30%),
    radial-gradient(circle at 100% 0%, rgba(200,255,0,.07), transparent 28%),
    linear-gradient(180deg, #070707, #0a0a0a);
  color:var(--text);
  font-family:Inter, Arial, sans-serif;
}

a {
  color:inherit;
}

.neo-sidebar {
  position:fixed;
  left:0;
  top:0;
  bottom:0;
  width:238px;
  background:
    linear-gradient(180deg, rgba(8,14,22,.98), rgba(5,9,15,.98)),
    radial-gradient(circle at 40% 0%, rgba(255,140,0,.10), transparent 38%);
  border-right:1px solid rgba(51,67,87,.75);
  padding:18px 14px;
  z-index:1000;
  box-shadow:18px 0 60px rgba(0,0,0,.28);
}

.neo-brand {
  display:flex;
  align-items:center;
  gap:12px;
  padding:7px 8px 22px;
  margin-bottom:16px;
  border-bottom:1px dashed rgba(255,140,0,.18);
}

.neo-logo {
  width:38px;
  height:38px;
  display:grid;
  place-items:center;
  border-radius:13px;
  background:rgba(200,255,0,.10);
  color:var(--green);
  border:1px solid rgba(200,255,0,.34);
  font-weight:900;
  box-shadow:0 0 24px rgba(200,255,0,.14);
}

.neo-brand-title {
  font-size:22px;
  font-weight:900;
  letter-spacing:.05em;
}

.neo-brand-sub {
  font-size:11px;
  color:var(--muted);
  margin-top:2px;
}

.neo-section {
  margin:18px 8px 8px;
  color:var(--muted2);
  font-size:11px;
  font-weight:900;
  text-transform:uppercase;
  letter-spacing:.16em;
}

.neo-nav a {
  min-height:40px;
  display:flex;
  align-items:center;
  gap:11px;
  padding:0 12px;
  margin-bottom:5px;
  border-radius:12px;
  text-decoration:none;
  color:#b8c5d8;
  font-size:14px;
  font-weight:700;
  border:1px solid transparent;
}

.neo-nav a:hover,
.neo-nav a.active {
  background:rgba(200,255,0,.08);
  border-color:rgba(200,255,0,.22);
  color:#eafff7;
}

.neo-nav .ico {
  width:22px;
  text-align:center;
  color:var(--cyan);
}

.wrap {
  max-width:none !important;
  margin-left:238px !important;
  padding:22px 28px 44px !important;
}

.neo-topbar {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:18px;
  margin-bottom:18px;
}

.neo-title {
  display:flex;
  align-items:center;
  gap:13px;
}

.neo-title-icon {
  width:44px;
  height:44px;
  display:grid;
  place-items:center;
  border-radius:15px;
  background:rgba(255,140,0,.08);
  color:var(--cyan);
  border:1px solid rgba(255,140,0,.25);
  font-weight:900;
  box-shadow:0 0 24px rgba(255,140,0,.08);
}

.neo-title h1 {
  margin:0;
  font-size:25px;
  letter-spacing:.04em;
}

.neo-sub {
  color:var(--muted);
  font-size:13px;
  margin-top:3px;
}

.neo-actions {
  display:flex;
  align-items:center;
  gap:10px;
}

.neo-round {
  width:42px;
  height:42px;
  display:grid;
  place-items:center;
  border-radius:14px;
  background:rgba(17,26,38,.9);
  color:var(--text);
  border:1px solid rgba(51,67,87,.9);
  text-decoration:none;
  font-weight:900;
  cursor:pointer;
}

.neo-round:hover {
  background:rgba(255,140,0,.10);
  color:#67eaff;
}

h1 {
  font-size:25px;
}

h2 {
  font-size:20px;
  letter-spacing:.02em;
}

.card,
.stat,
.qrbox,
.st-card {
  background:
    linear-gradient(180deg, rgba(18,27,40,.95), rgba(12,19,29,.95)) !important;
  border:1px solid rgba(51,67,87,.75) !important;
  box-shadow:0 18px 70px rgba(0,0,0,.34) !important;
}

.card {
  border-radius:18px !important;
  padding:18px !important;
  margin-bottom:16px !important;
}

.grid {
  display:grid !important;
  grid-template-columns:repeat(4,minmax(170px,1fr)) !important;
  gap:12px !important;
  margin-bottom:16px !important;
}

.stat {
  min-height:78px;
  border-radius:15px !important;
  position:relative;
  overflow:hidden;
}

.stat::after {
  content:"";
  position:absolute;
  right:14px;
  bottom:12px;
  width:38px;
  height:38px;
  border-radius:13px;
  background:rgba(200,255,0,.08);
  border:1px solid rgba(200,255,0,.18);
}

.stat .n {
  color:var(--green) !important;
  font-size:24px !important;
  text-shadow:0 0 18px rgba(200,255,0,.22);
}

.stat .l {
  color:var(--muted) !important;
  font-size:12px !important;
}

input[type=text],
input[type=password],
input {
  background:#09111c !important;
  border:1px solid rgba(70,88,110,.80) !important;
  color:var(--text) !important;
  border-radius:12px !important;
  outline:none !important;
}

input:focus {
  border-color:rgba(255,140,0,.65) !important;
  box-shadow:0 0 0 4px rgba(255,140,0,.08) !important;
}

button,
.btn {
  border-radius:12px !important;
  font-weight:900 !important;
  transition:.15s ease;
}

button:hover,
.btn:hover {
  transform:translateY(-1px);
  filter:brightness(1.06);
}

table {
  width:100%;
  border-collapse:separate !important;
  border-spacing:0 8px !important;
  font-size:14px;
}

thead th {
  border-bottom:0 !important;
  color:#94a6bb !important;
  font-size:12px !important;
  text-transform:uppercase;
  letter-spacing:.04em;
  padding:9px 10px !important;
}

tbody tr {
  background:rgba(7,7,7,.68);
}

tbody tr:hover {
  background:rgba(14,26,39,.96) !important;
}

tbody td {
  border-top:1px solid rgba(51,67,87,.45) !important;
  border-bottom:1px solid rgba(51,67,87,.45) !important;
  padding:13px 10px !important;
  vertical-align:middle;
}

tbody td:first-child {
  border-left:1px solid rgba(51,67,87,.45);
  border-radius:12px 0 0 12px;
}

tbody td:last-child {
  border-right:1px solid rgba(51,67,87,.45);
  border-radius:0 12px 12px 0;
}

code {
  background:#070d15 !important;
  border:1px solid rgba(51,67,87,.72) !important;
  color:#e8f3ff !important;
  border-radius:9px !important;
  padding:3px 7px;
}

pre {
  background:#070d15 !important;
  border:1px solid rgba(51,67,87,.72) !important;
  border-radius:14px !important;
  padding:16px !important;
}

.muted {
  color:var(--muted) !important;
}

.ok {
  color:var(--green) !important;
}

.bad {
  color:var(--red) !important;
}

.proto {
  border-radius:999px !important;
  font-size:12px;
  letter-spacing:.03em;
  padding:5px 10px !important;
  font-weight:900;
}

.proto-awg {
  background:rgba(255,140,0,.11) !important;
  color:#42e4ff !important;
  border:1px solid rgba(255,140,0,.22);
}

.proto-wg {
  background:rgba(200,255,0,.11) !important;
  color:#55ffb5 !important;
  border:1px solid rgba(200,255,0,.22);
}

.dot {
  width:10px !important;
  height:10px !important;
  vertical-align:middle;
}

.dot-green {
  background:var(--green) !important;
  box-shadow:0 0 18px rgba(200,255,0,.62) !important;
}

.btn.icon-btn,
button.icon-btn {
  width:38px !important;
  height:38px !important;
  padding:0 !important;
  margin:0 4px !important;
  display:inline-grid !important;
  place-items:center !important;
  border-radius:13px !important;
  font-size:16px !important;
  line-height:1 !important;
  color:var(--text) !important;
  background:rgba(26,38,54,.95) !important;
  border:1px solid rgba(70,88,110,.82) !important;
  box-shadow:0 8px 22px rgba(0,0,0,.22);
  text-decoration:none !important;
}

.btn.icon-open {
  color:#111820 !important;
  background:var(--orange) !important;
  border-color:rgba(244,163,64,.75) !important;
}

.btn.icon-delete,
button.icon-delete {
  background:rgba(74,18,29,.95) !important;
  color:#ffd2d8 !important;
  border-color:rgba(255,91,115,.42) !important;
}

.btn.icon-status {
  background:rgba(255,140,0,.10) !important;
  color:#54e8ff !important;
  border-color:rgba(255,140,0,.28) !important;
}

.qrgrid {
  gap:16px !important;
}

.qrbox img {
  border-radius:16px !important;
  box-shadow:0 18px 60px rgba(0,0,0,.25);
}

.modal-bg {
  display:none;
  position:fixed;
  inset:0;
  background:rgba(0,0,0,.72);
  z-index:2000;
  padding:30px;
  overflow:auto;
}

.modal-bg.open {
  display:block;
}

.modal-window {
  max-width:1350px;
  margin:20px auto;
  background:#0a111b;
  border:1px solid rgba(51,67,87,.9);
  border-radius:22px;
  box-shadow:0 30px 100px rgba(0,0,0,.65);
  overflow:hidden;
}

.modal-head {
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:18px 22px;
  background:#111b29;
  border-bottom:1px solid var(--line);
}

.modal-body {
  padding:22px;
}

.modal-close {
  background:#263149;
  color:#fff;
  border:1px solid #3b465f;
  border-radius:10px;
  padding:8px 12px;
  cursor:pointer;
  font-weight:800;
}

.status-grid,
.mask-grid {
  gap:12px !important;
}

::-webkit-scrollbar {
  width:9px;
  height:9px;
}

::-webkit-scrollbar-thumb {
  background:#26364a;
  border-radius:999px;
}

::-webkit-scrollbar-track {
  background:#08101a;
}

@media(max-width:1000px) {
  .neo-sidebar {
    display:none;
  }

  .wrap {
    margin-left:0 !important;
    padding:16px !important;
  }

  .grid {
    grid-template-columns:1fr !important;
  }

  .neo-topbar {
    flex-direction:column;
    align-items:flex-start;
  }

  table {
    font-size:12px !important;
  }
}
</style>
</head>
<body>

<aside class="neo-sidebar">
  <div class="neo-brand">
    <div class="neo-logo">3</div>
    <div>
      <div class="neo-brand-title">3WG</div>
      <div class="neo-brand-sub">CORE PLATFORM</div>
    </div>
  </div>

  <div class="neo-section">Обзор</div>
  <nav class="neo-nav">
    <a class="active" href="/"><span class="ico">⌂</span><span>Главная</span></a>
    <a href="/"><span class="ico">◉</span><span>Клиенты</span></a>
    <a href="#" data-status="wireguard"><span class="ico">≋</span><span>WG status</span></a>
    <a href="#" data-status="amneziawg"><span class="ico">✦</span><span>AWG status</span></a>
  </nav>

  <div class="neo-section">Управление</div>
  <nav class="neo-nav">
    <a href="/logout"><span class="ico">⇢</span><span>Выход</span></a>
  </nav>
</aside>

<div class="wrap">
  <div class="neo-topbar">
    <div class="neo-title">
      <div class="neo-title-icon">3WG</div>
      <div>
        <h1>__TITLE__</h1>
        <div class="neo-sub">WireGuard & AmneziaWG Management Platform</div>
      </div>
    </div>

    <div class="neo-actions">
      <button class="neo-round" title="WG status" data-status="wireguard">WG</button>
      <button class="neo-round" title="AWG status" data-status="amneziawg">AWG</button>
      <a class="neo-round" title="Logout" href="/logout">⇢</a>
    </div>
  </div>

  __BODY__
</div>

<div id="statusModal" class="modal-bg">
  <div class="modal-window">
    <div class="modal-head">
      <b id="statusModalTitle">Статус</b>
      <button class="modal-close" onclick="closeStatusModal()">Закрыть</button>
    </div>
    <div id="statusModalBody" class="modal-body">Загрузка...</div>
  </div>
</div>

<script>
function closeStatusModal() {
  const modal = document.getElementById('statusModal');
  if (modal) modal.classList.remove('open');
}

async function openStatusModal(protocol) {
  const modal = document.getElementById('statusModal');
  const body = document.getElementById('statusModalBody');
  const title = document.getElementById('statusModalTitle');

  if (!modal || !body || !title) {
    window.location.href = '/raw/' + protocol;
    return;
  }

  title.textContent = protocol === 'amneziawg' ? 'AWG status' : 'WG status';
  body.innerHTML = '<p class="muted">Загрузка статуса...</p>';
  modal.classList.add('open');

  try {
    const r = await fetch('/status/' + protocol, {cache: 'no-store'});
    if (!r.ok) throw new Error('status endpoint failed');
    body.innerHTML = await r.text();
  } catch (e) {
    const r2 = await fetch('/raw/' + protocol, {cache: 'no-store'});
    const txt = await r2.text();
    body.innerHTML = '<pre>' + txt.replace(/[&<>"']/g, function(m) {
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]);
    }) + '</pre>';
  }
}

function iconizeButtons() {
  document.querySelectorAll('a.btn, button.btn').forEach(function(el) {
    const text = (el.textContent || '').trim().toLowerCase();

    if (text.includes('открыть')) {
      el.classList.add('icon-btn', 'icon-open');
      el.setAttribute('title', 'Открыть');
      el.innerHTML = '↗';
    }

    if (text.includes('удалить')) {
      el.classList.add('icon-btn', 'icon-delete');
      el.setAttribute('title', 'Удалить');
      el.innerHTML = '🗑';
    }

    if (text.includes('wg show')) {
      el.classList.add('icon-btn', 'icon-status');
      el.setAttribute('title', 'WG status');
      el.innerHTML = 'WG';
    }

    if (text.includes('awg show')) {
      el.classList.add('icon-btn', 'icon-status');
      el.setAttribute('title', 'AWG status');
      el.innerHTML = 'AWG';
    }
  });

  document.querySelectorAll('button[type="submit"]').forEach(function(el) {
    const text = (el.textContent || '').trim().toLowerCase();
    if (text.includes('создать peer')) {
      el.innerHTML = '＋ Создать клиента';
    }
  });
}

document.addEventListener('DOMContentLoaded', iconizeButtons);

document.addEventListener('click', function(e) {
  const statusBtn = e.target.closest('[data-status]');
  if (statusBtn) {
    e.preventDefault();
    openStatusModal(statusBtn.getAttribute('data-status'));
    return;
  }

  const rawLink = e.target.closest('a[href^="/raw/"]');
  if (rawLink) {
    e.preventDefault();
    const protocol = rawLink.getAttribute('href').split('/raw/')[1];
    openStatusModal(protocol);
  }
});

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeStatusModal();
});

const modal = document.getElementById('statusModal');
if (modal) {
  modal.addEventListener('click', function(e) {
    if (e.target.id === 'statusModal') closeStatusModal();
  });
}
</script>

</body>
</html>"""

    return template.replace("__TITLE__", title_esc).replace("__BODY__", clean_body)


# =========================
# 3WG UI V5 CLEAN OVERRIDE
# =========================

def page(title: str, body: str) -> str:
    title_esc = html.escape(title)

    try:
        clean_body = re.sub(r'^\s*<h1>.*?</h1>\s*', '', body, count=1, flags=re.S)
    except Exception:
        clean_body = body

    template = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1">

<style>
:root {
  --bg: #000000;
  --bg-2: #0b111a;
  --side: #070b11;
  --panel: #101821;
  --panel-2: #0c131c;
  --row: #09111a;
  --row-hover: #0e1925;
  --border: #243140;
  --border-2: #333333;
  --text: #ffffff;
  --muted: #8493a8;
  --muted-2: #5f6f82;
  --green: #19e99a;
  --cyan: #20d7ff;
  --orange: #f5a33b;
  --red: #f35e74;
  --red-bg: #35111a;
  --blue-bg: #101f32;
  --radius: 7px;
  --radius-sm: 5px;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(circle at 26% -12%, rgba(32, 215, 255, .07), transparent 30%),
    radial-gradient(circle at 100% 0%, rgba(25, 233, 154, .045), transparent 28%),
    linear-gradient(180deg, #070707, #091018);
  color: var(--text);
  font-family: Inter, "Segoe UI", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.35;
}

a {
  color: inherit;
}

.neo-sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: 218px;
  background: linear-gradient(180deg, rgba(8,13,20,.98), rgba(5,8,13,.98));
  border-right: 1px solid rgba(51,51,51,.65);
  z-index: 1000;
  padding: 14px 10px;
}

.neo-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px 16px;
  margin-bottom: 12px;
  border-bottom: 1px dashed rgba(32,215,255,.14);
}

.neo-logo {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: rgba(25,233,154,.09);
  color: var(--green);
  border: 1px solid rgba(25,233,154,.25);
  font-size: 13px;
  font-weight: 900;
}

.neo-brand-title {
  font-size: 20px;
  line-height: 1;
  font-weight: 900;
  letter-spacing: .03em;
}

.neo-brand-sub {
  font-size: 10px;
  color: var(--muted);
  margin-top: 3px;
  letter-spacing: .06em;
}

.neo-section {
  margin: 16px 7px 7px;
  color: var(--muted-2);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: .14em;
}

.neo-nav a {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  margin-bottom: 4px;
  border-radius: 6px;
  text-decoration: none;
  color: #b9c7d9;
  font-size: 13px;
  font-weight: 700;
  border: 1px solid transparent;
}

.neo-nav a:hover,
.neo-nav a.active {
  background: rgba(25,233,154,.065);
  border-color: rgba(25,233,154,.18);
  color: #f0fff9;
}

.neo-nav .ico {
  width: 18px;
  height: 18px;
  display: inline-grid;
  place-items: center;
  color: var(--cyan);
}

.neo-nav svg,
.neo-round svg,
.icon-btn svg {
  width: 16px;
  height: 16px;
  display: block;
  stroke: currentColor;
  stroke-width: 2;
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.wrap {
  max-width: none !important;
  margin-left: 218px !important;
  padding: 16px 22px 36px !important;
}

.neo-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}

.neo-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.neo-title-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: rgba(32,215,255,.07);
  color: var(--cyan);
  border: 1px solid rgba(32,215,255,.22);
  font-size: 11px;
  font-weight: 900;
}

.neo-title h1 {
  margin: 0;
  font-size: 22px;
  letter-spacing: .03em;
  line-height: 1;
}

.neo-sub {
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
}

.neo-actions {
  display: flex;
  align-items: center;
  gap: 7px;
}

.neo-round {
  height: 32px;
  min-width: 32px;
  padding: 0 9px;
  display: inline-grid;
  place-items: center;
  border-radius: 6px;
  background: rgba(16,24,33,.92);
  color: var(--text);
  border: 1px solid rgba(51,51,51,.85);
  text-decoration: none;
  font-weight: 900;
  font-size: 11px;
  cursor: pointer;
}

.neo-round:hover {
  background: rgba(32,215,255,.09);
  color: #67eaff;
}

h1 {
  font-size: 22px;
}

h2 {
  font-size: 18px !important;
  margin: 0 0 14px !important;
  letter-spacing: .01em;
}

.card,
.stat,
.qrbox,
.st-card {
  background: linear-gradient(180deg, rgba(16,24,33,.96), rgba(12,19,28,.96)) !important;
  border: 1px solid rgba(51,51,51,.72) !important;
  box-shadow: none !important;
}

.card {
  border-radius: var(--radius) !important;
  padding: 16px !important;
  margin-bottom: 14px !important;
}

.grid {
  display: grid !important;
  grid-template-columns: repeat(4, minmax(170px, 1fr)) !important;
  gap: 10px !important;
  margin-bottom: 14px !important;
}

.stat {
  min-height: 66px;
  border-radius: var(--radius) !important;
  position: relative;
  overflow: hidden;
  padding: 13px 14px !important;
}

.stat::after {
  content: "";
  position: absolute;
  right: 13px;
  top: 50%;
  transform: translateY(-50%);
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: rgba(25,233,154,.055);
  border: 1px solid rgba(25,233,154,.14);
}

.stat .n {
  color: var(--green) !important;
  font-size: 21px !important;
  line-height: 1 !important;
  text-shadow: none !important;
}

.stat .l {
  color: var(--muted) !important;
  font-size: 11px !important;
  margin-top: 8px !important;
}

input[type=text],
input[type=password],
input {
  height: 34px;
  background: #080f17 !important;
  border: 1px solid rgba(70,88,110,.76) !important;
  color: var(--text) !important;
  border-radius: 5px !important;
  outline: none !important;
  padding: 0 10px !important;
  font-size: 13px !important;
}

input[type=checkbox] {
  width: 14px;
  height: 14px;
  vertical-align: -2px;
}

input:focus {
  border-color: rgba(32,215,255,.62) !important;
  box-shadow: 0 0 0 2px rgba(32,215,255,.07) !important;
}

button,
.btn {
  border-radius: 6px !important;
  font-weight: 800 !important;
  transition: .12s ease;
  border: 1px solid transparent;
}

button:hover,
.btn:hover {
  transform: none !important;
  filter: brightness(1.06);
}

table {
  width: 100%;
  border-collapse: collapse !important;
  border-spacing: 0 !important;
  table-layout: fixed;
  font-size: 13px;
}

thead th {
  color: #94a6bb !important;
  font-size: 11px !important;
  text-transform: uppercase;
  letter-spacing: .045em;
  padding: 9px 9px !important;
  border-bottom: 1px solid rgba(51,51,51,.72) !important;
  white-space: nowrap;
}

tbody tr {
  background: transparent !important;
}

tbody tr:hover {
  background: rgba(14,25,37,.62) !important;
}

tbody td {
  border-bottom: 1px solid rgba(51,51,51,.48) !important;
  padding: 10px 9px !important;
  vertical-align: middle;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

tbody td:first-child {
  width: 54px;
}

tbody td:nth-child(2) {
  width: 210px;
  white-space: normal;
  overflow: visible;
}

tbody td:nth-child(3) {
  width: 120px;
}

tbody td:nth-child(4) {
  width: 120px;
}

tbody td:nth-child(5) {
  width: 115px;
}

tbody td:nth-child(6) {
  width: 190px;
}

tbody td:nth-child(7) {
  width: 165px;
}

tbody td:nth-last-child(1) {
  width: 96px;
  text-align: right;
  overflow: visible;
}

tbody td:nth-last-child(2),
tbody td:nth-last-child(3) {
  width: 105px;
}

code {
  background: #070d15 !important;
  border: 1px solid rgba(51,51,51,.72) !important;
  color: #e8f3ff !important;
  border-radius: 5px !important;
  padding: 2px 6px !important;
  font-size: 12px;
}

pre {
  background: #070d15 !important;
  border: 1px solid rgba(51,51,51,.72) !important;
  border-radius: 6px !important;
  padding: 12px !important;
  line-height: 1.45;
}

.muted {
  color: var(--muted) !important;
  font-size: 12px;
}

.ok {
  color: var(--green) !important;
  font-weight: 900 !important;
}

.bad {
  color: var(--red) !important;
}

.proto {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 82px;
  border-radius: 5px !important;
  font-size: 11px;
  letter-spacing: .02em;
  padding: 4px 8px !important;
  font-weight: 900;
}

.proto-awg {
  background: rgba(32,215,255,.10) !important;
  color: #42e4ff !important;
  border: 1px solid rgba(32,215,255,.20);
}

.proto-wg {
  background: rgba(25,233,154,.10) !important;
  color: #55ffb5 !important;
  border: 1px solid rgba(25,233,154,.20);
}

.dot {
  width: 8px !important;
  height: 8px !important;
  margin-right: 7px !important;
  vertical-align: 1px;
}

.dot-green {
  background: var(--green) !important;
  box-shadow: 0 0 10px rgba(25,233,154,.52) !important;
}

form[method="post"] {
  display: inline-block;
  margin: 0;
}

.btn.icon-btn,
button.icon-btn {
  width: 30px !important;
  height: 30px !important;
  padding: 0 !important;
  margin: 0 0 0 5px !important;
  display: inline-grid !important;
  place-items: center !important;
  border-radius: 6px !important;
  color: var(--text) !important;
  background: rgba(20,30,42,.95) !important;
  border: 1px solid rgba(70,88,110,.76) !important;
  text-decoration: none !important;
  vertical-align: middle;
}

.btn.icon-open {
  color: #111820 !important;
  background: var(--orange) !important;
  border-color: rgba(244,163,64,.65) !important;
}

.btn.icon-delete,
button.icon-delete {
  background: rgba(53,17,26,.95) !important;
  color: #ffd2d8 !important;
  border-color: rgba(243,94,116,.38) !important;
}

.btn.icon-status {
  background: rgba(32,215,255,.08) !important;
  color: #54e8ff !important;
  border-color: rgba(32,215,255,.25) !important;
  width: auto !important;
  min-width: 42px !important;
  padding: 0 8px !important;
  font-size: 11px !important;
}

.qrgrid {
  gap: 12px !important;
}

.qrbox {
  border-radius: 7px !important;
}

.qrbox img {
  border-radius: 6px !important;
  box-shadow: none !important;
}

.modal-bg {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.72);
  z-index: 2000;
  padding: 22px;
  overflow: auto;
}

.modal-bg.open {
  display: block;
}

.modal-window {
  max-width: 1280px;
  margin: 18px auto;
  background: #0a111a;
  border: 1px solid rgba(51,51,51,.9);
  border-radius: 8px;
  box-shadow: 0 20px 70px rgba(0,0,0,.56);
  overflow: hidden;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: #111a25;
  border-bottom: 1px solid var(--border);
}

.modal-head b {
  font-size: 16px;
}

.modal-body {
  padding: 16px;
}

.modal-close {
  background: #202d40;
  color: #fff;
  border: 1px solid #3b465f;
  border-radius: 5px;
  padding: 7px 10px;
  cursor: pointer;
  font-weight: 800;
}

.modal-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}

.modal-title-row h2 {
  margin-bottom: 6px !important;
}

.status-grid {
  display: grid !important;
  grid-template-columns: repeat(4, minmax(180px, 1fr)) !important;
  gap: 10px !important;
  margin-bottom: 14px !important;
}

.st-card {
  border-radius: 6px !important;
  padding: 12px !important;
}

.st-label {
  font-size: 10px !important;
  color: var(--muted) !important;
  text-transform: uppercase;
  letter-spacing: .08em;
}

.st-value {
  font-size: 14px !important;
  margin-top: 6px !important;
  word-break: break-all;
}

.mask-grid {
  display: grid !important;
  grid-template-columns: repeat(6, minmax(110px, 1fr)) !important;
  gap: 8px !important;
  margin-bottom: 14px !important;
}

.st-mini {
  border-radius: 5px !important;
  padding: 8px !important;
  background: #08111a !important;
  border: 1px solid rgba(51,51,51,.65) !important;
}

.st-mini span {
  color: var(--muted) !important;
  font-size: 10px !important;
}

.st-mini b {
  color: var(--cyan) !important;
  font-size: 12px !important;
}

.table-scroll {
  overflow-x: auto;
}

.raw-box {
  margin-top: 12px;
  background: #08111a !important;
  border: 1px solid rgba(51,51,51,.65) !important;
  border-radius: 6px !important;
  padding: 10px !important;
}

.raw-box summary {
  cursor: pointer;
  color: var(--cyan);
  font-weight: 800;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-thumb {
  background: #26364a;
  border-radius: 4px;
}

::-webkit-scrollbar-track {
  background: #08101a;
}

@media(max-width: 1050px) {
  .neo-sidebar {
    display: none;
  }

  .wrap {
    margin-left: 0 !important;
    padding: 12px !important;
  }

  .grid,
  .status-grid,
  .mask-grid {
    grid-template-columns: 1fr !important;
  }

  table {
    min-width: 1120px;
  }

  .card {
    overflow-x: auto;
  }
}

/* 3WG UI V6 QR DOWNLOAD FIX */

.qrgrid {
  display: grid !important;
  grid-template-columns: repeat(auto-fit, minmax(300px, 390px)) !important;
  gap: 14px !important;
  align-items: start !important;
}

.qrbox {
  width: 100% !important;
  max-width: 420px !important;
  border-radius: 6px !important;
  padding: 14px !important;
}

.qrbox h2 {
  font-size: 16px !important;
  margin-bottom: 5px !important;
}

.qrbox p {
  margin: 8px 0 !important;
}

.qrbox img {
  width: 320px !important;
  max-width: 100% !important;
  height: auto !important;
  display: block !important;
  padding: 8px !important;
  border-radius: 4px !important;
  background: #fff !important;
  box-shadow: none !important;
}

.qrbox a[href*="/qr/"] {
  display: none !important;
}

.qrbox a[href*="/download"] {
  min-height: 32px !important;
  display: inline-flex !important;
  align-items: center !important;
  gap: 8px !important;
  padding: 0 11px !important;
  border-radius: 5px !important;
  background: var(--orange) !important;
  color: #101720 !important;
  border: 1px solid rgba(244,163,64,.65) !important;
  font-size: 12px !important;
  font-weight: 900 !important;
  text-decoration: none !important;
}

.qrbox a[href*="/download"] svg {
  width: 15px !important;
  height: 15px !important;
  stroke: currentColor !important;
  stroke-width: 2 !important;
  fill: none !important;
  stroke-linecap: round !important;
  stroke-linejoin: round !important;
}

.card:has(.qrgrid) {
  overflow: visible !important;
}

pre {
  max-height: 460px !important;
  overflow: auto !important;
}


/* 3WG UI V7 QR PNG DOWNLOAD */

.qrbox a.qr-download-png,
.qrbox a[href*="/qr/"].qr-download-png {
  min-height: 32px !important;
  display: inline-flex !important;
  align-items: center !important;
  gap: 8px !important;
  padding: 0 11px !important;
  margin-left: 6px !important;
  border-radius: 5px !important;
  background: rgba(32,215,255,.10) !important;
  color: #54e8ff !important;
  border: 1px solid rgba(32,215,255,.28) !important;
  font-size: 12px !important;
  font-weight: 900 !important;
  text-decoration: none !important;
}

.qrbox a.qr-download-png svg {
  width: 15px !important;
  height: 15px !important;
  stroke: currentColor !important;
  stroke-width: 2 !important;
  fill: none !important;
  stroke-linecap: round !important;
  stroke-linejoin: round !important;
}

</style>
</head>

<body>

<aside class="neo-sidebar">
  <div class="neo-brand">
    <div class="neo-logo">3</div>
    <div>
      <div class="neo-brand-title">3WG</div>
      <div class="neo-brand-sub">CORE PLATFORM</div>
    </div>
  </div>

  <div class="neo-section">Обзор</div>
  <nav class="neo-nav">
    <a class="active" href="/">
      <span class="ico"><svg viewBox="0 0 24 24"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></svg></span>
      <span>Главная</span>
    </a>
    <a href="/">
      <span class="ico"><svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg></span>
      <span>Клиенты</span>
    </a>
    <a href="#" data-status="wireguard">
      <span class="ico"><svg viewBox="0 0 24 24"><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/></svg></span>
      <span>WG status</span>
    </a>
    <a href="#" data-status="amneziawg">
      <span class="ico"><svg viewBox="0 0 24 24"><path d="M12 2v20"/><path d="M2 12h20"/><path d="M5 5l14 14"/><path d="M19 5L5 19"/></svg></span>
      <span>AWG status</span>
    </a>
  </nav>

  <div class="neo-section">Управление</div>
  <nav class="neo-nav">
    <a href="/logout">
      <span class="ico"><svg viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg></span>
      <span>Выход</span>
    </a>
  </nav>
</aside>

<div class="wrap">
  <div class="neo-topbar">
    <div class="neo-title">
      <div class="neo-title-icon">3WG</div>
      <div>
        <h1>__TITLE__</h1>
        <div class="neo-sub">WireGuard & AmneziaWG Management Platform</div>
      </div>
    </div>

    <div class="neo-actions">
      <button class="neo-round" title="WG status" data-status="wireguard">WG</button>
      <button class="neo-round" title="AWG status" data-status="amneziawg">AWG</button>
      <a class="neo-round" title="Logout" href="/logout">
        <svg viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>
      </a>
    </div>
  </div>

  __BODY__
</div>

<div id="statusModal" class="modal-bg">
  <div class="modal-window">
    <div class="modal-head">
      <b id="statusModalTitle">Статус</b>
      <button class="modal-close" onclick="closeStatusModal()">Закрыть</button>
    </div>
    <div id="statusModalBody" class="modal-body">Загрузка...</div>
  </div>
</div>

<script>
const SVG_OPEN = '<svg viewBox="0 0 24 24"><path d="M7 17L17 7"/><path d="M8 7h9v9"/></svg>';
const SVG_TRASH = '<svg viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>';

function closeStatusModal() {
  const modal = document.getElementById('statusModal');
  if (modal) modal.classList.remove('open');
}

async function openStatusModal(protocol) {
  const modal = document.getElementById('statusModal');
  const body = document.getElementById('statusModalBody');
  const title = document.getElementById('statusModalTitle');

  if (!modal || !body || !title) {
    window.location.href = '/raw/' + protocol;
    return;
  }

  title.textContent = protocol === 'amneziawg' ? 'AWG status' : 'WG status';
  body.innerHTML = '<p class="muted">Загрузка статуса...</p>';
  modal.classList.add('open');

  try {
    const r = await fetch('/status/' + protocol, {cache: 'no-store'});
    if (!r.ok) throw new Error('status endpoint failed');
    body.innerHTML = await r.text();
  } catch (e) {
    const r2 = await fetch('/raw/' + protocol, {cache: 'no-store'});
    const txt = await r2.text();
    body.innerHTML = '<pre>' + txt.replace(/[&<>"']/g, function(m) {
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]);
    }) + '</pre>';
  }
}

function iconizeButtons() {
  document.querySelectorAll('a.btn, button.btn').forEach(function(el) {
    const text = (el.textContent || '').trim().toLowerCase();

    if (text.includes('открыть')) {
      el.classList.add('icon-btn', 'icon-open');
      el.setAttribute('title', 'Открыть');
      el.innerHTML = SVG_OPEN;
    }

    if (text.includes('удалить')) {
      el.classList.add('icon-btn', 'icon-delete');
      el.setAttribute('title', 'Удалить');
      el.innerHTML = SVG_TRASH;
    }

    if (text.includes('wg show')) {
      el.classList.add('icon-btn', 'icon-status');
      el.setAttribute('title', 'WG status');
      el.innerHTML = 'WG';
    }

    if (text.includes('awg show')) {
      el.classList.add('icon-btn', 'icon-status');
      el.setAttribute('title', 'AWG status');
      el.innerHTML = 'AWG';
    }
  });

  document.querySelectorAll('button[type="submit"]').forEach(function(el) {
    const text = (el.textContent || '').trim().toLowerCase();
    if (text.includes('создать peer')) {
      el.innerHTML = '＋ Создать клиента';
    }
  });
}

document.addEventListener('DOMContentLoaded', iconizeButtons);

document.addEventListener('click', function(e) {
  const statusBtn = e.target.closest('[data-status]');
  if (statusBtn) {
    e.preventDefault();
    openStatusModal(statusBtn.getAttribute('data-status'));
    return;
  }

  const rawLink = e.target.closest('a[href^="/raw/"]');
  if (rawLink) {
    e.preventDefault();
    const protocol = rawLink.getAttribute('href').split('/raw/')[1];
    openStatusModal(protocol);
  }
});

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeStatusModal();
});

const modal = document.getElementById('statusModal');
if (modal) {
  modal.addEventListener('click', function(e) {
    if (e.target.id === 'statusModal') closeStatusModal();
  });
}
</script>


<script>
// 3WG UI V6 QR DOWNLOAD FIX
(function () {
  const SVG_DOWNLOAD = '<svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>';

  function fixQrDownloadButtons() {
    document.querySelectorAll('.qrbox a[href*="/qr/"]').forEach(function (a) {
      a.remove();
    });

    document.querySelectorAll('.qrbox a[href*="/download"]').forEach(function (a) {
      const href = a.getAttribute('href') || '';
      let label = 'Скачать';

      if (href.includes('download-vpn')) {
        label = 'Скачать .vpn';
      } else if (href.includes('download')) {
        label = 'Скачать .conf';
      }

      a.setAttribute('download', '');
      a.innerHTML = SVG_DOWNLOAD + '<span>' + label + '</span>';
    });
  }

  document.addEventListener('DOMContentLoaded', fixQrDownloadButtons);
  setTimeout(fixQrDownloadButtons, 300);
})();
</script>


<script>
// 3WG UI V7 QR PNG DOWNLOAD
(function () {
  const SVG_QR_DOWNLOAD = '<svg viewBox="0 0 24 24"><path d="M3 3h7v7H3z"/><path d="M14 3h7v7h-7z"/><path d="M3 14h7v7H3z"/><path d="M14 14h2"/><path d="M20 14h1"/><path d="M14 18h7"/><path d="M18 14v7"/></svg>';

  function addQrDownloadButtons() {
    document.querySelectorAll('.qrbox').forEach(function (box) {
      const img = box.querySelector('img[src*="/client/"][src*="/qr/"]');
      if (!img) return;

      const src = (img.getAttribute('src') || '').split('?')[0];
      if (!src) return;

      const href = src + '/download';

      if (box.querySelector('a.qr-download-png[href="' + href + '"]')) {
        return;
      }

      const btn = document.createElement('a');
      btn.className = 'qr-download-png';
      btn.href = href;
      btn.setAttribute('download', '');
      btn.innerHTML = SVG_QR_DOWNLOAD + '<span>Скачать QR</span>';

      let place = box.querySelector('p:last-of-type');
      if (!place) {
        place = document.createElement('p');
        box.appendChild(place);
      }

      place.appendChild(btn);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    addQrDownloadButtons();

    // Старый фикс мог удалить QR-ссылки через setTimeout,
    // поэтому повторяем добавление после него.
    setTimeout(addQrDownloadButtons, 500);
    setTimeout(addQrDownloadButtons, 1000);
  });
})();
</script>

</body>
</html>"""

    return template.replace("__TITLE__", title_esc).replace("__BODY__", clean_body)


# =========================
# 3WG PROTOCOL GUARD V8
# =========================

def protocol_check(protocol: str):
    if protocol not in PROTOCOLS:
        return False, "unknown protocol"

    try:
        p = PROTOCOLS[protocol]
        c = dc().containers.get(p["container"])
        c.reload()

        if c.status != "running":
            return False, f"container {p['container']} is {c.status}"

        # Проверяем инструмент, конфиг и интерфейс.
        script = (
            f"command -v {shlex.quote(p['tool'])} >/dev/null 2>&1 && "
            f"test -f {shlex.quote(p['config_path'])} && "
            f"{shlex.quote(p['tool'])} show {shlex.quote(p['interface'])} >/dev/null 2>&1"
        )

        result = c.exec_run(["sh", "-lc", script])

        if result.exit_code != 0:
            return False, f"{p['title']} is not ready inside {p['container']}"

        return True, "ok"

    except Exception as e:
        return False, str(e)


def available_protocols():
    result = {}

    for protocol, p in PROTOCOLS.items():
        ok, msg = protocol_check(protocol)
        result[protocol] = {
            "available": ok,
            "message": msg,
            "title": p["title"],
            "container": p["container"],
            "interface": p["interface"],
            "port": p["port"],
        }

    return result


def protocol_error_html(protocol: str, msg: str):
    title = PROTOCOLS.get(protocol, {}).get("title", protocol)

    return f"""
<div class="card">
  <h2>{html.escape(title)} недоступен</h2>
  <p class="muted">Этот протокол не установлен или контейнер не запущен на текущей ноде.</p>
  <pre>{html.escape(msg)}</pre>
  <p>
    <a class="btn btn2" href="/">Назад</a>
  </p>
</div>
"""


def _drop_route(path: str, method: str):
    new_routes = []

    for r in app.router.routes:
        r_path = getattr(r, "path", None)
        r_methods = getattr(r, "methods", set()) or set()

        if r_path == path and method.upper() in r_methods:
            continue

        new_routes.append(r)

    app.router.routes[:] = new_routes


# Убираем старые маршруты, которые могли падать при отсутствии контейнера.
_drop_route("/clients", "POST")
_drop_route("/raw/{protocol}", "GET")
_drop_route("/status/{protocol}", "GET")


@app.get("/protocol-health")
def protocol_health(user=Depends(auth)):
    return available_protocols()


@app.get("/protocol-guard.js")
def protocol_guard_js():
    return PlainTextResponse(r"""
(function () {
  const STYLE_ID = 'protocol-guard-v8-style';

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;

    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .protocol-disabled {
        opacity: .42 !important;
        cursor: not-allowed !important;
      }

      .protocol-disabled input {
        cursor: not-allowed !important;
      }

      .protocol-badge-off {
        display: inline-flex;
        align-items: center;
        margin-left: 7px;
        padding: 2px 6px;
        border-radius: 4px;
        background: rgba(243,94,116,.10);
        border: 1px solid rgba(243,94,116,.28);
        color: #ff9cac;
        font-size: 10px;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: .04em;
      }

      .protocol-warning {
        margin: 10px 0 0;
        padding: 9px 10px;
        border-radius: 5px;
        background: rgba(245,163,59,.08);
        border: 1px solid rgba(245,163,59,.22);
        color: #ffc980;
        font-size: 12px;
        max-width: 760px;
      }

      [data-protocol-unavailable="1"] {
        opacity: .45 !important;
        pointer-events: none !important;
      }
    `;
    document.head.appendChild(style);
  }

  async function loadHealth() {
    const r = await fetch('/protocol-health', {cache: 'no-store'});
    if (!r.ok) throw new Error('protocol-health failed');
    return await r.json();
  }

  function findProtocolCheckbox(protocol) {
    return document.querySelector('input[name="protocol"][value="' + protocol + '"]');
  }

  function disableProtocol(protocol, info) {
    const cb = findProtocolCheckbox(protocol);
    if (!cb) return;

    cb.checked = false;
    cb.disabled = true;

    const label = cb.closest('label') || cb.parentElement;
    if (label) {
      label.classList.add('protocol-disabled');
      label.title = info.message || 'protocol unavailable';

      if (!label.querySelector('.protocol-badge-off')) {
        const badge = document.createElement('span');
        badge.className = 'protocol-badge-off';
        badge.textContent = 'не установлен';
        label.appendChild(badge);
      }
    }
  }

  function enableProtocol(protocol) {
    const cb = findProtocolCheckbox(protocol);
    if (!cb) return;

    cb.disabled = false;

    const label = cb.closest('label') || cb.parentElement;
    if (label) {
      label.classList.remove('protocol-disabled');
      label.title = '';

      const badge = label.querySelector('.protocol-badge-off');
      if (badge) badge.remove();
    }
  }

  function addWarning(health) {
    const form = document.querySelector('form[action="/clients"]');
    if (!form) return;

    const old = form.querySelector('.protocol-warning');
    if (old) old.remove();

    const unavailable = [];

    Object.keys(health).forEach(function (protocol) {
      if (!health[protocol].available) {
        unavailable.push(health[protocol].title + ': ' + health[protocol].message);
      }
    });

    if (!unavailable.length) return;

    const div = document.createElement('div');
    div.className = 'protocol-warning';
    div.innerHTML = '<b>Внимание:</b> на этой ноде доступны не все протоколы.<br>' +
      unavailable.map(function (x) {
        return '• ' + x;
      }).join('<br>');

    form.appendChild(div);
  }

  function guardStatusButtons(health) {
    Object.keys(health).forEach(function (protocol) {
      const available = health[protocol].available;

      document.querySelectorAll('[data-status="' + protocol + '"]').forEach(function (el) {
        if (!available) {
          el.setAttribute('data-protocol-unavailable', '1');
          el.title = health[protocol].message || 'protocol unavailable';
        } else {
          el.removeAttribute('data-protocol-unavailable');
          el.title = '';
        }
      });
    });
  }

  async function applyProtocolGuard() {
    injectStyle();

    try {
      const health = await loadHealth();

      Object.keys(health).forEach(function (protocol) {
        if (health[protocol].available) {
          enableProtocol(protocol);
        } else {
          disableProtocol(protocol, health[protocol]);
        }
      });

      addWarning(health);
      guardStatusButtons(health);

      const createBtn = document.querySelector('form[action="/clients"] button[type="submit"]');
      const anyAvailable = Object.keys(health).some(function (p) {
        return health[p].available;
      });

      if (createBtn) {
        createBtn.disabled = !anyAvailable;
        if (!anyAvailable) {
          createBtn.textContent = 'Нет доступных протоколов';
        }
      }

    } catch (e) {
      console.warn('protocol guard failed', e);
    }
  }

  document.addEventListener('DOMContentLoaded', applyProtocolGuard);
  setTimeout(applyProtocolGuard, 500);
})();
""", media_type="application/javascript")


# Оборачиваем page(), чтобы подключить protocol guard JS ко всем страницам.
try:
    _page_before_protocol_guard_v8 = page

    def page(title: str, body: str) -> str:
        doc = _page_before_protocol_guard_v8(title, body)

        if "/protocol-guard.js" not in doc:
            doc = doc.replace("</body>", '<script src="/protocol-guard.js?v=8"></script>\n</body>')

        return doc

except NameError:
    pass


@app.post("/clients")
async def create_clients_guarded(request: Request, user=Depends(auth)):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    selected_protocols = form.getlist("protocol")

    if not name:
        return HTMLResponse(
            page("Ошибка", "<h1>Пустое имя</h1><a class='btn' href='/'>Назад</a>"),
            status_code=400,
        )

    if not selected_protocols:
        return HTMLResponse(
            page("Ошибка", "<h1>Не выбран протокол</h1><p class='muted'>На этой ноде может быть установлен только один протокол.</p><a class='btn' href='/'>Назад</a>"),
            status_code=400,
        )

    health = available_protocols()

    available_selected = []
    unavailable_selected = []

    for protocol in selected_protocols:
        if protocol not in PROTOCOLS:
            continue

        if health.get(protocol, {}).get("available"):
            available_selected.append(protocol)
        else:
            unavailable_selected.append((protocol, health.get(protocol, {}).get("message", "unavailable")))

    if not available_selected:
        msg = "\n".join([f"{p}: {m}" for p, m in unavailable_selected]) or "Нет доступных протоколов"
        return HTMLResponse(
            page("Протокол недоступен", f"<h1>Протокол недоступен</h1><pre>{html.escape(msg)}</pre><a class='btn' href='/'>Назад</a>"),
            status_code=400,
        )

    created = []

    try:
        for protocol in available_selected:
            created.append(create_client(name, protocol))

    except Exception as e:
        return HTMLResponse(
            page("Ошибка создания", f"<h1>Ошибка создания</h1><pre>{html.escape(str(e))}</pre><a class='btn' href='/'>Назад</a>"),
            status_code=500,
        )

    if created:
        return RedirectResponse(f"/client/{created[-1]}", status_code=303)

    return RedirectResponse("/", status_code=303)


@app.get("/raw/{protocol}")
def raw_guarded(protocol: str, user=Depends(auth)):
    if protocol not in PROTOCOLS:
        return PlainTextResponse("Unknown protocol", status_code=404)

    ok, msg = protocol_check(protocol)

    if not ok:
        return PlainTextResponse(f"{PROTOCOLS[protocol]['title']} unavailable:\n{msg}", status_code=404)

    p = proto(protocol)
    out = exec_c(p["container"], [p["tool"], "show", p["interface"]])
    return PlainTextResponse(out)


@app.get("/status/{protocol}", response_class=HTMLResponse)
def pretty_status_guarded(protocol: str, user=Depends(auth)):
    if protocol not in PROTOCOLS:
        return HTMLResponse("<h2>Unknown protocol</h2>", status_code=404)

    ok, msg = protocol_check(protocol)

    if not ok:
        return HTMLResponse(protocol_error_html(protocol, msg), status_code=200)

    try:
        if "render_pretty_status" in globals():
            return HTMLResponse(render_pretty_status(protocol))

        p = proto(protocol)
        out = exec_c(p["container"], [p["tool"], "show", p["interface"]])
        return HTMLResponse(f"<pre>{html.escape(out)}</pre>")

    except Exception as e:
        return HTMLResponse(protocol_error_html(protocol, str(e)), status_code=200)


# =========================
# 3WG PROTOCOL UI CLEANUP V9
# =========================

try:
    _page_before_protocol_ui_cleanup_v9 = page

    def page(title: str, body: str) -> str:
        doc = _page_before_protocol_ui_cleanup_v9(title, body)

        # Убираем страшные backend-ошибки из формы создания.
        doc = re.sub(
            r"<p\s+class=['\"]bad['\"]>\s*(wireguard|amneziawg):.*?</p>",
            "",
            doc,
            flags=re.S | re.I,
        )

        css = r"""
<style id="protocol-ui-cleanup-v9">
form[action="/clients"] {
  max-width: 760px;
}

form[action="/clients"] p {
  margin: 10px 0 !important;
}

form[action="/clients"] label {
  display: inline-flex !important;
  align-items: center !important;
  gap: 7px !important;
  min-height: 28px !important;
  margin-right: 14px !important;
  color: #d8e5f5 !important;
  font-size: 13px !important;
  line-height: 1 !important;
}

form[action="/clients"] input[type="checkbox"] {
  margin: 0 !important;
}

form[action="/clients"] button[type="submit"] {
  min-height: 34px !important;
  padding: 0 14px !important;
  background: #f5a33b !important;
  color: #101720 !important;
  border: 1px solid rgba(245,163,59,.65) !important;
  border-radius: 5px !important;
  font-size: 13px !important;
  font-weight: 900 !important;
}

.protocol-disabled {
  opacity: .58 !important;
}

.protocol-disabled input {
  opacity: .55 !important;
}

.protocol-badge-off {
  display: inline-flex !important;
  align-items: center !important;
  height: 18px !important;
  padding: 0 6px !important;
  margin-left: 2px !important;
  border-radius: 4px !important;
  background: rgba(243,94,116,.10) !important;
  border: 1px solid rgba(243,94,116,.25) !important;
  color: #ff9cac !important;
  font-size: 10px !important;
  font-weight: 900 !important;
  letter-spacing: .03em !important;
  white-space: nowrap !important;
}

.protocol-warning {
  max-width: 760px !important;
  margin: 12px 0 0 !important;
  padding: 10px 12px !important;
  border-radius: 5px !important;
  background: rgba(245,163,59,.075) !important;
  border: 1px solid rgba(245,163,59,.24) !important;
  color: #ffc980 !important;
  font-size: 12px !important;
  line-height: 1.45 !important;
}

.protocol-warning b {
  color: #ffd79b !important;
}

.protocol-unavailable-hidden {
  display: none !important;
}

[data-protocol-unavailable="1"] {
  display: none !important;
}

.card .bad {
  display: none !important;
}

.neo-actions [data-protocol-unavailable="1"] {
  display: none !important;
}

.neo-nav [data-protocol-unavailable="1"] {
  display: none !important;
}

.card a[href="/raw/wireguard"].protocol-unavailable-hidden,
.card a[href="/raw/amneziawg"].protocol-unavailable-hidden {
  display: none !important;
}

tbody tr.protocol-row-unavailable {
  opacity: .52;
}

tbody tr.protocol-row-unavailable .ok {
  color: #8493a8 !important;
}

tbody tr.protocol-row-unavailable::after {
  content: "";
}
</style>
"""

        js = r"""
<script id="protocol-ui-cleanup-v9-js">
(function () {
  function protocolSelector(protocol) {
    return protocol === 'wireguard' ? '.proto-wg' : '.proto-awg';
  }

  function titleByProtocol(protocol) {
    return protocol === 'wireguard' ? 'WireGuard' : 'AmneziaWG';
  }

  function rawHref(protocol) {
    return '/raw/' + protocol;
  }

  async function getProtocolHealth() {
    const r = await fetch('/protocol-health', {cache: 'no-store'});
    if (!r.ok) throw new Error('protocol-health failed');
    return await r.json();
  }

  function cleanOldBackendErrors() {
    document.querySelectorAll('.bad').forEach(function (el) {
      const text = (el.textContent || '').toLowerCase();
      if (
        text.includes('no such container') ||
        text.includes('404 client error') ||
        text.includes('not found') && (text.includes('wireguard') || text.includes('amnezia'))
      ) {
        el.remove();
      }
    });
  }

  function updateWarning(health) {
    const form = document.querySelector('form[action="/clients"]');
    if (!form) return;

    const unavailable = [];
    const available = [];

    Object.keys(health).forEach(function (protocol) {
      if (health[protocol].available) {
        available.push(health[protocol].title || titleByProtocol(protocol));
      } else {
        unavailable.push(health[protocol].title || titleByProtocol(protocol));
      }
    });

    let warning = form.querySelector('.protocol-warning');

    if (!unavailable.length) {
      if (warning) warning.remove();
      return;
    }

    if (!warning) {
      warning = document.createElement('div');
      warning.className = 'protocol-warning';
      form.appendChild(warning);
    }

    if (available.length) {
      warning.innerHTML =
        '<b>На этой ноде доступен не весь набор протоколов.</b><br>' +
        'Доступно: <b>' + available.join(', ') + '</b><br>' +
        'Не установлено: ' + unavailable.join(', ');
    } else {
      warning.innerHTML =
        '<b>На этой ноде нет доступных VPN-протоколов.</b><br>' +
        'Проверь контейнеры Amnezia.';
    }
  }

  function updateCheckboxes(health) {
    Object.keys(health).forEach(function (protocol) {
      const cb = document.querySelector('input[name="protocol"][value="' + protocol + '"]');
      if (!cb) return;

      const label = cb.closest('label') || cb.parentElement;

      if (!health[protocol].available) {
        cb.checked = false;
        cb.disabled = true;

        if (label) {
          label.classList.add('protocol-disabled');
          label.title = health[protocol].message || 'protocol unavailable';

          if (!label.querySelector('.protocol-badge-off')) {
            const badge = document.createElement('span');
            badge.className = 'protocol-badge-off';
            badge.textContent = 'не установлен';
            label.appendChild(badge);
          }
        }
      } else {
        cb.disabled = false;

        if (label) {
          label.classList.remove('protocol-disabled');
          label.title = '';

          const badge = label.querySelector('.protocol-badge-off');
          if (badge) badge.remove();
        }
      }
    });
  }

  function hideUnavailableStatusButtons(health) {
    Object.keys(health).forEach(function (protocol) {
      const available = !!health[protocol].available;

      document.querySelectorAll('[data-status="' + protocol + '"]').forEach(function (el) {
        if (!available) {
          el.classList.add('protocol-unavailable-hidden');
          el.setAttribute('data-protocol-unavailable', '1');
        } else {
          el.classList.remove('protocol-unavailable-hidden');
          el.removeAttribute('data-protocol-unavailable');
        }
      });

      document.querySelectorAll('a[href="' + rawHref(protocol) + '"]').forEach(function (el) {
        if (!available) {
          el.classList.add('protocol-unavailable-hidden');
        } else {
          el.classList.remove('protocol-unavailable-hidden');
        }
      });
    });
  }

  function markUnavailableRows(health) {
    Object.keys(health).forEach(function (protocol) {
      const available = !!health[protocol].available;
      const selector = protocolSelector(protocol);

      document.querySelectorAll(selector).forEach(function (badge) {
        const tr = badge.closest('tr');
        if (!tr) return;

        if (!available) {
          tr.classList.add('protocol-row-unavailable');

          const statusCell = tr.querySelector('td:nth-child(5)');
          if (statusCell && !statusCell.dataset.protocolMarked) {
            statusCell.dataset.protocolMarked = '1';
            statusCell.innerHTML = '<span class="muted">протокол не установлен</span>';
          }
        } else {
          tr.classList.remove('protocol-row-unavailable');
        }
      });
    });
  }

  function updateCreateButton(health) {
    const btn = document.querySelector('form[action="/clients"] button[type="submit"]');
    if (!btn) return;

    const anyAvailable = Object.keys(health).some(function (p) {
      return health[p].available;
    });

    btn.disabled = !anyAvailable;

    if (!anyAvailable) {
      btn.textContent = 'Нет доступных протоколов';
    } else {
      btn.textContent = '＋ Создать клиента';
    }
  }

  async function applyCleanup() {
    try {
      cleanOldBackendErrors();

      const health = await getProtocolHealth();

      updateCheckboxes(health);
      updateWarning(health);
      hideUnavailableStatusButtons(health);
      markUnavailableRows(health);
      updateCreateButton(health);
      cleanOldBackendErrors();
    } catch (e) {
      console.warn('protocol cleanup failed', e);
      cleanOldBackendErrors();
    }
  }

  document.addEventListener('DOMContentLoaded', applyCleanup);
  setTimeout(applyCleanup, 300);
  setTimeout(applyCleanup, 900);
})();
</script>
"""

        if "protocol-ui-cleanup-v9" not in doc:
            doc = doc.replace("</head>", css + "\n</head>")

        if "protocol-ui-cleanup-v9-js" not in doc:
            doc = doc.replace("</body>", js + "\n</body>")

        return doc

except NameError:
    pass


# =========================
# 3WG NO-FLICKER SERVER SIDE UI V10
# =========================

def v10_drop_route(path: str, method: str):
    new_routes = []

    for r in app.router.routes:
        r_path = getattr(r, "path", None)
        r_methods = getattr(r, "methods", set()) or set()

        if r_path == path and method.upper() in r_methods:
            continue

        new_routes.append(r)

    app.router.routes[:] = new_routes


def v10_protocol_health():
    result = {}

    for protocol, p in PROTOCOLS.items():
        try:
            c = dc().containers.get(p["container"])
            c.reload()

            if c.status != "running":
                result[protocol] = {
                    "available": False,
                    "message": f"container {p['container']} is {c.status}",
                    "title": p["title"],
                }
                continue

            check_cmd = (
                f"command -v {shlex.quote(p['tool'])} >/dev/null 2>&1 && "
                f"test -f {shlex.quote(p['config_path'])} && "
                f"{shlex.quote(p['tool'])} show {shlex.quote(p['interface'])} >/dev/null 2>&1"
            )

            r = c.exec_run(["sh", "-lc", check_cmd])

            if r.exit_code == 0:
                result[protocol] = {
                    "available": True,
                    "message": "ok",
                    "title": p["title"],
                }
            else:
                result[protocol] = {
                    "available": False,
                    "message": f"{p['title']} is not ready inside {p['container']}",
                    "title": p["title"],
                }

        except Exception:
            result[protocol] = {
                "available": False,
                "message": "не установлен",
                "title": p["title"],
            }

    return result


def v10_is_available(protocol: str, health=None) -> bool:
    health = health or v10_protocol_health()
    return bool(health.get(protocol, {}).get("available"))


def v10_proto_badge(protocol: str) -> str:
    p = PROTOCOLS[protocol]
    cls = "proto-awg" if protocol == "amneziawg" else "proto-wg"
    return f'<span class="proto {cls}">{html.escape(p["title"])}</span>'


def v10_action_buttons(c, available: bool) -> str:
    cid = c["id"]

    if available:
        delete_action = f"/client/{cid}/delete"
    else:
        delete_action = f"/client/{cid}/delete-local"

    return f"""
<a class="btn icon-btn icon-open" href="/client/{cid}" title="Открыть">
  <svg viewBox="0 0 24 24"><path d="M7 17L17 7"/><path d="M8 7h9v9"/></svg>
</a>
<form style="display:inline" method="post" action="{delete_action}" onsubmit="return confirm('Удалить клиента?')">
  <button class="btn icon-btn icon-delete" type="submit" title="Удалить">
    <svg viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
  </button>
</form>
"""


def v10_existing_peer_delete(protocol: str, pub: str) -> str:
    return f"""
<form style="display:inline" method="post" action="/peer/delete" onsubmit="return confirm('Удалить existing peer?')">
  <input type="hidden" name="protocol" value="{html.escape(protocol)}">
  <input type="hidden" name="public_key" value="{html.escape(pub)}">
  <button class="btn icon-btn icon-delete" type="submit" title="Удалить">
    <svg viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
  </button>
</form>
"""


def v10_checkbox(protocol: str, health: dict) -> str:
    p = PROTOCOLS[protocol]
    available = v10_is_available(protocol, health)

    if available:
        return f"""
<label>
  <input type="checkbox" name="protocol" value="{html.escape(protocol)}" checked>
  {html.escape(p["title"])}
</label>
"""

    return f"""
<label class="protocol-disabled" title="Протокол не установлен">
  <input type="checkbox" name="protocol" value="{html.escape(protocol)}" disabled>
  {html.escape(p["title"])}
  <span class="protocol-badge-off">не установлен</span>
</label>
"""


def v10_warning(health: dict) -> str:
    available = []
    unavailable = []

    for protocol, item in health.items():
        if item.get("available"):
            available.append(item.get("title", protocol))
        else:
            unavailable.append(item.get("title", protocol))

    if not unavailable:
        return ""

    if available:
        return f"""
<div class="protocol-warning">
  <b>На этой ноде доступен не весь набор протоколов.</b><br>
  Доступно: <b>{html.escape(", ".join(available))}</b><br>
  Не установлено: {html.escape(", ".join(unavailable))}
</div>
"""

    return """
<div class="protocol-warning">
  <b>На этой ноде нет доступных VPN-протоколов.</b><br>
  Проверь контейнеры Amnezia.
</div>
"""


try:
    v10_page_base = page

    def page(title: str, body: str) -> str:
        doc = v10_page_base(title, body)

        # Полностью убираем старые client-side guard'ы, которые вызывали мерцание.
        doc = re.sub(r'<script src="/protocol-guard\.js[^"]*"></script>\s*', '', doc, flags=re.S)
        doc = re.sub(r'<script id="protocol-ui-cleanup-v9-js">.*?</script>', '', doc, flags=re.S)
        doc = re.sub(r'<style id="protocol-ui-cleanup-v9">.*?</style>', '', doc, flags=re.S)
        doc = re.sub(r'<p\s+class=["\']bad["\']>.*?</p>', '', doc, flags=re.S | re.I)

        health = v10_protocol_health()

        hide_css = """
<style id="v10-no-flicker-css">
.bad {
  display: none !important;
}

.protocol-disabled {
  opacity: .58 !important;
}

.protocol-badge-off {
  display: inline-flex !important;
  align-items: center !important;
  height: 18px !important;
  padding: 0 6px !important;
  margin-left: 4px !important;
  border-radius: 4px !important;
  background: rgba(243,94,116,.10) !important;
  border: 1px solid rgba(243,94,116,.25) !important;
  color: #ff9cac !important;
  font-size: 10px !important;
  font-weight: 900 !important;
  white-space: nowrap !important;
}

.protocol-warning {
  max-width: 760px !important;
  margin: 12px 0 0 !important;
  padding: 10px 12px !important;
  border-radius: 5px !important;
  background: rgba(245,163,59,.075) !important;
  border: 1px solid rgba(245,163,59,.24) !important;
  color: #ffc980 !important;
  font-size: 12px !important;
  line-height: 1.45 !important;
}

.protocol-warning b {
  color: #ffd79b !important;
}
"""

        for protocol in PROTOCOLS:
            if not v10_is_available(protocol, health):
                hide_css += f"""
[data-status="{protocol}"],
a[href="/raw/{protocol}"] {{
  display: none !important;
}}
"""

        hide_css += "\n</style>\n"

        if "v10-no-flicker-css" not in doc:
            doc = doc.replace("</head>", hide_css + "\n</head>")

        return doc

except NameError:
    pass


@app.post("/client/{client_id}/delete-local")
def delete_client_local_route(client_id: int, user=Depends(auth)):
    c = load_client(client_id)

    try:
        with db() as conn:
            conn.execute(
                "UPDATE clients SET enabled = 0, deleted_at = ? WHERE id = ?",
                (int(time.time()), client_id),
            )
            conn.commit()

        conf_path = Path(c["config_path"])
        if conf_path.exists():
            conf_path.rename(conf_path.with_suffix(conf_path.suffix + f".deleted.{int(time.time())}"))

    except Exception as e:
        return HTMLResponse(
            page("Ошибка удаления", f"<h1>Ошибка удаления</h1><pre>{html.escape(str(e))}</pre><a class='btn' href='/'>Назад</a>"),
            status_code=500,
        )

    return RedirectResponse("/", status_code=303)


v10_drop_route("/", "GET")


@app.get("/", response_class=HTMLResponse)
def index_v10(user=Depends(auth)):
    health = v10_protocol_health()

    with db() as conn:
        try:
            rows_db = conn.execute(
                "SELECT * FROM clients WHERE COALESCE(deleted_at, 0) = 0 ORDER BY id DESC"
            ).fetchall()
        except Exception:
            rows_db = conn.execute(
                "SELECT * FROM clients ORDER BY id DESC"
            ).fetchall()

    live = {}

    for protocol in PROTOCOLS:
        if not v10_is_available(protocol, health):
            live[protocol] = {}
            continue

        try:
            live[protocol] = {x["public_key"]: x for x in live_peers(protocol)}
        except Exception:
            live[protocol] = {}

    rows = ""
    known = set()

    for c in rows_db:
        protocol = c["protocol"]

        if protocol not in PROTOCOLS:
            continue

        known.add((protocol, c["public_key"]))

        available = v10_is_available(protocol, health)
        lp = live.get(protocol, {}).get(c["public_key"]) if available else None

        if not available:
            status = '<span class="muted">протокол не установлен</span>'
            endpoint = "-"
            handshake = "-"
            rx = "0 B"
            tx = "0 B"
        elif lp:
            status = '<span class="dot dot-green"></span><span class="ok">ACTIVE</span>'
            endpoint = html.escape(lp["endpoint"])
            handshake = human_time(lp["latest_handshake"])
            rx = human_bytes(lp["rx"])
            tx = human_bytes(lp["tx"])
        else:
            status = '<span class="dot"></span><span class="muted">не подключался</span>'
            endpoint = "-"
            handshake = "-"
            rx = "0 B"
            tx = "0 B"

        rows += f"""
<tr>
<td>{c["id"]}</td>
<td><b>{html.escape(c["name"])}</b><br><span class="muted">создан панелью</span></td>
<td>{v10_proto_badge(protocol)}</td>
<td><code>{html.escape(c["ip_cidr"])}</code></td>
<td>{status}</td>
<td>{endpoint}</td>
<td>{handshake}</td>
<td>{rx}</td>
<td>{tx}</td>
<td>{v10_action_buttons(c, available)}</td>
</tr>
"""

    for protocol, peer_map in live.items():
        if not v10_is_available(protocol, health):
            continue

        for pub, lp in peer_map.items():
            if (protocol, pub) in known:
                continue

            pub_short = html.escape(pub[:12] + "..." + pub[-8:])
            endpoint = html.escape(lp["endpoint"])
            handshake = human_time(lp["latest_handshake"])
            rx = human_bytes(lp["rx"])
            tx = human_bytes(lp["tx"])

            if lp["endpoint"] != "(none)":
                status = '<span class="dot dot-green"></span><span class="ok">ACTIVE</span>'
            else:
                status = '<span class="dot"></span><span class="muted">не подключался</span>'

            rows += f"""
<tr>
<td>-</td>
<td><b>existing peer</b><br><code>{pub_short}</code></td>
<td>{v10_proto_badge(protocol)}</td>
<td><code>{html.escape(lp["allowed_ips"])}</code></td>
<td>{status}</td>
<td>{endpoint}</td>
<td>{handshake}</td>
<td>{rx}</td>
<td>{tx}</td>
<td>{v10_existing_peer_delete(protocol, pub)}</td>
</tr>
"""

    total = len(rows_db)
    live_count = sum(
        1
        for pm in live.values()
        for x in pm.values()
        if x.get("endpoint") != "(none)"
    )
    existing_count = sum(len(pm) for pm in live.values())

    body = f"""
<h1>3WG Core</h1>

<div class="grid">
  <div class="stat"><div class="n">{total}</div><div class="l">клиентов в панели</div></div>
  <div class="stat"><div class="n">{existing_count}</div><div class="l">peer'ов в контейнерах</div></div>
  <div class="stat"><div class="n">{live_count}</div><div class="l">сейчас в сети</div></div>
  <div class="stat"><div class="n">{sum(1 for p in health.values() if p.get("available"))}</div><div class="l">доступных протокола</div></div>
</div>

<div class="card">
<h2>Создать клиента</h2>
<form method="post" action="/clients">
<p><input type="text" name="name" placeholder="Например: Ivan iPhone" required></p>
<p>
{v10_checkbox("wireguard", health)}
{v10_checkbox("amneziawg", health)}
</p>
<button type="submit">＋ Создать клиента</button>
{v10_warning(health)}
</form>
<p class="muted">Endpoint host: <code>{html.escape(VPN_ENDPOINT_HOST)}</code></p>
</div>

<div class="card">
<h2>Клиенты</h2>
<table>
<thead>
<tr>
<th>ID</th>
<th>Имя пользователя</th>
<th>Протокол</th>
<th>Внутренний IP</th>
<th>Статус</th>
<th>Endpoint клиента</th>
<th>Последнее подключение</th>
<th>RX</th>
<th>TX</th>
<th></th>
</tr>
</thead>
<tbody>{rows if rows else '<tr><td colspan="10" class="muted">Пока нет клиентов</td></tr>'}</tbody>
</table>
</div>

<div class="card">
<h2>Статус</h2>
{('<a class="btn btn2" href="/raw/wireguard">WG</a>' if v10_is_available("wireguard", health) else '')}
{('<a class="btn btn2" href="/raw/amneziawg">AWG</a>' if v10_is_available("amneziawg", health) else '')}
</div>
"""

    return HTMLResponse(page("3WG Core", body))


# =========================
# 3WG ORANGE CREATE BUTTON V11
# =========================

try:
    _page_before_orange_button_v11 = page

    def page(title: str, body: str) -> str:
        doc = _page_before_orange_button_v11(title, body)

        css = """
<style id="orange-create-button-v11">
form[action="/clients"] button[type="submit"]:not(:disabled) {
  min-height: 34px !important;
  padding: 0 15px !important;
  background: #f5a33b !important;
  color: #101720 !important;
  border: 1px solid rgba(245,163,59,.75) !important;
  border-radius: 5px !important;
  font-size: 13px !important;
  font-weight: 900 !important;
  box-shadow: none !important;
  cursor: pointer !important;
}

form[action="/clients"] button[type="submit"]:not(:disabled):hover {
  background: #ffb24a !important;
  border-color: rgba(255,178,74,.9) !important;
  color: #0b111a !important;
}

form[action="/clients"] button[type="submit"]:disabled {
  min-height: 34px !important;
  padding: 0 15px !important;
  background: #202a36 !important;
  color: #7f8fa5 !important;
  border: 1px solid #344154 !important;
  border-radius: 5px !important;
  cursor: not-allowed !important;
}
</style>
"""

        if "orange-create-button-v11" not in doc:
            doc = doc.replace("</head>", css + "\n</head>")

        return doc

except NameError:
    pass


# =========================
# 3WG HIDE EXISTING PEERS V12
# =========================

HIDE_EXISTING_PEERS = os.getenv("HIDE_EXISTING_PEERS", "1").strip() not in ["0", "false", "False", "no", "NO"]


try:
    _page_before_hide_existing_peers_v12 = page

    def page(title: str, body: str) -> str:
        doc = _page_before_hide_existing_peers_v12(title, body)

        if HIDE_EXISTING_PEERS:
            # Убираем из основной таблицы строки технических peer'ов,
            # которые не были созданы панелью.
            doc = re.sub(
                r"\n?<tr>\s*<td>-</td>\s*<td><b>existing peer</b>.*?</tr>\s*",
                "\n",
                doc,
                flags=re.S | re.I,
            )

            # Если где-то остались строки с existing peer после предыдущих патчей.
            doc = re.sub(
                r"\n?<tr>.*?<b>existing peer</b>.*?</tr>\s*",
                "\n",
                doc,
                flags=re.S | re.I,
            )

        return doc

except NameError:
    pass



# === 3WG REACT FRONTEND START ===
from fastapi.responses import FileResponse as ReactFileResponse


@app.middleware('http')
async def react_frontend_middleware(request: Request, call_next):
    path = request.url.path
    dist = APP_DIR / 'frontend' / 'dist'
    index_file = dist / 'index.html'

    if path == '/logogrin.png':
        logo_file = APP_DIR / 'static' / 'logogrin.png'
        if logo_file.exists():
            return ReactFileResponse(
                logo_file,
                media_type='image/png',
                headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'},
            )

    if path.startswith('/assets/'):
        asset_file = dist / path.lstrip('/')
        if asset_file.exists() and asset_file.is_file():
            return ReactFileResponse(asset_file)

    if (path in ('/', '/login', '/ui', '/users', '/apikeys', '/monitoring', '/abuse', '/updates', '/audit', '/backups', '/migration', '/tools/system', '/tools/health', '/tools/ping', '/tools/traceroute') or re.match(r'^/client/\d+$', path) or re.match(r'^/status/(wireguard|amneziawg)$', path) or re.match(r'^/traffic/(wireguard|amneziawg)$', path)) and index_file.exists():
        return ReactFileResponse(
            index_file,
            media_type='text/html; charset=utf-8',
            headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'},
        )

    return await call_next(request)
# === 3WG REACT FRONTEND END ===

# === 3WG REACT API START ===
# JSON API for the future React frontend.
from fastapi.responses import JSONResponse


def api_is_authenticated(request: Request) -> bool:
    return api_current_user(request) is not None


def api_current_user(request: Request) -> dict | None:
    header_key = request.headers.get('x-api-key', '')
    validator = globals().get('api_key_valid')
    if header_key and callable(validator) and validator(header_key):
        return admin_user()
    cookie_token = request.cookies.get(SESSION_COOKIE)
    session_user = verify_user_session(cookie_token or "")
    if session_user:
        return session_user
    if cookie_token and secrets.compare_digest(cookie_token, make_session_token()):
        return admin_user()
    return None


def api_require_auth(request: Request):
    current = api_current_user(request)
    if current:
        return current
    raise HTTPException(status_code=401, detail='Unauthorized')


def api_require_admin(user=Depends(api_require_auth)):
    if user.get('is_admin'):
        return user
    raise HTTPException(status_code=403, detail='Admin only')


def api_actor_payload(user: dict | None) -> dict:
    user = user or {}
    username = str(user.get('username') or PANEL_USER)
    role = 'admin' if user.get('is_admin') else str(user.get('role') or 'user')
    actor_id = user.get('id')
    try:
        actor_id = int(actor_id) if actor_id is not None else None
    except (TypeError, ValueError):
        actor_id = None
    return {'id': actor_id, 'username': username, 'role': role}


def api_json_safe(value):
    if isinstance(value, dict):
        return {str(k): api_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [api_json_safe(v) for v in value]
    if isinstance(value, sqlite3.Row):
        return {k: api_json_safe(value[k]) for k in value.keys()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def api_audit_log(
    request: Request | None,
    user: dict | None,
    action: str,
    object_type: str,
    object_id=None,
    object_label: str | None = None,
    context: dict | None = None,
) -> None:
    actor = api_actor_payload(user)
    ip = None
    user_agent = None
    if request is not None:
        forwarded = request.headers.get('x-forwarded-for', '')
        ip = (forwarded.split(',')[0].strip() if forwarded else '') or (request.client.host if request.client else None)
        user_agent = request.headers.get('user-agent', '')[:300]
    try:
        payload = json.dumps(api_json_safe(context or {}), ensure_ascii=False, sort_keys=True)
    except Exception:
        payload = '{}'
    with db() as conn:
        conn.execute(
            """
            INSERT INTO audit_events(
                ts, actor_id, actor_username, actor_role, action, object_type,
                object_id, object_label, ip, user_agent, context
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(time.time()),
                actor['id'],
                actor['username'],
                actor['role'],
                str(action),
                str(object_type),
                None if object_id is None else str(object_id),
                None if object_label is None else str(object_label)[:200],
                ip,
                user_agent,
                payload,
            ),
        )
        conn.commit()


def api_audit_event_payload(row) -> dict:
    try:
        context = json.loads(row['context'] or '{}')
    except Exception:
        context = {}
    return {
        'id': row['id'],
        'ts': row['ts'],
        'actor': {
            'id': row['actor_id'],
            'username': row['actor_username'],
            'role': row['actor_role'],
        },
        'action': row['action'],
        'object_type': row['object_type'],
        'object_id': row['object_id'],
        'object_label': row['object_label'],
        'ip': row['ip'],
        'user_agent': row['user_agent'],
        'context': context,
    }


def api_manual_backup_dir() -> Path:
    path = BACKUPS_DIR / 'manual'
    path.mkdir(parents=True, exist_ok=True)
    return path


def api_migration_dir() -> Path:
    path = BACKUPS_DIR / 'migration'
    path.mkdir(parents=True, exist_ok=True)
    return path


def api_auto_backup_settings() -> dict:
    raw = panel_setting_get('backup_auto')
    settings = dict(AUTO_BACKUP_DEFAULTS)
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception:
            pass
    settings['enabled'] = bool(settings.get('enabled'))
    try:
        settings['interval_hours'] = int(settings.get('interval_hours', AUTO_BACKUP_DEFAULTS['interval_hours']))
    except (TypeError, ValueError):
        settings['interval_hours'] = AUTO_BACKUP_DEFAULTS['interval_hours']
    try:
        settings['keep_last'] = int(settings.get('keep_last', AUTO_BACKUP_DEFAULTS['keep_last']))
    except (TypeError, ValueError):
        settings['keep_last'] = AUTO_BACKUP_DEFAULTS['keep_last']
    try:
        settings['last_run_at'] = int(settings.get('last_run_at') or 0)
    except (TypeError, ValueError):
        settings['last_run_at'] = 0
    settings['interval_hours'] = min(max(settings['interval_hours'], 1), 168)
    settings['keep_last'] = min(max(settings['keep_last'], 1), 100)
    settings['next_run_at'] = (
        settings['last_run_at'] + settings['interval_hours'] * 3600
        if settings['enabled'] and settings['last_run_at']
        else 0
    )
    return settings


def api_save_auto_backup_settings(settings: dict) -> dict:
    interval_hours = min(max(int(settings.get('interval_hours', 24)), 1), 168)
    if interval_hours not in AUTO_BACKUP_INTERVALS:
        interval_hours = AUTO_BACKUP_DEFAULTS['interval_hours']
    payload = {
        'enabled': bool(settings.get('enabled')),
        'interval_hours': interval_hours,
        'keep_last': min(max(int(settings.get('keep_last', 7)), 1), 100),
        'last_run_at': int(settings.get('last_run_at') or 0),
    }
    panel_setting_set('backup_auto', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    return api_auto_backup_settings()


def api_prune_auto_backups(keep_last: int) -> list[str]:
    deleted = []
    auto_files = [
        p for p in sorted(api_manual_backup_dir().glob('3wg-panel.auto.*.tgz'), key=lambda x: x.stat().st_mtime, reverse=True)
        if p.is_file()
    ]
    for path in auto_files[max(1, keep_last):]:
        try:
            path.unlink()
            deleted.append(path.name)
        except FileNotFoundError:
            pass
    return deleted


def api_maybe_run_auto_backup(force: bool = False) -> dict | None:
    settings = api_auto_backup_settings()
    if not settings['enabled']:
        return None
    now = int(time.time())
    due_at = settings['last_run_at'] + settings['interval_hours'] * 3600 if settings['last_run_at'] else 0
    if not force and due_at and now < due_at:
        return None
    if not AUTO_BACKUP_LOCK.acquire(blocking=False):
        return None
    try:
        settings = api_auto_backup_settings()
        now = int(time.time())
        due_at = settings['last_run_at'] + settings['interval_hours'] * 3600 if settings['last_run_at'] else 0
        if not force and settings['last_run_at'] and now < due_at:
            return None
        path = api_create_backup_archive('auto')
        settings['last_run_at'] = int(path.stat().st_mtime)
        saved = api_save_auto_backup_settings(settings)
        deleted = api_prune_auto_backups(saved['keep_last'])
        return {'backup': api_backup_payload(path), 'deleted': deleted, 'auto': saved}
    finally:
        AUTO_BACKUP_LOCK.release()


def auto_backup_worker() -> None:
    while True:
        try:
            api_maybe_run_auto_backup()
        except Exception as e:
            print(f"Auto backup failed: {e}")
        time.sleep(60)


def start_auto_backup_worker() -> None:
    global AUTO_BACKUP_THREAD_STARTED
    if AUTO_BACKUP_THREAD_STARTED:
        return
    AUTO_BACKUP_THREAD_STARTED = True
    threading.Thread(target=auto_backup_worker, daemon=True).start()


def api_backup_path(name: str) -> Path:
    clean = Path(str(name or '')).name
    if not clean or clean != str(name or '') or not clean.endswith('.tgz'):
        raise HTTPException(status_code=400, detail='Некорректное имя backup')
    path = (api_manual_backup_dir() / clean).resolve()
    root = api_manual_backup_dir().resolve()
    if root not in path.parents:
        raise HTTPException(status_code=400, detail='Некорректный путь backup')
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail='Backup не найден')
    return path


def api_backup_payload(path: Path) -> dict:
    stat = path.stat()
    return {
        'name': path.name,
        'size': int(stat.st_size),
        'created_at': int(stat.st_mtime),
        'download_url': f'/api/backups/{path.name}/download',
    }


def api_list_backups() -> list[dict]:
    return [
        api_backup_payload(p)
        for p in sorted(api_manual_backup_dir().glob('*.tgz'), key=lambda x: x.stat().st_mtime, reverse=True)
        if p.is_file()
    ]


def api_migration_path(name: str) -> Path:
    clean = Path(str(name or '')).name
    if not clean or clean != str(name or '') or not clean.endswith('.tgz'):
        raise HTTPException(status_code=400, detail='Некорректное имя migration bundle')
    path = (api_migration_dir() / clean).resolve()
    root = api_migration_dir().resolve()
    if root not in path.parents:
        raise HTTPException(status_code=400, detail='Некорректный путь migration bundle')
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail='Migration bundle не найден')
    return path


def api_migration_payload(path: Path) -> dict:
    stat = path.stat()
    return {
        'name': path.name,
        'size': int(stat.st_size),
        'created_at': int(stat.st_mtime),
        'download_url': f'/api/migration/{path.name}/download',
    }


def api_list_migration_bundles() -> list[dict]:
    return [
        api_migration_payload(p)
        for p in sorted(api_migration_dir().glob('*.tgz'), key=lambda x: x.stat().st_mtime, reverse=True)
        if p.is_file()
    ]


def api_env_snapshot() -> bytes:
    keys = [
        'PANEL_USER', 'PANEL_PASSWORD', 'PANEL_CONTAINER',
        'PANEL_HOST', 'ENDPOINT_HOST', 'VPN_ENDPOINT_HOST', 'VPN_EGRESS_IP',
        'WG_CONTAINER', 'WG_INTERFACE', 'WG_PORT', 'WG_CONFIG_PATH', 'WG_NETWORK',
        'AWG_CONTAINER', 'AWG_INTERFACE', 'AWG_PORT', 'AWG_CONFIG_PATH', 'AWG_NETWORK',
        'DNS_SERVERS', 'SESSION_SECRET', 'HIDE_EXISTING_PEERS',
        'METRICS_ENABLED', 'METRICS_REQUIRE_TOKEN', 'METRICS_TOKEN',
        'TELEGRAM_ENABLED', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
        'UPDATE_RUNNER_ENABLED', 'UPDATE_RUNNER_SOCKET',
        'MIGRATION_RUNNER_ENABLED', 'MIGRATION_RUNNER_SOCKET',
    ]
    lines = []
    for key in keys:
        if key in os.environ:
            value = str(os.environ.get(key, '')).replace('\n', '')
            lines.append(f'{key}={value}')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def api_tar_add_bytes(tar: tarfile.TarFile, arcname: str, payload: bytes, mode: int = 0o600) -> None:
    info = tarfile.TarInfo(arcname)
    info.size = len(payload)
    info.mtime = int(time.time())
    info.mode = mode
    tar.addfile(info, io.BytesIO(payload))


def api_container_file_bytes(container_name: str, path: str) -> bytes | None:
    if not container_name or not path:
        return None
    try:
        container = dc().containers.get(container_name)
        stream, _ = container.get_archive(path)
        raw = b''.join(stream)
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as src_tar:
            member = next((m for m in src_tar.getmembers() if m.isfile()), None)
            if not member:
                return None
            extracted = src_tar.extractfile(member)
            return extracted.read() if extracted else None
    except Exception:
        return None


def api_create_migration_bundle(include_backups: bool = False) -> Path:
    migration_dir = api_migration_dir()
    ts = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())
    safe_host = re.sub(r'[^A-Za-z0-9_.-]+', '-', PANEL_HOST or VPN_ENDPOINT_HOST or socket.gethostname()).strip('-') or 'node'
    path = migration_dir / f'3wg-core.migration.{safe_host}.{ts}.tgz'
    manifest = {
        'product': '3WG Core',
        'kind': 'migration-bundle',
        'version': APP_VERSION,
        'created_at': int(time.time()),
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'legacy_endpoint_host': ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'include_backups': bool(include_backups),
        'includes': ['panel/.env', 'panel/data', 'panel/clients', 'protocols/*/config.conf'],
    }
    with tarfile.open(path, 'w:gz') as tar:
        api_tar_add_bytes(tar, 'metadata.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'), 0o600)
        api_tar_add_bytes(tar, 'panel/.env', api_env_snapshot(), 0o600)
        if DATA_DIR.exists():
            tar.add(DATA_DIR, arcname='panel/data', recursive=True)
        if CLIENTS_DIR.exists():
            tar.add(CLIENTS_DIR, arcname='panel/clients', recursive=True)
        if include_backups:
            for child in BACKUPS_DIR.iterdir() if BACKUPS_DIR.exists() else []:
                if child.name == 'migration':
                    continue
                tar.add(child, arcname=f'panel/backups/{child.name}', recursive=True)
        for protocol, p in PROTOCOLS.items():
            config = api_container_file_bytes(p['container'], p['config_path'])
            if config:
                api_tar_add_bytes(tar, f'protocols/{protocol}/config.conf', config, 0o600)
                api_tar_add_bytes(tar, f'protocols/{protocol}/container.txt', str(p['container']).encode('utf-8') + b'\n', 0o600)
                api_tar_add_bytes(tar, f'protocols/{protocol}/config_path.txt', str(p['config_path']).encode('utf-8') + b'\n', 0o600)
    path.chmod(0o600)
    return path


def api_create_backup_archive(reason: str = 'manual') -> Path:
    backup_dir = api_manual_backup_dir()
    ts = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())
    path = backup_dir / f'3wg-panel.{reason}.{ts}.tgz'
    manifest = {
        'app': '3wg-panel',
        'version': APP_VERSION,
        'created_at': int(time.time()),
        'reason': reason,
        'includes': ['data', 'clients'],
    }
    with tarfile.open(path, 'w:gz') as tar:
        if DATA_DIR.exists():
            tar.add(DATA_DIR, arcname='data', recursive=True)
        if CLIENTS_DIR.exists():
            tar.add(CLIENTS_DIR, arcname='clients', recursive=True)
        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
        info = tarfile.TarInfo('manifest.json')
        info.size = len(payload)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(payload))
    return path


def api_validate_backup_archive(path: Path) -> None:
    allowed_roots = {'data', 'clients', 'manifest.json'}
    try:
        with tarfile.open(path, 'r:gz') as tar:
            for member in tar.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or '..' in member_path.parts:
                    raise HTTPException(status_code=400, detail='Backup содержит небезопасный путь')
                if not member_path.parts or member_path.parts[0] not in allowed_roots:
                    raise HTTPException(status_code=400, detail='Backup содержит неизвестные данные')
    except tarfile.TarError as e:
        raise HTTPException(status_code=400, detail=f'Некорректный backup: {e}')


def api_clear_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def api_copy_directory_contents(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def api_diag_item(group: str, name: str, status: str, message: str, details: dict | None = None) -> dict:
    return {
        'group': group,
        'name': name,
        'status': status if status in ('ok', 'warn', 'fail') else 'warn',
        'message': message,
        'details': api_json_safe(details or {}),
    }


def api_node_diagnostics_payload() -> dict:
    checks = []

    try:
        docker_client = dc()
        docker_client.ping()
        checks.append(api_diag_item('Docker', 'Docker socket', 'ok', 'Docker API доступен'))
    except Exception as e:
        checks.append(api_diag_item('Docker', 'Docker socket', 'fail', 'Docker API недоступен', {'error': str(e)}))
        return {'ok': False, 'ts': int(time.time()), 'summary': {'ok': 0, 'warn': 0, 'fail': 1}, 'checks': checks}

    try:
        panel = docker_client.containers.get(PANEL_CONTAINER)
        status = getattr(panel, 'status', 'unknown') or 'unknown'
        checks.append(api_diag_item('Panel', PANEL_CONTAINER, 'ok' if status == 'running' else 'fail', f'Container status: {status}'))
    except Exception as e:
        checks.append(api_diag_item('Panel', PANEL_CONTAINER, 'fail', 'Контейнер панели не найден', {'error': str(e)}))

    for path, label in ((DATA_DIR, 'Data directory'), (CLIENTS_DIR, 'Clients directory'), (BACKUPS_DIR, 'Backups directory')):
        writable = path.exists() and os.access(path, os.W_OK)
        checks.append(api_diag_item('Storage', label, 'ok' if writable else 'fail', str(path), {'exists': path.exists(), 'writable': writable}))

    try:
        ips = sorted({item[4][0] for item in socket.getaddrinfo(PANEL_HOST, None)})
        checks.append(api_diag_item('Network', 'Panel DNS', 'ok', f'{PANEL_HOST} resolves', {'ips': ips}))
    except Exception as e:
        checks.append(api_diag_item('Network', 'Panel DNS', 'fail', f'{PANEL_HOST} не резолвится', {'error': str(e)}))

    try:
        ips = sorted({item[4][0] for item in socket.getaddrinfo(VPN_ENDPOINT_HOST, None)})
        checks.append(api_diag_item('Network', 'VPN endpoint DNS', 'ok', f'{VPN_ENDPOINT_HOST} resolves', {'ips': ips}))
    except Exception as e:
        checks.append(api_diag_item('Network', 'VPN endpoint DNS', 'fail', f'{VPN_ENDPOINT_HOST} не резолвится', {'error': str(e)}))

    caddy_found = False
    try:
        for container in docker_client.containers.list(all=True):
            name = (container.name or '').lower()
            if 'caddy' in name:
                caddy_found = True
                status = getattr(container, 'status', 'unknown') or 'unknown'
                checks.append(api_diag_item('Reverse proxy', container.name, 'ok' if status == 'running' else 'warn', f'Container status: {status}'))
        if not caddy_found:
            checks.append(api_diag_item('Reverse proxy', 'Caddy', 'warn', 'Caddy container не найден. Если reverse proxy стоит на host/systemd, это нормально.'))
    except Exception as e:
        checks.append(api_diag_item('Reverse proxy', 'Caddy', 'warn', 'Не удалось проверить Caddy', {'error': str(e)}))

    for protocol, p in PROTOCOLS.items():
        title = p['title']
        container = None
        try:
            container = docker_client.containers.get(p['container'])
            status = getattr(container, 'status', 'unknown') or 'unknown'
            checks.append(api_diag_item(title, 'Container', 'ok' if status == 'running' else 'fail', f"{p['container']}: {status}"))
        except Exception as e:
            checks.append(api_diag_item(title, 'Container', 'fail', f"Контейнер {p['container']} не найден", {'error': str(e)}))
            continue

        try:
            config_test = exec_c(p['container'], ['sh', '-lc', f"test -f {shlex.quote(p['config_path'])} && echo ok || echo missing"], check=False)
            checks.append(api_diag_item(title, 'Config path', 'ok' if config_test.strip() == 'ok' else 'fail', p['config_path']))
        except Exception as e:
            checks.append(api_diag_item(title, 'Config path', 'fail', 'Не удалось проверить config path', {'error': str(e)}))

        try:
            raw = exec_c(p['container'], [p['tool'], 'show', p['interface']], check=True)
            checks.append(api_diag_item(title, f"{p['tool']} show", 'ok', f"Interface {p['interface']} отвечает", {'output_head': raw[:400]}))
        except Exception as e:
            checks.append(api_diag_item(title, f"{p['tool']} show", 'fail', f"Interface {p['interface']} не отвечает", {'error': str(e)}))

        try:
            listen_port = interface_listen_port(protocol)
            published_port = docker_published_udp_port(protocol)
            ports = (container.attrs.get('NetworkSettings') or {}).get('Ports') or {}
            bindings = {k: v for k, v in ports.items() if str(k).endswith('/udp')}
            status = 'ok' if str(published_port).strip() else 'warn'
            checks.append(api_diag_item(title, 'UDP endpoint', status, f"{VPN_ENDPOINT_HOST}:{published_port}", {'listen_port': listen_port, 'configured_port': p['port'], 'bindings': bindings, 'vpn_egress_ip': VPN_EGRESS_IP}))
        except Exception as e:
            checks.append(api_diag_item(title, 'UDP endpoint', 'warn', 'Не удалось определить published UDP port', {'error': str(e)}))

    summary = {
        'ok': sum(1 for item in checks if item['status'] == 'ok'),
        'warn': sum(1 for item in checks if item['status'] == 'warn'),
        'fail': sum(1 for item in checks if item['status'] == 'fail'),
    }
    return {'ok': summary['fail'] == 0, 'ts': int(time.time()), 'summary': summary, 'checks': checks}


def api_user_where(user: dict, alias: str = 'c') -> tuple[str, list]:
    if user.get('is_admin'):
        return '', []
    return f" AND {alias}.owner_id = ?", [user.get('id')]


def api_user_peer_count(user: dict) -> int:
    if user.get('is_admin'):
        return 0
    with db() as conn:
        row = conn.execute(
            'SELECT COUNT(*) AS n FROM clients WHERE COALESCE(deleted_at, 0) = 0 AND owner_id = ?',
            (user.get('id'),),
        ).fetchone()
    return int(row['n'])


def api_user_quota(user: dict) -> dict:
    if user.get('is_admin'):
        return {'limited': False, 'limit': None, 'used': 0, 'remaining': None}
    limit = int(user.get('peer_limit') or 0)
    used = api_user_peer_count(user)
    return {'limited': True, 'limit': limit, 'used': used, 'remaining': max(0, limit - used)}


def api_parse_expires_at(value) -> int | None:
    if value in (None, '', False):
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Некорректный срок действия peer')
    if ts <= 0:
        return None
    if ts < int(time.time()) - 86400:
        raise HTTPException(status_code=400, detail='Срок действия уже в прошлом')
    return ts


def api_parse_user_expires_at(value) -> int | None:
    ts = api_parse_expires_at(value)
    if not ts:
        return None
    if ts > int(time.time()) + 366 * 86400:
        raise HTTPException(status_code=400, detail='Срок пользователя не может быть больше 1 года')
    return ts


def api_parse_traffic_limit(value) -> int:
    if value in (None, '', False):
        return 0
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Некорректный лимит трафика')
    if limit < 0:
        raise HTTPException(status_code=400, detail='Лимит трафика не может быть отрицательным')
    return limit


def api_expiration_payload(expires_at: int | None, enabled: bool) -> dict:
    if not expires_at:
        return {'enabled': False, 'expires_at': None, 'expired': False, 'seconds_left': None, 'label': 'без срока'}
    now = int(time.time())
    seconds_left = int(expires_at) - now
    expired = seconds_left <= 0
    if expired:
        label = 'истек'
    elif seconds_left < 86400:
        label = f"истекает через {max(1, seconds_left // 3600)} ч"
    else:
        label = f"истекает через {max(1, seconds_left // 86400)} д"
    return {
        'enabled': True,
        'expires_at': int(expires_at),
        'expired': expired,
        'seconds_left': seconds_left,
        'label': label,
        'active': enabled and not expired,
    }


def api_traffic_limit_payload(limit_bytes: int, live_peer: dict | None, counter: dict | None = None) -> dict:
    limit = max(0, int(limit_bytes or 0))
    rx = int((live_peer or {}).get('rx') or 0)
    tx = int((live_peer or {}).get('tx') or 0)
    if counter:
        rx = int(counter.get('rx_total') or 0)
        tx = int(counter.get('tx_total') or 0)
    used = rx + tx
    if limit <= 0:
        return {'enabled': False, 'limit_bytes': 0, 'used_bytes': used, 'rx_bytes': rx, 'tx_bytes': tx, 'remaining_bytes': None, 'percent': 0, 'exceeded': False, 'label': 'без лимита'}
    remaining = max(0, limit - used)
    percent = min(100, round((used / limit) * 100, 1)) if limit else 0
    return {
        'enabled': True,
        'limit_bytes': limit,
        'used_bytes': used,
        'rx_bytes': rx,
        'tx_bytes': tx,
        'remaining_bytes': remaining,
        'percent': percent,
        'exceeded': used >= limit,
        'label': f"{human_bytes(used)} / {human_bytes(limit)}",
    }


def api_user_traffic_totals(user_id: int) -> dict:
    with db() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(pt.rx_total), 0) AS rx_total,
                COALESCE(SUM(pt.tx_total), 0) AS tx_total
            FROM clients c
            LEFT JOIN peer_traffic_counters pt ON pt.client_id = c.id
            WHERE COALESCE(c.deleted_at, 0) = 0
              AND c.owner_id = ?
            """,
            (int(user_id),),
        ).fetchone()
    return {
        'rx_total': int(row['rx_total'] or 0),
        'tx_total': int(row['tx_total'] or 0),
    }


def api_user_traffic_limit_payload(user_id: int, limit_bytes: int) -> dict:
    return api_traffic_limit_payload(limit_bytes, None, api_user_traffic_totals(user_id))


def api_disable_expired_peers() -> int:
    now = int(time.time())
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, protocol, public_key, ip_cidr, expires_at
            FROM clients
            WHERE COALESCE(deleted_at, 0) = 0
              AND enabled = 1
              AND expires_at IS NOT NULL
              AND expires_at > 0
              AND expires_at <= ?
            """,
            (now,),
        ).fetchall()
    for row in rows:
        try:
            remove_peer(row['protocol'], row['public_key'])
            with db() as conn:
                conn.execute('UPDATE clients SET enabled = 0 WHERE id = ?', (int(row['id']),))
                conn.commit()
            api_audit_log(
                None,
                {'username': 'system', 'role': 'system', 'is_admin': True},
                'peer.expire',
                'peer',
                int(row['id']),
                row['name'],
                {'protocol': row['protocol'], 'ip_cidr': row['ip_cidr'], 'expires_at': int(row['expires_at'])},
            )
            telegram_notify(
                "peer отключён по сроку",
                [f"{row['name']} / {row['protocol']}", f"IP: {row['ip_cidr']}"],
            )
        except Exception as e:
            print(f"Failed to auto-disable expired peer {row['id']}: {e}")
    if rows:
        runtime_cache_clear()
    return len(rows)


def api_disable_traffic_limited_peers(live: dict, counters: dict | None = None) -> int:
    counters = counters if counters is not None else api_record_peer_traffic_counters(live)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, protocol, public_key, ip_cidr, traffic_limit_bytes
            FROM clients
            WHERE COALESCE(deleted_at, 0) = 0
              AND enabled = 1
              AND traffic_limit_bytes > 0
            """
        ).fetchall()
    disabled = 0
    for row in rows:
        lp = (live.get(row['protocol']) or {}).get(row['public_key'])
        counter = counters.get(int(row['id'])) if counters else None
        if not lp and not counter:
            continue
        if counter:
            used = int(counter.get('rx_total') or 0) + int(counter.get('tx_total') or 0)
        else:
            used = int(lp.get('rx') or 0) + int(lp.get('tx') or 0)
        limit = int(row['traffic_limit_bytes'] or 0)
        if used < limit:
            continue
        try:
            remove_peer(row['protocol'], row['public_key'])
            with db() as conn:
                conn.execute('UPDATE clients SET enabled = 0 WHERE id = ?', (int(row['id']),))
                conn.commit()
            disabled += 1
            api_audit_log(
                None,
                {'username': 'system', 'role': 'system', 'is_admin': True},
                'peer.traffic_limit',
                'peer',
                int(row['id']),
                row['name'],
                {'protocol': row['protocol'], 'ip_cidr': row['ip_cidr'], 'used_bytes': used, 'limit_bytes': limit},
            )
            telegram_notify(
                "peer отключён по лимиту трафика",
                [f"{row['name']} / {row['protocol']}", f"Использовано: {human_bytes(used)} из {human_bytes(limit)}"],
            )
        except Exception as e:
            print(f"Failed to auto-disable traffic-limited peer {row['id']}: {e}")
    if disabled:
        runtime_cache_clear()
    return disabled


def api_disable_user_traffic_limited_peers() -> int:
    with db() as conn:
        users = conn.execute(
            """
            SELECT id, username, traffic_limit_bytes
            FROM panel_users
            WHERE enabled = 1
              AND traffic_limit_bytes > 0
            """
        ).fetchall()
    disabled = 0
    for panel_user in users:
        limit = int(panel_user['traffic_limit_bytes'] or 0)
        traffic = api_user_traffic_limit_payload(int(panel_user['id']), limit)
        if not traffic['exceeded']:
            continue
        with db() as conn:
            peers = conn.execute(
                """
                SELECT id, name, protocol, public_key, ip_cidr
                FROM clients
                WHERE COALESCE(deleted_at, 0) = 0
                  AND enabled = 1
                  AND owner_id = ?
                """,
                (int(panel_user['id']),),
            ).fetchall()
        user_disabled = 0
        for row in peers:
            try:
                remove_peer(row['protocol'], row['public_key'])
                with db() as conn:
                    conn.execute('UPDATE clients SET enabled = 0 WHERE id = ?', (int(row['id']),))
                    conn.commit()
                disabled += 1
                user_disabled += 1
            except Exception as e:
                print(f"Failed to auto-disable user traffic-limited peer {row['id']}: {e}")
        if user_disabled:
            api_audit_log(
                None,
                {'username': 'system', 'role': 'system', 'is_admin': True},
                'user.traffic_limit',
                'panel_user',
                int(panel_user['id']),
                panel_user['username'],
                {
                    'disabled_peers': user_disabled,
                    'used_bytes': traffic['used_bytes'],
                    'limit_bytes': limit,
                },
            )
            telegram_notify(
                "пользователь превысил лимит трафика",
                [
                    f"Пользователь: {panel_user['username']}",
                    f"Отключено peer'ов: {user_disabled}",
                    f"Использовано: {human_bytes(traffic['used_bytes'])} из {human_bytes(limit)}",
                ],
            )
    if disabled:
        runtime_cache_clear()
    return disabled


def api_error(message: str, status_code: int = 400, **extra):
    payload = {'ok': False, 'error': message}
    payload.update(extra)
    return JSONResponse(payload, status_code=status_code)


def telegram_enabled() -> bool:
    value = panel_setting_get("telegram_enabled")
    if value is None:
        return TELEGRAM_ENABLED
    return value == "1"


def telegram_bot_token() -> str:
    return panel_setting_get("telegram_bot_token", TELEGRAM_BOT_TOKEN) or ""


def telegram_chat_id() -> str:
    return panel_setting_get("telegram_chat_id", TELEGRAM_CHAT_ID) or ""


def telegram_token_suffix() -> str:
    token = telegram_bot_token()
    return token[-6:] if token else ""


def telegram_configured() -> bool:
    return bool(telegram_bot_token() and telegram_chat_id())


def telegram_status_payload() -> dict:
    return {
        "ok": True,
        "enabled": telegram_enabled(),
        "configured": telegram_configured(),
        "chat_id": telegram_chat_id(),
        "token_suffix": telegram_token_suffix(),
        "env_token_present": bool(TELEGRAM_BOT_TOKEN),
        "env_chat_present": bool(TELEGRAM_CHAT_ID),
        "db_token_present": bool(panel_setting_get("telegram_bot_token", "")),
        "db_chat_present": bool(panel_setting_get("telegram_chat_id", "")),
    }


def telegram_send_message(title: str, lines: list[str] | None = None) -> bool:
    if not telegram_enabled() or not telegram_configured():
        return False
    text_lines = [f"3WG Core: {title}"]
    for line in lines or []:
        clean = str(line).strip()
        if clean:
            text_lines.append(clean)
    payload = json.dumps({
        "chat_id": telegram_chat_id(),
        "text": "\n".join(text_lines),
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{telegram_bot_token()}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=7) as resp:
            return 200 <= int(resp.status) < 300
    except Exception as e:
        print(f"Telegram notify failed: {e}")
        return False


def telegram_notify(title: str, lines: list[str] | None = None, wait: bool = False) -> bool:
    if wait:
        return telegram_send_message(title, lines)
    if not telegram_enabled() or not telegram_configured():
        return False
    threading.Thread(target=telegram_send_message, args=(title, lines), daemon=True).start()
    return True


async def api_read_payload(request: Request) -> dict:
    ctype = request.headers.get('content-type', '')
    if 'application/json' in ctype:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    try:
        form = await request.form()
        data = dict(form)
        if hasattr(form, 'getlist'):
            values = form.getlist('protocols') or form.getlist('protocol')
            if values:
                data['protocols'] = values
        return data
    except Exception:
        return {}


def api_protocol_state(protocol: str, include_raw: bool = False) -> dict:
    def load():
        p = proto(protocol)
        endpoint_port = docker_published_udp_port(protocol)
        item = {
            'protocol': protocol,
            'title': p['title'],
            'container': p['container'],
            'interface': p['interface'],
            'tool': p['tool'],
            'port': int(str(endpoint_port)),
            'configured_port': int(str(p['port'])),
            'panel_host': PANEL_HOST,
            'endpoint_host': VPN_ENDPOINT_HOST,
            'legacy_endpoint_host': ENDPOINT_HOST,
            'vpn_egress_ip': VPN_EGRESS_IP,
            'endpoint': f"{VPN_ENDPOINT_HOST}:{endpoint_port}",
            'network': p['network'],
            'available': False,
            'container_status': 'unknown',
            'reason': 'not checked',
        }
        try:
            container = dc().containers.get(p['container'])
            item['container_status'] = getattr(container, 'status', 'unknown') or 'unknown'
        except Exception as e:
            item['reason'] = 'container unavailable: ' + str(e)
            return item
        try:
            raw = exec_c(p['container'], [p['tool'], 'show', p['interface']], check=True)
            item['available'] = True
            item['reason'] = 'ok'
            item['raw'] = raw
        except Exception as e:
            item['reason'] = str(e)
        return item

    item = dict(cache_value(("protocol_state", protocol), RUNTIME_CACHE_TTL_SECONDS, load))
    if not include_raw:
        item.pop('raw', None)
    return item


def api_live_maps() -> tuple[dict, dict]:
    live = {}
    errors = {}
    for protocol in PROTOCOLS:
        try:
            live[protocol] = {x['public_key']: x for x in live_peers(protocol)}
        except Exception as e:
            live[protocol] = {}
            errors[protocol] = str(e)
    return live, errors


def api_protocol_traffic_totals(live: dict | None = None) -> dict:
    live = live if live is not None else api_live_maps()[0]
    totals = {}
    for protocol, p in PROTOCOLS.items():
        rows = live.get(protocol, {}) if live else {}
        rx = sum(int(peer.get('rx') or 0) for peer in rows.values())
        tx = sum(int(peer.get('tx') or 0) for peer in rows.values())
        totals[protocol] = {
            'protocol': protocol,
            'title': p['title'],
            'interface': p['interface'],
            'rx': rx,
            'tx': tx,
            'total': rx + tx,
        }
    return totals


def api_record_traffic_snapshot(live: dict | None = None, min_interval: int = 60) -> dict:
    now = int(time.time())
    totals = api_protocol_traffic_totals(live)
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traffic_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                protocol TEXT NOT NULL,
                interface TEXT NOT NULL,
                rx INTEGER NOT NULL,
                tx INTEGER NOT NULL
            )
        """)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_traffic_snapshots_protocol_ts ON traffic_snapshots(protocol, ts)')
        for protocol, item in totals.items():
            row = conn.execute(
                'SELECT ts, rx, tx FROM traffic_snapshots WHERE protocol = ? ORDER BY ts DESC LIMIT 1',
                (protocol,),
            ).fetchone()
            if row and int(row['ts']) > now - min_interval:
                continue
            conn.execute(
                'INSERT INTO traffic_snapshots(ts, protocol, interface, rx, tx) VALUES (?, ?, ?, ?, ?)',
                (now, protocol, item['interface'], int(item['rx']), int(item['tx'])),
            )
        conn.commit()
    return totals


def api_record_peer_traffic_counters(live: dict | None = None) -> dict[int, dict]:
    live = live if live is not None else api_live_maps()[0]
    now = int(time.time())
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, protocol, public_key
            FROM clients
            WHERE COALESCE(deleted_at, 0) = 0
            """
        ).fetchall()
        for row in rows:
            lp = (live.get(row['protocol']) or {}).get(row['public_key'])
            if not lp:
                continue
            rx = int(lp.get('rx') or 0)
            tx = int(lp.get('tx') or 0)
            current = conn.execute(
                'SELECT * FROM peer_traffic_counters WHERE client_id = ?',
                (int(row['id']),),
            ).fetchone()
            if current:
                last_rx = int(current['last_rx'] or 0)
                last_tx = int(current['last_tx'] or 0)
                rx_delta = rx - last_rx if rx >= last_rx else rx
                tx_delta = tx - last_tx if tx >= last_tx else tx
                conn.execute(
                    """
                    UPDATE peer_traffic_counters
                    SET protocol = ?, public_key = ?, rx_total = rx_total + ?, tx_total = tx_total + ?,
                        last_rx = ?, last_tx = ?, updated_at = ?
                    WHERE client_id = ?
                    """,
                    (row['protocol'], row['public_key'], max(0, rx_delta), max(0, tx_delta), rx, tx, now, int(row['id'])),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO peer_traffic_counters(client_id, protocol, public_key, rx_total, tx_total, last_rx, last_tx, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (int(row['id']), row['protocol'], row['public_key'], rx, tx, rx, tx, now),
                )
        conn.commit()
        counters = conn.execute('SELECT * FROM peer_traffic_counters').fetchall()
    return {
        int(row['client_id']): {
            'client_id': int(row['client_id']),
            'protocol': row['protocol'],
            'public_key': row['public_key'],
            'rx_total': int(row['rx_total']),
            'tx_total': int(row['tx_total']),
            'last_rx': int(row['last_rx']),
            'last_tx': int(row['last_tx']),
            'updated_at': int(row['updated_at']),
        }
        for row in counters
    }


def api_traffic_history_payload(protocol: str, days: int = 30) -> dict:
    if protocol not in PROTOCOLS:
        raise HTTPException(status_code=404, detail='Unknown protocol')
    days = max(1, min(int(days or 30), 90))
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    current = api_record_traffic_snapshot(live, min_interval=60).get(protocol)
    since = int(time.time()) - days * 86400
    with db() as conn:
        rows = conn.execute(
            'SELECT ts, rx, tx FROM traffic_snapshots WHERE protocol = ? AND ts >= ? ORDER BY ts ASC',
            (protocol, since),
        ).fetchall()
    buckets = {}
    for row in rows:
        day_ts = int(time.mktime(time.gmtime(int(row['ts']))[:3] + (0, 0, 0, 0, 0, 0)))
        item = buckets.setdefault(day_ts, {'day': day_ts, 'first_rx': int(row['rx']), 'first_tx': int(row['tx']), 'last_rx': int(row['rx']), 'last_tx': int(row['tx'])})
        item['last_rx'] = int(row['rx'])
        item['last_tx'] = int(row['tx'])
    today = int(time.mktime(time.gmtime(int(time.time()))[:3] + (0, 0, 0, 0, 0, 0)))
    series = []
    for i in range(days - 1, -1, -1):
        day = today - i * 86400
        item = buckets.get(day)
        rx = max(0, item['last_rx'] - item['first_rx']) if item else 0
        tx = max(0, item['last_tx'] - item['first_tx']) if item else 0
        series.append({'day': day, 'rx': rx, 'tx': tx, 'total': rx + tx})
    return {
        'ok': True,
        'protocol': protocol,
        'title': PROTOCOLS[protocol]['title'],
        'interface': PROTOCOLS[protocol]['interface'],
        'days': days,
        'current': current,
        'series': series,
        'month_total': sum(x['total'] for x in series),
        'note': 'История начинает накапливаться с момента включения snapshots.',
    }


ONLINE_HANDSHAKE_WINDOW_SECONDS = 180


def api_recent_handshake(lp: dict | None) -> tuple[bool, int | None]:
    if not lp:
        return False, None
    try:
        latest = int(str(lp.get('latest_handshake') or '0'))
    except (TypeError, ValueError):
        return False, None
    if latest <= 0:
        return False, None
    age = max(0, int(time.time()) - latest)
    return age <= ONLINE_HANDSHAKE_WINDOW_SECONDS, age


def api_clean_category_name(name: str) -> str:
    return re.sub(r'\s+', ' ', str(name or '').strip())[:64]


def api_category_id(value) -> int | None:
    if value in (None, '', 'null', 'none', 0, '0'):
        return None
    try:
        category_id = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Некорректная категория')
    with db() as conn:
        row = conn.execute('SELECT id FROM categories WHERE id = ?', (category_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Категория не найдена')
    return category_id


def api_categories_payload() -> list[dict]:
    with db() as conn:
        rows = conn.execute("""
            SELECT
                cat.id,
                cat.name,
                cat.created_at,
                COUNT(c.id) AS peers_count
            FROM categories cat
            LEFT JOIN clients c
                ON c.category_id = cat.id
                AND COALESCE(c.deleted_at, 0) = 0
            GROUP BY cat.id
            ORDER BY lower(cat.name)
        """).fetchall()
    return [
        {
            'id': int(row['id']),
            'name': row['name'],
            'created_at': int(row['created_at']),
            'peers_count': int(row['peers_count']),
        }
        for row in rows
    ]


def api_panel_user_payload(row) -> dict:
    with db() as conn:
        count = conn.execute(
            'SELECT COUNT(*) AS n FROM clients WHERE COALESCE(deleted_at, 0) = 0 AND owner_id = ?',
            (int(row['id']),),
        ).fetchone()['n']
    traffic_limit_bytes = int(row['traffic_limit_bytes']) if 'traffic_limit_bytes' in row.keys() and row['traffic_limit_bytes'] else 0
    traffic_limit = api_user_traffic_limit_payload(int(row['id']), traffic_limit_bytes)
    expires_at = int(row['expires_at']) if 'expires_at' in row.keys() and row['expires_at'] else None
    return {
        'id': int(row['id']),
        'username': row['username'],
        'role': row['role'],
        'peer_limit': int(row['peer_limit']),
        'peers_used': int(count),
        'traffic_limit_bytes': traffic_limit_bytes,
        'traffic_limit': traffic_limit,
        'expires_at': expires_at,
        'expiration': api_expiration_payload(expires_at, bool(row['enabled'])),
        'enabled': bool(row['enabled']),
        'created_at': int(row['created_at']),
    }


def api_panel_users_payload() -> list[dict]:
    with db() as conn:
        rows = conn.execute('SELECT * FROM panel_users ORDER BY id DESC').fetchall()
    return [api_panel_user_payload(row) for row in rows]


def api_peer_payload(c, live: dict | None = None, include_config: bool = False, counters: dict | None = None) -> dict:
    protocol = c['protocol']
    p = PROTOCOLS[protocol]
    endpoint = client_endpoint(protocol)
    lp = live.get(protocol, {}).get(c['public_key']) if live else None
    active, handshake_age = api_recent_handshake(lp)
    enabled = bool(c['enabled'])
    expires_at = int(c['expires_at']) if 'expires_at' in c.keys() and c['expires_at'] else None
    expiration = api_expiration_payload(expires_at, enabled)
    traffic_limit_bytes = int(c['traffic_limit_bytes']) if 'traffic_limit_bytes' in c.keys() and c['traffic_limit_bytes'] else 0
    counter = counters.get(int(c['id'])) if counters else None
    traffic_limit = api_traffic_limit_payload(traffic_limit_bytes, lp, counter)
    owner_username = c['owner_username'] if 'owner_username' in c.keys() and c['owner_username'] else PANEL_USER
    payload = {
        'id': int(c['id']),
        'name': c['name'],
        'protocol': protocol,
        'protocol_title': p['title'],
        'category_id': int(c['category_id']) if 'category_id' in c.keys() and c['category_id'] is not None else None,
        'category_name': c['category_name'] if 'category_name' in c.keys() else None,
        'owner_id': int(c['owner_id']) if 'owner_id' in c.keys() and c['owner_id'] is not None else None,
        'owner_username': owner_username,
        'created_by_label': owner_username,
        'note': c['note'] if 'note' in c.keys() and c['note'] else '',
        'ip_cidr': c['ip_cidr'],
        'public_key': c['public_key'],
        'enabled': enabled,
        'created_at': int(c['created_at']),
        'expires_at': expires_at,
        'expiration': expiration,
        'traffic_limit_bytes': traffic_limit_bytes,
        'traffic_limit': traffic_limit,
        'traffic_counter': counter,
        'deleted_at': int(c['deleted_at']) if 'deleted_at' in c.keys() else 0,
        'endpoint': endpoint,
        'status': 'limited' if traffic_limit['exceeded'] else ('expired' if expiration['expired'] else ('active' if enabled and active else ('offline' if enabled else 'disabled'))),
        'online_window_seconds': ONLINE_HANDSHAKE_WINDOW_SECONDS,
        'handshake_age_seconds': handshake_age,
        'live': lp or None,
        'links': {
            'html': f"/client/{c['id']}",
            'download': f"/client/{c['id']}/download",
            'download_vpn': f"/client/{c['id']}/download-vpn" if protocol == 'amneziawg' else None,
            'qr_native': f"/client/{c['id']}/qr/native",
            'qr_native_png': f"/client/{c['id']}/qr/native/download",
            'qr_amnezia_vpn': f"/client/{c['id']}/qr/amnezia-vpn" if protocol == 'amneziawg' else None,
            'qr_amnezia_vpn_png': f"/client/{c['id']}/qr/amnezia-vpn/download" if protocol == 'amneziawg' else None,
            'enable': f"/api/peers/{c['id']}/enable",
            'disable': f"/api/peers/{c['id']}/disable",
            'traffic_reset': f"/api/peers/{c['id']}/traffic-reset",
            'delete': f"/api/peers/{c['id']}",
        },
    }
    if include_config:
        payload['config'] = read_conf(c)
    return payload


def api_check_payload(status: str, name: str, message: str, details: dict | None = None) -> dict:
    return {'status': status, 'name': name, 'message': message, 'details': details or {}}


def api_peer_diagnostics_payload(c) -> dict:
    live, errors = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    peer = api_peer_payload(c, live=live, include_config=False, counters=counters)
    protocol = c['protocol']
    p = PROTOCOLS[protocol]
    lp = (live.get(protocol) or {}).get(c['public_key'])
    active, handshake_age = api_recent_handshake(lp)
    checks = []

    protocol_state = api_protocol_state(protocol)
    if protocol_state.get('available'):
        checks.append(api_check_payload('ok', 'Protocol interface', f"{p['title']} доступен: {p['container']} / {p['interface']}", protocol_state))
    else:
        checks.append(api_check_payload('fail', 'Protocol interface', protocol_state.get('reason') or 'protocol unavailable', protocol_state))

    try:
        container = dc().containers.get(p['container'])
        status = getattr(container, 'status', 'unknown') or 'unknown'
        checks.append(api_check_payload('ok' if status == 'running' else 'fail', 'Docker container', f"{p['container']} status: {status}", {'container': p['container'], 'status': status}))
    except Exception as exc:
        checks.append(api_check_payload('fail', 'Docker container', str(exc), {'container': p['container']}))

    config_path = Path(c['config_path'])
    if config_path.exists():
        checks.append(api_check_payload('ok', 'Client config file', str(config_path), {'path': str(config_path), 'size': config_path.stat().st_size}))
    else:
        checks.append(api_check_payload('fail', 'Client config file', f"Файл не найден: {config_path}", {'path': str(config_path)}))

    if lp:
        checks.append(api_check_payload('ok', 'Peer in live interface', 'Peer найден в live выводе контейнера', {'public_key': short_key(c['public_key']), 'endpoint': lp.get('endpoint')}))
    elif peer.get('enabled'):
        checks.append(api_check_payload('fail', 'Peer in live interface', 'Peer включён в панели, но не найден в live-интерфейсе', {'public_key': short_key(c['public_key'])}))
    else:
        checks.append(api_check_payload('warn', 'Peer in live interface', 'Peer отключён, поэтому в live-интерфейсе может отсутствовать', {'public_key': short_key(c['public_key'])}))

    if not peer.get('enabled'):
        checks.append(api_check_payload('warn', 'Access state', 'Peer отключён администратором', {'enabled': False}))
    elif peer.get('expiration', {}).get('expired'):
        checks.append(api_check_payload('fail', 'Access state', 'Срок действия peer истёк', peer.get('expiration')))
    elif peer.get('traffic_limit', {}).get('exceeded'):
        checks.append(api_check_payload('fail', 'Access state', 'Лимит трафика peer исчерпан', peer.get('traffic_limit')))
    else:
        checks.append(api_check_payload('ok', 'Access state', 'Peer разрешён к подключению', {'status': peer.get('status')}))

    endpoint = (lp or {}).get('endpoint')
    if endpoint and endpoint != '(none)':
        checks.append(api_check_payload('ok', 'Client endpoint', endpoint, {'endpoint': endpoint}))
    elif active:
        checks.append(api_check_payload('warn', 'Client endpoint', 'Handshake есть, endpoint не определён', {'endpoint': endpoint or '(none)'}))
    else:
        checks.append(api_check_payload('warn', 'Client endpoint', 'Клиент ещё не подключался или endpoint пустой', {'endpoint': endpoint or '(none)'}))

    if active:
        checks.append(api_check_payload('ok', 'Handshake freshness', f"Последний handshake {handshake_age} сек. назад", {'age_seconds': handshake_age, 'window_seconds': ONLINE_HANDSHAKE_WINDOW_SECONDS}))
    elif handshake_age is not None:
        checks.append(api_check_payload('warn', 'Handshake freshness', f"Handshake был {handshake_age} сек. назад, сейчас не считаем online", {'age_seconds': handshake_age, 'window_seconds': ONLINE_HANDSHAKE_WINDOW_SECONDS}))
    else:
        checks.append(api_check_payload('warn', 'Handshake freshness', 'Handshake ещё не зафиксирован', {'age_seconds': None}))

    rx = int((lp or {}).get('rx') or 0)
    tx = int((lp or {}).get('tx') or 0)
    if rx or tx:
        checks.append(api_check_payload('ok', 'Traffic counters', f"RX {human_bytes(rx)} / TX {human_bytes(tx)}", {'rx': rx, 'tx': tx}))
    else:
        checks.append(api_check_payload('warn', 'Traffic counters', 'Трафика пока нет', {'rx': rx, 'tx': tx}))

    if errors:
        checks.append(api_check_payload('warn', 'Live map errors', '; '.join(errors[:3]), {'errors': errors}))

    summary = {
        'ok': sum(1 for item in checks if item['status'] == 'ok'),
        'warn': sum(1 for item in checks if item['status'] == 'warn'),
        'fail': sum(1 for item in checks if item['status'] == 'fail'),
    }
    return {'ok': True, 'peer': peer, 'summary': summary, 'checks': checks, 'checked_at': int(time.time())}


@app.post('/api/auth/login')
async def api_auth_login(request: Request):
    data = await api_read_payload(request)
    username = str(data.get('username', ''))
    password = str(data.get('password', ''))
    login_user = authenticate_user(username, password)
    if not login_user:
        return api_error('Неверный логин или пароль', status_code=401)
    resp = JSONResponse({'ok': True, 'authenticated': True, 'user': login_user})
    resp.set_cookie(
        SESSION_COOKIE,
        make_user_session(login_user['username'], login_user['role']),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite='lax',
    )
    return resp


@app.post('/api/auth/logout')
def api_auth_logout(user=Depends(api_require_auth)):
    resp = JSONResponse({'ok': True})
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get('/api/auth/me')
def api_auth_me(request: Request):
    current = api_current_user(request)
    if not current:
        return JSONResponse({'ok': False, 'authenticated': False}, status_code=401)
    return {'ok': True, 'authenticated': True, 'user': current, 'quota': api_user_quota(current)}


@app.get('/api/version')
def api_version(user=Depends(api_require_auth)):
    return cached_version_status()


@app.get('/api/update/status')
def api_update_status(user=Depends(api_require_admin)):
    return update_status_payload()


@app.post('/api/update/run')
async def api_update_run(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    runner = update_runner_payload()
    if not runner['can_run']:
        return api_error(runner['reason'], status_code=409, runner=runner)
    job = update_job_payload()
    if job.get("running"):
        return api_error('Update уже выполняется', status_code=409, job=update_job_payload())
    if str(data.get('confirm', '')).strip() != runner['confirm_text']:
        return api_error(f"Для запуска нужно подтверждение {runner['confirm_text']}", status_code=400)
    backup = api_create_backup_archive('pre-ui-update')
    api_audit_log(request, user, 'update.start', 'update', 'runner', 'host', {'backup': backup.name, 'runner': runner})
    try:
        update_runner_request('run', actor=user.get('username'), backup=backup.name)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as e:
        api_audit_log(request, user, 'update.error', 'update', 'runner', 'host', {'error': str(e), 'backup': backup.name})
        return api_error(f'Не удалось запустить updater: {e}', status_code=502, runner=runner)
    return update_status_payload()


@app.get('/api/node/protocols')
def api_node_protocols(user=Depends(api_require_auth)):
    return {
        'ok': True,
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'legacy_endpoint_host': ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'fornex_vpn_ports': FORNEX_VPN_PORTS,
        'protocols': {protocol: api_protocol_state(protocol) for protocol in PROTOCOLS},
    }


@app.get('/api/node/protocols/ports')
def api_node_protocol_ports(user=Depends(api_require_admin)):
    return {
        'ok': True,
        'fornex_vpn_ports': FORNEX_VPN_PORTS,
        'recommendations': {
            'wireguard': 'Для Fornex используйте порт из разрешенного списка, например 1144/udp, если он свободен.',
            'amneziawg': 'Для AmneziaWG обычно лучше 443/udp, если на сервере он не занят другим UDP-сервисом.',
        },
    }


@app.patch('/api/node/protocols/{protocol}/port')
async def api_node_protocol_port_update(protocol: str, request: Request, user=Depends(api_require_admin)):
    proto(protocol)
    data = await api_read_payload(request)
    port = valid_udp_port(data.get('port'))
    if str(data.get('confirm', '')).strip().upper() != 'PORT':
        return api_error('Для смены порта введите подтверждение PORT', status_code=400)
    before = api_protocol_state(protocol)
    try:
        result = change_protocol_port(protocol, port)
    except HTTPException:
        raise
    except (docker.errors.APIError, docker.errors.NotFound, RuntimeError, OSError, ValueError) as e:
        api_audit_log(request, user, 'protocol.port.error', 'protocol', protocol, 'host', {'port': port, 'error': str(e)})
        return api_error(f'Не удалось сменить UDP порт: {e}', status_code=502)
    after = api_protocol_state(protocol)
    api_audit_log(
        request,
        user,
        'protocol.port.update',
        'protocol',
        protocol,
        'host',
        {'from': before.get('port'), 'to': port, 'changed': bool(result.get('changed'))},
    )
    telegram_notify(
        f"3WG Core: {user.get('username')} изменил UDP порт {after.get('title')}: "
        f"{before.get('port')} -> {after.get('port')}"
    )
    return {
        'ok': True,
        'result': result,
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'legacy_endpoint_host': ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'fornex_vpn_ports': FORNEX_VPN_PORTS,
        'protocols': {key: api_protocol_state(key) for key in PROTOCOLS},
    }


@app.get('/api/node/status')
def api_node_status(user=Depends(api_require_auth)):
    live, errors = api_live_maps()
    with db() as conn:
        total = conn.execute('SELECT COUNT(*) AS n FROM clients WHERE COALESCE(deleted_at, 0) = 0').fetchone()['n']
    return {
        'ok': True,
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'legacy_endpoint_host': ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'fornex_vpn_ports': FORNEX_VPN_PORTS,
        'dns_servers': DNS_SERVERS,
        'clients_total': int(total),
        'peers_total': sum(len(pm) for pm in live.values()),
        'peers_online': sum(1 for pm in live.values() for x in pm.values() if x.get('endpoint') != '(none)'),
        'protocols': {protocol: api_protocol_state(protocol, include_raw=True) for protocol in PROTOCOLS},
        'errors': errors,
    }


@app.get('/api/node/diagnostics')
def api_node_diagnostics(user=Depends(api_require_admin)):
    return api_node_diagnostics_payload()


@app.get('/api/peers')
def api_peers(user=Depends(api_require_auth)):
    expired_disabled = api_disable_expired_peers()
    live, errors = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    traffic_limited_disabled = api_disable_traffic_limited_peers(live, counters)
    user_traffic_limited_disabled = api_disable_user_traffic_limited_peers()
    if traffic_limited_disabled or user_traffic_limited_disabled:
        live, errors = api_live_maps()
        counters = api_record_peer_traffic_counters(live)
    api_record_traffic_snapshot(live)
    where, params = api_user_where(user, 'c')
    with db() as conn:
        rows = conn.execute(f"""
            SELECT c.*, cat.name AS category_name, u.username AS owner_username
            FROM clients c
            LEFT JOIN categories cat ON cat.id = c.category_id
            LEFT JOIN panel_users u ON u.id = c.owner_id
            WHERE COALESCE(c.deleted_at, 0) = 0
            {where}
            ORDER BY c.id DESC
        """, params).fetchall()
    return {
        'ok': True,
        'peers': [api_peer_payload(c, live=live, counters=counters) for c in rows],
        'categories': api_categories_payload() if user.get('is_admin') else [],
        'quota': api_user_quota(user),
        'errors': errors,
        'expired_disabled': expired_disabled,
        'traffic_limited_disabled': traffic_limited_disabled,
        'user_traffic_limited_disabled': user_traffic_limited_disabled,
    }


@app.get('/api/categories')
def api_categories(user=Depends(api_require_auth)):
    if not user.get('is_admin'):
        return {'ok': True, 'categories': []}
    return {'ok': True, 'categories': api_categories_payload()}


@app.get('/api/users')
def api_users(user=Depends(api_require_admin)):
    live, _errors = api_live_maps()
    api_record_peer_traffic_counters(live)
    api_disable_user_traffic_limited_peers()
    return {'ok': True, 'users': api_panel_users_payload()}


@app.get('/api/audit')
def api_audit_events(
    request: Request,
    limit: int = 100,
    action: str | None = None,
    actor: str | None = None,
    object_type: str | None = None,
    user=Depends(api_require_admin),
):
    limit = max(1, min(int(limit or 100), 500))
    clauses = []
    values = []
    if action:
        clauses.append('action = ?')
        values.append(action.strip())
    if actor:
        clauses.append('actor_username = ?')
        values.append(actor.strip())
    if object_type:
        clauses.append('object_type = ?')
        values.append(object_type.strip())
    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM audit_events
            {where}
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            [*values, limit],
        ).fetchall()
    return {'ok': True, 'events': [api_audit_event_payload(r) for r in rows]}


@app.get('/api/backups')
def api_backups_list(user=Depends(api_require_admin)):
    api_maybe_run_auto_backup()
    return {'ok': True, 'backups': api_list_backups(), 'auto': api_auto_backup_settings()}


@app.post('/api/backups')
async def api_backups_create(request: Request, user=Depends(api_require_admin)):
    path = api_create_backup_archive('manual')
    payload = api_backup_payload(path)
    api_audit_log(request, user, 'backup.create', 'backup', path.name, path.name, {'size': payload['size']})
    telegram_notify(
        "backup создан",
        [f"Файл: {path.name}", f"Размер: {human_bytes(payload['size'])}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'backup': payload, 'backups': api_list_backups(), 'auto': api_auto_backup_settings()}


@app.post('/api/backups/auto')
async def api_backups_auto_update(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    try:
        settings = api_auto_backup_settings()
        settings.update({
            'enabled': bool(data.get('enabled')),
            'interval_hours': int(data.get('interval_hours', settings['interval_hours'])),
            'keep_last': int(data.get('keep_last', settings['keep_last'])),
        })
        saved = api_save_auto_backup_settings(settings)
    except (TypeError, ValueError):
        return api_error('Некорректные настройки auto backup', status_code=400)
    deleted = api_prune_auto_backups(saved['keep_last'])
    result = api_maybe_run_auto_backup(force=bool(data.get('run_now')))
    if result:
        saved = result['auto']
        deleted.extend(result.get('deleted') or [])
    api_audit_log(
        request,
        user,
        'backup.auto.update',
        'backup',
        'auto',
        'auto backup',
        {'settings': saved, 'pruned': deleted},
    )
    return {'ok': True, 'auto': saved, 'deleted': deleted, 'backups': api_list_backups()}


@app.get('/api/backups/{name}/download')
def api_backups_download(name: str, user=Depends(api_require_admin)):
    path = api_backup_path(name)
    return FileResponse(path, filename=path.name, media_type='application/gzip')


@app.delete('/api/backups/{name}')
async def api_backups_delete(name: str, request: Request, user=Depends(api_require_admin)):
    path = api_backup_path(name)
    payload = api_backup_payload(path)
    path.unlink()
    api_audit_log(request, user, 'backup.delete', 'backup', payload['name'], payload['name'], {'size': payload['size']})
    telegram_notify(
        "backup удалён",
        [f"Файл: {payload['name']}", f"Размер: {human_bytes(payload['size'])}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'deleted': payload['name'], 'backups': api_list_backups(), 'auto': api_auto_backup_settings()}


@app.post('/api/backups/{name}/restore')
async def api_backups_restore(name: str, request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    if str(data.get('confirm', '')).strip() != 'RESTORE':
        return api_error('Для restore нужно подтверждение RESTORE', status_code=400)
    path = api_backup_path(name)
    api_validate_backup_archive(path)
    pre_restore = api_create_backup_archive('pre-restore')
    tmp_dir = Path(tempfile.mkdtemp(prefix='3wg-restore-', dir=str(BACKUPS_DIR)))
    try:
        with tarfile.open(path, 'r:gz') as tar:
            tar.extractall(tmp_dir)
        data_src = tmp_dir / 'data'
        clients_src = tmp_dir / 'clients'
        if data_src.exists():
            api_clear_directory(DATA_DIR)
            api_copy_directory_contents(data_src, DATA_DIR)
        if clients_src.exists():
            api_clear_directory(CLIENTS_DIR)
            api_copy_directory_contents(clients_src, CLIENTS_DIR)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    init_db()
    api_audit_log(
        request,
        user,
        'backup.restore',
        'backup',
        path.name,
        path.name,
        {'pre_restore_backup': pre_restore.name, 'restored': ['data', 'clients']},
    )
    return {
        'ok': True,
        'restored': path.name,
        'pre_restore_backup': api_backup_payload(pre_restore),
        'backups': api_list_backups(),
        'auto': api_auto_backup_settings(),
    }


@app.get('/api/migration')
def api_migration_list(user=Depends(api_require_admin)):
    return {'ok': True, 'bundles': api_list_migration_bundles()}


@app.post('/api/migration/export')
async def api_migration_export(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    include_backups = bool(data.get('include_backups'))
    path = api_create_migration_bundle(include_backups=include_backups)
    payload = api_migration_payload(path)
    api_audit_log(request, user, 'migration.export', 'migration', path.name, path.name, {'size': payload['size'], 'include_backups': include_backups})
    telegram_notify(
        "migration bundle создан",
        [f"Файл: {path.name}", f"Размер: {human_bytes(payload['size'])}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'bundle': payload, 'bundles': api_list_migration_bundles()}


@app.get('/api/migration/push')
def api_migration_push_status(user=Depends(api_require_admin)):
    return {'ok': True, 'runner': migration_runner_payload(), 'job': migration_job_payload()}


@app.post('/api/migration/push')
async def api_migration_push(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    archive = api_migration_path(str(data.get('archive') or ''))
    if str(data.get('confirm') or '').strip() != 'MIGRATE':
        raise HTTPException(status_code=400, detail='Для запуска введите MIGRATE')
    auth_method = str(data.get('auth_method') or 'password').strip()
    if auth_method not in ('password', 'key'):
        raise HTTPException(status_code=400, detail='Некорректный SSH auth method')
    payload = {
        'host': str(data.get('host') or '').strip(),
        'user': str(data.get('user') or 'root').strip() or 'root',
        'port': data.get('port') or 22,
        'auth_method': auth_method,
        'password': str(data.get('password') or ''),
        'private_key': str(data.get('private_key') or ''),
        'archive': archive.name,
        'install_dir': str(data.get('install_dir') or '/opt/3wg-panel').strip() or '/opt/3wg-panel',
        'repo_url': str(data.get('repo_url') or 'https://github.com/dblack-adminix/3wg-panel.git').strip(),
        'branch': str(data.get('branch') or 'dev').strip() or 'dev',
    }
    try:
        response = migration_runner_request('push', **payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    api_audit_log(
        request,
        user,
        'migration.push',
        'migration',
        archive.name,
        archive.name,
        {
            'host': payload['host'],
            'user': payload['user'],
            'port': payload['port'],
            'auth_method': auth_method,
            'archive': archive.name,
            'install_dir': payload['install_dir'],
            'repo_url': payload['repo_url'],
            'branch': payload['branch'],
        },
    )
    telegram_notify(
        "migration push запущен",
        [f"Target: {payload['user']}@{payload['host']}:{payload['port']}", f"Файл: {archive.name}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'runner': migration_runner_payload(), 'job': response.get('job') or migration_job_payload()}


@app.get('/api/migration/{name}/download')
def api_migration_download(name: str, user=Depends(api_require_admin)):
    path = api_migration_path(name)
    return FileResponse(path, filename=path.name, media_type='application/gzip')


@app.delete('/api/migration/{name}')
async def api_migration_delete(name: str, request: Request, user=Depends(api_require_admin)):
    path = api_migration_path(name)
    payload = api_migration_payload(path)
    path.unlink()
    api_audit_log(request, user, 'migration.delete', 'migration', payload['name'], payload['name'], {'size': payload['size']})
    return {'ok': True, 'deleted': payload['name'], 'bundles': api_list_migration_bundles()}


@app.post('/api/users')
async def api_user_create(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    username = re.sub(r'\s+', '', str(data.get('username', '')).strip())[:64]
    password = str(data.get('password', '')).strip()
    role = str(data.get('role', 'user')).strip()
    if role not in ('user', 'admin'):
        role = 'user'
    try:
        peer_limit = max(0, int(data.get('peer_limit', 1)))
    except (TypeError, ValueError):
        return api_error('Некорректный лимит peerов', status_code=400)
    try:
        traffic_limit_bytes = api_parse_traffic_limit(data.get('traffic_limit_bytes'))
        expires_at = api_parse_user_expires_at(data.get('expires_at'))
    except HTTPException as e:
        return api_error(str(e.detail), status_code=e.status_code)
    if not username:
        return api_error('Пустой логин', status_code=400)
    if username == PANEL_USER:
        return api_error('Этот логин занят системным администратором', status_code=409)
    if len(password) < 6:
        return api_error('Пароль должен быть не короче 6 символов', status_code=400)
    try:
        with db() as conn:
            conn.execute(
                'INSERT INTO panel_users(username, password_hash, role, peer_limit, traffic_limit_bytes, expires_at, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)',
                (username, password_hash(password), role, peer_limit, traffic_limit_bytes, expires_at, int(time.time())),
            )
            conn.commit()
            created_id = int(conn.execute('SELECT last_insert_rowid() AS id').fetchone()['id'])
    except sqlite3.IntegrityError:
        return api_error('Такой пользователь уже есть', status_code=409)
    api_audit_log(
        request,
        user,
        'user.create',
        'panel_user',
        created_id,
        username,
        {'role': role, 'peer_limit': peer_limit, 'traffic_limit_bytes': traffic_limit_bytes, 'expires_at': expires_at},
    )
    return {'ok': True, 'users': api_panel_users_payload()}


@app.patch('/api/users/{user_id}')
async def api_user_update(user_id: int, request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    fields = []
    values = []
    if 'peer_limit' in data:
        try:
            fields.append('peer_limit = ?')
            values.append(max(0, int(data.get('peer_limit'))))
        except (TypeError, ValueError):
            return api_error('Некорректный лимит peerов', status_code=400)
    if 'traffic_limit_bytes' in data:
        try:
            fields.append('traffic_limit_bytes = ?')
            values.append(api_parse_traffic_limit(data.get('traffic_limit_bytes')))
        except HTTPException as e:
            return api_error(str(e.detail), status_code=e.status_code)
    if 'expires_at' in data:
        try:
            fields.append('expires_at = ?')
            values.append(api_parse_user_expires_at(data.get('expires_at')))
        except HTTPException as e:
            return api_error(str(e.detail), status_code=e.status_code)
    if 'enabled' in data:
        fields.append('enabled = ?')
        values.append(1 if bool(data.get('enabled')) else 0)
    if 'role' in data:
        role = str(data.get('role', 'user')).strip()
        if role not in ('user', 'admin'):
            return api_error('Некорректная роль', status_code=400)
        fields.append('role = ?')
        values.append(role)
    if str(data.get('password', '')).strip():
        password = str(data.get('password')).strip()
        if len(password) < 6:
            return api_error('Пароль должен быть не короче 6 символов', status_code=400)
        fields.append('password_hash = ?')
        values.append(password_hash(password))
    if not fields:
        return {'ok': True, 'users': api_panel_users_payload()}
    with db() as conn:
        before = conn.execute('SELECT id, username, role, peer_limit, traffic_limit_bytes, expires_at, enabled FROM panel_users WHERE id = ?', (user_id,)).fetchone()
    if not before:
        return api_error('Пользователь не найден', status_code=404)
    values.append(user_id)
    with db() as conn:
        cur = conn.execute(f"UPDATE panel_users SET {', '.join(fields)} WHERE id = ?", values)
        if cur.rowcount == 0:
            return api_error('Пользователь не найден', status_code=404)
        conn.commit()
    changed = [f.split(' = ', 1)[0] for f in fields]
    api_audit_log(
        request,
        user,
        'user.update',
        'panel_user',
        user_id,
        before['username'],
        {'changed': changed, 'before': dict(before)},
    )
    return {'ok': True, 'users': api_panel_users_payload()}


@app.delete('/api/users/{user_id}')
def api_user_delete(user_id: int, request: Request, user=Depends(api_require_admin)):
    with db() as conn:
        row = conn.execute('SELECT id, username, role, peer_limit, traffic_limit_bytes, enabled FROM panel_users WHERE id = ?', (user_id,)).fetchone()
        if not row:
            return api_error('Пользователь не найден', status_code=404)
        conn.execute('UPDATE clients SET owner_id = NULL WHERE owner_id = ?', (user_id,))
        conn.execute('DELETE FROM panel_users WHERE id = ?', (user_id,))
        conn.commit()
    api_audit_log(request, user, 'user.delete', 'panel_user', user_id, row['username'], {'deleted': dict(row)})
    return {'ok': True, 'users': api_panel_users_payload()}


@app.post('/api/categories')
async def api_category_create(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    name = api_clean_category_name(data.get('name', ''))
    if not name:
        return api_error('Пустое имя категории', status_code=400)
    try:
        with db() as conn:
            cur = conn.execute(
                'INSERT INTO categories(name, created_at) VALUES (?, ?)',
                (name, int(time.time())),
            )
            conn.commit()
            category_id = int(cur.lastrowid)
    except sqlite3.IntegrityError:
        return api_error('Такая категория уже есть', status_code=409)
    api_audit_log(request, user, 'category.create', 'category', category_id, name)
    return {'ok': True, 'category': next((c for c in api_categories_payload() if c['id'] == category_id), None)}


@app.patch('/api/categories/{category_id}')
async def api_category_update(category_id: int, request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    name = api_clean_category_name(data.get('name', ''))
    if not name:
        return api_error('Пустое имя категории', status_code=400)
    with db() as conn:
        before = conn.execute('SELECT id, name FROM categories WHERE id = ?', (category_id,)).fetchone()
    if not before:
        return api_error('Категория не найдена', status_code=404)
    try:
        with db() as conn:
            cur = conn.execute('UPDATE categories SET name = ? WHERE id = ?', (name, category_id))
            if cur.rowcount == 0:
                return api_error('Категория не найдена', status_code=404)
            conn.commit()
    except sqlite3.IntegrityError:
        return api_error('Такая категория уже есть', status_code=409)
    api_audit_log(request, user, 'category.update', 'category', category_id, name, {'before': dict(before), 'name': name})
    return {'ok': True, 'categories': api_categories_payload()}


@app.delete('/api/categories/{category_id}')
def api_category_delete(category_id: int, request: Request, user=Depends(api_require_admin)):
    with db() as conn:
        row = conn.execute('SELECT id, name FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not row:
            return api_error('Категория не найдена', status_code=404)
        affected = conn.execute('SELECT COUNT(*) AS n FROM clients WHERE category_id = ?', (category_id,)).fetchone()['n']
        conn.execute('UPDATE clients SET category_id = NULL WHERE category_id = ?', (category_id,))
        conn.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        conn.commit()
    api_audit_log(request, user, 'category.delete', 'category', category_id, row['name'], {'affected_peers': affected})
    return {'ok': True, 'categories': api_categories_payload()}


@app.get('/api/traffic/history')
def api_traffic_history(protocol: str = 'amneziawg', days: int = 30, user=Depends(api_require_auth)):
    return api_traffic_history_payload(protocol, days)


@app.post('/api/peers')
async def api_create_peers(request: Request, user=Depends(api_require_auth)):
    data = await api_read_payload(request)
    name = str(data.get('name', '')).strip()
    category_id = None
    if user.get('is_admin'):
        try:
            category_id = api_category_id(data.get('category_id'))
            expires_at = api_parse_expires_at(data.get('expires_at'))
            traffic_limit_bytes = api_parse_traffic_limit(data.get('traffic_limit_bytes'))
        except HTTPException as e:
            return api_error(str(e.detail), status_code=e.status_code)
    else:
        expires_at = None
        traffic_limit_bytes = 0
    protocols = data.get('protocols', data.get('protocol', []))
    if isinstance(protocols, str):
        protocols = [protocols]
    protocols = [p for p in protocols if p in PROTOCOLS]

    if not name:
        return api_error('Пустое имя клиента', status_code=400)
    if not protocols:
        return api_error('Не выбран протокол', status_code=400)
    quota = api_user_quota(user)
    if quota.get('limited') and len(protocols) > int(quota.get('remaining') or 0):
        return api_error(f"Лимит peer'ов исчерпан: доступно {quota.get('remaining')}", status_code=403, quota=quota)

    created_ids = []
    try:
        for protocol in protocols:
            created_ids.append(create_client(name, protocol, category_id=category_id, owner_id=user.get('id'), expires_at=expires_at, traffic_limit_bytes=traffic_limit_bytes))
    except Exception as e:
        return api_error(str(e), status_code=500, created_ids=created_ids)

    for created_id in created_ids:
        api_audit_log(
            request,
            user,
            'peer.create',
            'peer',
            created_id,
            name,
            {'protocols': protocols, 'category_id': category_id, 'expires_at': expires_at, 'traffic_limit_bytes': traffic_limit_bytes},
        )
    telegram_notify(
        "создан peer",
        [
            f"Имя: {name}",
            f"Протоколы: {', '.join(protocols)}",
            f"Кто: {user.get('username')}",
        ],
    )

    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    with db() as conn:
        qmarks = ','.join('?' for _ in created_ids)
        rows = conn.execute(f"""
            SELECT c.*, cat.name AS category_name, u.username AS owner_username
            FROM clients c
            LEFT JOIN categories cat ON cat.id = c.category_id
            LEFT JOIN panel_users u ON u.id = c.owner_id
            WHERE c.id IN ({qmarks})
            ORDER BY c.id DESC
        """, created_ids).fetchall()
    return {'ok': True, 'created_ids': created_ids, 'peers': [api_peer_payload(c, live=live, counters=counters) for c in rows]}


@app.patch('/api/peers/{client_id}')
async def api_peer_update(client_id: int, request: Request, user=Depends(api_require_auth)):
    if not user.get('is_admin'):
        return api_error('Недостаточно прав', status_code=403)
    data = await api_read_payload(request)
    try:
        category_id = api_category_id(data.get('category_id')) if 'category_id' in data else None
        expires_at = api_parse_expires_at(data.get('expires_at')) if 'expires_at' in data else None
        traffic_limit_bytes = api_parse_traffic_limit(data.get('traffic_limit_bytes')) if 'traffic_limit_bytes' in data else None
    except HTTPException as e:
        return api_error(str(e.detail), status_code=e.status_code)
    note = str(data.get('note', '')).replace('\x00', '').strip()[:500] if 'note' in data else None
    if 'category_id' not in data and 'expires_at' not in data and 'traffic_limit_bytes' not in data and 'note' not in data:
        return api_error('Нет изменений', status_code=400)
    with db() as conn:
        before = conn.execute(
            'SELECT id, name, protocol, category_id, expires_at, traffic_limit_bytes, note FROM clients WHERE id = ? AND COALESCE(deleted_at, 0) = 0',
            (client_id,),
        ).fetchone()
        if not before:
            return api_error('Клиент не найден', status_code=404)
        fields = []
        values = []
        if 'category_id' in data:
            fields.append('category_id = ?')
            values.append(category_id)
        if 'expires_at' in data:
            fields.append('expires_at = ?')
            values.append(expires_at)
        if 'traffic_limit_bytes' in data:
            fields.append('traffic_limit_bytes = ?')
            values.append(traffic_limit_bytes)
        if 'note' in data:
            fields.append('note = ?')
            values.append(note)
        values.append(client_id)
        cur = conn.execute(
            f"UPDATE clients SET {', '.join(fields)} WHERE id = ? AND COALESCE(deleted_at, 0) = 0",
            values,
        )
        if cur.rowcount == 0:
            return api_error('Клиент не найден', status_code=404)
        conn.commit()
    api_audit_log(
        request,
        user,
        'peer.update',
        'peer',
        client_id,
        before['name'],
        {
            'protocol': before['protocol'],
            'before_category_id': before['category_id'],
            'category_id': category_id if 'category_id' in data else before['category_id'],
            'before_expires_at': before['expires_at'],
            'expires_at': expires_at if 'expires_at' in data else before['expires_at'],
            'before_traffic_limit_bytes': before['traffic_limit_bytes'],
            'traffic_limit_bytes': traffic_limit_bytes if 'traffic_limit_bytes' in data else before['traffic_limit_bytes'],
            'before_note': before['note'],
            'note': note if 'note' in data else before['note'],
        },
    )
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    with db() as conn:
        c = conn.execute("""
            SELECT c.*, cat.name AS category_name, u.username AS owner_username
            FROM clients c
            LEFT JOIN categories cat ON cat.id = c.category_id
            LEFT JOIN panel_users u ON u.id = c.owner_id
            WHERE c.id = ?
        """, (client_id,)).fetchone()
    return {'ok': True, 'peer': api_peer_payload(c, live=live, counters=counters), 'categories': api_categories_payload()}


@app.get('/api/peers/{client_id}')
def api_peer_get(client_id: int, user=Depends(api_require_auth)):
    api_disable_expired_peers()
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    if api_disable_traffic_limited_peers(live, counters):
        live, _ = api_live_maps()
        counters = api_record_peer_traffic_counters(live)
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    return {'ok': True, 'peer': api_peer_payload(c, live=live, include_config=True, counters=counters)}


@app.get('/api/peers/{client_id}/diagnostics')
def api_peer_diagnostics(client_id: int, user=Depends(api_require_auth)):
    api_disable_expired_peers()
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    return api_peer_diagnostics_payload(c)


@app.get('/api/peers/{client_id}/config')
def api_peer_config(client_id: int, user=Depends(api_require_auth)):
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    return PlainTextResponse(read_conf(c))


@app.post('/api/peers/{client_id}/enable')
def api_peer_enable(client_id: int, request: Request, user=Depends(api_require_auth)):
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    if c['expires_at'] and int(c['expires_at']) <= int(time.time()):
        return api_error('Срок действия peer истек. Продлите срок перед включением.', status_code=409)
    live, _ = api_live_maps()
    lp = (live.get(c['protocol']) or {}).get(c['public_key'])
    counters = api_record_peer_traffic_counters(live)
    if c['traffic_limit_bytes'] and api_traffic_limit_payload(int(c['traffic_limit_bytes']), lp, counters.get(int(c['id'])))['exceeded']:
        return api_error('Лимит трафика peer исчерпан. Увеличьте или снимите лимит перед включением.', status_code=409)
    try:
        enable_peer(c)
    except Exception as e:
        return api_error(str(e), status_code=500)
    api_audit_log(request, user, 'peer.enable', 'peer', client_id, c['name'], {'protocol': c['protocol'], 'ip_cidr': c['ip_cidr']})
    telegram_notify(
        "peer включён",
        [f"{c['name']} / {c['protocol']}", f"IP: {c['ip_cidr']}", f"Кто: {user.get('username')}"],
    )
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live, counters=counters)}


@app.post('/api/peers/{client_id}/disable')
def api_peer_disable(client_id: int, request: Request, user=Depends(api_require_auth)):
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    try:
        disable_peer(c)
    except Exception as e:
        return api_error(str(e), status_code=500)
    api_audit_log(request, user, 'peer.disable', 'peer', client_id, c['name'], {'protocol': c['protocol'], 'ip_cidr': c['ip_cidr']})
    telegram_notify(
        "peer отключён",
        [f"{c['name']} / {c['protocol']}", f"IP: {c['ip_cidr']}", f"Кто: {user.get('username')}"],
    )
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live, counters=counters)}


@app.post('/api/peers/{client_id}/traffic-reset')
def api_peer_traffic_reset(client_id: int, request: Request, user=Depends(api_require_auth)):
    if not user.get('is_admin'):
        return api_error('Недостаточно прав', status_code=403)
    c = load_client(client_id)
    live, _ = api_live_maps()
    lp = (live.get(c['protocol']) or {}).get(c['public_key']) or {}
    last_rx = int(lp.get('rx') or 0)
    last_tx = int(lp.get('tx') or 0)
    now = int(time.time())
    with db() as conn:
        before = conn.execute('SELECT * FROM peer_traffic_counters WHERE client_id = ?', (client_id,)).fetchone()
        conn.execute(
            """
            INSERT INTO peer_traffic_counters(client_id, protocol, public_key, rx_total, tx_total, last_rx, last_tx, updated_at)
            VALUES (?, ?, ?, 0, 0, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                protocol = excluded.protocol,
                public_key = excluded.public_key,
                rx_total = 0,
                tx_total = 0,
                last_rx = excluded.last_rx,
                last_tx = excluded.last_tx,
                updated_at = excluded.updated_at
            """,
            (client_id, c['protocol'], c['public_key'], last_rx, last_tx, now),
        )
        conn.commit()
    api_audit_log(
        request,
        user,
        'peer.traffic_reset',
        'peer',
        client_id,
        c['name'],
        {
            'protocol': c['protocol'],
            'ip_cidr': c['ip_cidr'],
            'before_rx_total': int(before['rx_total']) if before else 0,
            'before_tx_total': int(before['tx_total']) if before else 0,
            'last_rx': last_rx,
            'last_tx': last_tx,
        },
    )
    counters = api_record_peer_traffic_counters(live)
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live, counters=counters)}


@app.delete('/api/peers/{client_id}')
def api_peer_delete(client_id: int, request: Request, user=Depends(api_require_auth)):
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    try:
        remove_peer(c['protocol'], c['public_key'])
        with db() as conn:
            conn.execute('UPDATE clients SET enabled = 0, deleted_at = ? WHERE id = ?', (int(time.time()), client_id))
            conn.commit()
        conf_path = Path(c['config_path'])
        if conf_path.exists():
            conf_path.rename(conf_path.with_suffix(conf_path.suffix + f'.deleted.{int(time.time())}'))
    except Exception as e:
        return api_error(str(e), status_code=500)
    api_audit_log(request, user, 'peer.delete', 'peer', client_id, c['name'], {'protocol': c['protocol'], 'ip_cidr': c['ip_cidr']})
    telegram_notify(
        "peer удалён",
        [f"{c['name']} / {c['protocol']}", f"IP: {c['ip_cidr']}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'deleted_id': client_id}

# === 3WG P2P GUARD API START ===
P2P_GUARD_CHAIN = '3WG-P2P-GUARD'
P2P_GUARD_DEFAULTS = {
    'enabled': False,
    'mode': 'soft',
    'allow_udp_ports': '53,123,443',
    'updated_at': 0,
}
P2P_GUARD_PORTS = '6881:6999,6969,51413,2710,4444,45100:45199'
P2P_GUARD_SIGNATURES = [
    'BitTorrent protocol',
    'announce_peer',
    'find_node',
    'get_peers',
    'info_hash',
    'peer_id=',
    'torrent',
]


def p2p_guard_settings() -> dict:
    raw = panel_setting_get('p2p_guard')
    settings = dict(P2P_GUARD_DEFAULTS)
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception:
            pass
    mode = str(settings.get('mode') or 'soft').strip().lower()
    if mode not in ('soft', 'strict'):
        mode = 'soft'
    settings['mode'] = mode
    settings['enabled'] = bool(settings.get('enabled'))
    settings['allow_udp_ports'] = p2p_guard_normalize_ports(settings.get('allow_udp_ports') or '53,123,443')
    try:
        settings['updated_at'] = int(settings.get('updated_at') or 0)
    except (TypeError, ValueError):
        settings['updated_at'] = 0
    return settings


def p2p_guard_save_settings(settings: dict) -> dict:
    clean = dict(P2P_GUARD_DEFAULTS)
    clean.update(settings or {})
    clean['enabled'] = bool(clean.get('enabled'))
    clean['mode'] = str(clean.get('mode') or 'soft').strip().lower()
    if clean['mode'] not in ('soft', 'strict'):
        clean['mode'] = 'soft'
    clean['allow_udp_ports'] = p2p_guard_normalize_ports(clean.get('allow_udp_ports') or '53,123,443')
    clean['updated_at'] = int(time.time())
    panel_setting_set('p2p_guard', json.dumps(clean, ensure_ascii=False, separators=(',', ':')))
    return p2p_guard_settings()


def p2p_guard_normalize_ports(value) -> str:
    raw = str(value or '').replace(' ', '')
    if not raw:
        return '53,123,443'
    parts = []
    for item in raw.split(','):
        if not item:
            continue
        if ':' in item or '-' in item:
            sep = ':' if ':' in item else '-'
            left, right = item.split(sep, 1)
            if not left.isdigit() or not right.isdigit():
                raise HTTPException(status_code=400, detail='Некорректный список UDP портов')
            a, b = int(left), int(right)
            if a < 1 or b > 65535 or a > b:
                raise HTTPException(status_code=400, detail='Некорректный диапазон UDP портов')
            parts.append(f'{a}:{b}')
        else:
            if not item.isdigit():
                raise HTTPException(status_code=400, detail='Некорректный список UDP портов')
            port = int(item)
            if port < 1 or port > 65535:
                raise HTTPException(status_code=400, detail='Некорректный UDP порт')
            parts.append(str(port))
    return ','.join(dict.fromkeys(parts)) or '53,123,443'


def p2p_guard_exec(protocol: str, args: list[str]) -> dict:
    p = proto(protocol)
    started = time.time()
    try:
        container = dc().containers.get(p['container'])
        result = container.exec_run(args, stdout=True, stderr=True)
        output = result.output.decode('utf-8', errors='replace') if isinstance(result.output, (bytes, bytearray)) else str(result.output or '')
        return {
            'ok': result.exit_code == 0,
            'exit_code': int(result.exit_code or 0),
            'output': output.strip(),
            'duration_ms': int((time.time() - started) * 1000),
        }
    except Exception as e:
        return {'ok': False, 'exit_code': 125, 'output': str(e), 'duration_ms': int((time.time() - started) * 1000)}


def p2p_guard_iptables(protocol: str, args: list[str], check: bool = False) -> dict:
    result = p2p_guard_exec(protocol, ['iptables', *args])
    if check and not result['ok']:
        raise RuntimeError(result.get('output') or 'iptables failed')
    return result


def p2p_guard_chain_exists(protocol: str) -> bool:
    return p2p_guard_iptables(protocol, ['-S', P2P_GUARD_CHAIN])['ok']


def p2p_guard_hook_exists(protocol: str) -> bool:
    iface = PROTOCOLS[protocol]['interface']
    in_hook = p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])['ok']
    out_hook = p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])['ok']
    return in_hook and out_hook


def p2p_guard_status_for(protocol: str) -> dict:
    p = PROTOCOLS[protocol]
    state = api_protocol_state(protocol)
    chain = p2p_guard_chain_exists(protocol)
    hook = p2p_guard_hook_exists(protocol) if chain else False
    rules = p2p_guard_iptables(protocol, ['-S', P2P_GUARD_CHAIN]) if chain else {'ok': True, 'output': ''}
    rule_lines = [line for line in (rules.get('output') or '').splitlines() if line.strip()]
    return {
        'protocol': protocol,
        'title': p['title'],
        'container': p['container'],
        'interface': p['interface'],
        'available': bool(state.get('available')),
        'chain': chain,
        'hook': hook,
        'active': chain and hook,
        'rules_count': max(0, len([line for line in rule_lines if line.startswith('-A ')])),
        'rules': rule_lines[:80],
        'error': '' if rules.get('ok', True) else rules.get('output', ''),
    }


def p2p_guard_status_payload() -> dict:
    settings = p2p_guard_settings()
    protocols = {protocol: p2p_guard_status_for(protocol) for protocol in PROTOCOLS}
    return {'ok': True, 'settings': settings, 'protocols': protocols}


def p2p_guard_rule_args(iface: str, settings: dict) -> list[list[str]]:
    rules = [
        ['-N', P2P_GUARD_CHAIN],
        ['-F', P2P_GUARD_CHAIN],
        ['-I', 'FORWARD', '1', '-i', iface, '-j', P2P_GUARD_CHAIN],
        ['-I', 'FORWARD', '1', '-o', iface, '-j', P2P_GUARD_CHAIN],
    ]
    for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'):
        rules.append(['-A', P2P_GUARD_CHAIN, '-d', cidr, '-j', 'RETURN'])
    for proto_name in ('tcp', 'udp'):
        rules.append(['-A', P2P_GUARD_CHAIN, '-p', proto_name, '-m', 'multiport', '--dports', P2P_GUARD_PORTS, '-j', 'REJECT'])
    for signature in P2P_GUARD_SIGNATURES:
        for proto_name in ('tcp', 'udp'):
            rules.append(['-A', P2P_GUARD_CHAIN, '-p', proto_name, '-m', 'string', '--algo', 'bm', '--string', signature, '-j', 'REJECT'])
    if settings.get('mode') == 'strict':
        allowed = p2p_guard_normalize_ports(settings.get('allow_udp_ports') or '53,123,443')
        rules.append(['-A', P2P_GUARD_CHAIN, '-p', 'udp', '-m', 'multiport', '--dports', allowed, '-j', 'RETURN'])
        rules.append(['-A', P2P_GUARD_CHAIN, '-p', 'udp', '-j', 'REJECT'])
    rules.append(['-A', P2P_GUARD_CHAIN, '-j', 'RETURN'])
    return rules


def p2p_guard_script_text(protocol: str, settings: dict) -> str:
    iface = PROTOCOLS[protocol]['interface']
    lines = [
        '#!/bin/sh',
        'set -u',
        f'CHAIN={shlex.quote(P2P_GUARD_CHAIN)}',
        f'IFACE={shlex.quote(iface)}',
        'iptables -N "$CHAIN" 2>/dev/null || true',
        'while iptables -C FORWARD -i "$IFACE" -j "$CHAIN" 2>/dev/null; do iptables -D FORWARD -i "$IFACE" -j "$CHAIN" || break; done',
        'while iptables -C FORWARD -o "$IFACE" -j "$CHAIN" 2>/dev/null; do iptables -D FORWARD -o "$IFACE" -j "$CHAIN" || break; done',
        'iptables -F "$CHAIN"',
    ]
    for args in p2p_guard_rule_args(iface, settings):
        if args[0] in ('-N', '-F'):
            continue
        lines.append('iptables ' + ' '.join(shlex.quote(arg) for arg in args))
    return '\n'.join(lines) + '\n'


def p2p_guard_install_script(protocol: str, settings: dict) -> None:
    p = proto(protocol)
    container = dc().containers.get(p['container'])
    put_container_text_file(container, '/opt/amnezia/3wg-p2p-guard.sh', p2p_guard_script_text(protocol, settings), mode=0o755)
    ensure_protocol_autostart(protocol)


def p2p_guard_remove_script(protocol: str) -> None:
    p2p_guard_exec(protocol, ['sh', '-lc', 'rm -f /opt/amnezia/3wg-p2p-guard.sh'])
    try:
        ensure_protocol_autostart(protocol)
    except Exception:
        pass


def p2p_guard_reset_protocol(protocol: str) -> dict:
    iface = PROTOCOLS[protocol]['interface']
    # Delete all matching hooks; Docker/container restarts can occasionally leave duplicates.
    while p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])['ok']:
        p2p_guard_iptables(protocol, ['-D', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])
    while p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])['ok']:
        p2p_guard_iptables(protocol, ['-D', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])
    p2p_guard_iptables(protocol, ['-F', P2P_GUARD_CHAIN])
    p2p_guard_iptables(protocol, ['-X', P2P_GUARD_CHAIN])
    p2p_guard_remove_script(protocol)
    return p2p_guard_status_for(protocol)


def p2p_guard_apply_protocol(protocol: str, settings: dict) -> dict:
    iface = PROTOCOLS[protocol]['interface']
    p2p_guard_iptables(protocol, ['-N', P2P_GUARD_CHAIN])
    p2p_guard_iptables(protocol, ['-F', P2P_GUARD_CHAIN], check=True)
    while p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])['ok']:
        p2p_guard_iptables(protocol, ['-D', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])
    while p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])['ok']:
        p2p_guard_iptables(protocol, ['-D', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])
    p2p_guard_iptables(protocol, ['-I', 'FORWARD', '1', '-i', iface, '-j', P2P_GUARD_CHAIN], check=True)
    p2p_guard_iptables(protocol, ['-I', 'FORWARD', '1', '-o', iface, '-j', P2P_GUARD_CHAIN], check=True)
    for args in p2p_guard_rule_args(iface, settings):
        if args[0] in ('-N', '-F', '-I'):
            continue
        p2p_guard_iptables(protocol, args)
    p2p_guard_install_script(protocol, settings)
    return p2p_guard_status_for(protocol)


def p2p_guard_apply_all(settings: dict) -> dict:
    result = {}
    for protocol in PROTOCOLS:
        try:
            result[protocol] = p2p_guard_apply_protocol(protocol, settings) if settings.get('enabled') else p2p_guard_reset_protocol(protocol)
        except Exception as e:
            status = p2p_guard_status_for(protocol)
            status['error'] = str(e)
            result[protocol] = status
    return result


@app.get('/api/p2p-guard')
def api_p2p_guard_get(user=Depends(api_require_admin)):
    return p2p_guard_status_payload()


@app.patch('/api/p2p-guard')
async def api_p2p_guard_update(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    before = p2p_guard_settings()
    settings = p2p_guard_save_settings({
        'enabled': bool(data.get('enabled')),
        'mode': data.get('mode') or before.get('mode') or 'soft',
        'allow_udp_ports': data.get('allow_udp_ports') or before.get('allow_udp_ports') or '53,123,443',
    })
    protocols = p2p_guard_apply_all(settings)
    api_audit_log(request, user, 'p2p_guard.update', 'security', 'p2p_guard', 'P2P Guard', {'before': before, 'after': settings})
    telegram_notify(
        'P2P Guard обновлён',
        [f"Режим: {'enabled' if settings['enabled'] else 'disabled'} / {settings['mode']}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'settings': settings, 'protocols': protocols}


@app.post('/api/p2p-guard/apply')
async def api_p2p_guard_apply(request: Request, user=Depends(api_require_admin)):
    settings = p2p_guard_settings()
    protocols = p2p_guard_apply_all(settings)
    api_audit_log(request, user, 'p2p_guard.apply', 'security', 'p2p_guard', 'P2P Guard', {'settings': settings})
    return {'ok': True, 'settings': settings, 'protocols': protocols}
# === 3WG P2P GUARD API END ===

# === 3WG REACT API END ===

# === 3WG SYSTEM STATUS API START ===
import shutil as _shutil

def _read_proc_stat():
    with open('/proc/stat') as f:
        parts = f.readline().split()
    vals = [int(x) for x in parts[1:11]]
    idle = vals[3] + vals[4]
    total = sum(vals)
    return idle, total


def _read_proc_net_dev() -> list[dict]:
    interfaces = []
    try:
        with open('/proc/net/dev') as f:
            lines = f.read().splitlines()[2:]
        for line in lines:
            name, values = line.split(':', 1)
            parts = values.split()
            iface = name.strip()
            if iface == 'lo' or len(parts) < 16:
                continue
            interfaces.append({
                'name': iface,
                'rx': int(parts[0]),
                'rx_packets': int(parts[1]),
                'tx': int(parts[8]),
                'tx_packets': int(parts[9]),
            })
    except Exception:
        pass
    return interfaces


def _read_disk_mounts() -> list[dict]:
    mounts = []
    seen = set()
    allowed = {'ext2', 'ext3', 'ext4', 'xfs', 'btrfs', 'zfs', 'overlay'}
    try:
        with open('/proc/mounts') as f:
            rows = f.read().splitlines()
        for row in rows:
            parts = row.split()
            if len(parts) < 3:
                continue
            device, mountpoint, fstype = parts[:3]
            if fstype not in allowed or mountpoint in seen:
                continue
            if mountpoint.startswith(('/proc', '/sys', '/dev', '/run')):
                continue
            seen.add(mountpoint)
            try:
                usage = _shutil.disk_usage(mountpoint)
            except OSError:
                continue
            total = int(usage.total)
            used = int(usage.used)
            mounts.append({
                'device': device,
                'mountpoint': mountpoint,
                'fstype': fstype,
                'total': total,
                'used': used,
                'free': int(usage.free),
                'percent': round(used / total * 100, 1) if total else 0.0,
            })
    except Exception:
        pass
    mounts.sort(key=lambda item: (item['mountpoint'] != '/', item['mountpoint']))
    return mounts[:8]


def _read_top_processes(limit: int = 8) -> list[dict]:
    processes = []
    page_size = os.sysconf('SC_PAGE_SIZE') if hasattr(os, 'sysconf') else 4096
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            statm = (entry / 'statm').read_text(encoding='utf-8').split()
            rss = int(statm[1]) * page_size if len(statm) > 1 else 0
            cmdline = (entry / 'cmdline').read_bytes().replace(b'\x00', b' ').decode('utf-8', errors='replace').strip()
            name = cmdline or (entry / 'comm').read_text(encoding='utf-8', errors='replace').strip()
            if not name:
                continue
            processes.append({'pid': pid, 'name': name[:140], 'rss': int(rss)})
        except (OSError, ValueError):
            continue
    processes.sort(key=lambda item: item['rss'], reverse=True)
    return processes[:limit]


def _container_system_metric(name: str) -> dict:
    payload = {
        'name': name,
        'running': False,
        'status': 'missing',
        'image': '',
        'restart_count': 0,
        'ports': [],
        'cpu_percent': 0.0,
        'memory': {'usage': 0, 'limit': 0, 'percent': 0.0},
    }
    try:
        c = dc().containers.get(name)
        payload['status'] = c.status
        payload['running'] = c.status == 'running'
        payload['image'] = c.image.tags[0] if c.image.tags else c.image.short_id
        payload['restart_count'] = int(c.attrs.get('RestartCount') or 0)
        ports = c.attrs.get('NetworkSettings', {}).get('Ports') or {}
        payload['ports'] = [
            {'container': key, 'host': ', '.join(f"{p.get('HostIp', '')}:{p.get('HostPort', '')}".strip(':') for p in (value or []))}
            for key, value in sorted(ports.items())
        ]
    except Exception as exc:
        payload['status'] = f'error: {exc}'
    return payload


def _system_alerts(payload: dict, protocols: dict) -> list[dict]:
    alerts = []
    cpu = float(payload.get('cpu_percent') or 0)
    memory = float(payload.get('memory', {}).get('percent') or 0)
    disk = float(payload.get('disk', {}).get('percent') or 0)
    swap = float(payload.get('swap', {}).get('percent') or 0)
    if cpu >= 90:
        alerts.append({'level': 'fail', 'title': 'Высокая загрузка CPU', 'message': f'CPU сейчас {cpu}%'})
    elif cpu >= 75:
        alerts.append({'level': 'warn', 'title': 'CPU под нагрузкой', 'message': f'CPU сейчас {cpu}%'})
    if memory >= 90:
        alerts.append({'level': 'fail', 'title': 'Почти закончилась RAM', 'message': f'Используется {memory}%'})
    elif memory >= 80:
        alerts.append({'level': 'warn', 'title': 'Высокое использование RAM', 'message': f'Используется {memory}%'})
    if disk >= 90:
        alerts.append({'level': 'fail', 'title': 'Почти закончился диск', 'message': f'Занято {disk}%'})
    elif disk >= 80:
        alerts.append({'level': 'warn', 'title': 'Диск быстро заполняется', 'message': f'Занято {disk}%'})
    if swap >= 25:
        alerts.append({'level': 'warn', 'title': 'Используется swap', 'message': f'Swap занят на {swap}%'})
    for item in payload.get('containers') or []:
        if not item.get('running'):
            alerts.append({'level': 'fail', 'title': 'Контейнер не работает', 'message': f"{item.get('name')} status: {item.get('status')}"})
    for key, protocol in protocols.items():
        if not protocol.get('available'):
            alerts.append({'level': 'warn', 'title': 'VPN протокол недоступен', 'message': f"{protocol.get('title') or key}: {protocol.get('container')} / {protocol.get('interface')}"})
    if not alerts:
        alerts.append({'level': 'ok', 'title': 'Система в норме', 'message': 'Критичных предупреждений сейчас нет'})
    return alerts


def _system_network_totals(interfaces: list[dict]) -> dict:
    return {
        'rx': sum(int(item.get('rx') or 0) for item in interfaces),
        'tx': sum(int(item.get('tx') or 0) for item in interfaces),
    }


def _recent_cpu_average(current_cpu: float, minutes: int = 5) -> float:
    current = float(current_cpu or 0)
    since = int(time.time()) - max(1, int(minutes or 5)) * 60
    recent = []
    try:
        with db() as conn:
            rows = conn.execute(
                """
                SELECT cpu_percent
                FROM system_snapshots
                WHERE ts >= ?
                ORDER BY ts DESC
                LIMIT 8
                """,
                (since,),
            ).fetchall()
        recent = [float(row['cpu_percent'] or 0) for row in rows]
    except Exception:
        pass
    if not recent:
        return round(current, 1)
    recent_avg = sum(recent) / len(recent)
    return round(current * 0.7 + recent_avg * 0.3, 1)


def _record_system_snapshot(payload: dict, min_interval: int = 60) -> None:
    ts = int(payload.get('ts') or time.time())
    network_totals = _system_network_totals(payload.get('network', {}).get('interfaces') or [])
    containers = payload.get('containers') or []
    running = sum(1 for item in containers if item.get('running'))
    with db() as conn:
        last = conn.execute('SELECT ts FROM system_snapshots ORDER BY ts DESC LIMIT 1').fetchone()
        if last and ts - int(last['ts']) < min_interval:
            return
        conn.execute(
            """
            INSERT INTO system_snapshots(
                ts, cpu_percent, memory_percent, disk_percent, load_one,
                rx, tx, containers_running, containers_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                float(payload.get('cpu_percent') or payload.get('cpu', {}).get('percent') or 0),
                float(payload.get('memory', {}).get('percent') or 0),
                float(payload.get('disk', {}).get('percent') or 0),
                float(payload.get('load_average', {}).get('one') or 0),
                int(network_totals['rx']),
                int(network_totals['tx']),
                int(running),
                int(len(containers)),
            ),
        )
        cutoff = ts - 60 * 60 * 24 * 14
        conn.execute('DELETE FROM system_snapshots WHERE ts < ?', (cutoff,))
        conn.commit()


def _system_history_payload(hours: int = 24) -> dict:
    hours = max(1, min(int(hours or 24), 24 * 14))
    since = int(time.time()) - hours * 3600
    with db() as conn:
        rows = conn.execute(
            """
            SELECT ts, cpu_percent, memory_percent, disk_percent, load_one, rx, tx, containers_running, containers_total
            FROM system_snapshots
            WHERE ts >= ?
            ORDER BY ts ASC
            """,
            (since,),
        ).fetchall()
    points = []
    prev = None
    for row in rows:
        ts = int(row['ts'])
        rx_rate = 0.0
        tx_rate = 0.0
        if prev:
            dt = max(1, ts - int(prev['ts']))
            rx_rate = max(0.0, (int(row['rx']) - int(prev['rx'])) / dt)
            tx_rate = max(0.0, (int(row['tx']) - int(prev['tx'])) / dt)
        points.append({
            'ts': ts,
            'cpu': round(float(row['cpu_percent']), 2),
            'memory': round(float(row['memory_percent']), 2),
            'disk': round(float(row['disk_percent']), 2),
            'load': round(float(row['load_one']), 2),
            'rx': int(row['rx']),
            'tx': int(row['tx']),
            'rx_rate': round(rx_rate, 2),
            'tx_rate': round(tx_rate, 2),
            'containers_running': int(row['containers_running']),
            'containers_total': int(row['containers_total']),
        })
        prev = row
    return {'ok': True, 'hours': hours, 'points': points}


@app.get('/api/node/system')
def api_node_system(user=Depends(api_require_auth)):
    # CPU: два замера /proc/stat с паузой
    idle1, total1 = _read_proc_stat()
    time.sleep(1.0)
    idle2, total2 = _read_proc_stat()
    dt = total2 - total1
    cpu_percent = round((1 - (idle2 - idle1) / dt) * 100, 1) if dt > 0 else 0.0

    # Память: /proc/meminfo (в контейнере отражает хост)
    mem = {}
    with open('/proc/meminfo') as f:
        for line in f:
            k, v = line.split(':', 1)
            mem[k] = int(v.strip().split()[0]) * 1024
    mem_total = mem.get('MemTotal', 0)
    mem_available = mem.get('MemAvailable', 0)
    mem_used = mem_total - mem_available
    mem_percent = round(mem_used / mem_total * 100, 1) if mem_total else 0.0
    swap_total = mem.get('SwapTotal', 0)
    swap_free = mem.get('SwapFree', 0)
    swap_used = swap_total - swap_free
    swap_percent = round(swap_used / swap_total * 100, 1) if swap_total else 0.0

    # Диск: корень контейнера (overlay поверх корня хоста)
    du = _shutil.disk_usage('/')
    mounts = _read_disk_mounts()
    disk_percent = round(du.used / du.total * 100, 1) if du.total else 0.0
    load = os.getloadavg()
    uptime_seconds = 0
    try:
        with open('/proc/uptime') as f:
            uptime_seconds = int(float(f.read().split()[0]))
    except Exception:
        pass
    cpu_count = os.cpu_count() or 1
    containers = [_container_system_metric(PANEL_CONTAINER)]
    for p in PROTOCOLS.values():
        containers.append(_container_system_metric(p['container']))
    protocols = {protocol: api_protocol_state(protocol) for protocol in PROTOCOLS}
    cpu_sustained = _recent_cpu_average(cpu_percent)

    payload = {
        'ok': True,
        'ts': int(time.time()),
        'hostname': os.uname().nodename,
        'uptime_seconds': uptime_seconds,
        'load_average': {'one': round(load[0], 2), 'five': round(load[1], 2), 'fifteen': round(load[2], 2)},
        'cpu': {'percent': cpu_sustained, 'current_percent': cpu_percent, 'cores': cpu_count},
        'cpu_percent': cpu_sustained,
        'cpu_percent_current': cpu_percent,
        'memory': {'total': mem_total, 'available': mem_available, 'used': mem_used, 'percent': mem_percent},
        'swap': {'total': swap_total, 'used': swap_used, 'free': swap_free, 'percent': swap_percent},
        'disk': {'total': du.total, 'used': du.used, 'free': du.free, 'percent': disk_percent, 'mounts': mounts},
        'network': {'interfaces': _read_proc_net_dev()},
        'containers': containers,
        'processes': _read_top_processes(),
    }
    payload['alerts'] = _system_alerts(payload, protocols)
    _record_system_snapshot(payload)
    return payload


@app.get('/api/node/system/history')
def api_node_system_history(hours: int = 24, user=Depends(api_require_auth)):
    return _system_history_payload(hours)
# === 3WG SYSTEM STATUS API END ===


# === 3WG NETWORK TOOLS API START ===
import subprocess as _subprocess


def _tool_target(value: str) -> str:
    target = str(value or '').strip().rstrip('.')
    if not target or len(target) > 253:
        raise HTTPException(status_code=400, detail='Введите IP-адрес или hostname')
    if any(ch.isspace() for ch in target) or '/' in target or ':' in target and target.count(':') == 1:
        raise HTTPException(status_code=400, detail='Некорректный target')
    try:
        return str(ipaddress.ip_address(target))
    except ValueError:
        pass
    if not re.match(r'^(?=.{1,253}$)([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])$', target):
        raise HTTPException(status_code=400, detail='Некорректный hostname')
    return target


def _tool_run(command: list[str], timeout: int = 20) -> dict:
    started = time.time()
    try:
        proc = _subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        output = ((proc.stdout or '') + (proc.stderr or '')).strip()
        lines = output.splitlines()[:120]
        return {
            'ok': proc.returncode == 0,
            'return_code': proc.returncode,
            'duration_ms': int((time.time() - started) * 1000),
            'command': ' '.join(shlex.quote(x) for x in command),
            'output': '\n'.join(lines),
            'truncated': len(output.splitlines()) > len(lines),
        }
    except _subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or '') + (exc.stderr or '')).strip()
        return {
            'ok': False,
            'return_code': 124,
            'duration_ms': int((time.time() - started) * 1000),
            'command': ' '.join(shlex.quote(x) for x in command),
            'output': output or 'Timeout',
            'truncated': False,
        }


def _tool_protocol(value: str | None) -> str | None:
    protocol = str(value or '').strip()
    if not protocol:
        return None
    if protocol not in PROTOCOLS:
        raise HTTPException(status_code=400, detail='Некорректный protocol')
    return protocol


def _tool_run_in_protocol(protocol: str | None, command: list[str], timeout: int = 20) -> dict:
    if not protocol:
        payload = _tool_run(command, timeout=timeout)
        payload['source'] = {'type': 'panel', 'label': PANEL_CONTAINER, 'protocol': None}
        return payload

    container_name = PROTOCOLS[protocol]['container']
    started = time.time()
    try:
        container = dc().containers.get(container_name)
        result = container.exec_run(command, stdout=True, stderr=True)
        raw = result.output.decode('utf-8', errors='replace') if isinstance(result.output, (bytes, bytearray)) else str(result.output or '')
        output = raw.strip()
        lines = output.splitlines()[:120]
        return {
            'ok': int(result.exit_code or 0) == 0,
            'return_code': int(result.exit_code or 0),
            'duration_ms': int((time.time() - started) * 1000),
            'command': f"{container_name}$ " + ' '.join(shlex.quote(x) for x in command),
            'output': '\n'.join(lines),
            'truncated': len(output.splitlines()) > len(lines),
            'source': {'type': 'protocol', 'label': container_name, 'protocol': protocol},
        }
    except Exception as exc:
        return {
            'ok': False,
            'return_code': 125,
            'duration_ms': int((time.time() - started) * 1000),
            'command': f"{container_name}$ " + ' '.join(shlex.quote(x) for x in command),
            'output': str(exc),
            'truncated': False,
            'source': {'type': 'protocol', 'label': container_name, 'protocol': protocol},
        }


@app.post('/api/tools/ping')
async def api_tools_ping(request: Request, user=Depends(api_require_admin)):
    payload = await api_read_payload(request)
    target = _tool_target(payload.get('target', ''))
    protocol = _tool_protocol(payload.get('protocol'))
    count = max(1, min(10, int(payload.get('count') or 4)))
    binary = 'ping' if protocol else _shutil.which('ping')
    if not binary:
        raise HTTPException(status_code=500, detail='ping не установлен в контейнере')
    return _tool_run_in_protocol(protocol, [binary, '-n', '-c', str(count), '-W', '2', target], timeout=count * 3 + 3)


@app.post('/api/tools/traceroute')
async def api_tools_traceroute(request: Request, user=Depends(api_require_admin)):
    payload = await api_read_payload(request)
    target = _tool_target(payload.get('target', ''))
    protocol = _tool_protocol(payload.get('protocol'))
    max_hops = max(3, min(30, int(payload.get('max_hops') or 20)))
    binary = 'traceroute' if protocol else _shutil.which('traceroute')
    if not binary:
        raise HTTPException(status_code=500, detail='traceroute не установлен в контейнере')
    return _tool_run_in_protocol(protocol, [binary, '-n', '-w', '2', '-q', '1', '-m', str(max_hops), target], timeout=max_hops * 3)
# === 3WG NETWORK TOOLS API END ===


# === 3WG API KEYS START ===
def api_key_valid(token: str) -> bool:
    return valid_api_key(DB_PATH, token)


init_api_keys(DB_PATH)


def _apikey_session_only(request: Request):
    """Управление ключами — только через cookie-сессию (не по самому ключу)."""
    cookie_token = request.cookies.get(SESSION_COOKIE)
    current = verify_user_session(cookie_token or "")
    if not current and cookie_token and secrets.compare_digest(cookie_token, make_session_token()):
        current = admin_user()
    if current and current.get('is_admin'):
        return current
    raise HTTPException(status_code=401, detail='Unauthorized')


@app.get('/api/apikeys')
def api_apikeys_list(user=Depends(_apikey_session_only)):
    return {'ok': True, 'keys': list_api_keys(DB_PATH)}


@app.post('/api/apikeys')
async def api_apikeys_create(request: Request, user=Depends(_apikey_session_only)):
    data = await api_read_payload(request)
    name = data.get('name', '')
    created = create_api_key(DB_PATH, name)
    token = str(created.get('token') or '')
    api_audit_log(
        request,
        user,
        'apikey.create',
        'api_key',
        created.get('id'),
        created.get('name') or name,
        {'token_masked': f"{token[:6]}...{token[-4:]}" if token else ''},
    )
    return {'ok': True, **created}


@app.delete('/api/apikeys/{key_id}')
def api_apikeys_delete(key_id: int, request: Request, user=Depends(_apikey_session_only)):
    before = next((k for k in list_api_keys(DB_PATH) if int(k.get('id') or 0) == int(key_id)), None)
    if not delete_api_key(DB_PATH, key_id):
        return api_error('Ключ не найден', status_code=404)
    api_audit_log(request, user, 'apikey.delete', 'api_key', key_id, before.get('name') if before else None, {'key': before or {}})
    return {'ok': True, 'deleted_id': key_id}


# === 3WG API KEYS END ===


# === 3WG MONITORING SETTINGS API START ===
def monitoring_enabled() -> bool:
    value = panel_setting_get("metrics_enabled")
    if value is None:
        return METRICS_ENABLED
    return value == "1"


def monitoring_token_hash() -> str:
    return panel_setting_get("metrics_token_hash", "") or ""


def monitoring_token_suffix() -> str:
    return panel_setting_get("metrics_token_suffix", "") or ""


def monitoring_token_configured() -> bool:
    return bool(monitoring_token_hash() or METRICS_TOKEN)


def monitoring_status_payload() -> dict:
    return {
        "ok": True,
        "enabled": monitoring_enabled(),
        "require_token": METRICS_REQUIRE_TOKEN,
        "token_configured": monitoring_token_configured(),
        "token_suffix": monitoring_token_suffix() or (METRICS_TOKEN[-6:] if METRICS_TOKEN else ""),
        "metrics_path": "/metrics",
        "auth_header": "Authorization: Bearer <token>",
        "env_token_present": bool(METRICS_TOKEN),
        "db_token_present": bool(monitoring_token_hash()),
    }


@app.get('/api/monitoring')
def api_monitoring_get(user=Depends(api_require_admin)):
    return monitoring_status_payload()


@app.patch('/api/monitoring')
async def api_monitoring_update(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    before = monitoring_status_payload()
    if "enabled" in data:
        panel_setting_set("metrics_enabled", "1" if bool(data.get("enabled")) else "0")
    after = monitoring_status_payload()
    if before != after:
        api_audit_log(request, user, 'monitoring.update', 'monitoring', 'settings', 'metrics', {'before': before, 'after': after})
    return after


@app.post('/api/monitoring/token')
def api_monitoring_token_create(request: Request, user=Depends(api_require_admin)):
    token = secrets.token_urlsafe(32)
    panel_setting_set("metrics_token_hash", password_hash(token))
    panel_setting_set("metrics_token_suffix", token[-6:])
    panel_setting_set("metrics_enabled", "1")
    payload = monitoring_status_payload()
    payload["token"] = token
    api_audit_log(request, user, 'monitoring.token.create', 'monitoring', 'token', 'metrics', {'suffix': token[-6:]})
    return payload


@app.delete('/api/monitoring/token')
def api_monitoring_token_delete(request: Request, user=Depends(api_require_admin)):
    panel_setting_set("metrics_token_hash", "")
    panel_setting_set("metrics_token_suffix", "")
    api_audit_log(request, user, 'monitoring.token.delete', 'monitoring', 'token', 'metrics')
    return monitoring_status_payload()
# === 3WG MONITORING SETTINGS API END ===


# === 3WG TELEGRAM SETTINGS API START ===
@app.get('/api/telegram')
def api_telegram_get(user=Depends(api_require_admin)):
    return telegram_status_payload()


@app.patch('/api/telegram')
async def api_telegram_update(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    before = telegram_status_payload()
    if "enabled" in data:
        panel_setting_set("telegram_enabled", "1" if bool(data.get("enabled")) else "0")
    if "bot_token" in data:
        token = str(data.get("bot_token", "")).strip()
        if token:
            panel_setting_set("telegram_bot_token", token)
        elif data.get("clear_token"):
            panel_setting_set("telegram_bot_token", "")
    if "chat_id" in data:
        panel_setting_set("telegram_chat_id", str(data.get("chat_id", "")).strip())
    after = telegram_status_payload()
    if before != after:
        api_audit_log(request, user, 'telegram.update', 'telegram', 'settings', 'notifications', {'before': before, 'after': after})
    return after


@app.post('/api/telegram/test')
def api_telegram_test(request: Request, user=Depends(api_require_admin)):
    if not telegram_configured():
        return api_error('Telegram bot token и chat id не настроены', status_code=400)
    ok = telegram_notify(
        "тестовое уведомление",
        [f"Сервер: {PANEL_HOST}", f"VPN endpoint: {VPN_ENDPOINT_HOST}", f"Пользователь: {user.get('username')}"],
        wait=True,
    )
    api_audit_log(request, user, 'telegram.test', 'telegram', 'settings', 'notifications', {'sent': ok})
    if not ok:
        return api_error('Telegram не принял сообщение. Проверьте token/chat id.', status_code=502)
    return telegram_status_payload()
# === 3WG TELEGRAM SETTINGS API END ===


# === 3WG PROMETHEUS METRICS START ===
def metrics_bool(value) -> int:
    return 1 if value else 0


def metrics_label(value) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def metrics_line(name: str, value, labels: dict | None = None) -> str:
    label_text = ""
    if labels:
        label_text = "{" + ",".join(f'{key}="{metrics_label(val)}"' for key, val in labels.items()) + "}"
    return f"{name}{label_text} {value}"


def metrics_authorized(request: Request) -> bool:
    stored_hash = monitoring_token_hash()
    if not METRICS_REQUIRE_TOKEN and not METRICS_TOKEN and not stored_hash:
        return True
    tokens = []
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        tokens.append(auth.split(" ", 1)[1].strip())
    header_token = request.headers.get("x-metrics-token", "")
    if header_token:
        tokens.append(header_token)
    query_token = request.query_params.get("token", "")
    if query_token:
        tokens.append(query_token)
    for token in tokens:
        if METRICS_TOKEN and secrets.compare_digest(token, METRICS_TOKEN):
            return True
        if stored_hash and password_verify(token, stored_hash):
            return True
    return False


def docker_container_metric(name: str, role: str) -> dict:
    item = {"name": name, "role": role, "exists": 0, "running": 0, "status": "missing"}
    try:
        container = dc().containers.get(name)
        item["exists"] = 1
        item["status"] = getattr(container, "status", "unknown") or "unknown"
        item["running"] = 1 if item["status"] == "running" else 0
    except Exception:
        pass
    return item


def metrics_int(value, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def prometheus_metrics_payload() -> str:
    now = int(time.time())
    live, live_errors = api_live_maps()
    protocols = {protocol: api_protocol_state(protocol) for protocol in PROTOCOLS}

    with db() as conn:
        clients_total = int(conn.execute("SELECT COUNT(*) AS n FROM clients WHERE COALESCE(deleted_at, 0) = 0").fetchone()["n"])
        clients_enabled = int(conn.execute("SELECT COUNT(*) AS n FROM clients WHERE COALESCE(deleted_at, 0) = 0 AND enabled = 1").fetchone()["n"])
        clients_disabled = int(conn.execute("SELECT COUNT(*) AS n FROM clients WHERE COALESCE(deleted_at, 0) = 0 AND enabled = 0").fetchone()["n"])
        users_total = int(conn.execute("SELECT COUNT(*) AS n FROM panel_users").fetchone()["n"])
        users_enabled = int(conn.execute("SELECT COUNT(*) AS n FROM panel_users WHERE enabled = 1").fetchone()["n"])
        categories_total = int(conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"])

    lines = [
        "# HELP threewg_panel_build_info 3WG Core build information.",
        "# TYPE threewg_panel_build_info gauge",
        metrics_line("threewg_panel_build_info", 1, {"version": APP_VERSION, "panel_host": PANEL_HOST, "endpoint_host": VPN_ENDPOINT_HOST}),
        "# HELP threewg_panel_scrape_timestamp_seconds Last successful metrics scrape timestamp.",
        "# TYPE threewg_panel_scrape_timestamp_seconds gauge",
        metrics_line("threewg_panel_scrape_timestamp_seconds", now),
        "# HELP threewg_panel_clients_total Active clients in panel database.",
        "# TYPE threewg_panel_clients_total gauge",
        metrics_line("threewg_panel_clients_total", clients_total),
        "# HELP threewg_panel_clients_enabled Enabled clients in panel database.",
        "# TYPE threewg_panel_clients_enabled gauge",
        metrics_line("threewg_panel_clients_enabled", clients_enabled),
        "# HELP threewg_panel_clients_disabled Disabled clients in panel database.",
        "# TYPE threewg_panel_clients_disabled gauge",
        metrics_line("threewg_panel_clients_disabled", clients_disabled),
        "# HELP threewg_panel_users_total Panel users stored in database, excluding env admin.",
        "# TYPE threewg_panel_users_total gauge",
        metrics_line("threewg_panel_users_total", users_total),
        "# HELP threewg_panel_users_enabled Enabled panel users stored in database.",
        "# TYPE threewg_panel_users_enabled gauge",
        metrics_line("threewg_panel_users_enabled", users_enabled),
        "# HELP threewg_panel_categories_total Client categories in panel database.",
        "# TYPE threewg_panel_categories_total gauge",
        metrics_line("threewg_panel_categories_total", categories_total),
        "# HELP threewg_panel_protocol_available Protocol command is reachable inside configured container.",
        "# TYPE threewg_panel_protocol_available gauge",
        "# HELP threewg_panel_protocol_container_running Configured protocol Docker container is running.",
        "# TYPE threewg_panel_protocol_container_running gauge",
        "# HELP threewg_panel_protocol_peers_total Live peers reported by protocol tool.",
        "# TYPE threewg_panel_protocol_peers_total gauge",
        "# HELP threewg_panel_protocol_peers_online Peers with recent handshake inside online window.",
        "# TYPE threewg_panel_protocol_peers_online gauge",
        "# HELP threewg_panel_protocol_rx_bytes Total received bytes reported by protocol tool.",
        "# TYPE threewg_panel_protocol_rx_bytes gauge",
        "# HELP threewg_panel_protocol_tx_bytes Total transmitted bytes reported by protocol tool.",
        "# TYPE threewg_panel_protocol_tx_bytes gauge",
        "# HELP threewg_panel_protocol_listen_port Configured or detected UDP listen port.",
        "# TYPE threewg_panel_protocol_listen_port gauge",
        "# HELP threewg_panel_protocol_error Protocol live collection error flag.",
        "# TYPE threewg_panel_protocol_error gauge",
    ]

    for protocol, p in PROTOCOLS.items():
        state = protocols.get(protocol, {})
        container = docker_container_metric(p["container"], f"protocol:{protocol}")
        rows = list((live.get(protocol) or {}).values())
        online = sum(1 for item in rows if api_recent_handshake(item)[0])
        rx = sum(int(item.get("rx") or 0) for item in rows)
        tx = sum(int(item.get("tx") or 0) for item in rows)
        labels = {
            "protocol": protocol,
            "title": p["title"],
            "interface": p["interface"],
            "container": p["container"],
        }
        lines.extend([
            metrics_line("threewg_panel_protocol_available", metrics_bool(state.get("available")), labels),
            metrics_line("threewg_panel_protocol_container_running", container["running"], {**labels, "status": container["status"]}),
            metrics_line("threewg_panel_protocol_peers_total", len(rows), labels),
            metrics_line("threewg_panel_protocol_peers_online", online, labels),
            metrics_line("threewg_panel_protocol_rx_bytes", rx, labels),
            metrics_line("threewg_panel_protocol_tx_bytes", tx, labels),
            metrics_line("threewg_panel_protocol_listen_port", metrics_int(interface_listen_port(protocol) or p["port"]), labels),
            metrics_line("threewg_panel_protocol_error", metrics_bool(protocol in live_errors), {**labels, "reason": live_errors.get(protocol, "")}),
        ])

    lines.extend([
        "# HELP threewg_panel_docker_container_running Docker container running state for important containers.",
        "# TYPE threewg_panel_docker_container_running gauge",
    ])
    seen_containers = set()
    for role, name in [("panel", PANEL_CONTAINER), *[(f"protocol:{protocol}", p["container"]) for protocol, p in PROTOCOLS.items()]]:
        if name in seen_containers:
            continue
        seen_containers.add(name)
        item = docker_container_metric(name, role)
        lines.append(metrics_line("threewg_panel_docker_container_running", item["running"], {"name": name, "role": role, "status": item["status"]}))

    return "\n".join(lines) + "\n"


@app.get("/metrics")
def prometheus_metrics(request: Request):
    if not monitoring_enabled():
        raise HTTPException(status_code=404, detail="Metrics disabled")
    if not metrics_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return PlainTextResponse(prometheus_metrics_payload(), media_type="text/plain; version=0.0.4; charset=utf-8")
# === 3WG PROMETHEUS METRICS END ===

# === 3WG DASHBOARD MODEL API START ===
# API-модель экрана для будущего React: React должен повторять текущий красивый /.

def api_peer_view_model(peer: dict) -> dict:
    actions = [
        {'key': 'open', 'label': 'Открыть', 'kind': 'primary', 'url': peer['links']['html']},
        {'key': 'download', 'label': 'CONF', 'kind': 'download', 'url': peer['links']['download']},
        {'key': 'qr', 'label': 'QR', 'kind': 'qr', 'url': peer['links']['qr_native_png']},
    ]
    if peer['links'].get('download_vpn'):
        actions.insert(2, {'key': 'download_vpn', 'label': 'VPN', 'kind': 'download', 'url': peer['links']['download_vpn']})
    if peer['links'].get('qr_amnezia_vpn_png'):
        actions.append({'key': 'qr_amnezia_vpn', 'label': 'QR VPN', 'kind': 'qr', 'url': peer['links']['qr_amnezia_vpn_png']})
    if peer.get('enabled'):
        actions.append({'key': 'disable', 'label': 'Отключить', 'kind': 'block', 'url': peer['links']['disable']})
    else:
        actions.append({'key': 'enable', 'label': 'Включить', 'kind': 'enable', 'url': peer['links']['enable']})
    actions.append({'key': 'delete', 'label': 'Удалить', 'kind': 'danger', 'url': peer['links']['delete']})

    return {
        **peer,
        'ui': {
            'state': 'online' if peer['status'] == 'active' else ('blocked' if peer['status'] == 'disabled' else 'offline'),
            'status_label': 'ACTIVE' if peer['status'] == 'active' else ('BLOCKED' if peer['status'] == 'disabled' else 'OFFLINE'),
            'status_tone': 'success' if peer['status'] == 'active' else ('warning' if peer['status'] == 'disabled' else 'muted'),
            'actions': actions,
        },
    }


def api_protocol_view_model(protocol: dict) -> dict:
    return {
        **protocol,
        'ui': {
            'state': 'online' if protocol.get('available') else 'offline',
            'status_label': 'ONLINE' if protocol.get('available') else 'OFFLINE',
            'status_tone': 'success' if protocol.get('available') else 'danger',
            'subtitle': f"{protocol.get('container')} / {protocol.get('interface')}",
            'endpoint_label': protocol.get('endpoint'),
        },
    }


def api_dashboard_payload(user: dict) -> dict:
    live, errors = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    protocols = {protocol: api_protocol_state(protocol) for protocol in PROTOCOLS}
    where, params = api_user_where(user, 'c')

    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT c.*, cat.name AS category_name, u.username AS owner_username
            FROM clients c
            LEFT JOIN categories cat ON cat.id = c.category_id
            LEFT JOIN panel_users u ON u.id = c.owner_id
            WHERE COALESCE(c.deleted_at, 0) = 0
            {where}
            ORDER BY c.id DESC
            """,
            params,
        ).fetchall()

    peers = [api_peer_payload(c, live=live, counters=counters) for c in rows]
    online = sum(1 for p in peers if p.get('status') == 'active')
    available_protocols = [p for p in protocols.values() if p.get('available')]
    primary_protocol = available_protocols[0]['title'] if available_protocols else 'нет активного протокола'

    return {
        'ok': True,
        'screen': 'dashboard',
        'title': '3WG Core',
        'subtitle': f"Node / {PANEL_HOST}",
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'theme': {'name': 'classic-neo', 'source': 'legacy-html-design'},
        'user': user,
        'quota': api_user_quota(user),
        'navigation': [
            {'section': 'Обзор', 'items': [{'key': 'home', 'label': 'Главная', 'href': '/', 'active': True}]},
            {'section': 'Управление', 'items': [
                {'key': 'awg_status', 'label': 'AWG status', 'action': 'status_modal', 'protocol': 'amneziawg'},
                {'key': 'wg_status', 'label': 'WG status', 'action': 'status_modal', 'protocol': 'wireguard'},
            ]},
            {'section': 'Система', 'items': [{'key': 'logout', 'label': 'Выход', 'href': '/logout'}]},
        ],
        'cards': [
            {'key': 'clients_total', 'label': 'Клиентов', 'value': len(peers), 'tone': 'success'},
            {'key': 'peers_total', 'label': "Peer'ов", 'value': sum(len(pm) for pm in live.values()), 'tone': 'info'},
            {'key': 'peers_online', 'label': 'Online', 'value': online, 'tone': 'success'},
            {'key': 'primary_protocol', 'label': 'Основной протокол', 'value': primary_protocol, 'tone': 'accent'},
        ],
        'protocols': [api_protocol_view_model(p) for p in protocols.values()],
        'categories': api_categories_payload() if user.get('is_admin') else [],
        'peers': [api_peer_view_model(p) for p in peers],
        'errors': errors,
        'actions': {
            'refresh': {'method': 'GET', 'url': '/api/dashboard'},
            'create_peer': {'method': 'POST', 'url': '/api/peers'},
        },
    }


@app.get('/api/dashboard')
def api_dashboard(user=Depends(api_require_auth)):
    return api_dashboard_payload(user)


@app.get('/api/ui/dashboard')
def api_ui_dashboard(user=Depends(api_require_auth)):
    return api_dashboard_payload(user)
# === 3WG DASHBOARD MODEL API END ===
