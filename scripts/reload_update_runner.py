"""Reload the host runner after its updater exits, outside the runner's cgroup."""
import argparse
import re
import subprocess
import time
from pathlib import Path


def process_identity(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def wait_for_updater(pid, identity, timeout=7200):
    deadline = time.monotonic() + timeout
    while process_identity(pid) == identity:
        if time.monotonic() >= deadline:
            raise TimeoutError('Updater is still running; refusing to interrupt it')
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--identity', required=True)
    parser.add_argument('--service', required=True)
    args = parser.parse_args()
    if args.pid < 1 or not re.fullmatch(r'[A-Za-z0-9_.@-]+', args.service):
        parser.error('Invalid updater PID or service')
    wait_for_updater(args.pid, args.identity)
    time.sleep(2)
    subprocess.run(['systemctl', 'try-restart', args.service], check=True)


if __name__ == '__main__':
    main()
