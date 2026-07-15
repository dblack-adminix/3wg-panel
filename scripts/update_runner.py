#!/usr/bin/env python3
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


BASE = Path(os.environ.get("THREEWG_BASE", "/srv/3wg-panel")).resolve()
SOCKET_PATH = Path(os.environ.get("THREEWG_UPDATE_SOCKET", str(BASE / "run/update-runner.sock")))
UPDATE_SCRIPT = Path(os.environ.get("THREEWG_UPDATE_SCRIPT", str(BASE / "scripts/update.sh")))
LOG_PATH = Path(os.environ.get("THREEWG_UPDATE_LOG", str(BASE / "backups/update/ui-runner.log")))

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


def run_update(actor: str = "panel", backup: str = "") -> None:
    with STATE_LOCK:
        STATE.update({"running": True, "started_at": int(time.time()), "finished_at": None, "exit_code": None, "log": []})
    append_log(f"Actor: {actor}")
    if backup:
        append_log(f"Pre-update backup: {backup}")
    append_log(f"Base: {BASE}")
    append_log(f"Running: bash {UPDATE_SCRIPT}")
    try:
        proc = subprocess.Popen(
            ["bash", str(UPDATE_SCRIPT)],
            cwd=str(BASE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "INSTALL_DIR": str(BASE), "THREEWG_UPDATE_RUNNER_ACTIVE": "1"},
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            append_log(line)
        code = int(proc.wait())
        with STATE_LOCK:
            STATE["exit_code"] = code
        append_log(f"Exit code: {code}")
    except Exception as exc:
        with STATE_LOCK:
            STATE["exit_code"] = -1
        append_log(f"ERROR: {exc}")
    finally:
        with STATE_LOCK:
            STATE["finished_at"] = int(time.time())
            STATE["running"] = False


def handle_command(payload: dict) -> dict:
    command = str(payload.get("command", "status"))
    if command == "status":
        return {"ok": True, "runner": runner_payload(), "job": state_payload()}
    if command == "run":
        with STATE_LOCK:
            if STATE.get("running"):
                return {"ok": False, "error": "Update already running", "job": state_payload()}
            STATE.update({"running": True, "started_at": int(time.time()), "finished_at": None, "exit_code": None, "log": ["Queued"]})
        # Reset to a clean run state inside the worker. Marking running here closes the race.
        threading.Thread(
            target=run_update,
            args=(str(payload.get("actor") or "panel"), str(payload.get("backup") or "")),
            daemon=True,
        ).start()
        return {"ok": True, "runner": runner_payload(), "job": state_payload()}
    return {"ok": False, "error": f"Unknown command: {command}"}


def runner_payload() -> dict:
    return {
        "socket": str(SOCKET_PATH),
        "base": str(BASE),
        "update_script": str(UPDATE_SCRIPT),
        "script_exists": UPDATE_SCRIPT.exists(),
        "log_path": str(LOG_PATH),
        "pid": os.getpid(),
    }


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
    os.chmod(SOCKET_PATH, 0o666)
    server.listen(20)
    print(f"3WG update runner listening on {SOCKET_PATH}", flush=True)
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
