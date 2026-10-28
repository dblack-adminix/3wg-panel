"""Host-side IPv4 egress switching; only the installation's own NAT chain is changed."""
import hashlib
import ipaddress
import json
import socket
import subprocess
import threading
import time
from pathlib import Path


class NetworkManager:
    def __init__(self, base):
        self.base = Path(base)
        self.path = self.base / 'data/network-ip.json'
        self.chain = 'WGIP_' + hashlib.sha256(str(self.base).encode()).hexdigest()[:10]
        self.lock = threading.RLock()
        self.last_error = ''

    def run(self, *args, input=None):
        result = subprocess.run(args, input=input, capture_output=True, text=True, timeout=12)
        if result.returncode:
            raise RuntimeError(f'{args[0]}: {result.stderr.strip()[:350]}')
        return result.stdout

    def config(self):
        values = {}
        for line in (self.base / '.env').read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"\'')
        return values

    def state(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data))
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def inventory(self):
        result = []
        for interface in json.loads(self.run('ip', '-j', '-4', 'addr', 'show')):
            for addr in interface.get('addr_info', []):
                ip = addr.get('local', '')
                if addr.get('scope') == 'global' and ipaddress.ip_address(ip).is_global:
                    result.append({'ip': ip, 'interface': interface['ifname']})
        return result

    def topology(self, config):
        containers = []
        for key in ('WG_CONTAINER', 'AWG_CONTAINER'):
            name = config.get(key)
            if not name or any(c['name'] == name for c in containers):
                continue
            data = json.loads(self.run('docker', 'inspect', name))[0]
            mode = data['HostConfig']['NetworkMode']
            if mode in ('host', 'none') or mode.startswith('container:'):
                raise RuntimeError(f'{name}: поддерживается только отдельная bridge-сеть Docker')
            ports = data['HostConfig'].get('PortBindings') or {}
            if not data['State']['Running'] or not ports:
                raise RuntimeError(f'{name}: контейнер не запущен или порты не опубликованы')
            for bindings in ports.values():
                for binding in bindings or []:
                    if binding.get('HostIp') not in ('', '0.0.0.0', '::'):
                        raise RuntimeError(f'{name}: порт привязан к конкретному IP; сначала измените публикацию Docker')
            addresses = [n['IPAddress'] for n in data['NetworkSettings']['Networks'].values() if n.get('IPAddress')]
            if not addresses:
                raise RuntimeError(f'{name}: IPv4 Docker не найден')
            containers.append({'name': name, 'addresses': addresses})
        if not containers:
            raise RuntimeError('VPN-контейнеры не настроены')
        return containers

    def dns(self, host):
        try:
            return sorted({x[4][0] for x in socket.getaddrinfo(host, None, socket.AF_INET)})
        except socket.gaierror:
            return []

    def status(self):
        with self.lock:
            config = self.config()
            state = self.state()
            return {'ok': True, 'addresses': self.inventory(),
                    'panel_host': config.get('PANEL_HOST', ''),
                    'endpoint_host': config.get('VPN_ENDPOINT_HOST') or config.get('ENDPOINT_HOST', ''),
                    'configured_ip': config.get('VPN_EGRESS_IP', ''),
                    'active_ip': state.get('active_ip', ''), 'pending': state.get('pending'),
                    'last_error': self.last_error, 'supported': True}

    def preview(self, ip):
        ip = str(ipaddress.IPv4Address(ip))
        config = self.config()
        if ip not in {x['ip'] for x in self.inventory()}:
            raise ValueError('Выбранный публичный IPv4 не назначен серверу')
        hosts = {config.get('PANEL_HOST', ''), config.get('VPN_ENDPOINT_HOST') or config.get('ENDPOINT_HOST', '')}
        dns = [{'host': host, 'addresses': self.dns(host)} for host in sorted(hosts) if host]
        if not dns or any(ip not in host['addresses'] for host in dns):
            raise ValueError('Сначала направьте DNS панели и VPN на выбранный IP; проверьте также /etc/hosts')
        containers = self.topology(config)
        routes = json.loads(self.run('ip', '-j', '-4', 'route', 'get', '1.1.1.1', 'from', ip))
        device = routes[0].get('dev') if routes else None
        if not device:
            raise RuntimeError('Не найден исходящий интерфейс')
        self.run('iptables', '-w', '3', '-t', 'nat', '-S', 'POSTROUTING')
        return {'ok': True, 'ip': ip, 'dns': dns, 'containers': containers, 'device': device,
                'confirmation_seconds': 180}

    def rules(self, ip, plan=None):
        existing = self.run('iptables', '-w', '3', '-t', 'nat', '-S')
        present = f'-N {self.chain}' in existing or f':{self.chain} ' in existing
        commands = ['*nat']
        if not present:
            commands.append(f':{self.chain} - [0:0]')
        commands.append(f'-F {self.chain}')
        if ip:
            plan = plan or self.preview(ip)
            for container in plan['containers']:
                for source in container['addresses']:
                    source = str(ipaddress.IPv4Address(source))
                    commands.append(f'-A {self.chain} -s {source}/32 -o {plan["device"]} -j SNAT --to-source {ip}')
        jump = f'-A POSTROUTING -j {self.chain}'
        if jump not in existing.splitlines():
            commands.append(f'-I POSTROUTING 1 -j {self.chain}')
        commands.append('COMMIT')
        self.run('iptables-restore', '--wait', '3', '--noflush', input='\n'.join(commands) + '\n')

    def write_egress(self, ip):
        path = self.base / '.env'
        lines = path.read_text().splitlines()
        lines = [line for line in lines if not line.startswith('VPN_EGRESS_IP=')]
        lines.append(f'VPN_EGRESS_IP={ip}')
        tmp = path.with_suffix('.network.tmp')
        tmp.write_text('\n'.join(lines) + '\n')
        tmp.chmod(0o600)
        tmp.replace(path)

    def rollback(self, state):
        pending = state.get('pending') or {}
        previous = pending.get('previous_ip', '')
        # Rollback must not depend on DNS, which may already point at the new address.
        config = self.config()
        routes = json.loads(self.run('ip', '-j', '-4', 'route', 'get', '1.1.1.1'))
        plan = {'containers': self.topology(config), 'device': routes[0]['dev']} if previous else None
        self.rules(previous, plan)
        self.write_egress(pending.get('previous_configured_ip', ''))
        self.save({'active_ip': previous, 'pending': None})

    def command(self, command, payload):
        with self.lock:
            if command == 'network-status':
                return self.status()
            if command == 'network-preview':
                return self.preview(payload.get('ip', ''))
            state = self.state()
            if command == 'network-apply':
                if state.get('pending'):
                    raise ValueError('Сначала подтвердите или отмените предыдущее изменение')
                plan = self.preview(payload.get('ip', ''))
                backup = self.base / 'backups/network' / f'env-{time.time_ns()}.backup'
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes((self.base / '.env').read_bytes())
                backup.chmod(0o600)
                pending = {'previous_ip': state.get('active_ip', ''),
                           'previous_configured_ip': self.config().get('VPN_EGRESS_IP', ''),
                           'deadline': int(time.time()) + 180, 'backup': str(backup)}
                state = {'active_ip': plan['ip'], 'pending': pending}
                # Persist rollback intent before changing the firewall.
                self.save(state)
                try:
                    self.rules(plan['ip'], plan)
                    self.write_egress(plan['ip'])
                except Exception:
                    self.rollback(state)
                    raise
            elif command == 'network-confirm':
                if not state.get('pending') or state['pending']['deadline'] <= time.time():
                    raise ValueError('Нет ожидающего подтверждения изменения')
                if payload.get('ip') != state.get('active_ip'):
                    raise ValueError('IP подтверждения не совпадает')
                state['pending'] = None
                self.save(state)
            elif command == 'network-rollback':
                if not state.get('pending'):
                    raise ValueError('Нет изменения для отката')
                self.rollback(state)
            else:
                raise ValueError('Неизвестная сетевая операция')
            return self.status()

    def maintain_once(self):
        with self.lock:
            state = self.state()
            if state.get('pending') and state['pending']['deadline'] <= time.time():
                self.rollback(state)
            elif state.get('active_ip'):
                config = self.config()
                ip = state['active_ip']
                if ip not in {x['ip'] for x in self.inventory()}:
                    raise RuntimeError('Настроенный IPv4 больше не назначен серверу')
                routes = json.loads(self.run('ip', '-j', '-4', 'route', 'get', '1.1.1.1', 'from', ip))
                self.rules(ip, {'containers': self.topology(config), 'device': routes[0]['dev']})

    def maintain(self):
        while True:
            try:
                self.maintain_once()
                self.last_error = ''
            except Exception as exc:
                self.last_error = str(exc)
            time.sleep(15)
