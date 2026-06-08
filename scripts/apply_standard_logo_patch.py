#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / 'app/app.py'
START = '# === 3WG STANDARD PNG LOGO START ==='
END = '# === 3WG STANDARD PNG LOGO END ==='

RUNTIME = r'''
# === 3WG STANDARD PNG LOGO START ===
@app.get('/logogrin.png')
def logogrin_png():
    logo_path = APP_DIR / 'static' / 'logogrin.png'
    if not logo_path.exists():
        raise HTTPException(status_code=404, detail='Logo not found')
    return FileResponse(
        logo_path,
        media_type='image/png',
        headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0'},
    )


def standard_logo_img(width: str, height: str) -> str:
    return (
        '<img src="/logogrin.png" alt="3WG" '
        'style="display:block!important;'
        f'width:{width}!important;height:{height}!important;'
        'max-width:none!important;max-height:none!important;'
        'object-fit:contain!important;opacity:1!important;visibility:visible!important;'
        'background:transparent!important">'
    )


try:
    _login_html_before_standard_logo = login_html

    def login_html(*args, **kwargs) -> str:
        doc = _login_html_before_standard_logo(*args, **kwargs)
        login_logo = (
            '<div id="standard-login-logo" class="logo" style="height:62px;margin:0 0 10px 0;'
            'display:flex!important;align-items:center!important;justify-content:flex-start!important;'
            'background:transparent!important;overflow:visible!important">'
            + standard_logo_img('195px', '50px') +
            '</div>'
        )
        new_doc = re.sub(r'<div class="logo"[^>]*>.*?</div>', login_logo, doc, count=1, flags=re.S)
        if new_doc == doc and 'standard-login-logo' not in doc:
            new_doc = doc.replace('<div class="badge">SECURE NODE PANEL</div>', '<div class="badge">SECURE NODE PANEL</div>' + login_logo, 1)
        return new_doc
except NameError:
    pass


try:
    _page_before_standard_logo = page

    def page(title: str, body: str) -> str:
        doc = _page_before_standard_logo(title, body)
        sidebar_logo = (
            '<div class="neo-brand" id="standard-sidebar-logo" style="display:flex!important;align-items:center!important;'
            'justify-content:flex-start!important;min-height:58px!important;padding:0 0 18px!important;'
            'margin:0 0 18px!important;border-bottom:1px dashed rgba(64,82,106,.55)!important;'
            'background:transparent!important;overflow:visible!important">'
            + standard_logo_img('178px', '46px') +
            '</div>'
        )
        doc = re.sub(r'<div class="neo-brand"[^>]*>.*?</div>', sidebar_logo, doc, count=1, flags=re.S)
        doc = re.sub(r'<div class="neo-title-icon"[^>]*>.*?</div>\s*', '', doc, count=1, flags=re.S)
        return doc
except NameError:
    pass
# === 3WG STANDARD PNG LOGO END ===
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + RUNTIME
APP_PATH.write_text(text, encoding='utf-8')
print('standard PNG logo patch applied')
