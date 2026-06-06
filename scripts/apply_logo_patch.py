#!/usr/bin/env python3
from pathlib import Path
import base64
import re

APP_PATH = Path('/srv/3wg-panel/app/app.py')
LOGO_PATH = Path('/srv/3wg-panel/app/static/logogrin.png')
START = '# === 3WG SUPPLIED LOGO START ==='
END = '# === 3WG SUPPLIED LOGO END ==='

if LOGO_PATH.exists():
    logo_src = 'data:image/png;base64,' + base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii')
else:
    logo_src = '/static/logogrin.png'

block_lines = [
    START,
    '# Размещаем готовый PNG логотип пользователя в панели и на странице входа.',
    'LOGO_PATH_SUPPLIED = APP_DIR / "static" / "logogrin.png"',
    f'SUPPLIED_LOGO_SRC = {logo_src!r}',
    '',
    '@app.get("/static/logogrin.png")',
    'def static_logogrin_supplied():',
    '    if not LOGO_PATH_SUPPLIED.exists():',
    '        raise HTTPException(status_code=404, detail="Logo not found")',
    '    return FileResponse(LOGO_PATH_SUPPLIED)',
    '',
    'try:',
    '    _login_html_before_supplied_logo = login_html',
    '    def login_html(*args, **kwargs) -> str:',
    '        doc = _login_html_before_supplied_logo(*args, **kwargs)',
    '        logo_html = "<div class=\\"logo supplied-login-logo-wrap\\"><img class=\\"supplied-login-logo\\" src=\\"" + SUPPLIED_LOGO_SRC + "\\" alt=\\"3WG\\"></div>"',
    '        doc = re.sub(r"<div class=\\"logo\\">.*?</div>", logo_html, doc, count=1, flags=re.S)',
    '        css = "<style id=\\"supplied-login-logo-css\\">" + " \\n".join([',
    '            ".supplied-login-logo-wrap{min-height:54px!important;margin-bottom:8px!important;display:flex!important;align-items:center!important;justify-content:flex-start!important;background:transparent!important;color:transparent!important}",',
    '            ".supplied-login-logo{display:block!important;width:195px!important;max-width:195px!important;height:auto!important;max-height:50px!important;object-fit:contain!important;filter:drop-shadow(0 0 12px rgba(151,216,18,.18))}",',
    '        ]) + "</style>"',
    '        if "supplied-login-logo-css" not in doc:',
    '            doc = doc.replace("</head>", css + "\\n</head>")',
    '        return doc',
    'except NameError:',
    '    pass',
    '',
    'try:',
    '    _page_before_supplied_logo = page',
    '    def page(title: str, body: str) -> str:',
    '        doc = _page_before_supplied_logo(title, body)',
    '        brand_html = "<div class=\\"neo-brand neo-brand-supplied-logo\\"><img class=\\"supplied-logo-img\\" src=\\"" + SUPPLIED_LOGO_SRC + "\\" alt=\\"3WG\\" loading=\\"eager\\"></div>"',
    '        doc = re.sub(r"<div class=\\"neo-brand\\">\\s*<div class=\\"neo-logo\\">3</div>\\s*<div>\\s*<div class=\\"neo-brand-title\\">3WG</div>\\s*<div class=\\"neo-brand-sub\\">NODE PANEL</div>\\s*</div>\\s*</div>", brand_html, doc, count=1, flags=re.S)',
    '        title_icon_css_url = SUPPLIED_LOGO_SRC.replace(")", "%29").replace("(", "%28")',
    '        css = "<style id=\\"supplied-logo-css\\">" + " \\n".join([',
    '            ".neo-brand-supplied-logo{display:flex!important;align-items:center!important;justify-content:flex-start!important;min-height:46px!important;padding:0 0 18px!important;margin:0 0 18px!important;border-bottom:1px dashed rgba(64,82,106,.55)!important}",',
    '            ".supplied-logo-img{display:block!important;width:178px!important;max-width:178px!important;height:auto!important;max-height:46px!important;object-fit:contain!important;filter:drop-shadow(0 0 12px rgba(151,216,18,.16))}",',
    '            ".neo-title-icon{background-image:url(\'" + title_icon_css_url + "\')!important;background-size:contain!important;background-repeat:no-repeat!important;background-position:center!important;color:transparent!important;text-indent:-999px!important;overflow:hidden!important;width:54px!important;border:0!important;background-color:transparent!important}",',
    '        ]) + "</style>"',
    '        if "supplied-logo-css" not in doc:',
    '            doc = doc.replace("</head>", css + "\\n</head>")',
    '        return doc',
    'except NameError:',
    '    pass',
    END,
]

BLOCK = '\n'.join(block_lines) + '\n'
text = APP_PATH.read_text(encoding='utf-8')
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + BLOCK
APP_PATH.write_text(text, encoding='utf-8')
print('Supplied logo patched into app.py')
