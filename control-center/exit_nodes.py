"""Admin-only, pinned-host SSH bootstrap for minimal European exits."""
import base64
import hashlib
import hmac
import io
import ipaddress
import json
import secrets
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import paramiko
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from fastapi import Cookie, HTTPException, Request
from fastapi.responses import FileResponse

POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='exit-install')
LOCK = threading.Lock()
PENDING = 0
TEMPLATES = Path(__file__).parent / 'provision'


def target(ip, port):
    try:
        address = ipaddress.ip_address(str(ip))
        if address.version != 4 or not address.is_global or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError()
        return str(address), port
    except ValueError:
        raise HTTPException(400, 'Нужен публичный IPv4 и SSH-порт от 1 до 65535')


def fingerprint(key):
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')


def inspect_host(ip, port):
    sock = socket.create_connection((ip, port), timeout=10)
    transport = paramiko.Transport(sock)
    try:
        transport.start_client(timeout=10)
        return transport.get_remote_server_key()
    finally:
        transport.close()


def confirmation(secret, data):
    body = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode()
    return body + '.' + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def verify_confirmation(secret, token, ip, port):
    try:
        if len(token) > 16000:
            raise ValueError()
        body, signature = token.split('.')
        if not hmac.compare_digest(signature, hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(body))
        if data['ip'] != ip or data['port'] != port or data['expires'] <= time.time():
            raise ValueError()
        return data
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, 'Повторите проверку SSH-отпечатка')


def ssh_connect(row, password=None, private_key=None):
    sock = socket.create_connection((row['ip'], row['ssh_port']), timeout=10)
    transport = paramiko.Transport(sock)
    try:
        transport.start_client(timeout=15)
        key = transport.get_remote_server_key()
        if not hmac.compare_digest(key.asbytes(), base64.b64decode(row['host_key'])):
            raise RuntimeError('Host key changed')
        if password is not None:
            transport.auth_password('root', password)
        else:
            key = paramiko.Ed25519Key.from_private_key(io.StringIO(private_key))
            transport.auth_publickey('root', key)
        return transport
    except Exception:
        transport.close()
        raise


def command(transport, text, payload=None, timeout=60):
    channel = transport.open_session(timeout=15)
    try:
        channel.exec_command(text)
        if payload is not None:
            channel.sendall(payload)
        channel.shutdown_write()
        deadline = time.monotonic() + timeout
        output = bytearray()
        while True:
            while channel.recv_ready():
                block = channel.recv(32768)
                if len(output) < 65536:
                    output.extend(block[:65536-len(output)])
            while channel.recv_stderr_ready():
                channel.recv_stderr(32768)
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Remote operation timed out')
            time.sleep(.05)
        if channel.recv_exit_status() != 0:
            raise RuntimeError('Remote operation failed')
        return bytes(output)
    finally:
        channel.close()


def key_material():
    service = ed25519.Ed25519PrivateKey.generate()
    tunnel = x25519.X25519PrivateKey.generate()
    private = service.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()).decode()
    public = service.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    raw = tunnel.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    tunnel_public = tunnel.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    masking = 'Jc = 4\nJmin = 10\nJmax = 50\nS1 = 126\nS2 = 141\n'
    masking += ''.join(f'H{i+1} = {secrets.randbelow(400_000_000)+500_000_000*i+1000}\n' for i in range(4))
    config = '[Interface]\nPrivateKey = '+base64.b64encode(raw).decode()+'\nAddress = 10.254.200.2/32\nListenPort = 54443\nMTU = 1380\nTable = off\n'+masking
    return {'service_private':private, 'service_public':public, 'config':config, 'public_key':base64.b64encode(tunnel_public).decode()}


def install_worker(node_id, password, db, fernet):
    global PENDING
    transport = None
    staging = None
    def phase(status, message):
        with db() as conn:
            row = conn.execute('SELECT events FROM exit_nodes WHERE id=?', (node_id,)).fetchone()
            events = json.loads(row['events']) + [{'time':int(time.time()),'message':message}]
            conn.execute('UPDATE exit_nodes SET status=?,events=? WHERE id=?', (status,json.dumps(events),node_id))
    try:
        with db() as conn:
            row = conn.execute('SELECT * FROM exit_nodes WHERE id=?',(node_id,)).fetchone()
        phase('connecting','Проверка SSH-ключа и вход root')
        transport = ssh_connect(row, password=password)
        password = None
        phase('checking','Проверка ОС, свободного порта и отсутствия существующей установки')
        command(transport, 'test "$(id -u)" = 0 && test ! -e /opt/3wg-exit && test -c /dev/net/tun && . /etc/os-release && { test "$ID" = debian || test "$ID" = ubuntu; }', timeout=30)
        command(transport, 'if ! command -v python3 >/dev/null; then apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3; fi', timeout=300)
        command(transport, "python3 -c 'import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind((\"0.0.0.0\",54443));s.close()'")
        material = json.loads(fernet.decrypt(row['secrets_enc'].encode()))
        staging = '/root/.3wg-exit-' + secrets.token_hex(12)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            sftp.mkdir(staging, mode=0o700)
            files = {name:(TEMPLATES/name).read_bytes() for name in ('Dockerfile','start.sh','agent.py','install.sh')}
            files['exit0.conf'] = material['config'].encode()
            files['service.pub'] = ('\nrestrict,command="/usr/bin/python3 /usr/local/libexec/3wg-exit-agent.py" '+material['service_public']+' 3wg-managed-exit\n').encode()
            for name, content in files.items():
                with sftp.open(staging+'/'+name, 'wb') as stream:
                    stream.write(content)
                sftp.chmod(staging+'/'+name,0o600)
        finally:
            sftp.close()
        phase('installing','Установка минимального AWG-выхода; панель и клиентские пиры не устанавливаются')
        command(transport, 'sh '+staging+'/install.sh', timeout=1800)
        phase('verifying','Проверка отдельного служебного SSH-ключа')
        managed = ssh_connect(row, private_key=material['service_private'])
        try:
            result = json.loads(command(managed,'3wg-status',b'{"action":"status"}\n'))
            if not result.get('ok') or not result.get('running'):
                raise RuntimeError('Exit not running')
        finally:
            managed.close()
        phase('waiting_gateway','Выход установлен. Ожидает подключения входного узла РФ; каскад ещё не активен.')
    except Exception:
        phase('failed','Операция не завершена. Проверьте доступ, ОС, порт 54443/UDP и состояние сервера. Автоматического перезаписывания или удаления нет.')
    finally:
        password = None
        if transport:
            if staging:
                try:
                    command(transport, 'rm -rf -- '+staging, timeout=10)
                except Exception:
                    pass
            transport.close()
        with LOCK:
            PENDING -= 1


def register(app, db, require_auth, fernet, secret):
    with db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS exit_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,ip TEXT NOT NULL UNIQUE,
            ssh_port INTEGER NOT NULL,host_key TEXT NOT NULL,host_fingerprint TEXT NOT NULL,
            secrets_enc TEXT NOT NULL,status TEXT NOT NULL,events TEXT NOT NULL DEFAULT '[]',
            created_at INTEGER NOT NULL)''')
        conn.execute("UPDATE exit_nodes SET status='interrupted' WHERE status IN ('queued','connecting','checking','installing','verifying')")

    @app.get('/api/exits')
    async def list_exits(threewg_control_session: str | None = Cookie(default=None)):
        require_auth(threewg_control_session)
        with db() as conn:
            rows=conn.execute('SELECT id,name,ip,ssh_port,host_fingerprint,status,events,created_at FROM exit_nodes ORDER BY id DESC').fetchall()
        return {'exits':[{**dict(r),'events':json.loads(r['events'])} for r in rows]}

    @app.post('/api/exits/probe')
    async def probe(request: Request, threewg_control_session: str | None = Cookie(default=None)):
        require_auth(threewg_control_session)
        data=await request.json()
        ip,port=target(data.get('ip'),data.get('ssh_port',22))
        import asyncio
        try:
            key=await asyncio.to_thread(inspect_host,ip,port)
        except Exception:
            raise HTTPException(400,'SSH недоступен. Проверьте IP, порт и сетевой доступ.')
        payload={'ip':ip,'port':port,'key':base64.b64encode(key.asbytes()).decode(),'fingerprint':fingerprint(key),'expires':int(time.time())+600}
        return {'fingerprint':payload['fingerprint'],'confirmation':confirmation(secret,payload)}

    @app.post('/api/exits/install')
    async def install(request: Request, threewg_control_session: str | None = Cookie(default=None)):
        global PENDING
        require_auth(threewg_control_session)
        data=await request.json()
        ip,port=target(data.get('ip'),data.get('ssh_port',22))
        payload=verify_confirmation(secret,str(data.get('confirmation','')),ip,port)
        name,password=str(data.get('name','')).strip(),str(data.get('password',''))
        if not name or len(name)>100 or not 1<=len(password)<=1024 or data.get('confirmed') is not True:
            raise HTTPException(400,'Укажите название, root-пароль и подтвердите SSH-отпечаток')
        with LOCK:
            if PENDING>=2:
                raise HTTPException(429,'Дождитесь окончания текущих установок')
            material=key_material()
            try:
                with db() as conn:
                    import sqlite3
                    try:
                        node_id=conn.execute('INSERT INTO exit_nodes(name,ip,ssh_port,host_key,host_fingerprint,secrets_enc,status,created_at) VALUES(?,?,?,?,?,?,?,?)',
                            (name,ip,port,payload['key'],payload['fingerprint'],fernet.encrypt(json.dumps(material).encode()).decode(),'queued',int(time.time()))).lastrowid
                    except sqlite3.IntegrityError:
                        raise HTTPException(409,'Этот IP уже зарегистрирован; повторная установка запрещена')
                PENDING+=1
                POOL.submit(install_worker,node_id,password,db,fernet)
            finally:
                password=None
        return {'ok':True,'id':node_id}

    @app.post('/api/exits/{node_id}/{action}')
    async def manage(node_id: int, action: str, threewg_control_session: str | None = Cookie(default=None)):
        require_auth(threewg_control_session)
        if action not in ('status','restart','stop'):
            raise HTTPException(400,'Недопустимое действие')
        with db() as conn:
            row=conn.execute('SELECT * FROM exit_nodes WHERE id=?',(node_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Выход не найден')
        material=json.loads(fernet.decrypt(row['secrets_enc'].encode()))
        def execute():
            transport=ssh_connect(row,private_key=material['service_private'])
            try:
                return json.loads(command(transport,'3wg-'+action,json.dumps({'action':action}).encode()+b'\n'))
            finally:
                transport.close()
        import asyncio
        try:
            result=await asyncio.to_thread(execute)
        except Exception:
            raise HTTPException(502,'Служебный доступ недоступен или SSH-ключ сервера изменился')
        if action=='status':
            status='connected' if result.get('handshake') else 'waiting_gateway' if result.get('running') else 'stopped'
            with db() as conn:
                conn.execute('UPDATE exit_nodes SET status=? WHERE id=?',(status,node_id))
        return result

    @app.get('/exits')
    def exits_page():
        return FileResponse(Path(__file__).parent/'static'/'exits.html',headers={'Cache-Control':'no-store'})
