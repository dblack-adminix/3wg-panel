#!/usr/bin/env python3
from pathlib import Path
import re

APP_PATH = Path('/srv/3wg-panel/app/app.py')
text = APP_PATH.read_text(encoding='utf-8')


def set_radius(selector: str, value: str) -> None:
    global text
    pattern = r'(' + re.escape(selector) + r'\{\{.*?border-radius:)\s*[^;]+(;.*?\}\})'
    text = re.sub(pattern, r'\g<1>' + value + r'\g<2>', text, count=1, flags=re.S)

# Login screen: same sharper radius as the main panel cards/buttons.
set_radius('.login-card', '8px')
set_radius('input', '8px')
set_radius('button', '8px')
set_radius('.login-error', '8px')

APP_PATH.write_text(text, encoding='utf-8')
print('login radius patched to 8px')
