#!/usr/bin/env bash
set -euo pipefail

BASE="/srv/3wg-panel"
APP="$BASE/app/app.py"

echo "======================================================"
echo " 3WG PANEL DEV DEPLOY"
echo "======================================================"

cd "$BASE"

echo
echo "===== UI cleanup ====="
python3 - <<'PY'
from pathlib import Path
import re

app = Path("/srv/3wg-panel/app/app.py")
text = app.read_text(encoding="utf-8")
new_text = text

patterns = [
    r'\n[ \t]*<a\s+href="/"\s*>\s*\n[ \t]*<span\s+class="ico">.*?</span>\s*\n[ \t]*<span>Клиенты</span>\s*\n[ \t]*</a>',
    r'\n[ \t]*<a\s+href="/"><span\s+class="ico">.*?</span><span>Клиенты</span></a>',
]

removed = 0
for pattern in patterns:
    new_text, count = re.subn(pattern, "", new_text, flags=re.S)
    removed += count

if new_text != text:
    app.write_text(new_text, encoding="utf-8")
    print(f"removed redundant Clients sidebar links: {removed}")
else:
    print("no redundant Clients sidebar links found")
PY

echo
echo "===== React API patch ====="
python3 "$BASE/scripts/apply_api_patch.py"

echo
echo "===== React UI shell ====="
mkdir -p "$BASE/app/frontend_dist"
cat > "$BASE/app/frontend_dist/index.html" <<'EOF'
<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>3WG Panel React</title><style>
:root{--bg:#070c13;--card:#111a26;--line:#29374a;--text:#e8f0fb;--muted:#8795aa;--green:#14f0a0;--orange:#f4a340;--red:#ff5b73;--cyan:#25d9ff}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% -10%,rgba(37,217,255,.12),transparent 30%),linear-gradient(180deg,#070c13,#0a1018);color:var(--text);font-family:Inter,Arial,sans-serif}.layout{min-height:100vh}.side{position:fixed;inset:0 auto 0 0;width:238px;background:#070c13;border-right:1px solid var(--line);padding:18px 14px}.brand{font-size:24px;font-weight:900;margin:8px 8px 24px;color:var(--green)}.sec{margin:18px 8px 8px;color:#607086;font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.15em}.nav{display:block;padding:12px;border-radius:12px;margin-bottom:6px;color:#b8c5d8;text-decoration:none;background:transparent;border:1px solid transparent}.nav.on,.nav:hover{background:rgba(20,240,160,.08);border-color:rgba(20,240,160,.24);color:#fff}.main{margin-left:238px;padding:24px 28px 44px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.top p,.muted{color:var(--muted)}.btn{background:var(--orange);color:#111820;border:0;border-radius:12px;padding:11px 14px;font-weight:900;cursor:pointer}.cards{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px}.card{background:linear-gradient(180deg,rgba(18,27,40,.96),rgba(12,19,29,.96));border:1px solid var(--line);border-radius:18px;padding:18px;margin-bottom:16px;box-shadow:0 18px 70px rgba(0,0,0,.32)}.stat span{color:var(--muted);display:block}.stat b{font-size:28px;color:var(--green)}.grid{display:grid;grid-template-columns:repeat(2,minmax(250px,1fr));gap:12px}.pill{display:inline-block;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:900}.ok{color:var(--green);background:rgba(20,240,160,.09);border:1px solid rgba(20,240,160,.25)}.bad{color:var(--red);background:rgba(255,91,115,.08);border:1px solid rgba(255,91,115,.25)}code{background:#070d15;border:1px solid var(--line);border-radius:8px;padding:3px 7px}table{width:100%;border-collapse:separate;border-spacing:0 8px}th{text-align:left;color:#94a6bb;font-size:12px;text-transform:uppercase;padding:8px 10px}td{background:rgba(9,16,25,.68);border-top:1px solid rgba(51,67,87,.45);border-bottom:1px solid rgba(51,67,87,.45);padding:13px 10px}td:first-child{border-left:1px solid rgba(51,67,87,.45);border-radius:12px 0 0 12px}td:last-child{border-right:1px solid rgba(51,67,87,.45);border-radius:0 12px 12px 0}.actions a{display:inline-block;margin:3px;text-decoration:none;color:#111820;background:var(--orange);border-radius:10px;padding:7px 9px;font-size:12px;font-weight:900}.login{min-height:100vh;display:grid;place-items:center}.login form{width:100%;max-width:430px;background:#101827;border:1px solid var(--line);border-radius:24px;padding:30px}.login input{width:100%;margin:8px 0 14px;padding:14px;border-radius:14px;border:1px solid #344052;background:#080e17;color:#fff}.alert{background:rgba(255,91,115,.08);border:1px solid rgba(255,91,115,.25);color:#ff9aaa;border-radius:14px;padding:12px;margin:12px 0}@media(max-width:900px){.side{display:none}.main{margin-left:0}.cards,.grid{grid-template-columns:1fr}}
</style></head><body><div id="root">Loading...</div><script type="module">
import React from 'https://esm.sh/react@18';import{createRoot}from'https://esm.sh/react-dom@18/client';const h=React.createElement;
async function api(p,o={}){let r=await fetch(p,{credentials:'include',headers:{'Content-Type':'application/json'},...o});let t=await r.text();let d;try{d=t?JSON.parse(t):{}}catch{d={raw:t}}if(!r.ok){throw new Error(d.error||d.detail||('HTTP '+r.status))}return d}
function Pill({ok,text}){return h('span',{className:'pill '+(ok?'ok':'bad')},text)}
function Login({go}){const[u,su]=React.useState('admin'),[p,sp]=React.useState(''),[e,se]=React.useState('');async function sub(ev){ev.preventDefault();se('');try{await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:u,password:p})});go(true)}catch(x){se(x.message)}}return h('div',{className:'login'},h('form',{onSubmit:sub},h('h1',null,'3WG Panel'),h('p',{className:'muted'},'React UI'),e&&h('div',{className:'alert'},e),h('label',null,'Логин'),h('input',{value:u,onChange:e=>su(e.target.value)}),h('label',null,'Пароль'),h('input',{type:'password',value:p,onChange:e=>sp(e.target.value)}),h('button',{className:'btn'},'Войти')))}
function Dash({go}){const[st,setSt]=React.useState(null),[pr,setPr]=React.useState({}),[pe,setPe]=React.useState([]),[err,setErr]=React.useState('');async function load(){try{let a=await api('/api/node/protocols'),b=await api('/api/node/status'),c=await api('/api/peers');setPr(a.protocols||{});setSt(b);setPe(c.peers||[]);setErr('')}catch(e){setErr(e.message)}}React.useEffect(()=>{load()},[]);async function logout(){try{await api('/api/auth/logout',{method:'POST'})}catch{}go(false)}return h('div',{className:'layout'},h('aside',{className:'side'},h('div',{className:'brand'},'3WG'),h('div',{className:'sec'},'Обзор'),h('a',{className:'nav on',href:'/ui'},'Главная'),h('a',{className:'nav',href:'#peers'},"Peer'ы"),h('a',{className:'nav',href:'#status'},'Статус'),h('div',{className:'sec'},'Система'),h('button',{className:'nav',onClick:logout},'Выход')),h('main',{className:'main'},h('div',{className:'top'},h('div',null,h('h1',null,'3WG Panel'),h('p',null,st?.endpoint_host||'node')),h('button',{className:'btn',onClick:load},'Обновить')),err&&h('div',{className:'alert'},err),h('div',{className:'cards'},h('div',{className:'card stat'},h('span',null,'Клиентов'),h('b',null,st?.clients_total??0)),h('div',{className:'card stat'},h('span',null,"Peer'ов"),h('b',null,st?.peers_total??0)),h('div',{className:'card stat'},h('span',null,'Online'),h('b',null,st?.peers_online??0)),h('div',{className:'card stat'},h('span',null,'DNS'),h('b',null,'OK'))),h('section',{id:'status',className:'card'},h('h2',null,'Протоколы'),h('div',{className:'grid'},Object.values(pr).map(x=>h('div',{className:'card',key:x.protocol},h('h3',null,x.title),h('p',{className:'muted'},x.container+' / '+x.interface),h('code',null,x.endpoint),h('br'),h(Pill,{ok:x.available,text:x.available?'ONLINE':'OFFLINE'}),!x.available&&h('p',{className:'muted'},x.reason))))),h('section',{id:'peers',className:'card'},h('h2',null,"Peer'ы"),h('table',null,h('thead',null,h('tr',null,['ID','Имя','Протокол','IP','Статус','Действия'].map(x=>h('th',{key:x},x)))),h('tbody',null,pe.map(x=>h('tr',{key:x.id},h('td',null,x.id),h('td',null,x.name),h('td',null,x.protocol_title),h('td',null,h('code',null,x.ip_cidr)),h('td',null,h(Pill,{ok:x.status==='active',text:x.status.toUpperCase()})),h('td',{className:'actions'},h('a',{href:x.links.html},'Открыть'),h('a',{href:x.links.download},'CONF'),x.links.download_vpn&&h('a',{href:x.links.download_vpn},'VPN'),h('a',{href:x.links.qr_native_png},'QR')))))))))}
function Root(){const[a,setA]=React.useState(null);React.useEffect(()=>{api('/api/auth/me').then(()=>setA(true)).catch(()=>setA(false))},[]);if(a===null)return h('div',{className:'login'},'Loading...');return a?h(Dash,{go:setA}):h(Login,{go:setA})}createRoot(document.getElementById('root')).render(h(Root));
</script></body></html>
EOF

python3 - <<'PY'
from pathlib import Path
app = Path('/srv/3wg-panel/app/app.py')
text = app.read_text(encoding='utf-8')
start = '# === 3WG REACT UI START ==='
end = '# === 3WG REACT UI END ==='
block = '''
# === 3WG REACT UI START ===
REACT_UI_DIR = APP_DIR / 'frontend_dist'


def react_ui_index():
    index = REACT_UI_DIR / 'index.html'
    if not index.exists():
        raise HTTPException(status_code=404, detail='React UI is not built')
    return FileResponse(index)


@app.get('/ui')
def react_ui_root(user=Depends(auth)):
    return react_ui_index()


@app.get('/ui/')
def react_ui_root_slash(user=Depends(auth)):
    return react_ui_index()
# === 3WG REACT UI END ===
'''.strip() + '\n'
import re
text = re.sub(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + block
app.write_text(text, encoding='utf-8')
print('React UI routes patched into app.py')
PY

cat > "$BASE/app/Dockerfile" <<'EOF'
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY frontend_dist /app/frontend_dist

RUN mkdir -p /app/data /app/clients/wireguard /app/clients/amneziawg /app/backups/wireguard /app/backups/amneziawg

EXPOSE 18080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18080"]
EOF

echo
echo "===== Syntax check ====="
python3 -m py_compile "$APP"
echo "app.py syntax OK"

echo
echo "===== Backup current source ====="
mkdir -p "$BASE/backups/source"

tar -czf "$BASE/backups/source/3wg-panel-app.$(date +%F_%H-%M-%S).tgz" \
  -C "$BASE" app

echo
echo "===== Rebuild Docker image ====="
docker rm -f 3wg-panel 2>/dev/null || true
docker rmi 3wg-panel:local 2>/dev/null || true

docker build -t 3wg-panel:local "$BASE/app"

echo
echo "===== Run 3WG Panel ====="
docker run -d \
  --name 3wg-panel \
  --restart unless-stopped \
  --env-file "$BASE/.env" \
  -p 127.0.0.1:18080:18080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$BASE/data:/app/data" \
  -v "$BASE/clients:/app/clients" \
  -v "$BASE/backups:/app/backups" \
  3wg-panel:local

sleep 4

echo
echo "===== Health check ====="
docker exec 3wg-panel python - <<'PY'
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:18080/health").read().decode())
PY

echo
echo "===== Status ====="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "DONE"
