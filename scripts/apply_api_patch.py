#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / 'app/app.py'
START = '# === 3WG REACT API START ==='
END = '# === 3WG REACT API END ==='
FRONTEND_END = '# === 3WG REACT FRONTEND END ==='

PORT_CHANGE_HELPERS = r'''
def valid_udp_port(value) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Некорректный UDP порт")
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Некорректный UDP порт")
    return port


def env_key_for_protocol_port(protocol: str) -> str:
    return "WG_PORT" if protocol == "wireguard" else "AWG_PORT"


def env_file_path() -> Path:
    candidates = [Path("/srv/3wg-panel/.env"), APP_DIR / ".env"]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def update_env_port(protocol: str, port: int) -> bool:
    path = env_file_path()
    if not path.exists():
        return False
    key = env_key_for_protocol_port(protocol)
    text = path.read_text(encoding="utf-8")
    line = f"{key}={port}"
    if re.search(rf"^{re.escape(key)}=.*$", text, flags=re.M):
        text = re.sub(rf"^{re.escape(key)}=.*$", line, text, flags=re.M)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    backup = BACKUPS_DIR / "source" / f".env.port-change.{time.strftime('%Y%m%d_%H%M%S')}.backup"
    backup.parent.mkdir(parents=True, exist_ok=True)
    try:
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        backup.chmod(0o600)
    except Exception:
        pass
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return True


def docker_udp_port_owner(port: int) -> str | None:
    target = str(port)
    try:
        containers = dc().containers.list(all=True)
    except Exception:
        return None
    for container in containers:
        ports = (container.attrs.get("NetworkSettings") or {}).get("Ports") or {}
        for key, bindings in ports.items():
            if not str(key).endswith("/udp"):
                continue
            for binding in bindings or []:
                if str((binding or {}).get("HostPort") or "").strip() == target:
                    return container.name
    return None


def host_udp_port_owner(port: int) -> str | None:
    try:
        result = subprocess.run(
            ["ss", "-H", "-lunp"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    marker = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[4]
        if not (local.endswith(marker) or local.endswith(f"{marker}]") or f"{marker} " in line):
            continue
        match = re.search(r'users:\(\("([^"]+)"', line)
        if match:
            return match.group(1)
        return "system"
    return None


def ensure_udp_port_available(protocol: str, port: int) -> None:
    owner = docker_udp_port_owner(port)
    current_container = proto(protocol)["container"]
    if owner and owner != current_container:
        raise HTTPException(status_code=409, detail=f"UDP порт {port} уже занят контейнером {owner}")
    host_owner = host_udp_port_owner(port)
    if host_owner and host_owner != "docker-proxy":
        raise HTTPException(status_code=409, detail=f"UDP порт {port} уже занят процессом {host_owner}")


def docker_port_conflict_detail(error: Exception, port: int) -> str | None:
    text = str(error)
    lowered = text.lower()
    if "address already in use" not in lowered and "port is already allocated" not in lowered:
        return None
    if port == 443:
        return "UDP порт 443 уже занят на сервере. Обычно его занимает Caddy/HTTP3. Освободите 443/udp или выберите другой порт из списка."
    return f"UDP порт {port} уже занят на сервере. Освободите порт или выберите другой UDP порт."


def set_container_listen_port(protocol: str, port: int) -> None:
    p = proto(protocol)
    backup_config(protocol)
    script = (
        f"path={shlex.quote(p['config_path'])}\n"
        f"line='ListenPort = {port}'\n"
        f"if grep -Eq '^[[:space:]]*ListenPort[[:space:]]*=' \"$path\"; then\n"
        f"  sed -i -E \"s|^[[:space:]]*ListenPort[[:space:]]*=.*$|$line|\" \"$path\"\n"
        f"else\n"
        f"  printf '\\n%s\\n' \"$line\" >> \"$path\"\n"
        f"fi\n"
    )
    sh(p["container"], script)


def protocol_config_with_listen_port(text: str, port: int) -> str:
    line = f"ListenPort = {port}"
    if re.search(r"^\s*ListenPort\s*=.*$", text, flags=re.M):
        return re.sub(r"^\s*ListenPort\s*=.*$", line, text, flags=re.M)
    return text.rstrip() + "\n" + line + "\n"


def put_container_text_file(container, path: str, text: str, mode: int = 0o600) -> None:
    target = Path(path)
    base = target.parent.parent if len(target.parts) >= 3 else target.parent
    arc_dir = target.parent.name
    arc_name = f"{arc_dir}/{target.name}" if base != target.parent else target.name
    data = io.BytesIO()
    payload = text.encode("utf-8")
    with tarfile.open(fileobj=data, mode="w") as tar:
        if base != target.parent:
            dir_info = tarfile.TarInfo(arc_dir)
            dir_info.type = tarfile.DIRTYPE
            dir_info.mode = 0o700
            dir_info.mtime = int(time.time())
            tar.addfile(dir_info)
        info = tarfile.TarInfo(arc_name)
        info.size = len(payload)
        info.mode = mode
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(payload))
    data.seek(0)
    container.put_archive(str(base), data.read())


def protocol_autostart_script(protocol: str) -> str:
    p = proto(protocol)
    tool = shlex.quote(p["tool"])
    quick = shlex.quote(f"{p['tool']}-quick")
    iface = shlex.quote(p["interface"])
    config_path = shlex.quote(p["config_path"])
    return (
        "#!/bin/sh\n"
        f"if command -v {tool} >/dev/null 2>&1 && command -v {quick} >/dev/null 2>&1; then\n"
        f"  if ! {tool} show {iface} >/dev/null 2>&1; then\n"
        f"    {quick} up {config_path} || true\n"
        "  fi\n"
        "fi\n"
        "if [ -x /opt/amnezia/3wg-p2p-guard.sh ]; then\n"
        "  /opt/amnezia/3wg-p2p-guard.sh || true\n"
        "fi\n"
        "tail -f /dev/null\n"
    )


def ensure_protocol_autostart(protocol: str) -> None:
    p = proto(protocol)
    put_container_text_file(dc().containers.get(p["container"]), "/opt/amnezia/start.sh", protocol_autostart_script(protocol), mode=0o755)


def activate_protocol_interface(protocol: str) -> None:
    p = proto(protocol)
    try:
        exec_c(p["container"], [p["tool"], "show", p["interface"]], check=True)
        return
    except Exception:
        pass
    sh(p["container"], f"{shlex.quote(p['tool'] + '-quick')} up {shlex.quote(p['config_path'])}", check=False)
    exec_c(p["container"], [p["tool"], "show", p["interface"]], check=True)


def activate_protocol_interface_by_container(protocol: str, container_name: str) -> None:
    p = proto(protocol)
    try:
        exec_c(container_name, [p["tool"], "show", p["interface"]], check=True)
        return
    except Exception:
        pass
    sh(container_name, f"{shlex.quote(p['tool'] + '-quick')} up {shlex.quote(p['config_path'])}", check=False)
    exec_c(container_name, [p["tool"], "show", p["interface"]], check=True)


def recreate_protocol_container(protocol: str, port: int, config_text: str) -> None:
    p = proto(protocol)
    docker_client = dc()
    old = docker_client.containers.get(p["container"])
    attrs = old.attrs
    config = attrs.get("Config") or {}
    host_config = attrs.get("HostConfig") or {}
    image = config.get("Image") or (old.image.tags[0] if old.image.tags else old.image.id)
    env = list(config.get("Env") or [])
    binds = list(host_config.get("Binds") or [])
    cap_add = host_config.get("CapAdd") or []
    sysctls = host_config.get("Sysctls") or {}
    restart_name = (host_config.get("RestartPolicy") or {}).get("Name") or "unless-stopped"
    command = config.get("Cmd")
    entrypoint = config.get("Entrypoint")
    labels = config.get("Labels") or {}
    privileged = bool(host_config.get("Privileged"))
    security_opt = host_config.get("SecurityOpt") or None
    temp_name = f"{p['container']}-port-{int(time.time())}"
    new_container = docker_client.containers.create(
        image,
        name=temp_name,
        environment=env,
        command=command,
        entrypoint=entrypoint,
        labels=labels,
        volumes=binds,
        ports={f"{port}/udp": port},
        cap_add=cap_add,
        sysctls=sysctls,
        restart_policy={"Name": restart_name},
        privileged=privileged,
        security_opt=security_opt,
    )
    try:
        put_container_text_file(new_container, p["config_path"], config_text)
        put_container_text_file(new_container, "/opt/amnezia/start.sh", protocol_autostart_script(protocol), mode=0o755)
        new_container.start()
        activate_protocol_interface_by_container(protocol, new_container.name)
    except Exception as e:
        try:
            new_container.remove(force=True)
        except Exception:
            pass
        detail = docker_port_conflict_detail(e, port)
        if detail:
            raise HTTPException(status_code=409, detail=detail)
        raise

    old.stop(timeout=10)
    old.remove()
    new_container.reload()
    new_container.rename(p["container"])


def change_protocol_port(protocol: str, port: int) -> dict:
    ensure_udp_port_available(protocol, port)
    p = proto(protocol)
    current = int(docker_published_udp_port(protocol))
    if port == current:
        return {"changed": False, "protocol": protocol, "port": port, "state": api_protocol_state(protocol)}
    original_config = exec_c(p["container"], ["sh", "-lc", f"cat {shlex.quote(p['config_path'])}"], check=True)
    backup_config(protocol)
    next_config = protocol_config_with_listen_port(original_config, port)
    recreate_protocol_container(protocol, port, next_config)
    update_env_port(protocol, port)
    runtime_cache_clear()
    return {"changed": True, "protocol": protocol, "old_port": current, "port": port, "state": api_protocol_state(protocol)}
'''.strip() + '\n'

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


def api_migration_dir() -> Path:
    path = BACKUPS_DIR / 'migration'
    path.mkdir(parents=True, exist_ok=True)
    return path


def api_auto_backup_settings() -> dict:
    raw = panel_setting_get('backup_auto')
    settings = dict(AUTO_BACKUP_DEFAULTS)
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception:
            pass
    settings['enabled'] = bool(settings.get('enabled'))
    try:
        settings['interval_hours'] = int(settings.get('interval_hours', AUTO_BACKUP_DEFAULTS['interval_hours']))
    except (TypeError, ValueError):
        settings['interval_hours'] = AUTO_BACKUP_DEFAULTS['interval_hours']
    try:
        settings['keep_last'] = int(settings.get('keep_last', AUTO_BACKUP_DEFAULTS['keep_last']))
    except (TypeError, ValueError):
        settings['keep_last'] = AUTO_BACKUP_DEFAULTS['keep_last']
    try:
        settings['last_run_at'] = int(settings.get('last_run_at') or 0)
    except (TypeError, ValueError):
        settings['last_run_at'] = 0
    settings['interval_hours'] = min(max(settings['interval_hours'], 1), 168)
    settings['keep_last'] = min(max(settings['keep_last'], 1), 100)
    settings['next_run_at'] = (
        settings['last_run_at'] + settings['interval_hours'] * 3600
        if settings['enabled'] and settings['last_run_at']
        else 0
    )
    return settings


def api_save_auto_backup_settings(settings: dict) -> dict:
    interval_hours = min(max(int(settings.get('interval_hours', 24)), 1), 168)
    if interval_hours not in AUTO_BACKUP_INTERVALS:
        interval_hours = AUTO_BACKUP_DEFAULTS['interval_hours']
    payload = {
        'enabled': bool(settings.get('enabled')),
        'interval_hours': interval_hours,
        'keep_last': min(max(int(settings.get('keep_last', 7)), 1), 100),
        'last_run_at': int(settings.get('last_run_at') or 0),
    }
    panel_setting_set('backup_auto', json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    return api_auto_backup_settings()


def api_prune_auto_backups(keep_last: int) -> list[str]:
    deleted = []
    auto_files = [
        p for p in sorted(api_manual_backup_dir().glob('3wg-panel.auto.*.tgz'), key=lambda x: x.stat().st_mtime, reverse=True)
        if p.is_file()
    ]
    for path in auto_files[max(1, keep_last):]:
        try:
            path.unlink()
            deleted.append(path.name)
        except FileNotFoundError:
            pass
    return deleted


def api_maybe_run_auto_backup(force: bool = False) -> dict | None:
    settings = api_auto_backup_settings()
    if not settings['enabled']:
        return None
    now = int(time.time())
    due_at = settings['last_run_at'] + settings['interval_hours'] * 3600 if settings['last_run_at'] else 0
    if not force and due_at and now < due_at:
        return None
    if not AUTO_BACKUP_LOCK.acquire(blocking=False):
        return None
    try:
        settings = api_auto_backup_settings()
        now = int(time.time())
        due_at = settings['last_run_at'] + settings['interval_hours'] * 3600 if settings['last_run_at'] else 0
        if not force and settings['last_run_at'] and now < due_at:
            return None
        path = api_create_backup_archive('auto')
        settings['last_run_at'] = int(path.stat().st_mtime)
        saved = api_save_auto_backup_settings(settings)
        deleted = api_prune_auto_backups(saved['keep_last'])
        return {'backup': api_backup_payload(path), 'deleted': deleted, 'auto': saved}
    finally:
        AUTO_BACKUP_LOCK.release()


def auto_backup_worker() -> None:
    while True:
        try:
            api_maybe_run_auto_backup()
        except Exception as e:
            print(f"Auto backup failed: {e}")
        time.sleep(60)


def start_auto_backup_worker() -> None:
    global AUTO_BACKUP_THREAD_STARTED
    if AUTO_BACKUP_THREAD_STARTED:
        return
    AUTO_BACKUP_THREAD_STARTED = True
    threading.Thread(target=auto_backup_worker, daemon=True).start()


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


def api_migration_path(name: str) -> Path:
    clean = Path(str(name or '')).name
    if not clean or clean != str(name or '') or not clean.endswith('.tgz'):
        raise HTTPException(status_code=400, detail='Некорректное имя migration bundle')
    path = (api_migration_dir() / clean).resolve()
    root = api_migration_dir().resolve()
    if root not in path.parents:
        raise HTTPException(status_code=400, detail='Некорректный путь migration bundle')
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail='Migration bundle не найден')
    return path


def api_migration_payload(path: Path) -> dict:
    stat = path.stat()
    return {
        'name': path.name,
        'size': int(stat.st_size),
        'created_at': int(stat.st_mtime),
        'download_url': f'/api/migration/{path.name}/download',
    }


def api_list_migration_bundles() -> list[dict]:
    return [
        api_migration_payload(p)
        for p in sorted(api_migration_dir().glob('*.tgz'), key=lambda x: x.stat().st_mtime, reverse=True)
        if p.is_file()
    ]


def api_env_snapshot() -> bytes:
    keys = [
        'PANEL_USER', 'PANEL_PASSWORD', 'PANEL_CONTAINER',
        'PANEL_HOST', 'ENDPOINT_HOST', 'VPN_ENDPOINT_HOST', 'VPN_EGRESS_IP',
        'WG_CONTAINER', 'WG_INTERFACE', 'WG_PORT', 'WG_CONFIG_PATH', 'WG_NETWORK',
        'AWG_CONTAINER', 'AWG_INTERFACE', 'AWG_PORT', 'AWG_CONFIG_PATH', 'AWG_NETWORK',
        'DNS_SERVERS', 'SESSION_SECRET', 'HIDE_EXISTING_PEERS',
        'METRICS_ENABLED', 'METRICS_REQUIRE_TOKEN', 'METRICS_TOKEN',
        'TELEGRAM_ENABLED', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
        'UPDATE_RUNNER_ENABLED', 'UPDATE_RUNNER_SOCKET',
        'MIGRATION_RUNNER_ENABLED', 'MIGRATION_RUNNER_SOCKET',
    ]
    lines = []
    for key in keys:
        if key in os.environ:
            value = str(os.environ.get(key, '')).replace('\n', '')
            lines.append(f'{key}={value}')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def api_tar_add_bytes(tar: tarfile.TarFile, arcname: str, payload: bytes, mode: int = 0o600) -> None:
    info = tarfile.TarInfo(arcname)
    info.size = len(payload)
    info.mtime = int(time.time())
    info.mode = mode
    tar.addfile(info, io.BytesIO(payload))


def api_container_file_bytes(container_name: str, path: str) -> bytes | None:
    if not container_name or not path:
        return None
    try:
        container = dc().containers.get(container_name)
        stream, _ = container.get_archive(path)
        raw = b''.join(stream)
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as src_tar:
            member = next((m for m in src_tar.getmembers() if m.isfile()), None)
            if not member:
                return None
            extracted = src_tar.extractfile(member)
            return extracted.read() if extracted else None
    except Exception:
        return None


def api_create_migration_bundle(include_backups: bool = False) -> Path:
    migration_dir = api_migration_dir()
    ts = time.strftime('%Y-%m-%d_%H-%M-%S', time.localtime())
    safe_host = re.sub(r'[^A-Za-z0-9_.-]+', '-', PANEL_HOST or VPN_ENDPOINT_HOST or socket.gethostname()).strip('-') or 'node'
    path = migration_dir / f'3wg-core.migration.{safe_host}.{ts}.tgz'
    manifest = {
        'product': '3WG Core',
        'kind': 'migration-bundle',
        'version': APP_VERSION,
        'created_at': int(time.time()),
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'legacy_endpoint_host': ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'include_backups': bool(include_backups),
        'includes': ['panel/.env', 'panel/data', 'panel/clients', 'protocols/*/config.conf'],
    }
    with tarfile.open(path, 'w:gz') as tar:
        api_tar_add_bytes(tar, 'metadata.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'), 0o600)
        api_tar_add_bytes(tar, 'panel/.env', api_env_snapshot(), 0o600)
        if DATA_DIR.exists():
            tar.add(DATA_DIR, arcname='panel/data', recursive=True)
        if CLIENTS_DIR.exists():
            tar.add(CLIENTS_DIR, arcname='panel/clients', recursive=True)
        if include_backups:
            for child in BACKUPS_DIR.iterdir() if BACKUPS_DIR.exists() else []:
                if child.name == 'migration':
                    continue
                tar.add(child, arcname=f'panel/backups/{child.name}', recursive=True)
        for protocol, p in PROTOCOLS.items():
            config = api_container_file_bytes(p['container'], p['config_path'])
            if config:
                api_tar_add_bytes(tar, f'protocols/{protocol}/config.conf', config, 0o600)
                api_tar_add_bytes(tar, f'protocols/{protocol}/container.txt', str(p['container']).encode('utf-8') + b'\n', 0o600)
                api_tar_add_bytes(tar, f'protocols/{protocol}/config_path.txt', str(p['config_path']).encode('utf-8') + b'\n', 0o600)
    path.chmod(0o600)
    return path


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


def api_diag_item(group: str, name: str, status: str, message: str, details: dict | None = None) -> dict:
    return {
        'group': group,
        'name': name,
        'status': status if status in ('ok', 'warn', 'fail') else 'warn',
        'message': message,
        'details': api_json_safe(details or {}),
    }


def api_node_diagnostics_payload() -> dict:
    checks = []

    try:
        docker_client = dc()
        docker_client.ping()
        checks.append(api_diag_item('Docker', 'Docker socket', 'ok', 'Docker API доступен'))
    except Exception as e:
        checks.append(api_diag_item('Docker', 'Docker socket', 'fail', 'Docker API недоступен', {'error': str(e)}))
        return {'ok': False, 'ts': int(time.time()), 'summary': {'ok': 0, 'warn': 0, 'fail': 1}, 'checks': checks}

    try:
        panel = docker_client.containers.get(PANEL_CONTAINER)
        status = getattr(panel, 'status', 'unknown') or 'unknown'
        checks.append(api_diag_item('Panel', PANEL_CONTAINER, 'ok' if status == 'running' else 'fail', f'Container status: {status}'))
    except Exception as e:
        checks.append(api_diag_item('Panel', PANEL_CONTAINER, 'fail', 'Контейнер панели не найден', {'error': str(e)}))

    for path, label in ((DATA_DIR, 'Data directory'), (CLIENTS_DIR, 'Clients directory'), (BACKUPS_DIR, 'Backups directory')):
        writable = path.exists() and os.access(path, os.W_OK)
        checks.append(api_diag_item('Storage', label, 'ok' if writable else 'fail', str(path), {'exists': path.exists(), 'writable': writable}))

    try:
        ips = sorted({item[4][0] for item in socket.getaddrinfo(PANEL_HOST, None)})
        checks.append(api_diag_item('Network', 'Panel DNS', 'ok', f'{PANEL_HOST} resolves', {'ips': ips}))
    except Exception as e:
        checks.append(api_diag_item('Network', 'Panel DNS', 'fail', f'{PANEL_HOST} не резолвится', {'error': str(e)}))

    try:
        ips = sorted({item[4][0] for item in socket.getaddrinfo(VPN_ENDPOINT_HOST, None)})
        checks.append(api_diag_item('Network', 'VPN endpoint DNS', 'ok', f'{VPN_ENDPOINT_HOST} resolves', {'ips': ips}))
    except Exception as e:
        checks.append(api_diag_item('Network', 'VPN endpoint DNS', 'fail', f'{VPN_ENDPOINT_HOST} не резолвится', {'error': str(e)}))

    caddy_found = False
    try:
        for container in docker_client.containers.list(all=True):
            name = (container.name or '').lower()
            if 'caddy' in name:
                caddy_found = True
                status = getattr(container, 'status', 'unknown') or 'unknown'
                checks.append(api_diag_item('Reverse proxy', container.name, 'ok' if status == 'running' else 'warn', f'Container status: {status}'))
        if not caddy_found:
            checks.append(api_diag_item('Reverse proxy', 'Caddy', 'warn', 'Caddy container не найден. Если reverse proxy стоит на host/systemd, это нормально.'))
    except Exception as e:
        checks.append(api_diag_item('Reverse proxy', 'Caddy', 'warn', 'Не удалось проверить Caddy', {'error': str(e)}))

    for protocol, p in PROTOCOLS.items():
        title = p['title']
        container = None
        try:
            container = docker_client.containers.get(p['container'])
            status = getattr(container, 'status', 'unknown') or 'unknown'
            checks.append(api_diag_item(title, 'Container', 'ok' if status == 'running' else 'fail', f"{p['container']}: {status}"))
        except Exception as e:
            checks.append(api_diag_item(title, 'Container', 'fail', f"Контейнер {p['container']} не найден", {'error': str(e)}))
            continue

        try:
            config_test = exec_c(p['container'], ['sh', '-lc', f"test -f {shlex.quote(p['config_path'])} && echo ok || echo missing"], check=False)
            checks.append(api_diag_item(title, 'Config path', 'ok' if config_test.strip() == 'ok' else 'fail', p['config_path']))
        except Exception as e:
            checks.append(api_diag_item(title, 'Config path', 'fail', 'Не удалось проверить config path', {'error': str(e)}))

        try:
            raw = exec_c(p['container'], [p['tool'], 'show', p['interface']], check=True)
            checks.append(api_diag_item(title, f"{p['tool']} show", 'ok', f"Interface {p['interface']} отвечает", {'output_head': raw[:400]}))
        except Exception as e:
            checks.append(api_diag_item(title, f"{p['tool']} show", 'fail', f"Interface {p['interface']} не отвечает", {'error': str(e)}))

        try:
            listen_port = interface_listen_port(protocol)
            published_port = docker_published_udp_port(protocol)
            ports = (container.attrs.get('NetworkSettings') or {}).get('Ports') or {}
            bindings = {k: v for k, v in ports.items() if str(k).endswith('/udp')}
            status = 'ok' if str(published_port).strip() else 'warn'
            checks.append(api_diag_item(title, 'UDP endpoint', status, f"{VPN_ENDPOINT_HOST}:{published_port}", {'listen_port': listen_port, 'configured_port': p['port'], 'bindings': bindings, 'vpn_egress_ip': VPN_EGRESS_IP}))
        except Exception as e:
            checks.append(api_diag_item(title, 'UDP endpoint', 'warn', 'Не удалось определить published UDP port', {'error': str(e)}))

    summary = {
        'ok': sum(1 for item in checks if item['status'] == 'ok'),
        'warn': sum(1 for item in checks if item['status'] == 'warn'),
        'fail': sum(1 for item in checks if item['status'] == 'fail'),
    }
    return {'ok': summary['fail'] == 0, 'ts': int(time.time()), 'summary': summary, 'checks': checks}


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


def api_parse_expires_at(value) -> int | None:
    if value in (None, '', False):
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Некорректный срок действия peer')
    if ts <= 0:
        return None
    if ts < int(time.time()) - 86400:
        raise HTTPException(status_code=400, detail='Срок действия уже в прошлом')
    return ts


def api_parse_user_expires_at(value) -> int | None:
    ts = api_parse_expires_at(value)
    if not ts:
        return None
    if ts > int(time.time()) + 366 * 86400:
        raise HTTPException(status_code=400, detail='Срок пользователя не может быть больше 1 года')
    return ts


def api_parse_traffic_limit(value) -> int:
    if value in (None, '', False):
        return 0
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Некорректный лимит трафика')
    if limit < 0:
        raise HTTPException(status_code=400, detail='Лимит трафика не может быть отрицательным')
    return limit


def api_expiration_payload(expires_at: int | None, enabled: bool) -> dict:
    if not expires_at:
        return {'enabled': False, 'expires_at': None, 'expired': False, 'seconds_left': None, 'label': 'без срока'}
    now = int(time.time())
    seconds_left = int(expires_at) - now
    expired = seconds_left <= 0
    if expired:
        label = 'истек'
    elif seconds_left < 86400:
        label = f"истекает через {max(1, seconds_left // 3600)} ч"
    else:
        label = f"истекает через {max(1, seconds_left // 86400)} д"
    return {
        'enabled': True,
        'expires_at': int(expires_at),
        'expired': expired,
        'seconds_left': seconds_left,
        'label': label,
        'active': enabled and not expired,
    }


def api_traffic_limit_payload(limit_bytes: int, live_peer: dict | None, counter: dict | None = None) -> dict:
    limit = max(0, int(limit_bytes or 0))
    rx = int((live_peer or {}).get('rx') or 0)
    tx = int((live_peer or {}).get('tx') or 0)
    if counter:
        rx = int(counter.get('rx_total') or 0)
        tx = int(counter.get('tx_total') or 0)
    used = rx + tx
    if limit <= 0:
        return {'enabled': False, 'limit_bytes': 0, 'used_bytes': used, 'rx_bytes': rx, 'tx_bytes': tx, 'remaining_bytes': None, 'percent': 0, 'exceeded': False, 'label': 'без лимита'}
    remaining = max(0, limit - used)
    percent = min(100, round((used / limit) * 100, 1)) if limit else 0
    return {
        'enabled': True,
        'limit_bytes': limit,
        'used_bytes': used,
        'rx_bytes': rx,
        'tx_bytes': tx,
        'remaining_bytes': remaining,
        'percent': percent,
        'exceeded': used >= limit,
        'label': f"{human_bytes(used)} / {human_bytes(limit)}",
    }


def api_user_traffic_totals(user_id: int) -> dict:
    with db() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(pt.rx_total), 0) AS rx_total,
                COALESCE(SUM(pt.tx_total), 0) AS tx_total
            FROM clients c
            LEFT JOIN peer_traffic_counters pt ON pt.client_id = c.id
            WHERE COALESCE(c.deleted_at, 0) = 0
              AND c.owner_id = ?
            """,
            (int(user_id),),
        ).fetchone()
    return {
        'rx_total': int(row['rx_total'] or 0),
        'tx_total': int(row['tx_total'] or 0),
    }


def api_user_traffic_limit_payload(user_id: int, limit_bytes: int) -> dict:
    return api_traffic_limit_payload(limit_bytes, None, api_user_traffic_totals(user_id))


def api_disable_expired_peers() -> int:
    now = int(time.time())
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, protocol, public_key, ip_cidr, expires_at
            FROM clients
            WHERE COALESCE(deleted_at, 0) = 0
              AND enabled = 1
              AND expires_at IS NOT NULL
              AND expires_at > 0
              AND expires_at <= ?
            """,
            (now,),
        ).fetchall()
    for row in rows:
        try:
            remove_peer(row['protocol'], row['public_key'])
            with db() as conn:
                conn.execute('UPDATE clients SET enabled = 0 WHERE id = ?', (int(row['id']),))
                conn.commit()
            api_audit_log(
                None,
                {'username': 'system', 'role': 'system', 'is_admin': True},
                'peer.expire',
                'peer',
                int(row['id']),
                row['name'],
                {'protocol': row['protocol'], 'ip_cidr': row['ip_cidr'], 'expires_at': int(row['expires_at'])},
            )
            telegram_notify(
                "peer отключён по сроку",
                [f"{row['name']} / {row['protocol']}", f"IP: {row['ip_cidr']}"],
            )
        except Exception as e:
            print(f"Failed to auto-disable expired peer {row['id']}: {e}")
    if rows:
        runtime_cache_clear()
    return len(rows)


def api_disable_traffic_limited_peers(live: dict, counters: dict | None = None) -> int:
    counters = counters if counters is not None else api_record_peer_traffic_counters(live)
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, protocol, public_key, ip_cidr, traffic_limit_bytes
            FROM clients
            WHERE COALESCE(deleted_at, 0) = 0
              AND enabled = 1
              AND traffic_limit_bytes > 0
            """
        ).fetchall()
    disabled = 0
    for row in rows:
        lp = (live.get(row['protocol']) or {}).get(row['public_key'])
        counter = counters.get(int(row['id'])) if counters else None
        if not lp and not counter:
            continue
        if counter:
            used = int(counter.get('rx_total') or 0) + int(counter.get('tx_total') or 0)
        else:
            used = int(lp.get('rx') or 0) + int(lp.get('tx') or 0)
        limit = int(row['traffic_limit_bytes'] or 0)
        if used < limit:
            continue
        try:
            remove_peer(row['protocol'], row['public_key'])
            with db() as conn:
                conn.execute('UPDATE clients SET enabled = 0 WHERE id = ?', (int(row['id']),))
                conn.commit()
            disabled += 1
            api_audit_log(
                None,
                {'username': 'system', 'role': 'system', 'is_admin': True},
                'peer.traffic_limit',
                'peer',
                int(row['id']),
                row['name'],
                {'protocol': row['protocol'], 'ip_cidr': row['ip_cidr'], 'used_bytes': used, 'limit_bytes': limit},
            )
            telegram_notify(
                "peer отключён по лимиту трафика",
                [f"{row['name']} / {row['protocol']}", f"Использовано: {human_bytes(used)} из {human_bytes(limit)}"],
            )
        except Exception as e:
            print(f"Failed to auto-disable traffic-limited peer {row['id']}: {e}")
    if disabled:
        runtime_cache_clear()
    return disabled


def api_disable_user_traffic_limited_peers() -> int:
    with db() as conn:
        users = conn.execute(
            """
            SELECT id, username, traffic_limit_bytes
            FROM panel_users
            WHERE enabled = 1
              AND traffic_limit_bytes > 0
            """
        ).fetchall()
    disabled = 0
    for panel_user in users:
        limit = int(panel_user['traffic_limit_bytes'] or 0)
        traffic = api_user_traffic_limit_payload(int(panel_user['id']), limit)
        if not traffic['exceeded']:
            continue
        with db() as conn:
            peers = conn.execute(
                """
                SELECT id, name, protocol, public_key, ip_cidr
                FROM clients
                WHERE COALESCE(deleted_at, 0) = 0
                  AND enabled = 1
                  AND owner_id = ?
                """,
                (int(panel_user['id']),),
            ).fetchall()
        user_disabled = 0
        for row in peers:
            try:
                remove_peer(row['protocol'], row['public_key'])
                with db() as conn:
                    conn.execute('UPDATE clients SET enabled = 0 WHERE id = ?', (int(row['id']),))
                    conn.commit()
                disabled += 1
                user_disabled += 1
            except Exception as e:
                print(f"Failed to auto-disable user traffic-limited peer {row['id']}: {e}")
        if user_disabled:
            api_audit_log(
                None,
                {'username': 'system', 'role': 'system', 'is_admin': True},
                'user.traffic_limit',
                'panel_user',
                int(panel_user['id']),
                panel_user['username'],
                {
                    'disabled_peers': user_disabled,
                    'used_bytes': traffic['used_bytes'],
                    'limit_bytes': limit,
                },
            )
            telegram_notify(
                "пользователь превысил лимит трафика",
                [
                    f"Пользователь: {panel_user['username']}",
                    f"Отключено peer'ов: {user_disabled}",
                    f"Использовано: {human_bytes(traffic['used_bytes'])} из {human_bytes(limit)}",
                ],
            )
    if disabled:
        runtime_cache_clear()
    return disabled


def api_error(message: str, status_code: int = 400, **extra):
    payload = {'ok': False, 'error': message}
    payload.update(extra)
    return JSONResponse(payload, status_code=status_code)


def telegram_enabled() -> bool:
    value = panel_setting_get("telegram_enabled")
    if value is None:
        return TELEGRAM_ENABLED
    return value == "1"


def telegram_bot_token() -> str:
    return panel_setting_get("telegram_bot_token", TELEGRAM_BOT_TOKEN) or ""


def telegram_chat_id() -> str:
    return panel_setting_get("telegram_chat_id", TELEGRAM_CHAT_ID) or ""


def telegram_token_suffix() -> str:
    token = telegram_bot_token()
    return token[-6:] if token else ""


def telegram_configured() -> bool:
    return bool(telegram_bot_token() and telegram_chat_id())


def telegram_status_payload() -> dict:
    return {
        "ok": True,
        "enabled": telegram_enabled(),
        "configured": telegram_configured(),
        "chat_id": telegram_chat_id(),
        "token_suffix": telegram_token_suffix(),
        "env_token_present": bool(TELEGRAM_BOT_TOKEN),
        "env_chat_present": bool(TELEGRAM_CHAT_ID),
        "db_token_present": bool(panel_setting_get("telegram_bot_token", "")),
        "db_chat_present": bool(panel_setting_get("telegram_chat_id", "")),
    }


def telegram_send_message(title: str, lines: list[str] | None = None) -> bool:
    if not telegram_enabled() or not telegram_configured():
        return False
    text_lines = [f"3WG Core: {title}"]
    for line in lines or []:
        clean = str(line).strip()
        if clean:
            text_lines.append(clean)
    payload = json.dumps({
        "chat_id": telegram_chat_id(),
        "text": "\n".join(text_lines),
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{telegram_bot_token()}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=7) as resp:
            return 200 <= int(resp.status) < 300
    except Exception as e:
        print(f"Telegram notify failed: {e}")
        return False


def telegram_notify(title: str, lines: list[str] | None = None, wait: bool = False) -> bool:
    if wait:
        return telegram_send_message(title, lines)
    if not telegram_enabled() or not telegram_configured():
        return False
    threading.Thread(target=telegram_send_message, args=(title, lines), daemon=True).start()
    return True


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
            'panel_host': PANEL_HOST,
            'endpoint_host': VPN_ENDPOINT_HOST,
            'legacy_endpoint_host': ENDPOINT_HOST,
            'vpn_egress_ip': VPN_EGRESS_IP,
            'endpoint': f"{VPN_ENDPOINT_HOST}:{endpoint_port}",
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


def api_record_peer_traffic_counters(live: dict | None = None) -> dict[int, dict]:
    live = live if live is not None else api_live_maps()[0]
    now = int(time.time())
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, protocol, public_key
            FROM clients
            WHERE COALESCE(deleted_at, 0) = 0
            """
        ).fetchall()
        for row in rows:
            lp = (live.get(row['protocol']) or {}).get(row['public_key'])
            if not lp:
                continue
            rx = int(lp.get('rx') or 0)
            tx = int(lp.get('tx') or 0)
            current = conn.execute(
                'SELECT * FROM peer_traffic_counters WHERE client_id = ?',
                (int(row['id']),),
            ).fetchone()
            if current:
                last_rx = int(current['last_rx'] or 0)
                last_tx = int(current['last_tx'] or 0)
                rx_delta = rx - last_rx if rx >= last_rx else rx
                tx_delta = tx - last_tx if tx >= last_tx else tx
                conn.execute(
                    """
                    UPDATE peer_traffic_counters
                    SET protocol = ?, public_key = ?, rx_total = rx_total + ?, tx_total = tx_total + ?,
                        last_rx = ?, last_tx = ?, updated_at = ?
                    WHERE client_id = ?
                    """,
                    (row['protocol'], row['public_key'], max(0, rx_delta), max(0, tx_delta), rx, tx, now, int(row['id'])),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO peer_traffic_counters(client_id, protocol, public_key, rx_total, tx_total, last_rx, last_tx, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (int(row['id']), row['protocol'], row['public_key'], rx, tx, rx, tx, now),
                )
        conn.commit()
        counters = conn.execute('SELECT * FROM peer_traffic_counters').fetchall()
    return {
        int(row['client_id']): {
            'client_id': int(row['client_id']),
            'protocol': row['protocol'],
            'public_key': row['public_key'],
            'rx_total': int(row['rx_total']),
            'tx_total': int(row['tx_total']),
            'last_rx': int(row['last_rx']),
            'last_tx': int(row['last_tx']),
            'updated_at': int(row['updated_at']),
        }
        for row in counters
    }


def api_traffic_history_payload(protocol: str, days: int = 30) -> dict:
    if protocol not in PROTOCOLS:
        raise HTTPException(status_code=404, detail='Unknown protocol')
    days = max(1, min(int(days or 30), 90))
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
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
    traffic_limit_bytes = int(row['traffic_limit_bytes']) if 'traffic_limit_bytes' in row.keys() and row['traffic_limit_bytes'] else 0
    traffic_limit = api_user_traffic_limit_payload(int(row['id']), traffic_limit_bytes)
    expires_at = int(row['expires_at']) if 'expires_at' in row.keys() and row['expires_at'] else None
    return {
        'id': int(row['id']),
        'username': row['username'],
        'role': row['role'],
        'peer_limit': int(row['peer_limit']),
        'peers_used': int(count),
        'traffic_limit_bytes': traffic_limit_bytes,
        'traffic_limit': traffic_limit,
        'expires_at': expires_at,
        'expiration': api_expiration_payload(expires_at, bool(row['enabled'])),
        'enabled': bool(row['enabled']),
        'created_at': int(row['created_at']),
    }


def api_panel_users_payload() -> list[dict]:
    with db() as conn:
        rows = conn.execute('SELECT * FROM panel_users ORDER BY id DESC').fetchall()
    return [api_panel_user_payload(row) for row in rows]


def api_peer_payload(c, live: dict | None = None, include_config: bool = False, counters: dict | None = None) -> dict:
    protocol = c['protocol']
    p = PROTOCOLS[protocol]
    endpoint = client_endpoint(protocol)
    lp = live.get(protocol, {}).get(c['public_key']) if live else None
    active, handshake_age = api_recent_handshake(lp)
    enabled = bool(c['enabled'])
    expires_at = int(c['expires_at']) if 'expires_at' in c.keys() and c['expires_at'] else None
    expiration = api_expiration_payload(expires_at, enabled)
    traffic_limit_bytes = int(c['traffic_limit_bytes']) if 'traffic_limit_bytes' in c.keys() and c['traffic_limit_bytes'] else 0
    counter = counters.get(int(c['id'])) if counters else None
    traffic_limit = api_traffic_limit_payload(traffic_limit_bytes, lp, counter)
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
        'note': c['note'] if 'note' in c.keys() and c['note'] else '',
        'ip_cidr': c['ip_cidr'],
        'public_key': c['public_key'],
        'enabled': enabled,
        'created_at': int(c['created_at']),
        'expires_at': expires_at,
        'expiration': expiration,
        'traffic_limit_bytes': traffic_limit_bytes,
        'traffic_limit': traffic_limit,
        'traffic_counter': counter,
        'deleted_at': int(c['deleted_at']) if 'deleted_at' in c.keys() else 0,
        'endpoint': endpoint,
        'status': 'limited' if traffic_limit['exceeded'] else ('expired' if expiration['expired'] else ('active' if enabled and active else ('offline' if enabled else 'disabled'))),
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
            'traffic_reset': f"/api/peers/{c['id']}/traffic-reset",
            'delete': f"/api/peers/{c['id']}",
        },
    }
    if include_config:
        payload['config'] = read_conf(c)
    return payload


def api_check_payload(status: str, name: str, message: str, details: dict | None = None) -> dict:
    return {'status': status, 'name': name, 'message': message, 'details': details or {}}


def api_peer_diagnostics_payload(c) -> dict:
    live, errors = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    peer = api_peer_payload(c, live=live, include_config=False, counters=counters)
    protocol = c['protocol']
    p = PROTOCOLS[protocol]
    lp = (live.get(protocol) or {}).get(c['public_key'])
    active, handshake_age = api_recent_handshake(lp)
    checks = []

    protocol_state = api_protocol_state(protocol)
    if protocol_state.get('available'):
        checks.append(api_check_payload('ok', 'Protocol interface', f"{p['title']} доступен: {p['container']} / {p['interface']}", protocol_state))
    else:
        checks.append(api_check_payload('fail', 'Protocol interface', protocol_state.get('reason') or 'protocol unavailable', protocol_state))

    try:
        container = dc().containers.get(p['container'])
        status = getattr(container, 'status', 'unknown') or 'unknown'
        checks.append(api_check_payload('ok' if status == 'running' else 'fail', 'Docker container', f"{p['container']} status: {status}", {'container': p['container'], 'status': status}))
    except Exception as exc:
        checks.append(api_check_payload('fail', 'Docker container', str(exc), {'container': p['container']}))

    config_path = Path(c['config_path'])
    if config_path.exists():
        checks.append(api_check_payload('ok', 'Client config file', str(config_path), {'path': str(config_path), 'size': config_path.stat().st_size}))
    else:
        checks.append(api_check_payload('fail', 'Client config file', f"Файл не найден: {config_path}", {'path': str(config_path)}))

    if lp:
        checks.append(api_check_payload('ok', 'Peer in live interface', 'Peer найден в live выводе контейнера', {'public_key': short_key(c['public_key']), 'endpoint': lp.get('endpoint')}))
    elif peer.get('enabled'):
        checks.append(api_check_payload('fail', 'Peer in live interface', 'Peer включён в панели, но не найден в live-интерфейсе', {'public_key': short_key(c['public_key'])}))
    else:
        checks.append(api_check_payload('warn', 'Peer in live interface', 'Peer отключён, поэтому в live-интерфейсе может отсутствовать', {'public_key': short_key(c['public_key'])}))

    if not peer.get('enabled'):
        checks.append(api_check_payload('warn', 'Access state', 'Peer отключён администратором', {'enabled': False}))
    elif peer.get('expiration', {}).get('expired'):
        checks.append(api_check_payload('fail', 'Access state', 'Срок действия peer истёк', peer.get('expiration')))
    elif peer.get('traffic_limit', {}).get('exceeded'):
        checks.append(api_check_payload('fail', 'Access state', 'Лимит трафика peer исчерпан', peer.get('traffic_limit')))
    else:
        checks.append(api_check_payload('ok', 'Access state', 'Peer разрешён к подключению', {'status': peer.get('status')}))

    endpoint = (lp or {}).get('endpoint')
    if endpoint and endpoint != '(none)':
        checks.append(api_check_payload('ok', 'Client endpoint', endpoint, {'endpoint': endpoint}))
    elif active:
        checks.append(api_check_payload('warn', 'Client endpoint', 'Handshake есть, endpoint не определён', {'endpoint': endpoint or '(none)'}))
    else:
        checks.append(api_check_payload('warn', 'Client endpoint', 'Клиент ещё не подключался или endpoint пустой', {'endpoint': endpoint or '(none)'}))

    if active:
        checks.append(api_check_payload('ok', 'Handshake freshness', f"Последний handshake {handshake_age} сек. назад", {'age_seconds': handshake_age, 'window_seconds': ONLINE_HANDSHAKE_WINDOW_SECONDS}))
    elif handshake_age is not None:
        checks.append(api_check_payload('warn', 'Handshake freshness', f"Handshake был {handshake_age} сек. назад, сейчас не считаем online", {'age_seconds': handshake_age, 'window_seconds': ONLINE_HANDSHAKE_WINDOW_SECONDS}))
    else:
        checks.append(api_check_payload('warn', 'Handshake freshness', 'Handshake ещё не зафиксирован', {'age_seconds': None}))

    rx = int((lp or {}).get('rx') or 0)
    tx = int((lp or {}).get('tx') or 0)
    if rx or tx:
        checks.append(api_check_payload('ok', 'Traffic counters', f"RX {human_bytes(rx)} / TX {human_bytes(tx)}", {'rx': rx, 'tx': tx}))
    else:
        checks.append(api_check_payload('warn', 'Traffic counters', 'Трафика пока нет', {'rx': rx, 'tx': tx}))

    if errors:
        checks.append(api_check_payload('warn', 'Live map errors', '; '.join(errors[:3]), {'errors': errors}))

    summary = {
        'ok': sum(1 for item in checks if item['status'] == 'ok'),
        'warn': sum(1 for item in checks if item['status'] == 'warn'),
        'fail': sum(1 for item in checks if item['status'] == 'fail'),
    }
    return {'ok': True, 'peer': peer, 'summary': summary, 'checks': checks, 'checked_at': int(time.time())}


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


@app.get('/api/update/status')
def api_update_status(user=Depends(api_require_admin)):
    return update_status_payload()


@app.post('/api/update/run')
async def api_update_run(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    runner = update_runner_payload()
    if not runner['can_run']:
        return api_error(runner['reason'], status_code=409, runner=runner)
    job = update_job_payload()
    if job.get("running"):
        return api_error('Update уже выполняется', status_code=409, job=update_job_payload())
    if str(data.get('confirm', '')).strip() != runner['confirm_text']:
        return api_error(f"Для запуска нужно подтверждение {runner['confirm_text']}", status_code=400)
    backup = api_create_backup_archive('pre-ui-update')
    api_audit_log(request, user, 'update.start', 'update', 'runner', 'host', {'backup': backup.name, 'runner': runner})
    try:
        update_runner_request('run', actor=user.get('username'), backup=backup.name)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as e:
        api_audit_log(request, user, 'update.error', 'update', 'runner', 'host', {'error': str(e), 'backup': backup.name})
        return api_error(f'Не удалось запустить updater: {e}', status_code=502, runner=runner)
    return update_status_payload()


@app.get('/api/node/protocols')
def api_node_protocols(user=Depends(api_require_auth)):
    return {
        'ok': True,
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'legacy_endpoint_host': ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'fornex_vpn_ports': FORNEX_VPN_PORTS,
        'protocols': {protocol: api_protocol_state(protocol) for protocol in PROTOCOLS},
    }


@app.get('/api/node/protocols/ports')
def api_node_protocol_ports(user=Depends(api_require_admin)):
    return {
        'ok': True,
        'fornex_vpn_ports': FORNEX_VPN_PORTS,
        'recommendations': {
            'wireguard': 'Для Fornex используйте порт из разрешенного списка, например 1144/udp, если он свободен.',
            'amneziawg': 'Для AmneziaWG обычно лучше 443/udp, если на сервере он не занят другим UDP-сервисом.',
        },
    }


@app.patch('/api/node/protocols/{protocol}/port')
async def api_node_protocol_port_update(protocol: str, request: Request, user=Depends(api_require_admin)):
    proto(protocol)
    data = await api_read_payload(request)
    port = valid_udp_port(data.get('port'))
    if str(data.get('confirm', '')).strip().upper() != 'PORT':
        return api_error('Для смены порта введите подтверждение PORT', status_code=400)
    before = api_protocol_state(protocol)
    try:
        result = change_protocol_port(protocol, port)
    except HTTPException:
        raise
    except (docker.errors.APIError, docker.errors.NotFound, RuntimeError, OSError, ValueError) as e:
        api_audit_log(request, user, 'protocol.port.error', 'protocol', protocol, 'host', {'port': port, 'error': str(e)})
        return api_error(f'Не удалось сменить UDP порт: {e}', status_code=502)
    after = api_protocol_state(protocol)
    api_audit_log(
        request,
        user,
        'protocol.port.update',
        'protocol',
        protocol,
        'host',
        {'from': before.get('port'), 'to': port, 'changed': bool(result.get('changed'))},
    )
    telegram_notify(
        f"3WG Core: {user.get('username')} изменил UDP порт {after.get('title')}: "
        f"{before.get('port')} -> {after.get('port')}"
    )
    return {
        'ok': True,
        'result': result,
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'legacy_endpoint_host': ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'fornex_vpn_ports': FORNEX_VPN_PORTS,
        'protocols': {key: api_protocol_state(key) for key in PROTOCOLS},
    }


@app.get('/api/node/status')
def api_node_status(user=Depends(api_require_auth)):
    live, errors = api_live_maps()
    with db() as conn:
        total = conn.execute('SELECT COUNT(*) AS n FROM clients WHERE COALESCE(deleted_at, 0) = 0').fetchone()['n']
    return {
        'ok': True,
        'panel_host': PANEL_HOST,
        'endpoint_host': VPN_ENDPOINT_HOST,
        'legacy_endpoint_host': ENDPOINT_HOST,
        'vpn_egress_ip': VPN_EGRESS_IP,
        'fornex_vpn_ports': FORNEX_VPN_PORTS,
        'dns_servers': DNS_SERVERS,
        'clients_total': int(total),
        'peers_total': sum(len(pm) for pm in live.values()),
        'peers_online': sum(1 for pm in live.values() for x in pm.values() if x.get('endpoint') != '(none)'),
        'protocols': {protocol: api_protocol_state(protocol, include_raw=True) for protocol in PROTOCOLS},
        'errors': errors,
    }


@app.get('/api/node/diagnostics')
def api_node_diagnostics(user=Depends(api_require_admin)):
    return api_node_diagnostics_payload()


@app.get('/api/peers')
def api_peers(user=Depends(api_require_auth)):
    expired_disabled = api_disable_expired_peers()
    live, errors = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    traffic_limited_disabled = api_disable_traffic_limited_peers(live, counters)
    user_traffic_limited_disabled = api_disable_user_traffic_limited_peers()
    if traffic_limited_disabled or user_traffic_limited_disabled:
        live, errors = api_live_maps()
        counters = api_record_peer_traffic_counters(live)
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
        'peers': [api_peer_payload(c, live=live, counters=counters) for c in rows],
        'categories': api_categories_payload() if user.get('is_admin') else [],
        'quota': api_user_quota(user),
        'errors': errors,
        'expired_disabled': expired_disabled,
        'traffic_limited_disabled': traffic_limited_disabled,
        'user_traffic_limited_disabled': user_traffic_limited_disabled,
    }


@app.get('/api/categories')
def api_categories(user=Depends(api_require_auth)):
    if not user.get('is_admin'):
        return {'ok': True, 'categories': []}
    return {'ok': True, 'categories': api_categories_payload()}


@app.get('/api/users')
def api_users(user=Depends(api_require_admin)):
    live, _errors = api_live_maps()
    api_record_peer_traffic_counters(live)
    api_disable_user_traffic_limited_peers()
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
    api_maybe_run_auto_backup()
    return {'ok': True, 'backups': api_list_backups(), 'auto': api_auto_backup_settings()}


@app.post('/api/backups')
async def api_backups_create(request: Request, user=Depends(api_require_admin)):
    path = api_create_backup_archive('manual')
    payload = api_backup_payload(path)
    api_audit_log(request, user, 'backup.create', 'backup', path.name, path.name, {'size': payload['size']})
    telegram_notify(
        "backup создан",
        [f"Файл: {path.name}", f"Размер: {human_bytes(payload['size'])}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'backup': payload, 'backups': api_list_backups(), 'auto': api_auto_backup_settings()}


@app.post('/api/backups/auto')
async def api_backups_auto_update(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    try:
        settings = api_auto_backup_settings()
        settings.update({
            'enabled': bool(data.get('enabled')),
            'interval_hours': int(data.get('interval_hours', settings['interval_hours'])),
            'keep_last': int(data.get('keep_last', settings['keep_last'])),
        })
        saved = api_save_auto_backup_settings(settings)
    except (TypeError, ValueError):
        return api_error('Некорректные настройки auto backup', status_code=400)
    deleted = api_prune_auto_backups(saved['keep_last'])
    result = api_maybe_run_auto_backup(force=bool(data.get('run_now')))
    if result:
        saved = result['auto']
        deleted.extend(result.get('deleted') or [])
    api_audit_log(
        request,
        user,
        'backup.auto.update',
        'backup',
        'auto',
        'auto backup',
        {'settings': saved, 'pruned': deleted},
    )
    return {'ok': True, 'auto': saved, 'deleted': deleted, 'backups': api_list_backups()}


@app.get('/api/backups/{name}/download')
def api_backups_download(name: str, user=Depends(api_require_admin)):
    path = api_backup_path(name)
    return FileResponse(path, filename=path.name, media_type='application/gzip')


@app.delete('/api/backups/{name}')
async def api_backups_delete(name: str, request: Request, user=Depends(api_require_admin)):
    path = api_backup_path(name)
    payload = api_backup_payload(path)
    path.unlink()
    api_audit_log(request, user, 'backup.delete', 'backup', payload['name'], payload['name'], {'size': payload['size']})
    telegram_notify(
        "backup удалён",
        [f"Файл: {payload['name']}", f"Размер: {human_bytes(payload['size'])}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'deleted': payload['name'], 'backups': api_list_backups(), 'auto': api_auto_backup_settings()}


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
    return {
        'ok': True,
        'restored': path.name,
        'pre_restore_backup': api_backup_payload(pre_restore),
        'backups': api_list_backups(),
        'auto': api_auto_backup_settings(),
    }


@app.get('/api/migration')
def api_migration_list(user=Depends(api_require_admin)):
    return {'ok': True, 'bundles': api_list_migration_bundles()}


@app.post('/api/migration/export')
async def api_migration_export(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    include_backups = bool(data.get('include_backups'))
    path = api_create_migration_bundle(include_backups=include_backups)
    payload = api_migration_payload(path)
    api_audit_log(request, user, 'migration.export', 'migration', path.name, path.name, {'size': payload['size'], 'include_backups': include_backups})
    telegram_notify(
        "migration bundle создан",
        [f"Файл: {path.name}", f"Размер: {human_bytes(payload['size'])}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'bundle': payload, 'bundles': api_list_migration_bundles()}


@app.get('/api/migration/push')
def api_migration_push_status(user=Depends(api_require_admin)):
    return {'ok': True, 'runner': migration_runner_payload(), 'job': migration_job_payload()}


@app.post('/api/migration/push')
async def api_migration_push(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    archive = api_migration_path(str(data.get('archive') or ''))
    if str(data.get('confirm') or '').strip() != 'MIGRATE':
        raise HTTPException(status_code=400, detail='Для запуска введите MIGRATE')
    auth_method = str(data.get('auth_method') or 'password').strip()
    if auth_method not in ('password', 'key'):
        raise HTTPException(status_code=400, detail='Некорректный SSH auth method')
    payload = {
        'host': str(data.get('host') or '').strip(),
        'user': str(data.get('user') or 'root').strip() or 'root',
        'port': data.get('port') or 22,
        'auth_method': auth_method,
        'password': str(data.get('password') or ''),
        'private_key': str(data.get('private_key') or ''),
        'archive': archive.name,
        'install_dir': str(data.get('install_dir') or '/opt/3wg-panel').strip() or '/opt/3wg-panel',
        'repo_url': str(data.get('repo_url') or 'https://github.com/dblack-adminix/3wg-panel.git').strip(),
        'branch': str(data.get('branch') or 'dev').strip() or 'dev',
    }
    try:
        response = migration_runner_request('push', **payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    api_audit_log(
        request,
        user,
        'migration.push',
        'migration',
        archive.name,
        archive.name,
        {
            'host': payload['host'],
            'user': payload['user'],
            'port': payload['port'],
            'auth_method': auth_method,
            'archive': archive.name,
            'install_dir': payload['install_dir'],
            'repo_url': payload['repo_url'],
            'branch': payload['branch'],
        },
    )
    telegram_notify(
        "migration push запущен",
        [f"Target: {payload['user']}@{payload['host']}:{payload['port']}", f"Файл: {archive.name}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'runner': migration_runner_payload(), 'job': response.get('job') or migration_job_payload()}


@app.get('/api/migration/{name}/download')
def api_migration_download(name: str, user=Depends(api_require_admin)):
    path = api_migration_path(name)
    return FileResponse(path, filename=path.name, media_type='application/gzip')


@app.delete('/api/migration/{name}')
async def api_migration_delete(name: str, request: Request, user=Depends(api_require_admin)):
    path = api_migration_path(name)
    payload = api_migration_payload(path)
    path.unlink()
    api_audit_log(request, user, 'migration.delete', 'migration', payload['name'], payload['name'], {'size': payload['size']})
    return {'ok': True, 'deleted': payload['name'], 'bundles': api_list_migration_bundles()}


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
    try:
        traffic_limit_bytes = api_parse_traffic_limit(data.get('traffic_limit_bytes'))
        expires_at = api_parse_user_expires_at(data.get('expires_at'))
    except HTTPException as e:
        return api_error(str(e.detail), status_code=e.status_code)
    if not username:
        return api_error('Пустой логин', status_code=400)
    if username == PANEL_USER:
        return api_error('Этот логин занят системным администратором', status_code=409)
    if len(password) < 6:
        return api_error('Пароль должен быть не короче 6 символов', status_code=400)
    try:
        with db() as conn:
            conn.execute(
                'INSERT INTO panel_users(username, password_hash, role, peer_limit, traffic_limit_bytes, expires_at, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)',
                (username, password_hash(password), role, peer_limit, traffic_limit_bytes, expires_at, int(time.time())),
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
        {'role': role, 'peer_limit': peer_limit, 'traffic_limit_bytes': traffic_limit_bytes, 'expires_at': expires_at},
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
    if 'traffic_limit_bytes' in data:
        try:
            fields.append('traffic_limit_bytes = ?')
            values.append(api_parse_traffic_limit(data.get('traffic_limit_bytes')))
        except HTTPException as e:
            return api_error(str(e.detail), status_code=e.status_code)
    if 'expires_at' in data:
        try:
            fields.append('expires_at = ?')
            values.append(api_parse_user_expires_at(data.get('expires_at')))
        except HTTPException as e:
            return api_error(str(e.detail), status_code=e.status_code)
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
        before = conn.execute('SELECT id, username, role, peer_limit, traffic_limit_bytes, expires_at, enabled FROM panel_users WHERE id = ?', (user_id,)).fetchone()
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
        row = conn.execute('SELECT id, username, role, peer_limit, traffic_limit_bytes, enabled FROM panel_users WHERE id = ?', (user_id,)).fetchone()
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
            expires_at = api_parse_expires_at(data.get('expires_at'))
            traffic_limit_bytes = api_parse_traffic_limit(data.get('traffic_limit_bytes'))
        except HTTPException as e:
            return api_error(str(e.detail), status_code=e.status_code)
    else:
        expires_at = None
        traffic_limit_bytes = 0
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
            created_ids.append(create_client(name, protocol, category_id=category_id, owner_id=user.get('id'), expires_at=expires_at, traffic_limit_bytes=traffic_limit_bytes))
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
            {'protocols': protocols, 'category_id': category_id, 'expires_at': expires_at, 'traffic_limit_bytes': traffic_limit_bytes},
        )
    telegram_notify(
        "создан peer",
        [
            f"Имя: {name}",
            f"Протоколы: {', '.join(protocols)}",
            f"Кто: {user.get('username')}",
        ],
    )

    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
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
    return {'ok': True, 'created_ids': created_ids, 'peers': [api_peer_payload(c, live=live, counters=counters) for c in rows]}


@app.patch('/api/peers/{client_id}')
async def api_peer_update(client_id: int, request: Request, user=Depends(api_require_auth)):
    if not user.get('is_admin'):
        return api_error('Недостаточно прав', status_code=403)
    data = await api_read_payload(request)
    try:
        category_id = api_category_id(data.get('category_id')) if 'category_id' in data else None
        expires_at = api_parse_expires_at(data.get('expires_at')) if 'expires_at' in data else None
        traffic_limit_bytes = api_parse_traffic_limit(data.get('traffic_limit_bytes')) if 'traffic_limit_bytes' in data else None
    except HTTPException as e:
        return api_error(str(e.detail), status_code=e.status_code)
    note = str(data.get('note', '')).replace('\x00', '').strip()[:500] if 'note' in data else None
    if 'category_id' not in data and 'expires_at' not in data and 'traffic_limit_bytes' not in data and 'note' not in data:
        return api_error('Нет изменений', status_code=400)
    with db() as conn:
        before = conn.execute(
            'SELECT id, name, protocol, category_id, expires_at, traffic_limit_bytes, note FROM clients WHERE id = ? AND COALESCE(deleted_at, 0) = 0',
            (client_id,),
        ).fetchone()
        if not before:
            return api_error('Клиент не найден', status_code=404)
        fields = []
        values = []
        if 'category_id' in data:
            fields.append('category_id = ?')
            values.append(category_id)
        if 'expires_at' in data:
            fields.append('expires_at = ?')
            values.append(expires_at)
        if 'traffic_limit_bytes' in data:
            fields.append('traffic_limit_bytes = ?')
            values.append(traffic_limit_bytes)
        if 'note' in data:
            fields.append('note = ?')
            values.append(note)
        values.append(client_id)
        cur = conn.execute(
            f"UPDATE clients SET {', '.join(fields)} WHERE id = ? AND COALESCE(deleted_at, 0) = 0",
            values,
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
        {
            'protocol': before['protocol'],
            'before_category_id': before['category_id'],
            'category_id': category_id if 'category_id' in data else before['category_id'],
            'before_expires_at': before['expires_at'],
            'expires_at': expires_at if 'expires_at' in data else before['expires_at'],
            'before_traffic_limit_bytes': before['traffic_limit_bytes'],
            'traffic_limit_bytes': traffic_limit_bytes if 'traffic_limit_bytes' in data else before['traffic_limit_bytes'],
            'before_note': before['note'],
            'note': note if 'note' in data else before['note'],
        },
    )
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    with db() as conn:
        c = conn.execute("""
            SELECT c.*, cat.name AS category_name, u.username AS owner_username
            FROM clients c
            LEFT JOIN categories cat ON cat.id = c.category_id
            LEFT JOIN panel_users u ON u.id = c.owner_id
            WHERE c.id = ?
        """, (client_id,)).fetchone()
    return {'ok': True, 'peer': api_peer_payload(c, live=live, counters=counters), 'categories': api_categories_payload()}


@app.get('/api/peers/{client_id}')
def api_peer_get(client_id: int, user=Depends(api_require_auth)):
    api_disable_expired_peers()
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    if api_disable_traffic_limited_peers(live, counters):
        live, _ = api_live_maps()
        counters = api_record_peer_traffic_counters(live)
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    return {'ok': True, 'peer': api_peer_payload(c, live=live, include_config=True, counters=counters)}


@app.get('/api/peers/{client_id}/diagnostics')
def api_peer_diagnostics(client_id: int, user=Depends(api_require_auth)):
    api_disable_expired_peers()
    c = load_client(client_id)
    if not user.get('is_admin') and c['owner_id'] != user.get('id'):
        raise HTTPException(status_code=404, detail='Client not found')
    return api_peer_diagnostics_payload(c)


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
    if c['expires_at'] and int(c['expires_at']) <= int(time.time()):
        return api_error('Срок действия peer истек. Продлите срок перед включением.', status_code=409)
    live, _ = api_live_maps()
    lp = (live.get(c['protocol']) or {}).get(c['public_key'])
    counters = api_record_peer_traffic_counters(live)
    if c['traffic_limit_bytes'] and api_traffic_limit_payload(int(c['traffic_limit_bytes']), lp, counters.get(int(c['id'])))['exceeded']:
        return api_error('Лимит трафика peer исчерпан. Увеличьте или снимите лимит перед включением.', status_code=409)
    try:
        enable_peer(c)
    except Exception as e:
        return api_error(str(e), status_code=500)
    api_audit_log(request, user, 'peer.enable', 'peer', client_id, c['name'], {'protocol': c['protocol'], 'ip_cidr': c['ip_cidr']})
    telegram_notify(
        "peer включён",
        [f"{c['name']} / {c['protocol']}", f"IP: {c['ip_cidr']}", f"Кто: {user.get('username')}"],
    )
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live, counters=counters)}


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
    telegram_notify(
        "peer отключён",
        [f"{c['name']} / {c['protocol']}", f"IP: {c['ip_cidr']}", f"Кто: {user.get('username')}"],
    )
    live, _ = api_live_maps()
    counters = api_record_peer_traffic_counters(live)
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live, counters=counters)}


@app.post('/api/peers/{client_id}/traffic-reset')
def api_peer_traffic_reset(client_id: int, request: Request, user=Depends(api_require_auth)):
    if not user.get('is_admin'):
        return api_error('Недостаточно прав', status_code=403)
    c = load_client(client_id)
    live, _ = api_live_maps()
    lp = (live.get(c['protocol']) or {}).get(c['public_key']) or {}
    last_rx = int(lp.get('rx') or 0)
    last_tx = int(lp.get('tx') or 0)
    now = int(time.time())
    with db() as conn:
        before = conn.execute('SELECT * FROM peer_traffic_counters WHERE client_id = ?', (client_id,)).fetchone()
        conn.execute(
            """
            INSERT INTO peer_traffic_counters(client_id, protocol, public_key, rx_total, tx_total, last_rx, last_tx, updated_at)
            VALUES (?, ?, ?, 0, 0, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                protocol = excluded.protocol,
                public_key = excluded.public_key,
                rx_total = 0,
                tx_total = 0,
                last_rx = excluded.last_rx,
                last_tx = excluded.last_tx,
                updated_at = excluded.updated_at
            """,
            (client_id, c['protocol'], c['public_key'], last_rx, last_tx, now),
        )
        conn.commit()
    api_audit_log(
        request,
        user,
        'peer.traffic_reset',
        'peer',
        client_id,
        c['name'],
        {
            'protocol': c['protocol'],
            'ip_cidr': c['ip_cidr'],
            'before_rx_total': int(before['rx_total']) if before else 0,
            'before_tx_total': int(before['tx_total']) if before else 0,
            'last_rx': last_rx,
            'last_tx': last_tx,
        },
    )
    counters = api_record_peer_traffic_counters(live)
    c = load_client(client_id)
    return {'ok': True, 'peer': api_peer_payload(c, live=live, counters=counters)}


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
    telegram_notify(
        "peer удалён",
        [f"{c['name']} / {c['protocol']}", f"IP: {c['ip_cidr']}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'deleted_id': client_id}

# === 3WG P2P GUARD API START ===
P2P_GUARD_CHAIN = '3WG-P2P-GUARD'
P2P_GUARD_DEFAULTS = {
    'enabled': False,
    'mode': 'soft',
    'allow_udp_ports': '53,123,443',
    'updated_at': 0,
}
P2P_GUARD_PORTS = '6881:6999,6969,51413,2710,4444,45100:45199'
P2P_GUARD_SIGNATURES = [
    'BitTorrent protocol',
    'announce_peer',
    'find_node',
    'get_peers',
    'info_hash',
    'peer_id=',
    'torrent',
]


def p2p_guard_settings() -> dict:
    raw = panel_setting_get('p2p_guard')
    settings = dict(P2P_GUARD_DEFAULTS)
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception:
            pass
    mode = str(settings.get('mode') or 'soft').strip().lower()
    if mode not in ('soft', 'strict'):
        mode = 'soft'
    settings['mode'] = mode
    settings['enabled'] = bool(settings.get('enabled'))
    settings['allow_udp_ports'] = p2p_guard_normalize_ports(settings.get('allow_udp_ports') or '53,123,443')
    try:
        settings['updated_at'] = int(settings.get('updated_at') or 0)
    except (TypeError, ValueError):
        settings['updated_at'] = 0
    return settings


def p2p_guard_save_settings(settings: dict) -> dict:
    clean = dict(P2P_GUARD_DEFAULTS)
    clean.update(settings or {})
    clean['enabled'] = bool(clean.get('enabled'))
    clean['mode'] = str(clean.get('mode') or 'soft').strip().lower()
    if clean['mode'] not in ('soft', 'strict'):
        clean['mode'] = 'soft'
    clean['allow_udp_ports'] = p2p_guard_normalize_ports(clean.get('allow_udp_ports') or '53,123,443')
    clean['updated_at'] = int(time.time())
    panel_setting_set('p2p_guard', json.dumps(clean, ensure_ascii=False, separators=(',', ':')))
    return p2p_guard_settings()


def p2p_guard_normalize_ports(value) -> str:
    raw = str(value or '').replace(' ', '')
    if not raw:
        return '53,123,443'
    parts = []
    for item in raw.split(','):
        if not item:
            continue
        if ':' in item or '-' in item:
            sep = ':' if ':' in item else '-'
            left, right = item.split(sep, 1)
            if not left.isdigit() or not right.isdigit():
                raise HTTPException(status_code=400, detail='Некорректный список UDP портов')
            a, b = int(left), int(right)
            if a < 1 or b > 65535 or a > b:
                raise HTTPException(status_code=400, detail='Некорректный диапазон UDP портов')
            parts.append(f'{a}:{b}')
        else:
            if not item.isdigit():
                raise HTTPException(status_code=400, detail='Некорректный список UDP портов')
            port = int(item)
            if port < 1 or port > 65535:
                raise HTTPException(status_code=400, detail='Некорректный UDP порт')
            parts.append(str(port))
    return ','.join(dict.fromkeys(parts)) or '53,123,443'


def p2p_guard_exec(protocol: str, args: list[str]) -> dict:
    p = proto(protocol)
    started = time.time()
    try:
        container = dc().containers.get(p['container'])
        result = container.exec_run(args, stdout=True, stderr=True)
        output = result.output.decode('utf-8', errors='replace') if isinstance(result.output, (bytes, bytearray)) else str(result.output or '')
        return {
            'ok': result.exit_code == 0,
            'exit_code': int(result.exit_code or 0),
            'output': output.strip(),
            'duration_ms': int((time.time() - started) * 1000),
        }
    except Exception as e:
        return {'ok': False, 'exit_code': 125, 'output': str(e), 'duration_ms': int((time.time() - started) * 1000)}


def p2p_guard_iptables(protocol: str, args: list[str], check: bool = False) -> dict:
    result = p2p_guard_exec(protocol, ['iptables', *args])
    if check and not result['ok']:
        raise RuntimeError(result.get('output') or 'iptables failed')
    return result


def p2p_guard_chain_exists(protocol: str) -> bool:
    return p2p_guard_iptables(protocol, ['-S', P2P_GUARD_CHAIN])['ok']


def p2p_guard_hook_exists(protocol: str) -> bool:
    iface = PROTOCOLS[protocol]['interface']
    in_hook = p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])['ok']
    out_hook = p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])['ok']
    return in_hook and out_hook


def p2p_guard_status_for(protocol: str) -> dict:
    p = PROTOCOLS[protocol]
    state = api_protocol_state(protocol)
    chain = p2p_guard_chain_exists(protocol)
    hook = p2p_guard_hook_exists(protocol) if chain else False
    rules = p2p_guard_iptables(protocol, ['-S', P2P_GUARD_CHAIN]) if chain else {'ok': True, 'output': ''}
    rule_lines = [line for line in (rules.get('output') or '').splitlines() if line.strip()]
    return {
        'protocol': protocol,
        'title': p['title'],
        'container': p['container'],
        'interface': p['interface'],
        'available': bool(state.get('available')),
        'chain': chain,
        'hook': hook,
        'active': chain and hook,
        'rules_count': max(0, len([line for line in rule_lines if line.startswith('-A ')])),
        'rules': rule_lines[:80],
        'error': '' if rules.get('ok', True) else rules.get('output', ''),
    }


def p2p_guard_status_payload() -> dict:
    settings = p2p_guard_settings()
    protocols = {protocol: p2p_guard_status_for(protocol) for protocol in PROTOCOLS}
    return {'ok': True, 'settings': settings, 'protocols': protocols}


def p2p_guard_rule_args(iface: str, settings: dict) -> list[list[str]]:
    rules = [
        ['-N', P2P_GUARD_CHAIN],
        ['-F', P2P_GUARD_CHAIN],
        ['-I', 'FORWARD', '1', '-i', iface, '-j', P2P_GUARD_CHAIN],
        ['-I', 'FORWARD', '1', '-o', iface, '-j', P2P_GUARD_CHAIN],
    ]
    for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'):
        rules.append(['-A', P2P_GUARD_CHAIN, '-d', cidr, '-j', 'RETURN'])
    for proto_name in ('tcp', 'udp'):
        rules.append(['-A', P2P_GUARD_CHAIN, '-p', proto_name, '-m', 'multiport', '--dports', P2P_GUARD_PORTS, '-j', 'REJECT'])
    for signature in P2P_GUARD_SIGNATURES:
        for proto_name in ('tcp', 'udp'):
            rules.append(['-A', P2P_GUARD_CHAIN, '-p', proto_name, '-m', 'string', '--algo', 'bm', '--string', signature, '-j', 'REJECT'])
    if settings.get('mode') == 'strict':
        allowed = p2p_guard_normalize_ports(settings.get('allow_udp_ports') or '53,123,443')
        rules.append(['-A', P2P_GUARD_CHAIN, '-p', 'udp', '-m', 'multiport', '--dports', allowed, '-j', 'RETURN'])
        rules.append(['-A', P2P_GUARD_CHAIN, '-p', 'udp', '-j', 'REJECT'])
    rules.append(['-A', P2P_GUARD_CHAIN, '-j', 'RETURN'])
    return rules


def p2p_guard_script_text(protocol: str, settings: dict) -> str:
    iface = PROTOCOLS[protocol]['interface']
    lines = [
        '#!/bin/sh',
        'set -u',
        f'CHAIN={shlex.quote(P2P_GUARD_CHAIN)}',
        f'IFACE={shlex.quote(iface)}',
        'iptables -N "$CHAIN" 2>/dev/null || true',
        'while iptables -C FORWARD -i "$IFACE" -j "$CHAIN" 2>/dev/null; do iptables -D FORWARD -i "$IFACE" -j "$CHAIN" || break; done',
        'while iptables -C FORWARD -o "$IFACE" -j "$CHAIN" 2>/dev/null; do iptables -D FORWARD -o "$IFACE" -j "$CHAIN" || break; done',
        'iptables -F "$CHAIN"',
    ]
    for args in p2p_guard_rule_args(iface, settings):
        if args[0] in ('-N', '-F'):
            continue
        lines.append('iptables ' + ' '.join(shlex.quote(arg) for arg in args))
    return '\n'.join(lines) + '\n'


def p2p_guard_install_script(protocol: str, settings: dict) -> None:
    p = proto(protocol)
    container = dc().containers.get(p['container'])
    put_container_text_file(container, '/opt/amnezia/3wg-p2p-guard.sh', p2p_guard_script_text(protocol, settings), mode=0o755)
    ensure_protocol_autostart(protocol)


def p2p_guard_remove_script(protocol: str) -> None:
    p2p_guard_exec(protocol, ['sh', '-lc', 'rm -f /opt/amnezia/3wg-p2p-guard.sh'])
    try:
        ensure_protocol_autostart(protocol)
    except Exception:
        pass


def p2p_guard_reset_protocol(protocol: str) -> dict:
    iface = PROTOCOLS[protocol]['interface']
    # Delete all matching hooks; Docker/container restarts can occasionally leave duplicates.
    while p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])['ok']:
        p2p_guard_iptables(protocol, ['-D', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])
    while p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])['ok']:
        p2p_guard_iptables(protocol, ['-D', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])
    p2p_guard_iptables(protocol, ['-F', P2P_GUARD_CHAIN])
    p2p_guard_iptables(protocol, ['-X', P2P_GUARD_CHAIN])
    p2p_guard_remove_script(protocol)
    return p2p_guard_status_for(protocol)


def p2p_guard_apply_protocol(protocol: str, settings: dict) -> dict:
    iface = PROTOCOLS[protocol]['interface']
    p2p_guard_iptables(protocol, ['-N', P2P_GUARD_CHAIN])
    p2p_guard_iptables(protocol, ['-F', P2P_GUARD_CHAIN], check=True)
    while p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])['ok']:
        p2p_guard_iptables(protocol, ['-D', 'FORWARD', '-i', iface, '-j', P2P_GUARD_CHAIN])
    while p2p_guard_iptables(protocol, ['-C', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])['ok']:
        p2p_guard_iptables(protocol, ['-D', 'FORWARD', '-o', iface, '-j', P2P_GUARD_CHAIN])
    p2p_guard_iptables(protocol, ['-I', 'FORWARD', '1', '-i', iface, '-j', P2P_GUARD_CHAIN], check=True)
    p2p_guard_iptables(protocol, ['-I', 'FORWARD', '1', '-o', iface, '-j', P2P_GUARD_CHAIN], check=True)
    for args in p2p_guard_rule_args(iface, settings):
        if args[0] in ('-N', '-F', '-I'):
            continue
        p2p_guard_iptables(protocol, args)
    p2p_guard_install_script(protocol, settings)
    return p2p_guard_status_for(protocol)


def p2p_guard_apply_all(settings: dict) -> dict:
    result = {}
    for protocol in PROTOCOLS:
        try:
            result[protocol] = p2p_guard_apply_protocol(protocol, settings) if settings.get('enabled') else p2p_guard_reset_protocol(protocol)
        except Exception as e:
            status = p2p_guard_status_for(protocol)
            status['error'] = str(e)
            result[protocol] = status
    return result


@app.get('/api/p2p-guard')
def api_p2p_guard_get(user=Depends(api_require_admin)):
    return p2p_guard_status_payload()


@app.patch('/api/p2p-guard')
async def api_p2p_guard_update(request: Request, user=Depends(api_require_admin)):
    data = await api_read_payload(request)
    before = p2p_guard_settings()
    settings = p2p_guard_save_settings({
        'enabled': bool(data.get('enabled')),
        'mode': data.get('mode') or before.get('mode') or 'soft',
        'allow_udp_ports': data.get('allow_udp_ports') or before.get('allow_udp_ports') or '53,123,443',
    })
    protocols = p2p_guard_apply_all(settings)
    api_audit_log(request, user, 'p2p_guard.update', 'security', 'p2p_guard', 'P2P Guard', {'before': before, 'after': settings})
    telegram_notify(
        'P2P Guard обновлён',
        [f"Режим: {'enabled' if settings['enabled'] else 'disabled'} / {settings['mode']}", f"Кто: {user.get('username')}"],
    )
    return {'ok': True, 'settings': settings, 'protocols': protocols}


@app.post('/api/p2p-guard/apply')
async def api_p2p_guard_apply(request: Request, user=Depends(api_require_admin)):
    settings = p2p_guard_settings()
    protocols = p2p_guard_apply_all(settings)
    api_audit_log(request, user, 'p2p_guard.apply', 'security', 'p2p_guard', 'P2P Guard', {'settings': settings})
    return {'ok': True, 'settings': settings, 'protocols': protocols}
# === 3WG P2P GUARD API END ===

# === 3WG REACT API END ===
'''.strip() + '\n'

MIGRATION_HELPERS = r'''
def migration_runner_request(command: str, **extra) -> dict:
    payload = {"command": command, **extra}
    sock_path = Path(MIGRATION_RUNNER_SOCKET)
    if not MIGRATION_RUNNER_ENABLED:
        raise RuntimeError("Migration runner disabled")
    if not sock_path.exists():
        raise RuntimeError(f"Migration runner socket not found: {MIGRATION_RUNNER_SOCKET}")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5)
    try:
        client.connect(str(sock_path))
        client.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    finally:
        client.close()
    if not data:
        raise RuntimeError("Migration runner returned empty response")
    response = json.loads(data.decode("utf-8"))
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "Migration runner error"))
    return response


def migration_runner_status() -> dict | None:
    try:
        return migration_runner_request("status")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return None


def empty_migration_job() -> dict:
    return {"running": False, "started_at": None, "finished_at": None, "exit_code": None, "log": []}


def migration_runner_payload() -> dict:
    sock_path = Path(MIGRATION_RUNNER_SOCKET)
    exists = sock_path.exists()
    status = migration_runner_status() if MIGRATION_RUNNER_ENABLED and exists else None
    runner = status.get("runner") if status else {}
    can_run = bool(MIGRATION_RUNNER_ENABLED and exists and status)
    if not MIGRATION_RUNNER_ENABLED:
        reason = "Migration runner disabled"
    elif not exists:
        reason = f"Migration runner socket not found: {MIGRATION_RUNNER_SOCKET}"
    elif not status:
        reason = "Migration runner is not responding"
    else:
        reason = "ready"
    return {
        "enabled": MIGRATION_RUNNER_ENABLED,
        "socket": MIGRATION_RUNNER_SOCKET,
        "base": runner.get("base"),
        "log_path": runner.get("log_path"),
        "pid": runner.get("pid"),
        "sshpass": bool(runner.get("sshpass")),
        "exists": exists,
        "can_run": can_run,
        "reason": reason,
        "confirm_text": "MIGRATE",
    }


def migration_job_payload() -> dict:
    status = migration_runner_status()
    if status and isinstance(status.get("job"), dict):
        job = status["job"]
        return {
            "running": bool(job.get("running")),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "exit_code": job.get("exit_code"),
            "log": list(job.get("log") or [])[-240:],
        }
    return empty_migration_job()
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
if 'import subprocess\n' not in text:
    text = text.replace('import shutil\n', 'import shutil\nimport subprocess\n', 1)
if 'MIGRATION_RUNNER_ENABLED = ' not in text:
    text = text.replace(
        'UPDATE_RUNNER_SOCKET = os.getenv("UPDATE_RUNNER_SOCKET", "/app/run/update-runner.sock")\n',
        'UPDATE_RUNNER_SOCKET = os.getenv("UPDATE_RUNNER_SOCKET", "/app/run/update-runner.sock")\n'
        'MIGRATION_RUNNER_ENABLED = os.getenv("MIGRATION_RUNNER_ENABLED", "1") == "1"\n'
        'MIGRATION_RUNNER_SOCKET = os.getenv("MIGRATION_RUNNER_SOCKET", "/app/run/migration-runner.sock")\n',
        1,
    )
if 'FORNEX_VPN_PORTS = ' not in text:
    text = text.replace(
        'PANEL_CONTAINER = os.getenv("PANEL_CONTAINER", "3wg-panel")\n',
        'PANEL_CONTAINER = os.getenv("PANEL_CONTAINER", "3wg-panel")\n'
        'FORNEX_VPN_PORTS = (\n'
        '    "20, 21, 53, 80, 88, 110, 123, 143, 389, 443, 464, 500, "\n'
        '    "587, 636, 749, 853, 993, 995, 1116-1150, 1863, "\n'
        '    "3074-3079, 3268, 3269, 3283, 3306, 3389, 3478-3480, "\n'
        '    "3658, 3689, 3724, 4000, 4379, 4380, 4398, 4500, 5165, "\n'
        '    "5222, 5223, 5228-5230, 5235-5236, 5269, 5280"\n'
        ')\n',
        1,
    )
if 'def migration_runner_request(' not in text and 'def update_status_payload(' in text:
    text = text.replace('def update_status_payload() -> dict:\n', MIGRATION_HELPERS + '\n\ndef update_status_payload() -> dict:\n', 1)
if 'def change_protocol_port(' not in text and 'def db():\n' in text:
    text = text.replace('def db():\n', PORT_CHANGE_HELPERS + '\n\ndef db():\n', 1)
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
    APP_PATH.write_text(patched.rstrip() + '\n', encoding='utf-8')
    print('React API routes patched into app.py')
else:
    print('React API routes already up to date')
