#!/usr/bin/env python3
from pathlib import Path
import re

APP_PATH = Path('/srv/3wg-panel/app/app.py')
START = '# === 3WG VISUAL UI V13 START ==='
END = '# === 3WG VISUAL UI V13 END ==='

BLOCK = '''
# === 3WG VISUAL UI V13 START ===
try:
    _page_before_visual_ui_v13 = page

    def page(title: str, body: str) -> str:
        doc = _page_before_visual_ui_v13(title, body)
        css = "<style id=\"visual-ui-v13\">.card,.stat{border-color:rgba(64,82,106,.78)!important}.stat .n{color:#14f0a0!important}tbody tr:hover{filter:brightness(1.08)!important}</style>"
        if 'visual-ui-v13' not in doc:
            doc = doc.replace('</head>', css + '\\n</head>')
        return doc
except NameError:
    pass
# === 3WG VISUAL UI V13 END ===
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + BLOCK
APP_PATH.write_text(text, encoding='utf-8')
print('Visible classic UI v13 patched into app.py')
