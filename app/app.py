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
import struct
import time
import zlib
from pathlib import Path

import docker
import qrcode
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials


APP_DIR = Path("/app")
DATA_DIR = APP_DIR / "data"
CLIENTS_DIR = APP_DIR / "clients"
BACKUPS_DIR = APP_DIR / "backups"
DB_PATH = DATA_DIR / "panel.db"

PANEL_USER = os.getenv("PANEL_USER", "admin")
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "admin")
ENDPOINT_HOST = os.getenv("ENDPOINT_HOST", "cz-prg-01.nodax.eu")
DNS_SERVERS = os.getenv("DNS_SERVERS", "1.1.1.1, 1.0.0.1")
SESSION_SECRET = os.getenv("SESSION_SECRET", PANEL_PASSWORD + ENDPOINT_HOST)
SESSION_COOKIE = "3wg_session"
RUNTIME_CACHE = {}
RUNTIME_CACHE_TTL_SECONDS = float(os.getenv("RUNTIME_CACHE_TTL_SECONDS", "3"))
PORT_CACHE_TTL_SECONDS = float(os.getenv("PORT_CACHE_TTL_SECONDS", "30"))

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
    "Jc": "5",
    "Jmin": "10",
    "Jmax": "50",
    "S1": "19",
    "S2": "68",
    "S3": "45",
    "S4": "5",
    "H1": "19739311-1855633582",
    "H2": "2039341897-2052921390",
    "H3": "2097137237-2108606057",
    "H4": "2135860310-2139015251",
}

# Важно: для мобильного AmneziaWG убираем <r 2>, оставляем чистый <b ...>
AWG_I1_NATIVE = "<b 0x858000010001000000000669636c6f756403636f6d0000010001c00c000100010000105a00044d583737>"

app = FastAPI(title="3WG Panel")
security = HTTPBasic(auto_error=False)



def make_session_token() -> str:
    msg = f"{PANEL_USER}:{PANEL_PASSWORD}".encode("utf-8")
    key = SESSION_SECRET.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def auth(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    cookie_token = request.cookies.get(SESSION_COOKIE)

    if cookie_token and secrets.compare_digest(cookie_token, make_session_token()):
        return PANEL_USER

    if credentials is not None:
        ok_user = secrets.compare_digest(credentials.username, PANEL_USER)
        ok_pass = secrets.compare_digest(credentials.password, PANEL_PASSWORD)
        if ok_user and ok_pass:
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
<title>3WG Panel Login</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  --bg:#070b12;
  --card:#101827;
  --line:#283247;
  --text:#e9eefc;
  --muted:#8d9ab0;
  --orange:#f4a340;
  --green:#14f0a0;
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
    radial-gradient(circle at 80% 70%, rgba(20,240,160,.09), transparent 28%),
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
  border:1px solid rgba(20,240,160,.4);
  background:rgba(20,240,160,.08);
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
    <div class="badge">SECURE NODE PANEL</div>
    <div class="logo">3WG Panel</div>
    <div class="sub">Управление WireGuard / AmneziaWG peer'ами</div>
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

    ok_user = secrets.compare_digest(username, PANEL_USER)
    ok_pass = secrets.compare_digest(password, PANEL_PASSWORD)

    if not (ok_user and ok_pass):
        return HTMLResponse(login_html("Неверный логин или пароль"), status_code=401)

    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE,
        make_session_token(),
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
    return f"{ENDPOINT_HOST}:{docker_published_udp_port(protocol)}"


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
        conn.commit()


@app.on_event("startup")
def startup():
    init_db()


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


def used_ips(protocol: str):
    used = set()

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
Address = {ip_cidr}
DNS = {DNS_SERVERS}
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

    text += f"""
[Peer]
PublicKey = {srv_pub}
PresharedKey = {psk}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = {client_endpoint(protocol)}
PersistentKeepalive = 25
"""

    return text


def create_client(name: str, protocol: str) -> int:
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
            (name, protocol, ip_cidr, private_key, public_key, preshared_key, config_path, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (name, protocol, ip_cidr, private_key, public_key, psk, str(path), ts),
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
        "hostName": ENDPOINT_HOST,
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
        "hostName": ENDPOINT_HOST,
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
  --bg:#080d14;
  --card:#111822;
  --card2:#0d131c;
  --line:#2a3441;
  --text:#dce7f5;
  --muted:#7e8ba0;
  --green:#14f0a0;
  --cyan:#27d9ff;
  --red:#ff5b6c;
  --yellow:#f8b62d;
  --orange:#f4a340;
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
code,pre{{background:#070c13;color:#e9eefc;border:1px solid var(--line);border-radius:12px}}
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
<h1>3WG Panel</h1>

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
<p class="muted">Endpoint host: <code>{html.escape(ENDPOINT_HOST)}</code></p>
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
    return HTMLResponse(page("3WG Panel", body))


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
<p>Endpoint: <code>{html.escape(ENDPOINT_HOST)}:{html.escape(p["port"])}</code></p>
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
  --bg:#080d14;
  --card:#111822;
  --card2:#0d131c;
  --line:#2a3441;
  --text:#dce7f5;
  --muted:#7e8ba0;
  --green:#14f0a0;
  --cyan:#27d9ff;
  --red:#ff5b6c;
  --yellow:#f8b62d;
  --orange:#f4a340;
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
code,pre{{background:#070c13;color:#e9eefc;border:1px solid var(--line);border-radius:12px}}
code{{padding:3px 7px}}
pre{{padding:16px;overflow-x:auto;white-space:pre-wrap;line-height:1.45}}
.muted{{color:var(--muted)}}
.ok{{color:var(--green);font-weight:900}}
.bad{{color:var(--red);font-weight:900}}
.dot{{display:inline-block;width:12px;height:12px;border-radius:50%;background:var(--yellow);box-shadow:0 0 16px rgba(248,182,45,.5);margin-right:8px}}
.dot-green{{background:var(--green);box-shadow:0 0 16px rgba(20,240,160,.5)}}
.dot-red{{background:var(--red)}}
.proto{{padding:5px 10px;border-radius:999px;background:#1d2a3b;color:#eaf4ff;font-weight:900}}
.proto-awg{{background:#102d39;color:#30dfff}}
.proto-wg{{background:#1b2d20;color:#4cff94}}
.qrgrid{{display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:18px}}
.qrbox{{background:#0c131d;border:1px solid var(--line);border-radius:18px;padding:18px}}
.qrbox img{{background:#fff;padding:14px;border-radius:14px;max-width:360px;width:100%}}

.modal-bg{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:9999;padding:30px;overflow:auto}}
.modal-bg.open{{display:block}}
.modal-window{{max-width:1350px;margin:20px auto;background:#0b111b;border:1px solid #344052;border-radius:22px;box-shadow:0 30px 100px rgba(0,0,0,.65);overflow:hidden}}
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
  --neo-bg: #080d14;
  --neo-bg2: #0b111b;
  --neo-sidebar: #070c13;
  --neo-card: #111a26;
  --neo-card2: #0e1621;
  --neo-border: #263342;
  --neo-border2: #314255;
  --neo-text: #e8f0fb;
  --neo-muted: #8c9aac;
  --neo-muted2: #667489;
  --neo-green: #14f0a0;
  --neo-green2: #0bbd80;
  --neo-cyan: #25d9ff;
  --neo-blue: #4a7cff;
  --neo-red: #ff5b73;
  --neo-red2: #4a121d;
  --neo-yellow: #f8b62d;
  --neo-orange: #f4a340;
  --neo-shadow: 0 18px 70px rgba(0,0,0,.38);
}

html {
  background: var(--neo-bg);
}

body {
  background:
    radial-gradient(circle at 20% -10%, rgba(37,217,255,.08), transparent 32%),
    radial-gradient(circle at 100% 0%, rgba(20,240,160,.06), transparent 28%),
    linear-gradient(180deg, #080d14 0%, #0a1018 100%) !important;
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
    linear-gradient(180deg, rgba(9,16,25,.98), rgba(6,10,16,.98)),
    radial-gradient(circle at top, rgba(37,217,255,.08), transparent 38%);
  border-right: 1px solid rgba(49,66,85,.75);
  z-index: 1000;
  padding: 18px 14px;
  box-shadow: 18px 0 60px rgba(0,0,0,.25);
}

.neo-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 6px 8px 22px;
  border-bottom: 1px dashed rgba(37,217,255,.18);
  margin-bottom: 18px;
}

.neo-brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 11px;
  display: grid;
  place-items: center;
  background: rgba(20,240,160,.1);
  color: var(--neo-green);
  border: 1px solid rgba(20,240,160,.35);
  font-weight: 900;
  box-shadow: 0 0 22px rgba(20,240,160,.12);
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
  color: #b9c5d6;
  text-decoration: none;
  font-weight: 700;
  font-size: 14px;
  margin-bottom: 4px;
  border: 1px solid transparent;
}

.neo-nav a:hover,
.neo-nav a.active {
  background: rgba(20,240,160,.08);
  border-color: rgba(20,240,160,.22);
  color: #eafff6;
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
  background: rgba(37,217,255,.08);
  border: 1px solid rgba(37,217,255,.25);
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
  border: 1px solid rgba(49,66,85,.9);
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
  border: 1px solid rgba(49,66,85,.75) !important;
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
  background: rgba(20,240,160,.08);
  border: 1px solid rgba(20,240,160,.18);
}

.stat .n {
  color: var(--neo-green) !important;
  font-size: 24px !important;
  text-shadow: 0 0 18px rgba(20,240,160,.22);
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
  border-color: rgba(37,217,255,.65) !important;
  box-shadow: 0 0 0 4px rgba(37,217,255,.08) !important;
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
  background: rgba(9,16,25,.66);
  border: 1px solid rgba(49,66,85,.55);
}

tbody tr:hover {
  background: rgba(14,26,39,.96) !important;
}

tbody td {
  border-bottom: 1px solid rgba(49,66,85,.45) !important;
  padding: 13px 10px !important;
}

tbody td:first-child {
  border-left: 1px solid rgba(49,66,85,.45);
  border-radius: 12px 0 0 12px;
}

tbody td:last-child {
  border-right: 1px solid rgba(49,66,85,.45);
  border-radius: 0 12px 12px 0;
}

code {
  background: #070d15 !important;
  border: 1px solid rgba(49,66,85,.72) !important;
  color: #e8f3ff !important;
  border-radius: 9px !important;
}

.proto {
  border-radius: 999px !important;
  font-size: 12px;
  letter-spacing: .03em;
}

.proto-awg {
  background: rgba(37,217,255,.11) !important;
  color: #42e4ff !important;
  border: 1px solid rgba(37,217,255,.22);
}

.proto-wg {
  background: rgba(20,240,160,.11) !important;
  color: #55ffb5 !important;
  border: 1px solid rgba(20,240,160,.22);
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
  box-shadow: 0 0 18px rgba(20,240,160,.62) !important;
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
  background: rgba(37,217,255,.10) !important;
  color: #54e8ff !important;
  border-color: rgba(37,217,255,.28) !important;
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
  border: 1px solid rgba(49,66,85,.9) !important;
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
  0% { box-shadow: 0 0 0 0 rgba(20,240,160,.26); }
  70% { box-shadow: 0 0 0 9px rgba(20,240,160,0); }
  100% { box-shadow: 0 0 0 0 rgba(20,240,160,0); }
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
            <div class="neo-brand-sub">NODE PANEL</div>
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
      const title = oldH1 ? oldH1.textContent.trim() : '3WG Panel';
      if (oldH1) oldH1.remove();

      const top = document.createElement('div');
      top.className = 'neo-topbar';
      top.innerHTML = `
        <div class="neo-title">
          <div class="neo-title-badge neo-pulse">3WG</div>
          <div>
            <h1>${title}</h1>
            <div class="muted">WireGuard / AmneziaWG node management</div>
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
  --bg:#070c13;
  --bg2:#0b111b;
  --sidebar:#070c13;
  --card:#111a26;
  --card2:#0d1622;
  --line:#263342;
  --line2:#334357;
  --text:#e8f0fb;
  --muted:#8795aa;
  --muted2:#5f6d80;
  --green:#14f0a0;
  --cyan:#25d9ff;
  --orange:#f4a340;
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
    radial-gradient(circle at 24% -10%, rgba(37,217,255,.10), transparent 30%),
    radial-gradient(circle at 100% 0%, rgba(20,240,160,.07), transparent 28%),
    linear-gradient(180deg, #070c13, #0a1018);
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
    radial-gradient(circle at 40% 0%, rgba(37,217,255,.10), transparent 38%);
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
  border-bottom:1px dashed rgba(37,217,255,.18);
}

.neo-logo {
  width:38px;
  height:38px;
  display:grid;
  place-items:center;
  border-radius:13px;
  background:rgba(20,240,160,.10);
  color:var(--green);
  border:1px solid rgba(20,240,160,.34);
  font-weight:900;
  box-shadow:0 0 24px rgba(20,240,160,.14);
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
  background:rgba(20,240,160,.08);
  border-color:rgba(20,240,160,.22);
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
  background:rgba(37,217,255,.08);
  color:var(--cyan);
  border:1px solid rgba(37,217,255,.25);
  font-weight:900;
  box-shadow:0 0 24px rgba(37,217,255,.08);
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
  background:rgba(37,217,255,.10);
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
  background:rgba(20,240,160,.08);
  border:1px solid rgba(20,240,160,.18);
}

.stat .n {
  color:var(--green) !important;
  font-size:24px !important;
  text-shadow:0 0 18px rgba(20,240,160,.22);
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
  border-color:rgba(37,217,255,.65) !important;
  box-shadow:0 0 0 4px rgba(37,217,255,.08) !important;
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
  background:rgba(9,16,25,.68);
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
  background:rgba(37,217,255,.11) !important;
  color:#42e4ff !important;
  border:1px solid rgba(37,217,255,.22);
}

.proto-wg {
  background:rgba(20,240,160,.11) !important;
  color:#55ffb5 !important;
  border:1px solid rgba(20,240,160,.22);
}

.dot {
  width:10px !important;
  height:10px !important;
  vertical-align:middle;
}

.dot-green {
  background:var(--green) !important;
  box-shadow:0 0 18px rgba(20,240,160,.62) !important;
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
  background:rgba(37,217,255,.10) !important;
  color:#54e8ff !important;
  border-color:rgba(37,217,255,.28) !important;
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
      <div class="neo-brand-sub">NODE PANEL</div>
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
        <div class="neo-sub">WireGuard / AmneziaWG node management</div>
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
  --bg: #080d14;
  --bg-2: #0b111a;
  --side: #070b11;
  --panel: #101821;
  --panel-2: #0c131c;
  --row: #09111a;
  --row-hover: #0e1925;
  --border: #243140;
  --border-2: #314255;
  --text: #e8f0fb;
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
    linear-gradient(180deg, #070c13, #091018);
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
  border-right: 1px solid rgba(49,66,85,.65);
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
  border: 1px solid rgba(49,66,85,.85);
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
  border: 1px solid rgba(49,66,85,.72) !important;
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
  border-bottom: 1px solid rgba(49,66,85,.72) !important;
  white-space: nowrap;
}

tbody tr {
  background: transparent !important;
}

tbody tr:hover {
  background: rgba(14,25,37,.62) !important;
}

tbody td {
  border-bottom: 1px solid rgba(49,66,85,.48) !important;
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
  border: 1px solid rgba(49,66,85,.72) !important;
  color: #e8f3ff !important;
  border-radius: 5px !important;
  padding: 2px 6px !important;
  font-size: 12px;
}

pre {
  background: #070d15 !important;
  border: 1px solid rgba(49,66,85,.72) !important;
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
  border: 1px solid rgba(49,66,85,.9);
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
  border: 1px solid rgba(49,66,85,.65) !important;
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
  border: 1px solid rgba(49,66,85,.65) !important;
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
      <div class="neo-brand-sub">NODE PANEL</div>
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
        <div class="neo-sub">WireGuard / AmneziaWG node management</div>
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
<h1>3WG Panel</h1>

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
<p class="muted">Endpoint host: <code>{html.escape(ENDPOINT_HOST)}</code></p>
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

    return HTMLResponse(page("3WG Panel", body))


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

    if (path in ('/', '/login', '/ui') or re.match(r'^/client/\d+$', path) or re.match(r'^/status/(wireguard|amneziawg)$', path) or re.match(r'^/traffic/(wireguard|amneziawg)$', path)) and index_file.exists():
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
    cookie_token = request.cookies.get(SESSION_COOKIE)
    return bool(cookie_token and secrets.compare_digest(cookie_token, make_session_token()))


def api_require_auth(request: Request):
    if api_is_authenticated(request):
        return PANEL_USER
    raise HTTPException(status_code=401, detail='Unauthorized')


def api_error(message: str, status_code: int = 400, **extra):
    payload = {'ok': False, 'error': message}
    payload.update(extra)
    return JSONResponse(payload, status_code=status_code)


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
            'endpoint_host': ENDPOINT_HOST,
            'endpoint': f"{ENDPOINT_HOST}:{endpoint_port}",
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


def api_traffic_history_payload(protocol: str, days: int = 30) -> dict:
    if protocol not in PROTOCOLS:
        raise HTTPException(status_code=404, detail='Unknown protocol')
    days = max(1, min(int(days or 30), 90))
    live, _ = api_live_maps()
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


def api_peer_payload(c, live: dict | None = None, include_config: bool = False) -> dict:
    protocol = c['protocol']
    p = PROTOCOLS[protocol]
    endpoint = client_endpoint(protocol)
    lp = live.get(protocol, {}).get(c['public_key']) if live else None
    active, handshake_age = api_recent_handshake(lp)
    enabled = bool(c['enabled'])
    payload = {
        'id': int(c['id']),
        'name': c['name'],
        'protocol': protocol,
        'protocol_title': p['title'],
        'ip_cidr': c['ip_cidr'],
        'public_key': c['public_key'],
        'enabled': enabled,
        'created_at': int(c['created_at']),
        'deleted_at': int(c['deleted_at']) if 'deleted_at' in c.keys() else 0,
        'endpoint': endpoint,
        'status': 'active' if enabled and active else ('offline' if enabled else 'disabled'),
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
            'delete': f"/api/peers/{c['id']}",
        },
    }
    if include_config:
        payload['config'] = read_conf(c)
    return payload


@app.post('/api/auth/login')
async def api_auth_login(request: Request):
    data = await api_read_payload(request)
    username = str(data.get('username', ''))
    password = str(data.get('password', ''))
    ok_user = secrets.compare_digest(username, PANEL_USER)
    ok_pass = secrets.compare_digest(password, PANEL_PASSWORD)
    if not (ok_user and ok_pass):
        return api_error('Неверный логин или пароль', status_code=401)
    resp = JSONResponse({'ok': True, 'authenticated': True, 'user': PANEL_USER})
    resp.set_cookie(
        SESSION_COOKIE,
        make_session_token(),
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
    if not api_is_authenticated(request):
        return JSONResponse({'ok': False, 'authenticated': False}, status_code=401)
    return {'ok': True, 'authenticated': True, 'user': PANEL_USER}


@app.get('/api/node/protocols')
def api_node_protocols(user=Depends(api_require_auth)):
    return {
        'ok': True,
        'endpoint_host': ENDPOINT_HOST,
        'protocols': {protocol: api_protocol_state(protocol) for protocol in PROTOCOLS},
    }


@app.get('/api/node/status')
def api_node_status(user=Depends(api_require_auth)):
    live, errors = api_live_maps()
    with db() as conn:
        total = conn.execute('SELECT COUNT(*) AS n FROM clients WHERE COALESCE(deleted_at, 0) = 0').fetchone()['n']
    return {
        'ok': True,
        'endpoint_host': ENDPOINT_HOST,
        'dns_servers': DNS_SERVERS,
        'clients_total': int(total),
        'peers_total': sum(len(pm) for pm in live.values()),
        'peers_online': sum(1 for pm in live.values() for x in pm.values() if x.get('endpoint') != '(none)'),
        'protocols': {protocol: api_protocol_state(protocol, include_raw=True) for protocol in PROTOCOLS},
        'errors': errors,
    }


@app.get('/api/peers')
def api_peers(user=Depends(api_require_auth)):
    live, errors = api_live_maps()
    api_record_traffic_snapshot(live)
    with db() as conn:
        rows = conn.execute('SELECT * FROM clients WHERE COALESCE(deleted_at, 0) = 0 ORDER BY id DESC').fetchall()
    return {'ok': True, 'peers': [api_peer_payload(c, live=live) for c in rows], 'errors': errors}


@app.get('/api/traffic/history')
def api_traffic_history(protocol: str = 'amneziawg', days: int = 30, user=Depends(api_require_auth)):
    return api_traffic_history_payload(protocol, days)


@app.post('/api/peers')
async def api_create_peers(request: Request, user=Depends(api_require_auth)):
    data = await api_read_payload(request)
    name = str(data.get('name', '')).strip()
    protocols = data.get('protocols', data.get('protocol', []))
    if isinstance(protocols, str):
        protocols = [protocols]
    protocols = [p for p in protocols if p in PROTOCOLS]

    if not name:
        return api_error('Пустое имя клиента', status_code=400)
    if not protocols:
        return api_error('Не выбран протокол', status_code=400)

    created_ids = []
    try:
        for protocol in protocols:
            created_ids.append(create_client(name, protocol))
    except Exception as e:
        return api_error(str(e), status_code=500, created_ids=created_ids)

    live, _ = api_live_maps()
    with db() as conn:
        qmarks = ','.join('?' for _ in created_ids)
        rows = conn.execute(f'SELECT * FROM clients WHERE id IN ({qmarks}) ORDER BY id DESC', created_ids).fetchall()
    return {'ok': True, 'created_ids': created_ids, 'peers': [api_peer_payload(c, live=live) for c in rows]}


@app.get('/api/peers/{client_id}')
def api_peer_get(client_id: int, user=Depends(api_require_auth)):
    live, _ = api_live_maps()
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live, include_config=True)}


@app.get('/api/peers/{client_id}/config')
def api_peer_config(client_id: int, user=Depends(api_require_auth)):
    c = load_client(client_id)
    return PlainTextResponse(read_conf(c))


@app.post('/api/peers/{client_id}/enable')
def api_peer_enable(client_id: int, user=Depends(api_require_auth)):
    c = load_client(client_id)
    try:
        enable_peer(c)
    except Exception as e:
        return api_error(str(e), status_code=500)
    live, _ = api_live_maps()
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live)}


@app.post('/api/peers/{client_id}/disable')
def api_peer_disable(client_id: int, user=Depends(api_require_auth)):
    c = load_client(client_id)
    try:
        disable_peer(c)
    except Exception as e:
        return api_error(str(e), status_code=500)
    live, _ = api_live_maps()
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live)}


@app.delete('/api/peers/{client_id}')
def api_peer_delete(client_id: int, user=Depends(api_require_auth)):
    c = load_client(client_id)
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
    return {'ok': True, 'deleted_id': client_id}
# === 3WG REACT API END ===

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


def api_dashboard_payload() -> dict:
    live, errors = api_live_maps()
    protocols = {protocol: api_protocol_state(protocol) for protocol in PROTOCOLS}

    with db() as conn:
        rows = conn.execute(
            'SELECT * FROM clients WHERE COALESCE(deleted_at, 0) = 0 ORDER BY id DESC'
        ).fetchall()

    peers = [api_peer_payload(c, live=live) for c in rows]
    online = sum(1 for p in peers if p.get('status') == 'active')
    available_protocols = [p for p in protocols.values() if p.get('available')]
    primary_protocol = available_protocols[0]['title'] if available_protocols else 'нет активного протокола'

    return {
        'ok': True,
        'screen': 'dashboard',
        'title': '3WG Panel',
        'subtitle': f"Node / {ENDPOINT_HOST}",
        'endpoint_host': ENDPOINT_HOST,
        'theme': {'name': 'classic-neo', 'source': 'legacy-html-design'},
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
        'peers': [api_peer_view_model(p) for p in peers],
        'errors': errors,
        'actions': {
            'refresh': {'method': 'GET', 'url': '/api/dashboard'},
            'create_peer': {'method': 'POST', 'url': '/api/peers'},
        },
    }


@app.get('/api/dashboard')
def api_dashboard(user=Depends(api_require_auth)):
    return api_dashboard_payload()


@app.get('/api/ui/dashboard')
def api_ui_dashboard(user=Depends(api_require_auth)):
    return api_dashboard_payload()
# === 3WG DASHBOARD MODEL API END ===
