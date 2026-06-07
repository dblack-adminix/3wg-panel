import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  ArrowUpRight,
  Download,
  Home,
  LogOut,
  Network,
  Plus,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Users,
  Wifi,
  WifiOff,
} from 'lucide-react';
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

function IconButton({ href, onClick, title, tone = 'default', children }) {
  const className = `icon-button ${tone}`;
  if (href) {
    return <a className={className} href={href} title={title} aria-label={title}>{children}</a>;
  }
  return <button className={className} onClick={onClick} title={title} aria-label={title} type="button">{children}</button>;
}

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
      </div>
      <div className="nav-title">ОБЗОР</div>
      <a className="nav active" href="#top"><Home size={14} /> <span>Главная</span></a>
      <a className="nav" href="#status"><Activity size={14} /> <span>AWG status</span></a>
      <div className="nav-title">УПРАВЛЕНИЕ</div>
      <button className="nav logout" onClick={onLogout}><LogOut size={14} /> <span>Выход</span></button>
    </aside>
  );
}

function StatCard({ value, label, icon: Icon }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      <div className="stat-mark">{Icon && <Icon size={16} />}</div>
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
    <section className="card create-card compact-create">
      <h2>Создать клиента</h2>
      <form onSubmit={submit}>
        <input className="name-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Например: Ivan iPhone" />
        <div className="protocol-row">
          <label className={!wgAvailable ? 'muted' : ''}><input type="checkbox" checked={wireguard} disabled={!wgAvailable} onChange={(e) => setWireguard(e.target.checked)} /> WireGuard {!wgAvailable && <span className="pill bad">не установлен</span>}</label>
          <label><input type="checkbox" checked={amnezia} disabled={!available} onChange={(e) => setAmnezia(e.target.checked)} /> AmneziaWG</label>
        </div>
        <button className="orange-btn" disabled={loading || !name.trim()}><Plus size={15} /> Создать клиента</button>
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
      <div className="section-head">
        <h2>Клиенты</h2>
        <IconButton onClick={onRefresh} title="Обновить таблицу" tone="ghost"><RefreshCw size={15} /></IconButton>
      </div>
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
            <col style={{ width: 96 }} />
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
              <th>Actions</th>
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
                <td className="actions">
                  <IconButton href={p.links?.html || '#'} title="Открыть клиента" tone="open"><ArrowUpRight size={14} /></IconButton>
                  <IconButton href={p.links?.download || '#'} title="Скачать config" tone="download"><Download size={14} /></IconButton>
                  <IconButton href={p.links?.qr_native_png || '#'} title="Скачать QR" tone="qr"><QrCode size={14} /></IconButton>
                </td>
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
          <div className="top-actions"><span>AWG</span><button onClick={onLogout} title="Выйти"><LogOut size={15} /></button></div>
        </header>
        {state.error && <div className="warning">{state.error}</div>}
        <div className="stats-grid">
          <StatCard value={state.status?.clients_total ?? state.peers.length} label="клиентов в панели" icon={Users} />
          <StatCard value={state.status?.peers_total ?? 0} label="peer'ов в контейнерах" icon={Network} />
          <StatCard value={online} label="сейчас в сети" icon={Wifi} />
          <StatCard value={available} label="доступных протокола" icon={ShieldCheck} />
        </div>
        <CreateClient protocols={state.protocols} onCreated={load} />
        <ClientsTable peers={state.peers} onRefresh={load} />
        <section className="card status-card" id="status"><h2>Статус</h2><div className="status-grid">{Object.values(state.protocols || {}).map((p) => <div className="status-item" key={p.protocol}><b>{p.title}</b><span className={p.available ? 'status-ok' : 'status-bad'}>{p.available ? <Wifi size={14} /> : <WifiOff size={14} />}{p.available ? 'ONLINE' : 'OFFLINE'}</span><small>{p.container} / {p.interface}</small></div>)}</div></section>
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
