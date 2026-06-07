#!/usr/bin/env python3
from pathlib import Path
import re

p = Path('/srv/3wg-panel/app/app.py')
s = p.read_text(encoding='utf-8')

lt = chr(60)
gt = chr(62)

# Убираем все старые варианты моего CSS для таблицы, чтобы они не конфликтовали.
s = re.sub(r'\n\.clients-table\{\{.*?white-space:nowrap!important\}\}', '', s, flags=re.S)
s = re.sub(r'\n\.clients-table\{\{.*?text-overflow:ellipsis\}\}', '', s, flags=re.S)

base_css = 'table{{width:100%;border-collapse:collapse;font-size:14px}}'
compact_css = '''
.clients-wrap{{width:100%;overflow-x:auto}}
.clients-table{{width:max-content!important;min-width:1180px!important;max-width:none!important;table-layout:auto!important}}
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
.clients-table th:nth-child(2),.clients-table td:nth-child(2){{width:170px!important;min-width:170px!important;max-width:170px!important}}
.clients-table th:nth-child(3),.clients-table td:nth-child(3){{width:125px!important;min-width:125px!important;max-width:125px!important}}
.clients-table th:nth-child(4),.clients-table td:nth-child(4){{width:130px!important;min-width:130px!important;max-width:130px!important}}
'''
if '.clients-wrap{{width:100%;overflow-x:auto}}' not in s:
    s = s.replace(base_css, base_css + compact_css, 1)

plain_table = lt + 'table' + gt + '\n' + lt + 'thead' + gt
full_colgroup = (
    lt + 'table class="clients-table"' + gt + '\n' +
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
    lt + '/colgroup' + gt + '\n' +
    lt + 'thead' + gt
)

# Если таблица ещё обычная — превращаем её в нормальную clients-table с colgroup всех колонок.
if lt + 'table class="clients-table"' + gt not in s:
    s = s.replace(plain_table, full_colgroup, 1)
else:
    # Если класс уже есть, заменяем старый неполный colgroup на полный.
    s = re.sub(
        re.escape(lt + 'table class="clients-table"' + gt) + r'\n' + re.escape(lt + 'colgroup' + gt) + r'.*?' + re.escape(lt + '/colgroup' + gt) + r'\n' + re.escape(lt + 'thead' + gt),
        full_colgroup,
        s,
        count=1,
        flags=re.S,
    )

# Заворачиваем только таблицу клиентов в scroll-wrapper, чтобы таблица не растягивала ячейки на всю карточку.
if 'class="clients-wrap"' not in s:
    s = s.replace(lt + 'table class="clients-table"' + gt, lt + 'div class="clients-wrap"' + gt + '\n' + lt + 'table class="clients-table"' + gt, 1)
    s = s.replace(lt + '/table' + gt + '\n' + lt + '/div' + gt + '\n\n' + lt + 'div class="card"' + gt + '\n' + lt + 'h2' + gt + 'Статус' + lt + '/h2' + gt,
                  lt + '/table' + gt + '\n' + lt + '/div' + gt + '\n' + lt + '/div' + gt + '\n\n' + lt + 'div class="card"' + gt + '\n' + lt + 'h2' + gt + 'Статус' + lt + '/h2' + gt,
                  1)

p.write_text(s, encoding='utf-8')
print('clients table layout patched: compact colgroup, ID 46px')
