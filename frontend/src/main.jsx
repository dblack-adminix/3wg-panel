import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  ArrowUpRight,
  ChevronLeft,
  Copy,
  Download,
  Home,
  LogOut,
  Network,
  Plus,
  QrCode,
  RefreshCw,
  X,
  ShieldCheck,
  Terminal,
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
  const path = window.location.pathname;
  const isHome = path === '/' || path === '/ui';
  const isStatus = path.startsWith('/status/');

  return (
    <aside className="sidebar">
      <div className="brand-block">
        <img src="/logogrin.png" alt="3WG" />
      </div>
      <div className="nav-title">ОБЗОР</div>
      <a className={`nav ${isHome ? 'active' : ''}`} href="/"><Home size={14} /> <span>Главная</span></a>
      <a className={`nav ${isStatus ? 'active' : ''}`} href="/status/amneziawg"><Activity size={14} /> <span>AWG status</span></a>
      <div className="nav-title">УПРАВЛЕНИЕ</div>
      <button className="nav logout" onClick={onLogout}><LogOut size={14} /> <span>Выход</span></button>
    </aside>
  );
}

function Shell({ title, subtitle, onLogout, children }) {
  return (
    <div className="layout" id="top">
      <Sidebar onLogout={onLogout} />
      <main className="main">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          <div className="top-actions"><span>AWG</span><button onClick={onLogout} title="Выйти"><LogOut size={15} /></button></div>
        </header>
        {children}
      </main>
    </div>
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
  const allProtocolsAvailable = Boolean(available && wgAvailable);

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
      <div className={allProtocolsAvailable ? 'success compact-warning' : 'warning compact-warning'}>
        {allProtocolsAvailable ? (
          <>
            <b>Все протоколы установлены.</b>
            Доступно: WireGuard и AmneziaWG
          </>
        ) : (
          <>
            <b>На этой ноде доступен не весь набор протоколов.</b>
            Доступно: {available ? 'AmneziaWG' : '—'}<br />
            Не установлено: {!wgAvailable ? 'WireGuard' : '—'}
          </>
        )}
      </div>
      <div className="endpoint-host">Endpoint host: <code>{location.hostname}</code></div>
    </section>
  );
}

function ClientsTable({ peers, onRefresh }) {
  const [qrPeer, setQrPeer] = useState(null);

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
            <col style={{ width: 102 }} />
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
                <td className="actions-cell">
                  <div className="actions">
                    <IconButton href={p.links?.html || '#'} title="Открыть клиента" tone="open"><ArrowUpRight size={14} /></IconButton>
                    <IconButton href={p.links?.download || '#'} title="Скачать config" tone="download"><Download size={14} /></IconButton>
                    <IconButton onClick={() => setQrPeer(p)} title="Показать QR" tone="qr"><QrCode size={14} /></IconButton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {qrPeer && <QrModal peer={qrPeer} onClose={() => setQrPeer(null)} />}
    </section>
  );
}

function QrModal({ peer, onClose }) {
  const variants = [
    {
      key: 'native',
      title: 'AmneziaWG app',
      hint: 'Native .conf для AmneziaWG.',
      file: peer.links?.download,
      qr: peer.links?.qr_native_png,
      fileLabel: 'Скачать .conf',
    },
    peer.links?.download_vpn && peer.links?.qr_amnezia_vpn_png ? {
      key: 'vpn',
      title: 'AmneziaVPN app',
      hint: 'Специальный .vpn payload для AmneziaVPN.',
      file: peer.links.download_vpn,
      qr: peer.links.qr_amnezia_vpn_png,
      fileLabel: 'Скачать .vpn',
    } : null,
  ].filter(Boolean);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div className="modal-card qr-modal multi-qr-modal" role="dialog" aria-modal="true" aria-label="QR коды клиента" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>{peer.name}</h2>
            <p>{peer.protocol_title || peer.protocol} / {peer.ip_cidr}</p>
          </div>
          <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={17} /></button>
        </div>
        <div className="modal-qr-grid">
          {variants.map((item) => (
            <div className="modal-qr-panel" key={item.key}>
              <h3>{item.title}</h3>
              <p>{item.hint}</p>
              {item.qr && <img className="modal-qr-image" src={item.qr} alt={`${item.title} QR ${peer.name}`} />}
              <div className="modal-actions">
                <a className="orange-btn small" href={item.file}><Download size={14} /> {item.fileLabel}</a>
                <a className="blue-btn small" href={item.qr}><QrCode size={14} /> Скачать код</a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


function ClientPage({ clientId, onLogout }) {
  const [state, setState] = useState({ loading: true, peer: null, error: '' });

  const load = async () => {
    try {
      const data = await api(`/api/peers/${clientId}`);
      setState({ loading: false, peer: data.peer, error: '' });
    } catch (err) {
      setState({ loading: false, peer: null, error: err.message || 'Ошибка загрузки клиента' });
    }
  };

  useEffect(() => { load(); }, [clientId]);

  const peer = state.peer;
  const title = peer ? `${peer.name} ${peer.protocol_title || peer.protocol}` : 'Клиент';

  return (
    <Shell title={title} subtitle="WireGuard / AmneziaWG node management" onLogout={onLogout}>
      {state.error && <div className="warning">{state.error}</div>}
      {state.loading && <section className="card detail-card">Загрузка...</section>}
      {peer && (
        <>
          <section className="card detail-card">
            <div className="detail-head">
              <a className="back-link" href="/"><ChevronLeft size={16} /> Назад</a>
              <span className={peer.status === 'active' ? 'active-text' : 'muted'}>{peer.status === 'active' ? 'ACTIVE' : 'OFFLINE'}</span>
            </div>
            <div className="detail-grid">
              <div><span>IP</span><code>{peer.ip_cidr}</code></div>
              <div><span>Endpoint</span><code>{peer.endpoint}</code></div>
              <div><span>Protocol</span><b>{peer.protocol_title || peer.protocol}</b></div>
              <div><span>Public key</span><code title={peer.public_key}>{shortKey(peer.public_key)}</code></div>
            </div>
          </section>

          <section className="qr-grid">
            <QrPanel
              title="QR для AmneziaWG app"
              hint="Native .conf. Если QR не применяется, скачай .conf и импортируй файлом."
              img={peer.links?.qr_native_png}
              config={peer.links?.download}
              qr={peer.links?.qr_native_png}
              configLabel="Скачать .conf"
            />
            {peer.links?.download_vpn && (
              <QrPanel
                title="QR для AmneziaVPN app"
                hint="Специальный payload для AmneziaVPN. Дополнительно можно скачать .vpn ключ."
                img={peer.links?.qr_amnezia_vpn_png}
                config={peer.links?.download_vpn}
                qr={peer.links?.qr_amnezia_vpn_png}
                configLabel="Скачать .vpn"
              />
            )}
          </section>

          <section className="card config-card">
            <div className="section-head">
              <h2>Конфиг</h2>
              <button className="copy-button" type="button" onClick={() => navigator.clipboard?.writeText(peer.config || '')}><Copy size={15} /> Copy</button>
            </div>
            <pre>{peer.config}</pre>
          </section>
        </>
      )}
    </Shell>
  );
}

function QrPanel({ title, hint, img, config, qr, configLabel }) {
  return (
    <section className="card qr-card">
      <h2>{title}</h2>
      <p>{hint}</p>
      {img && <img className="qr-image" src={img} alt={title} />}
      <div className="qr-actions">
        <a className="orange-btn small" href={config}><Download size={14} /> {configLabel}</a>
        <a className="blue-btn small" href={qr}><QrCode size={14} /> Скачать QR</a>
      </div>
    </section>
  );
}

function shortKey(value) {
  if (!value) return '-';
  return value.length > 22 ? `${value.slice(0, 10)}...${value.slice(-8)}` : value;
}

function formatBytes(v) {
  const n = Number(v || 0);
  if (!n) return '0.00 B';
  const units = ['B', 'KiB', 'MiB', 'GiB'];
  let x = n, i = 0;
  while (x >= 1024 && i < units.length - 1) { x /= 1024; i++; }
  return `${x.toFixed(2)} ${units[i]}`;
}

function StatusPage({ protocol, onLogout }) {
  const [state, setState] = useState({ loading: true, status: null, error: '' });

  const load = async () => {
    try {
      const data = await api('/api/node/status');
      setState({ loading: false, status: data, error: '' });
    } catch (err) {
      setState({ loading: false, status: null, error: err.message || 'Ошибка статуса' });
    }
  };

  useEffect(() => { load(); }, [protocol]);

  const item = state.status?.protocols?.[protocol];
  const raw = item?.raw || '';
  const peers = useMemo(() => parseStatusPeers(raw), [raw]);
  const online = peers.filter((p) => p.online).length;
  const title = `${item?.title || protocol} status`;
  const [rawOpen, setRawOpen] = useState(false);

  return (
    <Shell title={title} subtitle={item ? `${item.container} / ${item.interface}` : 'Protocol health'} onLogout={onLogout}>
      {state.error && <div className="warning">{state.error}</div>}
      {state.loading && <section className="card detail-card">Загрузка...</section>}
      {item && (
        <>
          <div className="status-hero">
            <section className="card status-summary-card">
              <div className="status-summary-head">
                <div>
                  <span className="eyebrow">Protocol</span>
                  <h2>{item.title}</h2>
                </div>
                <span className={item.available ? 'status-pill online' : 'status-pill offline'}>{item.available ? <Wifi size={14} /> : <WifiOff size={14} />}{item.available ? 'ONLINE' : 'OFFLINE'}</span>
              </div>
              <div className="status-meta-grid">
                <div><span>Interface</span><code>{item.interface}</code></div>
                <div><span>Container</span><code>{item.container}</code></div>
                <div><span>Endpoint</span><code>{item.endpoint}</code></div>
                <div><span>Network</span><code>{item.network}</code></div>
              </div>
            </section>
            <div className="status-kpis">
              <StatCard value={peers.length} label="peer'ов всего" icon={Users} />
              <StatCard value={online} label="активных peer'ов" icon={Wifi} />
              <StatCard value={item.port} label="порт UDP" icon={Network} />
            </div>
          </div>

          <section className="card status-peers-card">
            <div className="section-head">
              <h2>Peer'ы</h2>
              <button className="blue-btn small" type="button" onClick={() => setRawOpen(true)}><Terminal size={14} /> raw</button>
            </div>
            <div className="table-wrap">
              <table className="status-table">
                <colgroup>
                  <col style={{ width: 100 }} />
                  <col style={{ width: 210 }} />
                  <col style={{ width: 150 }} />
                  <col style={{ width: 190 }} />
                  <col style={{ width: 210 }} />
                  <col style={{ width: 230 }} />
                </colgroup>
                <thead><tr><th>Статус</th><th>Public key</th><th>Allowed IP</th><th>Endpoint</th><th>Handshake</th><th>Transfer</th></tr></thead>
                <tbody>
                  {peers.map((peer) => (
                    <tr key={peer.publicKey}>
                      <td><span className={peer.online ? 'active-text' : 'muted'}>{peer.online ? 'ACTIVE' : 'OFFLINE'}</span></td>
                      <td title={peer.publicKey}><code>{shortKey(peer.publicKey)}</code></td>
                      <td>{peer.allowedIp || '-'}</td>
                      <td title={peer.endpoint}>{peer.endpoint || '-'}</td>
                      <td>{peer.handshake || '-'}</td>
                      <td>{peer.transfer || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card raw-card compact-raw-card">
            <div className="section-head"><h2>Raw output</h2><button className="copy-button" type="button" onClick={() => setRawOpen(true)}><Terminal size={15} /> Open</button></div>
            <pre>{raw || item.reason}</pre>
          </section>
          {rawOpen && <RawModal title={`${item.title} raw output`} raw={raw || item.reason} onClose={() => setRawOpen(false)} />}
        </>
      )}
    </Shell>
  );
}

function RawModal({ title, raw, onClose }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div className="modal-card raw-modal" role="dialog" aria-modal="true" aria-label="Raw output" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            <p>Live command output</p>
          </div>
          <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть"><X size={17} /></button>
        </div>
        <pre>{raw}</pre>
        <div className="modal-actions">
          <button className="blue-btn small" type="button" onClick={() => navigator.clipboard?.writeText(raw)}><Copy size={14} /> Copy</button>
        </div>
      </div>
    </div>
  );
}

function parseStatusPeers(raw) {
  const peers = [];
  let current = null;
  for (const line of String(raw || '').split('\n')) {
    const trimmed = line.trim();
    if (trimmed.startsWith('peer: ')) {
      current = { publicKey: trimmed.slice(6), endpoint: '', allowedIp: '', handshake: '', transfer: '', online: false };
      peers.push(current);
      continue;
    }
    if (!current) continue;
    if (trimmed.startsWith('endpoint: ')) {
      current.endpoint = trimmed.slice(10);
      current.online = current.endpoint && current.endpoint !== '(none)';
    } else if (trimmed.startsWith('allowed ips: ')) {
      current.allowedIp = trimmed.slice(13);
    } else if (trimmed.startsWith('latest handshake: ')) {
      current.handshake = trimmed.slice(18);
      if (current.handshake && current.handshake !== '0' && current.handshake !== '(none)') current.online = true;
    } else if (trimmed.startsWith('transfer: ')) {
      current.transfer = trimmed.slice(10);
    }
  }
  return peers;
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
    <Shell title="3WG Panel" subtitle="WireGuard / AmneziaWG node management" onLogout={onLogout}>
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
    </Shell>
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
  if (!auth.ok) return <Login onLogin={check} />;
  const clientMatch = window.location.pathname.match(/^\/client\/(\d+)$/);
  const statusMatch = window.location.pathname.match(/^\/status\/(wireguard|amneziawg)$/);
  if (clientMatch) return <ClientPage clientId={clientMatch[1]} onLogout={logout} />;
  if (statusMatch) return <StatusPage protocol={statusMatch[1]} onLogout={logout} />;
  return <Dashboard onLogout={logout} />;
}

createRoot(document.getElementById('root')).render(<App />);
