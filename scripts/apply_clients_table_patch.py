#!/usr/bin/env python3
from pathlib import Path

p = Path('/srv/3wg-panel/app/app.py')
s = p.read_text(encoding='utf-8')

old_css = 'table{{width:100%;border-collapse:collapse;font-size:14px}}'
add_css = '\n.clients-table{{table-layout:fixed!important}}\n.clients-table col.c-id{{width:42px!important}}\n.clients-table col.c-name{{width:150px!important}}\n.clients-table col.c-proto{{width:115px!important}}\n.clients-table col.c-ip{{width:115px!important}}\n.clients-table th:nth-child(1),.clients-table td:nth-child(1){{width:42px!important;min-width:42px!important;max-width:42px!important;padding-left:8px!important;padding-right:4px!important;text-align:left!important}}\n.clients-table th:nth-child(2),.clients-table td:nth-child(2){{width:150px!important;min-width:150px!important;max-width:150px!important}}\n.clients-table th:nth-child(3),.clients-table td:nth-child(3){{width:115px!important;min-width:115px!important;max-width:115px!important}}\n.clients-table th:nth-child(4),.clients-table td:nth-child(4){{width:115px!important;min-width:115px!important;max-width:115px!important}}\n.clients-table th,.clients-table td{{overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important}}'

# Удаляем старый вариант CSS, если он уже был вставлен предыдущим патчем.
old_add_css = '\n.clients-table{{table-layout:fixed}}\n.clients-table .c-id{{width:64px}}\n.clients-table .c-name{{width:220px}}\n.clients-table .c-proto{{width:130px}}\n.clients-table .c-ip{{width:140px}}\n.clients-table th,.clients-table td{{overflow:hidden;text-overflow:ellipsis}}'
s = s.replace(old_add_css, '')

if '.clients-table{{table-layout:fixed!important}}' not in s:
    s = s.replace(old_css, old_css + add_css, 1)

lt = chr(60)
gt = chr(62)
old = lt + 'table' + gt + '\n' + lt + 'thead' + gt
new = lt + 'table class="clients-table"' + gt + '\n' + lt + 'colgroup' + gt + lt + 'col class="c-id"' + gt + lt + 'col class="c-name"' + gt + lt + 'col class="c-proto"' + gt + lt + 'col class="c-ip"' + gt + lt + 'col' + gt + lt + 'col' + gt + lt + 'col' + gt + lt + 'col' + gt + lt + 'col' + gt + lt + 'col' + gt + lt + '/colgroup' + gt + '\n' + lt + 'thead' + gt
if lt + 'table class="clients-table"' + gt not in s:
    s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('clients table layout patched: ID column 42px')
