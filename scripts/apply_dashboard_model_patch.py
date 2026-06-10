#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / 'app/app.py'
START = '# === 3WG DASHBOARD MODEL API START ==='
END = '# === 3WG DASHBOARD MODEL API END ==='

BLOCK = '''
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
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + BLOCK
APP_PATH.write_text(text, encoding='utf-8')
print('Dashboard model API patched into app.py')
