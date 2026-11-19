#!/usr/bin/env python3
"""Merge Yahoo dividend history (<folder>/dividends_yahoo.json, from fetch_yahoo_dividends.py) into the pools for companies
whose Capital IQ extract has no dividend data.

  python3 scripts/add_div_hist.py            # first: raw Capital IQ history (resets divHist for every company)
  python3 scripts/merge_dividends.py         # then: Yahoo fill for the all-null ones  (both are idempotent, run in this order)

Per company (only when Yahoo shows evidence: dividend events or a cash-flow dividend figure; a company with neither stays "not
reported", because Yahoo's coverage of some exchanges is thin):
  divHist  = cash dividends paid per slot in USD m where a fiscal-year figure exists (else null)
  divFlags = 1/0 per slot: a dividend was paid in that 12-month window (Yahoo events or cash flow)
  divSrc   = 'yahoo'
  divPct   = paid slots among the last nRevPeriods slots / nRevPeriods   (same definition as the Capital IQ-based score)
  fixedPts.dividend_consistency = divPct x 4, fixedSumNoGm moved by the difference (the score then follows via score_pool).
Prints how many scores and top-50 places change.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoring as S

ROOT = Path(__file__).resolve().parent.parent
REGIONS = {
    'data': ['companies_1000_scored.json', 'companies_pool_all.json', 'companies_pool_nonfinancial.json'],
    'data-us': ['companies_pool_all.json', 'companies_pool_nonfinancial.json'],
    'data-asia': ['companies_pool_all.json', 'companies_pool_nonfinancial.json'],
    'data-micro': ['companies_pool_all.json', 'companies_pool_nonfinancial.json'],
}


def usable(e):
    return bool(e) and e.get('status') == 'ok' and (e.get('nEvents', 0) > 0 or e.get('annual'))


def ranks(pool, ov, gmo):
    sc, _ = S.score_pool(pool, ov, gmo)
    order = sorted(range(len(pool)), key=lambda i: -sc[i]['total'])
    return {pool[i]['ticker']: (r + 1, sc[i]['total']) for r, i in enumerate(order)}


def main():
    for folder, files in REGIONS.items():
        yp = ROOT / folder / 'dividends_yahoo.json'
        if not yp.exists():
            continue
        yd = json.load(open(yp))
        ov = json.load(open(ROOT / folder / 'mc_overrides_applied.json'))
        gmo = S.load_overrides()[1] if folder == 'data' else {}
        main_file = files[0]
        before = ranks(json.load(open(ROOT / folder / main_file)), ov, gmo)
        filled = changed = 0
        for pf in files:
            p = ROOT / folder / pf
            if not p.exists():
                continue
            pool = json.load(open(p))
            for c in pool:
                e = yd.get(c['ticker'])
                if c.get('divSrc') != 'yahoo' and any(v is not None for v in (c.get('divHist') or [])):
                    continue                      # Capital IQ has dividend data for this company: keep it
                if not usable(e):
                    continue
                n = c.get('nRevPeriods') or 0
                c['divHist'] = e['amounts']
                c['divFlags'] = e['flags']
                c['divSrc'] = 'yahoo'
                new_pct = (sum(e['flags'][-n:]) / n) if n else 0.0
                old_pts = c['fixedPts']['dividend_consistency']
                new_pts = round(new_pct * 4.0, 4)
                c['fixedSumNoGm'] = round(c['fixedSumNoGm'] + (new_pts - old_pts), 4)
                c['fixedPts']['dividend_consistency'] = new_pts
                c['divPct'] = new_pct
                if pf == main_file:
                    filled += 1
                    changed += abs(new_pts - old_pts) > 1e-9
            json.dump(pool, open(p, 'w'), ensure_ascii=False)
        after = ranks(json.load(open(ROOT / folder / main_file)), ov, gmo)
        t50_b = {t for t, (r, _) in before.items() if r <= 50}
        t50_a = {t for t, (r, _) in after.items() if r <= 50}
        gain = sorted(((after[t][1] - before[t][1], t) for t in after), reverse=True)
        print(f'{folder}: {filled} companies filled from Yahoo, {changed} with changed dividend points | '
              f'top-50 turnover {len(t50_a - t50_b)} in / {len(t50_b - t50_a)} out | largest score gain {gain[0][0]:+.2f}')


if __name__ == '__main__':
    main()
