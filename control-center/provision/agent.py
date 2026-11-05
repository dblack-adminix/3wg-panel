#!/usr/bin/env python3
"""Forced SSH command: no remote shell or caller-provided Docker arguments."""
import json
import subprocess
import sys

try:
    request=json.loads(sys.stdin.buffer.readline(4097))
    action=request.get('action')
    if action=='status':
        result=subprocess.run(['docker','inspect','--format','{{.State.Status}}','3wg-exit'],capture_output=True,text=True,timeout=15,check=True)
        status=result.stdout.strip()
        handshake=False
        if status=='running':
            result=subprocess.run(['docker','exec','3wg-exit','awg','show','exit0','latest-handshakes'],capture_output=True,text=True,timeout=15,check=True)
            import time
            handshake=any(0<int(line.split()[-1]) and time.time()-int(line.split()[-1])<180 for line in result.stdout.splitlines())
        print(json.dumps({'ok':True,'running':status=='running','handshake':handshake}))
    elif action in ('restart','stop'):
        subprocess.run(['docker',action,'3wg-exit'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=45,check=True)
        print(json.dumps({'ok':True}))
    else:
        print(json.dumps({'ok':False,'error':'Unsupported action'}))
        sys.exit(1)
except Exception:
    print(json.dumps({'ok':False,'error':'Exit agent failed'}))
    sys.exit(1)
