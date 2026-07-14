import React, { useEffect, useMemo, useState } from 'react';
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
  Network,
  Power,
  Pencil,
  Plus,
  QrCode,
  RefreshCw,
  Trash2,
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

function Sidebar({ onLogout, protocols: initialProtocols = null, user }) {
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
    <aside className="sidebar">
      <div className="brand-block">
        <img src="/logogrin.png" alt="3WG" />
      </div>
      <div className="nav-title">ОБЗОР</div>
      <a className={`nav ${isHome ? 'active' : ''}`} href="/"><Home size={14} /> <span>Главная</span></a>
      {isAdmin && showWireGuardStatus && <a className={`nav ${path === '/status/wireguard' ? 'active' : ''}`} href="/status/wireguard"><Activity size={14} /> <span>WG status</span></a>}
      {isAdmin && showAmneziaStatus && <a className={`nav ${path === '/status/amneziawg' ? 'active' : ''}`} href="/status/amneziawg"><Activity size={14} /> <span>AWG status</span></a>}
      {isAdmin && <div className="nav-title">УПРАВЛЕНИЕ</div>}
      {isAdmin && <a className={`nav ${path === '/users' ? 'active' : ''}`} href="/users"><Users size={14} /> <span>Пользователи</span></a>}
      {isAdmin && <a className={`nav ${path === '/apikeys' ? 'active' : ''}`} href="/apikeys"><Key size={14} /> <span>API-ключи</span></a>}
      <button className="nav logout" onClick={onLogout}><LogOut size={14} /> <span>Выход</span></button>
    </aside>
  );
}

function Shell({ title, subtitle, onLogout, protocols, user, children }) {
  return (
    <div className="layout" id="top">
      <Sidebar onLogout={onLogout} protocols={protocols} user={user} />
      <main className="main">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          <div className="top-actions"><button onClick={onLogout} title="Выйти"><LogOut size={15} /></button></div>
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
      await api('/api/peers', { method: 'POST', body: JSON.stringify({ name, protocols: selected, category_id: categoryId || null }) });
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
        {isAdmin && (
          <select className="category-select create-category-select" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Без категории</option>
            {(categories || []).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
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
      window.alert(err.message || 'Ошибка создания категории');
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
      window.alert(err.message || 'Ошибка изменения категории');
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
      window.alert(err.message || 'Ошибка удаления категории');
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
      window.alert(err.message || 'Ошибка изменения категории');
    } finally {
      setBusyId(null);
    }
  };

  const mutatePeer = async (peer, action) => {
    setBusyId(peer.id);
    try {
      if (action === 'delete') {
        await api(peer.links?.delete || `/api/peers/${peer.id}`, { method: 'DELETE' });
      } else {
        await api(peer.links?.[action] || `/api/peers/${peer.id}/${action}`, { method: 'POST' });
      }
      await onRefresh();
    } catch (err) {
      window.alert(err.message || 'Ошибка операции');
    } finally {
      setBusyId(null);
    }
  };

  const askPeerAction = (peer, action) => setPendingAction({ peer, action });

  const confirmMeta = pendingAction ? getPeerConfirmMeta(pendingAction.peer, pendingAction.action) : null;

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
            <col style={{ width: 46 }} />
            <col style={{ width: 170 }} />
            {isAdmin && <col style={{ width: 130 }} />}
            {isAdmin && <col style={{ width: 145 }} />}
            <col style={{ width: 125 }} />
            <col style={{ width: 130 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 180 }} />
            <col style={{ width: 170 }} />
            <col style={{ width: 105 }} />
            <col style={{ width: 105 }} />
            <col style={{ width: 154 }} />
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
              <th>Endpoint клиента</th>
              <th>Последнее подключение</th>
              <th>RX</th>
              <th>TX</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredPeers.map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td><b>{p.name}</b><small>создал: {p.created_by_label || p.owner_username || 'admin'}</small></td>
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
                <td title={p.live?.endpoint || ''}>{p.live?.endpoint || '(none)'}</td>
                <td>{p.live?.latest_handshake && p.live.latest_handshake !== '0' ? new Date(Number(p.live.latest_handshake) * 1000).toLocaleString('ru-RU') : '-'}</td>
                <td>{formatBytes(p.live?.rx)}</td>
                <td>{formatBytes(p.live?.tx)}</td>
                <td className="actions-cell">
                  <div className="actions">
                    <IconButton href={p.links?.html || '#'} title="Открыть клиента" tone="open"><ArrowUpRight size={14} /></IconButton>
                    <IconButton href={p.links?.download || '#'} title="Скачать config" tone="download"><Download size={14} /></IconButton>
                    <IconButton onClick={() => setQrPeer(p)} title="Показать QR" tone="qr"><QrCode size={14} /></IconButton>
                    {p.enabled ? (
                      <IconButton onClick={() => askPeerAction(p, 'disable')} title="Отключить peer" tone="block" disabled={busyId === p.id}><Power size={14} /></IconButton>
                    ) : (
                      <IconButton onClick={() => askPeerAction(p, 'enable')} title="Включить peer" tone="enable" disabled={busyId === p.id}><Power size={14} /></IconButton>
                    )}
                    <IconButton onClick={() => askPeerAction(p, 'delete')} title="Удалить peer" tone="danger" disabled={busyId === p.id}><Trash2 size={14} /></IconButton>
                  </div>
                </td>
              </tr>
            ))}
            {filteredPeers.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 12 : 10} className="empty-table">В этой категории пока нет peer'ов</td>
              </tr>
            )}
          </tbody>
        </table>
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

function PeerStatus({ peer }) {
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


function ClientPage({ clientId, onLogout, user }) {
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
    <Shell title={title} subtitle="WireGuard / AmneziaWG node management" onLogout={onLogout} user={user}>
      {state.error && <div className="warning">{state.error}</div>}
      {state.loading && <section className="card detail-card">Загрузка...</section>}
      {peer && (
        <>
          <section className="card detail-card">
            <div className="detail-head">
              <a className="back-link" href="/"><ChevronLeft size={16} /> Назад</a>
              <span className={peer.status === 'active' ? 'active-text' : 'muted'}>{peer.status === 'active' ? 'ONLINE' : 'OFFLINE'}</span>
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
    </Shell>
  );
}

function UsersPage({ onLogout, user }) {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ username: '', password: '', peer_limit: 1, role: 'user' });
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
      const data = await api('/api/users', { method: 'POST', body: JSON.stringify(form) });
      setUsers(data.users || []);
      setForm({ username: '', password: '', peer_limit: 1, role: 'user' });
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
    } catch (err) {
      window.alert(err.message || 'Ошибка изменения пользователя');
    } finally {
      setBusy(false);
    }
  };

  const deleteUser = async (item) => {
    if (!window.confirm(`Удалить пользователя "${item.username}"? Его peer'ы перейдут администратору.`)) return;
    setBusy(item.id);
    try {
      const data = await api(`/api/users/${item.id}`, { method: 'DELETE' });
      setUsers(data.users || []);
    } catch (err) {
      window.alert(err.message || 'Ошибка удаления пользователя');
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
            <input className="name-input" placeholder="Логин" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            <input className="name-input" placeholder="Пароль" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <input className="name-input" min="0" type="number" value={form.peer_limit} onChange={(e) => setForm({ ...form, peer_limit: Number(e.target.value) })} />
            <select className="category-select" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="user">Пользователь</option>
              <option value="admin">Администратор</option>
            </select>
            <button className="orange-btn" disabled={busy || !form.username.trim() || !form.password.trim()}><Plus size={15} /> Создать</button>
          </form>
          {error && <div className="warning">{error}</div>}
        </section>
        <section className="card users-list-card">
          <div className="section-head"><h2>Аккаунты</h2><button className="copy-button" type="button" onClick={load}><RefreshCw size={14} /> Обновить</button></div>
          <div className="table-wrap">
            <table className="clients-table users-table">
              <thead><tr><th>ID</th><th>Логин</th><th>Роль</th><th>Peer'ы</th><th>Лимит</th><th>Статус</th><th>Действия</th></tr></thead>
              <tbody>
                {users.map((item) => (
                  <UserRow key={item.id} item={item} busy={busy === item.id} onPatch={patchUser} onDelete={deleteUser} />
                ))}
                {users.length === 0 && <tr><td className="empty-table" colSpan={7}>Дополнительных пользователей пока нет</td></tr>}
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
  const [password, setPassword] = useState('');
  useEffect(() => { setLimit(item.peer_limit); }, [item.peer_limit]);
  return (
    <tr>
      <td>{item.id}</td>
      <td><b>{item.username}</b></td>
      <td>{item.role === 'admin' ? 'Администратор' : 'Пользователь'}</td>
      <td>{item.peers_used}</td>
      <td><input className="inline-number" type="number" min="0" value={limit} onChange={(e) => setLimit(Number(e.target.value))} /></td>
      <td><span className={item.enabled ? 'status-ok' : 'status-bad'}>{item.enabled ? 'ON' : 'OFF'}</span></td>
      <td className="actions-cell">
        <div className="user-actions">
          <button className="icon-button download" title="Сохранить лимит" disabled={busy} onClick={() => onPatch(item.id, { peer_limit: limit })}><Check size={14} /></button>
          <button className="icon-button block" title={item.enabled ? 'Отключить' : 'Включить'} disabled={busy} onClick={() => onPatch(item.id, { enabled: !item.enabled })}><Power size={14} /></button>
          <input className="inline-password" placeholder="новый пароль" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button className="icon-button qr" title="Сменить пароль" disabled={busy || password.length < 6} onClick={async () => { await onPatch(item.id, { password }); setPassword(''); }}><Key size={14} /></button>
          <button className="icon-button danger" title="Удалить" disabled={busy} onClick={() => onDelete(item)}><Trash2 size={14} /></button>
        </div>
      </td>
    </tr>
  );
}

function ApiKeysPage({ onLogout, user }) {
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
    if (!window.confirm('Удалить ключ? Интеграции, использующие его, перестанут работать.')) return;
    try { await api(`/api/apikeys/${id}`, { method: 'DELETE' }); await load(); }
    catch (e) { setError(String(e.message || e)); }
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
  return <Dashboard onLogout={logout} user={auth.user} />;
}

createRoot(document.getElementById('root')).render(<App />);
