"""One-off (re-runnable) fix for the IPO-era share-count artefact in the
dilution gate - see scripts/dilution_rule.py for the rule.

For each pool (Europe, USA/Canada) it
  1. re-measures dilution for companies already in the pool (a stub at the
     start of the series can only have overstated it) and updates the
     dilution score if the banded points change, and
  2. adds companies from the raw Capital IQ extract that were rejected ONLY
     because the stub made dilution look > 20% and that pass every other
     gate and the corrected dilution gate. They are appended flagged
     `dilutionAdjusted: true`; GM starts as the pool-median fallback and
     the thesis empty until researched.

Usage: python3 scripts/ipo_artefact_fix.py   (then scripts/build_site.py and
build_site_us.py; the build resyncs ranks). Idempotent.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_us_pool as I
import us_scoring as U
from dilution_rule import measure_dilution

ROOT = Path(__file__).resolve().parent.parent
REGIONS = [
    ('Europe', ROOT / 'data/raw/Europe_15m-1B.xls', [ROOT / 'data/companies_1000_scored.json'], True),
    ('USA/Canada', ROOT / 'data-us/raw/USA_and_Canada_15m-1B.xls',
     [ROOT / 'data-us/companies_pool_all.json', ROOT / 'data-us/companies_pool_nonfinancial.json'], False),
]


def candidate(row):
    """build_company() with the shares gate switched off, dilution then
    measured with the corrected rule. Returns (company, ipoAdjusted) or None."""
    shares = I.series(row, I.SHARES_COLS, treat_zero_missing=True)
    dil, adjusted = measure_dilution(shares)
    if dil is None or dil > 0.20:
        return None
    blank = list(row)
    for col in I.SHARES_COLS:
        blank[col] = 0.0
    c = I.build_company(blank)
    if not c:
        return None
    c['dilution'], c['dilutionDataMissing'] = dil, False
    return c, adjusted


def main():
    for region, raw, pool_paths, europe in REGIONS:
        I.RAW = raw
        rows = {r[I.COL_TICKER]: r for r in I.load_raw_rows()}
        for path in pool_paths:
            pool = json.load(open(path))
            have = {c['ticker'] for c in pool}
            changed = 0
            for c in pool:
                r = rows.get(c['ticker'])
                if not r or c.get('dilution') is None:
                    continue
                dil, adj = measure_dilution(I.series(r, I.SHARES_COLS, treat_zero_missing=True))
                if adj and U.dilution_points(dil) != U.dilution_points(c['dilution']):
                    c['dilution'] = dil
                    c['fixedPts']['dilution'] = round(U.dilution_points(dil), 4)
                    c['fixedSumNoGm'] = round(sum(v for v in c['fixedPts'].values() if v is not None), 4)
                    c['dilutionAdjusted'] = True
                    changed += 1
                    print(f'  {region}: re-scored {c["ticker"]} dilution -> {dil:.3f}')
            added = []
            nonfin_only = path.name.endswith('nonfinancial.json')
            for tk, r in rows.items():
                if tk in have:
                    continue
                got = candidate(r)
                if not got or not got[1]:
                    continue
                c, _ = got
                if nonfin_only and c['is_financial_sector']:
                    continue
                c['dilutionAdjusted'] = True
                c['fixedPts'], c['fixedSumNoGm'] = U.compute_fixed_pts(dict(c, gm=None))
                c['gm'] = None
                c['hasThesis'] = False
                c['thesis'] = None
                c['industry'], c['archetype'] = None, None
                if europe:
                    c['roe'] = (c['avgNI'] / c['equity']) if (c['avgNI'] is not None and c['equity']) else None
                    c.pop('is_financial_sector', None)
                    c['gmFiscalYear'], c['gmSourceType'], c['gmSourceUrl'] = None, None, None
                    c['gmPts'], c['gmPtsUsed'], c['gmIsFallback'] = None, None, True
                else:
                    c['gmIsVerified'] = False
                have.add(tk)
                added.append(c)
            pool.extend(added)
            json.dump(pool, open(path, 'w'))
            print(f'{region} {path.name}: {changed} re-scored, {len(added)} added, pool now {len(pool)}')


if __name__ == '__main__':
    main()
