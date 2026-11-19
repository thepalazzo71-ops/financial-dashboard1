"""Model: v6 score with EV-based valuation lenses, compared with the current v6 ranking (all four dashboards).

Current valuation (18 pts) = 18 x best percentile of
   A = market cap / gross profit (lower better)
   B = (P/B) / max(ROE/10%, 0.1)       (lower better)
   C = (avg NI last ~yr / market cap) x (1 + growth capped 0-200%)   (higher better)
Model:
   A' = EV / gross profit
   B  unchanged
   C' = (3-year average NI / EV) x (1 + growth capped 0-200%)
   EV = market cap + net debt (data/.../net_debt.json tier A/B), floored at 5% of market cap;
        market cap when no net debt / financial.  Everything else in the score is unchanged.
Writes docs/valuation-ev-model.xlsx (one tab per dashboard: top 50 before vs after, plus all movers) and prints a summary.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import scoring as S

REGIONS = [('Europe', 'data', 'companies_1000_scored.json'), ('USA & Canada', 'data-us', 'companies_pool_all.json'),
           ('Asia & Pacific', 'data-asia', 'companies_pool_all.json'), ('Europe micro', 'data-micro', 'companies_pool_all.json')]


def avg3(c):
    h = [v for v in (c.get('niHist') or []) if v is not None]
    return sum(h) / len(h) if len(h) >= 4 else c.get('avgNI')


def model(folder, poolf):
    pool = json.load(open(ROOT / folder / poolf))
    ov = json.load(open(ROOT / folder / 'mc_overrides_applied.json'))
    try:
        dl = {k for k in json.load(open(ROOT / folder / 'delisted.json')) if not k.startswith('_')}
    except Exception:
        dl = set()
    try:
        nd = json.load(open(ROOT / folder / 'net_debt.json'))['entries']
    except Exception:
        nd = {}
    base, _ = S.score_pool(pool, ov, {})
    A2, B2, C2, evs = [], [], [], []
    for c, r in zip(pool, base):
        mc, gm = r['mc'], r['gm']
        e = nd.get(c['ticker']) or {}
        has = e.get('tier') in ('A', 'B') and e.get('netDebtUsd') is not None
        ev = max(mc + e['netDebtUsd'], 0.05 * mc) if has and mc else mc
        evs.append((ev, has))
        a, b, _, _ = S.lenses(c, mc, gm)
        A2.append((ev / c['revLTM']) / gm if gm and gm > 0 and c['revLTM'] else None)
        B2.append(b)
        ni = avg3(c)
        g = min(max(c['revGrowth'] or 0, 0), 2.0)
        C2.append((ni / ev) * (1 + g) if ni is not None and ev else None)
    out = []
    for i, (c, r) in enumerate(zip(pool, base)):
        ps = [S.percentile_rank(A2, i, False), S.percentile_rank(B2, i, False), S.percentile_rank(C2, i, True)]
        best = max([p for p in ps if p is not None], default=0)
        val2 = best / 100 * 18
        tot2 = r['total'] - r['val_pts'] + val2
        out.append(dict(t=c['ticker'], n=c['name'], co=c['country'], dl=c['ticker'] in dl, mc=r['mc'], ev=evs[i][0], has_nd=evs[i][1],
                        val1=r['val_pts'], val2=val2, tot1=r['total'], tot2=tot2))
    live = [x for x in out if not x['dl']]
    for k, key in (('r1', 'tot1'), ('r2', 'tot2')):
        for rank, x in enumerate(sorted(live, key=lambda x: -x[key]), 1):
            x[k] = rank
    return live


def main():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    wb.remove(wb.active)
    summary = {}
    for label, folder, poolf in REGIONS:
        rows = model(folder, poolf)
        by1 = sorted(rows, key=lambda x: x['r1'])[:50]
        by2 = sorted(rows, key=lambda x: x['r2'])[:50]
        s1, s2 = {x['t'] for x in by1}, {x['t'] for x in by2}
        summary[label] = dict(n=len(rows), nd=sum(x['has_nd'] for x in rows), overlap=len(s1 & s2),
                              entered=[x for x in by2 if x['t'] not in s1], left=[x for x in by1 if x['t'] not in s2], by1=by1, by2=by2)
        ws = wb.create_sheet(label[:31])
        ws.append([f'{label}: top 50 by v6 score, current valuation vs EV-based valuation model (everything else unchanged)'])
        ws['A1'].font = Font(name='Arial', bold=True, size=12)
        ws.append(['Rank', 'CURRENT: company', 'Country', 'Total', 'Val pts', '', 'MODEL: company', 'Country', 'Total', 'Val pts',
                   'Was rank', 'Net debt used?', 'EV / market cap'])
        for c in ws[2]:
            c.font = Font(name='Arial', bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='2F4B3C')
        for i in range(50):
            a, b = by1[i], by2[i]
            ws.append([i + 1, a['n'], a['co'], round(a['tot1'], 1), round(a['val1'], 1), '', b['n'], b['co'], round(b['tot2'], 1),
                       round(b['val2'], 1), b['r1'], 'yes' if b['has_nd'] else 'no (market cap)', round(b['ev'] / b['mc'], 2) if b['mc'] else None])
            if b['t'] not in s1:
                for col in range(7, 14):
                    ws.cell(row=ws.max_row, column=col).fill = PatternFill('solid', fgColor='E3EFE7')
        ws.append([])
        ws.append(['Biggest movers (whole pool, by rank change)'])
        ws.cell(row=ws.max_row, column=1).font = Font(name='Arial', bold=True)
        ws.append(['Company', 'Country', 'Current rank', 'Model rank', 'Change', 'EV / market cap', 'Net debt used?'])
        movers = sorted(rows, key=lambda x: -abs(x['r1'] - x['r2']))[:40]
        for x in movers:
            ws.append([x['n'], x['co'], x['r1'], x['r2'], x['r1'] - x['r2'], round(x['ev'] / x['mc'], 2) if x['mc'] else None, 'yes' if x['has_nd'] else 'no'])
        for col, w in zip('ABCDEFGHIJKLM', (8, 38, 14, 8, 8, 2, 38, 14, 8, 8, 9, 16, 12)):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if c.font is None or not c.font.bold:
                    c.font = Font(name='Arial', size=10, bold=bool(c.font and c.font.bold), color=(c.font.color if c.font and c.font.color else None))
    out = ROOT / 'docs' / 'valuation-ev-model.xlsx'
    wb.save(out)
    json.dump({k: {kk: (vv if not isinstance(vv, list) else [dict(t=x['t'], n=x['n'], co=x['co'], r1=x['r1'], r2=x['r2'], tot1=round(x['tot1'], 1), tot2=round(x['tot2'], 1), val1=round(x['val1'], 1), val2=round(x['val2'], 1), evmc=round(x['ev'] / x['mc'], 2) if x['mc'] else None, nd=x['has_nd']) for x in vv]) for kk, vv in v.items()} for k, v in summary.items()},
              open(ROOT / 'docs' / 'valuation-ev-model-summary.json', 'w'), ensure_ascii=False, indent=0)
    for k, v in summary.items():
        print(f"{k}: pool {v['n']}, net debt used for {v['nd']}; top-50 overlap {v['overlap']}/50; entered {len(v['entered'])}")
    print('wrote', out)


if __name__ == '__main__':
    main()
