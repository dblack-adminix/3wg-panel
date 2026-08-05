#!/usr/bin/env python3
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


BASE = Path(os.environ.get("THREEWG_BASE", "/srv/3wg-panel")).resolve()
SOCKET_PATH = Path(os.environ.get("THREEWG_MIGRATION_SOCKET", str(BASE / "run/migration-runner.sock")))
LOG_PATH = Path(os.environ.get("THREEWG_MIGRATION_LOG", str(BASE / "backups/migration/ui-runner.log")))
REPO_URL_DEFAULT = os.environ.get("THREEWG_REPO_URL", "https://github.com/dblack-adminix/3wg-panel.git")
BRANCH_DEFAULT = os.environ.get("THREEWG_BRANCH", "dev")

STATE_LOCK = threading.Lock()
STATE = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "log": [],
}


def append_log(line: str) -> None:
    text = str(line).rstrip()
    with STATE_LOCK:
        STATE.setdefault("log", []).append(text)
        STATE["log"] = STATE["log"][-500:]
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def state_payload() -> dict:
    with STATE_LOCK:
        return {
            "running": bool(STATE.get("running")),
            "started_at": STATE.get("started_at"),
            "finished_at": STATE.get("finished_at"),
            "exit_code": STATE.get("exit_code"),
            "log": list(STATE.get("log") or [])[-240:],
        }


def clean_host(value: str) -> str:
    value = str(value or "").strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
    if not value or any(ch not in allowed for ch in value):
        raise ValueError("Некорректный SSH host")
    return value


def clean_user(value: str) -> str:
    value = str(value or "root").strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if not value or any(ch not in allowed for ch in value):
        raise ValueError("Некорректный SSH user")
    return value


def clean_port(value) -> int:
    port = int(value or 22)
    if port < 1 or port > 65535:
        raise ValueError("Некорректный SSH port")
    return port


def safe_archive(name: str) -> Path:
    clean = Path(str(name or "")).name
    path = (BASE / "backups/migration" / clean).resolve()
    root = (BASE / "backups/migration").resolve()
    if not clean.endswith(".tgz") or root not in path.parents or not path.is_file():
        raise ValueError("Migration bundle не найден")
    return path


def display_cmd(cmd: list[str]) -> str:
    masked: list[str] = []
    for idx, part in enumerate(cmd):
        if idx >= 1 and cmd[idx - 1] == "-p" and idx >= 2 and cmd[idx - 2] == "sshpass":
            masked.append("******")
        else:
            masked.append(part)
    return " ".join(shlex.quote(part) for part in masked)


def run_cmd(cmd: list[str], *, input_text: str | None = None, env: dict | None = None, timeout: int = 900) -> None:
    append_log("$ " + display_cmd(cmd))
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, **(env or {})},
    )
    assert proc.stdout is not None
    if input_text is not None and proc.stdin is not None:
        proc.stdin.write(input_text)
        proc.stdin.close()
    started = time.time()
    for line in proc.stdout:
        append_log(line)
        if time.time() - started > timeout:
            proc.kill()
            raise TimeoutError("Command timeout")
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"Command failed with exit code {code}")


def auth_prefix(payload: dict, temp_files: list[Path]) -> tuple[list[str], list[str], dict]:
    method = str(payload.get("auth_method") or "password")
    password = str(payload.get("password") or "")
    private_key = str(payload.get("private_key") or "")
    ssh_opts = [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=12",
    ]
    prefix: list[str] = []
    env: dict = {}
    if method == "password":
        if not password:
            raise ValueError("Введите SSH password")
        if not shutil.which("sshpass"):
            raise RuntimeError("На host не установлен sshpass. Переустановите migration runner или установите пакет sshpass.")
        prefix = ["sshpass", "-e"]
        env["SSHPASS"] = password
    elif method == "key":
        if not private_key.strip():
            raise ValueError("Введите SSH private key")
        key_file = Path(tempfile.mkstemp(prefix="3wg-migration-key.", text=True)[1])
        key_file.write_text(private_key.rstrip() + "\n", encoding="utf-8")
        key_file.chmod(0o600)
        temp_files.append(key_file)
        ssh_opts.extend(["-i", str(key_file)])
    else:
        raise ValueError("Некорректный SSH auth method")
    return prefix, ssh_opts, env


def remote_script(install_dir: str, repo_url: str, branch: str, archive_remote: str) -> str:
    return f"""set -euo pipefail
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y git curl python3 docker.io nodejs npm >/dev/null
  systemctl enable --now docker >/dev/null 2>&1 || true
fi
mkdir -p {shlex.quote(str(Path(install_dir).parent))}
if [ ! -d {shlex.quote(install_dir)}/.git ]; then
  git clone --branch {shlex.quote(branch)} {shlex.quote(repo_url)} {shlex.quote(install_dir)}
else
  git -C {shlex.quote(install_dir)} fetch --all --tags
  git -C {shlex.quote(install_dir)} checkout {shlex.quote(branch)}
  git -C {shlex.quote(install_dir)} pull --ff-only
fi
cd {shlex.quote(install_dir)}
bash scripts/migration_import.sh {shlex.quote(archive_remote)}
"""


def run_push(payload: dict) -> None:
    with STATE_LOCK:
        STATE.update({"running": True, "started_at": int(time.time()), "finished_at": None, "exit_code": None, "log": []})
    temp_files: list[Path] = []
    try:
        host = clean_host(payload.get("host"))
        user = clean_user(payload.get("user") or "root")
        port = clean_port(payload.get("port") or 22)
        install_dir = str(payload.get("install_dir") or "/opt/3wg-panel").strip() or "/opt/3wg-panel"
        repo_url = str(payload.get("repo_url") or REPO_URL_DEFAULT).strip() or REPO_URL_DEFAULT
        branch = str(payload.get("branch") or BRANCH_DEFAULT).strip() or BRANCH_DEFAULT
        archive = safe_archive(str(payload.get("archive") or ""))
        remote_archive = f"{install_dir.rstrip('/')}/backups/migration/{archive.name}"
        target = f"{user}@{host}"
        prefix, ssh_opts, auth_env = auth_prefix(payload, temp_files)

        append_log(f"Target: {target}:{port}")
        append_log(f"Install dir: {install_dir}")
        append_log(f"Archive: {archive.name}")
        append_log(f"Branch/tag: {branch}")

        ssh_base = [*prefix, "ssh", "-p", str(port), *ssh_opts, target]
        scp_base = [*prefix, "scp", "-P", str(port), *ssh_opts]

        run_cmd([*ssh_base, f"mkdir -p {shlex.quote(install_dir.rstrip('/') + '/backups/migration')}"], env=auth_env)
        run_cmd([*scp_base, str(archive), f"{target}:{remote_archive}"], env=auth_env)
        run_cmd([*ssh_base, "bash -s"], input_text=remote_script(install_dir, repo_url, branch, remote_archive), env=auth_env, timeout=1800)

        with STATE_LOCK:
            STATE["exit_code"] = 0
        append_log("Migration push finished successfully")
    except Exception as exc:
        with STATE_LOCK:
            STATE["exit_code"] = -1
        append_log(f"ERROR: {exc}")
    finally:
        for path in temp_files:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        with STATE_LOCK:
            STATE["finished_at"] = int(time.time())
            STATE["running"] = False


def runner_payload() -> dict:
    return {
        "socket": str(SOCKET_PATH),
        "base": str(BASE),
        "log_path": str(LOG_PATH),
        "pid": os.getpid(),
        "sshpass": bool(shutil.which("sshpass")),
    }


def handle_command(payload: dict) -> dict:
    command = str(payload.get("command", "status"))
    if command == "status":
        return {"ok": True, "runner": runner_payload(), "job": state_payload()}
    if command == "push":
        with STATE_LOCK:
            if STATE.get("running"):
                return {"ok": False, "error": "Migration push already running", "job": state_payload()}
            STATE.update({"running": True, "started_at": int(time.time()), "finished_at": None, "exit_code": None, "log": ["Queued"]})
        threading.Thread(target=run_push, args=(payload,), daemon=True).start()
        return {"ok": True, "runner": runner_payload(), "job": state_payload()}
    return {"ok": False, "error": f"Unknown command: {command}"}


def client_thread(conn: socket.socket) -> None:
    try:
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
        try:
            payload = json.loads(data.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            response = {"ok": False, "error": f"Invalid JSON: {exc}"}
        else:
            response = handle_command(payload)
        conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        conn.close()


def shutdown(signum, _frame):
    raise SystemExit(128 + int(signum))


def main() -> int:
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    os.chmod(SOCKET_PATH, 0o660)
    server.listen(20)
    print(f"3WG migration push runner listening on {SOCKET_PATH}", flush=True)
    try:
        while True:
            conn, _addr = server.accept()
            threading.Thread(target=client_thread, args=(conn,), daemon=True).start()
    finally:
        server.close()
        try:
            SOCKET_PATH.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
