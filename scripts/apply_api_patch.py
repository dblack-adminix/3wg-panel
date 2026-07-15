#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / 'app/app.py'
START = '# === 3WG REACT API START ==='
END = '# === 3WG REACT API END ==='
FRONTEND_END = '# === 3WG REACT FRONTEND END ==='

API_BLOCK = r'''
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
    return {
        'id': int(row['id']),
        'username': row['username'],
        'role': row['role'],
        'peer_limit': int(row['peer_limit']),
        'peers_used': int(count),
        'enabled': bool(row['enabled']),
        'created_at': int(row['created_at']),
    }


def api_panel_users_payload() -> list[dict]:
    with db() as conn:
        rows = conn.execute('SELECT * FROM panel_users ORDER BY id DESC').fetchall()
    return [api_panel_user_payload(row) for row in rows]


def api_peer_payload(c, live: dict | None = None, include_config: bool = False) -> dict:
    protocol = c['protocol']
    p = PROTOCOLS[protocol]
    endpoint = client_endpoint(protocol)
    lp = live.get(protocol, {}).get(c['public_key']) if live else None
    active, handshake_age = api_recent_handshake(lp)
    enabled = bool(c['enabled'])
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
        'peers': [api_peer_payload(c, live=live) for c in rows],
        'categories': api_categories_payload() if user.get('is_admin') else [],
        'quota': api_user_quota(user),
        'errors': errors,
    }


@app.get('/api/categories')
def api_categories(user=Depends(api_require_auth)):
    if not user.get('is_admin'):
        return {'ok': True, 'categories': []}
    return {'ok': True, 'categories': api_categories_payload()}


@app.get('/api/users')
def api_users(user=Depends(api_require_admin)):
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
    return {'ok': True, 'backups': api_list_backups()}


@app.post('/api/backups')
async def api_backups_create(request: Request, user=Depends(api_require_admin)):
    path = api_create_backup_archive('manual')
    payload = api_backup_payload(path)
    api_audit_log(request, user, 'backup.create', 'backup', path.name, path.name, {'size': payload['size']})
    return {'ok': True, 'backup': payload, 'backups': api_list_backups()}


@app.get('/api/backups/{name}/download')
def api_backups_download(name: str, user=Depends(api_require_admin)):
    path = api_backup_path(name)
    return FileResponse(path, filename=path.name, media_type='application/gzip')


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
    return {'ok': True, 'restored': path.name, 'pre_restore_backup': api_backup_payload(pre_restore), 'backups': api_list_backups()}


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
    if not username:
        return api_error('Пустой логин', status_code=400)
    if username == PANEL_USER:
        return api_error('Этот логин занят системным администратором', status_code=409)
    if len(password) < 6:
        return api_error('Пароль должен быть не короче 6 символов', status_code=400)
    try:
        with db() as conn:
            conn.execute(
                'INSERT INTO panel_users(username, password_hash, role, peer_limit, enabled, created_at) VALUES (?, ?, ?, ?, 1, ?)',
                (username, password_hash(password), role, peer_limit, int(time.time())),
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
        {'role': role, 'peer_limit': peer_limit},
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
        before = conn.execute('SELECT id, username, role, peer_limit, enabled FROM panel_users WHERE id = ?', (user_id,)).fetchone()
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
        row = conn.execute('SELECT id, username, role, peer_limit, enabled FROM panel_users WHERE id = ?', (user_id,)).fetchone()
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
        except HTTPException as e:
            return api_error(str(e.detail), status_code=e.status_code)
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
            created_ids.append(create_client(name, protocol, category_id=category_id, owner_id=user.get('id')))
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
            {'protocols': protocols, 'category_id': category_id},
        )

    live, _ = api_live_maps()
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
    return {'ok': True, 'created_ids': created_ids, 'peers': [api_peer_payload(c, live=live) for c in rows]}


@app.patch('/api/peers/{client_id}')
async def api_peer_update(client_id: int, request: Request, user=Depends(api_require_auth)):
    if not user.get('is_admin'):
        return api_error('Недостаточно прав', status_code=403)
    data = await api_read_payload(request)
    try:
        category_id = api_category_id(data.get('category_id'))
    except HTTPException as e:
        return api_error(str(e.detail), status_code=e.status_code)
    with db() as conn:
        before = conn.execute(
            'SELECT id, name, protocol, category_id FROM clients WHERE id = ? AND COALESCE(deleted_at, 0) = 0',
            (client_id,),
        ).fetchone()
        if not before:
            return api_error('Клиент не найден', status_code=404)
        cur = conn.execute(
            'UPDATE clients SET category_id = ? WHERE id = ? AND COALESCE(deleted_at, 0) = 0',
            (category_id, client_id),
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
        {'protocol': before['protocol'], 'before_category_id': before['category_id'], 'category_id': category_id},
    )
    live, _ = api_live_maps()
    with db() as conn:
        c = conn.execute("""
            SELECT c.*, cat.name AS category_name, u.username AS owner_username
            FROM clients c
            LEFT JOIN categories cat ON cat.id = c.category_id
            LEFT JOIN panel_users u ON u.id = c.owner_id
            WHERE c.id = ?
        """, (client_id,)).fetchone()
    return {'ok': True, 'peer': api_peer_payload(c, live=live), 'categories': api_categories_payload()}


@app.get('/api/peers/{client_id}')
def api_peer_get(client_id: int, user=Depends(api_require_auth)):
    live, _ = api_live_maps()
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    return {'ok': True, 'peer': api_peer_payload(c, live=live, include_config=True)}


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
    try:
        enable_peer(c)
    except Exception as e:
        return api_error(str(e), status_code=500)
    api_audit_log(request, user, 'peer.enable', 'peer', client_id, c['name'], {'protocol': c['protocol'], 'ip_cidr': c['ip_cidr']})
    live, _ = api_live_maps()
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live)}


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
    live, _ = api_live_maps()
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live)}


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
    return {'ok': True, 'deleted_id': client_id}
# === 3WG REACT API END ===
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
block_re = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', flags=re.S)
cleaned = block_re.sub('', text).rstrip()
if FRONTEND_END in cleaned:
    patched = cleaned.replace(FRONTEND_END, FRONTEND_END + '\n\n' + API_BLOCK, 1)
else:
    patched = cleaned + '\n\n' + API_BLOCK
patched = re.sub(
    r'(# === 3WG REACT FRONTEND END ===)\n{3,}(# === 3WG REACT API START ===)',
    r'\1\n\n\2',
    patched,
)
patched = re.sub(
    r'(# === 3WG REACT API END ===)\n{3,}(# === 3WG SYSTEM STATUS API START ===)',
    r'\1\n\n\2',
    patched,
)

if patched != text:
    APP_PATH.write_text(patched, encoding='utf-8')
    print('React API routes patched into app.py')
else:
    print('React API routes already up to date')
