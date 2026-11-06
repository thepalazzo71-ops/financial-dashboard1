"""One-off: add the 5-year price columns / Big swingers hooks to the 4 templates (idempotent)."""
import re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
EU = 'template.html'
for name in ['template.html', 'template_us.html', 'template_asia.html', 'template_micro.html']:
    p = ROOT / 'site' / name
    s = p.read_text()
    if '__SWINGERS_CSS__' in s:
        print(name, 'already patched'); continue
    def sub1(old, new, count=1):
        global s
        assert s.count(old) >= 1, (name, old[:60])
        if count == 1: assert s.count(old) == 1, (name, 'ambiguous', old[:60], s.count(old))
        s = s.replace(old, new, count)
    sub1('</style>', '/*__SWINGERS_CSS__*/\n</style>', 1) if s.count('</style>') == 1 else s.__class__
    if '/*__SWINGERS_CSS__*/' not in s:
        s = s.replace('</style>', '/*__SWINGERS_CSS__*/\n</style>', 1)
    sub1('<div class="modal-backdrop" id="moversModalBackdrop">', '<!--__SWINGERS_HTML__-->\n<div class="modal-backdrop" id="moversModalBackdrop">')
    sub1('function fmtNum(', '/*__SWINGERS_JS__*/\nfunction fmtNum(')
    sub1('<button class="btn ghost small" id="moversBtn">Biggest movers</button>',
         '<button class="btn ghost small" id="moversBtn">Biggest movers</button>\n    <button class="btn ghost small" id="swingersBtn" title="Widest 5-year share-price swings">Big swingers (5y)</button>')
    th = ('<th class="num-col" title="Last close vs the 5-year closing high (always 0 or negative)">vs 5y High</th>\n'
          '          <th class="num-col" title="Last close vs the 5-year closing low (always 0 or positive)">vs 5y Low</th>')
    if name == EU:
        sub1('EV / Earn.</th>', 'EV / Earn.</th>\n          ' + th)
        sub1('${valuationCells(c, mc, isHistorical)}', '${valuationCells(c, mc, isHistorical)}\n        ${priceCells(c, isHistorical)}')
        sub1('<td colspan="12">${renderDetailPanel(row, rank)}', '<td colspan="14">${renderDetailPanel(row, rank)}')
        sub1('${valuationBox(row)}', '${valuationBox(row)}\n      ${priceBox(c)}')
    else:
        sub1('<th class="num-col">Mkt Cap ($M)</th>', '<th class="num-col">Mkt Cap ($M)</th>\n          ' + th)
        m = re.search(r'(<div class="mc-cell">.*?</div>`\}\n\s*</td>)', s, re.S)
        assert m, name
        s = s.replace(m.group(1), m.group(1) + '\n        ${priceCells(c, isHistorical)}', 1)
        sub1('<td colspan="9">${renderDetailPanel(row, rank)}', '<td colspan="11">${renderDetailPanel(row, rank)}')
        sub1('      <div class="breakdown">', '      ${priceBox(c)}\n      <div class="breakdown">')
    sub1('<option value="name">Sort: name</option>',
         '<option value="offHigh">Sort: furthest below 5y high</option>\n      <option value="swing">Sort: widest 5y range</option>\n      <option value="name">Sort: name</option>')
    sub1("    if (sf==='name') return x.c.n.localeCompare(y.c.n);",
         "    if (sf==='offHigh') { const a = pxOf(x.c), b = pxOf(y.c); return (a ? a.vsHi : 9) - (b ? b.vsHi : 9); }\n"
         "    if (sf==='swing') { const a = pxOf(x.c), b = pxOf(y.c); return (b ? b.range : 0) - (a ? a.range : 0); }\n"
         "    if (sf==='name') return x.c.n.localeCompare(y.c.n);")
    p.write_text(s)
    print(name, 'patched')
