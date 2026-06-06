#!/usr/bin/env python3
from pathlib import Path
import re

APP_PATH = Path('/srv/3wg-panel/app/app.py')
START = '# === 3WG VISUAL UI V13 START ==='
END = '# === 3WG VISUAL UI V13 END ==='

BLOCK = r'''
# === 3WG VISUAL UI V13 START ===
# Видимое улучшение текущего красивого интерфейса / без отдельного /ui.
LOGO_PATH_V13 = APP_DIR / 'static' / 'logogrin.png'


@app.get('/static/logogrin.png')
def static_logogrin_v13():
    if not LOGO_PATH_V13.exists():
        raise HTTPException(status_code=404, detail='Logo not found')
    return FileResponse(LOGO_PATH_V13)


try:
    _page_before_visual_ui_v13 = page

    def page(title: str, body: str) -> str:
        doc = _page_before_visual_ui_v13(title, body)

        hero = f'''
<div class="neo-hero">
  <div class="neo-hero-logo-wrap">
    <img class="neo-logo-v13" src="/static/logogrin.png" alt="3WG" loading="eager">
  </div>
  <div class="neo-hero-main">
    <div class="neo-eyebrow">NODE CONTROL</div>
    <h1>3WG Panel</h1>
    <p>Управление клиентами WireGuard / AmneziaWG на <code>{html.escape(ENDPOINT_HOST)}</code></p>
  </div>
  <div class="neo-hero-right">
    <span class="neo-chip">LIVE</span>
    <span class="neo-chip neo-chip-orange">CLASSIC UI</span>
  </div>
</div>
'''
        doc = doc.replace('<h1>3WG Panel</h1>', hero, 1)

        css = '''
<style id="visual-ui-v13">
:root {
  --v13-bg: #070c13;
  --v13-card: rgba(17,26,38,.94);
  --v13-line: rgba(64,82,106,.78);
  --v13-text: #e8f0fb;
  --v13-muted: #8c9bb0;
  --v13-green: #14f0a0;
  --v13-orange: #f5a33b;
  --v13-red: #ff5b73;
}
body {
  background:
    radial-gradient(circle at 18% -8%, rgba(37,217,255,.13), transparent 30%),
    radial-gradient(circle at 95% 5%, rgba(20,240,160,.09), transparent 28%),
    linear-gradient(180deg,#070c13,#090f18) !important;
}
.neo-hero {
  display:flex;
  justify-content:space-between;
  gap:18px;
  align-items:center;
  margin: 0 0 18px;
  padding: 18px 22px;
  border: 1px solid var(--v13-line);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(20,240,160,.075), rgba(37,217,255,.045)), rgba(10,16,25,.72);
  box-shadow: 0 24px 90px rgba(0,0,0,.32);
}
.neo-hero-logo-wrap {
  flex: 0 0 auto;
  display:flex;
  align-items:center;
  justify-content:center;
  min-width: 205px;
}
.neo-logo-v13 {
  display:block;
  width: 195px;
  height: auto;
  max-height: 50px;
  object-fit: contain;
  image-rendering: auto;
  filter: drop-shadow(0 0 16px rgba(151, 216, 18, .16));
}
.neo-hero-main { flex: 1 1 auto; min-width: 220px; }
.neo-hero h1 { margin: 4px 0 7px !important; letter-spacing: -.03em; }
.neo-hero p { margin:0 !important; color: var(--v13-muted) !important; }
.neo-eyebrow { color: var(--v13-green); font-size: 11px; font-weight: 900; letter-spacing: .18em; }
.neo-hero-right { display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
.neo-chip {
  display:inline-flex;
  align-items:center;
  min-height:26px;
  padding:0 10px;
  border-radius:999px;
  color:var(--v13-green);
  background:rgba(20,240,160,.08);
  border:1px solid rgba(20,240,160,.28);
  font-size:11px;
  font-weight:900;
}
.neo-chip-orange { color:#ffc575; background:rgba(245,163,59,.08); border-color:rgba(245,163,59,.28); }
.card, .stat {
  border-color: var(--v13-line) !important;
  background: linear-gradient(180deg, rgba(18,27,40,.96), rgba(12,19,29,.96)) !important;
  box-shadow: 0 18px 70px rgba(0,0,0,.30) !important;
}
.stat .n { color: var(--v13-green) !important; text-shadow: 0 0 24px rgba(20,240,160,.16); }
table { border-spacing: 0 9px !important; }
tbody tr { transition: transform .12s ease, filter .12s ease; }
tbody tr:hover { transform: translateY(-1px); filter: brightness(1.07); }
td { background: rgba(8,15,24,.76) !important; }
.btn, button[type="submit"] { transition: transform .12s ease, filter .12s ease; }
.btn:hover, button[type="submit"]:hover { transform: translateY(-1px); filter: brightness(1.07); }
.status-modal-v13 {
  position: fixed;
  inset: 0;
  z-index: 99999;
  display:none;
  align-items:center;
  justify-content:center;
  padding: 24px;
  background: rgba(2,6,12,.72);
  backdrop-filter: blur(9px);
}
.status-modal-v13.open { display:flex; }
.status-modal-card-v13 {
  width:min(980px, 96vw);
  max-height:86vh;
  overflow:hidden;
  border:1px solid var(--v13-line);
  border-radius:18px;
  background:#08101a;
  box-shadow:0 30px 140px rgba(0,0,0,.62);
}
.status-modal-head-v13 {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:14px 16px;
  border-bottom:1px solid var(--v13-line);
}
.status-modal-head-v13 b { color:var(--v13-green); }
.status-modal-close-v13 {
  background:var(--v13-orange);
  color:#101720;
  border:0;
  border-radius:8px;
  padding:8px 11px;
  font-weight:900;
  cursor:pointer;
}
.status-modal-pre-v13 {
  margin:0;
  padding:16px;
  max-height:70vh;
  overflow:auto;
  white-space:pre-wrap;
  color:#d8e6f7;
  font-size:12px;
  line-height:1.5;
}
@media(max-width:900px){ .neo-hero{display:block}.neo-hero-logo-wrap{justify-content:flex-start;margin-bottom:12px}.neo-hero-right{justify-content:flex-start;margin-top:12px} }
</style>
'''

        js = '''
<div class="status-modal-v13" id="statusModalV13">
  <div class="status-modal-card-v13">
    <div class="status-modal-head-v13"><b id="statusModalTitleV13">STATUS</b><button class="status-modal-close-v13" type="button">Закрыть</button></div>
    <pre class="status-modal-pre-v13" id="statusModalBodyV13">loading...</pre>
  </div>
</div>
<script id="visual-ui-v13-js">
(function(){
  const modal = document.getElementById('statusModalV13');
  const body = document.getElementById('statusModalBodyV13');
  const title = document.getElementById('statusModalTitleV13');
  if (!modal || !body || !title) return;
  function close(){ modal.classList.remove('open'); }
  modal.querySelector('.status-modal-close-v13').addEventListener('click', close);
  modal.addEventListener('click', function(e){ if(e.target === modal) close(); });
  document.addEventListener('keydown', function(e){ if(e.key === 'Escape') close(); });
  document.querySelectorAll('a[href="/raw/wireguard"],a[href="/raw/amneziawg"]').forEach(function(a){
    a.addEventListener('click', async function(e){
      e.preventDefault();
      title.textContent = a.textContent.trim() + ' STATUS';
      body.textContent = 'loading...';
      modal.classList.add('open');
      try {
        const r = await fetch(a.getAttribute('href'), {cache:'no-store'});
        body.textContent = await r.text();
      } catch (err) {
        body.textContent = String(err);
      }
    });
  });
})();
</script>
'''
        if 'visual-ui-v13' not in doc:
            doc = doc.replace('</head>', css + '\n</head>')
        if 'visual-ui-v13-js' not in doc:
            doc = doc.replace('</body>', js + '\n</body>')
        return doc

except NameError:
    pass
# === 3WG VISUAL UI V13 END ===
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + BLOCK
APP_PATH.write_text(text, encoding='utf-8')
print('Visible classic UI v13 patched into app.py')
