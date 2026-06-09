#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / 'app/app.py'
START = '# === 3WG REACT API START ==='
END = '# === 3WG REACT API END ==='

API_BLOCK = '''
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
        if include_raw:
            item['raw'] = raw
    except Exception as e:
        item['reason'] = str(e)
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
    payload = {
        'id': int(c['id']),
        'name': c['name'],
        'protocol': protocol,
        'protocol_title': p['title'],
        'ip_cidr': c['ip_cidr'],
        'public_key': c['public_key'],
        'enabled': bool(c['enabled']),
        'created_at': int(c['created_at']),
        'deleted_at': int(c['deleted_at']) if 'deleted_at' in c.keys() else 0,
        'endpoint': endpoint,
        'status': 'active' if active else 'offline',
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
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
block_re = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', flags=re.S)
cleaned = block_re.sub('', text).rstrip() + '\n\n'
patched = cleaned + API_BLOCK

if patched != text:
    APP_PATH.write_text(patched, encoding='utf-8')
    print('React API routes patched into app.py')
else:
    print('React API routes already up to date')
