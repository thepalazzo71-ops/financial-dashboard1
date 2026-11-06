"""Build docs/all-data.json: ONE compact dataset with EVERY company of all three
regions (Europe, USA/Canada, Asia/Pacific) - scores and their parts, market cap
+ refresh info, fundamentals, gross margin with its source quality, the research
text, delisted / distress / corporate-action flags. The 'Download ALL data'
button on each dashboard fetches this file and turns it into one Excel workbook
with a tab per region (adding the viewer's own comments client-side).

Scores come from scripts/scoring.py (same v6 model and the same market-cap /
gross-margin overrides the pages are built from), on each region's ALL-SECTOR
pool. Run after build_site*.py; CI runs it too.   Usage: python3 scripts/build_all_data.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from scoring import score_pool

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import price_stats

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "all-data.json"

HEADERS = ['Rank (all)', 'Rank (excl. delisted)', 'Ticker', 'Company', 'Country', 'Delisted', 'Distress flag', 'v6 score',
           'Mkt cap ($M)', 'Mkt cap refreshed', 'Mkt cap source', 'Equity ($M)', 'P/B', 'ROE', 'Rev LTM ($M)', 'Rev growth',
           'Rev consistency', 'Dilution', 'Profit %', 'CFO+ %', 'Dividend %', 'Periods',
           'Gross margin', 'GM quality', 'GM fiscal year', 'GM source link', 'Pts: rev growth', 'Pts: consistency', 'Pts: dilution',
           'Pts: profitability', 'Pts: CFO', 'Pts: track', 'Pts: dividend', 'Pts: gross margin', 'Pts: valuation', 'Non-financial pool',
           'Business description', 'Competitive position', 'Main shareholders', 'Insider ownership', 'Red flags', 'Website',
           'Corporate actions (events)', 'Latest corporate action',
           'Net debt ($M)', 'EV ($M)', 'EV / earnings', 'Net debt basis',
           'Last close', 'Price currency', '5y high', '5y high date', '5y low', '5y low date', 'vs 5y high', 'vs 5y low', '5y range (x)', 'Price as of']
# column kinds the client uses for number formats: pct columns / multiple
PCT_COLS = ['vs 5y high', 'vs 5y low', 'ROE', 'Rev growth', 'Dilution', 'Profit %', 'CFO+ %', 'Dividend %', 'Gross margin']

REGIONS = [
    ('europe', 'Europe', ROOT / 'data', 'companies_1000_scored.json', None),
    ('micro', 'Europe micro', ROOT / 'data-micro', 'companies_pool_all.json', 'companies_pool_nonfinancial.json'),
    ('us', 'USA & Canada', ROOT / 'data-us', 'companies_pool_all.json', 'companies_pool_nonfinancial.json'),
    ('asia', 'Asia & Pacific', ROOT / 'data-asia', 'companies_pool_all.json', 'companies_pool_nonfinancial.json'),
]


def load(path, default):
    return json.load(open(path)) if path.exists() else default


def gm_quality(c):
    if c.get('gm') is None:
        return 'none (pool-median points)'
    if c.get('gmEstimated'):
        return 'ESTIMATE (industry-peer median)'
    st = c.get('gmSourceType')
    if st == 'industry_estimate':
        return 'ESTIMATE (industry-peer median)'
    if st:
        return 'sourced - ' + str(st).replace('_', ' ')
    return 'sourced - ' + ('company filing' if c.get('gmIsVerified') else 'unverified')


def r(x, d):
    return None if x is None else round(float(x), d)


def build_region(key, label, folder, pool_file, nonfin_file):
    pool = json.load(open(folder / pool_file))
    nonfin = {c['ticker'] for c in json.load(open(folder / nonfin_file))} if nonfin_file else None
    mc = load(folder / 'mc_overrides_applied.json', {})
    gmo = load(folder / 'gm_overrides_applied.json', {})
    delisted = {k: v for k, v in load(folder / 'delisted.json', {}).items() if not k.startswith('_')}
    distress = {k: v for k, v in load(folder / 'distress_flags.json', {}).items() if not k.startswith('_')}
    ca = load(folder / 'corporate_actions.json', {})
    nd_all = {}
    if key == 'europe' and (folder / 'net_debt.json').exists():
        nd_all = json.load(open(folder / 'net_debt.json')).get('entries', {})
    ca_by = {}
    for cat, items in ca.items():
        for a in items:
            ca_by.setdefault(a.get('ticker'), []).append((cat, a))
    scored, _ = score_pool(pool, mc, gmo)
    order = sorted(range(len(pool)), key=lambda i: -scored[i]['total'])
    rows, live = [], 0
    for rank, i in enumerate(order, 1):
        c, s = pool[i], scored[i]
        t = c['ticker']
        dl = delisted.get(t)
        if not dl:
            live += 1
        fp = c.get('fixedPts') or {}
        th = c.get('thesis') or {}
        o = mc.get(t)
        evs = sorted(ca_by.get(t, []), key=lambda x: x[1].get('date') or '', reverse=True)
        latest = ''
        if evs:
            cat, a = evs[0]
            latest = f"{a.get('date') or ''} {cat.replace('_', ' ')}: {(a.get('note') or a.get('terms') or '')[:300]}"
        gm_link = c.get('gmSourceUrl') or ''
        if gm_link.startswith('['):
            import re
            m = re.search(r'\((https?://[^)]+)\)', gm_link)
            gm_link = m.group(1) if m else ''
        nd = nd_all.get(t) or {}
        ni = next((x for x in reversed(c.get('niHist') or []) if x is not None), None)
        if nd.get('ltmNetIncomeUsd') is not None:
            ni = nd['ltmNetIncomeUsd']
        ev = (s['mc'] + nd['netDebtUsd']) if nd.get('netDebtUsd') is not None and s['mc'] else None
        nd_cols = [r(nd.get('netDebtUsd'), 1), r(ev, 1), r(ev / ni, 2) if ev and ev > 0 and ni and ni > 0 else None,
                   ('financial - n/a' if nd.get('tier') == 'F' else (f"tier {nd['tier']} {nd.get('currency')} {nd.get('balanceSheetDate')}" if nd.get('tier') else ''))]
        px = price_stats.px_for(t)
        px_cols = ([px['l'], px['cur'], px['h'], px['hd'], px['lo'], px['ld'], r(px['l'] / px['h'] - 1, 4), r(px['l'] / px['lo'] - 1, 4),
                    r(px['h'] / px['lo'], 2), px['d']] if px else [None] * 10)
        rows.append([
            rank, None if dl else live, t, c['name'], c['country'], ('yes ' + (dl.get('date') or '')) if dl else '',
            (distress.get(t) or {}).get('level', ''), r(s['total'], 2),
            r(s['mc'], 1), (o.get('updatedAt') or '')[:10] if o else '', (o.get('source') or '') if o else '', r(c.get('equity'), 1),
            r(s['pb'], 2), r(s['roe'], 3), r(c.get('revLTM'), 1), r(c.get('revGrowth'), 3), r(c.get('revConsistency'), 2),
            r(c.get('dilution'), 3), r(c.get('profitPct'), 2), r(c.get('cfoPct'), 2), r(c.get('divPct'), 2), c.get('nRevPeriods'),
            r(s['gm'], 3), gm_quality(c) if not (gmo.get(t)) else 'edited override', c.get('gmFiscalYear') or '', gm_link,
            r(fp.get('revenue_growth'), 2), r(fp.get('revenue_consistency'), 2), r(fp.get('dilution'), 2), r(fp.get('profitability'), 2),
            r(fp.get('cfo_positive'), 2), r(fp.get('track_record'), 2), r(fp.get('dividend_consistency'), 2), r(s['gm_pts'], 2), r(s['val_pts'], 2),
            ('' if nonfin is None else ('yes' if t in nonfin else 'no')),
            th.get('business_description') or '', th.get('competitive_position') or '', th.get('main_shareholders') or '',
            th.get('insider_ownership') or '', th.get('red_flags') or '', th.get('website') or '',
            len(evs), latest,
        ] + nd_cols + px_cols)
    return {'key': key, 'label': label, 'rows': rows}


def main():
    data = {
        'generated': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'headers': HEADERS, 'pctCols': PCT_COLS,
        'regions': [build_region(*x) for x in REGIONS],
    }
    OUT.write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB): " + ', '.join(f"{g['label']} {len(g['rows'])}" for g in data['regions']))


if __name__ == '__main__':
    main()
