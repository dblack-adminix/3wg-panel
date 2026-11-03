"""Validated, fixed-URL catalog of optional ru-direct resources."""
import hashlib
import io
import ipaddress
import json
import re
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from client_routes import allowed_routes, resolve_groups

SOURCES = {
    'domains': 'Домены',
    'ipv4': 'IPv4',
    'ipv6': 'IPv6',
}
LOCK = threading.Lock()


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent':'3WG-Bypass-Catalog/1'})
    with urllib.request.urlopen(request, timeout=10) as response:
        content = response.read(2_000_001)
    if len(content) > 2_000_000:
        raise ValueError('Источник ru-direct превышает допустимый размер')
    return content


def group_sources(sources, metadata, domain_configs):
    categories = metadata.get('categories')
    if not isinstance(categories, list) or len(categories) > 50:
        raise ValueError('Некорректные категории ru-direct')
    available = {s['id']:set(s['items']) for s in sources}
    ip_items = {kind:{value:ipaddress.ip_network(value) for value in available[kind]} for kind in ('ipv4','ipv6')}
    groups = {kind:[] for kind in SOURCES}
    service_count = 0
    for category in categories:
        category_id = str(category.get('id', ''))
        if not re.fullmatch('[a-z0-9_-]{1,60}', category_id):
            raise ValueError('Некорректная категория ru-direct')
        title = str(category.get('title', category_id))[:100]
        domain_map = {s['name']:s.get('domains', []) for s in domain_configs.get(category_id, {}).get('services', [])}
        category_groups = {kind:{'id':category_id,'title':title,'services':[]} for kind in SOURCES}
        for service in category.get('services', []):
            service_count += 1
            if service_count > 250:
                raise ValueError('Слишком много сервисов ru-direct')
            if service.get('tier') not in ('lite','standard'):
                continue
            name = str(service.get('name', ''))[:100]
            service_id = category_id + '-' + hashlib.sha256(name.encode()).hexdigest()[:12]
            for kind in SOURCES:
                values = domain_map.get(name, []) if kind == 'domains' else service.get(kind, [])
                if not isinstance(values,list) or len(values)>5000 or not all(isinstance(v,str) for v in values):
                    raise ValueError('Некорректные записи сервиса ru-direct')
                parsed = parse_source(kind, '\n'.join(values)) if values else []
                if kind == 'domains':
                    items = sorted(set(parsed) & available[kind])
                else:
                    networks = list(map(ipaddress.ip_network,parsed))
                    items = sorted(value for value,network in ip_items[kind].items() if any(network.overlaps(other) for other in networks))
                if items:
                    category_groups[kind]['services'].append({'id':service_id,'title':name,'items':items})
        for kind, group in category_groups.items():
            if group['services']:
                group['items'] = sorted({value for service in group['services'] for value in service['items']})
                groups[kind].append(group)
    for source in sources:
        assigned = {value for group in groups[source['id']] for value in group['items']}
        remaining = sorted(available[source['id']] - assigned)
        if remaining:
            groups[source['id']].append({'id':'other','title':'Прочее','items':remaining,'services':[{'id':'other','title':'Без категории','items':remaining}]})
        source['groups'] = groups[source['id']]


def fetch_groups(sources):
    metadata = json.loads(download('https://github.com/kyoresuas/ru-direct/releases/latest/download/services.json'))
    if not isinstance(metadata.get('categories'), list) or len(metadata['categories']) > 50 or not all(isinstance(c,dict) for c in metadata['categories']):
        raise ValueError('Некорректные категории ru-direct')
    archive = zipfile.ZipFile(io.BytesIO(download('https://codeload.github.com/kyoresuas/ru-direct/zip/refs/heads/main')))
    configs = {}
    with archive:
        for category in metadata.get('categories', []):
            category_id = str(category.get('id', ''))
            if not re.fullmatch('[a-z0-9_-]{1,60}', category_id):
                raise ValueError('Некорректная категория ru-direct')
            path = 'ru-direct-main/config/services/' + category_id + '.json'
            if archive.getinfo(path).file_size > 200000:
                raise ValueError('Описание категории слишком большое')
            configs[category_id] = json.loads(archive.read(path))
    group_sources(sources, metadata, configs)


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
        if previous and previous.get('grouping_version') == 1 and not refresh and time.time() - previous['updated_at'] < 86400:
            return previous
        try:
            sources = []
            for kind, title in SOURCES.items():
                url = f'https://github.com/kyoresuas/ru-direct/releases/latest/download/ru-standard.{kind}.txt'
                content = download(url)
                items = parse_source(kind, content.decode('utf-8-sig'))
                sources.append({'id':kind, 'title':'ru-standard · '+title, 'url':url,
                                'items':items, 'count':len(items), 'sha256':hashlib.sha256(content).hexdigest()})
            fetch_groups(sources)
            result = {'sources':sources, 'updated_at':int(time.time()), 'stale':False, 'grouping_version':1}
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
