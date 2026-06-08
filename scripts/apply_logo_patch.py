#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / 'app/app.py'
START = '# === 3WG SUPPLIED LOGO START ==='
END = '# === 3WG SUPPLIED LOGO END ==='

logo_src = '/static/logogrin.png?v=3wg-logo-20260606-2'

runtime = """
# === 3WG SUPPLIED LOGO START ===
LOGO_PATH_SUPPLIED = APP_DIR / 'static' / 'logogrin.png'
SUPPLIED_LOGO_SRC = __LOGO_SRC__

@app.get('/static/logogrin.png')
def static_logogrin_supplied():
    if not LOGO_PATH_SUPPLIED.exists():
        raise HTTPException(status_code=404, detail='Logo not found')
    return FileResponse(LOGO_PATH_SUPPLIED)

try:
    _login_html_before_supplied_logo = login_html
    def login_html(*args, **kwargs) -> str:
        doc = _login_html_before_supplied_logo(*args, **kwargs)
        logo_html = '<div style="height:62px;margin:0 0 10px 0;display:flex;align-items:center;justify-content:flex-start;background:transparent!important;overflow:visible!important"><img src="' + SUPPLIED_LOGO_SRC + '" alt="3WG" style="display:block!important;width:195px!important;height:50px!important;min-width:195px!important;min-height:50px!important;max-width:none!important;max-height:none!important;object-fit:contain!important;opacity:1!important;visibility:visible!important;filter:drop-shadow(0 0 12px rgba(151,216,18,.22))"></div>'
        doc = re.sub(r'<div class="logo">.*?</div>', logo_html, doc, count=1, flags=re.S)
        return doc
except NameError:
    pass

try:
    _page_before_supplied_logo = page
    def page(title: str, body: str) -> str:
        doc = _page_before_supplied_logo(title, body)
        brand_html = '<div class="neo-brand" style="display:flex!important;align-items:center!important;justify-content:flex-start!important;min-height:50px!important;padding:0 0 18px!important;margin:0 0 18px!important;border-bottom:1px dashed rgba(64,82,106,.55)!important;overflow:visible!important"><img src="' + SUPPLIED_LOGO_SRC + '" alt="3WG" loading="eager" style="display:block!important;width:178px!important;height:46px!important;min-width:178px!important;min-height:46px!important;max-width:none!important;max-height:none!important;object-fit:contain!important;opacity:1!important;visibility:visible!important;filter:drop-shadow(0 0 12px rgba(151,216,18,.18))"></div>'
        doc = re.sub(r'<div class="neo-brand">\s*<div class="neo-logo">3</div>\s*<div>\s*<div class="neo-brand-title">3WG</div>\s*<div class="neo-brand-sub">NODE PANEL</div>\s*</div>\s*</div>', brand_html, doc, count=1, flags=re.S)
        title_icon = '<img src="' + SUPPLIED_LOGO_SRC + '" alt="3WG" style="display:block!important;width:54px!important;height:auto!important;max-height:26px!important;object-fit:contain!important;opacity:1!important;visibility:visible!important">'
        doc = re.sub(r'<div class="neo-title-icon">.*?</div>', '<div class="neo-title-icon" style="width:58px!important;background:transparent!important;border:0!important;display:flex!important;align-items:center!important;justify-content:center!important;overflow:visible!important">' + title_icon + '</div>', doc, count=1, flags=re.S)
        return doc
except NameError:
    pass
# === 3WG SUPPLIED LOGO END ===
""".strip() + "\n"

runtime = runtime.replace('__LOGO_SRC__', repr(logo_src))
text = APP_PATH.read_text(encoding='utf-8')
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + runtime
APP_PATH.write_text(text, encoding='utf-8')
print('Supplied logo patched into app.py')
