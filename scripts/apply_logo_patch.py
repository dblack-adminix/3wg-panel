#!/usr/bin/env python3
from pathlib import Path
import re

APP_PATH = Path('/srv/3wg-panel/app/app.py')
START = '# === 3WG SUPPLIED LOGO START ==='
END = '# === 3WG SUPPLIED LOGO END ==='

BLOCK = r'''
# === 3WG SUPPLIED LOGO START ===
# Размещаем готовый PNG логотип пользователя в текущем интерфейсе.
LOGO_PATH_SUPPLIED = APP_DIR / 'static' / 'logogrin.png'


@app.get('/static/logogrin.png')
def static_logogrin_supplied():
    if not LOGO_PATH_SUPPLIED.exists():
        raise HTTPException(status_code=404, detail='Logo not found')
    return FileResponse(LOGO_PATH_SUPPLIED)


try:
    _page_before_supplied_logo = page

    def page(title: str, body: str) -> str:
        doc = _page_before_supplied_logo(title, body)

        old_brand = '''
  <div class="neo-brand">
    <div class="neo-logo">3</div>
    <div>
      <div class="neo-brand-title">3WG</div>
      <div class="neo-brand-sub">NODE PANEL</div>
    </div>
  </div>
'''
        new_brand = '''
  <div class="neo-brand neo-brand-supplied-logo">
    <img class="supplied-logo-img" src="/static/logogrin.png" alt="3WG" loading="eager">
  </div>
'''
        if old_brand in doc:
            doc = doc.replace(old_brand, new_brand, 1)

        # На случай, если старый brand уже чуть поменялся, заменяем через regex.
        doc = re.sub(
            r'<div class="neo-brand">\s*<div class="neo-logo">3</div>\s*<div>\s*<div class="neo-brand-title">3WG</div>\s*<div class="neo-brand-sub">NODE PANEL</div>\s*</div>\s*</div>',
            '<div class="neo-brand neo-brand-supplied-logo"><img class="supplied-logo-img" src="/static/logogrin.png" alt="3WG" loading="eager"></div>',
            doc,
            count=1,
            flags=re.S,
        )

        css = '''
<style id="supplied-logo-css">
.neo-brand-supplied-logo {
  display: flex !important;
  align-items: center !important;
  justify-content: flex-start !important;
  min-height: 46px !important;
  padding: 0 0 18px !important;
  margin: 0 0 18px !important;
  border-bottom: 1px dashed rgba(64,82,106,.55) !important;
}
.supplied-logo-img {
  display: block !important;
  width: 178px !important;
  max-width: 178px !important;
  height: auto !important;
  max-height: 46px !important;
  object-fit: contain !important;
  filter: drop-shadow(0 0 12px rgba(151,216,18,.16));
}
.neo-title-icon {
  background-image: url('/static/logogrin.png') !important;
  background-size: contain !important;
  background-repeat: no-repeat !important;
  background-position: center !important;
  color: transparent !important;
  text-indent: -999px !important;
  overflow: hidden !important;
  width: 54px !important;
  border: 0 !important;
  background-color: transparent !important;
}
.login-card .logo {
  background-image: url('/static/logogrin.png') !important;
  background-repeat: no-repeat !important;
  background-size: contain !important;
  background-position: left center !important;
  color: transparent !important;
  min-height: 50px !important;
  text-indent: -999px !important;
  overflow: hidden !important;
}
</style>
'''
        if 'supplied-logo-css' not in doc:
            doc = doc.replace('</head>', css + '\n</head>')
        return doc

except NameError:
    pass
# === 3WG SUPPLIED LOGO END ===
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + BLOCK
APP_PATH.write_text(text, encoding='utf-8')
print('Supplied logo patched into app.py')
