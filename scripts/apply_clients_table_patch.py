#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'app/app.py'
s = p.read_text(encoding='utf-8')

# Убираем сломанные runtime-блоки, если они уже были вставлены.
for start, end in [
    ('# === 3WG CLIENTS TABLE RUNTIME START ===', '# === 3WG CLIENTS TABLE RUNTIME END ==='),
    ('# === 3WG CLIENTS TABLE WIDTH START ===', '# === 3WG CLIENTS TABLE WIDTH END ==='),
]:
    s = re.sub(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', s, flags=re.S)

base_css = 'table{{width:100%;border-collapse:collapse;font-size:14px}}'
clients_css = '''
.clients-table-wrap{{width:max-content!important;max-width:100%!important;overflow-x:auto!important}}
.clients-table{{width:auto!important;min-width:0!important;max-width:none!important;table-layout:fixed!important}}
.clients-table th,.clients-table td{{overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important}}
.clients-table th:nth-child(1),.clients-table td:nth-child(1){{width:46px!important;min-width:46px!important;max-width:46px!important;padding-left:8px!important;padding-right:4px!important;text-align:left!important}}
.clients-table th:nth-child(2),.clients-table td:nth-child(2){{width:170px!important;min-width:170px!important;max-width:170px!important}}
.clients-table th:nth-child(3),.clients-table td:nth-child(3){{width:125px!important;min-width:125px!important;max-width:125px!important}}
.clients-table th:nth-child(4),.clients-table td:nth-child(4){{width:130px!important;min-width:130px!important;max-width:130px!important}}
.clients-table th:nth-child(5),.clients-table td:nth-child(5){{width:110px!important;min-width:110px!important;max-width:110px!important}}
.clients-table th:nth-child(6),.clients-table td:nth-child(6){{width:180px!important;min-width:180px!important;max-width:180px!important}}
.clients-table th:nth-child(7),.clients-table td:nth-child(7){{width:170px!important;min-width:170px!important;max-width:170px!important}}
.clients-table th:nth-child(8),.clients-table td:nth-child(8){{width:105px!important;min-width:105px!important;max-width:105px!important}}
.clients-table th:nth-child(9),.clients-table td:nth-child(9){{width:105px!important;min-width:105px!important;max-width:105px!important}}
.clients-table th:nth-child(10),.clients-table td:nth-child(10){{width:82px!important;min-width:82px!important;max-width:82px!important}}
'''

# Убираем старый CSS моих прошлых попыток.
s = re.sub(r'\n\.clients-(?:table|wrap)[\s\S]*?(?=\n\.[a-zA-Z_-]|\n</style>|\n</head>|\n\s*[a-zA-Z0-9_.#:-]+\{\{|$)', '\n', s)

if '.clients-table-wrap{{width:max-content!important' not in s:
    s = s.replace(base_css, base_css + clients_css, 1)

if '<h2>Клиенты</h2>\n<table>' in s and '<table class="clients-table">' not in s:
    s = s.replace('<h2>Клиенты</h2>\n<table>', '<h2>Клиенты</h2>\n<div class="clients-table-wrap">\n<table class="clients-table">', 1)

marker = '</table>\n</div>\n\n<div class="card">\n<h2>Статус</h2>'
if '<div class="clients-table-wrap">' in s and marker in s:
    s = s.replace(marker, '</table>\n</div>\n</div>\n\n<div class="card">\n<h2>Статус</h2>', 1)

p.write_text(s, encoding='utf-8')
print('clients table layout patched: safe source CSS')
