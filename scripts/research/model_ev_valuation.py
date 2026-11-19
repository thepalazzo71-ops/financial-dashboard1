"""Before/after: v6 ranking with the OLD market-cap valuation lenses vs the LIVE EV-based lenses (all four dashboards).

Old valuation (until Nov 2026; 18 pts = 18 x best percentile of):
   A = market cap / gross profit, B = (P/B) / max(ROE/10%, 0.1), C = (avg NI last ~yr / market cap) x (1 + growth 0-200%)
Live (scripts/scoring.lenses, adopted Nov 2026):
   A = EV / gross profit, B unchanged, C = (3-year average NI / EV) x (1 + growth 0-200%)
   EV = market cap + net debt (net_debt.json tier A/B), net cash credited only up to 50% of market cap;
        market cap when there is no net-debt record or the company is a financial.
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
    gmo = S.load_overrides()[1] if folder == 'data' else {}
    live_sc, _ = S.score_pool(pool, ov, gmo)
    ND = S.net_debt_lookup()
    A1, B1, C1 = [], [], []
    for c, r in zip(pool, live_sc):
        mc, gm = r['mc'], r['gm']
        A1.append((mc / c['revLTM']) / gm if gm and gm > 0 and c['revLTM'] else None)
        B1.append(S.lenses(c, mc, gm)[1])
        g = min(max(c['revGrowth'] or 0, 0), 2.0)
        C1.append((c['avgNI'] / mc) * (1 + g) if c['avgNI'] is not None and mc else None)
    out = []
    for i, (c, r) in enumerate(zip(pool, live_sc)):
        ps = [S.percentile_rank(A1, i, False), S.percentile_rank(B1, i, False), S.percentile_rank(C1, i, True)]
        val1 = max([p for p in ps if p is not None], default=0) / 100 * 18
        tot1 = r['total'] - r['val_pts'] + val1
        nd = ND.get(c['ticker'])
        ev = S.enterprise_value(r['mc'], nd)
        out.append(dict(t=c['ticker'], n=c['name'], co=c['country'], dl=c['ticker'] in dl, mc=r['mc'], ev=ev, has_nd=nd is not None,
                        val1=val1, val2=r['val_pts'], tot1=tot1, tot2=r['total']))
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
        ws.append([f'{label}: top 50 by v6 score, BEFORE (market-cap valuation lenses) vs LIVE (EV-based lenses, net cash capped at 50% of market cap); everything else unchanged'])
        ws['A1'].font = Font(name='Arial', bold=True, size=12)
        ws.append(['Rank', 'BEFORE: company', 'Country', 'Total', 'Val pts', '', 'LIVE: company', 'Country', 'Total', 'Val pts',
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
        ws.append(['Biggest movers (whole pool, by rank change before -> live)'])
        ws.cell(row=ws.max_row, column=1).font = Font(name='Arial', bold=True)
        ws.append(['Company', 'Country', 'Rank before', 'Rank live', 'Change', 'EV / market cap', 'Net debt used?'])
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
