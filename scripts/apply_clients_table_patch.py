#!/usr/bin/env python3
from pathlib import Path
import re

p = Path('/srv/3wg-panel/app/app.py')
s = p.read_text(encoding='utf-8')

lt = chr(60)
gt = chr(62)

base_css = 'table{{width:100%;border-collapse:collapse;font-size:14px}}'
compact_css = '''
.clients-wrap{{width:100%;overflow-x:auto}}
.clients-table{{display:inline-table!important;width:auto!important;min-width:0!important;max-width:none!important;table-layout:fixed!important}}
.clients-table col.c-id{{width:46px!important}}
.clients-table col.c-name{{width:170px!important}}
.clients-table col.c-proto{{width:125px!important}}
.clients-table col.c-ip{{width:130px!important}}
.clients-table col.c-status{{width:110px!important}}
.clients-table col.c-endpoint{{width:180px!important}}
.clients-table col.c-last{{width:170px!important}}
.clients-table col.c-rx{{width:105px!important}}
.clients-table col.c-tx{{width:105px!important}}
.clients-table col.c-actions{{width:82px!important}}
.clients-table th,.clients-table td{{overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important}}
.clients-table th:nth-child(1),.clients-table td:nth-child(1){{width:46px!important;min-width:46px!important;max-width:46px!important;text-align:left!important;padding-left:8px!important;padding-right:4px!important}}
'''
if '.clients-table{{display:inline-table!important' not in s:
    s = s.replace(base_css, base_css + compact_css, 1)

colgroup = (
    lt + 'colgroup' + gt +
    lt + 'col class="c-id"' + gt +
    lt + 'col class="c-name"' + gt +
    lt + 'col class="c-proto"' + gt +
    lt + 'col class="c-ip"' + gt +
    lt + 'col class="c-status"' + gt +
    lt + 'col class="c-endpoint"' + gt +
    lt + 'col class="c-last"' + gt +
    lt + 'col class="c-rx"' + gt +
    lt + 'col class="c-tx"' + gt +
    lt + 'col class="c-actions"' + gt +
    lt + '/colgroup' + gt
)

old_start = lt + 'h2' + gt + 'Клиенты' + lt + '/h2' + gt + '\n' + lt + 'table' + gt + '\n' + lt + 'thead' + gt
new_start = lt + 'h2' + gt + 'Клиенты' + lt + '/h2' + gt + '\n' + lt + 'div class="clients-wrap"' + gt + '\n' + lt + 'table class="clients-table"' + gt + '\n' + colgroup + '\n' + lt + 'thead' + gt

old_end = lt + '/table' + gt + '\n' + lt + '/div' + gt + '\n\n' + lt + 'div class="card"' + gt + '\n' + lt + 'h2' + gt + 'Статус' + lt + '/h2' + gt
new_end = lt + '/table' + gt + '\n' + lt + '/div' + gt + '\n' + lt + '/div' + gt + '\n\n' + lt + 'div class="card"' + gt + '\n' + lt + 'h2' + gt + 'Статус' + lt + '/h2' + gt

if 'class="clients-table"' not in s:
    s = s.replace(old_start, new_start, 1)
    s = s.replace(old_end, new_end, 1)
else:
    s = re.sub(
        re.escape(lt + 'h2' + gt + 'Клиенты' + lt + '/h2' + gt) + r'\n.*?' + re.escape(lt + 'thead' + gt),
        new_start,
        s,
        count=1,
        flags=re.S,
    )

p.write_text(s, encoding='utf-8')
print('clients table layout patched: targeted clients table only, ID 46px')
