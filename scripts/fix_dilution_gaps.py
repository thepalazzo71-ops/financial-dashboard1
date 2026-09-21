"""One-off (but re-runnable) fix for companies with dilution=null in
data/companies_1000_scored.json.

Background: 84 of the 1000 companies in the scored pool had `dilution:
null`, which the v6 model scores as 0/12 points (the worst possible
dilution score) -- but the underlying shares-outstanding data needed to
compute a real value was simply missing from the scored-pool JSON, not
from the original Capital IQ extract. This was discovered when a prior
AI-generated run (20 Mar 2026) had ProCook Group plc (LSE:PROC) ranked
#100, but the current scored pool had it at #508 -- entirely explained by
this one missing field.

This script recomputes dilution from data/raw/Europe_15m-1B.xls (the raw
Capital IQ "Weighted Avg. Diluted Shares Out." columns, 10 LTM snapshots
matching the revenue/NI history already in the pool) and applies the same
dilution-points formula the rest of the pool already used -- reverse-
engineered from existing (dilution, points) pairs in the data and cross-
checked against multiple known-good companies before use:

  dilution <= 0.10            -> 12.0
  0.10 < dilution <= 0.15     -> 12.0 - (dilution - 0.10) * 72.0
  0.15 < dilution <= 0.20     -> 8.4  - (dilution - 0.15) * 168.0
  dilution > 0.20             -> 0.0

Dilution itself is (last reported shares / first reported shares) - 1,
using the earliest and latest non-missing values in the 10-period
history (CapIQ uses both blank cells and literal 0.0 as "not reported"
for this field -- 0.0 is filtered out here since no real company has
zero diluted shares outstanding). This exactly matches how dilution is
already computed for the other ~900 companies in the pool that do have
non-null values (verified against BIT:FNM and XTRA:TMV, both of which
have missing early periods).

Of the 84 gaps, 69 had enough real share data to compute a value; the
other 15 have no shares-outstanding data at all across all 10 periods
and remain unresolved (still dilution=null, 0 points) -- there is
nothing to compute them from until a better-covered source appears.

Effect: recomputing 69 companies' dilution changes their total score,
which reshuffles rankFull for the whole 1000-pool. Run this, then
scripts/build_site.py to regenerate the dashboard with the corrected
rankings.

Usage: python3 scripts/fix_dilution_gaps.py
"""
import xlrd

from scoring import ROOT, load_companies

import json

RAW_XLS = ROOT / "data" / "raw" / "Europe_15m-1B.xls"
POOL_PATH = ROOT / "data" / "companies_1000_scored.json"

SHARES_COL_START = 57  # "Weighted Avg. Diluted Shares Out. [LTM - 36]"
SHARES_COL_END = 67    # exclusive; 10 columns through "[LTM]"
TICKER_COL = 1
HEADER_ROW = 7


def dilution_points(d):
    if d <= 0.10:
        return 12.0
    if d <= 0.15:
        return 12.0 - (d - 0.10) * 72.0
    if d <= 0.20:
        return 8.4 - (d - 0.15) * 168.0
    return 0.0


def load_shares_by_ticker():
    wb = xlrd.open_workbook(RAW_XLS)
    ws = wb.sheet_by_name('Screening')
    shares_by_ticker = {}
    for r in range(HEADER_ROW + 1, ws.nrows):
        ticker = ws.cell_value(r, TICKER_COL)
        if not ticker:
            continue
        vals = []
        for c in range(SHARES_COL_START, SHARES_COL_END):
            v = ws.cell_value(r, c)
            vals.append(v if isinstance(v, (int, float)) and v != 0 else None)
        shares_by_ticker[ticker] = vals
    return shares_by_ticker


FIXED_DIMS = ['revenue_growth', 'revenue_consistency', 'dilution', 'profitability',
              'cfo_positive', 'track_record', 'dividend_consistency']


def main():
    shares_by_ticker = load_shares_by_ticker()
    companies = load_companies()

    fixed, not_found, insufficient = [], [], []
    for c in companies:
        if c['dilution'] is not None:
            continue
        shares = shares_by_ticker.get(c['ticker'])
        if shares is None:
            not_found.append(c['ticker'])
            continue
        non_missing = [v for v in shares if v is not None]
        if len(non_missing) < 2:
            insufficient.append(c['ticker'])
            continue
        dilution = (non_missing[-1] / non_missing[0]) - 1
        c['dilution'] = dilution
        c['fixedPts']['dilution'] = round(dilution_points(dilution), 4)
        c['fixedSumNoGm'] = round(sum(c['fixedPts'][k] for k in FIXED_DIMS), 4)
        c['fixedSum'] = round(c['fixedSumNoGm'] + c['gmPtsUsed'], 4)
        c['total'] = round(c['fixedSum'] + c['valPts'], 4)
        fixed.append(c['ticker'])

    companies.sort(key=lambda c: -c['total'])
    for i, c in enumerate(companies):
        c['rankFull'] = i + 1

    with open(POOL_PATH, 'w') as f:
        json.dump(companies, f)

    print(f'fixed: {len(fixed)}, not_found_in_raw: {len(not_found)}, '
          f'insufficient_data: {len(insufficient)}')
    if insufficient:
        print('still unresolved (no shares data at all):', insufficient)


if __name__ == '__main__':
    main()
