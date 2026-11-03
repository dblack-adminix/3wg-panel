"""Build static client-side split routes using Python's IP network operations."""
import ipaddress
import re
import socket
from functools import lru_cache


def resolve_domain(host):
    try:
        addresses = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f'Не удалось разрешить домен {host}; прежние настройки сохранены') from exc
    networks = {str(ipaddress.ip_network(address[4][0])) for address in addresses}
    if not networks:
        raise ValueError(f'Не найдены адреса домена {host}; прежние настройки сохранены')
    return networks


def allowed_routes(networks):
    return list(_allowed_routes(tuple(sorted(set(networks)))))


@lru_cache(maxsize=16)
def _allowed_routes(networks):
    routes = []
    for version, root in [(4, '0.0.0.0/0'), (6, '::/0')]:
        exclusions = list(ipaddress.collapse_addresses([ipaddress.ip_network(n) for n in networks if ipaddress.ip_network(n).version == version]))
        remaining = [ipaddress.ip_network(root)]
        for excluded in exclusions:
            updated = []
            for network in remaining:
                if network.subnet_of(excluded):
                    continue
                updated.extend(network.address_exclude(excluded) if excluded.subnet_of(network) else [network])
            remaining = updated
        routes.extend(str(n) for n in ipaddress.collapse_addresses(remaining))
    if len(routes) > 16384 or not routes:
        raise ValueError('Слишком много маршрутов или список исключает весь интернет')
    return tuple(routes)


def resolve_groups(groups):
    if not isinstance(groups, list) or len(groups) > 32:
        raise ValueError('Допускается до 32 ресурсов')
    result = []
    count = 0
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('Некорректный ресурс')
        name = str(group.get('name', '')).strip()[:100]
        targets = group.get('targets', [])
        if not name or not isinstance(targets, list) or not targets:
            raise ValueError('Укажите название ресурса и его домены или сети')
        normalized, networks = [], set()
        for target in targets:
            count += 1
            if count > 128:
                raise ValueError('Допускается до 128 доменов и сетей')
            target = str(target).strip()
            try:
                network = ipaddress.ip_network(target, strict=False)
                if network.prefixlen == 0:
                    raise ValueError('Нельзя исключить весь интернет')
                networks.add(str(network))
                normalized.append(str(network))
                continue
            except ValueError:
                if '/' in target or ':' in target:
                    raise ValueError(f'Некорректная сеть: {target}')
            host = target.rstrip('.').encode('idna').decode('ascii').lower()
            if len(host) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}', host):
                raise ValueError(f'Укажите точный домен без URL и звёздочки: {target}')
            networks.update(resolve_domain(host))
            normalized.append(host)
        result.append({'name': name, 'targets': normalized, 'networks': sorted(networks)})
    routes = allowed_routes([n for g in result for n in g['networks']])
    return result, routes
