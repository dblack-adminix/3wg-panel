#!/usr/bin/env python3
from pathlib import Path
import re

APP_PATH = Path('/srv/3wg-panel/app/app.py')
START = '# === 3WG CLIENTS TABLE RUNTIME START ==='
END = '# === 3WG CLIENTS TABLE RUNTIME END ==='

RUNTIME = r'''
# === 3WG CLIENTS TABLE RUNTIME START ===
try:
    _page_before_clients_table_runtime = page

    def page(title: str, body: str) -> str:
        doc = _page_before_clients_table_runtime(title, body)
        css = '''
<style id="clients-table-runtime-css">
.clients-table-fixed-box{width:100%!important;overflow-x:auto!important}
.clients-table-fixed{width:auto!important;min-width:1120px!important;max-width:none!important;table-layout:fixed!important}
.clients-table-fixed th,.clients-table-fixed td{overflow:hidden!important;text-overflow:ellipsis!important;white-space:nowrap!important}
.clients-table-fixed th:nth-child(1),.clients-table-fixed td:nth-child(1){width:46px!important;min-width:46px!important;max-width:46px!important;padding-left:8px!important;padding-right:4px!important;text-align:left!important}
.clients-table-fixed th:nth-child(2),.clients-table-fixed td:nth-child(2){width:170px!important;min-width:170px!important;max-width:170px!important}
.clients-table-fixed th:nth-child(3),.clients-table-fixed td:nth-child(3){width:125px!important;min-width:125px!important;max-width:125px!important}
.clients-table-fixed th:nth-child(4),.clients-table-fixed td:nth-child(4){width:130px!important;min-width:130px!important;max-width:130px!important}
.clients-table-fixed th:nth-child(5),.clients-table-fixed td:nth-child(5){width:110px!important;min-width:110px!important;max-width:110px!important}
.clients-table-fixed th:nth-child(6),.clients-table-fixed td:nth-child(6){width:180px!important;min-width:180px!important;max-width:180px!important}
.clients-table-fixed th:nth-child(7),.clients-table-fixed td:nth-child(7){width:170px!important;min-width:170px!important;max-width:170px!important}
.clients-table-fixed th:nth-child(8),.clients-table-fixed td:nth-child(8){width:105px!important;min-width:105px!important;max-width:105px!important}
.clients-table-fixed th:nth-child(9),.clients-table-fixed td:nth-child(9){width:105px!important;min-width:105px!important;max-width:105px!important}
.clients-table-fixed th:nth-child(10),.clients-table-fixed td:nth-child(10){width:82px!important;min-width:82px!important;max-width:82px!important}
</style>
'''
        js = '''
<script id="clients-table-runtime-js">
(function(){
  function fixClientsTable(){
    var heads = Array.prototype.slice.call(document.querySelectorAll('h2'));
    var h = heads.find(function(x){ return (x.textContent || '').trim() === 'Клиенты'; });
    if (!h) return;
    var card = h.closest('.card') || h.parentElement;
    if (!card) return;
    var table = card.querySelector('table');
    if (!table) return;
    table.classList.add('clients-table-fixed');
    table.style.width = 'auto';
    table.style.minWidth = '1120px';
    table.style.maxWidth = 'none';
    table.style.tableLayout = 'fixed';
    var widths = ['46px','170px','125px','130px','110px','180px','170px','105px','105px','82px'];
    Array.prototype.forEach.call(table.rows, function(row){
      Array.prototype.forEach.call(row.cells, function(cell, i){
        if (!widths[i]) return;
        cell.style.width = widths[i];
        cell.style.minWidth = widths[i];
        cell.style.maxWidth = widths[i];
        cell.style.overflow = 'hidden';
        cell.style.textOverflow = 'ellipsis';
        cell.style.whiteSpace = 'nowrap';
        if (i === 0) {
          cell.style.paddingLeft = '8px';
          cell.style.paddingRight = '4px';
          cell.style.textAlign = 'left';
        }
      });
    });
    if (!table.parentElement.classList.contains('clients-table-fixed-box')) {
      var box = document.createElement('div');
      box.className = 'clients-table-fixed-box';
      table.parentNode.insertBefore(box, table);
      box.appendChild(table);
    }
  }
  document.addEventListener('DOMContentLoaded', fixClientsTable);
  fixClientsTable();
  setTimeout(fixClientsTable, 100);
  setTimeout(fixClientsTable, 600);
})();
</script>
'''
        if 'clients-table-runtime-css' not in doc:
            doc = doc.replace('</head>', css + '\n</head>')
        if 'clients-table-runtime-js' not in doc:
            doc = doc.replace('</body>', js + '\n</body>')
        return doc
except NameError:
    pass
# === 3WG CLIENTS TABLE RUNTIME END ===
'''.strip() + '\n'

text = APP_PATH.read_text(encoding='utf-8')
text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S).rstrip() + '\n\n' + RUNTIME
APP_PATH.write_text(text, encoding='utf-8')
print('clients table runtime layout patch applied')
