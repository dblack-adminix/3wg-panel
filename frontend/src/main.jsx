import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  ArrowUpRight,
  ChevronLeft,
  Check,
  Copy,
  Download,
  Folder,
  FolderPlus,
  Home,
  Key,
  LogOut,
  Menu,
  Network,
  Moon,
  Power,
  Pencil,
  Plus,
  QrCode,
  RefreshCw,
  RotateCcw,
  Send,
  Trash2,
  X,
  ShieldCheck,
  Sun,
  Terminal,
  Users,
  Wifi,
  WifiOff,
} from 'lucide-react';
import './styles.css';

const getInitialTheme = () => {
  try {
    return localStorage.getItem('3wg-theme') || 'light';
  } catch {
    return 'light';
  }
};

const applyTheme = (theme) => {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('3wg-theme', theme); } catch {}
};

applyTheme(getInitialTheme());

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

function IconButton({ href, onClick, title, tone = 'default', disabled = false, children }) {
  const className = `icon-button ${tone}`;
  if (href) {
    return <a className={className} href={href} title={title} aria-label={title}>{children}</a>;
  }
  return <button className={className} onClick={onClick} title={title} aria-label={title} type="button" disabled={disabled}>{children}</button>;
}

function VersionLine() {
  const [version, setVersion] = useState({ loading: true, data: null });

  useEffect(() => {
    let alive = true;
    api('/api/version')
      .then((data) => { if (alive) setVersion({ loading: false, data }); })
      .catch(() => { if (alive) setVersion({ loading: false, data: { state: 'unknown' } }); });
    return () => { alive = false; };
  }, []);

  if (version.loading) {
    return <div className="version-line muted-version">Проверяю версию...</div>;
  }

  const data = version.data || {};
  if (data.state === 'outdated') {
    return (
      <div className="version-line update-available">
        Доступно обновление <code>({data.latest})</code>. Установлена версия <code>({data.current})</code>
      </div>
    );
  }
  if (data.state === 'latest') {
    return <div className="version-line">Вы используете последнюю версию <code>({data.current})</code></div>;
  }
  if (data.state === 'ahead') {
    return <div className="version-line">Установлена dev-версия <code>({data.current})</code>, последний tag <code>({data.latest})</code></div>;
  }
  return <div className="version-line muted-version">Версия <code>({data.current || 'unknown'})</code>. Проверка обновлений недоступна</div>;
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

function Sidebar({ onLogout, protocols: initialProtocols = null, user, mobileOpen = false, onClose }) {
  const path = window.location.pathname;
  const isHome = path === '/' || path === '/ui';
  const [protocols, setProtocols] = useState(initialProtocols);
  const isAdmin = Boolean(user?.is_admin);

  useEffect(() => {
    if (initialProtocols) {
      setProtocols(initialProtocols);
      return undefined;
    }
    let alive = true;
    api('/api/node/protocols')
      .then((data) => { if (alive) setProtocols(data.protocols || {}); })
      .catch(() => { if (alive) setProtocols({}); });
    return () => { alive = false; };
  }, [initialProtocols]);

  const showWireGuardStatus = Boolean(protocols?.wireguard?.available);
  const showAmneziaStatus = protocols?.amneziawg?.available !== false;

  return (
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="brand-block">
        <img src="/logogrin.png" alt="3WG" />
      </div>
      <div className="nav-title">ОБЗОР</div>
      <a className={`nav ${isHome ? 'active' : ''}`} href="/" onClick={onClose}><Home size={14} /> <span>Главная</span></a>
      {isAdmin && showWireGuardStatus && <a className={`nav ${path === '/status/wireguard' ? 'active' : ''}`} href="/status/wireguard" onClick={onClose}><Activity size={14} /> <span>WG status</span></a>}
      {isAdmin && showAmneziaStatus && <a className={`nav ${path === '/status/amneziawg' ? 'active' : ''}`} href="/status/amneziawg" onClick={onClose}><Activity size={14} /> <span>AWG status</span></a>}
      {isAdmin && <div className="nav-title">УПРАВЛЕНИЕ</div>}
      {isAdmin && <a className={`nav ${path === '/users' ? 'active' : ''}`} href="/users" onClick={onClose}><Users size={14} /> <span>Пользователи</span></a>}
      {isAdmin && <a className={`nav ${path === '/apikeys' ? 'active' : ''}`} href="/apikeys" onClick={onClose}><Key size={14} /> <span>API-ключи</span></a>}
      {isAdmin && <a className={`nav ${path === '/monitoring' ? 'active' : ''}`} href="/monitoring" onClick={onClose}><Activity size={14} /> <span>Мониторинг</span></a>}
      {isAdmin && <a className={`nav ${path === '/updates' ? 'active' : ''}`} href="/updates" onClick={onClose}><RefreshCw size={14} /> <span>Обновления</span></a>}
      {isAdmin && <a className={`nav ${path === '/audit' ? 'active' : ''}`} href="/audit" onClick={onClose}><Terminal size={14} /> <span>Audit log</span></a>}
      {isAdmin && <a className={`nav ${path === '/backups' ? 'active' : ''}`} href="/backups" onClick={onClose}><Download size={14} /> <span>Backups</span></a>}
      {isAdmin && <div className="nav-title">ИНСТРУМЕНТЫ</div>}
      {isAdmin && <a className={`nav ${path === '/tools/system' ? 'active' : ''}`} href="/tools/system" onClick={onClose}><Activity size={14} /> <span>System Status</span></a>}
      {isAdmin && <a className={`nav ${path === '/tools/health' ? 'active' : ''}`} href="/tools/health" onClick={onClose}><ShieldCheck size={14} /> <span>Diagnostics</span></a>}
      {isAdmin && <a className={`nav ${path === '/tools/ping' ? 'active' : ''}`} href="/tools/ping" onClick={onClose}><Network size={14} /> <span>Ping</span></a>}
      {isAdmin && <a className={`nav ${path === '/tools/traceroute' ? 'active' : ''}`} href="/tools/traceroute" onClick={onClose}><ArrowUpRight size={14} /> <span>Traceroute</span></a>}
      <button className="nav logout" onClick={onLogout}><LogOut size={14} /> <span>Выход</span></button>
    </aside>
  );
}

function Shell({ title, subtitle, onLogout, protocols, user, children }) {
  const [navOpen, setNavOpen] = useState(false);
  const [theme, setTheme] = useState(getInitialTheme);
  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light';
    setTheme(next);
    applyTheme(next);
  };

  return (
    <div className="layout" id="top">
      <Sidebar onLogout={onLogout} protocols={protocols} user={user} mobileOpen={navOpen} onClose={() => setNavOpen(false)} />
      {navOpen && <button className="sidebar-backdrop" type="button" aria-label="Закрыть меню" onClick={() => setNavOpen(false)} />}
      <main className="main">
        <header className="topbar">
          <button className="mobile-menu-button" type="button" title="Меню" aria-label="Открыть меню" onClick={() => setNavOpen(true)}><Menu size={18} /></button>
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          <div className="top-actions">
            <button onClick={toggleTheme} title={theme === 'light' ? 'Темная тема' : 'Светлая тема'} aria-label="Переключить тему">
              {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
            </button>
            <button onClick={onLogout} title="Выйти"><LogOut size={15} /></button>
          </div>
        </header>
        {children}
        <footer className="app-footer">
          <div>© 2026 3WG Panel. Все права защищены. Связь: <a href="https://t.me/vorchiks" target="_blank" rel="noreferrer">@vorchiks</a>, <a href="mailto:vitaly@goreev.ru">vitaly@goreev.ru</a>, <a href="https://3wg.ru" target="_blank" rel="noreferrer">3wg.ru</a>, <a href="https://github.com/dblack-adminix/3wg-panel" target="_blank" rel="noreferrer">GitHub</a>.</div>
          <VersionLine />
        </footer>
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

function CreateClient({ protocols, categories, quota, isAdmin, onCreated }) {
  const [name, setName] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [expiresPreset, setExpiresPreset] = useState('');
  const [trafficLimitPreset, setTrafficLimitPreset] = useState('');
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
      const payload = { name, protocols: selected, category_id: categoryId || null };
      if (isAdmin) payload.expires_at = expiresPreset ? futureExpiresAt(Number(expiresPreset)) : null;
      if (isAdmin) payload.traffic_limit_bytes = trafficLimitPreset ? gibToBytes(Number(trafficLimitPreset)) : 0;
      await api('/api/peers', { method: 'POST', body: JSON.stringify(payload) });
      setName('');
      setExpiresPreset('');
      setTrafficLimitPreset('');
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
        {isAdmin && (
          <select className="category-select create-category-select" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Без категории</option>
            {(categories || []).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
          </select>
        )}
        {isAdmin && (
          <select className="category-select create-category-select" value={expiresPreset} onChange={(e) => setExpiresPreset(e.target.value)}>
            <option value="">Без срока</option>
            <option value="1">На 1 день</option>
            <option value="7">На 7 дней</option>
            <option value="30">На 30 дней</option>
            <option value="90">На 90 дней</option>
          </select>
        )}
        {isAdmin && (
          <select className="category-select create-category-select" value={trafficLimitPreset} onChange={(e) => setTrafficLimitPreset(e.target.value)}>
            <option value="">Без лимита трафика</option>
            <option value="1">1 GiB</option>
            <option value="5">5 GiB</option>
            <option value="10">10 GiB</option>
            <option value="50">50 GiB</option>
            <option value="100">100 GiB</option>
          </select>
        )}
        <div className="protocol-row">
          <label className={!wgAvailable ? 'muted' : ''}><input type="checkbox" checked={wireguard} disabled={!wgAvailable} onChange={(e) => setWireguard(e.target.checked)} /> WireGuard {!wgAvailable && <span className="pill bad">не установлен</span>}</label>
          <label><input type="checkbox" checked={amnezia} disabled={!available} onChange={(e) => setAmnezia(e.target.checked)} /> AmneziaWG</label>
        </div>
        <button className="orange-btn" disabled={loading || !name.trim() || (quota?.limited && quota.remaining <= 0)}><Plus size={15} /> Создать клиента</button>
        {error && <div className="warning">{error}</div>}
      </form>
      {quota?.limited && <div className="quota-note">Лимит peer'ов: <b>{quota.used}</b> из <b>{quota.limit}</b>, доступно <b>{quota.remaining}</b></div>}
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

function ClientsTable({ peers, categories, isAdmin, onRefresh }) {
  const toast = useToast();
  const [qrPeer, setQrPeer] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [activeCategory, setActiveCategory] = useState('all');
  const [newCategoryName, setNewCategoryName] = useState('');
  const [categoryBusy, setCategoryBusy] = useState(false);
  const [editingCategory, setEditingCategory] = useState(null);
  const [categoryToDelete, setCategoryToDelete] = useState(null);

  const filteredPeers = useMemo(() => {
    if (activeCategory === 'all') return peers;
    if (activeCategory === 'none') return peers.filter((peer) => !peer.category_id);
    return peers.filter((peer) => String(peer.category_id || '') === activeCategory);
  }, [peers, activeCategory]);

  const categoryCounts = useMemo(() => {
    const counts = { all: peers.length, none: 0 };
    for (const peer of peers) {
      if (peer.category_id) counts[peer.category_id] = (counts[peer.category_id] || 0) + 1;
      else counts.none += 1;
    }
    return counts;
  }, [peers]);

  const createCategory = async (e) => {
    e.preventDefault();
    const name = newCategoryName.trim();
    if (!name) return;
    setCategoryBusy('create');
    try {
      const data = await api('/api/categories', { method: 'POST', body: JSON.stringify({ name }) });
      setNewCategoryName('');
      if (data.category?.id) setActiveCategory(String(data.category.id));
      await onRefresh();
    } catch (err) {
      toast.error(err.message || 'Ошибка создания категории');
    } finally {
      setCategoryBusy(false);
    }
  };

  const updateCategory = async (e) => {
    e.preventDefault();
    const id = editingCategory?.id;
    const name = editingCategory?.name?.trim();
    if (!id || !name) return;
    setCategoryBusy(`edit-${id}`);
    try {
      await api(`/api/categories/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) });
      setEditingCategory(null);
      await onRefresh();
    } catch (err) {
      toast.error(err.message || 'Ошибка изменения категории');
    } finally {
      setCategoryBusy(false);
    }
  };

  const deleteCategory = async (category) => {
    setCategoryBusy(`delete-${category.id}`);
    try {
      await api(`/api/categories/${category.id}`, { method: 'DELETE' });
      if (activeCategory === String(category.id)) setActiveCategory('none');
      setCategoryToDelete(null);
      await onRefresh();
    } catch (err) {
      toast.error(err.message || 'Ошибка удаления категории');
    } finally {
      setCategoryBusy(false);
    }
  };

  const changePeerCategory = async (peer, categoryId) => {
    setBusyId(peer.id);
    try {
      await api(`/api/peers/${peer.id}`, { method: 'PATCH', body: JSON.stringify({ category_id: categoryId || null }) });
      await onRefresh();
    } catch (err) {
      toast.error(err.message || 'Ошибка изменения категории');
    } finally {
      setBusyId(null);
    }
  };

  const changePeerExpiration = async (peer, preset) => {
    setBusyId(peer.id);
    try {
      const expiresAt = preset ? futureExpiresAt(Number(preset)) : null;
      await api(`/api/peers/${peer.id}`, { method: 'PATCH', body: JSON.stringify({ expires_at: expiresAt }) });
      await onRefresh();
    } catch (err) {
      toast.error(err.message || 'Ошибка изменения срока');
    } finally {
      setBusyId(null);
    }
  };

  const changePeerTrafficLimit = async (peer, preset) => {
    setBusyId(peer.id);
    try {
      const limitBytes = preset ? gibToBytes(Number(preset)) : 0;
      await api(`/api/peers/${peer.id}`, { method: 'PATCH', body: JSON.stringify({ traffic_limit_bytes: limitBytes }) });
      await onRefresh();
    } catch (err) {
      toast.error(err.message || 'Ошибка изменения лимита');
    } finally {
      setBusyId(null);
    }
  };

  const mutatePeer = async (peer, action) => {
    setBusyId(peer.id);
    try {
      if (action === 'delete') {
        await api(peer.links?.delete || `/api/peers/${peer.id}`, { method: 'DELETE' });
      } else if (action === 'traffic_reset') {
        await api(peer.links?.traffic_reset || `/api/peers/${peer.id}/traffic-reset`, { method: 'POST' });
      } else {
        await api(peer.links?.[action] || `/api/peers/${peer.id}/${action}`, { method: 'POST' });
      }
      await onRefresh();
    } catch (err) {
      toast.error(err.message || 'Ошибка операции');
    } finally {
      setBusyId(null);
    }
  };

  const askPeerAction = (peer, action) => setPendingAction({ peer, action });

  const confirmMeta = pendingAction ? getPeerConfirmMeta(pendingAction.peer, pendingAction.action) : null;
  const isInteractiveTarget = (target) => Boolean(target?.closest?.('a,button,input,select,textarea,label,[role="button"]'));
  const openPeer = (peer) => {
    if (peer?.links?.html) window.location.href = peer.links.html;
  };
  const openPeerFromEvent = (event, peer) => {
    if (isInteractiveTarget(event.target)) return;
    openPeer(peer);
  };

  return (
    <section className="card clients-card">
      <div className="section-head">
        <h2>Клиенты</h2>
        <IconButton onClick={onRefresh} title="Обновить таблицу" tone="ghost"><RefreshCw size={15} /></IconButton>
      </div>
      {isAdmin && <div className="category-panel">
        <div className="category-filters" aria-label="Категории клиентов">
          <button className={activeCategory === 'all' ? 'category-chip active' : 'category-chip'} onClick={() => setActiveCategory('all')} type="button">
            <Folder size={14} /> Все <span>{categoryCounts.all}</span>
          </button>
          <button className={activeCategory === 'none' ? 'category-chip active' : 'category-chip'} onClick={() => setActiveCategory('none')} type="button">
            Без категории <span>{categoryCounts.none}</span>
          </button>
          {(categories || []).map((category) => (
            <div className={activeCategory === String(category.id) ? 'category-item active' : 'category-item'} key={category.id}>
              {editingCategory?.id === category.id ? (
                <form className="category-edit" onSubmit={updateCategory}>
                  <input value={editingCategory.name} onChange={(e) => setEditingCategory({ ...editingCategory, name: e.target.value })} autoFocus maxLength={64} />
                  <button className="category-tool save" type="submit" title="Сохранить" disabled={categoryBusy === `edit-${category.id}`}><Check size={13} /></button>
                  <button className="category-tool" type="button" title="Отмена" onClick={() => setEditingCategory(null)}><X size={13} /></button>
                </form>
              ) : (
                <>
                  <button className="category-chip" onClick={() => setActiveCategory(String(category.id))} type="button">
                    {category.name} <span>{categoryCounts[category.id] || 0}</span>
                  </button>
                  <button className="category-tool" type="button" title="Переименовать категорию" onClick={() => setEditingCategory({ id: category.id, name: category.name })}><Pencil size={13} /></button>
                  <button className="category-tool danger" type="button" title="Удалить категорию" onClick={() => setCategoryToDelete(category)}><Trash2 size={13} /></button>
                </>
              )}
            </div>
          ))}
        </div>
        <form className="category-create" onSubmit={createCategory}>
          <FolderPlus size={15} />
          <input value={newCategoryName} onChange={(e) => setNewCategoryName(e.target.value)} placeholder="Новая категория" maxLength={64} />
          <button disabled={Boolean(categoryBusy) || !newCategoryName.trim()} type="submit">Создать</button>
        </form>
      </div>}
      <div className="table-wrap">
        <table className="clients-table">
          <colgroup>
            <col style={{ width: 42 }} />
            <col style={{ width: 155 }} />
            {isAdmin && <col style={{ width: 78 }} />}
            {isAdmin && <col style={{ width: 120 }} />}
            <col style={{ width: 100 }} />
            <col style={{ width: 100 }} />
            <col style={{ width: 82 }} />
            {isAdmin && <col style={{ width: 210 }} />}
            <col style={{ width: 180 }} />
            <col style={{ width: 100 }} />
            <col style={{ width: isAdmin ? 110 : 96 }} />
          </colgroup>
          <thead>
            <tr>
              <th>ID</th>
              <th>Имя пользователя</th>
              {isAdmin && <th>Создал</th>}
              {isAdmin && <th>Категория</th>}
              <th>Протокол</th>
              <th>Внутренний IP</th>
              <th>Статус</th>
              {isAdmin && <th>Ограничения</th>}
              <th>Сеть</th>
              <th>Трафик</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredPeers.map((p) => (
              <tr className="clickable-row" key={p.id} tabIndex={0} onClick={(e) => openPeerFromEvent(e, p)} onKeyDown={(e) => { if (e.key === 'Enter') openPeer(p); }}>
                <td>{p.id}</td>
                <td><b>{p.name}</b>{!isAdmin && <small>создал: {p.created_by_label || p.owner_username || 'admin'}</small>}</td>
                {isAdmin && <td><span className="owner-badge">{p.created_by_label || p.owner_username || 'admin'}</span></td>}
                {isAdmin && (
                  <td>
                    <select className="category-select table-category-select" value={p.category_id || ''} disabled={busyId === p.id} onChange={(e) => changePeerCategory(p, e.target.value)}>
                      <option value="">Без категории</option>
                      {(categories || []).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
                    </select>
                  </td>
                )}
                <td><span className={`proto ${p.protocol === 'wireguard' ? 'proto-wireguard' : ''}`}>{p.protocol_title || p.protocol}</span></td>
                <td><code>{p.ip_cidr}</code></td>
                <td><PeerStatus peer={p} /></td>
                {isAdmin && (
                  <td>
                    <div className="policy-cell">
                      <div className="policy-selects">
                        <select className="category-select table-expiration-select" value={expirationPresetValue(p)} disabled={busyId === p.id} onChange={(e) => changePeerExpiration(p, e.target.value)}>
                          <option value="">Без срока</option>
                          <option value="1">1 день</option>
                          <option value="7">7 дней</option>
                          <option value="30">30 дней</option>
                          <option value="90">90 дней</option>
                        </select>
                        <select className="category-select table-limit-select" value={trafficLimitPresetValue(p)} disabled={busyId === p.id} onChange={(e) => changePeerTrafficLimit(p, e.target.value)}>
                          <option value="">Без лимита</option>
                          <option value="1">1 GiB</option>
                          <option value="5">5 GiB</option>
                          <option value="10">10 GiB</option>
                          <option value="50">50 GiB</option>
                          <option value="100">100 GiB</option>
                        </select>
                      </div>
                      <span className={p.traffic_limit?.exceeded ? 'limit-bar exceeded' : 'limit-bar'} title={p.traffic_limit?.label || 'без лимита'}>
                        <i style={{ width: `${p.traffic_limit?.enabled ? Math.max(4, p.traffic_limit.percent || 0) : 0}%` }} />
                      </span>
                      <small>
                        <span className={p.expiration?.expired ? 'expiration-bad' : p.expiration?.enabled ? 'expiration-soon' : ''}>{p.expiration?.label || 'без срока'}</span>
                        <span className={p.traffic_limit?.exceeded ? 'expiration-bad' : p.traffic_limit?.enabled ? 'expiration-soon' : ''}>{p.traffic_limit?.label || 'без лимита'}</span>
                      </small>
                    </div>
                  </td>
                )}
                <td title={`${p.live?.endpoint || '(none)'} ${p.live?.latest_handshake || ''}`}>
                  <div className="network-cell">
                    <b>{p.live?.endpoint || '(none)'}</b>
                    <small>{p.live?.latest_handshake && p.live.latest_handshake !== '0' ? new Date(Number(p.live.latest_handshake) * 1000).toLocaleString('ru-RU') : '-'}</small>
                  </div>
                </td>
                <td>
                  <div className="traffic-cell">
                    <span><b>RX</b> {formatBytes(p.live?.rx)}</span>
                    <span><b>TX</b> {formatBytes(p.live?.tx)}</span>
                  </div>
                </td>
                <td className="actions-cell">
                  <div className="actions">
                    <IconButton href={p.links?.download || '#'} title="Скачать config" tone="download"><Download size={14} /></IconButton>
                    <IconButton onClick={() => setQrPeer(p)} title="Показать QR" tone="qr"><QrCode size={14} /></IconButton>
                    {p.enabled ? (
                      <IconButton onClick={() => askPeerAction(p, 'disable')} title="Отключить peer" tone="block" disabled={busyId === p.id}><Power size={14} /></IconButton>
                    ) : (
                      <IconButton onClick={() => askPeerAction(p, 'enable')} title="Включить peer" tone="enable" disabled={busyId === p.id}><Power size={14} /></IconButton>
                    )}
                    {isAdmin && <IconButton onClick={() => askPeerAction(p, 'traffic_reset')} title="Сбросить счётчик трафика" tone="reset" disabled={busyId === p.id}><RotateCcw size={14} /></IconButton>}
                    <IconButton onClick={() => askPeerAction(p, 'delete')} title="Удалить peer" tone="danger" disabled={busyId === p.id}><Trash2 size={14} /></IconButton>
                  </div>
                </td>
              </tr>
            ))}
            {filteredPeers.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 11 : 8} className="empty-table">В этой категории пока нет peer'ов</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="mobile-peer-list">
        {filteredPeers.map((p) => (
          <article className="mobile-peer-card clickable-card" key={p.id} tabIndex={0} onClick={(e) => openPeerFromEvent(e, p)} onKeyDown={(e) => { if (e.key === 'Enter') openPeer(p); }}>
            <div className="mobile-peer-head">
              <div>
                <b>{p.name}</b>
                <small>#{p.id}{isAdmin ? ` · ${p.created_by_label || p.owner_username || 'admin'}` : ''}</small>
              </div>
              <span className={`proto ${p.protocol === 'wireguard' ? 'proto-wireguard' : ''}`}>{p.protocol_title || p.protocol}</span>
            </div>
            <div className="mobile-peer-meta">
              <div><span>IP</span><code>{p.ip_cidr}</code></div>
              <div><span>Статус</span><PeerStatus peer={p} /></div>
              <div><span>RX</span><b>{formatBytes(p.live?.rx)}</b></div>
              <div><span>TX</span><b>{formatBytes(p.live?.tx)}</b></div>
            </div>
            <div className="mobile-peer-network">
              <span>Endpoint</span>
              <b>{p.live?.endpoint || '(none)'}</b>
              <small>{p.live?.latest_handshake && p.live.latest_handshake !== '0' ? new Date(Number(p.live.latest_handshake) * 1000).toLocaleString('ru-RU') : 'последнего подключения нет'}</small>
            </div>
            {isAdmin && (
              <div className="mobile-peer-admin">
                <select className="category-select" value={p.category_id || ''} disabled={busyId === p.id} onChange={(e) => changePeerCategory(p, e.target.value)}>
                  <option value="">Без категории</option>
                  {(categories || []).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
                </select>
                <div className="policy-selects">
                  <select className="category-select table-expiration-select" value={expirationPresetValue(p)} disabled={busyId === p.id} onChange={(e) => changePeerExpiration(p, e.target.value)}>
                    <option value="">Без срока</option>
                    <option value="1">1 день</option>
                    <option value="7">7 дней</option>
                    <option value="30">30 дней</option>
                    <option value="90">90 дней</option>
                  </select>
                  <select className="category-select table-limit-select" value={trafficLimitPresetValue(p)} disabled={busyId === p.id} onChange={(e) => changePeerTrafficLimit(p, e.target.value)}>
                    <option value="">Без лимита</option>
                    <option value="1">1 GiB</option>
                    <option value="5">5 GiB</option>
                    <option value="10">10 GiB</option>
                    <option value="50">50 GiB</option>
                    <option value="100">100 GiB</option>
                  </select>
                </div>
                <small>
                  <span className={p.expiration?.expired ? 'expiration-bad' : p.expiration?.enabled ? 'expiration-soon' : ''}>{p.expiration?.label || 'без срока'}</span>
                  <span className={p.traffic_limit?.exceeded ? 'expiration-bad' : p.traffic_limit?.enabled ? 'expiration-soon' : ''}>{p.traffic_limit?.label || 'без лимита'}</span>
                </small>
              </div>
            )}
            <div className="mobile-peer-actions">
              <IconButton href={p.links?.download || '#'} title="Скачать config" tone="download"><Download size={14} /></IconButton>
              <IconButton onClick={() => setQrPeer(p)} title="Показать QR" tone="qr"><QrCode size={14} /></IconButton>
              {p.enabled ? (
                <IconButton onClick={() => askPeerAction(p, 'disable')} title="Отключить peer" tone="block" disabled={busyId === p.id}><Power size={14} /></IconButton>
              ) : (
                <IconButton onClick={() => askPeerAction(p, 'enable')} title="Включить peer" tone="enable" disabled={busyId === p.id}><Power size={14} /></IconButton>
              )}
              {isAdmin && <IconButton onClick={() => askPeerAction(p, 'traffic_reset')} title="Сбросить счётчик трафика" tone="reset" disabled={busyId === p.id}><RotateCcw size={14} /></IconButton>}
              <IconButton onClick={() => askPeerAction(p, 'delete')} title="Удалить peer" tone="danger" disabled={busyId === p.id}><Trash2 size={14} /></IconButton>
            </div>
          </article>
        ))}
        {filteredPeers.length === 0 && <div className="mobile-empty">В этой категории пока нет peer'ов</div>}
      </div>
      {qrPeer && <QrModal peer={qrPeer} onClose={() => setQrPeer(null)} />}
      {categoryToDelete && (
        <ConfirmModal
          title="Удалить категорию"
          message={`Удалить категорию "${categoryToDelete.name}"?`}
          details={`Peer'ы внутри категории не удалятся. Они перейдут в "Без категории": ${categoryCounts[categoryToDelete.id] || 0} шт.`}
          tone="danger"
          confirmLabel="Удалить"
          loading={categoryBusy === `delete-${categoryToDelete.id}`}
          onCancel={() => setCategoryToDelete(null)}
          onConfirm={() => deleteCategory(categoryToDelete)}
        />
      )}
      {pendingAction && (
        <ConfirmModal
          title={confirmMeta.title}
          message={confirmMeta.message}
          details={confirmMeta.details}
          tone={confirmMeta.tone}
          confirmLabel={confirmMeta.confirmLabel}
          loading={busyId === pendingAction.peer.id}
          onCancel={() => setPendingAction(null)}
          onConfirm={async () => {
            await mutatePeer(pendingAction.peer, pendingAction.action);
            setPendingAction(null);
          }}
        />
      )}
    </section>
  );
}

function getPeerConfirmMeta(peer, action) {
  if (action === 'delete') {
    return {
      title: 'Удалить peer',
      message: `Удалить "${peer.name}" окончательно?`,
      details: 'Peer будет удален из контейнера, server config и скрыт из панели. Конфиг будет переименован как deleted.',
      tone: 'danger',
      confirmLabel: 'Удалить',
    };
  }
  if (action === 'disable') {
    return {
      title: 'Отключить peer',
      message: `Отключить "${peer.name}"?`,
      details: 'Клиент останется в панели, но peer будет снят с интерфейса и не сможет подключаться.',
      tone: 'block',
      confirmLabel: 'Отключить',
    };
  }
  if (action === 'traffic_reset') {
    return {
      title: 'Сбросить трафик',
      message: `Сбросить счётчик трафика для "${peer.name}"?`,
      details: `Накопленный RX/TX станет 0. Текущий live-счётчик контейнера будет принят как новая базовая точка. Сейчас: ${peer.traffic_limit?.label || 'без лимита'}.`,
      tone: 'block',
      confirmLabel: 'Сбросить',
    };
  }
  return {
    title: 'Включить peer',
    message: `Включить "${peer.name}"?`,
    details: 'Peer будет возвращен в live-интерфейс и server config.',
    tone: 'enable',
    confirmLabel: 'Включить',
  };
}

function ConfirmModal({ title, message, details, tone = 'default', confirmLabel, loading, onCancel, onConfirm }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onCancel}>
      <div className={`modal-card confirm-modal ${tone}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            <p>Подтверждение действия</p>
          </div>
          <button className="modal-close" type="button" onClick={onCancel} aria-label="Закрыть"><X size={17} /></button>
        </div>
        <div className="confirm-body">
          <strong>{message}</strong>
          <p>{details}</p>
        </div>
        <div className="confirm-actions">
          <button className="confirm-cancel" type="button" onClick={onCancel} disabled={loading}>Отмена</button>
          <button className={`confirm-submit ${tone}`} type="button" onClick={onConfirm} disabled={loading}>{loading ? 'Выполняю...' : confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

const ToastContext = createContext({ show: () => {}, success: () => {}, error: () => {}, info: () => {} });
const ConfirmContext = createContext(async () => false);

function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const show = useCallback((tone, message, title) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setItems((list) => [...list, { id, tone, title, message }].slice(-4));
    window.setTimeout(() => setItems((list) => list.filter((item) => item.id !== id)), 4200);
  }, []);
  const apiValue = useMemo(() => ({
    show,
    success: (message, title = 'Готово') => show('success', message, title),
    error: (message, title = 'Ошибка') => show('error', message, title),
    info: (message, title = 'Информация') => show('info', message, title),
  }), [show]);
  return (
    <ToastContext.Provider value={apiValue}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {items.map((item) => (
          <div className={`toast-item ${item.tone}`} key={item.id}>
            <b>{item.title}</b>
            <span>{item.message}</span>
            <button type="button" onClick={() => setItems((list) => list.filter((current) => current.id !== item.id))}><X size={13} /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ConfirmProvider({ children }) {
  const [pending, setPending] = useState(null);
  const confirm = useCallback((options) => new Promise((resolve) => {
    setPending({ ...options, resolve });
  }), []);
  const close = (result) => {
    const resolve = pending?.resolve;
    setPending(null);
    if (resolve) resolve(result);
  };
  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <ConfirmModal
          title={pending.title || 'Подтвердите действие'}
          message={pending.message || 'Продолжить?'}
          details={pending.details || ''}
          tone={pending.tone || 'default'}
          confirmLabel={pending.confirmLabel || 'Продолжить'}
          onCancel={() => close(false)}
          onConfirm={() => close(true)}
        />
      )}
    </ConfirmContext.Provider>
  );
}

function useToast() {
  return useContext(ToastContext);
}

function useConfirm() {
  return useContext(ConfirmContext);
}

function PeerStatus({ peer }) {
  if (peer.traffic_limit?.exceeded || peer.status === 'limited') {
    return <span className="blocked-text">LIMIT</span>;
  }
  if (peer.expiration?.expired || peer.status === 'expired') {
    return <span className="blocked-text">EXPIRED</span>;
  }
  if (!peer.enabled || peer.status === 'disabled') {
    return <span className="blocked-text">BLOCKED</span>;
  }
  if (peer.status === 'active') {
    return <span className="active-text">ONLINE</span>;
  }
  return <span className="muted">OFFLINE</span>;
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


function PeerDiagnosticsResult({ data }) {
  const summary = data?.summary || {};
  const checks = data?.checks || [];
  return (
    <div className="peer-diag">
      <div className="peer-diag-summary">
        <div className="ok"><span>OK</span><b>{summary.ok || 0}</b></div>
        <div className="warn"><span>WARN</span><b>{summary.warn || 0}</b></div>
        <div className="fail"><span>FAIL</span><b>{summary.fail || 0}</b></div>
      </div>
      <div className="peer-diag-list">
        {checks.map((item, idx) => (
          <div className={`peer-diag-check ${item.status}`} key={`${item.name}-${idx}`}>
            <span>{item.status?.toUpperCase() || 'WARN'}</span>
            <div>
              <b>{item.name}</b>
              <small>{item.message}</small>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


function ClientPage({ clientId, onLogout, user }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [state, setState] = useState({ loading: true, peer: null, error: '' });
  const [diag, setDiag] = useState({ loading: false, result: null, error: '' });
  const [noteDraft, setNoteDraft] = useState('');
  const [noteSaving, setNoteSaving] = useState(false);

  const load = async () => {
    try {
      const data = await api(`/api/peers/${clientId}`);
      setState({ loading: false, peer: data.peer, error: '' });
    } catch (err) {
      setState({ loading: false, peer: null, error: err.message || 'Ошибка загрузки клиента' });
    }
  };

  useEffect(() => { load(); }, [clientId]);
  useEffect(() => { setNoteDraft(state.peer?.note || ''); }, [state.peer?.id, state.peer?.note]);

  const peer = state.peer;
  const title = peer ? `${peer.name} ${peer.protocol_title || peer.protocol}` : 'Клиент';
  const live = peer?.live || {};
  const clientEndpoint = live.endpoint && live.endpoint !== '(none)' ? live.endpoint : null;
  const lastHandshake = live.latest_handshake && live.latest_handshake !== '0' ? Number(live.latest_handshake) : null;
  const peerIp = peer?.ip_cidr ? peer.ip_cidr.split('/')[0] : '';
  const isOnline = peer?.status === 'active';

  const runPeerDiagnostics = async () => {
    if (!peer?.id) return;
    setDiag({ loading: true, result: null, error: '' });
    try {
      const result = await api(`/api/peers/${peer.id}/diagnostics`);
      setDiag({ loading: false, result, error: '' });
    } catch (err) {
      setDiag({ loading: false, result: null, error: err.message || 'Ошибка диагностики peer' });
    }
  };

  const resetPeerTraffic = async () => {
    if (!peer || !user?.is_admin) return;
    const ok = await confirm({
      title: 'Сбросить трафик',
      message: `Сбросить накопленный трафик для "${peer.name}"?`,
      details: 'Счётчик RX/TX будет обнулён в панели. Конфиг peer не изменится.',
      tone: 'block',
      confirmLabel: 'Сбросить',
    });
    if (!ok) return;
    try {
      await api(peer.links?.traffic_reset || `/api/peers/${peer.id}/traffic-reset`, { method: 'POST' });
      await load();
      toast.success('Счётчик трафика сброшен');
    } catch (err) {
      toast.error(err.message || 'Ошибка сброса счётчика');
    }
  };

  const savePeerNote = async () => {
    if (!peer || !user?.is_admin) return;
    setNoteSaving(true);
    try {
      const data = await api(`/api/peers/${peer.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ note: noteDraft }),
      });
      setState({ loading: false, peer: data.peer, error: '' });
    } catch (err) {
      setState((s) => ({ ...s, error: err.message || 'Ошибка сохранения заметки' }));
    } finally {
      setNoteSaving(false);
    }
  };

  return (
    <Shell title={title} subtitle="WireGuard / AmneziaWG node management" onLogout={onLogout} user={user}>
      {state.error && <div className="warning">{state.error}</div>}
      {state.loading && <section className="card detail-card">Загрузка...</section>}
      {peer && (
        <>
          <section className="card detail-card peer-hero-card">
            <div className="detail-head">
              <a className="back-link" href="/"><ChevronLeft size={16} /> Назад</a>
              <div className="peer-hero-actions">
                <button className="copy-button" type="button" onClick={load}><RefreshCw size={14} /> Обновить</button>
                {user?.is_admin && <button className="orange-btn small" type="button" onClick={runPeerDiagnostics} disabled={diag.loading}><Activity size={14} /> Диагностика</button>}
                {user?.is_admin && <button className="blue-btn small" type="button" onClick={resetPeerTraffic}><RotateCcw size={14} /> Сброс трафика</button>}
                <span className={isOnline ? 'status-pill online' : peer.enabled ? 'status-pill offline' : 'status-pill disabled'}>{isOnline ? 'ONLINE' : peer.enabled ? 'OFFLINE' : 'DISABLED'}</span>
              </div>
            </div>
            <div className="peer-hero-grid">
              <div className="peer-identity">
                <span className="eyebrow">Peer #{peer.id}</span>
                <h2>{peer.name}</h2>
                <div className="peer-badges">
                  <span className={peer.protocol === 'wireguard' ? 'protocol-badge wg' : 'protocol-badge awg'}>{peer.protocol_title || peer.protocol}</span>
                  <span>{peer.category_name || 'Без категории'}</span>
                  <span>создал: {peer.created_by_label || peer.owner_username || 'admin'}</span>
                </div>
              </div>
              <div className="peer-live-card">
                <span>Последний handshake</span>
                <b>{lastHandshake ? formatPeerTime(lastHandshake) : '-'}</b>
                <small>{peer.handshake_age_seconds != null ? `${formatDuration(peer.handshake_age_seconds)} назад` : 'нет подключения'}</small>
              </div>
            </div>
            <div className="detail-grid peer-detail-grid">
              <div><span>Internal IP</span><code>{peer.ip_cidr}</code></div>
              <div><span>Server endpoint</span><code>{peer.endpoint}</code></div>
              <div><span>Client endpoint</span><code>{clientEndpoint || '(none)'}</code></div>
              <div><span>Created</span><b>{formatPeerTime(peer.created_at)}</b></div>
              <div><span>Expires</span><b>{peer.expiration?.label || 'без срока'}</b></div>
              <div><span>Traffic limit</span><b>{peer.traffic_limit?.label || 'без лимита'}</b></div>
              <div><span>Public key</span><code title={peer.public_key}>{shortKey(peer.public_key)}</code></div>
              <div><span>RX / TX</span><b>{formatBytes(live.rx)} / {formatBytes(live.tx)}</b></div>
            </div>
          </section>

          <section className="card peer-note-card">
            <div className="section-head">
              <h2>Заметка</h2>
              {user?.is_admin && <button className="copy-button" type="button" onClick={savePeerNote} disabled={noteSaving || noteDraft === (peer.note || '')}>{noteSaving ? 'Сохраняю...' : 'Сохранить'}</button>}
            </div>
            {user?.is_admin ? (
              <textarea
                className="peer-note-input"
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
                maxLength={500}
                placeholder="Например: телефон клиента, офис, ответственный, дата выдачи..."
              />
            ) : (
              <p className="peer-note-view">{peer.note || 'Заметки нет'}</p>
            )}
            <div className="peer-note-meta">{noteDraft.length}/500</div>
          </section>

          {(diag.result || diag.error || diag.loading) && (
            <section className="card peer-diagnostics-card">
              <div className="section-head">
                <h2>Диагностика peer</h2>
                <span className={diag.result?.summary?.fail ? 'status-pill offline' : diag.loading ? 'status-pill disabled' : 'status-pill online'}>{diag.loading ? 'RUNNING' : diag.result?.summary?.fail ? 'ISSUES' : 'OK'}</span>
              </div>
              {diag.loading && <div className="tool-placeholder"><Terminal size={28} /><span>Проверяю {peerIp} из контейнера {peer.protocol_title}...</span></div>}
              {diag.error && <div className="warning">{diag.error}</div>}
              {diag.result && <PeerDiagnosticsResult data={diag.result} />}
            </section>
          )}

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

function formatPeerTime(ts) {
  return ts ? new Date(Number(ts) * 1000).toLocaleString('ru-RU') : '-';
}

function futureExpiresAt(days) {
  return Math.floor(Date.now() / 1000) + Math.max(1, Number(days || 1)) * 86400;
}

function gibToBytes(gib) {
  return Math.round(Math.max(0, Number(gib || 0)) * 1024 * 1024 * 1024);
}

function expirationPresetValue(peer) {
  const secondsLeft = Number(peer?.expiration?.seconds_left || 0);
  if (!peer?.expiration?.enabled || secondsLeft <= 0) return '';
  const days = Math.max(1, Math.round(secondsLeft / 86400));
  if (days <= 1) return '1';
  if (days <= 7) return '7';
  if (days <= 30) return '30';
  return '90';
}

function trafficLimitPresetValue(peer) {
  const limit = Number(peer?.traffic_limit?.limit_bytes || 0);
  if (!limit) return '';
  const gib = Math.round(limit / 1024 / 1024 / 1024);
  if (gib <= 1) return '1';
  if (gib <= 5) return '5';
  if (gib <= 10) return '10';
  if (gib <= 50) return '50';
  return '100';
}

function userTrafficLimitPresetValue(user) {
  const limit = Number(user?.traffic_limit?.limit_bytes || user?.traffic_limit_bytes || 0);
  if (!limit) return '';
  const gib = Math.round(limit / 1024 / 1024 / 1024);
  if (gib <= 10) return '10';
  if (gib <= 50) return '50';
  if (gib <= 100) return '100';
  if (gib <= 250) return '250';
  return '500';
}

function userExpirationPresetValue(user) {
  const secondsLeft = Number(user?.expiration?.seconds_left || 0);
  if (!user?.expiration?.enabled || secondsLeft <= 0) return '';
  const days = Math.max(1, Math.round(secondsLeft / 86400));
  if (days <= 7) return '7';
  if (days <= 30) return '30';
  if (days <= 90) return '90';
  if (days <= 180) return '180';
  return '365';
}

function formatDuration(seconds) {
  const n = Math.max(0, Number(seconds || 0));
  if (n < 60) return `${Math.round(n)} сек`;
  if (n < 3600) return `${Math.floor(n / 60)} мин`;
  if (n < 86400) return `${Math.floor(n / 3600)} ч ${Math.floor((n % 3600) / 60)} мин`;
  return `${Math.floor(n / 86400)} д ${Math.floor((n % 86400) / 3600)} ч`;
}

function formatBytes(v) {
  const n = Number(v || 0);
  if (!n) return '0.00 B';
  const units = ['B', 'KiB', 'MiB', 'GiB'];
  let x = n, i = 0;
  while (x >= 1024 && i < units.length - 1) { x /= 1024; i++; }
  return `${x.toFixed(2)} ${units[i]}`;
}

function StatusPage({ protocol, onLogout, user }) {
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
    <Shell title={title} subtitle={item ? `${item.container} / ${item.interface}` : 'Protocol health'} onLogout={onLogout} user={user}>
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
                      <td><span className={peer.online ? 'active-text' : 'muted'}>{peer.online ? 'ONLINE' : 'OFFLINE'}</span></td>
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

function isRecentHandshakeText(value) {
  if (!value || value === '0' || value === '(none)' || value === '-') return false;
  const normalized = value.toLowerCase();
  if (normalized.includes('second')) return true;
  const minuteMatch = normalized.match(/(\d+)\s+minute/);
  if (minuteMatch) return Number(minuteMatch[1]) <= 3;
  return false;
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
    } else if (trimmed.startsWith('allowed ips: ')) {
      current.allowedIp = trimmed.slice(13);
    } else if (trimmed.startsWith('latest handshake: ')) {
      current.handshake = trimmed.slice(18);
      current.online = isRecentHandshakeText(current.handshake);
    } else if (trimmed.startsWith('transfer: ')) {
      current.transfer = trimmed.slice(10);
    }
  }
  return peers;
}

function protocolTrafficRows(peers, protocols) {
  const map = new Map();
  for (const p of Object.values(protocols || {})) {
    map.set(p.protocol, {
      protocol: p.protocol,
      title: p.title,
      interface: p.interface,
      available: p.available,
      rx: 0,
      tx: 0,
      peers: 0,
    });
  }
  for (const peer of peers || []) {
    const key = peer.protocol;
    const row = map.get(key) || {
      protocol: key,
      title: peer.protocol_title || key,
      interface: key,
      available: true,
      rx: 0,
      tx: 0,
      peers: 0,
    };
    row.rx += Number(peer.live?.rx || 0);
    row.tx += Number(peer.live?.tx || 0);
    row.peers += 1;
    map.set(key, row);
  }
  return Array.from(map.values()).filter((row) => row.available || row.peers || row.rx || row.tx);
}

function TrafficChart({ points }) {
  const data = points.length ? points : [{ rate: 0 }];
  const max = Math.max(1, ...data.map((p) => p.rate || 0));
  const width = 360;
  const height = 88;
  const step = data.length > 1 ? width / (data.length - 1) : width;
  const coords = data.map((p, i) => {
    const x = i * step;
    const y = height - ((p.rate || 0) / max) * (height - 10) - 5;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const area = coords.length > 1 ? `0,${height} ${coords.join(' ')} ${width},${height}` : `0,${height} ${width},${height}`;
  return (
    <svg className="traffic-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <polygon points={area} />
      <polyline points={coords.join(' ')} />
    </svg>
  );
}

function TrafficStatusTracker({ history, active = true }) {
  const count = 36;
  const samples = history.slice(-count);
  const padded = [...Array(Math.max(0, count - samples.length)).fill(null), ...samples];

  return (
    <div className="status-tracker" aria-label="Последние замеры трафика">
      {padded.map((item, index) => {
        const rx = Number(item?.rxRate || 0);
        const tx = Number(item?.txRate || 0);
        const moving = rx + tx > 0;
        const status = !active ? 'down' : !item ? 'empty' : moving ? 'live' : 'idle';
        const trafficMix = rx > 0 && tx > 0 ? 'both' : rx > 0 ? 'rx' : tx > 0 ? 'tx' : '';
        const rxPct = moving ? Math.max(8, Math.min(92, Math.round((rx / (rx + tx)) * 100))) : 0;
        const title = item ? `${formatBytes(item.rxRate || 0)}/s RX · ${formatBytes(item.txRate || 0)}/s TX` : 'Нет замера';
        const style = trafficMix === 'both'
          ? { background: `linear-gradient(180deg, #d7ff2f 0 ${rxPct}%, #ff8c00 ${rxPct}% 100%)` }
          : undefined;
        return <i className={`${status} ${trafficMix}`} style={style} key={`${index}-${item?.t || 'empty'}`} title={title} />;
      })}
    </div>
  );
}

function TrafficWidget({ peers, protocols, history }) {
  const rows = useMemo(() => protocolTrafficRows(peers, protocols), [peers, protocols]);
  const totals = rows.reduce((acc, row) => ({ rx: acc.rx + row.rx, tx: acc.tx + row.tx }), { rx: 0, tx: 0 });
  const total = totals.rx + totals.tx;
  const latest = history.at(-1);
  const rxRate = latest?.rxRate || 0;
  const txRate = latest?.txRate || 0;
  const maxRow = Math.max(1, ...rows.map((row) => row.rx + row.tx));
  const operational = rows.filter((row) => row.available).length;
  const moving = rxRate + txRate > 0;

  return (
    <section className="card traffic-card">
      <div className="section-head traffic-head">
        <h2><Activity size={18} /> Трафик интерфейсов</h2>
        <span className={`live-dot ${moving ? 'active' : 'idle'}`}>{moving ? 'LIVE' : 'IDLE'}</span>
      </div>
      <div className="traffic-layout">
        <div className="traffic-total">
          <div className="traffic-status-title">
            <span className={`status-orb ${moving ? 'live' : 'idle'}`} />
            <b>{operational === rows.length ? 'Интерфейсы доступны' : 'Есть недоступные интерфейсы'}</b>
          </div>
          <span>Общий трафик</span>
          <strong>{formatBytes(total)}</strong>
          <div className="traffic-rates">
            <div><small>RX / sec</small><b>{formatBytes(rxRate)}</b></div>
            <div><small>TX / sec</small><b>{formatBytes(txRate)}</b></div>
          </div>
          <TrafficStatusTracker history={history} active={operational > 0} />
          <div className="traffic-color-legend">
            <span><i className="rx" /> RX входящий</span>
            <span><i className="tx" /> TX исходящий</span>
          </div>
          <div className="tracker-scale"><span>раньше</span><span>сейчас</span></div>
        </div>
        <div className="traffic-interfaces">
          {rows.map((row) => {
            const rowTotal = row.rx + row.tx;
            const pct = Math.max(3, Math.round((rowTotal / maxRow) * 100));
            const rowMoving = row.available && rowTotal > 0 && moving;
            const statusText = !row.available ? 'DOWN' : rowMoving ? 'TRAFFIC' : 'READY';
            return (
              <a className="traffic-row" key={row.protocol} href={`/traffic/${row.protocol}`}>
                <div className="traffic-row-top">
                  <span className={`traffic-proto ${row.protocol === 'wireguard' ? 'wg' : 'awg'}`}>{row.title}</span>
                  <span className={`traffic-state ${!row.available ? 'down' : rowMoving ? 'live' : 'idle'}`}>{statusText}</span>
                  <b>{formatBytes(rowTotal)}</b>
                </div>
                <div className="traffic-meta">
                  <span>{row.interface}</span>
                  <span>RX {formatBytes(row.rx)}</span>
                  <span>TX {formatBytes(row.tx)}</span>
                  <span>{row.peers} peer'ов</span>
                </div>
                <div className="traffic-bar"><i style={{ width: `${pct}%` }} /></div>
                <TrafficStatusTracker history={history} active={row.available} />
              </a>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function formatTrafficDay(day) {
  return new Date(Number(day) * 1000).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' });
}

function formatTrafficAxis(value) {
  const text = formatBytes(value);
  return text.replace('.00 ', ' ');
}

function TrafficMetric({ label, value, sub }) {
  return (
    <div className="traffic-metric">
      <span>{label}</span>
      <b>{value}</b>
      {sub && <small>{sub}</small>}
    </div>
  );
}

function MonthlyTrafficChart({ series }) {
  const width = 980;
  const height = 360;
  const margin = { top: 18, right: 22, bottom: 42, left: 72 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const max = Math.max(1, ...series.map((item) => item.total));
  const ticks = [1, 0.75, 0.5, 0.25, 0];
  const step = series.length ? plotWidth / series.length : plotWidth;
  const barWidth = Math.min(22, Math.max(8, step * 0.48));
  const xLabelEvery = Math.max(1, Math.ceil(series.length / 8));

  return (
    <div className="month-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="График трафика за 30 дней">
        {ticks.map((tick) => {
          const y = margin.top + (1 - tick) * plotHeight;
          return (
            <g key={tick}>
              <line className="chart-grid-line" x1={margin.left} x2={width - margin.right} y1={y} y2={y} />
              <text className="chart-axis-label" x={margin.left - 12} y={y + 4} textAnchor="end">{formatTrafficAxis(max * tick)}</text>
            </g>
          );
        })}
        <line className="chart-axis-line" x1={margin.left} x2={width - margin.right} y1={margin.top + plotHeight} y2={margin.top + plotHeight} />
        {series.map((item, index) => {
          const x = margin.left + index * step + (step - barWidth) / 2;
          const base = margin.top + plotHeight;
          const rxHeight = item.total ? Math.max(2, (item.rx / max) * plotHeight) : 0;
          const txHeight = item.total ? Math.max(item.tx ? 2 : 0, (item.tx / max) * plotHeight) : 0;
          const totalHeight = item.total ? Math.max(2, rxHeight + txHeight) : 1;
          const emptyY = base - totalHeight;
          const showLabel = index % xLabelEvery === 0 || index === series.length - 1;

          return (
            <g className="month-bar" key={item.day}>
              <title>{`${formatTrafficDay(item.day)}: ${formatBytes(item.total)} | RX ${formatBytes(item.rx)} | TX ${formatBytes(item.tx)}`}</title>
              {item.total ? (
                <>
                  <rect className="chart-rx-bar" x={x} y={base - rxHeight} width={barWidth} height={rxHeight} rx="4" />
                  <rect className="chart-tx-bar" x={x} y={base - rxHeight - txHeight} width={barWidth} height={txHeight} rx="4" />
                </>
              ) : (
                <rect className="chart-empty-bar" x={x} y={emptyY} width={barWidth} height={totalHeight} rx="3" />
              )}
              {showLabel && (
                <text className="chart-date-label" x={x + barWidth / 2} y={height - 16} textAnchor="middle">{formatTrafficDay(item.day)}</text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function TrafficDayTable({ series }) {
  const max = Math.max(1, ...series.map((item) => item.total));
  return (
    <div className="traffic-table-wrap">
      <table className="traffic-data-table">
        <thead>
          <tr>
            <th>Дата</th>
            <th>RX</th>
            <th>TX</th>
            <th>Всего</th>
            <th>Доля</th>
          </tr>
        </thead>
        <tbody>
          {series.slice().reverse().map((item) => {
            const pct = item.total ? Math.max(3, Math.round((item.total / max) * 100)) : 0;
            return (
              <tr key={item.day}>
                <td>{formatTrafficDay(item.day)}</td>
                <td>{formatBytes(item.rx)}</td>
                <td>{formatBytes(item.tx)}</td>
                <td><b>{formatBytes(item.total)}</b></td>
                <td>
                  <div className="table-progress" aria-label={`${pct}%`}>
                    <i style={{ width: `${pct}%` }} />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TrafficPage({ protocol, onLogout, user }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' });

  const load = async () => {
    try {
      const data = await api(`/api/traffic/history?protocol=${encodeURIComponent(protocol)}&days=30`);
      setState({ loading: false, data, error: '' });
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: err.message || 'Ошибка трафика' }));
    }
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 60000);
    return () => window.clearInterval(timer);
  }, [protocol]);

  const data = state.data;
  const current = data?.current || {};
  const series = data?.series || [];
  const today = series.at(-1) || { rx: 0, tx: 0, total: 0 };
  const activeDays = series.filter((item) => item.total > 0).length;
  const peak = series.reduce((best, item) => (item.total > best.total ? item : best), { rx: 0, tx: 0, total: 0, day: 0 });
  const title = data ? `${data.title} traffic` : 'Traffic';

  return (
    <Shell title={title} subtitle={data ? `${data.interface} / 30 дней` : 'Traffic history'} onLogout={onLogout} user={user}>
      <section className="traffic-page-card">
        <div className="detail-head">
          <a className="back-link" href="/"><ChevronLeft size={16} /> Главная</a>
          <button className="copy-button" type="button" onClick={load}><RefreshCw size={14} /> Обновить</button>
        </div>
        {state.error && <div className="warning">{state.error}</div>}
        {state.loading && <div className="muted">Загрузка...</div>}
        {data && (
          <>
            <div className="traffic-kpi-grid">
              <TrafficMetric label="Текущий счётчик" value={formatBytes(current.total)} sub={`RX ${formatBytes(current.rx)} / TX ${formatBytes(current.tx)}`} />
              <TrafficMetric label="За сегодня" value={formatBytes(today.total)} sub={`RX ${formatBytes(today.rx)} / TX ${formatBytes(today.tx)}`} />
              <TrafficMetric label="За 30 дней" value={formatBytes(data.month_total)} sub={`${activeDays} активных дней`} />
              <TrafficMetric label="Пиковый день" value={formatBytes(peak.total)} sub={peak.day ? formatTrafficDay(peak.day) : data.interface} />
            </div>
            <section className="traffic-analytics-panel">
              <div className="section-head traffic-chart-head">
                <div>
                  <h2>Динамика трафика</h2>
                  <p>{data.interface} · последние 30 дней</p>
                </div>
                <div className="traffic-legend">
                  <span><i className="rx-dot" /> RX</span>
                  <span><i className="tx-dot" /> TX</span>
                </div>
              </div>
              <MonthlyTrafficChart series={series} />
            </section>
            <section className="traffic-analytics-panel">
              <div className="section-head traffic-chart-head">
                <div>
                  <h2>Разбор по дням</h2>
                  <p>Приходящий, исходящий и общий объем</p>
                </div>
              </div>
              <TrafficDayTable series={series} />
            </section>
            <p className="traffic-note">{data.note}</p>
          </>
        )}
      </section>
    </Shell>
  );
}

function UserHome({ state, online, available, onRefresh, user }) {
  const quota = state.quota || {};
  const traffic = user?.traffic_limit || {};
  const totals = useMemo(() => state.peers.reduce((acc, peer) => ({
    rx: acc.rx + Number(peer.live?.rx || 0),
    tx: acc.tx + Number(peer.live?.tx || 0),
  }), { rx: 0, tx: 0 }), [state.peers]);
  const totalTraffic = totals.rx + totals.tx;
  const quotaPercent = quota?.limited && quota.limit ? Math.min(100, Math.round((Number(quota.used || 0) / Number(quota.limit || 1)) * 100)) : 0;
  const trafficPercent = traffic?.enabled ? Math.min(100, Math.round(Number(traffic.percent || 0))) : 0;

  return (
    <>
      <section className="user-hero-card">
        <div className="user-hero-copy">
          <span>Личный кабинет</span>
          <h2>{user?.username || 'Пользователь'}</h2>
          <p>Создавайте peer'ы в рамках выданного лимита, скачивайте конфиги и открывайте QR без админских инструментов.</p>
        </div>
        <div className="user-hero-stats">
          <div>
            <span>Peer'ы</span>
            <b>{quota?.limited ? `${quota.used} / ${quota.limit}` : state.peers.length}</b>
            <i><em style={{ width: `${quotaPercent}%` }} /></i>
            <small>{quota?.limited ? `доступно ${quota.remaining}` : 'без ограничения'}</small>
          </div>
          <div>
            <span>Трафик</span>
            <b>{traffic?.enabled ? traffic.label : formatBytes(totalTraffic)}</b>
            <i><em style={{ width: `${trafficPercent}%` }} /></i>
            <small>{traffic?.enabled ? `осталось ${formatBytes(traffic.remaining_bytes)}` : 'без общего лимита'}</small>
          </div>
          <div>
            <span>Сейчас в сети</span>
            <b>{online}</b>
            <small>{available} протокола доступно</small>
          </div>
        </div>
      </section>
      <div className="user-dashboard-grid">
        <CreateClient protocols={state.protocols} categories={state.categories} quota={state.quota} isAdmin={false} onCreated={onRefresh} />
        <section className="card user-peer-summary">
          <div className="section-head">
            <h2>Мои peer'ы</h2>
            <button className="copy-button" type="button" onClick={onRefresh}><RefreshCw size={14} /> Обновить</button>
          </div>
          <div className="user-peer-kpis">
            <div><span>Всего</span><b>{state.peers.length}</b></div>
            <div><span>Online</span><b>{online}</b></div>
            <div><span>RX</span><b>{formatBytes(totals.rx)}</b></div>
            <div><span>TX</span><b>{formatBytes(totals.tx)}</b></div>
          </div>
          <p>Ниже только ваши peer'ы. Для каждого доступны QR, скачивание config и быстрые действия.</p>
        </section>
      </div>
      <ClientsTable peers={state.peers} categories={state.categories} isAdmin={false} onRefresh={onRefresh} />
    </>
  );
}

function Dashboard({ onLogout, user }) {
  const [state, setState] = useState({ loading: true, peers: [], categories: [], status: null, protocols: {}, quota: null, error: '' });
  const [trafficHistory, setTrafficHistory] = useState([]);

  const load = async () => {
    try {
      const data = await api('/api/dashboard');
      const nextPeers = data.peers || [];
      const categories = data.categories || [];
      const cards = Object.fromEntries((data.cards || []).map((item) => [item.key, item]));
      const protocols = Object.fromEntries((data.protocols || []).map((item) => [item.protocol, item]));
      const status = {
        clients_total: cards.clients_total?.value ?? nextPeers.length,
        peers_total: cards.peers_total?.value ?? 0,
      };
      setState({ loading: false, peers: nextPeers, categories, status, protocols, quota: data.quota || null, error: '' });
      const totals = nextPeers.reduce((acc, peer) => ({
        rx: acc.rx + Number(peer.live?.rx || 0),
        tx: acc.tx + Number(peer.live?.tx || 0),
      }), { rx: 0, tx: 0 });
      setTrafficHistory((items) => {
        const prev = items.at(-1);
        const now = Date.now();
        const seconds = prev ? Math.max(1, (now - prev.t) / 1000) : 1;
        const rxRate = prev ? Math.max(0, (totals.rx - prev.rx) / seconds) : 0;
        const txRate = prev ? Math.max(0, (totals.tx - prev.tx) / seconds) : 0;
        return [...items.slice(-23), {
          t: now,
          rx: totals.rx,
          tx: totals.tx,
          rxRate,
          txRate,
          rate: rxRate + txRate,
        }];
      });
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: err.message || 'Ошибка загрузки' }));
    }
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const online = useMemo(() => state.peers.filter((p) => p.status === 'active').length, [state.peers]);
  const available = Object.values(state.protocols || {}).filter((p) => p.available).length;

  return (
    <Shell title="3WG Panel" subtitle={user?.is_admin ? 'WireGuard / AmneziaWG node management' : 'Личный кабинет peer-ов'} onLogout={onLogout} protocols={state.protocols} user={user}>
      {state.error && <div className="warning">{state.error}</div>}
      {!user?.is_admin ? (
        <UserHome state={state} online={online} available={available} onRefresh={load} user={user} />
      ) : (
        <>
      <div className="stats-grid">
        <StatCard value={state.status?.clients_total ?? state.peers.length} label="клиентов в панели" icon={Users} />
        <StatCard value={state.status?.peers_total ?? 0} label="peer'ов в контейнерах" icon={Network} />
        <StatCard value={online} label="сейчас в сети" icon={Wifi} />
        <StatCard value={available} label="доступных протокола" icon={ShieldCheck} />
      </div>
      <div className="dashboard-row">
        <CreateClient protocols={state.protocols} categories={state.categories} quota={state.quota} isAdmin={Boolean(user?.is_admin)} onCreated={load} />
        {user?.is_admin && <TrafficWidget peers={state.peers} protocols={state.protocols} history={trafficHistory} />}
      </div>
      <ClientsTable peers={state.peers} categories={state.categories} isAdmin={Boolean(user?.is_admin)} onRefresh={load} />
      {user?.is_admin && <section className="card status-card" id="status"><h2>Статус</h2><div className="status-grid">{Object.values(state.protocols || {}).map((p) => <div className="status-item" key={p.protocol}><b>{p.title}</b><span className={p.available ? 'status-ok' : 'status-bad'}>{p.available ? <Wifi size={14} /> : <WifiOff size={14} />}{p.available ? 'ONLINE' : 'OFFLINE'}</span><small>{p.container} / {p.interface}</small></div>)}</div></section>}
        </>
      )}
    </Shell>
  );
}

function UsersPage({ onLogout, user }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ username: '', password: '', peer_limit: 1, role: 'user', traffic_limit_bytes: 0, expires_days: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      const data = await api('/api/users');
      setUsers(data.users || []);
      setError('');
    } catch (err) {
      setError(err.message || 'Ошибка пользователей');
    }
  };

  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { expires_days, ...payload } = form;
      payload.expires_at = expires_days ? futureExpiresAt(Number(expires_days)) : null;
      const data = await api('/api/users', { method: 'POST', body: JSON.stringify(payload) });
      setUsers(data.users || []);
      setForm({ username: '', password: '', peer_limit: 1, role: 'user', traffic_limit_bytes: 0, expires_days: '' });
      setError('');
    } catch (err) {
      setError(err.message || 'Ошибка создания пользователя');
    } finally {
      setBusy(false);
    }
  };

  const patchUser = async (id, payload) => {
    setBusy(id);
    try {
      const data = await api(`/api/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
      setUsers(data.users || []);
      toast.success('Пользователь обновлён');
    } catch (err) {
      toast.error(err.message || 'Ошибка изменения пользователя');
    } finally {
      setBusy(false);
    }
  };

  const deleteUser = async (item) => {
    const ok = await confirm({
      title: 'Удалить пользователя',
      message: `Удалить пользователя "${item.username}"?`,
      details: "Его peer'ы не удалятся, они перейдут администратору.",
      tone: 'danger',
      confirmLabel: 'Удалить',
    });
    if (!ok) return;
    setBusy(item.id);
    try {
      const data = await api(`/api/users/${item.id}`, { method: 'DELETE' });
      setUsers(data.users || []);
      toast.success('Пользователь удалён');
    } catch (err) {
      toast.error(err.message || 'Ошибка удаления пользователя');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Пользователи" subtitle="Лимиты доступа к созданию peer'ов" onLogout={onLogout} user={user}>
      <div className="user-admin-grid">
        <section className="card user-create-card">
          <h2>Добавить пользователя</h2>
          <form onSubmit={create}>
            <label className="user-create-field">
              <span>Логин</span>
              <input className="name-input" placeholder="Например: client01" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </label>
            <label className="user-create-field">
              <span>Пароль</span>
              <input className="name-input" placeholder="Пароль" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </label>
            <label className="user-create-field">
              <span>Лимит peer'ов</span>
              <input className="name-input" min="0" type="number" value={form.peer_limit} onChange={(e) => setForm({ ...form, peer_limit: Number(e.target.value) })} />
            </label>
            <label className="user-create-field">
              <span>Лимит трафика</span>
              <select className="category-select" value={form.traffic_limit_bytes ? String(Math.round(form.traffic_limit_bytes / 1024 / 1024 / 1024)) : ''} onChange={(e) => setForm({ ...form, traffic_limit_bytes: e.target.value ? gibToBytes(Number(e.target.value)) : 0 })}>
                <option value="">Без лимита</option>
                <option value="10">10 GiB на пользователя</option>
                <option value="50">50 GiB на пользователя</option>
                <option value="100">100 GiB на пользователя</option>
                <option value="250">250 GiB на пользователя</option>
                <option value="500">500 GiB на пользователя</option>
              </select>
            </label>
            <label className="user-create-field">
              <span>Срок доступа</span>
              <select className="category-select" value={form.expires_days} onChange={(e) => setForm({ ...form, expires_days: e.target.value })}>
                <option value="">Без срока</option>
                <option value="7">7 дней</option>
                <option value="30">30 дней</option>
                <option value="90">90 дней</option>
                <option value="180">180 дней</option>
                <option value="365">1 год</option>
              </select>
            </label>
            <label className="user-create-field">
              <span>Роль</span>
              <select className="category-select" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="user">Пользователь</option>
                <option value="admin">Администратор</option>
              </select>
            </label>
            <button className="orange-btn" disabled={busy || !form.username.trim() || !form.password.trim()}><Plus size={15} /> Создать</button>
          </form>
          {error && <div className="warning">{error}</div>}
        </section>
        <section className="card users-list-card">
          <div className="section-head"><h2>Аккаунты</h2><button className="copy-button" type="button" onClick={load}><RefreshCw size={14} /> Обновить</button></div>
          <div className="table-wrap">
            <table className="clients-table users-table">
              <thead><tr><th>ID</th><th>Логин</th><th>Роль</th><th>Peer'ы</th><th>Лимит</th><th>Трафик</th><th>Срок</th><th>Статус</th><th>Действия</th></tr></thead>
              <tbody>
                {users.map((item) => (
                  <UserRow key={item.id} item={item} busy={busy === item.id} onPatch={patchUser} onDelete={deleteUser} />
                ))}
                {users.length === 0 && <tr><td className="empty-table" colSpan={9}>Дополнительных пользователей пока нет</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  );
}

function UserRow({ item, busy, onPatch, onDelete }) {
  const [limit, setLimit] = useState(item.peer_limit);
  const [trafficLimit, setTrafficLimit] = useState(userTrafficLimitPresetValue(item));
  const [expiresPreset, setExpiresPreset] = useState(userExpirationPresetValue(item));
  const [password, setPassword] = useState('');
  useEffect(() => { setLimit(item.peer_limit); }, [item.peer_limit]);
  useEffect(() => { setTrafficLimit(userTrafficLimitPresetValue(item)); }, [item.traffic_limit_bytes]);
  useEffect(() => { setExpiresPreset(userExpirationPresetValue(item)); }, [item.expires_at]);
  const traffic = item.traffic_limit || {};
  const expiration = item.expiration || {};
  const savePayload = {
    peer_limit: limit,
    traffic_limit_bytes: trafficLimit ? gibToBytes(Number(trafficLimit)) : 0,
    expires_at: expiresPreset ? futureExpiresAt(Number(expiresPreset)) : null,
  };
  return (
    <tr>
      <td>{item.id}</td>
      <td><b>{item.username}</b></td>
      <td>{item.role === 'admin' ? 'Администратор' : 'Пользователь'}</td>
      <td>{item.peers_used}</td>
      <td><input className="inline-number" type="number" min="0" value={limit} onChange={(e) => setLimit(Number(e.target.value))} /></td>
      <td>
        <div className="traffic-limit-cell user-traffic-limit-cell">
          <select className="category-select table-limit-select" value={trafficLimit} disabled={busy} onChange={(e) => setTrafficLimit(e.target.value)}>
            <option value="">без лимита</option>
            <option value="10">10 GiB</option>
            <option value="50">50 GiB</option>
            <option value="100">100 GiB</option>
            <option value="250">250 GiB</option>
            <option value="500">500 GiB</option>
          </select>
          <small className={traffic.exceeded ? 'expiration-bad' : ''}>{traffic.label || 'без лимита'}</small>
          <span className={`limit-bar ${traffic.exceeded ? 'exceeded' : ''}`}><i style={{ width: `${Math.max(2, Number(traffic.percent || 0))}%` }} /></span>
        </div>
      </td>
      <td>
        <div className="user-expiration-cell">
          <select className="category-select table-expiration-select" value={expiresPreset} disabled={busy} onChange={(e) => setExpiresPreset(e.target.value)}>
            <option value="">без срока</option>
            <option value="7">7 дней</option>
            <option value="30">30 дней</option>
            <option value="90">90 дней</option>
            <option value="180">180 дней</option>
            <option value="365">1 год</option>
          </select>
          <small className={expiration.expired ? 'expiration-bad' : expiration.enabled ? 'expiration-soon' : ''}>{expiration.label || 'без срока'}</small>
        </div>
      </td>
      <td><span className={item.enabled ? 'status-ok' : 'status-bad'}>{item.enabled ? 'ON' : 'OFF'}</span></td>
      <td className="actions-cell">
        <div className="user-actions">
          <div className="user-action-buttons">
            <button className="icon-button download" title="Сохранить лимиты" disabled={busy} onClick={() => onPatch(item.id, savePayload)}><Check size={14} /></button>
            <button className="icon-button block" title={item.enabled ? 'Отключить' : 'Включить'} disabled={busy} onClick={() => onPatch(item.id, { enabled: !item.enabled })}><Power size={14} /></button>
            <button className="icon-button danger" title="Удалить" disabled={busy} onClick={() => onDelete(item)}><Trash2 size={14} /></button>
          </div>
          <div className="user-password-row">
            <input className="inline-password" placeholder="новый пароль" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <button className="icon-button qr" title="Сменить пароль" disabled={busy || password.length < 6} onClick={async () => { await onPatch(item.id, { password }); setPassword(''); }}><Key size={14} /></button>
          </div>
        </div>
      </td>
    </tr>
  );
}

function formatAuditTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleString('ru-RU') : '-';
}

function AuditPage({ onLogout, user }) {
  const [events, setEvents] = useState([]);
  const [filters, setFilters] = useState({ limit: 100, action: '', actor: '', object_type: '' });
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', String(filters.limit || 100));
      if (filters.action.trim()) params.set('action', filters.action.trim());
      if (filters.actor.trim()) params.set('actor', filters.actor.trim());
      if (filters.object_type.trim()) params.set('object_type', filters.object_type.trim());
      const data = await api(`/api/audit?${params.toString()}`);
      setEvents(data.events || []);
      setError('');
    } catch (err) {
      setError(err.message || 'Ошибка audit log');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const actions = [...new Set(events.map((e) => e.action).filter(Boolean))].sort();
  const objectTypes = [...new Set(events.map((e) => e.object_type).filter(Boolean))].sort();

  return (
    <Shell title="Audit log" subtitle="История действий администраторов, пользователей и интеграций" onLogout={onLogout} user={user}>
      <section className="card audit-filter-card">
        <div className="section-head">
          <h2>Фильтры</h2>
          <button className="copy-button" type="button" onClick={load} disabled={loading}><RefreshCw size={14} /> Обновить</button>
        </div>
        <div className="audit-filters">
          <label><span>Limit</span><input className="name-input" type="number" min="1" max="500" value={filters.limit} onChange={(e) => setFilters({ ...filters, limit: Number(e.target.value) })} /></label>
          <label><span>Action</span><input className="name-input" list="audit-actions" value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} placeholder="peer.create" /></label>
          <label><span>Actor</span><input className="name-input" value={filters.actor} onChange={(e) => setFilters({ ...filters, actor: e.target.value })} placeholder="admin" /></label>
          <label><span>Object</span><input className="name-input" list="audit-objects" value={filters.object_type} onChange={(e) => setFilters({ ...filters, object_type: e.target.value })} placeholder="peer" /></label>
          <button className="orange-btn" type="button" onClick={load} disabled={loading}><Terminal size={15} /> Показать</button>
        </div>
        <datalist id="audit-actions">{actions.map((a) => <option key={a} value={a} />)}</datalist>
        <datalist id="audit-objects">{objectTypes.map((t) => <option key={t} value={t} />)}</datalist>
        {error && <div className="warning">{error}</div>}
      </section>

      <section className="card">
        <div className="section-head">
          <h2>События</h2>
          <span className="muted">{events.length} записей</span>
        </div>
        <div className="table-wrap">
          <table className="clients-table audit-table">
            <thead><tr><th>Время</th><th>Кто</th><th>Action</th><th>Object</th><th>IP</th><th>Context</th></tr></thead>
            <tbody>
              {events.length === 0 && <tr><td className="empty-table" colSpan={6}>{loading ? 'Загрузка...' : 'Событий пока нет'}</td></tr>}
              {events.map((event) => (
                <React.Fragment key={event.id}>
                  <tr>
                    <td>{formatAuditTime(event.ts)}</td>
                    <td><b>{event.actor?.username || '-'}</b><small>{event.actor?.role || '-'}</small></td>
                    <td><span className="audit-action">{event.action}</span></td>
                    <td><b>{event.object_label || event.object_id || '-'}</b><small>{event.object_type}{event.object_id ? ` #${event.object_id}` : ''}</small></td>
                    <td>{event.ip || '-'}</td>
                    <td>
                      <button className="copy-button" type="button" onClick={() => setExpanded(expanded === event.id ? null : event.id)}>
                        {expanded === event.id ? <ChevronLeft size={14} /> : <Terminal size={14} />} Details
                      </button>
                    </td>
                  </tr>
                  {expanded === event.id && (
                    <tr className="audit-details-row">
                      <td colSpan={6}>
                        <pre>{JSON.stringify({ context: event.context, user_agent: event.user_agent }, null, 2)}</pre>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Shell>
  );
}

function formatBackupTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleString('ru-RU') : '-';
}

const DEFAULT_AUTO_BACKUP = { enabled: false, interval_hours: 24, keep_last: 7, last_run_at: 0, next_run_at: 0 };

function BackupsPage({ onLogout, user }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [backups, setBackups] = useState([]);
  const [autoBackup, setAutoBackup] = useState(DEFAULT_AUTO_BACKUP);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = async () => {
    setBusy(true);
    try {
      const data = await api('/api/backups');
      setBackups(data.backups || []);
      setAutoBackup({ ...DEFAULT_AUTO_BACKUP, ...(data.auto || {}) });
      setError('');
    } catch (err) {
      setError(err.message || 'Ошибка загрузки backup');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    setBusy(true);
    setNotice('');
    try {
      const data = await api('/api/backups', { method: 'POST' });
      setBackups(data.backups || []);
      setAutoBackup({ ...DEFAULT_AUTO_BACKUP, ...(data.auto || {}) });
      setNotice(`Backup создан: ${data.backup?.name || ''}`);
      setError('');
    } catch (err) {
      setError(err.message || 'Ошибка создания backup');
    } finally {
      setBusy(false);
    }
  };

  const restore = async (backup, confirmText) => {
    const ok = await confirm({
      title: 'Восстановить backup',
      message: `Восстановить состояние панели из ${backup.name}?`,
      details: 'Будут заменены data/ и clients/. Перед восстановлением панель автоматически создаст pre-restore backup текущего состояния.',
      tone: 'danger',
      confirmLabel: 'Восстановить',
    });
    if (!ok) return;
    setBusy(backup.name);
    setNotice('');
    try {
      const data = await api(`/api/backups/${encodeURIComponent(backup.name)}/restore`, {
        method: 'POST',
        body: JSON.stringify({ confirm: 'RESTORE' }),
      });
      setBackups(data.backups || []);
      setAutoBackup({ ...DEFAULT_AUTO_BACKUP, ...(data.auto || {}) });
      setNotice(`Restore выполнен. Pre-restore backup: ${data.pre_restore_backup?.name || '-'}`);
      setError('');
      toast.success('Restore выполнен');
    } catch (err) {
      setError(err.message || 'Ошибка restore');
    } finally {
      setBusy(false);
    }
  };

  const saveAutoBackup = async (runNow = false) => {
    setBusy('auto');
    setNotice('');
    try {
      const data = await api('/api/backups/auto', {
        method: 'POST',
        body: JSON.stringify({ ...autoBackup, run_now: runNow }),
      });
      setBackups(data.backups || []);
      setAutoBackup({ ...DEFAULT_AUTO_BACKUP, ...(data.auto || {}) });
      setNotice(runNow ? 'Auto backup выполнен и настройки сохранены.' : 'Настройки auto backup сохранены.');
      setError('');
    } catch (err) {
      setError(err.message || 'Ошибка сохранения auto backup');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (backup) => {
    const ok = await confirm({
      title: 'Удалить backup',
      message: `Удалить архив ${backup.name}?`,
      details: 'Файл будет удалён с сервера. Восстановиться из него уже не получится.',
      tone: 'danger',
      confirmLabel: 'Удалить',
    });
    if (!ok) return;
    setBusy(backup.name);
    setNotice('');
    try {
      const data = await api(`/api/backups/${encodeURIComponent(backup.name)}`, { method: 'DELETE' });
      setBackups(data.backups || []);
      setAutoBackup({ ...DEFAULT_AUTO_BACKUP, ...(data.auto || {}) });
      setNotice(`Backup удалён: ${data.deleted || backup.name}`);
      setError('');
      toast.success('Backup удалён');
    } catch (err) {
      setError(err.message || 'Ошибка удаления backup');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Backups" subtitle="Снимки данных панели и клиентских конфигов" onLogout={onLogout} user={user}>
      <section className="card backup-hero-card">
        <div>
          <h2>Backup / Restore</h2>
          <p className="muted">Ручной backup нужен перед обновлениями, массовыми правками peer'ов и экспериментами с настройками.</p>
          <div className="backup-explain-grid">
            <div>
              <span>В backup входит</span>
              <b>data/ и clients/</b>
              <small>База панели, категории, пользователи, API-ключи, история, клиентские конфиги и QR payload.</small>
            </div>
            <div>
              <span>Не входит</span>
              <b>.env и Docker</b>
              <small>Секреты и host-настройки нужно хранить отдельно на сервере или в защищённом vault.</small>
            </div>
            <div>
              <span>Restore</span>
              <b>Безопасный откат</b>
              <small>Перед восстановлением автоматически создаётся pre-restore backup текущего состояния.</small>
            </div>
          </div>
        </div>
        <div className="backup-actions">
          <button className="orange-btn" type="button" onClick={create} disabled={busy}><Download size={15} /> Создать backup</button>
          <button className="copy-button" type="button" onClick={load} disabled={busy}><RefreshCw size={14} /> Обновить</button>
        </div>
        {notice && <div className="success">{notice}</div>}
        {error && <div className="warning">{error}</div>}
      </section>

      <section className="card backup-auto-card">
        <div className="section-head">
          <div>
            <h2>Auto backup</h2>
            <p className="muted">Панель сама создаёт архивы data/ и clients/ и чистит старые auto-файлы по лимиту.</p>
          </div>
          <span className={`runner-pill ${autoBackup.enabled ? 'ready' : 'disabled'}`}>{autoBackup.enabled ? 'ENABLED' : 'DISABLED'}</span>
        </div>
        <div className="backup-auto-grid">
          <label className="backup-toggle">
            <span>Расписание</span>
            <button
              className={`toggle-button ${autoBackup.enabled ? 'on' : ''}`}
              type="button"
              onClick={() => setAutoBackup((v) => ({ ...v, enabled: !v.enabled }))}
            >
              {autoBackup.enabled ? 'Включено' : 'Выключено'}
            </button>
          </label>
          <label>
            <span>Интервал</span>
            <select
              className="category-select"
              value={autoBackup.interval_hours}
              onChange={(e) => setAutoBackup((v) => ({ ...v, interval_hours: Number(e.target.value) }))}
            >
              <option value={1}>каждый час</option>
              <option value={6}>каждые 6 часов</option>
              <option value={12}>каждые 12 часов</option>
              <option value={24}>раз в сутки</option>
              <option value={48}>раз в 2 дня</option>
              <option value={168}>раз в неделю</option>
            </select>
          </label>
          <label>
            <span>Хранить auto backup'ов</span>
            <input
              className="inline-number"
              type="number"
              min="1"
              max="100"
              value={autoBackup.keep_last}
              onChange={(e) => setAutoBackup((v) => ({ ...v, keep_last: Number(e.target.value) }))}
            />
          </label>
          <div className="backup-auto-meta">
            <span>Последний запуск</span>
            <b>{formatBackupTime(autoBackup.last_run_at)}</b>
          </div>
          <div className="backup-auto-meta">
            <span>Следующий запуск</span>
            <b>{autoBackup.enabled ? formatBackupTime(autoBackup.next_run_at) : '-'}</b>
          </div>
          <div className="backup-auto-actions">
            <button className="copy-button" type="button" disabled={busy === 'auto'} onClick={() => saveAutoBackup(false)}><Check size={14} /> Сохранить</button>
            <button className="orange-btn" type="button" disabled={busy === 'auto'} onClick={() => saveAutoBackup(true)}><Download size={14} /> Создать сейчас</button>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="section-head">
          <h2>Файлы</h2>
          <span className="muted">{backups.length} backup'ов</span>
        </div>
        <div className="table-wrap">
          <table className="clients-table backup-table">
            <thead><tr><th>Файл</th><th>Размер</th><th>Создан</th><th>Действия</th></tr></thead>
            <tbody>
              {backups.length === 0 && <tr><td className="empty-table" colSpan={4}>{busy ? 'Загрузка...' : 'Backup пока нет'}</td></tr>}
              {backups.map((backup) => (
                <BackupRow key={backup.name} backup={backup} busy={busy === backup.name} onRestore={restore} onDelete={remove} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Shell>
  );
}

function BackupRow({ backup, busy, onRestore, onDelete }) {
  return (
    <tr>
      <td><b className="backup-name" title={backup.name}>{backup.name}</b></td>
      <td>{formatBytes(backup.size)}</td>
      <td>{formatBackupTime(backup.created_at)}</td>
      <td className="backup-row-actions">
        <a className="copy-button" href={backup.download_url} title="Скачать backup"><Download size={14} /> Скачать</a>
        <button className="copy-button danger-action" type="button" title="Восстановить из backup" disabled={busy} onClick={() => onRestore(backup)}>
          <RefreshCw size={14} /> Восстановить
        </button>
        <button className="copy-button delete-action" type="button" title="Удалить backup" disabled={busy} onClick={() => onDelete(backup)}>
          <Trash2 size={14} /> Удалить
        </button>
      </td>
    </tr>
  );
}

function ApiKeysPage({ onLogout, user }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [keys, setKeys] = useState([]);
  const [name, setName] = useState('');
  const [newToken, setNewToken] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = async () => {
    try { const d = await api('/api/apikeys'); setKeys(d.keys || []); setError(''); }
    catch (e) { setError(String(e.message || e)); }
  };
  useEffect(() => { load(); }, []);
  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const d = await api('/api/apikeys', { method: 'POST', body: JSON.stringify({ name }) });
      setNewToken(d.token);
      setName('');
      await load();
    } catch (e2) { setError(String(e2.message || e2)); }
    finally { setBusy(false); }
  };
  const remove = async (id) => {
    const ok = await confirm({
      title: 'Удалить API-ключ',
      message: 'Удалить ключ?',
      details: 'Интеграции, использующие его, перестанут работать.',
      tone: 'danger',
      confirmLabel: 'Удалить',
    });
    if (!ok) return;
    try { await api(`/api/apikeys/${id}`, { method: 'DELETE' }); await load(); toast.success('API-ключ удалён'); }
    catch (e) { const message = String(e.message || e); setError(message); toast.error(message); }
  };
  const fmt = (ts) => (ts ? new Date(ts * 1000).toLocaleString('ru-RU') : '—');
  return (
    <Shell title="API-ключи" subtitle="Доступ внешних систем по заголовку X-API-Key" onLogout={onLogout} user={user}>
      <div className="card create-card compact-create">
        <h2>Создать ключ</h2>
        <form onSubmit={create}>
          <input className="name-input" placeholder="Название (например: 3wg.ru backend)" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="orange-btn" type="submit" disabled={busy}><Plus size={15} /> Создать ключ</button>
        </form>
        {newToken && (
          <div className="success" style={{ wordBreak: 'break-all' }}>
            Новый ключ (скопируйте сейчас — он больше не будет показан):<br />
            <code>{newToken}</code>
            <button className="copy-button" type="button" style={{ marginLeft: 8 }} onClick={() => navigator.clipboard?.writeText(newToken)}><Copy size={13} /> Copy</button>
          </div>
        )}
        {error && <div className="warning">{error}</div>}
      </div>
      <div className="card">
        <h2>Активные ключи</h2>
        <div className="table-wrap">
          <table className="clients-table" style={{ width: '100%', minWidth: 640 }}>
            <thead><tr><th>ID</th><th>Название</th><th>Ключ</th><th>Создан</th><th>Использован</th><th></th></tr></thead>
            <tbody>
              {keys.length === 0 && <tr><td className="empty-table" colSpan={6}>Ключей пока нет</td></tr>}
              {keys.map((k) => (
                <tr key={k.id}>
                  <td>{k.id}</td>
                  <td>{k.name}</td>
                  <td><code>{k.token_masked}</code></td>
                  <td>{fmt(k.created_at)}</td>
                  <td>{fmt(k.last_used_at)}</td>
                  <td className="actions-cell"><div className="actions">
                    <button className="icon-button danger" title="Удалить" onClick={() => remove(k.id)}><Trash2 size={14} /></button>
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}

function MonitoringPage({ onLogout, user }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  const [telegram, setTelegram] = useState({ loading: true, data: null, error: '' });
  const [telegramForm, setTelegramForm] = useState({ enabled: false, bot_token: '', chat_id: '' });
  const [newToken, setNewToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [telegramBusy, setTelegramBusy] = useState(false);
  const [telegramSaved, setTelegramSaved] = useState('');

  const load = async () => {
    try {
      const [data, telegramData] = await Promise.all([api('/api/monitoring'), api('/api/telegram')]);
      setState({ loading: false, data, error: '' });
      setTelegram({ loading: false, data: telegramData, error: '' });
      setTelegramForm({ enabled: Boolean(telegramData.enabled), bot_token: '', chat_id: telegramData.chat_id || '' });
    } catch (err) {
      setState({ loading: false, data: null, error: err.message || 'Ошибка мониторинга' });
      setTelegram({ loading: false, data: null, error: err.message || 'Ошибка Telegram' });
    }
  };

  useEffect(() => { load(); }, []);

  const setEnabled = async (enabled) => {
    setBusy(true);
    try {
      const data = await api('/api/monitoring', { method: 'PATCH', body: JSON.stringify({ enabled }) });
      setState({ loading: false, data, error: '' });
    } catch (err) {
      setState((s) => ({ ...s, error: err.message || 'Ошибка сохранения' }));
    } finally {
      setBusy(false);
    }
  };

  const generateToken = async () => {
    if (state.data?.token_configured) {
      const ok = await confirm({
        title: 'Перевыпустить token',
        message: 'Создать новый token?',
        details: 'Старый token перестанет работать сразу после выпуска нового.',
        tone: 'block',
        confirmLabel: 'Перевыпустить',
      });
      if (!ok) return;
    }
    setBusy(true);
    try {
      const data = await api('/api/monitoring/token', { method: 'POST' });
      setNewToken(data.token || '');
      setState({ loading: false, data, error: '' });
      toast.success('Token создан. Скопируйте его сейчас.');
    } catch (err) {
      setState((s) => ({ ...s, error: err.message || 'Ошибка генерации token' }));
      toast.error(err.message || 'Ошибка генерации token');
    } finally {
      setBusy(false);
    }
  };

  const saveTelegram = async (e) => {
    e.preventDefault();
    setTelegramBusy(true);
    setTelegramSaved('');
    try {
      const payload = { enabled: telegramForm.enabled, chat_id: telegramForm.chat_id };
      if (telegramForm.bot_token.trim()) payload.bot_token = telegramForm.bot_token.trim();
      const data = await api('/api/telegram', { method: 'PATCH', body: JSON.stringify(payload) });
      setTelegram({ loading: false, data, error: '' });
      setTelegramForm({ enabled: Boolean(data.enabled), bot_token: '', chat_id: data.chat_id || '' });
      setTelegramSaved('Настройки Telegram сохранены');
    } catch (err) {
      setTelegram((s) => ({ ...s, error: err.message || 'Ошибка сохранения Telegram' }));
    } finally {
      setTelegramBusy(false);
    }
  };

  const testTelegram = async () => {
    setTelegramBusy(true);
    setTelegramSaved('');
    try {
      const data = await api('/api/telegram/test', { method: 'POST' });
      setTelegram({ loading: false, data, error: '' });
      setTelegramSaved('Тестовое сообщение отправлено');
    } catch (err) {
      setTelegram((s) => ({ ...s, error: err.message || 'Ошибка отправки Telegram' }));
    } finally {
      setTelegramBusy(false);
    }
  };

  const data = state.data || {};
  const curlExample = data.token_configured
    ? 'curl -H "Authorization: Bearer <token>" http://127.0.0.1:18080/metrics'
    : 'Сначала создайте token';

  return (
    <Shell title="Мониторинг" subtitle="Prometheus / Grafana metrics" onLogout={onLogout} user={user}>
      {(state.error || telegram.error) && <div className="warning">{state.error || telegram.error}</div>}
      {(state.loading || telegram.loading) && <section className="card">Загрузка...</section>}
      {!state.loading && !telegram.loading && (
        <div className="monitoring-grid">
          <section className="card monitoring-card">
            <div className="section-head">
              <h2>Prometheus /metrics</h2>
              <span className={data.enabled ? 'active-text' : 'muted'}>{data.enabled ? 'ENABLED' : 'DISABLED'}</span>
            </div>
            <div className="monitoring-status">
              <div><span>Endpoint</span><code>{data.metrics_path || '/metrics'}</code></div>
              <div><span>Auth</span><code>{data.auth_header || 'Authorization: Bearer <token>'}</code></div>
              <div><span>Token</span><b>{data.token_configured ? `настроен ...${data.token_suffix || ''}` : 'не создан'}</b></div>
              <div><span>Источник</span><b>{data.db_token_present ? 'web UI' : data.env_token_present ? '.env' : '-'}</b></div>
            </div>
            <div className="monitoring-actions">
              <button className="orange-btn" type="button" onClick={() => setEnabled(!data.enabled)} disabled={busy}>
                <Power size={15} /> {data.enabled ? 'Выключить /metrics' : 'Включить /metrics'}
              </button>
              <button className="blue-btn" type="button" onClick={generateToken} disabled={busy}>
                <Key size={15} /> {data.token_configured ? 'Перевыпустить token' : 'Создать token'}
              </button>
            </div>
          </section>

          <section className="card monitoring-card">
            <h2>Token для Prometheus</h2>
            {newToken ? (
              <div className="success monitoring-token">
                <span>Скопируйте token сейчас, потом он не будет показан:</span>
                <code>{newToken}</code>
                <button className="copy-button" type="button" onClick={() => navigator.clipboard?.writeText(newToken)}><Copy size={13} /> Copy</button>
              </div>
            ) : (
              <p className="muted">Plaintext token показывается только один раз после генерации. В базе хранится только hash.</p>
            )}
            <div className="monitoring-snippet">
              <span>Локальная проверка</span>
              <code>{curlExample}</code>
            </div>
          </section>

          <section className="card monitoring-card">
            <div className="section-head">
              <h2>Telegram notifications</h2>
              <span className={telegram.data?.enabled ? 'active-text' : 'muted'}>{telegram.data?.enabled ? 'ENABLED' : 'DISABLED'}</span>
            </div>
            <form className="monitoring-form" onSubmit={saveTelegram}>
              <label>
                <span>Bot token</span>
                <input className="name-input" type="password" placeholder={telegram.data?.token_suffix ? `настроен ...${telegram.data.token_suffix}` : '123456:ABC...'} value={telegramForm.bot_token} onChange={(e) => setTelegramForm({ ...telegramForm, bot_token: e.target.value })} />
              </label>
              <label>
                <span>Chat ID</span>
                <input className="name-input" placeholder="-1001234567890" value={telegramForm.chat_id} onChange={(e) => setTelegramForm({ ...telegramForm, chat_id: e.target.value })} />
              </label>
              <label className="toggle-row">
                <input type="checkbox" checked={telegramForm.enabled} onChange={(e) => setTelegramForm({ ...telegramForm, enabled: e.target.checked })} />
                <span>Отправлять важные события в Telegram</span>
              </label>
              <div className="monitoring-actions">
                <button className="orange-btn" type="submit" disabled={telegramBusy}><Check size={15} /> Сохранить</button>
                <button className="blue-btn" type="button" onClick={testTelegram} disabled={telegramBusy || !telegram.data?.configured}><Send size={15} /> Проверить</button>
              </div>
            </form>
            <div className="monitoring-status compact">
              <div><span>Token</span><b>{telegram.data?.configured ? `настроен ...${telegram.data?.token_suffix || ''}` : 'не настроен'}</b></div>
              <div><span>Chat</span><b>{telegram.data?.chat_id || '-'}</b></div>
              <div><span>Источник</span><b>{telegram.data?.db_token_present ? 'web UI' : telegram.data?.env_token_present ? '.env' : '-'}</b></div>
            </div>
            {telegramSaved && <div className="success">{telegramSaved}</div>}
            <p className="muted">Уведомления отправляются при создании, включении, отключении и удалении peer'ов, backup, истечении срока и превышении лимитов трафика.</p>
          </section>
        </div>
      )}
    </Shell>
  );
}

function UpdateCenterPage({ onLogout, user }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const data = await api('/api/update/status');
      setState({ loading: false, data, error: '' });
    } catch (err) {
      setState({ loading: false, data: null, error: err.message || 'Ошибка проверки обновлений' });
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const runUpdate = async () => {
    const confirmText = state.data?.runner?.confirm_text || 'UPDATE';
    const ok = await confirm({
      title: 'Запустить обновление',
      message: 'Запустить update.sh на сервере?',
      details: `Будет отправлено подтверждение ${confirmText}. Процесс пойдёт через update runner.`,
      tone: 'block',
      confirmLabel: 'Запустить',
    });
    if (!ok) return;
    setBusy(true);
    try {
      const data = await api('/api/update/run', { method: 'POST', body: JSON.stringify({ confirm: confirmText }) });
      setState({ loading: false, data, error: '' });
      toast.success('Обновление запущено');
    } catch (err) {
      toast.error(err.message || 'Не удалось запустить обновление');
      await load();
    } finally {
      setBusy(false);
    }
  };

  const data = state.data || {};
  const version = data.version || {};
  const runner = data.runner || {};
  const job = data.job || {};
  const links = data.links || {};
  const stateLabel = version.state === 'latest' ? 'последняя' : version.state === 'outdated' ? 'доступно обновление' : version.state === 'ahead' ? 'dev/ahead' : 'unknown';
  const runnerLabel = runner.can_run ? 'Готов к запуску' : 'Запуск выключен';
  const runnerReason = runner.reason === 'UI update runner disabled'
    ? 'Обновление из панели выключено'
    : runner.reason === 'ready'
      ? 'Runner готов'
      : runner.reason || '-';
  const jobLabel = job.running ? 'выполняется' : job.exit_code === null || job.exit_code === undefined ? 'ожидает запуска' : `код ${job.exit_code}`;

  return (
    <Shell title="Обновления" subtitle="Версия, история изменений и безопасный запуск обновления" onLogout={onLogout} user={user}>
      {state.error && <div className="warning">{state.error}</div>}
      {state.loading && <section className="card">Загрузка...</section>}
      {!state.loading && (
        <div className="update-grid">
          <section className="card update-hero-card">
            <div>
              <h2>Версия продукта</h2>
              <div className={`update-state ${version.state || 'unknown'}`}>{stateLabel}</div>
            </div>
            <div className="update-version-grid">
              <div><span>Установлена</span><b>{version.current || '-'}</b></div>
              <div><span>Latest tag</span><b>{version.latest || '-'}</b></div>
              <div><span>Проверено</span><b>{version.checked_at ? new Date(version.checked_at * 1000).toLocaleString('ru-RU') : '-'}</b></div>
            </div>
            <div className="update-actions">
              <button className="copy-button" type="button" onClick={load}><RefreshCw size={14} /> Обновить статус</button>
              {links.tags && <a className="update-link-btn" href={links.tags} target="_blank" rel="noreferrer"><ArrowUpRight size={14} /> Все версии</a>}
              {links.compare && <a className="update-link-btn" href={links.compare} target="_blank" rel="noreferrer"><ArrowUpRight size={14} /> Что изменилось</a>}
            </div>
          </section>

          <section className="card update-runner-card">
            <div className="section-head">
              <h2>Запуск обновления</h2>
              <span className={`runner-pill ${runner.can_run ? 'ready' : 'disabled'}`}>{runnerLabel}</span>
            </div>
            <div className="monitoring-status compact">
              <div><span>Скрипт</span><code>{runner.path || '-'}</code></div>
              <div><span>Состояние</span><b>{runnerReason}</b></div>
              <div><span>Файл</span><b>{runner.exists ? 'найден' : 'не найден'}</b></div>
              <div><span>Задача</span><b>{jobLabel}</b></div>
            </div>
            {!runner.can_run && <div className="warning">Обновление из панели пока выключено. Для безопасного запуска нужен отдельный host runner, потому что web-контейнер не должен сам менять исходники на сервере.</div>}
            <div className="update-actions">
              <button className="orange-btn" type="button" disabled={!runner.can_run || job.running || busy} onClick={runUpdate}><RefreshCw size={15} /> Запустить обновление</button>
            </div>
          </section>

          <section className="card update-log-card">
            <div className="section-head"><h2>Лог обновления</h2><button className="copy-button" type="button" onClick={load}><RefreshCw size={14} /></button></div>
            {job.log?.length ? <pre>{job.log.join('\n')}</pre> : <div className="empty-state"><Terminal size={28} /><span>Update ещё не запускался.</span></div>}
          </section>
        </div>
      )}
    </Shell>
  );
}

function percentStyle(value) {
  return { width: `${Math.max(0, Math.min(100, Number(value || 0)))}%` };
}

function formatUptime(seconds) {
  const n = Number(seconds || 0);
  const days = Math.floor(n / 86400);
  const hours = Math.floor((n % 86400) / 3600);
  const mins = Math.floor((n % 3600) / 60);
  if (days) return `${days}д ${hours}ч ${mins}м`;
  if (hours) return `${hours}ч ${mins}м`;
  return `${mins}м`;
}

function buildSmoothPath(coords) {
  if (!coords.length) return '';
  if (coords.length === 1) return `M ${coords[0].x.toFixed(1)} ${coords[0].y.toFixed(1)}`;
  return coords.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    const prev = coords[index - 1];
    const midX = (prev.x + point.x) / 2;
    return `${path} C ${midX.toFixed(1)} ${prev.y.toFixed(1)}, ${midX.toFixed(1)} ${point.y.toFixed(1)}, ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
  }, '');
}

function MiniLineChart({ points, keys = ['value'], colors = ['#c8ff00'], height = 86, maxValue }) {
  const data = points.length ? points : [{ value: 0 }];
  const max = maxValue || Math.max(1, ...data.flatMap((p) => keys.map((k) => Number(p[k] || 0))));
  const width = 520;
  const pad = { top: 12, right: 8, bottom: 18, left: 8 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const step = data.length > 1 ? plotWidth / (data.length - 1) : plotWidth;
  const coordsFor = (key) => data.map((p, i) => {
    const x = pad.left + i * step;
    const y = pad.top + plotHeight - (Number(p[key] || 0) / max) * plotHeight;
    return { x, y };
  });
  const pathFor = (key) => buildSmoothPath(coordsFor(key));
  const areaFor = (key) => {
    const coords = coordsFor(key);
    if (!coords.length) return '';
    const base = pad.top + plotHeight;
    return `${buildSmoothPath(coords)} L ${coords[coords.length - 1].x.toFixed(1)} ${base.toFixed(1)} L ${coords[0].x.toFixed(1)} ${base.toFixed(1)} Z`;
  };
  return (
    <svg className="mini-line-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      {[0, .25, .5, .75, 1].map((tick) => {
        const y = pad.top + plotHeight * tick;
        return <line className="mini-chart-grid" key={tick} x1={pad.left} y1={y} x2={width - pad.right} y2={y} />;
      })}
      <line className="mini-chart-axis" x1={pad.left} y1={pad.top + plotHeight} x2={width - pad.right} y2={pad.top + plotHeight} />
      {keys.map((key, idx) => (
        <path key={`${key}-area`} className="mini-chart-area" d={areaFor(key)} style={{ fill: colors[idx] || colors[0] }} />
      ))}
      {keys.map((key, idx) => {
        const coords = coordsFor(key);
        const last = coords[coords.length - 1] || { x: 0, y: height };
        return (
          <g key={key}>
            <path className="mini-chart-line" d={pathFor(key)} style={{ stroke: colors[idx] || colors[0] }} />
            <circle className="mini-chart-dot" cx={last.x} cy={last.y} r="3.2" style={{ fill: colors[idx] || colors[0] }} />
          </g>
        );
      })}
    </svg>
  );
}

function SystemStatusPage({ onLogout, user }) {
  const [state, setState] = useState({ loading: true, system: null, status: null, dashboard: null, error: '' });
  const [historyHours, setHistoryHours] = useState(24);
  const [history, setHistory] = useState([]);

  const load = async () => {
    try {
      const [system, status, dashboard, historyData] = await Promise.all([
        api('/api/node/system'),
        api('/api/node/status'),
        api('/api/dashboard'),
        api(`/api/node/system/history?hours=${historyHours}`),
      ]);
      setState({ loading: false, system, status, dashboard, error: '' });
      setHistory(historyData.points || []);
    } catch (err) {
      setState((s) => ({ ...s, loading: false, error: err.message || 'Ошибка system status' }));
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [historyHours]);

  const system = state.system || {};
  const memory = system.memory || {};
  const swap = system.swap || {};
  const disk = system.disk || {};
  const diskMounts = disk.mounts || [];
  const loadAvg = system.load_average || {};
  const network = system.network?.interfaces || [];
  const containers = system.containers || [];
  const alerts = system.alerts || [];
  const processes = system.processes || [];
  const protocols = state.status?.protocols || {};
  const traffic = state.dashboard?.traffic?.protocols || {};
  const stats = state.dashboard?.stats || {};
  const protocolRows = ['wireguard', 'amneziawg'].map((key) => ({
    key,
    title: protocols[key]?.title || (key === 'wireguard' ? 'WireGuard' : 'AmneziaWG'),
    available: Boolean(protocols[key]?.available),
    container: protocols[key]?.container || '-',
    interface: protocols[key]?.interface || '-',
    endpoint: protocols[key]?.endpoint || '-',
    peers: state.dashboard?.stats?.peers_total || 0,
    rx: traffic[key]?.rx || 0,
    tx: traffic[key]?.tx || 0,
  }));
  const netTotal = network.reduce((acc, item) => ({ rx: acc.rx + Number(item.rx || 0), tx: acc.tx + Number(item.tx || 0) }), { rx: 0, tx: 0 });
  const lastHistory = history[history.length - 1] || {};
  const peakCpu = history.reduce((max, item) => Math.max(max, Number(item.cpu || 0)), 0);
  const peakRx = history.reduce((max, item) => Math.max(max, Number(item.rx_rate || 0)), 0);
  const peakTx = history.reduce((max, item) => Math.max(max, Number(item.tx_rate || 0)), 0);

  return (
    <Shell title="System Status" subtitle="Состояние панели, контейнеров и сетевых интерфейсов" onLogout={onLogout} user={user}>
      {state.error && <div className="warning">{state.error}</div>}
      <div className="section-head">
        <h2>Обзор сервера</h2>
        <button className="copy-button" type="button" onClick={load}><RefreshCw size={14} /> Обновить</button>
      </div>
      {state.loading ? <section className="card">Загрузка...</section> : (
        <>
          <div className="tools-kpi-grid">
            <section className="card tool-kpi">
              <span>CPU</span>
              <b>{system.cpu_percent ?? 0}%</b>
              <small>{system.cpu?.cores || 1} cores · current {system.cpu?.current_percent ?? system.cpu_percent ?? 0}% · load {loadAvg.one ?? 0}</small>
              <div className="tool-progress"><i style={percentStyle(system.cpu_percent)} /></div>
            </section>
            <section className="card tool-kpi">
              <span>Memory</span>
              <b>{memory.percent ?? 0}%</b>
              <small>{formatBytes(memory.used)} / {formatBytes(memory.total)}</small>
              <div className="tool-progress"><i style={percentStyle(memory.percent)} /></div>
            </section>
            <section className="card tool-kpi">
              <span>Storage</span>
              <b>{disk.percent ?? 0}%</b>
              <small>{formatBytes(disk.used)} / {formatBytes(disk.total)}</small>
              <div className="tool-progress"><i style={percentStyle(disk.percent)} /></div>
            </section>
            <section className="card tool-kpi">
              <span>Uptime</span>
              <b>{formatUptime(system.uptime_seconds)}</b>
              <small>{system.hostname || '3wg-panel'}</small>
              <div className="tool-progress"><i style={percentStyle(protocolRows.filter((p) => p.available).length / protocolRows.length * 100)} /></div>
            </section>
          </div>

          <section className="system-alerts">
            {alerts.map((item, idx) => (
              <div className={`system-alert ${item.level || 'warn'}`} key={`${item.title}-${idx}`}>
                <span>{(item.level || 'warn').toUpperCase()}</span>
                <div>
                  <b>{item.title}</b>
                  <small>{item.message}</small>
                </div>
              </div>
            ))}
          </section>

          <div className="system-dashboard-grid">
            <section className="card system-chart-card">
              <div className="section-head">
                <h2>Ресурсы</h2>
                <select className="category-select system-range-select" value={historyHours} onChange={(e) => setHistoryHours(Number(e.target.value))}>
                  <option value="1">1 час</option>
                  <option value="24">24 часа</option>
                  <option value="168">7 дней</option>
                </select>
              </div>
              <MiniLineChart points={history} keys={['cpu', 'memory', 'disk']} colors={['#c8ff00', '#ff8c00', '#6aa7ff']} maxValue={100} height={118} />
              <div className="traffic-color-legend">
                <span><i className="rx" /> CPU</span>
                <span><i className="tx" /> Memory</span>
                <span><i style={{ background: '#6aa7ff' }} /> Storage</span>
              </div>
              <div className="system-history-meta">
                <span>точек: <b>{history.length}</b></span>
                <span>CPU peak: <b>{peakCpu.toFixed(1)}%</b></span>
              </div>
            </section>
            <section className="card system-chart-card">
              <div className="section-head">
                <h2>Сеть</h2>
                <span className="muted">RX {formatBytes(lastHistory.rx_rate)}/s · TX {formatBytes(lastHistory.tx_rate)}/s</span>
              </div>
              <MiniLineChart points={history} keys={['rx_rate', 'tx_rate']} colors={['#c8ff00', '#ff8c00']} height={118} />
              <div className="system-net-total">
                <span>RX total <b>{formatBytes(netTotal.rx)}</b></span>
                <span>TX total <b>{formatBytes(netTotal.tx)}</b></span>
              </div>
              <div className="system-history-meta">
                <span>RX peak: <b>{formatBytes(peakRx)}/s</b></span>
                <span>TX peak: <b>{formatBytes(peakTx)}/s</b></span>
              </div>
            </section>
          </div>

          <div className="system-detail-grid">
            <section className="card system-panel">
              <h2>Load / Memory</h2>
              <div className="system-facts">
                <div><span>Load 1m</span><b>{loadAvg.one ?? 0}</b></div>
                <div><span>Load 5m</span><b>{loadAvg.five ?? 0}</b></div>
                <div><span>Load 15m</span><b>{loadAvg.fifteen ?? 0}</b></div>
                <div><span>Swap</span><b>{swap.total ? `${swap.percent}%` : 'none'}</b><small>{formatBytes(swap.used)} / {formatBytes(swap.total)}</small></div>
              </div>
            </section>
            <section className="card system-panel">
              <h2>Docker containers</h2>
              <div className="container-list">
                {containers.map((item) => (
                  <div key={item.name}>
                    <span className={item.running ? 'status-orb live' : 'status-orb idle'} />
                    <b>{item.name}</b>
                    <small>{item.status}</small>
                    <em>CPU {item.cpu_percent}% · RAM {formatBytes(item.memory?.usage)} · restarts {item.restart_count || 0}</em>
                    <small className="container-image">{item.image || '-'}</small>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className="card tools-status-card">
            <div className="section-head"><h2>VPN сервисы</h2><span className="live-dot">LIVE</span></div>
            <div className="tool-service-grid">
              {protocolRows.map((row) => (
                <div className="tool-service" key={row.key}>
                  <div className="tool-service-head">
                    <b className={row.key === 'wireguard' ? 'traffic-proto wg' : 'traffic-proto awg'}>{row.title}</b>
                    <span className={row.available ? 'status-pill online' : 'status-pill offline'}>{row.available ? 'ONLINE' : 'OFFLINE'}</span>
                  </div>
                  <div className="tool-service-meta">
                    <span>{row.interface}</span>
                    <span>{row.container}</span>
                    <span>{row.endpoint}</span>
                  </div>
                  <div className="traffic-meta">
                    <span>RX {formatBytes(row.rx)}</span>
                    <span>TX {formatBytes(row.tx)}</span>
                    <span>Peers {stats.peers_total || 0}</span>
                  </div>
                  <div className="tool-progress split"><i style={percentStyle((row.rx / Math.max(1, row.rx + row.tx)) * 100)} /><em style={percentStyle((row.tx / Math.max(1, row.rx + row.tx)) * 100)} /></div>
                </div>
              ))}
            </div>
          </section>

          <section className="card system-panel">
            <div className="section-head"><h2>Network interfaces</h2><span className="muted">{network.length} interfaces</span></div>
            <div className="interface-grid">
              {network.map((item) => (
                <div key={item.name}>
                  <b>{item.name}</b>
                  <span>RX {formatBytes(item.rx)} · {item.rx_packets} pkt</span>
                  <span>TX {formatBytes(item.tx)} · {item.tx_packets} pkt</span>
                </div>
              ))}
            </div>
          </section>

          <div className="system-detail-grid">
            <section className="card system-panel">
              <div className="section-head"><h2>Disk mounts</h2><span className="muted">{diskMounts.length} mounts</span></div>
              <div className="system-table-list">
                {diskMounts.map((item) => (
                  <div key={`${item.device}-${item.mountpoint}`}>
                    <div>
                      <b>{item.mountpoint}</b>
                      <small>{item.device} · {item.fstype}</small>
                    </div>
                    <span>{formatBytes(item.used)} / {formatBytes(item.total)}</span>
                    <em>{item.percent}%</em>
                    <div className="tool-progress"><i style={percentStyle(item.percent)} /></div>
                  </div>
                ))}
              </div>
            </section>
            <section className="card system-panel">
              <div className="section-head"><h2>Top processes</h2><span className="muted">by RSS memory</span></div>
              <div className="process-list">
                {processes.map((item) => (
                  <div key={item.pid}>
                    <span>{item.pid}</span>
                    <b>{item.name}</b>
                    <em>{formatBytes(item.rss)}</em>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      )}
    </Shell>
  );
}

function parsePingSummary(output = '') {
  const packetMatch = output.match(/(\d+)\s+packets transmitted,\s+(\d+)\s+(?:packets\s+)?received,\s+([\d.]+)%\s+packet loss(?:,\s+time\s+(\d+)ms)?/i);
  const rttMatch = output.match(/(?:rtt|round-trip).*?=\s*([\d.]+)\/([\d.]+)\/([\d.]+)\/([\d.]+)\s*ms/i);
  const replies = output
    .split('\n')
    .map((line) => {
      const from = line.match(/from\s+([^\s:]+)/i)?.[1] || '';
      const seq = line.match(/icmp_seq=(\d+)/i)?.[1] || '';
      const ttl = line.match(/ttl=(\d+)/i)?.[1] || '';
      const timeMs = line.match(/time=([\d.]+)\s*ms/i)?.[1] || '';
      return timeMs ? { from, seq, ttl, timeMs } : null;
    })
    .filter(Boolean);
  return {
    sent: packetMatch ? Number(packetMatch[1]) : null,
    received: packetMatch ? Number(packetMatch[2]) : null,
    loss: packetMatch ? Number(packetMatch[3]) : null,
    totalTime: packetMatch?.[4] ? Number(packetMatch[4]) : null,
    min: rttMatch ? Number(rttMatch[1]) : null,
    avg: rttMatch ? Number(rttMatch[2]) : null,
    max: rttMatch ? Number(rttMatch[3]) : null,
    mdev: rttMatch ? Number(rttMatch[4]) : null,
    replies,
  };
}

function parseTraceSummary(output = '') {
  const hops = output
    .split('\n')
    .map((line) => {
      const match = line.match(/^\s*(\d+)\s+(.+)$/);
      if (!match) return null;
      const parts = match[2].trim().split(/\s+/);
      const host = parts[0] || '*';
      const timeMs = parts.find((part) => /^[\d.]+$/.test(part));
      return { index: Number(match[1]), host, timeMs: timeMs || '' };
    })
    .filter(Boolean);
  const answered = hops.filter((hop) => hop.host && hop.host !== '*' && hop.timeMs);
  const timedOut = hops.length > 0 && answered.length === 0;
  return { hops, answered, timedOut, lastHop: answered[answered.length - 1] || hops[hops.length - 1] || null };
}

function healthStatusLabel(status) {
  if (status === 'ok') return 'OK';
  if (status === 'fail') return 'FAIL';
  return 'WARN';
}

function HealthDiagnosticsPage({ onLogout, user }) {
  const [state, setState] = useState({ loading: true, data: null, error: '' });
  const [expanded, setExpanded] = useState(null);

  const load = async () => {
    try {
      const data = await api('/api/node/diagnostics');
      setState({ loading: false, data, error: '' });
    } catch (err) {
      setState({ loading: false, data: null, error: err.message || 'Ошибка diagnostics' });
    }
  };

  useEffect(() => { load(); }, []);

  const data = state.data || {};
  const checks = data.checks || [];
  const groups = checks.reduce((acc, item) => {
    const key = item.group || 'General';
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});
  const summary = data.summary || { ok: 0, warn: 0, fail: 0 };
  const renderCheck = (group, item, idx) => {
    const key = `${group}-${idx}-${item.name}`;
    const details = item.details || null;
    const hasDetails = details && (Array.isArray(details) ? details.length > 0 : Object.keys(details).length > 0);
    return (
      <div className={`health-check ${item.status}`} key={key}>
        <div className="health-check-main">
          <span className={`health-pill ${item.status}`}>{healthStatusLabel(item.status)}</span>
          <div>
            <b>{item.name}</b>
            <small>{item.message}</small>
          </div>
          {hasDetails ? <button className="copy-button" type="button" onClick={() => setExpanded(expanded === key ? null : key)}>
            {expanded === key ? 'Скрыть' : 'Детали'}
          </button> : <span className="health-no-details">—</span>}
        </div>
        {hasDetails && expanded === key && <pre>{JSON.stringify(details, null, 2)}</pre>}
      </div>
    );
  };
  const renderGroupPanel = (group, items) => (
    <div className="health-group-panel" key={group}>
      <div className="health-group-title">
        <h3>{group}</h3>
        <span className="muted">{items.length} checks</span>
      </div>
      <div className="health-check-list">
        {items.map((item, idx) => renderCheck(group, item, idx))}
      </div>
    </div>
  );
  const generalGroups = ['Panel', 'Docker', 'Storage', 'Network', 'Reverse proxy'].filter((group) => groups[group]);
  const protocolGroups = ['WireGuard', 'AmneziaWG'].filter((group) => groups[group]);
  const otherGroups = Object.keys(groups).filter((group) => !generalGroups.includes(group) && !protocolGroups.includes(group)).sort();

  return (
    <Shell title="Health diagnostics" subtitle="Проверки панели, Docker, протоколов и endpoint'ов" onLogout={onLogout} user={user}>
      {state.error && <div className="warning">{state.error}</div>}
      <div className="section-head">
        <h2>Диагностика</h2>
        <button className="copy-button" type="button" onClick={load}><RefreshCw size={14} /> Обновить</button>
      </div>
      {state.loading ? <section className="card">Загрузка...</section> : (
        <>
          <div className="health-summary-grid">
            <section className="card health-summary ok"><span>OK</span><b>{summary.ok || 0}</b></section>
            <section className="card health-summary warn"><span>WARN</span><b>{summary.warn || 0}</b></section>
            <section className="card health-summary fail"><span>FAIL</span><b>{summary.fail || 0}</b></section>
          </div>
          {generalGroups.length > 0 && (
            <section className="card health-section-card">
              <div className="section-head">
                <h2>Основные проверки</h2>
                <span className="muted">{generalGroups.reduce((sum, group) => sum + groups[group].length, 0)} checks</span>
              </div>
              <div className="health-section-grid core">
                {generalGroups.map((group) => renderGroupPanel(group, groups[group]))}
              </div>
            </section>
          )}
          {protocolGroups.length > 0 && (
            <section className="card health-section-card">
              <div className="section-head">
                <h2>VPN протоколы</h2>
                <span className="muted">{protocolGroups.reduce((sum, group) => sum + groups[group].length, 0)} checks</span>
              </div>
              <div className="health-section-grid protocols">
                {protocolGroups.map((group) => renderGroupPanel(group, groups[group]))}
              </div>
            </section>
          )}
          {otherGroups.length > 0 && (
            <section className="card health-section-card">
              <div className="section-head">
                <h2>Дополнительно</h2>
                <span className="muted">{otherGroups.reduce((sum, group) => sum + groups[group].length, 0)} checks</span>
              </div>
              <div className="health-section-grid core">
                {otherGroups.map((group) => renderGroupPanel(group, groups[group]))}
              </div>
            </section>
          )}
        </>
      )}
    </Shell>
  );
}

function NetworkToolResult({ kind, result, peer }) {
  const isTrace = kind === 'traceroute';
  const ping = !isTrace ? parsePingSummary(result.output || '') : null;
  const trace = isTrace ? parseTraceSummary(result.output || '') : null;
  const healthy = isTrace ? Boolean(result.ok && trace.answered.length > 0) : result.ok;
  const traceTimedOut = isTrace && trace.timedOut;
  const vpnActive = Boolean(peer && (peer.status === 'active' || peer.status === 'online' || peer.live?.latest_handshake));
  const statusTitle = healthy
    ? (isTrace ? 'Маршрут построен' : 'Host отвечает')
    : traceTimedOut
      ? 'Маршрут не виден'
    : vpnActive
      ? 'VPN активен, ICMP не отвечает'
      : (isTrace ? 'Маршрут не завершён' : 'Ответов нет');
  const statusLabel = healthy
    ? 'Проверка успешна'
    : traceTimedOut
      ? 'Нет ответов от hops'
      : vpnActive
        ? 'VPN peer online'
        : 'Есть проблема';
  const heroClass = healthy ? 'ok' : (traceTimedOut || vpnActive) ? 'warn' : 'bad';

  return (
    <>
      <div className={`tool-result-hero ${heroClass}`}>
        <div>
          <span>{statusLabel}</span>
          <b>{statusTitle}</b>
          {traceTimedOut && <small>Команда выполнилась, но все переходы вернули `*`. Обычно ICMP/UDP traceroute фильтруется контейнером, peer'ом или сетью.</small>}
        </div>
        <strong>{result.duration_ms} ms</strong>
      </div>

      {isTrace ? (
        <div className="tool-summary-grid">
          <div><span>Hops</span><b>{trace.hops.length}</b></div>
          <div><span>Answered</span><b className={trace.answered.length ? 'active-text' : 'danger-text'}>{trace.answered.length}</b></div>
          <div><span>Last hop</span><b title={trace.lastHop?.host || '-'}>{trace.lastHop?.host || '-'}</b></div>
          <div><span>Return code</span><b>{result.return_code}</b></div>
        </div>
      ) : (
        <div className="tool-summary-grid">
          <div><span>Sent</span><b>{ping.sent ?? '-'}</b></div>
          <div><span>Received</span><b>{ping.received ?? '-'}</b></div>
          <div><span>Loss</span><b className={ping.loss ? 'danger-text' : 'active-text'}>{ping.loss ?? '-'}%</b></div>
          <div><span>Avg</span><b>{ping.avg != null ? `${ping.avg} ms` : '-'}</b></div>
        </div>
      )}

      {!isTrace && ping.replies.length > 0 && (
        <div className="tool-replies">
          {ping.replies.map((reply) => (
            <div key={`${reply.seq}-${reply.timeMs}`}>
              <span>seq {reply.seq}</span>
              <b>{reply.timeMs} ms</b>
              <small>{reply.from}{reply.ttl ? ` · ttl ${reply.ttl}` : ''}</small>
            </div>
          ))}
        </div>
      )}

      {isTrace && trace.hops.length > 0 && (
        <div className="tool-hops">
          {trace.hops.map((hop) => (
            <div key={`${hop.index}-${hop.host}`}>
              <span>{hop.index}</span>
              <b title={hop.host}>{hop.host}</b>
              <small>{hop.timeMs ? `${hop.timeMs} ms` : '*'}</small>
            </div>
          ))}
        </div>
      )}

      <details className="tool-raw-details">
        <summary>Raw output</summary>
        <pre className="tool-output">{result.output || 'Нет вывода'}</pre>
      </details>
    </>
  );
}

function getNetworkToolBadge(kind, result, peer) {
  if (!result) return null;
  if (kind === 'traceroute') {
    const trace = parseTraceSummary(result.output || '');
    if (result.ok && trace.timedOut) return { className: 'status-pill warn', label: 'WARN' };
  }
  const vpnActive = Boolean(peer && (peer.status === 'active' || peer.status === 'online' || peer.live?.latest_handshake));
  if (kind === 'ping' && !result.ok && vpnActive) {
    return { className: 'status-pill warn', label: 'WARN' };
  }
  return result.ok
    ? { className: 'status-pill online', label: 'OK' }
    : { className: 'status-pill offline', label: `CODE ${result.return_code}` };
}

function NetworkToolPage({ kind, onLogout, user }) {
  const isTrace = kind === 'traceroute';
  const [peers, setPeers] = useState([]);
  const [selectedPeer, setSelectedPeer] = useState('');
  const [target, setTarget] = useState('');
  const [count, setCount] = useState(4);
  const [maxHops, setMaxHops] = useState(20);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/api/peers')
      .then((data) => setPeers(data.peers || []))
      .catch(() => setPeers([]));
  }, []);

  const selectPeer = (value) => {
    setSelectedPeer(value);
    const peer = peers.find((item) => String(item.id) === String(value));
    setTarget((peer?.ip_cidr || '').replace('/32', ''));
    setResult(null);
    setError('');
  };

  const changeTarget = (value) => {
    setTarget(value);
    setSelectedPeer('');
    setResult(null);
    setError('');
  };

  const run = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const selected = peers.find((item) => String(item.id) === String(selectedPeer));
      const payload = isTrace
        ? { target, max_hops: maxHops, protocol: selected?.protocol || '' }
        : { target, count, protocol: selected?.protocol || '' };
      const data = await api(`/api/tools/${kind}`, { method: 'POST', body: JSON.stringify(payload) });
      setResult(data);
    } catch (err) {
      setError(err.message || 'Ошибка запуска');
    } finally {
      setBusy(false);
    }
  };

  const title = isTrace ? 'Traceroute' : 'Ping';
  const subtitle = isTrace ? 'Проверка маршрута от панели до IP или hostname' : 'Проверка доступности IP или hostname от панели';
  const selectedPeerData = peers.find((item) => String(item.id) === String(selectedPeer));
  const resultBadge = getNetworkToolBadge(kind, result, selectedPeerData);

  return (
    <Shell title={title} subtitle={subtitle} onLogout={onLogout} user={user}>
      {error && <div className="warning">{error}</div>}
      <div className="network-tool-grid">
        <section className="card network-tool-card">
          <h2>{title}</h2>
          <form onSubmit={run}>
            <label>
              <span>Peer из панели</span>
              <select className="category-select" value={selectedPeer} onChange={(e) => selectPeer(e.target.value)}>
                <option value="">Выбрать клиента</option>
                {peers.map((peer) => (
                  <option key={peer.id} value={String(peer.id)}>{peer.name} · {peer.protocol_title || peer.protocol} · {peer.ip_cidr}</option>
                ))}
              </select>
            </label>
            <label>
              <span>IP-адрес / hostname</span>
              <input className="name-input" value={target} onChange={(e) => changeTarget(e.target.value)} placeholder="1.1.1.1 или example.com" />
            </label>
            {isTrace ? (
              <label>
                <span>Max hops</span>
                <input className="inline-number" type="number" min="3" max="30" value={maxHops} onChange={(e) => setMaxHops(e.target.value)} />
              </label>
            ) : (
              <label>
                <span>Число пакетов</span>
                <input className="inline-number" type="number" min="1" max="10" value={count} onChange={(e) => setCount(e.target.value)} />
              </label>
            )}
            <button className="orange-btn" type="submit" disabled={busy || !target.trim()}>
              <Activity size={15} /> {busy ? 'Выполняю...' : isTrace ? 'Trace' : 'Ping'}
            </button>
          </form>
        </section>

        <section className="card network-result-card">
          <div className="section-head">
            <h2>Результат</h2>
            {resultBadge && <span className={resultBadge.className}>{resultBadge.label}</span>}
          </div>
          {result ? (
            <>
              <div className="monitoring-status">
                <div><span>Команда</span><code>{result.command}</code></div>
                <div><span>Время</span><b>{result.duration_ms} ms</b></div>
                <div><span>Источник</span><b>{result.source?.label || '3wg-panel'}</b></div>
                {selectedPeerData && <div><span>VPN статус</span><b className={selectedPeerData.status === 'active' ? 'active-text' : 'muted'}>{selectedPeerData.status === 'active' ? 'ONLINE' : selectedPeerData.status}</b></div>}
              </div>
              <NetworkToolResult kind={kind} result={result} peer={selectedPeerData} />
            </>
          ) : (
            <div className="tool-placeholder">
              <Terminal size={34} />
              <span>Выберите target и запустите проверку.</span>
            </div>
          )}
        </section>
      </div>
    </Shell>
  );
}


function App() {
  const [auth, setAuth] = useState({ loading: true, ok: false, user: null });
  const check = async () => {
    try { const data = await api('/api/auth/me'); setAuth({ loading: false, ok: true, user: data.user }); }
    catch { setAuth({ loading: false, ok: false, user: null }); }
  };
  useEffect(() => { check(); }, []);
  const logout = async () => { try { await api('/api/auth/logout', { method: 'POST' }); } finally { setAuth({ loading: false, ok: false, user: null }); } };
  if (auth.loading) return <div className="boot">3WG</div>;
  if (!auth.ok) return <Login onLogin={check} />;
  const isAdmin = Boolean(auth.user?.is_admin);
  const clientMatch = window.location.pathname.match(/^\/client\/(\d+)$/);
  const statusMatch = window.location.pathname.match(/^\/status\/(wireguard|amneziawg)$/);
  const trafficMatch = window.location.pathname.match(/^\/traffic\/(wireguard|amneziawg)$/);
  if (clientMatch) return <ClientPage clientId={clientMatch[1]} onLogout={logout} user={auth.user} />;
  if (isAdmin && statusMatch) return <StatusPage protocol={statusMatch[1]} onLogout={logout} user={auth.user} />;
  if (isAdmin && trafficMatch) return <TrafficPage protocol={trafficMatch[1]} onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/apikeys') return <ApiKeysPage onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/users') return <UsersPage onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/monitoring') return <MonitoringPage onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/updates') return <UpdateCenterPage onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/audit') return <AuditPage onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/backups') return <BackupsPage onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/tools/system') return <SystemStatusPage onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/tools/health') return <HealthDiagnosticsPage onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/tools/ping') return <NetworkToolPage kind="ping" onLogout={logout} user={auth.user} />;
  if (isAdmin && window.location.pathname === '/tools/traceroute') return <NetworkToolPage kind="traceroute" onLogout={logout} user={auth.user} />;
  return <Dashboard onLogout={logout} user={auth.user} />;
}

createRoot(document.getElementById('root')).render(
  <ToastProvider>
    <ConfirmProvider>
      <App />
    </ConfirmProvider>
  </ToastProvider>
);
