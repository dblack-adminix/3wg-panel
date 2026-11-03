"""Validated, fixed-URL catalog of optional ru-direct resources."""
import hashlib
import ipaddress
import json
import re
import threading
import time
import urllib.request
from pathlib import Path

from client_routes import allowed_routes, resolve_groups

SOURCES = {
    'domains': 'Домены',
    'ipv4': 'IPv4',
    'ipv6': 'IPv6',
}
LOCK = threading.Lock()


def parse_source(kind, text):
    items = set()
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith('#'):
            continue
        if kind == 'domains':
            value = value.rstrip('.').encode('idna').decode('ascii').lower()
            if len(value) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}', value):
                raise ValueError('Некорректный домен в ru-direct')
        else:
            network = ipaddress.ip_network(value, strict=True)
            if network.version != (4 if kind == 'ipv4' else 6) or network.prefixlen == 0:
                raise ValueError('Некорректная сеть в ru-direct')
            value = str(network)
        items.add(value)
        if len(items) > 20000:
            raise ValueError('Список ru-direct слишком большой')
    if not items:
        raise ValueError('Источник ru-direct вернул пустой список')
    return sorted(items)


def load_catalog(path, refresh=False):
    path = Path(path)
    with LOCK:
        previous = json.loads(path.read_text()) if path.exists() else None
        if previous and not refresh and time.time() - previous['updated_at'] < 86400:
            return previous
        try:
            sources = []
            for kind, title in SOURCES.items():
                url = f'https://github.com/kyoresuas/ru-direct/releases/latest/download/ru-standard.{kind}.txt'
                request = urllib.request.Request(url, headers={'User-Agent':'3WG-Bypass-Catalog/1'})
                with urllib.request.urlopen(request, timeout=10) as response:
                    content = response.read(2_000_001)
                if len(content) > 2_000_000:
                    raise ValueError('Источник ru-direct превышает допустимый размер')
                items = parse_source(kind, content.decode('utf-8-sig'))
                sources.append({'id':kind, 'title':'ru-standard · '+title, 'url':url,
                                'items':items, 'count':len(items), 'sha256':hashlib.sha256(content).hexdigest()})
            result = {'sources':sources, 'updated_at':int(time.time()), 'stale':False}
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps(result))
            tmp.chmod(0o600)
            tmp.replace(path)
            return result
        except Exception as exc:
            if previous:
                return {**previous, 'stale':True, 'error':'Не удалось обновить ru-direct. Используется сохранённая копия.'}
            raise ValueError('Не удалось загрузить списки ru-direct. Повторите обновление.') from exc


def resolve_policy(groups, selected, catalog):
    if not isinstance(selected, dict) or any(k not in SOURCES for k in selected):
        raise ValueError('Некорректный выбор источников')
    available = {s['id']:set(s['items']) for s in catalog.get('sources', [])}
    selections = {}
    for kind, values in selected.items():
        if not isinstance(values, list) or len(values) > 20000 or not all(isinstance(v,str) for v in values):
            raise ValueError('Некорректный выбор записей')
        if not set(values).issubset(available.get(kind,set())):
            raise ValueError('Часть выбранных записей отсутствует в каталоге. Проверьте выбор.')
        selections[kind] = sorted(set(values))
    domains = selections.get('domains', [])
    if not isinstance(groups,list) or any(not isinstance(g,dict) or not isinstance(g.get('targets'),list) for g in groups):
        raise ValueError('Некорректные ручные ресурсы')
    if len(domains) + sum(len(g['targets']) for g in groups) > 128:
        raise ValueError('Выберите до 128 доменов и ручных адресов суммарно. Готовые IPv4/IPv6-сети не входят в этот лимит.')
    resolved, _ = resolve_groups(groups)
    source_networks = selections.get('ipv4', []) + selections.get('ipv6', [])
    if domains:
        domain_groups, _ = resolve_groups([{'name':'ru-standard domains','targets':domains}])
        source_networks += domain_groups[0]['networks']
    source_networks = sorted(set(source_networks))
    routes = allowed_routes(source_networks + [n for g in resolved for n in g['networks']])
    return resolved, source_networks, routes
