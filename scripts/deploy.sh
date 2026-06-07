#!/usr/bin/env bash
set -euo pipefail

BASE="/srv/3wg-panel"
APP="$BASE/app/app.py"
FRONT="$BASE/frontend"

echo "======================================================"
echo " 3WG PANEL DEV DEPLOY - REACT FRONTEND"
echo "======================================================"

cd "$BASE"

echo
echo "===== Clean old generated visual Python blocks ====="
python3 - <<'PY'
from pathlib import Path
import re

app = Path('/srv/3wg-panel/app/app.py')
text = app.read_text(encoding='utf-8')

for start, end in [
    ('# === 3WG REACT UI START ===', '# === 3WG REACT UI END ==='),
    ('# === 3WG SUPPLIED LOGO START ===', '# === 3WG SUPPLIED LOGO END ==='),
    ('# === 3WG SIMPLE LOGO START ===', '# === 3WG SIMPLE LOGO END ==='),
    ('# === 3WG DIRECT PNG LOGO START ===', '# === 3WG DIRECT PNG LOGO END ==='),
    ('# === 3WG ROOT LOGO START ===', '# === 3WG ROOT LOGO END ==='),
    ('# === 3WG STANDARD PNG LOGO START ===', '# === 3WG STANDARD PNG LOGO END ==='),
    ('# === 3WG CLIENTS TABLE RUNTIME START ===', '# === 3WG CLIENTS TABLE RUNTIME END ==='),
    ('# === 3WG CLIENTS TABLE WIDTH START ===', '# === 3WG CLIENTS TABLE WIDTH END ==='),
    ('# === 3WG REACT FRONTEND START ===', '# === 3WG REACT FRONTEND END ==='),
]:
    text = re.sub(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', text, flags=re.S)

app.write_text(text.rstrip() + '\n', encoding='utf-8')
print('old visual Python blocks removed')
PY

echo
echo "===== React API patch ====="
python3 "$BASE/scripts/apply_api_patch.py"

echo
echo "===== Dashboard model API patch ====="
python3 "$BASE/scripts/apply_dashboard_model_patch.py"

echo
echo "===== React frontend route patch ====="
python3 - <<'PY'
from pathlib import Path
import re

app = Path('/srv/3wg-panel/app/app.py')
text = app.read_text(encoding='utf-8')
START = '# === 3WG REACT FRONTEND START ==='
END = '# === 3WG REACT FRONTEND END ==='
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S)

block = r'''
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

    if path in ('/', '/login', '/ui') and index_file.exists():
        return ReactFileResponse(
            index_file,
            media_type='text/html; charset=utf-8',
            headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'},
        )

    return await call_next(request)
# === 3WG REACT FRONTEND END ===
'''.strip() + '\n'

app.write_text(text.rstrip() + '\n\n' + block, encoding='utf-8')
print('React frontend middleware patched')
PY

echo
echo "===== Create React frontend sources ====="
rm -rf "$FRONT"
mkdir -p "$FRONT/src"

cat > "$FRONT/package.json" <<'EOF'
{
  "scripts": {
    "build": "vite build",
    "dev": "vite --host 0.0.0.0"
  },
  "dependencies": {
    "@vitejs/plugin-react": "5.1.1",
    "vite": "7.2.4",
    "react": "19.2.1",
    "react-dom": "19.2.1"
  },
  "devDependencies": {}
}
EOF

cat > "$FRONT/index.html" <<'EOF'
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>3WG Panel</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
EOF

cat > "$FRONT/src/main.jsx" <<'EOF'
import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const api = async (path, options = {}) => {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const message = data?.error || data?.detail || `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data;
};

function Login({ onLogin }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
      await onLogin();
    } catch (err) {
      setError(err.message || 'Ошибка входа');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="badge">SECURE NODE PANEL</div>
        <img className="login-logo" src="/logogrin.png" alt="3WG" />
        <p className="login-subtitle">Управление WireGuard / AmneziaWG peer&apos;ами</p>
        {error && <div className="login-error">{error}</div>}
        <label>Логин</label>
        <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        <label>Пароль</label>
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" autoFocus />
        <button disabled={loading}>{loading ? 'Вход...' : 'Войти'}</button>
        <div className="login-host">{location.hostname}</div>
      </form>
    </main>
  );
}

function Sidebar({ onLogout }) {
  return (
    <aside className="sidebar">
      <div className="brand-block">
        <img src="/logogrin.png" alt="3WG" />
        <div className="brand-title">3WG</div>
        <div className="brand-sub">NODE PANEL</div>
      </div>
      <div className="nav-title">ОБЗОР</div>
      <a className="nav active" href="#top">⌂ <span>Главная</span></a>
      <a className="nav" href="#status">✶ <span>AWG status</span></a>
      <div className="nav-title">УПРАВЛЕНИЕ</div>
      <button className="nav logout" onClick={onLogout}>↪ <span>Выход</span></button>
    </aside>
  );
}

function StatCard({ value, label }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      <div className="stat-mark" />
    </div>
  );
}

function CreateClient({ protocols, onCreated }) {
  const [name, setName] = useState('');
  const available = protocols?.amneziawg?.available;
  const wgAvailable = protocols?.wireguard?.available;
  const [amnezia, setAmnezia] = useState(true);
  const [wireguard, setWireguard] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    const selected = [];
    if (wireguard) selected.push('wireguard');
    if (amnezia) selected.push('amneziawg');
    setError('');
    setLoading(true);
    try {
      await api('/api/peers', { method: 'POST', body: JSON.stringify({ name, protocols: selected }) });
      setName('');
      await onCreated();
    } catch (err) {
      setError(err.message || 'Ошибка создания');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="card create-card">
      <h2>Создать клиента</h2>
      <form onSubmit={submit}>
        <input className="name-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Например: Ivan iPhone" />
        <div className="protocol-row">
          <label className={!wgAvailable ? 'muted' : ''}><input type="checkbox" checked={wireguard} disabled={!wgAvailable} onChange={(e) => setWireguard(e.target.checked)} /> WireGuard {!wgAvailable && <span className="pill bad">не установлен</span>}</label>
          <label><input type="checkbox" checked={amnezia} disabled={!available} onChange={(e) => setAmnezia(e.target.checked)} /> AmneziaWG</label>
        </div>
        <button className="orange-btn" disabled={loading || !name.trim()}>+ Создать клиента</button>
        {error && <div className="warning">{error}</div>}
      </form>
      <div className="warning compact-warning">
        <b>На этой ноде доступен не весь набор протоколов.</b><br />
        Доступно: {available ? 'AmneziaWG' : '—'}<br />
        Не установлено: {!wgAvailable ? 'WireGuard' : '—'}
      </div>
      <div className="endpoint-host">Endpoint host: <code>{location.hostname}</code></div>
    </section>
  );
}

function ClientsTable({ peers, onRefresh }) {
  return (
    <section className="card clients-card">
      <h2>Клиенты</h2>
      <div className="table-wrap">
        <table className="clients-table">
          <colgroup>
            <col style={{ width: 46 }} />
            <col style={{ width: 170 }} />
            <col style={{ width: 125 }} />
            <col style={{ width: 130 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 180 }} />
            <col style={{ width: 170 }} />
            <col style={{ width: 105 }} />
            <col style={{ width: 105 }} />
            <col style={{ width: 82 }} />
          </colgroup>
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
          <tbody>
            {peers.map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td><b>{p.name}</b><small>создан панелью</small></td>
                <td><span className="proto">{p.protocol_title || p.protocol}</span></td>
                <td><code>{p.ip_cidr}</code></td>
                <td><span className={p.status === 'active' ? 'active-text' : 'muted'}>{p.status === 'active' ? 'ACTIVE' : 'OFFLINE'}</span></td>
                <td title={p.live?.endpoint || ''}>{p.live?.endpoint || '(none)'}</td>
                <td>{p.live?.latest_handshake && p.live.latest_handshake !== '0' ? new Date(Number(p.live.latest_handshake) * 1000).toLocaleString('ru-RU') : '-'}</td>
                <td>{formatBytes(p.live?.rx)}</td>
                <td>{formatBytes(p.live?.tx)}</td>
                <td className="actions"><a href={p.links?.html || '#'}>↗</a><button onClick={onRefresh}>↻</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatBytes(v) {
  const n = Number(v || 0);
  if (!n) return '0.00 B';
  const units = ['B', 'KiB', 'MiB', 'GiB'];
  let x = n, i = 0;
  while (x >= 1024 && i < units.length - 1) { x /= 1024; i++; }
  return `${x.toFixed(2)} ${units[i]}`;
}

function Dashboard({ onLogout }) {
  const [state, setState] = useState({ loading: true, peers: [], status: null, protocols: null, error: '' });

  const load = async () => {
    try {
      const [status, peers, proto] = await Promise.all([
        api('/api/node/status'),
        api('/api/peers'),
        api('/api/node/protocols'),
      ]);
      setState({ loading: false, peers: peers.peers || [], status, protocols: proto.protocols || {}, error: '' });
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: err.message || 'Ошибка загрузки' }));
    }
  };

  useEffect(() => { load(); }, []);

  const online = useMemo(() => state.peers.filter((p) => p.status === 'active').length, [state.peers]);
  const available = Object.values(state.protocols || {}).filter((p) => p.available).length;

  return (
    <div className="layout" id="top">
      <Sidebar onLogout={onLogout} />
      <main className="main">
        <header className="topbar">
          <div>
            <h1>3WG Panel</h1>
            <p>WireGuard / AmneziaWG node management</p>
          </div>
          <div className="top-actions"><span>AWG</span><button onClick={onLogout}>↪</button></div>
        </header>
        {state.error && <div className="warning">{state.error}</div>}
        <div className="stats-grid">
          <StatCard value={state.status?.clients_total ?? state.peers.length} label="клиентов в панели" />
          <StatCard value={state.status?.peers_total ?? 0} label="peer'ов в контейнерах" />
          <StatCard value={online} label="сейчас в сети" />
          <StatCard value={available} label="доступных протокола" />
        </div>
        <CreateClient protocols={state.protocols} onCreated={load} />
        <ClientsTable peers={state.peers} onRefresh={load} />
        <section className="card" id="status"><h2>Статус</h2><a className="status-link" href="/status/amneziawg">AWG</a></section>
      </main>
    </div>
  );
}

function App() {
  const [auth, setAuth] = useState({ loading: true, ok: false });
  const check = async () => {
    try { await api('/api/auth/me'); setAuth({ loading: false, ok: true }); }
    catch { setAuth({ loading: false, ok: false }); }
  };
  useEffect(() => { check(); }, []);
  const logout = async () => { try { await api('/api/auth/logout', { method: 'POST' }); } finally { setAuth({ loading: false, ok: false }); } };
  if (auth.loading) return <div className="boot">3WG</div>;
  return auth.ok ? <Dashboard onLogout={logout} /> : <Login onLogin={check} />;
}

createRoot(document.getElementById('root')).render(<App />);
EOF

cat > "$FRONT/src/styles.css" <<'EOF'
:root{--bg:#080d14;--panel:#0b111a;--card:#101923;--line:#263546;--muted:#95a9c2;--text:#f3f7ff;--green:#24f0a0;--cyan:#14d9ff;--orange:#f7a83d;--red:#7c293a;--radius:8px}*{box-sizing:border-box}html,body,#root{height:100%;margin:0}body{background:radial-gradient(circle at 20% -20%,#123f3a55,transparent 30%),linear-gradient(180deg,#081019,#070b11);color:var(--text);font-family:Inter,"Segoe UI",Arial,sans-serif;font-size:14px}.boot{height:100%;display:grid;place-items:center;color:var(--green);font-weight:900;font-size:38px}.login-page{min-height:100%;display:grid;place-items:center;padding:24px}.login-card{width:430px;border:1px solid var(--line);border-radius:8px;background:#101824;padding:30px;box-shadow:0 18px 60px #0008}.badge{display:inline-flex;border:1px solid #0b8f6c;color:var(--green);border-radius:8px;padding:6px 12px;font-weight:900;letter-spacing:.04em}.login-logo{display:block;width:195px;height:50px;object-fit:contain;margin:24px 0 10px}.login-subtitle{color:#a7bbd6;font-size:16px;margin:0 0 24px}.login-card label{display:block;margin:14px 0 8px;color:#c9d9ee;font-weight:700}.login-card input,.name-input{width:100%;height:38px;border-radius:8px;border:1px solid #314155;background:#0b121b;color:var(--text);padding:0 12px}.login-card button,.orange-btn{width:100%;height:42px;border:0;border-radius:8px;background:var(--orange);color:#080b10;font-weight:900;font-size:15px;cursor:pointer}.login-error,.warning{border:1px solid #7d5d2c;background:#1c1a14;color:#ffd386;border-radius:8px;padding:10px 12px;margin:12px 0}.login-host{text-align:center;color:#91a5bf;margin-top:18px}.layout{min-height:100%;display:grid;grid-template-columns:170px 1fr}.sidebar{background:#080d14;border-right:1px solid #233043;padding:6px 8px}.brand-block{border-bottom:1px dashed #40526a;padding-bottom:18px;margin-bottom:18px}.brand-block img{display:block;width:132px;height:34px;object-fit:contain}.brand-title{font-size:21px;font-weight:900;margin-top:18px}.brand-sub,.nav-title{color:#8191a8;font-size:10px;letter-spacing:.22em;font-weight:800}.nav-title{margin:18px 0 8px}.nav{width:100%;display:flex;gap:10px;align-items:center;height:34px;color:#d9e7f7;text-decoration:none;border:1px solid transparent;border-radius:6px;background:transparent;padding:0 10px;font-weight:800}.nav.active{border-color:#075c4c;background:#06251f}.logout{cursor:pointer}.main{padding:8px 16px 40px;overflow:hidden}.topbar{height:44px;display:flex;justify-content:space-between;align-items:flex-start}.topbar h1{font-size:24px;line-height:1;margin:0}.topbar p{margin:6px 0 0;color:#a9bad1}.top-actions{display:flex;gap:8px}.top-actions span,.top-actions button{border:1px solid #2e3d51;border-radius:6px;background:#0c141e;color:#e9f2ff;font-weight:900;padding:6px 10px}.stats-grid{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:8px;margin:8px 0 12px}.stat-card,.card{border:1px solid var(--line);border-radius:8px;background:#0d151f}.stat-card{height:72px;padding:14px 16px;position:relative}.stat-value{font-size:20px;color:var(--green);font-weight:900}.stat-label{color:#92a6c0;font-size:12px;margin-top:8px}.stat-mark{position:absolute;right:12px;top:22px;width:26px;height:26px;border:1px solid #0a684e;border-radius:6px;background:#0b2a24}.card{padding:16px;margin-bottom:10px}.card h2{margin:0 0 18px;font-size:19px}.create-card{min-height:180px}.name-input{width:260px}.protocol-row{display:flex;gap:14px;align-items:center;margin:14px 0}.protocol-row input{accent-color:#48b8ff}.muted{color:#8796a9}.pill{font-size:10px;padding:2px 6px;border-radius:4px;margin-left:4px}.pill.bad{background:#552335;color:#ffb3c6}.compact-warning{display:inline-block;margin-top:12px}.endpoint-host{color:#92a6c0;margin-top:8px}.endpoint-host code,.clients-table code{background:#050a10;border:1px solid #263546;border-radius:4px;padding:2px 6px;color:#fff}.table-wrap{width:100%;overflow-x:auto}.clients-table{width:auto;min-width:1120px;table-layout:fixed;border-collapse:collapse;font-size:13px}.clients-table th,.clients-table td{border-bottom:1px solid #223042;padding:10px 8px;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.clients-table th{color:#9fb3cd;text-transform:uppercase;font-size:11px;letter-spacing:.08em}.clients-table td:first-child,.clients-table th:first-child{padding-left:8px}.clients-table small{display:block;color:#8194ac;margin-top:4px}.proto{display:inline-block;background:#073947;color:#17eaff;border:1px solid #116174;border-radius:5px;padding:4px 8px;font-weight:900}.active-text{color:var(--green);font-weight:900}.actions{display:flex;gap:6px}.actions a,.actions button{display:inline-grid;place-items:center;width:24px;height:24px;border-radius:5px;border:0;text-decoration:none;background:var(--orange);color:#111;font-weight:900}.actions button{background:#4b1728;color:#ffc6d5;cursor:pointer}.status-link{color:#fff;font-size:16px;font-weight:900}@media(max-width:900px){.layout{grid-template-columns:1fr}.sidebar{display:none}.stats-grid{grid-template-columns:1fr 1fr}.main{padding:12px}.login-card{width:min(430px,94vw)}}
EOF

cat >> "$FRONT/src/styles.css" <<'EOF'

/* ===== CLASSIC 3WG GEOMETRY RESTORE ===== */
.layout {
  grid-template-columns: 212px minmax(0, 1fr) !important;
}

.sidebar {
  padding: 10px !important;
}

.brand-block {
  padding-bottom: 18px !important;
  margin-bottom: 18px !important;
}

.brand-block img {
  width: 195px !important;
  height: 50px !important;
  object-fit: contain !important;
  margin-bottom: 14px !important;
}

.main {
  padding: 12px 22px 40px !important;
}

.topbar {
  height: 54px !important;
}

.topbar h1 {
  font-size: 26px !important;
}

.stats-grid {
  grid-template-columns: repeat(4, minmax(180px, 1fr)) !important;
  gap: 10px !important;
  margin: 8px 0 14px !important;
}

.card {
  padding: 18px 20px !important;
  margin-bottom: 12px !important;
}

.create-card {
  min-height: 250px !important;
}

.create-form {
  display: block !important;
}

.name-input {
  width: 220px !important;
}

.orange-btn {
  width: 180px !important;
  height: 38px !important;
}

.compact-warning {
  display: inline-block !important;
  max-width: 360px !important;
}

.clients-table {
  width: auto !important;
  min-width: 1120px !important;
  table-layout: fixed !important;
}

.clients-table th,
.clients-table td {
  padding: 10px 8px !important;
}
EOF

echo
echo "===== Restore React Dockerfile ====="
cat > "$BASE/app/Dockerfile" <<'EOF'
FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json ./package.json
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app/app.py /app/app.py
COPY app/static /app/static
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
RUN mkdir -p /app/data /app/clients/wireguard /app/clients/amneziawg /app/backups/wireguard /app/backups/amneziawg /app/static /app/frontend/dist
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
tar -czf "$BASE/backups/source/3wg-panel-app.$(date +%F_%H-%M-%S).tgz" -C "$BASE" app scripts frontend

echo
echo "===== Rebuild Docker image ====="
docker rm -f 3wg-panel 2>/dev/null || true
docker rmi 3wg-panel:local 2>/dev/null || true
docker build -f "$BASE/app/Dockerfile" -t 3wg-panel:local "$BASE"

echo
echo "===== Run 3WG Panel ====="
docker rm -f 3wg-panel 2>/dev/null || true
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
print(urllib.request.urlopen('http://127.0.0.1:18080/health').read().decode())
PY

echo
echo "===== React UI check ====="
python3 - <<'PY'
import hashlib
import urllib.request
for url in ['http://127.0.0.1:18080/logogrin.png', 'http://127.0.0.1:18080/', 'http://127.0.0.1:18080/login']:
    data = urllib.request.urlopen(url, timeout=10).read()
    if url.endswith('.png'):
        print(url, data[:8], hashlib.sha256(data).hexdigest())
    else:
        text = data.decode('utf-8', errors='replace')
        print(url, '<div id="root"></div>' in text, '/assets/' in text)
PY

echo
echo "===== Status ====="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "DONE"
